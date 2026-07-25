"""Appeal letter drafting. Only runs on likely_deny (see check.py).

Design choice that matters: the model never generates the policy citation itself. It writes
the clinical narrative (why the evidence fell short, what would fix it); the citation is the
criterion's own `source_span`, already verified grounded against the policy text back in
extract.py. That's not a defense-in-depth check bolted on after the fact -- it structurally
can't hallucinate a citation, because it never gets asked to produce one. Every citation is
still re-verified in draft_appeal() anyway, since the project docs's rule is "verify programmatically,"
not "trust the design."
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from . import llm, verify
from .schemas import Criterion, CoverageDecision, CriterionCheck

SYSTEM = """You write the substantive content for a Medicare coverage appeal letter: for each \
criterion that was not met, explain why (based on the clinical note's evidence) and what \
specific documentation or clinical fact would resolve it.

Do not invent or quote policy language yourself -- the exact policy citation is inserted \
separately from verified source data. Focus only on the clinical narrative. Be specific and \
actionable: "provide more documentation" is not useful; "document the patient's most recent \
HbA1c reading" is."""


class AppealPoint(BaseModel):
    criterion_id: str
    explanation: str = Field(description="Why this criterion was not met, grounded in the note's evidence")
    what_would_satisfy: str = Field(description="Specific documentation or clinical facts that would resolve this")


class AppealDraft(BaseModel):
    points: list[AppealPoint]
    closing: str = Field(description="A short closing paragraph for the letter")


def _prompt(title: str, criteria_by_id: dict[str, Criterion], checks_by_id: dict[str, CriterionCheck], unmet: list[str]) -> str:
    lines = [f"Policy: {title}", "", "Criteria that were not met:"]
    for cid in unmet:
        crit = criteria_by_id[cid]
        check = checks_by_id.get(cid)
        lines.append(f"- [{cid}] {crit.text}")
        if check:
            lines.append(f"  Note evidence: {check.evidence_span!r} — {check.reasoning}")
    return "\n".join(lines)


def draft_appeal(
    policy_id: str,
    title: str,
    coverage_text: str,
    criteria: list[Criterion],
    decision: CoverageDecision,
    model: str | None = None,
) -> tuple[str, llm.LLMResponse]:
    if decision.decision != "likely_deny" or not decision.unmet_criteria:
        raise ValueError("draft_appeal only runs on likely_deny decisions with unmet criteria")

    criteria_by_id = {c.id: c for c in criteria}
    checks_by_id = {c.criterion_id: c for c in decision.checks}

    prompt = _prompt(title, criteria_by_id, checks_by_id, decision.unmet_criteria)
    parsed, response = llm.structured(AppealDraft, prompt, system=SYSTEM, model=model)
    points_by_id = {p.criterion_id: p for p in parsed.points}

    unverifiable = []
    body = [f"RE: Prior Authorization Appeal — {policy_id} ({title})", ""]
    for cid in decision.unmet_criteria:
        crit = criteria_by_id[cid]
        if not verify.span_is_grounded(crit.source_span, coverage_text):
            unverifiable.append(cid)
            continue
        point = points_by_id.get(cid)
        body.append(f'Criterion: {crit.text}')
        body.append(f'Policy language ({policy_id}): "{crit.source_span}"')
        if point:
            body.append(f"Why this was not met: {point.explanation}")
            body.append(f"What would resolve this: {point.what_would_satisfy}")
        body.append("")

    if unverifiable:
        raise RuntimeError(
            f"Refusing to draft appeal: citation(s) for {unverifiable} are not grounded in the "
            f"policy text. This should never happen if extract.py's grounding check passed -- "
            f"treat it as a data-integrity bug, not something to paper over."
        )

    body.append(parsed.closing)
    return "\n".join(body), response
