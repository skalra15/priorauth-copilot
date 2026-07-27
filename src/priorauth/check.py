"""Clinical note + extracted criteria -> per-criterion verdicts -> coverage decision.

Correctness-critical. Same grounding discipline as extract.py: every
evidence_span must be a verbatim substring of the NOTE, verified by verify.span_is_grounded.

The aggregate decision (approve/deny/needs_review) is computed deterministically from the
model's per-criterion checks, not asked of the model -- that logic is exact and auditable,
and there's no reason to spend a model call re-deriving something Python can compute exactly.
"""

from __future__ import annotations

from . import llm, verify
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
    """Deterministic decision + a rationale written to actually explain itself.

    The rule this implements -- any single unmet required criterion or triggered
    exclusion denies coverage, full stop, regardless of how many other criteria were
    satisfied -- is not a vote or a score. A policy with 5 satisfied criteria and 1
    failed one is still denied, because Medicare coverage criteria are conjunctive
    (all must hold), not a majority test. That's true and correct, but silent about
    it produces a genuinely confusing UI: someone sees "5 met, 1 not met" and a deny
    decision and reasonably wonders why the majority didn't win. The rationale string
    says so explicitly, every time it's the reason, instead of leaving that inference
    to the reader.
    """
    by_id = {c.id: c for c in criteria}
    by_check = {c.criterion_id: c for c in checks}
    unmet: list[str] = []
    needs_review: list[str] = []
    satisfied = 0
    for crit in criteria:
        check = by_check.get(crit.id)
        if check is None:
            needs_review.append(crit.id)
            continue
        if check.verdict == Verdict.INSUFFICIENT_EVIDENCE:
            needs_review.append(crit.id)
        elif crit.type == CriterionType.REQUIRED and check.verdict == Verdict.NOT_MET:
            unmet.append(crit.id)
        elif crit.type == CriterionType.EXCLUSION and check.verdict == Verdict.MET:
            unmet.append(crit.id)
        else:
            satisfied += 1

    total = len(criteria)

    def _list(ids: list[str]) -> str:
        return "; ".join(f"\"{by_id[cid].text}\"" for cid in ids)

    if unmet:
        offset_note = (
            f" This holds regardless of the other {satisfied} criteria being satisfied -- "
            f"coverage requires every applicable criterion to hold, not a majority of them."
            if satisfied
            else ""
        )
        rationale = (
            f"Denied: {len(unmet)} of {total} criteria failed -- {_list(unmet)}."
            f"{offset_note}"
        )
        return "likely_deny", unmet, rationale

    if needs_review:
        rationale = (
            f"Needs human review: the note has insufficient evidence for {len(needs_review)} "
            f"of {total} criteria -- {_list(needs_review)}. A person needs to confirm these "
            f"before a coverage decision can be made; the system does not guess to avoid "
            f"abstaining."
        )
        return "needs_human_review", unmet, rationale

    rationale = (
        f"Approved: all {total} applicable criteria were satisfied -- every required "
        f"criterion was met and no exclusion was triggered."
    )
    return "likely_approve", unmet, rationale


def _verify_evidence(checks: list[CriterionCheck], note_text: str) -> list[CriterionCheck]:
    """Enforce the grounding rule the module docstring already claims: every
    evidence_span must be a verbatim substring of the note. This was
    previously documented but never actually called -- a live check against
    30 synthetic notes found 3/219 (1.4%) evidence spans were paraphrased or
    "..."-compressed rather than real verbatim quotes, which is exactly the
    hallucination this function exists to catch.

    A span that fails grounding is not trustworthy evidence, so the check is
    downgraded to insufficient_evidence (span dropped) rather than shown to
    the user as if it were a real quote -- consistent with this project's
    abstain-rather-than-guess stance, and gentler than raising, since an
    occasional paraphrase is a model slip on ONE criterion, not the
    should-never-happen data-corruption case appeal.py's citations guard
    against (those are re-quoting an already-verified source_span; this is
    the model quoting fresh from the note for the first time)."""
    verified = []
    for c in checks:
        if c.evidence_span and not verify.span_is_grounded(c.evidence_span, note_text):
            verified.append(
                c.model_copy(
                    update={
                        "verdict": Verdict.INSUFFICIENT_EVIDENCE,
                        "evidence_span": None,
                        "reasoning": (
                            f"{c.reasoning} [Downgraded: the model's cited evidence span was not "
                            f"a verbatim match in the note, so it could not be verified.]"
                        ),
                    }
                )
            )
        else:
            verified.append(c)
    return verified


def check_note(
    policy_id: str, criteria: list[Criterion], note_text: str, model: str | None = None
) -> tuple[CoverageDecision, llm.LLMResponse]:
    testable = _testable(criteria)
    prompt = _prompt(policy_id, testable, note_text)
    parsed, response = llm.structured(CriterionChecks, prompt, system=SYSTEM, model=model)

    checks = _verify_evidence(parsed.checks, note_text)
    decision, unmet, rationale = _aggregate(testable, checks)
    coverage = CoverageDecision(
        policy_id=policy_id, checks=checks, decision=decision, unmet_criteria=unmet, rationale=rationale
    )
    return coverage, response
