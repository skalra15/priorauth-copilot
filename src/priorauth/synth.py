"""Synthesize clinical notes for the checker eval set.

Three variants per policy:
  meets_all     -- clearly satisfies every APPLICABLE required criterion, triggers no exclusions
  fails_one     -- satisfies everything applicable except one targeted criterion, which it fails
  ambiguous_one -- satisfies everything applicable except one targeted criterion, left unaddressed

The third category is the one that matters: it's where insufficient_evidence has to be
a first-class answer instead of a forced guess.

"Applicable" is doing real work in that first sentence. Some policies offer alternative,
mutually exclusive coverage pathways (e.g. Vitamin B12 injections: covered for pernicious
anemia, OR separately as a pemetrexed/pralatrexate adjunct) -- one coherent patient note can
only realistically document ONE such pathway. An earlier version of this module assumed
"meets_all" meant literally every required criterion in the policy must read as satisfied,
which produced ground truth that was simply wrong for any policy with alternative pathways:
a checker correctly reporting insufficient_evidence on the pathway the note doesn't address
was being scored as an error. Fixed by having the note-writing model itself report which
required criteria its chosen scenario actually addresses (SyntheticNote.addressed_required_ids)
-- expected_verdicts() derives ground truth from that self-report instead of assuming every
criterion is simultaneously in scope.
"""

from __future__ import annotations

from . import llm
from .schemas import Criterion, CriterionType, SyntheticNote, Verdict

SYSTEM = """You write realistic, synthetic clinical notes for a healthcare AI research project. \
These are entirely fictional -- no real patient data, ever -- but should read like an authentic \
physician's note: plausible history, exam findings, and clinical vocabulary.

You'll be given a policy's required and exclusion coverage criteria, and a task:
- meets_all: pick ONE coherent, realistic clinical scenario and write a note that clearly \
satisfies every required criterion that scenario plausibly involves, triggering no exclusions. \
Some policies list alternative coverage pathways (e.g. covered for condition A, OR separately \
as an adjunct to treatment B) -- your note only needs to address the ONE pathway your chosen \
scenario actually involves. Report exactly which required criteria your note addresses in \
addressed_required_ids; leave out any that describe a pathway your scenario doesn't pertain to \
-- don't force unrelated criteria into one note just because they're on the list.
- fails_one: same as meets_all, except target_criterion_id, which your note should clearly fail \
(for a required target: document facts clearly inconsistent with it) or clearly trigger (for an \
exclusion target: document the excluded circumstance as present). Don't soften this. Do NOT \
include the target in addressed_required_ids.
- ambiguous_one: same as meets_all, except target_criterion_id, which your note should simply \
not address, or address too vaguely for a careful reader to tell either way. Do NOT include the \
target in addressed_required_ids.

The note should read as one coherent clinical encounter, not a checklist. Don't mention criterion \
IDs or quote policy language -- translate into what a clinician would actually write."""


def _testable(criteria: list[Criterion]) -> list[Criterion]:
    return [c for c in criteria if c.type in (CriterionType.REQUIRED, CriterionType.EXCLUSION)]


def _prompt(
    policy_id: str, title: str, criteria: list[Criterion], variant: str, target_criterion_id: str | None
) -> str:
    lines = [f"Policy: {policy_id} — {title}", "", "Required/exclusion criteria:"]
    for c in criteria:
        tag = " [TARGET]" if c.id == target_criterion_id else ""
        lines.append(f"- [{c.id}] ({c.type.value}) {c.text}{tag}")
    lines.append("")
    task = f"Task: variant={variant}"
    if target_criterion_id:
        task += f", target_criterion_id={target_criterion_id}"
    lines.append(task)
    return "\n".join(lines)


def synthesize_note(
    policy_id: str,
    title: str,
    criteria: list[Criterion],
    variant: str,
    target_criterion_id: str | None = None,
    model: str | None = None,
) -> tuple[SyntheticNote, llm.LLMResponse]:
    testable = _testable(criteria)
    prompt = _prompt(policy_id, title, testable, variant, target_criterion_id)
    return llm.structured(SyntheticNote, prompt, system=SYSTEM, model=model)


def expected_verdicts(criteria: list[Criterion], note: SyntheticNote) -> dict[str, str]:
    """Ground truth for the synthesized note.

    Required criteria: 'met' only if the note-writer says its scenario actually addresses
    them (addressed_required_ids); otherwise 'insufficient_evidence' -- an unaddressed
    alternative pathway is correctly ambiguous, not correctly false. The one exception is
    fails_one's own target, which is deliberately, explicitly failed.

    Exclusion criteria: 'met' (triggered) only if triggered_exclusion_ids says so; otherwise
    'not_met'. This default assumes an exclusion not mentioned is genuinely absent, which is
    usually right -- but breaks for a handful of policy-shaped edge cases (a blanket
    "this service is never covered" exclusion is unavoidably triggered by any note documenting
    the service at all; a "conditional on a specific prior episode" exclusion may not be
    something a first encounter note should be expected to address either way). Not fixed here:
    doing so generally requires distinguishing those exclusion sub-types, which the current
    schema doesn't encode. Known, disclosed limitation, not something to paper
    over with a special case per policy.
    """
    expected: dict[str, str] = {}
    for c in _testable(criteria):
        if c.id == note.target_criterion_id and note.variant == "fails_one":
            expected[c.id] = (Verdict.NOT_MET if c.type == CriterionType.REQUIRED else Verdict.MET).value
        elif c.id == note.target_criterion_id and note.variant == "ambiguous_one":
            expected[c.id] = Verdict.INSUFFICIENT_EVIDENCE.value
        elif c.type == CriterionType.REQUIRED:
            expected[c.id] = (
                Verdict.MET.value if c.id in note.addressed_required_ids else Verdict.INSUFFICIENT_EVIDENCE.value
            )
        else:
            expected[c.id] = (
                Verdict.MET.value if c.id in note.triggered_exclusion_ids else Verdict.NOT_MET.value
            )
    return expected
