# ruff: noqa: E501

"""Recipient-bound external report grant lifecycle."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hmac import compare_digest
from typing import Any, Literal, TypedDict, cast

import structlog
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.db.models import Analysis, AuditLog, ExternalReportGrant, Organization
from api.db.session import (
    bind_current_org_to_session,
    bind_public_share_grant_hash_to_session,
)
from api.errors import APIError
from api.external_report_delivery_keyring import ExternalReportDeliveryKeyRing
from api.schemas.reports_fto_io import (
    ExternalReportGrantActivityEvent,
    ExternalReportGrantActivityItem,
)
from api.security import hash_password, verify_password
from api.services.analyses import get_analysis_for_org, load_analysis_review_status
from api.services.email import PostmarkClient, get_email_client
from api.services.email_models import DeliveryLookupResult, DeliverySubmissionResult
from api.services.external_sharing_policy import (
    get_external_sharing_policy,
    require_recipient_domain_allowed,
)
from api.services.report_access import (
    report_payload_fingerprint,
    require_completed_report_payload,
)
from api.services.reports import (
    build_export_readiness_blockers,
    ensure_analysis_export_ready,
    load_export_reviewer_decisions,
)
from api.templates.email_layout import esc, esc_url, wrap_email

logger = structlog.get_logger()

GRANT_TOKEN_MIN_LENGTH = 40
GRANT_TOKEN_MAX_LENGTH = 64
ACCESS_SECRET_HEADER = "X-Praviar-Grant-Access"
VERIFICATION_CODE_DIGITS = 8
VERIFICATION_TTL = timedelta(minutes=10)
VERIFICATION_RESEND_COOLDOWN = timedelta(seconds=60)
MAX_VERIFICATION_ATTEMPTS = 8
ACCESS_TTL = timedelta(minutes=30)
DELIVERY_DISPATCH_TIMEOUT = timedelta(minutes=10)
DELIVERY_RECONCILIATION_BASE_BACKOFF = timedelta(minutes=5)
DELIVERY_RECONCILIATION_MAX_BACKOFF = timedelta(hours=24)
DELIVERY_KEY_MIN_LENGTH = 16
DELIVERY_KEY_MAX_LENGTH = 128
_DELIVERY_AES_INFO = b"praviar:external-report-delivery:aes-gcm:v1"
_UNRESOLVED_DELIVERY_STATES = (
    "prepared",
    "dispatching",
    "provider_accepted",
    "outcome_unknown",
)

_GRANT_ACTIVITY_EVENTS: dict[str, ExternalReportGrantActivityEvent] = {
    "report.share.delivery_dispatch_started": "delivery_dispatch_started",
    "report.share.delivery_provider_accepted": "delivery_provider_accepted",
    "report.share.delivery_rejected": "delivery_rejected",
    "report.share.delivery_outcome_unknown": "delivery_outcome_unknown",
    "report.share.delivery_cancelled_by_policy": "delivery_cancelled_by_policy",
    "report.share.delivery_cancelled_expired": "delivery_cancelled_expired",
    "report.share.delivery_cancelled_retention_expired": ("delivery_cancelled_retention_expired"),
    "report.share.delivery_reconciliation_alert": "delivery_reconciliation_alert",
    "report.share.invitation_sent": "invitation_sent",
    "report.share.recipient_verified": "recipient_verified",
    "report.share.viewed": "report_viewed",
    "report.share.grant_revoked": "revoked",
    "report.share.grant_revoked_by_policy": "revoked_by_policy",
    "report.share.grant_revoked_by_reissue": "revoked_by_reissue",
}


@dataclass(frozen=True)
class CreatedGrant:
    grant: ExternalReportGrant
    raw_token: str | None
    is_replay: bool = False


@dataclass(frozen=True)
class ActivatedGrant:
    grant: ExternalReportGrant
    rotated_grant_ids: tuple[uuid.UUID, ...] = ()


@dataclass(frozen=True)
class DeliveryDispatch:
    grant: ExternalReportGrant
    raw_token: str | None
    needs_provider_submission: bool


@dataclass(frozen=True)
class _DeliveryReconciliationCandidate:
    """Immutable delivery identity captured before any provider network I/O."""

    grant_id: uuid.UUID
    analysis_id: uuid.UUID
    operation_digest: str | None
    delivery_email: str
    canonical_email: str
    delivery_state: str
    dispatch_started_at: datetime | None
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    has_ciphertext: bool
    reconciliation_attempt_count: int
    reconciliation_next_attempt_at: datetime | None


class _DeliveryReconciliationCounts(TypedDict):
    activated: int
    cancelled_by_policy: int
    cancelled_expired: int
    outcome_unknown: int
    ciphertext_cleared: int
    lookup_not_found: int
    reconciliation_alerts: int
    processed: int
    has_more: bool


_DeliveryActivationOutcome = Literal[
    "activated",
    "cancelled_by_policy",
    "cancelled_expired",
    "skipped",
]


_DELIVERY_UNIQUE_CONSTRAINTS = {
    "uq_external_report_grants_org_delivery_operation",
    "uq_external_report_grants_one_unresolved_delivery",
}


def _integrity_constraint_name(exc: IntegrityError) -> str | None:
    original = exc.orig
    # psycopg exposes ``diag.constraint_name`` while SQLAlchemy's asyncpg
    # adapter may wrap the native exception as the chained cause. Inspect only
    # this bounded set of driver surfaces; callers still allowlist exact names.
    for source in (
        original,
        getattr(original, "__cause__", None),
        getattr(original, "__context__", None),
    ):
        name = getattr(source, "constraint_name", None)
        if isinstance(name, str) and name:
            return name
        diagnostic = getattr(source, "diag", None)
        name = getattr(diagnostic, "constraint_name", None)
        if isinstance(name, str) and name:
            return name
    return None


def _replay_delivery(
    existing: ExternalReportGrant,
    *,
    request_hash: str,
    now: datetime,
) -> CreatedGrant:
    if not compare_digest(existing.delivery_request_hash or "", request_hash):
        raise APIError(
            409,
            "Conflict",
            "Idempotency-Key was already used with a different invitation request",
        )
    if existing.revoked_at is not None or _utc(existing.expires_at) <= now:
        raise APIError(410, "Gone", "External report invitation is no longer available")
    raw_token = (
        _decrypt_delivery_token(existing)
        if existing.delivery_token_ciphertext is not None
        and existing.delivery_state in {"prepared", "provider_accepted"}
        else None
    )
    return CreatedGrant(grant=existing, raw_token=raw_token, is_replay=True)


def validate_delivery_idempotency_key(value: str) -> str:
    """Validate a high-entropy, log-safe client operation key."""
    normalized = value.strip()
    if not DELIVERY_KEY_MIN_LENGTH <= len(normalized) <= DELIVERY_KEY_MAX_LENGTH:
        raise APIError(
            422,
            "Validation Error",
            "Idempotency-Key must contain 16 to 128 visible ASCII characters",
        )
    if any(ord(character) < 0x21 or ord(character) > 0x7E for character in normalized):
        raise APIError(
            422,
            "Validation Error",
            "Idempotency-Key must contain 16 to 128 visible ASCII characters",
        )
    return normalized


def _delivery_keyring() -> ExternalReportDeliveryKeyRing:
    try:
        return ExternalReportDeliveryKeyRing.from_secret(
            get_settings().external_report_delivery_keyring_secret.get_secret_value()
        )
    except ValueError as exc:
        raise RuntimeError("External report delivery keyring is invalid") from exc


def _derive_delivery_key(*, root_key: bytes, info: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"praviar:external-report-delivery:hkdf-salt:v1",
        info=info,
    ).derive(root_key)


def _delivery_operation_digest(*, org_id: uuid.UUID, idempotency_key: str) -> str:
    key = _delivery_keyring().operation_hmac_key
    message = f"{org_id}\x00{idempotency_key}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _delivery_request_hash(
    *,
    analysis_id: uuid.UUID,
    recipient_email: str,
    expires_in_days: int,
    max_views: int,
) -> str:
    canonical = json.dumps(
        {
            "analysis_id": str(analysis_id),
            "expires_in_days": expires_in_days,
            "max_views": max_views,
            "recipient_email": recipient_email,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _delivery_aad(grant: ExternalReportGrant) -> bytes:
    return (
        "praviar:external-report-delivery:v1\x00"
        f"{grant.org_id}\x00{grant.analysis_id}\x00{grant.id}\x00"
        f"{grant.delivery_operation_key_digest}\x00{grant.delivery_request_hash}"
    ).encode()


def _encrypt_delivery_token(grant: ExternalReportGrant, raw_token: str) -> str:
    keyring = _delivery_keyring()
    grant.delivery_encryption_key_id = keyring.active_key_id
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(
        _derive_delivery_key(root_key=keyring.active_encryption_key, info=_DELIVERY_AES_INFO)
    ).encrypt(
        nonce,
        raw_token.encode("utf-8"),
        _delivery_aad(grant),
    )
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def _decrypt_delivery_token(grant: ExternalReportGrant) -> str:
    encoded = grant.delivery_token_ciphertext
    if not encoded:
        raise APIError(409, "Conflict", "Invitation delivery token is unavailable")
    key_id = grant.delivery_encryption_key_id
    if not key_id:
        raise RuntimeError("External report delivery encryption key id is missing")
    try:
        keyring = _delivery_keyring()
        packed = base64.urlsafe_b64decode(encoded.encode("ascii"))
        plaintext = AESGCM(
            _derive_delivery_key(root_key=keyring.encryption_key(key_id), info=_DELIVERY_AES_INFO)
        ).decrypt(
            packed[:12],
            packed[12:],
            _delivery_aad(grant),
        )
        token = plaintext.decode("utf-8")
    except Exception as exc:
        raise RuntimeError("External report delivery token could not be decrypted") from exc
    validate_grant_token_shape(token)
    if not compare_digest(grant.grant_token_hash, _secret_digest(token)):
        raise RuntimeError("External report delivery token digest mismatch")
    return token


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _secret_digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def validate_grant_token_shape(token: str) -> None:
    """Reject malformed locators before persistence access."""
    if not GRANT_TOKEN_MIN_LENGTH <= len(token) <= GRANT_TOKEN_MAX_LENGTH:
        raise APIError(404, "Not Found", "Shared report is unavailable")
    if any(
        character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        for character in token
    ):
        raise APIError(404, "Not Found", "Shared report is unavailable")


def normalize_recipient_email(value: str) -> tuple[str, str, str]:
    """Return preserved delivery address, canonical identity, and IDNA domain."""
    try:
        result = validate_email(
            value,
            check_deliverability=False,
            allow_smtputf8=False,
        )
    except EmailNotValidError as exc:
        raise APIError(422, "Validation Error", "Enter a valid recipient email") from exc
    delivery_email = result.ascii_email or result.normalized
    canonical_email = delivery_email.casefold()
    local_part, separator, domain = canonical_email.rpartition("@")
    if not separator or not local_part or not domain or "." not in domain:
        raise APIError(422, "Validation Error", "Enter a valid recipient email")
    return delivery_email, canonical_email, domain


def serialize_grant(grant: ExternalReportGrant) -> dict[str, Any]:
    """Build sender-only grant metadata."""
    now = datetime.now(UTC)
    delivery_state = getattr(grant, "delivery_state", "active")
    terminal_reason = getattr(grant, "delivery_terminal_reason", None)
    if delivery_state == "cancelled" and terminal_reason == "policy":
        grant_status = "delivery_cancelled_by_policy"
    elif delivery_state == "cancelled" and terminal_reason == "expired":
        grant_status = "delivery_cancelled_expired"
    elif delivery_state == "cancelled" and terminal_reason == "retention_expired":
        grant_status = "delivery_cancelled_retention_expired"
    elif (
        delivery_state == "outcome_unknown"
        and getattr(grant, "delivery_reconciliation_alerted_at", None) is not None
    ):
        grant_status = "delivery_reconciliation_alert"
    elif grant.revoked_at is not None:
        grant_status = "revoked"
    elif _utc(grant.expires_at) <= now:
        grant_status = "expired"
    elif delivery_state == "rejected":
        grant_status = "delivery_rejected"
    elif delivery_state == "outcome_unknown":
        grant_status = "delivery_outcome_unknown"
    elif grant.invitation_sent_at is None:
        grant_status = "delivery_pending"
    elif grant.view_count >= grant.max_views:
        grant_status = "view_limit_reached"
    else:
        grant_status = "active"
    return {
        "id": grant.id,
        "recipient_email": grant.recipient_email,
        "recipient_domain": grant.recipient_domain,
        "invitation_sent_at": grant.invitation_sent_at,
        "expires_at": grant.expires_at,
        "revoked_at": grant.revoked_at,
        "max_views": grant.max_views,
        "view_count": grant.view_count,
        "download_allowed": grant.download_allowed,
        "max_downloads": grant.max_downloads,
        "download_count": grant.download_count,
        "last_accessed_at": grant.last_accessed_at,
        "status": grant_status,
    }


async def _refresh_analysis_share_state(
    db: AsyncSession,
    *,
    analysis: Analysis,
    now: datetime,
) -> None:
    active_filter = (
        ExternalReportGrant.analysis_id == analysis.id,
        ExternalReportGrant.org_id == analysis.org_id,
        ExternalReportGrant.revoked_at.is_(None),
        ExternalReportGrant.invitation_sent_at.is_not(None),
        ExternalReportGrant.expires_at > now,
        ExternalReportGrant.view_count < ExternalReportGrant.max_views,
    )
    count_result = await db.execute(
        select(func.count(ExternalReportGrant.id), func.max(ExternalReportGrant.expires_at)).where(
            *active_filter
        )
    )
    active_count, active_until = count_result.one()
    analysis.share_active_grant_count = int(active_count or 0)
    analysis.share_active_until = active_until


def _invitation_message(*, report_url: str, expires_at: datetime) -> tuple[str, str, str]:
    safe_url = esc_url(report_url)
    expiry = esc(_utc(expires_at).strftime("%d %b %Y at %H:%M UTC"))
    html = wrap_email(
        "A Praviar report was shared with you",
        f"""
<tr><td style="padding:32px;">
  <h2 style="margin:0 0 16px;font-size:22px;color:#0B1F24;">A report is ready for your review</h2>
  <p style="margin:0 0 20px;line-height:1.6;color:#516F68;">The sender bound this read-only report grant to this mailbox. Opening the link will require a one-time code sent to the same mailbox.</p>
  <p style="margin:0 0 24px;"><a href="{safe_url}" style="display:inline-block;padding:12px 20px;border-radius:8px;background:#0E6F68;color:#FFFFFF;text-decoration:none;font-weight:700;">Verify and view report</a></p>
  <p style="margin:0;font-size:13px;line-height:1.6;color:#516F68;">Grant expires {expiry}. Downloads and workspace access are disabled.</p>
</td></tr>
""",
    )
    text = (
        "A Praviar report was shared with you. Open the link and request the "
        f"one-time mailbox verification code: {report_url}\nGrant expires {expiry}. "
        "Downloads and workspace access are disabled."
    )
    return "A Praviar report was shared with you", html, text


def _verification_message(*, code: str) -> tuple[str, str, str]:
    safe_code = esc(code)
    html = wrap_email(
        "Your Praviar verification code",
        f"""
<tr><td style="padding:32px;">
  <h2 style="margin:0 0 16px;font-size:22px;color:#0B1F24;">Verify report access</h2>
  <p style="margin:0 0 18px;line-height:1.6;color:#516F68;">Enter this one-time code in the report access page. It expires in 10 minutes.</p>
  <p style="margin:0 0 18px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:30px;font-weight:800;letter-spacing:0.18em;color:#0B4F4C;">{safe_code}</p>
  <p style="margin:0;font-size:13px;line-height:1.6;color:#516F68;">If you did not request this code, do not forward it and contact the sender.</p>
</td></tr>
""",
    )
    text = f"Your Praviar report access code is {code}. It expires in 10 minutes."
    return "Your Praviar report access code", html, text


async def _send_or_fail(
    *,
    email_client: PostmarkClient,
    recipient_email: str,
    subject: str,
    html: str,
    text: str,
    tag: str,
) -> None:
    result = await email_client.send_email(
        to=recipient_email,
        subject=subject,
        html_body=html,
        text_body=text,
        tag=tag,
    )
    if not result.success:
        raise APIError(
            503,
            "Service Unavailable",
            "Recipient verification email was not accepted for delivery",
        )


async def create_external_report_grant(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    created_by: uuid.UUID,
    recipient_email: str,
    expires_in_days: int,
    max_views: int,
    idempotency_key: str,
    now_fn=datetime.now,
) -> CreatedGrant:
    """Prepare or replay one durable recipient-bound delivery operation."""
    normalized_key = validate_delivery_idempotency_key(idempotency_key)
    delivery_email, canonical_email, recipient_domain = normalize_recipient_email(recipient_email)
    operation_digest = _delivery_operation_digest(
        org_id=org_id,
        idempotency_key=normalized_key,
    )
    request_hash = _delivery_request_hash(
        analysis_id=analysis_id,
        recipient_email=canonical_email,
        expires_in_days=expires_in_days,
        max_views=max_views,
    )
    now = now_fn(UTC)
    existing_result = await db.execute(
        select(ExternalReportGrant)
        .where(
            ExternalReportGrant.org_id == org_id,
            ExternalReportGrant.delivery_operation_key_digest == operation_digest,
        )
        .with_for_update()
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        return _replay_delivery(existing, request_hash=request_hash, now=now)

    # The policy mutation path takes the same organization row lock before
    # revoking grants, closing the allow-check/create race.
    policy = await get_external_sharing_policy(db, org_id=org_id, for_update=True)
    # The first read may have raced a same-key transaction that committed while
    # this request waited for the organization lock. Recheck exact operation
    # identity before treating the winner as a generic recipient conflict.
    exact_result = await db.execute(
        select(ExternalReportGrant)
        .where(
            ExternalReportGrant.org_id == org_id,
            ExternalReportGrant.delivery_operation_key_digest == operation_digest,
        )
        .with_for_update()
    )
    exact = exact_result.scalar_one_or_none()
    if exact is not None:
        return _replay_delivery(exact, request_hash=request_hash, now=now)
    unresolved_result = await db.execute(
        select(ExternalReportGrant)
        .where(
            ExternalReportGrant.org_id == org_id,
            ExternalReportGrant.analysis_id == analysis_id,
            ExternalReportGrant.recipient_email_normalized == canonical_email,
            ExternalReportGrant.delivery_state.in_(_UNRESOLVED_DELIVERY_STATES),
        )
        .with_for_update()
    )
    expired_delivery_cancelled = False
    for unresolved in unresolved_result.scalars().all():
        if unresolved.revoked_at is not None or _utc(unresolved.expires_at) <= now:
            _cancel_reconciled_delivery(
                db,
                grant=unresolved,
                now=now,
                audit_action="report.share.delivery_cancelled_expired",
                reason="grant_expired_before_dispatch_completed",
            )
            expired_delivery_cancelled = True
            continue
        raise APIError(
            409,
            "Invitation already in progress",
            "An invitation for this report and recipient is already "
            f"{unresolved.delivery_state}; retry it with its original "
            "Idempotency-Key or revoke it before creating another invitation",
        )
    if expired_delivery_cancelled:
        # Release the partial unique-index slot before inserting its successor.
        await db.flush()
    analysis = await get_analysis_for_org(db, analysis_id=analysis_id, org_id=org_id)
    await ensure_analysis_export_ready(
        db,
        analysis_id=analysis_id,
        org_id=org_id,
        analysis=analysis,
    )
    require_recipient_domain_allowed(
        policy,
        recipient_domain=recipient_domain,
    )
    expires_at = now + timedelta(days=expires_in_days)

    raw_token = secrets.token_urlsafe(32)
    grant = ExternalReportGrant(
        id=uuid.uuid4(),
        org_id=org_id,
        analysis_id=analysis_id,
        created_by=created_by,
        recipient_email=delivery_email,
        recipient_email_normalized=canonical_email,
        recipient_domain=recipient_domain,
        grant_token_hash=_secret_digest(raw_token),
        report_fingerprint=report_payload_fingerprint(analysis.report_data or {}),
        delivery_operation_key_digest=operation_digest,
        delivery_request_hash=request_hash,
        delivery_state="prepared",
        expires_at=expires_at,
        max_views=max_views,
        download_allowed=False,
        max_downloads=0,
    )
    grant.delivery_token_ciphertext = _encrypt_delivery_token(grant, raw_token)
    db.add(grant)
    try:
        await db.flush()
    except IntegrityError as exc:
        constraint_name = _integrity_constraint_name(exc)
        await db.rollback()
        if constraint_name not in _DELIVERY_UNIQUE_CONSTRAINTS:
            raise
        await get_external_sharing_policy(db, org_id=org_id, for_update=True)
        winner_result = await db.execute(
            select(ExternalReportGrant)
            .where(
                ExternalReportGrant.org_id == org_id,
                ExternalReportGrant.delivery_operation_key_digest == operation_digest,
            )
            .with_for_update()
        )
        winner = winner_result.scalar_one_or_none()
        if winner is not None:
            return _replay_delivery(winner, request_hash=request_hash, now=now)
        conflicting_result = await db.execute(
            select(ExternalReportGrant)
            .where(
                ExternalReportGrant.org_id == org_id,
                ExternalReportGrant.analysis_id == analysis_id,
                ExternalReportGrant.recipient_email_normalized == canonical_email,
                ExternalReportGrant.delivery_state.in_(_UNRESOLVED_DELIVERY_STATES),
            )
            .with_for_update()
        )
        conflicting = conflicting_result.scalar_one_or_none()
        if conflicting is not None:
            raise APIError(
                409,
                "Invitation already in progress",
                "An invitation for this report and recipient is already in progress; "
                "retry it with its original Idempotency-Key or revoke it first",
            ) from exc
        raise RuntimeError("Delivery uniqueness conflict could not be resolved") from exc

    logger.info(
        "external_report_grant_created_pending_delivery",
        grant_id=str(grant.id),
        analysis_id=str(analysis_id),
        org_id=str(org_id),
        recipient_domain=recipient_domain,
    )
    return CreatedGrant(grant=grant, raw_token=raw_token, is_replay=False)


async def send_external_report_grant_invitation(
    created: CreatedGrant,
    *,
    email_client: PostmarkClient | None = None,
) -> DeliverySubmissionResult:
    """Submit one already-dispatched grant invitation exactly once."""
    if created.raw_token is None:
        raise APIError(409, "Conflict", "Invitation delivery token is unavailable")
    settings = get_settings()
    report_url = f"{settings.app_url.rstrip('/')}/share/{created.raw_token}"
    subject, html, text = _invitation_message(
        report_url=report_url,
        expires_at=created.grant.expires_at,
    )
    submission_id = created.grant.delivery_operation_key_digest
    if not submission_id:
        raise APIError(500, "Delivery unavailable", "Invitation operation identity is missing")
    client = email_client or get_email_client()
    return await client.submit_email_once(
        to=created.grant.recipient_email,
        subject=subject,
        html_body=html,
        text_body=text,
        tag="external-report-grant",
        submission_id=submission_id,
    )


async def claim_external_report_delivery_dispatch(
    db: AsyncSession,
    *,
    grant_id: uuid.UUID,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    now_fn=datetime.now,
) -> DeliveryDispatch:
    """Persist the at-most-once dispatch boundary before any provider call."""
    result = await db.execute(
        select(ExternalReportGrant)
        .where(
            ExternalReportGrant.id == grant_id,
            ExternalReportGrant.analysis_id == analysis_id,
            ExternalReportGrant.org_id == org_id,
        )
        .with_for_update()
    )
    grant = result.scalar_one_or_none()
    if grant is None:
        raise APIError(404, "Not Found", "External report grant not found")
    now = now_fn(UTC)
    if grant.revoked_at is not None or _utc(grant.expires_at) <= now:
        raise APIError(410, "Gone", "External report invitation is no longer available")
    state = grant.delivery_state
    if state == "prepared":
        raw_token = _decrypt_delivery_token(grant)
        grant.delivery_state = "dispatching"
        grant.delivery_dispatch_started_at = now
        await db.flush()
        return DeliveryDispatch(
            grant=grant,
            raw_token=raw_token,
            needs_provider_submission=True,
        )
    if state == "provider_accepted":
        return DeliveryDispatch(
            grant=grant,
            raw_token=(
                _decrypt_delivery_token(grant)
                if grant.delivery_token_ciphertext is not None
                else None
            ),
            needs_provider_submission=False,
        )
    if state == "active":
        return DeliveryDispatch(grant=grant, raw_token=None, needs_provider_submission=False)
    if state in {"dispatching", "outcome_unknown"}:
        raise APIError(
            503,
            "Invitation outcome unknown",
            "The provider outcome could not be confirmed and this invitation will not be resent",
        )
    if state == "rejected":
        raise APIError(
            503,
            "Invitation rejected",
            "The email provider rejected this invitation; use a new Idempotency-Key to retry",
        )
    raise RuntimeError(f"Unsupported external report delivery state: {state}")


async def record_external_report_delivery_result(
    db: AsyncSession,
    *,
    grant_id: uuid.UUID,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    result: DeliverySubmissionResult,
    now_fn=datetime.now,
) -> ExternalReportGrant:
    """Persist provider acceptance or a terminal no-resend outcome."""
    loaded = await db.execute(
        select(ExternalReportGrant)
        .where(
            ExternalReportGrant.id == grant_id,
            ExternalReportGrant.analysis_id == analysis_id,
            ExternalReportGrant.org_id == org_id,
        )
        .with_for_update()
    )
    grant = loaded.scalar_one_or_none()
    if grant is None:
        raise APIError(404, "Not Found", "External report grant not found")
    if grant.delivery_state != "dispatching":
        raise APIError(409, "Conflict", "Invitation dispatch state changed")
    now = now_fn(UTC)
    if result.status == "accepted":
        grant.delivery_state = "provider_accepted"
        grant.delivery_provider_accepted_at = now
        grant.delivery_provider_message_id = result.message_id
    elif result.status in {"rejected", "outcome_unknown"}:
        grant.delivery_state = result.status
        grant.delivery_terminal_at = now
        grant.delivery_token_ciphertext = None
        grant.delivery_provider_message_id = None
    else:  # pragma: no cover - constrained dataclass contract
        raise RuntimeError(f"Unsupported provider result: {result.status}")
    await db.flush()
    return grant


async def list_external_report_grants(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[ExternalReportGrant]:
    await get_analysis_for_org(db, analysis_id=analysis_id, org_id=org_id)
    result = await db.execute(
        select(ExternalReportGrant)
        .where(
            ExternalReportGrant.analysis_id == analysis_id,
            ExternalReportGrant.org_id == org_id,
        )
        .order_by(ExternalReportGrant.created_at.desc())
    )
    return list(result.scalars().all())


async def list_external_report_grant_activity(
    db: AsyncSession,
    *,
    grant_id: uuid.UUID,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
) -> list[ExternalReportGrantActivityItem]:
    """Return a non-secret timeline for exactly one tenant-scoped grant.

    Internal preparation is omitted, while non-secret dispatch and provider
    acceptance states make crash recovery reconstructable for the sender.
    """
    await get_analysis_for_org(db, analysis_id=analysis_id, org_id=org_id)
    grant_result = await db.execute(
        select(ExternalReportGrant.id).where(
            ExternalReportGrant.id == grant_id,
            ExternalReportGrant.analysis_id == analysis_id,
            ExternalReportGrant.org_id == org_id,
        )
    )
    if grant_result.scalar_one_or_none() is None:
        raise APIError(404, "Not Found", "External report grant not found")

    audit_result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.org_id == org_id,
            AuditLog.analysis_id == analysis_id,
            AuditLog.action.in_(tuple(_GRANT_ACTIVITY_EVENTS)),
            AuditLog.details["external_grant_id"].as_string() == str(grant_id),
        )
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
    )
    items: list[ExternalReportGrantActivityItem] = []
    for event in audit_result.scalars().all():
        view_number = event.details.get("view_number")
        items.append(
            ExternalReportGrantActivityItem(
                id=event.id,
                event=_GRANT_ACTIVITY_EVENTS[event.action],
                occurred_at=event.created_at,
                view_number=(
                    view_number
                    if isinstance(view_number, int)
                    and not isinstance(view_number, bool)
                    and view_number > 0
                    else None
                ),
            )
        )
    return items


async def activate_external_report_grant(
    db: AsyncSession,
    *,
    grant_id: uuid.UUID,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    reconciliation_lease_id: uuid.UUID | None = None,
    now_fn=datetime.now,
) -> ActivatedGrant:
    """After provider acceptance, activate new access and rotate old access atomically."""
    if reconciliation_lease_id is not None:
        lease_result = await db.execute(
            select(Organization.id)
            .where(
                Organization.id == org_id,
                Organization.external_report_delivery_reconciliation_lease_id
                == reconciliation_lease_id,
                Organization.external_report_delivery_reconciliation_lease_expires_at > now_fn(UTC),
            )
            .with_for_update()
        )
        if lease_result.scalar_one_or_none() is None:
            raise APIError(409, "Conflict", "Delivery reconciliation lease is no longer current")
    policy = await get_external_sharing_policy(db, org_id=org_id, for_update=True)
    analysis = await get_analysis_for_org(db, analysis_id=analysis_id, org_id=org_id)
    result = await db.execute(
        select(ExternalReportGrant)
        .where(
            ExternalReportGrant.id == grant_id,
            ExternalReportGrant.analysis_id == analysis_id,
            ExternalReportGrant.org_id == org_id,
            ExternalReportGrant.revoked_at.is_(None),
        )
        .with_for_update()
    )
    grant = result.scalar_one_or_none()
    if grant is None:
        raise APIError(404, "Not Found", "External report grant not found")
    now = now_fn(UTC)
    if _utc(grant.expires_at) <= now:
        raise APIError(410, "Gone", "External report grant expired before activation")
    require_recipient_domain_allowed(
        policy,
        recipient_domain=grant.recipient_domain,
    )
    if grant.invitation_sent_at is not None:
        if grant.delivery_state == "active":
            return ActivatedGrant(grant=grant)
        raise APIError(409, "Conflict", "External report grant is already active")
    if grant.delivery_state != "provider_accepted":
        raise APIError(409, "Conflict", "Invitation has not been accepted by the provider")

    rotation_result = await db.execute(
        select(ExternalReportGrant)
        .where(
            ExternalReportGrant.id != grant.id,
            ExternalReportGrant.analysis_id == analysis_id,
            ExternalReportGrant.org_id == org_id,
            ExternalReportGrant.recipient_email_normalized == grant.recipient_email_normalized,
            ExternalReportGrant.revoked_at.is_(None),
            ExternalReportGrant.invitation_sent_at.is_not(None),
            ExternalReportGrant.expires_at > now,
            ExternalReportGrant.view_count < ExternalReportGrant.max_views,
        )
        .with_for_update()
    )
    rotated_grants = tuple(rotation_result.scalars().all())
    for rotated_grant in rotated_grants:
        rotated_grant.revoked_at = now
        rotated_grant.verification_code_hash = None
        rotated_grant.verification_expires_at = None
        rotated_grant.verification_sent_at = None
        rotated_grant.verification_consumed_at = None
        rotated_grant.verification_attempt_count = 0
        rotated_grant.access_secret_hash = None
        rotated_grant.access_expires_at = None

    grant.invitation_sent_at = now
    grant.delivery_state = "active"
    grant.delivery_terminal_at = now
    grant.delivery_token_ciphertext = None
    grant.delivery_reconciliation_next_attempt_at = None
    await _refresh_analysis_share_state(db, analysis=analysis, now=now)
    return ActivatedGrant(
        grant=grant,
        rotated_grant_ids=tuple(rotated_grant.id for rotated_grant in rotated_grants),
    )


def add_external_report_activation_audits(
    db: AsyncSession,
    *,
    activated: ActivatedGrant,
) -> None:
    """Add non-secret activation and rotation audits to the current transaction."""
    grant = activated.grant
    base = {
        "recipient_email": grant.recipient_email,
        "recipient_domain": grant.recipient_domain,
    }
    db.add(
        AuditLog(
            org_id=grant.org_id,
            user_id=grant.created_by,
            analysis_id=grant.analysis_id,
            action="report.share.invitation_sent",
            details={"external_grant_id": str(grant.id), **base},
            ip_address="",
        )
    )
    for rotated_id in activated.rotated_grant_ids:
        db.add(
            AuditLog(
                org_id=grant.org_id,
                user_id=grant.created_by,
                analysis_id=grant.analysis_id,
                action="report.share.grant_revoked_by_reissue",
                details={
                    "external_grant_id": str(rotated_id),
                    "replacement_external_grant_id": str(grant.id),
                    "recipient_domain": grant.recipient_domain,
                },
                ip_address="",
            )
        )
    if activated.rotated_grant_ids:
        db.add(
            AuditLog(
                org_id=grant.org_id,
                user_id=grant.created_by,
                analysis_id=grant.analysis_id,
                action="report.share.recipient_grants_rotated",
                details={
                    "replacement_external_grant_id": str(grant.id),
                    **base,
                    "revoked_external_grant_ids": [
                        str(grant_id) for grant_id in activated.rotated_grant_ids
                    ],
                    "revoked_grant_count": len(activated.rotated_grant_ids),
                },
                ip_address="",
            )
        )


async def _lock_delivery_reconciliation_candidate(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    candidate: _DeliveryReconciliationCandidate,
    reconciliation_lease_id: uuid.UUID | None = None,
) -> ExternalReportGrant | None:
    """Lock one candidate in the canonical organization -> grant order."""
    organization_statement = select(Organization.id).where(Organization.id == org_id)
    if reconciliation_lease_id is not None:
        organization_statement = organization_statement.where(
            Organization.external_report_delivery_reconciliation_lease_id
            == reconciliation_lease_id,
            Organization.external_report_delivery_reconciliation_lease_expires_at
            > datetime.now(UTC),
        )
    organization_result = await db.execute(organization_statement.with_for_update())
    if organization_result.scalar_one_or_none() is None:
        return None
    operation_filter = (
        ExternalReportGrant.delivery_operation_key_digest == candidate.operation_digest
        if candidate.operation_digest is not None
        else ExternalReportGrant.delivery_operation_key_digest.is_(None)
    )
    grant_result = await db.execute(
        select(ExternalReportGrant)
        .where(
            ExternalReportGrant.id == candidate.grant_id,
            ExternalReportGrant.analysis_id == candidate.analysis_id,
            ExternalReportGrant.org_id == org_id,
            ExternalReportGrant.recipient_email_normalized == candidate.canonical_email,
            operation_filter,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    return grant_result.scalar_one_or_none()


def _clear_delivery_ciphertext(grant: ExternalReportGrant) -> bool:
    if grant.delivery_token_ciphertext is None:
        return False
    grant.delivery_token_ciphertext = None
    return True


def _schedule_delivery_reconciliation_retry(
    grant: ExternalReportGrant,
    *,
    now: datetime,
) -> None:
    attempt_count = max(0, int(grant.delivery_reconciliation_attempt_count or 0)) + 1
    grant.delivery_reconciliation_attempt_count = attempt_count
    delay_seconds = min(
        DELIVERY_RECONCILIATION_BASE_BACKOFF.total_seconds() * (2 ** min(attempt_count - 1, 12)),
        DELIVERY_RECONCILIATION_MAX_BACKOFF.total_seconds(),
    )
    grant.delivery_reconciliation_next_attempt_at = now + timedelta(seconds=delay_seconds)


def _cancel_reconciled_delivery(
    db: AsyncSession,
    *,
    grant: ExternalReportGrant,
    now: datetime,
    audit_action: str,
    reason: str,
) -> None:
    """Fail closed after acceptance when the grant can no longer activate."""
    grant.revoked_at = grant.revoked_at or now
    grant.delivery_state = "cancelled"
    grant.delivery_terminal_at = now
    grant.delivery_terminal_reason = {
        "report.share.delivery_cancelled_by_policy": "policy",
        "report.share.delivery_cancelled_expired": "expired",
        "report.share.delivery_cancelled_retention_expired": "retention_expired",
    }[audit_action]
    grant.delivery_token_ciphertext = None
    grant.verification_code_hash = None
    grant.verification_expires_at = None
    grant.verification_sent_at = None
    grant.verification_consumed_at = None
    grant.access_secret_hash = None
    grant.access_expires_at = None
    db.add(
        AuditLog(
            org_id=grant.org_id,
            user_id=grant.created_by,
            analysis_id=grant.analysis_id,
            action=audit_action,
            details={
                "external_grant_id": str(grant.id),
                "recipient_domain": grant.recipient_domain,
                "reason": reason,
                "provider_resubmission_blocked": True,
            },
            ip_address="",
        )
    )


async def _activate_reconciled_delivery(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    candidate: _DeliveryReconciliationCandidate,
    now: datetime,
    now_fn,
    reconciliation_lease_id: uuid.UUID | None,
) -> _DeliveryActivationOutcome:
    """Activate a recovered acceptance or terminalize it without aborting the sweep."""
    try:
        activated = await activate_external_report_grant(
            db,
            grant_id=candidate.grant_id,
            analysis_id=candidate.analysis_id,
            org_id=org_id,
            reconciliation_lease_id=reconciliation_lease_id,
            now_fn=now_fn,
        )
    except APIError as exc:
        if exc.status not in {403, 404, 409, 410}:
            raise
        await db.rollback()
        grant = await _lock_delivery_reconciliation_candidate(
            db,
            org_id=org_id,
            candidate=candidate,
            reconciliation_lease_id=reconciliation_lease_id,
        )
        if grant is None:
            await db.commit()
            return "skipped"
        if grant.revoked_at is not None:
            _clear_delivery_ciphertext(grant)
            await db.commit()
            return "skipped"
        if grant.delivery_state != "provider_accepted":
            await db.commit()
            return "skipped"
        if exc.status == 403:
            _cancel_reconciled_delivery(
                db,
                grant=grant,
                now=now,
                audit_action="report.share.delivery_cancelled_by_policy",
                reason="recipient_domain_no_longer_allowed",
            )
            await db.commit()
            return "cancelled_by_policy"
        if exc.status == 410:
            _cancel_reconciled_delivery(
                db,
                grant=grant,
                now=now,
                audit_action="report.share.delivery_cancelled_expired",
                reason="grant_expired_before_activation",
            )
            await db.commit()
            return "cancelled_expired"
        await db.commit()
        return "skipped"
    add_external_report_activation_audits(db, activated=activated)
    await db.commit()
    return "activated"


def _new_delivery_reconciliation_counts() -> _DeliveryReconciliationCounts:
    return {
        "activated": 0,
        "cancelled_by_policy": 0,
        "cancelled_expired": 0,
        "outcome_unknown": 0,
        "ciphertext_cleared": 0,
        "lookup_not_found": 0,
        "reconciliation_alerts": 0,
        "processed": 0,
        "has_more": False,
    }


def _delivery_reconciliation_candidate(
    row: Any,
    *,
    now: datetime,
) -> _DeliveryReconciliationCandidate:
    return _DeliveryReconciliationCandidate(
        grant_id=row.id,
        analysis_id=row.analysis_id,
        operation_digest=row.delivery_operation_key_digest,
        delivery_email=getattr(row, "recipient_email", row.recipient_email_normalized),
        canonical_email=row.recipient_email_normalized,
        delivery_state=row.delivery_state,
        dispatch_started_at=row.delivery_dispatch_started_at,
        created_at=getattr(row, "created_at", now),
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        has_ciphertext=row.delivery_token_ciphertext is not None,
        reconciliation_attempt_count=getattr(row, "delivery_reconciliation_attempt_count", 0),
        reconciliation_next_attempt_at=getattr(
            row,
            "delivery_reconciliation_next_attempt_at",
            None,
        ),
    )


async def _discover_delivery_reconciliation_candidates(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    now: datetime,
    batch_size: int,
) -> tuple[tuple[_DeliveryReconciliationCandidate, ...], bool]:
    result = await db.execute(
        select(
            ExternalReportGrant.id,
            ExternalReportGrant.analysis_id,
            ExternalReportGrant.delivery_operation_key_digest,
            ExternalReportGrant.recipient_email,
            ExternalReportGrant.recipient_email_normalized,
            ExternalReportGrant.delivery_state,
            ExternalReportGrant.delivery_dispatch_started_at,
            ExternalReportGrant.created_at,
            ExternalReportGrant.expires_at,
            ExternalReportGrant.revoked_at,
            ExternalReportGrant.delivery_token_ciphertext,
            ExternalReportGrant.delivery_reconciliation_attempt_count,
            ExternalReportGrant.delivery_reconciliation_next_attempt_at,
        )
        .where(
            ExternalReportGrant.org_id == org_id,
            or_(
                ExternalReportGrant.delivery_state == "provider_accepted",
                and_(
                    ExternalReportGrant.delivery_state == "prepared",
                    ExternalReportGrant.expires_at <= now,
                ),
                and_(
                    ExternalReportGrant.delivery_state == "dispatching",
                    or_(
                        ExternalReportGrant.expires_at <= now,
                        ExternalReportGrant.delivery_dispatch_started_at.is_(None),
                        ExternalReportGrant.delivery_dispatch_started_at
                        <= now - DELIVERY_DISPATCH_TIMEOUT,
                    ),
                ),
                and_(
                    ExternalReportGrant.delivery_state == "outcome_unknown",
                    or_(
                        ExternalReportGrant.expires_at <= now,
                        ExternalReportGrant.delivery_reconciliation_next_attempt_at.is_(None),
                        ExternalReportGrant.delivery_reconciliation_next_attempt_at <= now,
                    ),
                ),
                and_(
                    ExternalReportGrant.delivery_state.in_(("active", "rejected", "cancelled")),
                    ExternalReportGrant.delivery_token_ciphertext.is_not(None),
                ),
            ),
        )
        .order_by(
            case(
                (ExternalReportGrant.delivery_state == "provider_accepted", 0),
                (ExternalReportGrant.expires_at <= now, 1),
                (ExternalReportGrant.delivery_state == "dispatching", 2),
                (ExternalReportGrant.delivery_state == "outcome_unknown", 3),
                else_=4,
            ),
            ExternalReportGrant.delivery_reconciliation_next_attempt_at.asc().nullsfirst(),
            ExternalReportGrant.updated_at.asc(),
        )
        .limit(batch_size + 1)
    )
    discovered_candidates = tuple(
        _delivery_reconciliation_candidate(row, now=now) for row in result.all()
    )
    candidates = discovered_candidates[:batch_size]
    has_more = len(discovered_candidates) > batch_size
    # Release the read transaction before the first provider lookup or row lock.
    await db.commit()
    return candidates, has_more


def _record_activation_outcome(
    counts: _DeliveryReconciliationCounts,
    outcome: _DeliveryActivationOutcome,
) -> None:
    if outcome == "activated":
        counts["activated"] += 1
    elif outcome == "cancelled_by_policy":
        counts["cancelled_by_policy"] += 1
    elif outcome == "cancelled_expired":
        counts["cancelled_expired"] += 1


def _add_delivery_outcome_unknown_audit(
    db: AsyncSession,
    *,
    grant: ExternalReportGrant,
    provider_lookup_retention_expired: bool = False,
) -> None:
    details: dict[str, Any] = {
        "external_grant_id": str(grant.id),
        "recipient_domain": grant.recipient_domain,
        "provider_resubmission_blocked": True,
    }
    if provider_lookup_retention_expired:
        details["provider_lookup_retention_expired"] = True
    db.add(
        AuditLog(
            org_id=grant.org_id,
            user_id=grant.created_by,
            analysis_id=grant.analysis_id,
            action="report.share.delivery_outcome_unknown",
            details=details,
            ip_address="",
        )
    )


async def _reconcile_expired_delivery(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    candidate: _DeliveryReconciliationCandidate,
    now: datetime,
    reconciliation_lease_id: uuid.UUID | None,
    counts: _DeliveryReconciliationCounts,
) -> None:
    grant = await _lock_delivery_reconciliation_candidate(
        db,
        org_id=org_id,
        candidate=candidate,
        reconciliation_lease_id=reconciliation_lease_id,
    )
    if (
        grant is not None
        and grant.delivery_state in _UNRESOLVED_DELIVERY_STATES
        and _utc(grant.expires_at) <= now
    ):
        had_ciphertext = grant.delivery_token_ciphertext is not None
        _cancel_reconciled_delivery(
            db,
            grant=grant,
            now=now,
            audit_action="report.share.delivery_cancelled_expired",
            reason="grant_expired_before_delivery_completed",
        )
        grant.delivery_reconciliation_next_attempt_at = None
        counts["cancelled_expired"] += 1
        if had_ciphertext:
            counts["ciphertext_cleared"] += 1
    await db.commit()


async def _clear_terminal_delivery_ciphertext(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    candidate: _DeliveryReconciliationCandidate,
    reconciliation_lease_id: uuid.UUID | None,
    counts: _DeliveryReconciliationCounts,
) -> None:
    if not candidate.has_ciphertext:
        return
    grant = await _lock_delivery_reconciliation_candidate(
        db,
        org_id=org_id,
        candidate=candidate,
        reconciliation_lease_id=reconciliation_lease_id,
    )
    if grant is not None and _clear_delivery_ciphertext(grant):
        counts["ciphertext_cleared"] += 1
    await db.commit()


async def _reconcile_provider_accepted_delivery(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    candidate: _DeliveryReconciliationCandidate,
    now: datetime,
    now_fn,
    reconciliation_lease_id: uuid.UUID | None,
    counts: _DeliveryReconciliationCounts,
) -> None:
    outcome = await _activate_reconciled_delivery(
        db,
        org_id=org_id,
        candidate=candidate,
        now=now,
        reconciliation_lease_id=reconciliation_lease_id,
        now_fn=now_fn,
    )
    _record_activation_outcome(counts, outcome)


async def _terminalize_delivery_after_provider_retention(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    candidate: _DeliveryReconciliationCandidate,
    now: datetime,
    reconciliation_lease_id: uuid.UUID | None,
    counts: _DeliveryReconciliationCounts,
) -> None:
    grant = await _lock_delivery_reconciliation_candidate(
        db,
        org_id=org_id,
        candidate=candidate,
        reconciliation_lease_id=reconciliation_lease_id,
    )
    if grant is None:
        await db.commit()
        return
    if grant.delivery_state == "dispatching":
        _add_delivery_outcome_unknown_audit(
            db,
            grant=grant,
            provider_lookup_retention_expired=True,
        )
        counts["outcome_unknown"] += 1
    had_ciphertext = grant.delivery_token_ciphertext is not None
    if grant.delivery_state in {"dispatching", "outcome_unknown"}:
        _cancel_reconciled_delivery(
            db,
            grant=grant,
            now=now,
            audit_action="report.share.delivery_cancelled_retention_expired",
            reason="provider_lookup_retention_expired",
        )
        counts["cancelled_expired"] += 1
        grant.delivery_reconciliation_next_attempt_at = None
    if had_ciphertext:
        counts["ciphertext_cleared"] += 1
    await db.commit()


def _record_recovered_provider_acceptance(
    db: AsyncSession,
    *,
    grant: ExternalReportGrant,
    lookup: DeliveryLookupResult,
    now: datetime,
) -> None:
    grant.delivery_reconciliation_attempt_count = (
        int(grant.delivery_reconciliation_attempt_count or 0) + 1
    )
    grant.delivery_reconciliation_next_attempt_at = None
    grant.delivery_state = "provider_accepted"
    grant.delivery_provider_accepted_at = now
    grant.delivery_provider_message_id = lookup.message_id
    db.add(
        AuditLog(
            org_id=grant.org_id,
            user_id=grant.created_by,
            analysis_id=grant.analysis_id,
            action="report.share.delivery_provider_accepted",
            details={
                "external_grant_id": str(grant.id),
                "recipient_domain": grant.recipient_domain,
                "provider_message_id": lookup.message_id,
                "recovered_by_metadata_lookup": True,
            },
            ip_address="",
        )
    )


def _record_unresolved_provider_lookup(
    db: AsyncSession,
    *,
    grant: ExternalReportGrant,
    lookup: DeliveryLookupResult,
    now: datetime,
    counts: _DeliveryReconciliationCounts,
) -> None:
    _schedule_delivery_reconciliation_retry(grant, now=now)
    if grant.delivery_state == "dispatching":
        grant.delivery_state = "outcome_unknown"
        grant.delivery_terminal_at = now
        if _clear_delivery_ciphertext(grant):
            counts["ciphertext_cleared"] += 1
        _add_delivery_outcome_unknown_audit(db, grant=grant)
        counts["outcome_unknown"] += 1
    if lookup.status == "not_found":
        counts["lookup_not_found"] += 1
    if lookup.status == "alert" and grant.delivery_reconciliation_alerted_at is None:
        grant.delivery_reconciliation_alerted_at = now
        db.add(
            AuditLog(
                org_id=grant.org_id,
                user_id=grant.created_by,
                analysis_id=grant.analysis_id,
                action="report.share.delivery_reconciliation_alert",
                details={
                    "external_grant_id": str(grant.id),
                    "recipient_domain": grant.recipient_domain,
                    "reason": lookup.detail,
                },
                ip_address="",
            )
        )
        counts["reconciliation_alerts"] += 1


async def _apply_delivery_lookup_result(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    candidate: _DeliveryReconciliationCandidate,
    lookup: DeliveryLookupResult,
    now: datetime,
    now_fn,
    reconciliation_lease_id: uuid.UUID | None,
    counts: _DeliveryReconciliationCounts,
) -> None:
    grant = await _lock_delivery_reconciliation_candidate(
        db,
        org_id=org_id,
        candidate=candidate,
        reconciliation_lease_id=reconciliation_lease_id,
    )
    if grant is None:
        await db.commit()
        return
    if grant.revoked_at is not None:
        if _clear_delivery_ciphertext(grant):
            counts["ciphertext_cleared"] += 1
        await db.commit()
        return
    if grant.delivery_state not in {"dispatching", "outcome_unknown"}:
        await db.commit()
        return
    if lookup.status == "found":
        _record_recovered_provider_acceptance(db, grant=grant, lookup=lookup, now=now)
        await db.commit()
        await _reconcile_provider_accepted_delivery(
            db,
            org_id=org_id,
            candidate=candidate,
            now=now,
            now_fn=now_fn,
            reconciliation_lease_id=reconciliation_lease_id,
            counts=counts,
        )
    elif lookup.status in {"not_found", "unavailable", "alert"}:
        _record_unresolved_provider_lookup(
            db,
            grant=grant,
            lookup=lookup,
            now=now,
            counts=counts,
        )
        await db.commit()


async def _reconcile_delivery_with_provider_lookup(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    candidate: _DeliveryReconciliationCandidate,
    provider: PostmarkClient,
    provider_retention: timedelta,
    now: datetime,
    now_fn,
    reconciliation_lease_id: uuid.UUID | None,
    counts: _DeliveryReconciliationCounts,
) -> None:
    started_at = candidate.dispatch_started_at or candidate.created_at
    if _utc(started_at) <= now - provider_retention:
        await _terminalize_delivery_after_provider_retention(
            db,
            org_id=org_id,
            candidate=candidate,
            now=now,
            reconciliation_lease_id=reconciliation_lease_id,
            counts=counts,
        )
        return
    lookup = await provider.lookup_outbound_submission(
        submission_id=candidate.operation_digest or "",
        expected_to=candidate.delivery_email,
        expected_subject="A Praviar report was shared with you",
        expected_tag="external-report-grant",
    )
    await _apply_delivery_lookup_result(
        db,
        org_id=org_id,
        candidate=candidate,
        lookup=lookup,
        now=now,
        now_fn=now_fn,
        reconciliation_lease_id=reconciliation_lease_id,
        counts=counts,
    )


async def _reconcile_delivery_candidate(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    candidate: _DeliveryReconciliationCandidate,
    provider: PostmarkClient,
    provider_retention: timedelta,
    now: datetime,
    now_fn,
    reconciliation_lease_id: uuid.UUID | None,
    counts: _DeliveryReconciliationCounts,
) -> None:
    if (
        candidate.delivery_state in _UNRESOLVED_DELIVERY_STATES
        and _utc(candidate.expires_at) <= now
    ):
        await _reconcile_expired_delivery(
            db,
            org_id=org_id,
            candidate=candidate,
            now=now,
            reconciliation_lease_id=reconciliation_lease_id,
            counts=counts,
        )
        return
    if candidate.delivery_state == "prepared":
        # Live prepared rows are intentionally absent from the due query.
        return
    if candidate.revoked_at is not None or candidate.delivery_state in {
        "active",
        "rejected",
        "cancelled",
    }:
        await _clear_terminal_delivery_ciphertext(
            db,
            org_id=org_id,
            candidate=candidate,
            reconciliation_lease_id=reconciliation_lease_id,
            counts=counts,
        )
        return
    if candidate.delivery_state == "provider_accepted":
        await _reconcile_provider_accepted_delivery(
            db,
            org_id=org_id,
            candidate=candidate,
            now=now,
            now_fn=now_fn,
            reconciliation_lease_id=reconciliation_lease_id,
            counts=counts,
        )
        return
    if candidate.delivery_state in {"dispatching", "outcome_unknown"}:
        await _reconcile_delivery_with_provider_lookup(
            db,
            org_id=org_id,
            candidate=candidate,
            provider=provider,
            provider_retention=provider_retention,
            now=now,
            now_fn=now_fn,
            reconciliation_lease_id=reconciliation_lease_id,
            counts=counts,
        )


async def reconcile_external_report_deliveries(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    email_client: PostmarkClient | None = None,
    reconciliation_lease_id: uuid.UUID | None = None,
    batch_size: int = 20,
    time_budget_seconds: float = 210.0,
    now_fn=datetime.now,
    monotonic_fn=time.monotonic,
) -> dict[str, int | bool]:
    """Recover accepted sends through Postmark metadata lookup without resend.

    Provider lookups occur only after the discovery transaction commits. Each
    result is then revalidated while locks are acquired in the canonical
    organization -> grant order, so no network I/O occurs under row locks.
    """
    if batch_size < 1 or batch_size > 100:
        raise ValueError("batch_size must be between 1 and 100")
    if time_budget_seconds <= 0:
        raise ValueError("time_budget_seconds must be positive")
    started_monotonic = monotonic_fn()
    now = now_fn(UTC)
    retention_days = get_settings().postmark_outbound_retention_days
    if retention_days is None:
        raise RuntimeError("POSTMARK_OUTBOUND_RETENTION_DAYS is required")
    provider_retention = timedelta(days=retention_days)
    counts = _new_delivery_reconciliation_counts()
    candidates, has_more = await _discover_delivery_reconciliation_candidates(
        db,
        org_id=org_id,
        now=now,
        batch_size=batch_size,
    )
    counts["has_more"] = has_more
    provider = email_client or get_email_client()
    for candidate in candidates:
        if monotonic_fn() - started_monotonic >= time_budget_seconds:
            counts["has_more"] = True
            break
        counts["processed"] += 1
        await _reconcile_delivery_candidate(
            db,
            org_id=org_id,
            candidate=candidate,
            provider=provider,
            provider_retention=provider_retention,
            now=now,
            now_fn=now_fn,
            reconciliation_lease_id=reconciliation_lease_id,
            counts=counts,
        )
    return cast(dict[str, int | bool], counts)


async def revoke_external_report_grant(
    db: AsyncSession,
    *,
    grant_id: uuid.UUID,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    now_fn=datetime.now,
) -> ExternalReportGrant:
    analysis = await get_analysis_for_org(db, analysis_id=analysis_id, org_id=org_id)
    result = await db.execute(
        select(ExternalReportGrant)
        .where(
            ExternalReportGrant.id == grant_id,
            ExternalReportGrant.analysis_id == analysis_id,
            ExternalReportGrant.org_id == org_id,
        )
        .with_for_update()
    )
    grant = result.scalar_one_or_none()
    if grant is None:
        raise APIError(404, "Not Found", "External report grant not found")
    now = now_fn(UTC)
    grant.revoked_at = grant.revoked_at or now
    if grant.delivery_state in {
        "prepared",
        "dispatching",
        "provider_accepted",
        "outcome_unknown",
    }:
        grant.delivery_state = "cancelled"
        grant.delivery_terminal_at = now
        grant.delivery_terminal_reason = "user_revoked"
    grant.delivery_token_ciphertext = None
    grant.verification_code_hash = None
    grant.access_secret_hash = None
    grant.access_expires_at = None
    await _refresh_analysis_share_state(db, analysis=analysis, now=now)
    return grant


async def _load_public_grant(
    session: AsyncSession,
    *,
    token: str,
    for_update: bool,
) -> ExternalReportGrant:
    validate_grant_token_shape(token)
    token_hash = _secret_digest(token)
    await bind_public_share_grant_hash_to_session(session, token_hash)
    statement = select(ExternalReportGrant).where(
        ExternalReportGrant.grant_token_hash == token_hash
    )
    if for_update:
        statement = statement.with_for_update()
    result = await session.execute(statement)
    grant = result.scalar_one_or_none()
    if grant is None or not compare_digest(grant.grant_token_hash, token_hash):
        raise APIError(404, "Not Found", "Shared report is unavailable")
    return grant


def _ensure_grant_active(grant: ExternalReportGrant, *, now: datetime) -> None:
    if (
        grant.delivery_state != "active"
        or grant.invitation_sent_at is None
        or grant.revoked_at is not None
        or _utc(grant.expires_at) <= now
    ):
        raise APIError(410, "Gone", "Shared report is unavailable")
    if grant.view_count >= grant.max_views:
        raise APIError(410, "Gone", "Shared report is unavailable")


async def issue_external_grant_challenge(
    token: str,
    *,
    async_session_factory_fn,
    email_client: PostmarkClient | None = None,
    now_fn=datetime.now,
) -> None:
    """Send a one-time code to the grant's bound mailbox."""
    recipient_email = ""
    code = ""
    issued_at: datetime | None = None
    async with async_session_factory_fn() as session:
        grant = await _load_public_grant(session, token=token, for_update=True)
        now = now_fn(UTC)
        _ensure_grant_active(grant, now=now)
        if grant.verification_sent_at is not None and (
            now - _utc(grant.verification_sent_at) < VERIFICATION_RESEND_COOLDOWN
        ):
            raise APIError(429, "Too Many Requests", "Wait before requesting another code")
        await bind_current_org_to_session(session, grant.org_id)
        code = f"{secrets.randbelow(10**VERIFICATION_CODE_DIGITS):0{VERIFICATION_CODE_DIGITS}d}"
        grant.verification_code_hash = hash_password(code)
        grant.verification_expires_at = now + VERIFICATION_TTL
        grant.verification_sent_at = now
        grant.verification_consumed_at = None
        grant.verification_attempt_count = 0
        grant.access_secret_hash = None
        grant.access_expires_at = None
        recipient_email = grant.recipient_email
        issued_at = now
        await session.commit()

    subject, html, text = _verification_message(code=code)
    try:
        await _send_or_fail(
            email_client=email_client or get_email_client(),
            recipient_email=recipient_email,
            subject=subject,
            html=html,
            text=text,
            tag="external-report-verification",
        )
    except Exception:
        # Compensate a provider rejection by invalidating the committed challenge.
        # If Postmark accepted the message but its response was lost, this
        # intentionally makes the sent code unusable rather than granting
        # access when the provider-acceptance state is ambiguous.
        async with async_session_factory_fn() as cleanup_session:
            cleanup_grant = await _load_public_grant(
                cleanup_session,
                token=token,
                for_update=True,
            )
            await bind_current_org_to_session(cleanup_session, cleanup_grant.org_id)
            if (
                cleanup_grant.verification_sent_at is not None
                and issued_at is not None
                and _utc(cleanup_grant.verification_sent_at) == issued_at
                and cleanup_grant.verification_consumed_at is None
            ):
                cleanup_grant.verification_code_hash = None
                cleanup_grant.verification_expires_at = None
                cleanup_grant.verification_sent_at = None
            await cleanup_session.commit()
        raise


async def verify_external_grant_challenge(
    token: str,
    *,
    code: str,
    async_session_factory_fn,
    now_fn=datetime.now,
) -> tuple[str, datetime]:
    """Consume a valid mailbox code and mint a short-lived access proof."""
    async with async_session_factory_fn() as session:
        grant = await _load_public_grant(session, token=token, for_update=True)
        now = now_fn(UTC)
        _ensure_grant_active(grant, now=now)
        await bind_current_org_to_session(session, grant.org_id)
        if (
            grant.verification_code_hash is None
            or grant.verification_expires_at is None
            or _utc(grant.verification_expires_at) <= now
            or grant.verification_consumed_at is not None
        ):
            raise APIError(401, "Unauthorized", "Verification code is invalid or expired")
        if grant.verification_attempt_count >= MAX_VERIFICATION_ATTEMPTS:
            raise APIError(429, "Too Many Requests", "Verification attempts exhausted")

        grant.verification_attempt_count += 1
        try:
            verified = verify_password(code, grant.verification_code_hash)
        except Exception:
            verified = False
        if not verified:
            await session.commit()
            raise APIError(401, "Unauthorized", "Verification code is invalid or expired")

        access_secret = secrets.token_urlsafe(32)
        access_expires_at = min(_utc(grant.expires_at), now + ACCESS_TTL)
        grant.access_secret_hash = _secret_digest(access_secret)
        grant.access_expires_at = access_expires_at
        grant.verification_consumed_at = now
        grant.verification_code_hash = None
        session.add(
            AuditLog(
                org_id=grant.org_id,
                user_id=None,
                analysis_id=grant.analysis_id,
                action="report.share.recipient_verified",
                details={
                    "external_grant_id": str(grant.id),
                    "recipient_email": grant.recipient_email,
                    "recipient_domain": grant.recipient_domain,
                },
                ip_address="",
            )
        )
        await session.commit()
        return access_secret, access_expires_at


async def fetch_authorized_shared_analysis(
    token: str,
    *,
    access_secret: str,
    async_session_factory_fn,
    ip_address: str,
    now_fn=datetime.now,
) -> Analysis:
    """Authorize, meter, and audit one recipient-attributable report view."""
    if not GRANT_TOKEN_MIN_LENGTH <= len(access_secret) <= GRANT_TOKEN_MAX_LENGTH:
        raise APIError(401, "Unauthorized", "Recipient verification is required")
    access_hash = _secret_digest(access_secret)
    async with async_session_factory_fn() as session:
        grant = await _load_public_grant(session, token=token, for_update=True)
        now = now_fn(UTC)
        _ensure_grant_active(grant, now=now)
        if (
            grant.access_secret_hash is None
            or grant.access_expires_at is None
            or _utc(grant.access_expires_at) <= now
            or not compare_digest(grant.access_secret_hash, access_hash)
        ):
            raise APIError(401, "Unauthorized", "Recipient verification is required")

        await bind_current_org_to_session(session, grant.org_id)
        result = await session.execute(
            select(Analysis).where(
                Analysis.id == grant.analysis_id,
                Analysis.org_id == grant.org_id,
            )
        )
        analysis = cast(Analysis | None, result.scalar_one_or_none())
        if analysis is None:
            raise APIError(410, "Gone", "Shared report is unavailable")
        review_status = await load_analysis_review_status(
            session,
            analysis_id=analysis.id,
            org_id=analysis.org_id,
        )
        reviewer_decisions = await load_export_reviewer_decisions(
            session,
            analysis_id=analysis.id,
            org_id=analysis.org_id,
        )
        report_data = require_completed_report_payload(
            analysis,
            status_code=410,
            title="Gone",
            detail="Shared report is unavailable",
        )
        if not compare_digest(
            grant.report_fingerprint,
            report_payload_fingerprint(report_data),
        ):
            raise APIError(410, "Gone", "Shared report is unavailable")
        blockers = build_export_readiness_blockers(
            report_data=report_data,
            review_status=review_status,
            reviewer_decisions=reviewer_decisions,
        )
        if blockers:
            raise APIError(410, "Gone", "Shared report is unavailable")

        grant.view_count += 1
        grant.last_accessed_at = now
        analysis.share_view_count += 1
        analysis.share_last_viewed_at = now
        analysis.__dict__["_share_expires_at"] = grant.expires_at
        analysis.__dict__["_share_recipient_email"] = grant.recipient_email
        analysis.__dict__["_share_view_number"] = grant.view_count
        analysis.__dict__["_share_access_expires_at"] = grant.access_expires_at
        analysis.__dict__["_share_id"] = str(grant.id)
        analysis.__dict__["_share_report_fingerprint"] = grant.report_fingerprint
        analysis.__dict__["_share_review_status"] = review_status
        session.add(
            AuditLog(
                org_id=grant.org_id,
                user_id=None,
                analysis_id=grant.analysis_id,
                action="report.share.viewed",
                details={
                    "external_grant_id": str(grant.id),
                    "recipient_email": grant.recipient_email,
                    "recipient_domain": grant.recipient_domain,
                    "recipient_verified": True,
                    "view_number": grant.view_count,
                    "download_allowed": False,
                },
                ip_address=ip_address[:45],
            )
        )
        await _refresh_analysis_share_state(session, analysis=analysis, now=now)
        await session.commit()
        return analysis
