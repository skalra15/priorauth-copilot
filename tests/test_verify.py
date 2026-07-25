"""Tests for the grounding check — the mechanism behind the headline metric.

If these ever get loosened, the hallucination rate stops meaning what the README
says it means. Treat changes here as changes to the published results.
"""

from priorauth.verify import grounding_report, span_is_grounded, ungrounded_spans

POLICY = """
Continuous glucose monitors are covered when the beneficiary has diabetes mellitus,
is insulin-treated with three or more daily injections, and has been seen by the
treating practitioner within six months prior to ordering the device.
"""


def test_exact_span_is_grounded():
    assert span_is_grounded("has diabetes mellitus", POLICY)


def test_whitespace_and_case_are_forgiven():
    assert span_is_grounded("HAS   DIABETES\n MELLITUS", POLICY)


def test_paraphrase_is_not_grounded():
    # This is the failure mode the metric exists to catch.
    assert not span_is_grounded("patient is diabetic", POLICY)


def test_invented_span_is_not_grounded():
    assert not span_is_grounded("must have failed two prior therapies", POLICY)


def test_empty_span_is_not_grounded():
    assert not span_is_grounded(None, POLICY)
    assert not span_is_grounded("", POLICY)


def test_grounding_report_counts():
    spans = ["has diabetes mellitus", "patient is diabetic", None]
    report = grounding_report(spans, POLICY)
    assert report["n"] == 2
    assert report["grounded"] == 1
    assert report["hallucinated"] == 1
    assert report["hallucination_rate"] == 0.5


def test_ungrounded_spans_are_returned_for_inspection():
    spans = ["has diabetes mellitus", "patient is diabetic"]
    assert ungrounded_spans(spans, POLICY) == ["patient is diabetic"]
