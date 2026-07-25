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

MATCH_THRESHOLD = 0.5  # token-overlap needed to count two criteria as the same one


def _tokens(text: str) -> set[str]:
    return set(verify.normalize(text).split())


def _overlap(a: str, b: str) -> float:
    """Best of Jaccard and containment on normalized tokens.

    Jaccard penalizes two spans of very different length even when the shorter
    is entirely inside the longer — common here, since one labeler quotes a bare
    clause and the other quotes the whole sentence around it. Containment
    (intersection / smaller set) catches that case; Jaccard still catches
    same-length rewordings containment would over-credit. Taking the max means
    either signal is enough — this measures "same criterion," not "same
    quoting style."
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    jaccard = inter / len(ta | tb)
    containment = inter / min(len(ta), len(tb))
    return max(jaccard, containment)


def _criterion_text(c: Criterion) -> str:
    return " ".join([c.source_span, *c.sub_conditions])


def _pair_score(g: Criterion, p: Criterion) -> float:
    """Best of two comparisons: source_span alone, and source_span+sub_conditions.

    Neither is strictly better: comparing full text catches cases where both
    sides break a criterion into the same sub-conditions but anchor source_span
    differently (see the earlier documentation-requirements example); comparing
    source_span alone catches the opposite case, where only one side chose to
    itemize sub_conditions and the other left everything in prose — appending
    that extra text would drag an otherwise-clear match below threshold."""
    return max(_overlap(g.source_span, p.source_span), _overlap(_criterion_text(g), _criterion_text(p)))


def match_criteria(
    gold: list[Criterion], predicted: list[Criterion], threshold: float = MATCH_THRESHOLD
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Greedy one-to-one match — see `_overlap` and `_pair_score` for why this
    isn't exact string equality or plain Jaccard on source_span alone.

    Returns (matched (gold_idx, pred_idx) pairs, unmatched gold indices, unmatched
    predicted indices).
    """
    candidates = sorted(
        (
            (_pair_score(g, p), gi, pi)
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
