"""Clinical note + extracted criteria -> per-criterion verdicts -> coverage decision.

Correctness-critical (see the project docs). Same grounding discipline as extract.py: every
evidence_span must be a verbatim substring of the NOTE, verified by verify.span_is_grounded.

The aggregate decision (approve/deny/needs_review) is computed deterministically from the
model's per-criterion checks, not asked of the model -- that logic is exact and auditable,
and there's no reason to spend a model call re-deriving something Python can compute exactly.
"""

from __future__ import annotations

from . import llm
from .schemas import Criterion, CriterionChecks, CoverageDecision, CriterionCheck, CriterionType, Verdict

SYSTEM = """You determine whether a clinical note satisfies each coverage criterion for a \
Medicare prior-authorization decision.

For each criterion given, decide:
- verdict: "met" -- the note clearly documents facts satisfying this criterion. For an \
exclusion-type criterion, "met" means the EXCLUDING circumstance is documented as present. \
"not_met" -- the note clearly documents facts inconsistent with the criterion (for an exclusion, \
the excluding circumstance is documented as absent). "insufficient_evidence" -- the note doesn't \
address this, or addresses it too vaguely to tell either way.
- evidence_span: VERBATIM substring of the note supporting met/not_met. Null when verdict is \
insufficient_evidence.
- reasoning: one or two sentences, no hedging boilerplate.
- confidence: 0.0-1.0.

One distinction matters for exclusion criteria specifically: if the exclusion names a specific \
procedure, test, or billable action ("test X was performed", "service Y was billed"), the note's \
silence about it means "not_met" (absent) -- clinical and billing notes document what WAS done, \
not an exhaustive list of everything that wasn't, so an unmentioned specific action is reliable \
evidence it didn't happen in this encounter. Reserve insufficient_evidence for exclusions \
describing a broader clinical circumstance or diagnosis the note could plausibly omit without \
meaning to rule it out (e.g. an unscreened comorbidity). Don't apply this distinction to required \
criteria -- silence about a symptom or history item is genuinely ambiguous there.

Never guess between met and not_met to avoid abstaining -- insufficient_evidence is a first-class, \
correct answer when the note doesn't say. Produce exactly one check per criterion listed."""


def _testable(criteria: list[Criterion]) -> list[Criterion]:
    return [c for c in criteria if c.type in (CriterionType.REQUIRED, CriterionType.EXCLUSION)]


def _prompt(policy_id: str, criteria: list[Criterion], note_text: str) -> str:
    lines = [f"Policy: {policy_id}", "", "Criteria to check:"]
    for c in criteria:
        extra = []
        if c.sub_conditions:
            extra.append(f"{c.logic.value}: " + "; ".join(c.sub_conditions))
        if c.temporal:
            extra.append(f"temporal: {c.temporal}")
        suffix = f"  [{'; '.join(extra)}]" if extra else ""
        lines.append(f"- [{c.id}] ({c.type.value}) {c.text}{suffix}")
    lines += ["", "Clinical note:", "---", note_text, "---", "Produce a check for every criterion listed above."]
    return "\n".join(lines)


def _aggregate(criteria: list[Criterion], checks: list[CriterionCheck]) -> tuple[str, list[str], str]:
    by_id = {c.criterion_id: c for c in checks}
    unmet: list[str] = []
    needs_review: list[str] = []
    for crit in criteria:
        check = by_id.get(crit.id)
        if check is None:
            needs_review.append(crit.id)
            continue
        if check.verdict == Verdict.INSUFFICIENT_EVIDENCE:
            needs_review.append(crit.id)
        elif crit.type == CriterionType.REQUIRED and check.verdict == Verdict.NOT_MET:
            unmet.append(crit.id)
        elif crit.type == CriterionType.EXCLUSION and check.verdict == Verdict.MET:
            unmet.append(crit.id)

    if unmet:
        return "likely_deny", unmet, f"{len(unmet)} criterion(s) not satisfied: {', '.join(unmet)}."
    if needs_review:
        return (
            "needs_human_review",
            unmet,
            f"{len(needs_review)} criterion(s) have insufficient evidence in the note: {', '.join(needs_review)}.",
        )
    return "likely_approve", unmet, "All required criteria met; no exclusions triggered."


def check_note(
    policy_id: str, criteria: list[Criterion], note_text: str, model: str | None = None
) -> tuple[CoverageDecision, llm.LLMResponse]:
    testable = _testable(criteria)
    prompt = _prompt(policy_id, testable, note_text)
    parsed, response = llm.structured(CriterionChecks, prompt, system=SYSTEM, model=model)

    decision, unmet, rationale = _aggregate(testable, parsed.checks)
    coverage = CoverageDecision(
        policy_id=policy_id, checks=parsed.checks, decision=decision, unmet_criteria=unmet, rationale=rationale
    )
    return coverage, response
