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


def _atoms(criteria: list[Criterion]) -> list[tuple[int, str]]:
    """Expand criteria into atomic testable facts, each tagged with its parent
    criterion's index.

    Two independent extractions of the same policy routinely disagree on where
    a "criterion" boundary sits: one bundles a list of exclusions under a
    single parent with sub_conditions, the other gives each item its own
    top-level criterion. Matching whole Criterion objects 1:1 fails hard in
    that case — a bundled gold criterion can only ever match ONE of N
    equivalent unbundled predicted ones, making the other N-1 register as
    false positives even though every one of them is real, grounded content.
    Atomizing both sides to the same granularity before matching (one atom per
    sub_condition when present, else the whole source_span as one atom) fixes
    this regardless of which side bundles."""
    atoms = []
    for i, c in enumerate(criteria):
        for text in (c.sub_conditions if c.sub_conditions else [c.source_span]):
            atoms.append((i, text))
    return atoms


def match_atoms(
    gold: list[Criterion], predicted: list[Criterion], threshold: float = MATCH_THRESHOLD
) -> tuple[list[tuple[int, int]], list[int], list[int], list[tuple[int, str]], list[tuple[int, str]]]:
    """Greedy one-to-one match on atomic facts (see `_atoms`).

    Returns (matched (gold_atom_pos, pred_atom_pos) pairs, unmatched gold atom
    positions, unmatched pred atom positions, gold_atoms, pred_atoms) — positions
    index into the returned atom lists, not the original criteria lists.
    """
    gold_atoms = _atoms(gold)
    pred_atoms = _atoms(predicted)
    scored = sorted(
        (
            (_overlap(g_text, p_text), gpos, ppos)
            for gpos, (_, g_text) in enumerate(gold_atoms)
            for ppos, (_, p_text) in enumerate(pred_atoms)
        ),
        reverse=True,
    )
    used_gold: set[int] = set()
    used_pred: set[int] = set()
    matches: list[tuple[int, int]] = []
    for score, gpos, ppos in scored:
        if score < threshold or gpos in used_gold or ppos in used_pred:
            continue
        used_gold.add(gpos)
        used_pred.add(ppos)
        matches.append((gpos, ppos))
    unmatched_gold = [i for i in range(len(gold_atoms)) if i not in used_gold]
    unmatched_pred = [i for i in range(len(pred_atoms)) if i not in used_pred]
    return matches, unmatched_gold, unmatched_pred, gold_atoms, pred_atoms


def score_extraction(gold: ExtractedCriteria, predicted: ExtractedCriteria) -> dict:
    """Precision/recall of one extraction against its hand-labeled gold, plus the
    grounding (hallucination) check on the predicted spans.

    Scored on atomic facts, not top-level criteria (see `_atoms`/`match_atoms`) --
    "how many criteria" is itself a labeling choice that gold and predicted
    routinely disagree on (bundled vs. one-per-item), and scoring at that level
    would mostly measure which convention was used, not extraction quality.

    Also reports `type_agreement`: of the atoms that matched on content, what
    fraction also agree on the parent criterion's `type` (required/exclusion/
    informational). Matching text alone can't catch a matched pair that
    disagrees on type -- e.g. one side calls a clause an exclusion, the other
    calls the same clause required -- which inverts the actual coverage
    decision downstream. That's a real correctness failure precision/recall
    on span text alone is structurally blind to.
    """
    matches, unmatched_gold, unmatched_pred, gold_atoms, pred_atoms = match_atoms(
        gold.criteria, predicted.criteria
    )
    n_gold, n_pred = len(gold_atoms), len(pred_atoms)

    type_agree = 0
    type_disagreements = []
    for gpos, ppos in matches:
        g_crit = gold.criteria[gold_atoms[gpos][0]]
        p_crit = predicted.criteria[pred_atoms[ppos][0]]
        if g_crit.type == p_crit.type:
            type_agree += 1
        else:
            type_disagreements.append(
                {"text": gold_atoms[gpos][1], "gold_type": g_crit.type.value, "predicted_type": p_crit.type.value}
            )

    return {
        "n_gold": n_gold,
        "n_predicted": n_pred,
        "n_matched": len(matches),
        "precision": len(matches) / n_pred if n_pred else 0.0,
        "recall": len(matches) / n_gold if n_gold else 0.0,
        "type_agree_count": type_agree,
        "type_agreement": type_agree / len(matches) if matches else 0.0,
        "type_disagreements": type_disagreements,
        "missed_gold": [gold_atoms[i][1] for i in unmatched_gold],
        "spurious_predicted": [pred_atoms[i][1] for i in unmatched_pred],
    }
