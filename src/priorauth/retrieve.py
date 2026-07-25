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


def retrieve(
    cpt: str | None = None,
    icd10: str | None = None,
    state: str | None = None,
    query_text: str | None = None,
    top_k: int = 5,
) -> dict:
    """Deterministic lookup first; semantic fallback only if it comes up empty."""
    deterministic: dict[str, dict] = {}
    for code, system in ((cpt, "HCPCS"), (icd10, "ICD10")):
        if not code:
            continue
        for r in lookup_by_code(code, system, state):
            existing = deterministic.get(r["policy_id"])
            if not existing or r["score"] > existing["score"]:
                deterministic[r["policy_id"]] = r

    if deterministic:
        ranked = sorted(deterministic.values(), key=lambda x: (-x["score"], x["policy_id"]))
        return {"method": "deterministic", "results": ranked[:top_k]}

    if query_text:
        hits = semantic_search(query_text, top_k=top_k)
        return {
            "method": "semantic",
            "results": [{"policy_id": pid, "score": score} for pid, score in hits],
        }

    return {"method": "none", "results": []}
