"""Opaque, database-bound capabilities for weekly digest unsubscribe."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from api.config import get_settings
from api.external_report_delivery_keyring import ExternalReportDeliveryKeyRing

_TOKEN_PREFIX = "du1"
_TOKEN_BYTES = 64
_TOKEN_TTL = timedelta(days=90)
_DIGEST_CONTEXT = b"praviar:weekly-digest-unsubscribe-digest:v1"


class InvalidUnsubscribeTokenError(ValueError):
    """Raised when an opaque unsubscribe capability is malformed."""


@dataclass(frozen=True)
class DigestUnsubscribeCapability:
    """Raw one-time capability plus the only representation stored in the DB."""

    token: str
    token_digest: str
    expires_at: datetime


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise InvalidUnsubscribeTokenError("unsubscribe capability is malformed") from exc


def _token_keyring() -> ExternalReportDeliveryKeyRing:
    settings = get_settings()
    return ExternalReportDeliveryKeyRing.from_secret(
        settings.external_report_delivery_keyring_secret.get_secret_value()
    )


def _digest_key() -> bytes:
    return hmac.new(
        _token_keyring().operation_hmac_key,
        _DIGEST_CONTEXT,
        hashlib.sha256,
    ).digest()


def _validate_token_shape(token: str) -> bytes:
    try:
        prefix, encoded = token.split(".", 1)
    except ValueError as exc:
        raise InvalidUnsubscribeTokenError("unsubscribe capability is malformed") from exc
    if prefix != _TOKEN_PREFIX or not encoded:
        raise InvalidUnsubscribeTokenError("unsubscribe capability is malformed")
    raw = _b64url_decode(encoded)
    if len(raw) != _TOKEN_BYTES or _b64url_encode(raw) != encoded:
        raise InvalidUnsubscribeTokenError("unsubscribe capability is malformed")
    return raw


def digest_unsubscribe_token(token: str) -> str:
    """Return the keyed lookup digest for a validated opaque capability."""
    raw = _validate_token_shape(token)
    return hmac.new(_digest_key(), raw, hashlib.sha256).hexdigest()


def unsubscribe_token_locator(token: str) -> str:
    """Return a non-secret route/rate-limit locator without logging the token."""
    _validate_token_shape(token)
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def create_digest_unsubscribe_capability(
    *,
    now: datetime | None = None,
) -> DigestUnsubscribeCapability:
    """Create a high-entropy capability whose identity exists only in the DB."""
    issued_at = now or datetime.now(UTC)
    if issued_at.tzinfo is None:
        raise ValueError("unsubscribe capability time must be timezone-aware")
    token = f"{_TOKEN_PREFIX}.{_b64url_encode(secrets.token_bytes(_TOKEN_BYTES))}"
    return DigestUnsubscribeCapability(
        token=token,
        token_digest=digest_unsubscribe_token(token),
        expires_at=issued_at + _TOKEN_TTL,
    )
