"""Tests for the /metrics endpoint access gate.

Verifies that ``_internal_only`` correctly allows loopback callers and
rejects all others, including those attempting to spoof the now-removed
``X-Goog-Internal`` header.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from api.app_setup import _internal_only


def _make_request(host: str, headers: dict[str, str] | None = None) -> MagicMock:
    """Build a minimal mock Request with the given client host and headers."""
    request = MagicMock()
    request.client = MagicMock()
    request.client.host = host
    request.headers = headers or {}
    return request


# ---------------------------------------------------------------------------
# Allowed callers
# ---------------------------------------------------------------------------


def test_loopback_ipv4_is_allowed():
    """127.0.0.1 must pass through without raising."""
    _internal_only(_make_request("127.0.0.1"))


def test_loopback_ipv6_is_allowed():
    """::1 must pass through without raising."""
    _internal_only(_make_request("::1"))


# ---------------------------------------------------------------------------
# Rejected callers
# ---------------------------------------------------------------------------


def test_non_loopback_ip_is_rejected():
    """A non-loopback IP must receive 403, no exceptions."""
    with pytest.raises(HTTPException) as exc_info:
        _internal_only(_make_request("10.0.0.1"))
    assert exc_info.value.status_code == 403


def test_public_ip_is_rejected():
    """A public internet IP must receive 403."""
    with pytest.raises(HTTPException) as exc_info:
        _internal_only(_make_request("203.0.113.42"))
    assert exc_info.value.status_code == 403


def test_spoofed_x_goog_internal_header_does_not_bypass_gate():
    """Sending X-Goog-Internal must NOT grant access to a non-loopback caller.

    The previous implementation admitted any caller that sent this header.
    This test confirms the forgeable header path has been removed.
    """
    with pytest.raises(HTTPException) as exc_info:
        _internal_only(_make_request("10.0.0.1", headers={"X-Goog-Internal": "1"}))
    assert exc_info.value.status_code == 403


def test_spoofed_x_goog_internal_with_public_ip_is_rejected():
    """A public-internet caller with X-Goog-Internal header still gets 403."""
    with pytest.raises(HTTPException) as exc_info:
        _internal_only(_make_request("203.0.113.42", headers={"X-Goog-Internal": "true"}))
    assert exc_info.value.status_code == 403


def test_missing_client_is_rejected():
    """A request with no client information must be denied access."""
    request = MagicMock()
    request.client = None
    with pytest.raises(HTTPException) as exc_info:
        _internal_only(request)
    assert exc_info.value.status_code == 403
