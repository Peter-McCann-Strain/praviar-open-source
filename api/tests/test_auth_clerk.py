"""Tests for api.auth.clerk.verify_clerk_token.

Covers:
  - Default Clerk tokens are not treated as publishable-key audiences
  - Missing CLERK_DOMAIN raises ValueError
  - Missing or untrusted authorized-party claims fail closed
  - Expired token raises jwt.ExpiredSignatureError
  - Pending sessions are rejected
  - Generic JWT error raises jwt.PyJWTError
  - Valid token returns Clerk session token v2 claims with sub and o.id
  - Issuer constraint is always added
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jwt
import pytest
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError
from jwt.utils import base64url_encode

from api.circuit_breaker import CircuitBreaker, CircuitState


def _make_settings(
    *,
    clerk_jwks_url: str = "https://clerk.example.com/.well-known/jwks.json",
    clerk_publishable_key: str = "pk_test_abc",
    clerk_domain: str = "clerk.example.com",
    app_url: str = "https://app.example.com",
    cors_origins: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        clerk_jwks_url=clerk_jwks_url,
        clerk_publishable_key=clerk_publishable_key,
        clerk_domain=clerk_domain,
        app_url=app_url,
        cors_origins=(["https://app.example.com"] if cors_origins is None else cors_origins),
    )


def _patch_clerk(settings=None, *, signing_key=None, decode_return=None, decode_side_effect=None):
    """Return a stack of context-manager patches for a verify_clerk_token call."""
    if settings is None:
        settings = _make_settings()

    mock_signing_key = MagicMock()
    mock_signing_key.key = "fake-rsa-key"

    mock_jwks_client = MagicMock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = signing_key or mock_signing_key

    patches = [
        patch("api.auth.clerk.get_settings", return_value=settings),
        patch("api.auth.clerk._jwks_client", mock_jwks_client),
    ]

    if decode_side_effect is not None:
        patches.append(patch("api.auth.clerk.jwt.decode", side_effect=decode_side_effect))
    elif decode_return is not None:
        patches.append(patch("api.auth.clerk.jwt.decode", return_value=decode_return))

    return patches


# ---------------------------------------------------------------------------
# Verification prerequisites
# ---------------------------------------------------------------------------


def test_verify_clerk_token_does_not_use_publishable_key_as_audience():
    """Default Clerk session tokens have no aud claim."""
    settings = _make_settings(clerk_publishable_key="")
    expected_payload = {
        "sub": "user_clerk_abc123",
        "sid": "sess_abc123",
        "v": 2,
        "azp": "https://app.example.com",
    }
    mock_signing_key = MagicMock()
    mock_signing_key.key = "fake-rsa-key"
    mock_jwks_client = MagicMock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key
    mock_decode = MagicMock(return_value=expected_payload)

    with (
        patch("api.auth.clerk.get_settings", return_value=settings),
        patch("api.auth.clerk._jwks_client", mock_jwks_client),
        patch("api.auth.clerk.jwt.decode", mock_decode),
    ):
        from api.auth.clerk import verify_clerk_token

        assert verify_clerk_token(_unsigned_test_token(kid="known-key")) is expected_payload

    _, decode_kwargs = mock_decode.call_args
    assert "audience" not in decode_kwargs


def test_verify_clerk_token_requires_authorized_parties():
    settings = _make_settings(app_url="", cors_origins=[])

    with (
        patch("api.auth.clerk.get_settings", return_value=settings),
        pytest.raises(ValueError, match="APP_URL or CORS_ORIGINS"),
    ):
        from api.auth.clerk import verify_clerk_token

        verify_clerk_token(_unsigned_test_token(kid="known-key"))


def test_verify_clerk_token_rejects_path_as_authorized_party_origin():
    settings = _make_settings(
        app_url="https://app.example.com/not-an-origin",
        cors_origins=[],
    )

    with (
        patch("api.auth.clerk.get_settings", return_value=settings),
        pytest.raises(ValueError, match="APP_URL or CORS_ORIGINS"),
    ):
        from api.auth.clerk import verify_clerk_token

        verify_clerk_token(_unsigned_test_token(kid="known-key"))


def test_verify_clerk_token_empty_domain_raises():
    """verify_clerk_token must refuse to decode without issuer validation."""
    settings = _make_settings(clerk_domain="")

    with (
        patch("api.auth.clerk.get_settings", return_value=settings),
        pytest.raises(ValueError, match="CLERK_DOMAIN must be set"),
    ):
        from api.auth.clerk import verify_clerk_token

        verify_clerk_token(_unsigned_test_token(kid="known-key"))


# ---------------------------------------------------------------------------
# JWT error paths
# ---------------------------------------------------------------------------


def test_verify_clerk_token_expired_signature_re_raised():
    """ExpiredSignatureError from jwt.decode is re-raised unchanged."""
    settings = _make_settings()

    mock_signing_key = MagicMock()
    mock_signing_key.key = "fake-key"
    mock_jwks_client = MagicMock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    with (
        patch("api.auth.clerk.get_settings", return_value=settings),
        patch("api.auth.clerk._jwks_client", mock_jwks_client),
        patch("api.auth.clerk.jwt.decode", side_effect=jwt.ExpiredSignatureError("expired")),
    ):
        from api.auth.clerk import verify_clerk_token

        with pytest.raises(jwt.ExpiredSignatureError):
            verify_clerk_token(_unsigned_test_token(kid="known-key"))


def test_verify_clerk_token_rejects_untrusted_authorized_party():
    """A signed token from another frontend origin is not authorized here."""
    settings = _make_settings()

    mock_signing_key = MagicMock()
    mock_signing_key.key = "fake-key"
    mock_jwks_client = MagicMock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    with (
        patch("api.auth.clerk.get_settings", return_value=settings),
        patch("api.auth.clerk._jwks_client", mock_jwks_client),
        patch(
            "api.auth.clerk.jwt.decode",
            return_value={
                "sub": "user_abc",
                "sid": "sess_abc",
                "v": 2,
                "azp": "https://evil.example",
            },
        ),
    ):
        from api.auth.clerk import verify_clerk_token

        with pytest.raises(jwt.InvalidTokenError, match="Unauthorized Clerk token party"):
            verify_clerk_token(_unsigned_test_token(kid="known-key"))


def test_verify_clerk_token_rejects_missing_authorized_party():
    settings = _make_settings()
    mock_signing_key = MagicMock()
    mock_signing_key.key = "fake-key"
    mock_jwks_client = MagicMock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    with (
        patch("api.auth.clerk.get_settings", return_value=settings),
        patch("api.auth.clerk._jwks_client", mock_jwks_client),
        patch(
            "api.auth.clerk.jwt.decode",
            return_value={"sub": "user_abc", "sid": "sess_abc", "v": 2},
        ),
    ):
        from api.auth.clerk import verify_clerk_token

        with pytest.raises(jwt.InvalidTokenError, match="Unauthorized Clerk token party"):
            verify_clerk_token(_unsigned_test_token(kid="known-key"))


@pytest.mark.parametrize(
    "payload",
    [
        {"sid": "sess_abc", "v": 2, "azp": "https://app.example.com"},
        {"sub": "", "sid": "sess_abc", "v": 2, "azp": "https://app.example.com"},
        {"sub": "user_abc", "v": 2, "azp": "https://app.example.com"},
        {"sub": "user_abc", "sid": "", "v": 2, "azp": "https://app.example.com"},
        {"sub": "user_abc", "sid": "sess_abc", "azp": "https://app.example.com"},
        {
            "sub": "user_abc",
            "sid": "sess_abc",
            "v": 1,
            "org_id": "org_legacy",
            "azp": "https://app.example.com",
        },
        {
            "sub": "user_abc",
            "sid": "sess_abc",
            "v": 2,
            "o": {},
            "azp": "https://app.example.com",
        },
    ],
)
def test_verify_clerk_token_rejects_malformed_identity_claims(payload):
    settings = _make_settings()
    mock_signing_key = MagicMock()
    mock_signing_key.key = "fake-key"
    mock_jwks_client = MagicMock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    with (
        patch("api.auth.clerk.get_settings", return_value=settings),
        patch("api.auth.clerk._jwks_client", mock_jwks_client),
        patch("api.auth.clerk.jwt.decode", return_value=payload),
    ):
        from api.auth.clerk import verify_clerk_token

        with pytest.raises(jwt.InvalidTokenError):
            verify_clerk_token(_unsigned_test_token(kid="known-key"))


def test_verify_clerk_token_rejects_pending_session():
    settings = _make_settings()
    mock_signing_key = MagicMock()
    mock_signing_key.key = "fake-key"
    mock_jwks_client = MagicMock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    with (
        patch("api.auth.clerk.get_settings", return_value=settings),
        patch("api.auth.clerk._jwks_client", mock_jwks_client),
        patch(
            "api.auth.clerk.jwt.decode",
            return_value={
                "sub": "user_pending",
                "sid": "sess_pending",
                "v": 2,
                "azp": "https://app.example.com",
                "sts": "pending",
            },
        ),
    ):
        from api.auth.clerk import verify_clerk_token

        with pytest.raises(jwt.InvalidTokenError, match="session is pending"):
            verify_clerk_token(_unsigned_test_token(kid="known-key"))


@pytest.mark.parametrize("session_status", ["suspended", {"state": "active"}])
def test_verify_clerk_token_rejects_unknown_session_status(session_status):
    settings = _make_settings()
    mock_signing_key = MagicMock()
    mock_signing_key.key = "fake-key"
    mock_jwks_client = MagicMock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    with (
        patch("api.auth.clerk.get_settings", return_value=settings),
        patch("api.auth.clerk._jwks_client", mock_jwks_client),
        patch(
            "api.auth.clerk.jwt.decode",
            return_value={
                "sub": "user_unknown_status",
                "sid": "sess_unknown_status",
                "v": 2,
                "azp": "https://app.example.com",
                "sts": session_status,
            },
        ),
    ):
        from api.auth.clerk import verify_clerk_token

        with pytest.raises(jwt.InvalidTokenError, match="Invalid Clerk session status"):
            verify_clerk_token(_unsigned_test_token(kid="known-key"))


def test_verify_clerk_token_generic_pyjwt_error_re_raised():
    """Any other PyJWTError is re-raised."""
    settings = _make_settings()

    mock_signing_key = MagicMock()
    mock_signing_key.key = "fake-key"
    mock_jwks_client = MagicMock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    with (
        patch("api.auth.clerk.get_settings", return_value=settings),
        patch("api.auth.clerk._jwks_client", mock_jwks_client),
        patch("api.auth.clerk.jwt.decode", side_effect=jwt.DecodeError("malformed")),
    ):
        from api.auth.clerk import verify_clerk_token

        with pytest.raises(jwt.PyJWTError):
            verify_clerk_token(_unsigned_test_token(kid="known-key"))


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_verify_clerk_token_success_returns_payload():
    """A valid token returns the decoded payload dict."""
    settings = _make_settings(clerk_publishable_key="pk_test_abc")
    expected_payload = {
        "sub": "user_clerk_abc123",
        "sid": "sess_clerk_abc123",
        "v": 2,
        "o": {"id": "org_clerk_xyz", "rol": "member"},
        "azp": "https://app.example.com",
        "sts": "active",
        "email": "user@praviar.io",
    }

    mock_signing_key = MagicMock()
    mock_signing_key.key = "fake-rsa-key"
    mock_jwks_client = MagicMock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    with (
        patch("api.auth.clerk.get_settings", return_value=settings),
        patch("api.auth.clerk._jwks_client", mock_jwks_client),
        patch("api.auth.clerk.jwt.decode", return_value=expected_payload),
    ):
        from api.auth.clerk import verify_clerk_token

        payload = verify_clerk_token(_unsigned_test_token(kid="known-key"))

    assert payload["sub"] == "user_clerk_abc123"
    assert payload["v"] == 2
    assert payload["o"]["id"] == "org_clerk_xyz"


def test_verify_clerk_token_canonicalizes_configured_origin():
    settings = _make_settings(
        app_url="https://APP.EXAMPLE.COM:443/",
        cors_origins=[],
    )
    expected_payload = {
        "sub": "user_origin",
        "sid": "sess_origin",
        "v": 2,
        "azp": "https://app.example.com",
    }
    mock_signing_key = MagicMock()
    mock_signing_key.key = "fake-rsa-key"
    mock_jwks_client = MagicMock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    with (
        patch("api.auth.clerk.get_settings", return_value=settings),
        patch("api.auth.clerk._jwks_client", mock_jwks_client),
        patch("api.auth.clerk.jwt.decode", return_value=expected_payload),
    ):
        from api.auth.clerk import verify_clerk_token

        assert verify_clerk_token(_unsigned_test_token(kid="known-key")) is expected_payload


def test_verify_clerk_token_includes_issuer_when_domain_set():
    """When clerk_domain is configured, the issuer constraint is passed to jwt.decode."""
    settings = _make_settings(
        clerk_publishable_key="pk_test_abc",
        clerk_domain="clerk.praviar.io",
    )
    expected_payload = {
        "sub": "user_abc",
        "sid": "sess_abc",
        "v": 2,
        "o": {"id": "org_xyz", "rol": "member"},
        "azp": "https://app.example.com",
    }

    mock_signing_key = MagicMock()
    mock_signing_key.key = "fake-rsa-key"
    mock_jwks_client = MagicMock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    mock_decode = MagicMock(return_value=expected_payload)

    with (
        patch("api.auth.clerk.get_settings", return_value=settings),
        patch("api.auth.clerk._jwks_client", mock_jwks_client),
        patch("api.auth.clerk.jwt.decode", mock_decode),
    ):
        from api.auth.clerk import verify_clerk_token

        verify_clerk_token(_unsigned_test_token(kid="known-key"))

    _, call_kwargs = mock_decode.call_args
    assert call_kwargs.get("issuer") == "https://clerk.praviar.io"


def test_verify_clerk_token_rejects_empty_domain_before_decode():
    """An empty Clerk domain must fail before JWKS or JWT decode is attempted."""
    settings = _make_settings(clerk_publishable_key="pk_test_abc", clerk_domain="")

    mock_signing_key = MagicMock()
    mock_signing_key.key = "fake-rsa-key"
    mock_jwks_client = MagicMock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    mock_decode = MagicMock(return_value={"sub": "user_abc"})

    with (
        patch("api.auth.clerk.get_settings", return_value=settings),
        patch("api.auth.clerk._jwks_client", mock_jwks_client),
        patch("api.auth.clerk.jwt.decode", mock_decode),
        pytest.raises(ValueError, match="CLERK_DOMAIN must be set"),
    ):
        from api.auth.clerk import verify_clerk_token

        verify_clerk_token(_unsigned_test_token(kid="known-key"))

    mock_jwks_client.get_signing_key_from_jwt.assert_not_called()
    mock_decode.assert_not_called()


def test_verify_clerk_token_requires_time_and_identity_claims():
    """PyJWT must require Clerk's signed temporal and identity claims."""
    settings = _make_settings(clerk_publishable_key="pk_live_secretkey")
    expected_payload = {
        "sub": "user_live",
        "sid": "sess_live",
        "v": 2,
        "azp": "https://app.example.com",
    }

    mock_signing_key = MagicMock()
    mock_signing_key.key = "fake-rsa-key"
    mock_jwks_client = MagicMock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    mock_decode = MagicMock(return_value=expected_payload)

    with (
        patch("api.auth.clerk.get_settings", return_value=settings),
        patch("api.auth.clerk._jwks_client", mock_jwks_client),
        patch("api.auth.clerk.jwt.decode", mock_decode),
    ):
        from api.auth.clerk import verify_clerk_token

        verify_clerk_token(_unsigned_test_token(kid="known-key"))

    _, call_kwargs = mock_decode.call_args
    assert "audience" not in call_kwargs
    assert call_kwargs.get("algorithms") == ["RS256"]
    assert call_kwargs.get("options") == {
        "require": ["exp", "nbf", "iss", "sub", "sid", "v", "azp"]
    }


# ---------------------------------------------------------------------------
# JWKS client lazy init
# ---------------------------------------------------------------------------


def _unsigned_test_token(*, kid: str, algorithm: str = "RS256") -> str:
    header = base64url_encode(
        json.dumps({"alg": algorithm, "kid": kid}, separators=(",", ":")).encode()
    ).decode()
    payload = base64url_encode(b"{}").decode()
    signature = base64url_encode(b"test-signature").decode()
    return f"{header}.{payload}.{signature}"


def _test_jwks(*, kid: str = "known-key") -> dict[str, list[dict[str, str]]]:
    return {
        "keys": [
            {
                "kty": "oct",
                "kid": kid,
                "use": "sig",
                "alg": "HS256",
                "k": "c2VjcmV0",
            }
        ]
    }


def test_unknown_kid_does_not_open_shared_jwks_breaker() -> None:
    """Untrusted key misses remain authentication failures, not provider failures."""
    from api.auth.clerk import _CircuitProtectedPyJWKClient

    breaker = CircuitBreaker(
        "clerk_jwks_test",
        failure_threshold=1,
        recovery_timeout_s=30.0,
    )
    client = _CircuitProtectedPyJWKClient("https://clerk.example.test/jwks")
    assert client.jwk_set_cache is not None
    client.jwk_set_cache.put(_test_jwks())

    with (
        patch("api.circuit_breaker.clerk_jwks_breaker", breaker),
        patch.object(PyJWKClient, "fetch_data", return_value=_test_jwks()) as fetch_data,
    ):
        for kid in ("attacker-key-1", "attacker-key-2", "attacker-key-3"):
            with pytest.raises(PyJWKClientError, match="Unable to find a signing key"):
                client.get_signing_key_from_jwt(_unsigned_test_token(kid=kid))

    assert breaker.state == CircuitState.CLOSED
    fetch_data.assert_called_once()


def test_distinct_unknown_kids_share_one_inflight_refresh() -> None:
    """Concurrent attacker misses coalesce behind one bounded provider fetch."""
    from api.auth.clerk import _CircuitProtectedPyJWKClient

    client = _CircuitProtectedPyJWKClient("https://clerk.example.test/jwks")
    assert client.jwk_set_cache is not None
    client.jwk_set_cache.put(_test_jwks())
    fetch_started = threading.Event()
    release_fetch = threading.Event()

    def fetch_same_keys() -> dict[str, list[dict[str, str]]]:
        fetch_started.set()
        assert release_fetch.wait(timeout=2)
        return _test_jwks()

    def lookup(kid: str) -> str:
        with pytest.raises(PyJWKClientError, match="Unable to find a signing key"):
            client.get_signing_key(kid)
        return "missing"

    with (
        patch.object(PyJWKClient, "fetch_data", side_effect=fetch_same_keys) as fetch_data,
        ThreadPoolExecutor(max_workers=4) as executor,
    ):
        futures = [executor.submit(lookup, f"attacker-key-{index}") for index in range(4)]
        assert fetch_started.wait(timeout=2)
        release_fetch.set()
        assert [future.result(timeout=2) for future in futures] == ["missing"] * 4

    fetch_data.assert_called_once()


def test_negative_kid_cache_is_bounded() -> None:
    from api.auth.clerk import _CircuitProtectedPyJWKClient

    client = _CircuitProtectedPyJWKClient(
        "https://clerk.example.test/jwks",
        negative_kid_cache_size=2,
    )
    assert client.jwk_set_cache is not None
    client.jwk_set_cache.put(_test_jwks())

    with patch.object(PyJWKClient, "fetch_data", return_value=_test_jwks()) as fetch_data:
        for kid in ("unknown-1", "unknown-2", "unknown-3", "unknown-4"):
            with pytest.raises(PyJWKClientError):
                client.get_signing_key(kid)

    assert list(client._negative_kids) == ["unknown-3", "unknown-4"]
    fetch_data.assert_called_once()


def test_recent_provider_failure_throttles_distinct_unknown_kids_as_unavailable() -> None:
    """A failed refresh is not retried or misreported as a bad token in the window."""
    from api.auth.clerk import _CircuitProtectedPyJWKClient

    client = _CircuitProtectedPyJWKClient("https://clerk.example.test/jwks")
    assert client.jwk_set_cache is not None
    client.jwk_set_cache.put(_test_jwks())

    with patch.object(
        PyJWKClient,
        "fetch_data",
        side_effect=PyJWKClientConnectionError("provider unavailable"),
    ) as fetch_data:
        with pytest.raises(PyJWKClientConnectionError, match="provider unavailable"):
            client.get_signing_key("unknown-1")
        with pytest.raises(PyJWKClientConnectionError, match="temporarily unavailable"):
            client.get_signing_key("unknown-2")

    fetch_data.assert_called_once()


def test_cold_cache_provider_failure_is_not_refetched_during_cooldown() -> None:
    from api.auth.clerk import _CircuitProtectedPyJWKClient

    client = _CircuitProtectedPyJWKClient("https://clerk.example.test/jwks")

    with patch.object(
        PyJWKClient,
        "fetch_data",
        side_effect=PyJWKClientConnectionError("provider unavailable"),
    ) as fetch_data:
        with pytest.raises(PyJWKClientConnectionError, match="provider unavailable"):
            client.get_signing_key("unknown-1")
        with pytest.raises(PyJWKClientConnectionError, match="temporarily unavailable"):
            client.get_signing_key("unknown-2")

    fetch_data.assert_called_once()


def test_expired_negative_kid_can_refresh_after_legitimate_key_rotation() -> None:
    from api.auth.clerk import _CircuitProtectedPyJWKClient

    clock = [100.0]
    client = _CircuitProtectedPyJWKClient(
        "https://clerk.example.test/jwks",
        miss_refresh_cooldown_seconds=1.0,
        negative_kid_ttl_seconds=1.0,
    )
    assert client.jwk_set_cache is not None
    client.jwk_set_cache.put(_test_jwks())

    with (
        patch("api.auth.clerk.time.monotonic", side_effect=lambda: clock[0]),
        patch.object(
            PyJWKClient,
            "fetch_data",
            side_effect=[_test_jwks(), _test_jwks(kid="rotated-key")],
        ) as fetch_data,
    ):
        with pytest.raises(PyJWKClientError):
            client.get_signing_key("rotated-key")
        clock[0] = 100.5
        with pytest.raises(PyJWKClientError):
            client.get_signing_key("rotated-key")
        clock[0] = 101.1
        signing_key = client.get_signing_key("rotated-key")

    assert signing_key.key_id == "rotated-key"
    assert fetch_data.call_count == 2


@pytest.mark.parametrize(
    ("token", "message"),
    [
        ("a" * (16 * 1024 + 1), "maximum size"),
        (f'{"a" * (2 * 1024 + 1)}.e30.c2ln', "header exceeds"),
        (_unsigned_test_token(kid="k" * 257), "key ID exceeds"),
        (_unsigned_test_token(kid="known-key", algorithm="HS256"), "must use RS256"),
        (_unsigned_test_token(kid="bad\nkey"), "control characters"),
    ],
)
def test_untrusted_token_envelope_is_bounded_before_jwks_access(
    token: str,
    message: str,
) -> None:
    from api.auth.clerk import _validated_token_key_id

    with pytest.raises(jwt.PyJWTError, match=message):
        _validated_token_key_id(token)


def test_jwks_transport_failure_still_opens_shared_breaker() -> None:
    """Actual Clerk transport failures continue to influence dependency health."""
    from api.auth.clerk import _CircuitProtectedPyJWKClient

    breaker = CircuitBreaker(
        "clerk_jwks_test",
        failure_threshold=1,
        recovery_timeout_s=30.0,
    )
    client = _CircuitProtectedPyJWKClient("https://clerk.example.test/jwks")

    with (
        patch("api.circuit_breaker.clerk_jwks_breaker", breaker),
        patch.object(
            PyJWKClient,
            "fetch_data",
            side_effect=PyJWKClientConnectionError("Clerk JWKS unavailable"),
        ),
        pytest.raises(PyJWKClientConnectionError, match="unavailable"),
    ):
        client.get_signing_key_from_jwt(_unsigned_test_token(kid="known-key"))

    assert breaker.state == CircuitState.OPEN


def test_malformed_token_never_reaches_jwks_transport() -> None:
    from api.auth.clerk import _CircuitProtectedPyJWKClient

    client = _CircuitProtectedPyJWKClient("https://clerk.example.test/jwks")

    with (
        patch.object(PyJWKClient, "fetch_data") as fetch_data,
        pytest.raises(jwt.DecodeError),
    ):
        client.get_signing_key_from_jwt("not-a-jwt")

    fetch_data.assert_not_called()


def test_get_jwks_client_initialised_once(monkeypatch):
    """_get_jwks_client reuses the cached singleton across calls."""
    import api.auth.clerk as clerk_module

    monkeypatch.setattr(clerk_module, "_jwks_client", None)

    settings = _make_settings(clerk_jwks_url="https://clerk.example.com/.well-known/jwks.json")

    mock_pyjwkclient_cls = MagicMock()
    mock_instance = MagicMock()
    mock_pyjwkclient_cls.return_value = mock_instance

    with (
        patch("api.auth.clerk.get_settings", return_value=settings),
        patch("api.auth.clerk._CircuitProtectedPyJWKClient", mock_pyjwkclient_cls),
    ):
        c1 = clerk_module._get_jwks_client()
        c2 = clerk_module._get_jwks_client()

    # Constructor called only once
    assert mock_pyjwkclient_cls.call_count == 1
    assert c1 is c2
