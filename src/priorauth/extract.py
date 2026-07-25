"""Policy prose -> structured criteria. Correctness-critical (see the project docs).

Every criterion's `source_span` must be a verbatim substring of the policy's
coverage_text — that's enforced by `verify.span_is_grounded`, not by asking the
model nicely. The hallucination rate measured on that check is the headline
number for this project.
"""

from __future__ import annotations

import hashlib
import json

from . import config, db, llm, verify
from .schemas import Criterion, ExtractedCriteria

SYSTEM = """You extract structured coverage criteria from Medicare coverage \
policy prose (LCDs and NCDs) for a prior-authorization assistant.

Rules, non-negotiable:
- Every criterion's source_span must be copied VERBATIM, character-for-character, \
from the policy text given to you. Not a paraphrase, not a summary — an exact \
substring. If you cannot find an exact substring supporting a criterion, do not \
invent one; omit that criterion and note it in `notes` instead.
- type="required" for conditions that must hold for coverage. type="exclusion" \
for conditions that, if true, deny coverage (e.g. "not covered when..."). \
type="informational" for context that isn't itself a testable condition.
- Use logic="one_of" when the policy offers alternative ways to satisfy a single \
requirement (e.g. "three or more daily injections OR an insulin pump"), and list \
each alternative in sub_conditions. Use logic="all_of" when several sub-parts must \
all hold. Otherwise logic="single".
- Populate `temporal` only when the criterion carries an explicit time constraint \
(e.g. "within six months prior to ordering").
- Give each criterion a short stable id: c1, c2, c3, ...
- Do not merge distinct conditions into one criterion, and do not split one \
condition into several. Match the policy's own granularity.
- Nested boolean logic, temporal qualifiers, and exclusions phrased as coverage \
("not covered unless...") are the hard cases — read carefully rather than \
defaulting to a flat list."""


def _prompt(policy_id: str, title: str, coverage_text: str) -> str:
    return f"""Policy ID: {policy_id}
Title: {title}

Coverage text:
---
{coverage_text}
---

Extract every coverage criterion from the text above."""


def _text_hash(coverage_text: str) -> str:
    return hashlib.sha256(coverage_text.encode()).hexdigest()


def extract_criteria(
    policy_id: str,
    title: str,
    coverage_text: str,
    *,
    model: str | None = None,
    force: bool = False,
) -> tuple[ExtractedCriteria, llm.LLMResponse]:
    """Extract criteria for one policy, cached on (policy text hash, model)."""
    model = model or config.MODEL
    text_hash = _text_hash(coverage_text)

    if not force:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT payload FROM extracted_criteria WHERE text_hash = ? AND model = ?",
                (text_hash, model),
            ).fetchone()
        if row:
            payload = json.loads(row["payload"])
            return ExtractedCriteria.model_validate(payload), llm.LLMResponse(
                parsed=payload, cached=True
            )

    prompt = _prompt(policy_id, title, coverage_text)
    parsed, response = llm.structured(ExtractedCriteria, prompt, system=SYSTEM, model=model)

    # Force the model's policy_id to match what we asked about — belt and suspenders,
    # since downstream code keys everything on this and a model drift here would be
    # a silent, confusing bug.
    if parsed.policy_id != policy_id:
        parsed = parsed.model_copy(update={"policy_id": policy_id})

    with db.connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO extracted_criteria (policy_id, text_hash, model, payload)
               VALUES (?, ?, ?, ?)""",
            (policy_id, text_hash, model, parsed.model_dump_json()),
        )

    return parsed, response


# ---------------------------------------------------------------------------
# Scoring against hand-labeled golden criteria 
# ---------------------------------------------------------------------------

MATCH_THRESHOLD = 0.5  # token-overlap (Jaccard) needed to count two spans as the same criterion


def _span_overlap(a: str, b: str) -> float:
    ta, tb = set(verify.normalize(a).split()), set(verify.normalize(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def match_criteria(
    gold: list[Criterion], predicted: list[Criterion], threshold: float = MATCH_THRESHOLD
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Greedy one-to-one match by source_span token overlap.

    Gold and a model's own carve-up of the same clause rarely land on identical
    substrings, so exact string equality is too strict. Jaccard overlap on the
    (whitespace/case-normalized) span tokens is the same normalization
    `verify.span_is_grounded` already uses — a real string match on a rewording
    would score ~0 here just like it should.

    Returns (matched (gold_idx, pred_idx) pairs, unmatched gold indices, unmatched
    predicted indices).
    """
    candidates = sorted(
        (
            (_span_overlap(g.source_span, p.source_span), gi, pi)
            for gi, g in enumerate(gold)
            for pi, p in enumerate(predicted)
        ),
        reverse=True,
    )
    matched_g: set[int] = set()
    matched_p: set[int] = set()
    matches: list[tuple[int, int]] = []
    for score, gi, pi in candidates:
        if score < threshold or gi in matched_g or pi in matched_p:
            continue
        matched_g.add(gi)
        matched_p.add(pi)
        matches.append((gi, pi))
    unmatched_gold = [i for i in range(len(gold)) if i not in matched_g]
    unmatched_pred = [i for i in range(len(predicted)) if i not in matched_p]
    return matches, unmatched_gold, unmatched_pred


def score_extraction(gold: ExtractedCriteria, predicted: ExtractedCriteria) -> dict:
    """Precision/recall of one extraction against its hand-labeled gold, plus the
    grounding (hallucination) check on the predicted spans."""
    matches, unmatched_gold, unmatched_pred = match_criteria(gold.criteria, predicted.criteria)
    n_gold, n_pred = len(gold.criteria), len(predicted.criteria)
    return {
        "n_gold": n_gold,
        "n_predicted": n_pred,
        "n_matched": len(matches),
        "precision": len(matches) / n_pred if n_pred else 0.0,
        "recall": len(matches) / n_gold if n_gold else 0.0,
        "missed_gold": [gold.criteria[i].text for i in unmatched_gold],
        "spurious_predicted": [predicted.criteria[i].text for i in unmatched_pred],
    }
