"""Policy retrieval: deterministic code lookup first, semantic embedding fallback.

Coverage policies are explicitly code-indexed (CPT/HCPCS/ICD-10 -> policy), so the
deterministic path should resolve most queries with no model involved at all.
The semantic path exists for the cases it can't reach — free-text symptoms with
no code yet, or a code/state combination with no direct hit.

Local sentence-transformers, not a hosted vector DB: ~1,300 policies fit in
memory as a plain numpy array. No FAISS, no external service.
"""

from __future__ import annotations

import json
from typing import Any

from . import config, db

_model_cache: dict[str, Any] = {}


def _get_model(model_name: str | None = None):
    model_name = model_name or config.EMBEDDING_MODEL
    if model_name not in _model_cache:
        from sentence_transformers import SentenceTransformer

        _model_cache[model_name] = SentenceTransformer(model_name)
    return _model_cache[model_name]


# ---------------------------------------------------------------------------
# Deterministic path: code + state -> policy_codes/policies lookup
# ---------------------------------------------------------------------------


def lookup_by_code(code: str, code_system: str, state: str | None = None) -> list[dict]:
    """Direct code -> policy lookup, ranked by jurisdiction relevance.

    A code can legitimately appear in many policies (different specialties,
    different MAC jurisdictions). Rank so an exact state match comes first,
    then NCDs (national, always in scope), then everything else — this is a
    heuristic, not a guarantee of correctness, and is exactly what the
    recall@k eval below is checking.
    """
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT p.policy_id, p.title, p.policy_type, p.jurisdiction, p.states
            FROM policy_codes pc
            JOIN policies p ON p.policy_id = pc.policy_id
            WHERE pc.code = ? AND pc.code_system = ? AND pc.covered = 1
            """,
            (code, code_system),
        ).fetchall()

    results = []
    for r in rows:
        states = json.loads(r["states"] or "[]")
        if state and state in states:
            score = 2.0
        elif r["policy_type"] == "NCD":
            score = 1.5
        elif not states:
            score = 1.0
        else:
            score = 0.5
        results.append({"policy_id": r["policy_id"], "title": r["title"], "score": score})

    results.sort(key=lambda x: (-x["score"], x["policy_id"]))
    return results


# ---------------------------------------------------------------------------
# Semantic fallback: local embeddings over coverage_text
# ---------------------------------------------------------------------------


def build_index(model_name: str | None = None) -> int:
    """Embed every policy's coverage_text and save the index to data/index/.

    Run this once after ingest/normalize, and again any time coverage_text
    changes. Not run automatically per-query — embedding ~1,300 policies takes
    a while and there's no reason to repeat it on every search.
    """
    import numpy as np

    with db.connect() as conn:
        rows = conn.execute("SELECT policy_id, coverage_text FROM policies").fetchall()
    policy_ids = [r["policy_id"] for r in rows]
    texts = [r["coverage_text"] for r in rows]

    model = _get_model(model_name)
    embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)

    config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.save(config.INDEX_DIR / "embeddings.npy", embeddings.astype("float32"))
    (config.INDEX_DIR / "policy_ids.json").write_text(json.dumps(policy_ids))
    return len(policy_ids)


def _load_index() -> tuple[list[str], Any]:
    import numpy as np

    ids_path = config.INDEX_DIR / "policy_ids.json"
    emb_path = config.INDEX_DIR / "embeddings.npy"
    if not ids_path.exists() or not emb_path.exists():
        raise FileNotFoundError("No embedding index. Run `cli embed` first.")
    policy_ids = json.loads(ids_path.read_text())
    embeddings = np.load(emb_path)
    return policy_ids, embeddings


def semantic_search(query: str, top_k: int = 5, model_name: str | None = None) -> list[tuple[str, float]]:
    """Cosine similarity search over the local embedding index."""
    policy_ids, embeddings = _load_index()
    model = _get_model(model_name)
    query_emb = model.encode([query], normalize_embeddings=True)[0]
    scores = embeddings @ query_emb
    top_idx = scores.argsort()[::-1][:top_k]
    return [(policy_ids[i], float(scores[i])) for i in top_idx]


# ---------------------------------------------------------------------------
# Combined retrieval
# ---------------------------------------------------------------------------


BOTH_CODES_BONUS = 10.0
# Belt-and-suspenders, not the mechanism that actually does the work: measured
# directly (sensitivity sweep 0-50, identical top-1 results at every value on
# the 50-query eval) that the real improvement from combined cpt+icd10 lookup
# over single-code lookup comes from summing two independent jurisdiction
# scores, not from this bonus. Kept anyway as a safeguard for the asymmetric
# case this eval didn't happen to sample: a correct AND-match with weak
# jurisdiction fit (e.g. 0.5+0.5) losing to an incorrect single-code match with
# a strong one (2.0) -- summation alone doesn't guarantee the AND-match wins
# there, this bonus does.


def retrieve(
    cpt: str | None = None,
    icd10: str | None = None,
    state: str | None = None,
    query_text: str | None = None,
    top_k: int = 5,
) -> dict:
    """Deterministic lookup first; semantic fallback only if it comes up empty.

    A single code is often shared by dozens of unrelated policies (e.g. a common
    lab test code referenced by every policy that happens to cover it, for
    entirely different diagnoses) -- ranking on jurisdiction alone doesn't
    disambiguate that. A policy matching BOTH the procedure code and the
    diagnosis code is a much stronger, more specific signal than either alone,
    so it's boosted to always outrank a single-code match.
    """
    by_system: dict[str, dict[str, dict]] = {}
    for code, system in (("cpt", "HCPCS"), ("icd10", "ICD10")):
        value = cpt if code == "cpt" else icd10
        if not value:
            continue
        by_system[system] = {r["policy_id"]: r for r in lookup_by_code(value, system, state)}

    all_policy_ids = set().union(*(d.keys() for d in by_system.values())) if by_system else set()
    deterministic: dict[str, dict] = {}
    for policy_id in all_policy_ids:
        matches = [d[policy_id] for d in by_system.values() if policy_id in d]
        r = dict(matches[0])
        r["score"] = sum(m["score"] for m in matches) + (BOTH_CODES_BONUS if len(matches) > 1 else 0)
        deterministic[policy_id] = r

    if deterministic:
        ranked = sorted(deterministic.values(), key=lambda x: (-x["score"], x["policy_id"]))
        return {"method": "deterministic", "results": ranked[:top_k]}

    if query_text:
        hits = semantic_search(query_text, top_k=top_k)
        results = []
        for pid, score in hits:
            p = db.get_policy(pid)
            results.append({"policy_id": pid, "score": score, "title": p["title"] if p else ""})
        return {"method": "semantic", "results": results}

    return {"method": "none", "results": []}
