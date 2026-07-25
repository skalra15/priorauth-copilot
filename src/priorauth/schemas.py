"""Pydantic models. Single source of truth for every structured boundary in the system.

These double as the JSON schemas handed to Claude for tool-use structured output,
so changing a field description here changes model behaviour. Edit deliberately.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# Policies ()
# --------------------------------------------------------------------------


class Policy(BaseModel):
    """A normalized coverage determination. Target shape for ingest.normalize()."""

    policy_id: str = Field(description="e.g. 'L33822' for an LCD, 'NCD-20.4' for an NCD")
    policy_type: Literal["LCD", "NCD"]
    title: str
    jurisdiction: str | None = Field(
        default=None, description="MAC jurisdiction code; None for NCDs (national)"
    )
    states: list[str] = Field(default_factory=list)
    effective_date: str | None = None
    retired_date: str | None = None
    coverage_text: str = Field(
        description=(
            "The 'Coverage Indications, Limitations, and/or Medical Necessity' "
            "section, HTML-stripped. This is what the criteria extractor reads."
        )
    )
    source_url: str | None = None


class PolicyCode(BaseModel):
    policy_id: str
    code: str
    code_system: Literal["CPT", "HCPCS", "ICD10"]
    covered: bool = Field(
        default=True, description="False for explicitly non-covered ICD-10 lists"
    )


# --------------------------------------------------------------------------
# Criteria extraction ()
# --------------------------------------------------------------------------


class CriterionType(str, Enum):
    REQUIRED = "required"
    EXCLUSION = "exclusion"
    INFORMATIONAL = "informational"


class CriterionLogic(str, Enum):
    SINGLE = "single"
    ALL_OF = "all_of"
    ONE_OF = "one_of"


class Criterion(BaseModel):
    id: str = Field(description="Stable short id, e.g. 'c1'")
    text: str = Field(description="The criterion restated as a single testable condition")
    type: CriterionType = Field(
        description=(
            "'required' must be satisfied for coverage. 'exclusion' denies coverage if "
            "TRUE. 'informational' is context that is not itself testable."
        )
    )
    logic: CriterionLogic = Field(
        default=CriterionLogic.SINGLE,
        description="'one_of' when the policy offers alternative ways to satisfy this",
    )
    sub_conditions: list[str] = Field(
        default_factory=list,
        description="Populated only when logic is 'one_of' or 'all_of'",
    )
    temporal: str | None = Field(
        default=None,
        description="Any time constraint, e.g. 'within 6 months prior to ordering'",
    )
    source_span: str = Field(
        description=(
            "VERBATIM substring of the policy text this criterion came from. "
            "Must appear character-for-character in the source. Do not paraphrase."
        )
    )


class ExtractedCriteria(BaseModel):
    policy_id: str
    criteria: list[Criterion]
    notes: str | None = Field(
        default=None, description="Anything ambiguous or unparseable in this policy"
    )


# --------------------------------------------------------------------------
# Synthetic clinical notes ()
# --------------------------------------------------------------------------


class SyntheticNote(BaseModel):
    note_text: str = Field(description="A realistic clinical note. Synthetic -- no real PHI, ever.")
    variant: Literal["meets_all", "fails_one", "ambiguous_one"] = Field(
        description=(
            "'meets_all': documents one coherent, realistic clinical scenario that clearly "
            "satisfies every required criterion that plausibly applies to it, and triggers no "
            "exclusions. 'fails_one': same, except target_criterion_id, which it clearly fails "
            "(or, for an exclusion criterion, clearly triggers). 'ambiguous_one': same, except "
            "target_criterion_id, which the note is silent or ambiguous about."
        )
    )
    target_criterion_id: str | None = Field(
        default=None, description="Required for fails_one/ambiguous_one. Null for meets_all."
    )
    addressed_required_ids: list[str] = Field(
        description=(
            "IDs of the REQUIRED criteria this specific note's clinical scenario actually "
            "addresses and clearly satisfies (excluding target_criterion_id for fails_one, "
            "which is deliberately NOT satisfied). Some policies offer alternative, mutually "
            "exclusive coverage pathways (e.g. 'covered for condition A' OR 'covered as an "
            "adjunct to treatment B') -- one coherent note can only realistically document ONE "
            "such pathway. Required criteria describing a pathway this note's scenario doesn't "
            "pertain to must be OMITTED here, not force-included -- a checker reading this note "
            "should correctly find no evidence for them, not incorrectly find them satisfied."
        )
    )
    triggered_exclusion_ids: list[str] = Field(
        default_factory=list,
        description=(
            "IDs of EXCLUSION criteria this note's scenario actually triggers (the excluding "
            "circumstance is present). Normally empty for meets_all/ambiguous_one. For "
            "fails_one with an exclusion-type target, include exactly that target here."
        ),
    )


# --------------------------------------------------------------------------
# Checking ()
# --------------------------------------------------------------------------


class Verdict(str, Enum):
    MET = "met"
    NOT_MET = "not_met"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class CriterionCheck(BaseModel):
    criterion_id: str
    verdict: Verdict = Field(
        description=(
            "Use 'insufficient_evidence' when the note is silent or ambiguous. "
            "Never guess between met and not_met to avoid abstaining."
        )
    )
    evidence_span: str | None = Field(
        default=None,
        description=(
            "VERBATIM substring of the clinical note supporting this verdict. "
            "Null only when verdict is insufficient_evidence."
        )
    )
    reasoning: str = Field(description="One or two sentences. No hedging boilerplate.")
    confidence: float = Field(ge=0.0, le=1.0)


class CriterionChecks(BaseModel):
    """What the model actually produces for one note. The aggregate `decision`
    below is computed deterministically from these in check.py, not asked of
    the model -- required-met/exclusion-triggered logic is exact and auditable,
    not something to spend a model call re-deriving each time."""

    checks: list[CriterionCheck]


class CoverageDecision(BaseModel):
    policy_id: str
    checks: list[CriterionCheck]
    decision: Literal["likely_approve", "likely_deny", "needs_human_review"]
    unmet_criteria: list[str] = Field(default_factory=list)
    rationale: str


# --------------------------------------------------------------------------
# Eval ()
# --------------------------------------------------------------------------


class EvalResult(BaseModel):
    model: str
    n_cases: int
    extraction_precision: float | None = None
    extraction_recall: float | None = None
    hallucinated_span_rate: float | None = None
    retrieval_recall_at_1: float | None = None
    retrieval_recall_at_5: float | None = None
    verdict_accuracy: float | None = None
    abstention_rate: float | None = None
    correct_abstention_rate: float | None = None
    mean_latency_s: float | None = None
    total_cost_usd: float | None = None
