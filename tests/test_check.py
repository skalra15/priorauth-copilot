"""Tests for the deterministic parts of check.py -- the aggregation rule and
the evidence-grounding enforcement. No model call in either path.
"""

from __future__ import annotations

from priorauth.check import _aggregate, _testable, _verify_evidence
from priorauth.schemas import Criterion, CriterionCheck, CriterionType, Verdict

NOTE = "Patient has diabetes mellitus and is insulin-treated with three daily injections."


def _crit(id_, type_, text="some criterion"):
    return Criterion(id=id_, text=text, type=type_, source_span=text)


def _check(criterion_id, verdict, evidence_span=None, reasoning="because", confidence=0.9):
    return CriterionCheck(
        criterion_id=criterion_id, verdict=verdict, evidence_span=evidence_span,
        reasoning=reasoning, confidence=confidence,
    )


def test_testable_excludes_informational():
    criteria = [
        _crit("c1", CriterionType.REQUIRED),
        _crit("c2", CriterionType.EXCLUSION),
        _crit("c3", CriterionType.INFORMATIONAL),
    ]
    assert [c.id for c in _testable(criteria)] == ["c1", "c2"]


def test_aggregate_approves_when_all_required_met_and_no_exclusion_triggered():
    criteria = [_crit("c1", CriterionType.REQUIRED), _crit("c2", CriterionType.EXCLUSION)]
    checks = [_check("c1", Verdict.MET), _check("c2", Verdict.NOT_MET)]
    decision, unmet, rationale = _aggregate(criteria, checks)
    assert decision == "likely_approve"
    assert unmet == []
    assert "Approved" in rationale


def test_aggregate_denies_on_unmet_required_criterion():
    criteria = [_crit("c1", CriterionType.REQUIRED)]
    checks = [_check("c1", Verdict.NOT_MET)]
    decision, unmet, rationale = _aggregate(criteria, checks)
    assert decision == "likely_deny"
    assert unmet == ["c1"]


def test_aggregate_denies_when_exclusion_criterion_is_triggered():
    # For an exclusion criterion, verdict=met means the excluding circumstance
    # IS present -- that's the bad outcome, and it must deny regardless of
    # every other criterion being satisfied.
    criteria = [_crit("c1", CriterionType.REQUIRED), _crit("c2", CriterionType.EXCLUSION)]
    checks = [_check("c1", Verdict.MET), _check("c2", Verdict.MET)]
    decision, unmet, rationale = _aggregate(criteria, checks)
    assert decision == "likely_deny"
    assert unmet == ["c2"]


def test_aggregate_deny_takes_priority_over_needs_review():
    # A denial should never be softened into "needs review" just because some
    # other, unrelated criterion also happened to be ambiguous -- the failed
    # criterion alone is a sufficient, final answer.
    criteria = [_crit("c1", CriterionType.REQUIRED), _crit("c2", CriterionType.REQUIRED)]
    checks = [_check("c1", Verdict.NOT_MET), _check("c2", Verdict.INSUFFICIENT_EVIDENCE)]
    decision, unmet, _ = _aggregate(criteria, checks)
    assert decision == "likely_deny"
    assert unmet == ["c1"]


def test_aggregate_needs_review_when_insufficient_evidence_and_nothing_failed():
    criteria = [_crit("c1", CriterionType.REQUIRED)]
    checks = [_check("c1", Verdict.INSUFFICIENT_EVIDENCE)]
    decision, unmet, rationale = _aggregate(criteria, checks)
    assert decision == "needs_human_review"
    assert unmet == []
    assert "insufficient evidence" in rationale.lower()


def test_aggregate_missing_check_for_a_criterion_counts_as_needs_review():
    criteria = [_crit("c1", CriterionType.REQUIRED)]
    decision, unmet, _ = _aggregate(criteria, checks=[])
    assert decision == "needs_human_review"


def test_verify_evidence_passes_through_grounded_span():
    checks = [_check("c1", Verdict.MET, evidence_span="has diabetes mellitus")]
    verified = _verify_evidence(checks, NOTE)
    assert verified[0].verdict == Verdict.MET
    assert verified[0].evidence_span == "has diabetes mellitus"


def test_verify_evidence_downgrades_ungrounded_span():
    checks = [_check("c1", Verdict.MET, evidence_span="patient is diabetic")]
    verified = _verify_evidence(checks, NOTE)
    assert verified[0].verdict == Verdict.INSUFFICIENT_EVIDENCE
    assert verified[0].evidence_span is None
    assert "Downgraded" in verified[0].reasoning
