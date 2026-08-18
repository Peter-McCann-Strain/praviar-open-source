"""Clerk JWT verification for FastAPI."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, NoReturn
from urllib.parse import urlsplit

import jwt
import structlog
from jwt import PyJWK, PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

from api.config import get_settings

logger = structlog.get_logger()

CLERK_JWT_MAX_BYTES = 16 * 1024
CLERK_JWT_HEADER_SEGMENT_MAX_BYTES = 2 * 1024
CLERK_JWT_KID_MAX_BYTES = 256
CLERK_JWKS_MISS_REFRESH_COOLDOWN_SECONDS = 5.0
CLERK_JWKS_NEGATIVE_KID_TTL_SECONDS = 30.0
CLERK_JWKS_NEGATIVE_KID_CACHE_SIZE = 128

_jwks_client: PyJWKClient | None = None


class _CircuitProtectedPyJWKClient(PyJWKClient):
    """Bound and coalesce remote JWKS work caused by untrusted key IDs.

    Token parsing and key-id matching are deliberately left outside the
    dependency circuit.  Those operations can fail because of untrusted token
    input and therefore must not be allowed to degrade the health state shared
    by legitimate authentication requests.
    """

    def __init__(
        self,
        uri: str,
        *,
        miss_refresh_cooldown_seconds: float = CLERK_JWKS_MISS_REFRESH_COOLDOWN_SECONDS,
        negative_kid_ttl_seconds: float = CLERK_JWKS_NEGATIVE_KID_TTL_SECONDS,
        negative_kid_cache_size: int = CLERK_JWKS_NEGATIVE_KID_CACHE_SIZE,
        **kwargs: Any,
    ) -> None:
        if miss_refresh_cooldown_seconds <= 0:
            raise ValueError("JWKS miss refresh cooldown must be positive")
        if negative_kid_ttl_seconds <= 0:
            raise ValueError("JWKS negative-kid TTL must be positive")
        if negative_kid_cache_size <= 0:
            raise ValueError("JWKS negative-kid cache size must be positive")
        super().__init__(uri, **kwargs)
        self._miss_refresh_cooldown_seconds = miss_refresh_cooldown_seconds
        self._negative_kid_ttl_seconds = negative_kid_ttl_seconds
        self._negative_kid_cache_size = negative_kid_cache_size
        self._key_refresh_lock = threading.Lock()
        self._negative_kids: OrderedDict[str, float] = OrderedDict()
        self._last_fetch_attempt_at = float("-inf")
        self._last_fetch_had_provider_failure = False

    def fetch_data(self) -> Any:
        from api.circuit_breaker import clerk_jwks_breaker

        self._last_fetch_attempt_at = time.monotonic()
        try:
            data = clerk_jwks_breaker.call_sync(super().fetch_data)
        except Exception:
            self._last_fetch_had_provider_failure = True
            raise
        self._last_fetch_had_provider_failure = False
        return data

    def _coalesced_signing_keys(self) -> list[PyJWK]:
        with self._key_refresh_lock:
            # The cache may expire between a fast-path check and PyJWT's own
            # lookup, so serialize even cache reads to guarantee that an expiry
            # produces at most one in-flight provider fetch.
            now = time.monotonic()
            if (
                self._last_fetch_had_provider_failure
                and now - self._last_fetch_attempt_at < self._miss_refresh_cooldown_seconds
            ):
                cache = self.jwk_set_cache
                if cache is None or cache.get() is None:
                    self._raise_provider_unavailable()
            return super().get_signing_keys()

    def _negative_kid_is_live(self, kid: str, *, now: float) -> bool:
        expires_at = self._negative_kids.pop(kid, None)
        if expires_at is None or expires_at <= now:
            return False
        self._negative_kids[kid] = expires_at
        return True

    def _remember_negative_kid(self, kid: str, *, now: float) -> None:
        self._negative_kids.pop(kid, None)
        self._negative_kids[kid] = now + self._negative_kid_ttl_seconds
        while len(self._negative_kids) > self._negative_kid_cache_size:
            self._negative_kids.popitem(last=False)

    @staticmethod
    def _raise_missing_signing_key() -> NoReturn:
        # Do not reflect an attacker-controlled key ID into logs or responses.
        raise PyJWKClientError("Unable to find a signing key for this token")

    @staticmethod
    def _raise_provider_unavailable() -> NoReturn:
        raise PyJWKClientConnectionError("Clerk JWKS is temporarily unavailable")

    def get_signing_key(self, kid: str) -> PyJWK:
        """Return one key, refreshing at most once per bounded miss window."""
        if not isinstance(kid, str) or not kid:
            self._raise_missing_signing_key()

        signing_key = self.match_kid(self._coalesced_signing_keys(), kid)
        if signing_key is not None:
            return signing_key

        with self._key_refresh_lock:
            # A coalesced refresh may have completed while this request waited.
            signing_key = self.match_kid(super().get_signing_keys(), kid)
            if signing_key is not None:
                return signing_key

            now = time.monotonic()
            if self._negative_kid_is_live(kid, now=now):
                self._raise_missing_signing_key()
            if now - self._last_fetch_attempt_at < self._miss_refresh_cooldown_seconds:
                if self._last_fetch_had_provider_failure:
                    # A stale key set cannot distinguish an attacker miss from
                    # legitimate key rotation while the provider is unavailable.
                    # Preserve that distinction for the dependency layer so it
                    # returns a retryable 503 rather than a misleading 401.
                    self._raise_provider_unavailable()
                self._remember_negative_kid(kid, now=now)
                self._raise_missing_signing_key()

            signing_key = self.match_kid(super().get_signing_keys(refresh=True), kid)
            if signing_key is not None:
                return signing_key

            self._remember_negative_kid(kid, now=time.monotonic())
            self._raise_missing_signing_key()


def _validated_token_key_id(token: str) -> str:
    """Validate the bounded untrusted JWT envelope before any JWKS access."""
    if not isinstance(token, str):
        raise jwt.DecodeError("Clerk JWT must be text")
    # Reject oversized values before encoding so an attacker cannot force a
    # second, equally large in-memory copy merely to establish the byte count.
    if len(token) > CLERK_JWT_MAX_BYTES:
        raise jwt.DecodeError("Clerk JWT exceeds the maximum size")
    try:
        token_bytes = token.encode("ascii")
    except UnicodeEncodeError as exc:
        raise jwt.DecodeError("Clerk JWT must be ASCII") from exc
    if len(token_bytes) > CLERK_JWT_MAX_BYTES:
        raise jwt.DecodeError("Clerk JWT exceeds the maximum size")

    segments = token.split(".")
    if len(segments) != 3 or not all(segments):
        raise jwt.DecodeError("Clerk JWT must contain three non-empty segments")
    if len(segments[0]) > CLERK_JWT_HEADER_SEGMENT_MAX_BYTES:
        raise jwt.DecodeError("Clerk JWT header exceeds the maximum size")

    header = jwt.get_unverified_header(token)
    if header.get("alg") != "RS256":
        raise jwt.InvalidAlgorithmError("Clerk JWT must use RS256")
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise jwt.InvalidTokenError("Clerk JWT must contain a key ID")
    if len(kid.encode("utf-8")) > CLERK_JWT_KID_MAX_BYTES:
        raise jwt.InvalidTokenError("Clerk JWT key ID exceeds the maximum size")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in kid):
        raise jwt.InvalidTokenError("Clerk JWT key ID contains control characters")
    return kid


def clerk_v2_org_context(payload: dict) -> tuple[str, str] | None:
    """Return the active org ID and normalized role from a v2 session token."""
    if payload.get("v") != 2:
        raise jwt.InvalidTokenError("Unsupported Clerk session token version")

    organization_claim = payload.get("o")
    if organization_claim is None:
        return None
    if not isinstance(organization_claim, dict):
        raise jwt.InvalidTokenError("Malformed Clerk organization claim")

    org_id = organization_claim.get("id")
    if not isinstance(org_id, str) or not org_id.strip():
        raise jwt.InvalidTokenError("Malformed Clerk organization ID")
    org_role = organization_claim.get("rol")
    if not isinstance(org_role, str) or org_role not in {"admin", "member"}:
        raise jwt.InvalidTokenError("Malformed Clerk organization role")
    return org_id, org_role


def clerk_v2_org_id(payload: dict) -> str | None:
    """Return the active org ID from a valid Clerk session-token-v2 payload."""
    context = clerk_v2_org_context(payload)
    return context[0] if context is not None else None


def _canonical_origin(value: object) -> str | None:
    """Canonicalize one explicit HTTP(S) origin, rejecting URL-like variants."""
    raw = str(value or "").strip()
    if not raw or raw == "*":
        return None
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return None

    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.lower()
    host = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None and not (
        (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    ):
        host = f"{host}:{port}"
    return f"{scheme}://{host}"


def _authorized_parties(settings: object) -> frozenset[str]:
    """Return configured frontend origins accepted by Clerk's ``azp`` claim."""
    configured = [
        getattr(settings, "app_url", ""),
        *getattr(settings, "cors_origins", ()),
    ]
    return frozenset(
        canonical for origin in configured if (canonical := _canonical_origin(origin)) is not None
    )


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        settings = get_settings()
        logger.debug("jwks_client_init", jwks_url=settings.clerk_jwks_url)
        # lifespan=300s caches the JWKS for 5 minutes to avoid fetching on
        # every request.  timeout=5s caps the blocking network call so a slow
        # Clerk JWKS endpoint cannot block the request worker indefinitely.
        _jwks_client = _CircuitProtectedPyJWKClient(
            settings.clerk_jwks_url,
            lifespan=300,
            timeout=5,
        )
    return _jwks_client


def verify_clerk_token(token: str) -> dict:
    """Verify a Clerk JWT and return the decoded payload.

    Raises jwt.PyJWTError on failure.
    Raises ValueError if CLERK_DOMAIN or the authorized-party allowlist is empty.
    Clerk's default session tokens do not carry ``aud``. Instead, this verifies
    ``azp`` against the configured application/CORS origins, as required by
    Clerk's manual verification contract.
    """
    settings = get_settings()

    if not settings.clerk_domain:
        logger.error(
            "clerk_issuer_validation_disabled",
            reason="CLERK_DOMAIN is empty",
        )
        raise ValueError("CLERK_DOMAIN must be set for JWT verification.")
    authorized_parties = _authorized_parties(settings)
    if not authorized_parties:
        logger.error("clerk_authorized_parties_missing")
        raise ValueError("APP_URL or CORS_ORIGINS must authorize Clerk token origins.")

    _validated_token_key_id(token)
    # PyJWKClient repeats the bounded header parse and then delegates key lookup
    # to the coalesced, negatively cached implementation above. Its transport is
    # the only operation protected by the dependency circuit.
    signing_key = _get_jwks_client().get_signing_key_from_jwt(token)

    decode_kwargs: dict = {
        "algorithms": ["RS256"],
        "issuer": f"https://{settings.clerk_domain}",
        "options": {"require": ["exp", "nbf", "iss", "sub", "sid", "v", "azp"]},
    }

    logger.debug(
        "clerk_token_decode_start",
        authorized_parties_count=len(authorized_parties),
    )

    try:
        payload = jwt.decode(token, signing_key.key, **decode_kwargs)
    except jwt.ExpiredSignatureError:
        logger.warning("clerk_token_expired")
        raise
    except jwt.PyJWTError as exc:
        logger.error("clerk_token_decode_failed", error=str(exc), exc_info=True)
        raise

    subject = payload.get("sub")
    session_id = payload.get("sid")
    if not isinstance(subject, str) or not subject.strip():
        logger.warning("clerk_token_subject_invalid")
        raise jwt.InvalidTokenError("Invalid Clerk token subject")
    if not isinstance(session_id, str) or not session_id.strip():
        logger.warning("clerk_token_session_id_invalid", sub=subject)
        raise jwt.InvalidTokenError("Invalid Clerk session ID")

    active_org_id = clerk_v2_org_id(payload)
    authorized_party = _canonical_origin(payload.get("azp"))
    if authorized_party is None or authorized_party not in authorized_parties:
        logger.warning("clerk_token_unauthorized_party", authorized_party=authorized_party)
        raise jwt.InvalidTokenError("Unauthorized Clerk token party")
    session_status = payload.get("sts")
    if session_status == "pending":
        logger.warning("clerk_token_session_pending", sub=payload.get("sub"))
        raise jwt.InvalidTokenError("Clerk session is pending")
    if session_status not in (None, "", "active"):
        logger.warning(
            "clerk_token_session_status_invalid",
            sub=payload.get("sub"),
            session_status=session_status,
        )
        raise jwt.InvalidTokenError("Invalid Clerk session status")

    logger.debug(
        "clerk_token_verified",
        sub=payload.get("sub"),
        token_version=payload.get("v"),
        org_id=active_org_id,
    )
    return payload
