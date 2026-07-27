"""Tests for the stdlib rate limiter in api.py.

Replaced an earlier slowapi-based implementation that returned HTTP 500 on
Render (worked locally, broke in the deployed environment -- never fully
diagnosed, so replaced with a dependency-free version instead of chased
further). This covers the actual limiting behavior directly.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from priorauth.api import _enforce_rate_limit, _request_log


@pytest.fixture(autouse=True)
def _clear_request_log():
    _request_log.clear()
    yield
    _request_log.clear()


def _request(ip: str):
    req = MagicMock()
    req.client.host = ip
    return req


def test_allows_requests_under_the_limit():
    req = _request("1.1.1.1")
    for _ in range(5):
        _enforce_rate_limit(req, max_requests=5, window_seconds=60)


def test_blocks_requests_over_the_limit():
    req = _request("2.2.2.2")
    for _ in range(5):
        _enforce_rate_limit(req, max_requests=5, window_seconds=60)
    with pytest.raises(HTTPException) as exc_info:
        _enforce_rate_limit(req, max_requests=5, window_seconds=60)
    assert exc_info.value.status_code == 429


def test_different_ips_are_tracked_independently():
    req_a = _request("3.3.3.3")
    req_b = _request("4.4.4.4")
    for _ in range(5):
        _enforce_rate_limit(req_a, max_requests=5, window_seconds=60)
    # req_a is now at the limit, but req_b has made no requests yet
    _enforce_rate_limit(req_b, max_requests=5, window_seconds=60)
