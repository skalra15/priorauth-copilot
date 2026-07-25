"""Grounding verification — the mechanism behind the headline metric.

A criterion or evidence span is *grounded* only if it appears in its source text.
Anything else is a hallucination, and the rate at which it happens is the number
this project leads with.

Normalisation is deliberately conservative: whitespace and case only. Resist the
urge to add fuzzy matching. If you ever do, say so explicitly in the eval report,
because it changes what the headline number means.
"""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    return _WS.sub(" ", text or "").strip().lower()


def span_is_grounded(span: str | None, source: str) -> bool:
    """True if `span` appears verbatim (modulo whitespace/case) in `source`."""
    if not span:
        return False
    return normalize(span) in normalize(source)


def grounding_report(spans: list[str | None], source: str) -> dict[str, float | int]:
    checked = [s for s in spans if s]
    if not checked:
        return {"n": 0, "grounded": 0, "hallucinated": 0, "hallucination_rate": 0.0}
    grounded = sum(1 for s in checked if span_is_grounded(s, source))
    return {
        "n": len(checked),
        "grounded": grounded,
        "hallucinated": len(checked) - grounded,
        "hallucination_rate": round(1 - grounded / len(checked), 4),
    }


def ungrounded_spans(spans: list[str | None], source: str) -> list[str]:
    """The actual offending spans — read these, they tell you how it fails."""
    return [s for s in spans if s and not span_is_grounded(s, source)]
