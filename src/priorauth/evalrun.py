"""one reproducible, versioned eval run across extraction + retrieval + checking.

Everything before this phase produced ad-hoc numbers from separate commands. This ties
them into one EvalResult per model, so the model sweep ('s actual differentiator)
is an apples-to-apples comparison, not three different people's idea of "ran the eval."

Cost is computed from every call's stored token counts, cache hit or not -- it represents
the cost to reproduce this eval sweep from scratch, a fixed property of the sweep rather
than an artifact of which calls happened to already be cached when the report was
generated. (An earlier version only summed fresh-call cost; rerunning a fully-cached sweep
then reported $0.00 for every model, which was accurate for "cost of this rerun" but
misleading as a headline number and inconsistent with the same sweep's first, live run.)
Latency stays averaged over fresh calls only, since a cache hit's near-zero latency isn't
a real system property -- it's reported as None when a model's entire sweep was served from
cache. Cache hit rate is reported separately so neither of these is hidden.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import appeal, check, config, db, extract, retrieve, verify
from .schemas import EvalResult, ExtractedCriteria


def _run_extraction_eval(model: str, golden_dir: Path) -> dict:
    files = [f for f in sorted(golden_dir.glob("*.json")) if f.name != ".gitkeep"]
    total_gold = total_pred = total_matched = 0
    all_spans: list[str | None] = []
    all_sources: list[str] = []
    cost = 0.0
    latencies: list[float] = []
    n_calls = n_cached = 0

    for path in files:
        raw = json.loads(path.read_text())
        if not raw.get("criteria"):
            continue
        pid = raw["policy_id"]
        p = db.get_policy(pid)
        if not p:
            continue
        gold = ExtractedCriteria.model_validate({k: v for k, v in raw.items() if not k.startswith("_")})
        try:
            predicted, response = extract.extract_criteria(pid, p["title"], p["coverage_text"], model=model)
        except Exception:
            continue

        n_calls += 1
        cost += response.cost_usd(model)
        if response.cached:
            n_cached += 1
        else:
            latencies.append(response.latency_s)

        result = extract.score_extraction(gold, predicted)
        total_gold += result["n_gold"]
        total_pred += result["n_predicted"]
        total_matched += result["n_matched"]
        spans = [c.source_span for c in predicted.criteria]
        all_spans.extend(spans)
        all_sources.extend([p["coverage_text"]] * len(spans))

    hallucination = 1 - (
        sum(verify.span_is_grounded(s, src) for s, src in zip(all_spans, all_sources)) / len(all_spans)
        if all_spans
        else 0
    )
    return {
        "precision": total_matched / total_pred if total_pred else 0.0,
        "recall": total_matched / total_gold if total_gold else 0.0,
        "hallucination_rate": hallucination,
        "cost": cost,
        "latencies": latencies,
        "n_calls": n_calls,
        "n_cached": n_cached,
    }


def _run_retrieval_eval(queries_path: Path) -> dict:
    """Model-independent -- deterministic lookup + local embeddings, no Claude calls."""
    if not queries_path.exists():
        return {"recall_at_1": None, "recall_at_5": None}
    queries = json.loads(queries_path.read_text())
    r1 = r5 = 0
    for q in queries:
        result = retrieve.retrieve(cpt=q["cpt"], icd10=q["icd10"], state=q["state"], top_k=5)
        ids = [r["policy_id"] for r in result["results"]]
        r1 += ids[:1] == [q["expected_policy_id"]]
        r5 += q["expected_policy_id"] in ids[:5]
    n = len(queries)
    return {"recall_at_1": r1 / n, "recall_at_5": r5 / n}


def _run_checker_eval(model: str, notes_dir: Path) -> dict:
    files = [f for f in sorted(notes_dir.glob("*.json")) if f.name != ".gitkeep"]
    total = correct = actual_abstentions = 0
    should_abstain = correct_abstain = 0
    cost = 0.0
    latencies: list[float] = []
    n_calls = n_cached = 0
    n_deny = n_appeal_ok = n_appeal_failed = 0

    for path in files:
        raw = json.loads(path.read_text())
        pid = raw["policy_id"]
        p = db.get_policy(pid)
        if not p:
            continue
        try:
            predicted, _ = extract.extract_criteria(pid, p["title"], p["coverage_text"], model=model)
            decision, response = check.check_note(pid, predicted.criteria, raw["note_text"], model=model)
        except Exception:
            continue

        n_calls += 1
        cost += response.cost_usd(model)
        if response.cached:
            n_cached += 1
        else:
            latencies.append(response.latency_s)

        checks_by_id = {c.criterion_id: c for c in decision.checks}
        for cid, expected in raw["expected_verdicts"].items():
            actual = checks_by_id.get(cid)
            av = actual.verdict.value if actual else None
            total += 1
            if av == expected:
                correct += 1
            if av == "insufficient_evidence":
                actual_abstentions += 1
            if expected == "insufficient_evidence":
                should_abstain += 1
                if av == "insufficient_evidence":
                    correct_abstain += 1

        if decision.decision == "likely_deny":
            n_deny += 1
            try:
                _, _, _, appeal_response = appeal.draft_appeal(
                    pid, p["title"], p["coverage_text"], predicted.criteria, decision, model=model
                )
                n_appeal_ok += 1
                n_calls += 1
                cost += appeal_response.cost_usd(model)
                if appeal_response.cached:
                    n_cached += 1
                else:
                    latencies.append(appeal_response.latency_s)
            except Exception:
                n_appeal_failed += 1

    return {
        "verdict_accuracy": correct / total if total else 0.0,
        "abstention_rate": actual_abstentions / total if total else 0.0,
        "correct_abstention_rate": correct_abstain / should_abstain if should_abstain else 0.0,
        "n_deny": n_deny,
        "n_appeal_ok": n_appeal_ok,
        "n_appeal_failed": n_appeal_failed,
        "cost": cost,
        "latencies": latencies,
        "n_calls": n_calls,
        "n_cached": n_cached,
    }


def run_full_eval(
    model: str,
    golden_dir: Path | None = None,
    notes_dir: Path | None = None,
    queries_path: Path | None = None,
) -> tuple[EvalResult, dict]:
    """Returns (the EvalResult for the report, extra detail not in that schema)."""
    golden_dir = golden_dir or (config.GOLDEN_DIR / "criteria")
    notes_dir = notes_dir or (config.GOLDEN_DIR / "notes")
    queries_path = queries_path or (config.GOLDEN_DIR / "retrieval_queries.json")

    extraction = _run_extraction_eval(model, golden_dir)
    retrieval = _run_retrieval_eval(queries_path)
    checker = _run_checker_eval(model, notes_dir)

    all_latencies = extraction["latencies"] + checker["latencies"]
    total_cost = extraction["cost"] + checker["cost"]
    total_calls = extraction["n_calls"] + checker["n_calls"]
    total_cached = extraction["n_cached"] + checker["n_cached"]

    result = EvalResult(
        model=model,
        n_cases=total_calls,
        extraction_precision=extraction["precision"],
        extraction_recall=extraction["recall"],
        hallucinated_span_rate=extraction["hallucination_rate"],
        retrieval_recall_at_1=retrieval["recall_at_1"],
        retrieval_recall_at_5=retrieval["recall_at_5"],
        verdict_accuracy=checker["verdict_accuracy"],
        abstention_rate=checker["abstention_rate"],
        correct_abstention_rate=checker["correct_abstention_rate"],
        mean_latency_s=sum(all_latencies) / len(all_latencies) if all_latencies else None,
        total_cost_usd=round(total_cost, 4),
    )
    extra = {
        "cache_hit_rate": total_cached / total_calls if total_calls else None,
        "n_appeal_ok": checker["n_appeal_ok"],
        "n_appeal_failed": checker["n_appeal_failed"],
        "n_deny_cases": checker["n_deny"],
    }
    return result, extra
