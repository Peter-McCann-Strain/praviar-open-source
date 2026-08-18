"""Durable state transitions for retry-safe weekly digest delivery."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.models import User, WeeklyDigestDelivery
from api.external_report_delivery_keyring import ExternalReportDeliveryKeyRing
from api.services.email_models import DeliveryLookupResult, DeliverySubmissionResult
from api.services.notification_unsubscribe import (
    DigestUnsubscribeCapability,
    create_digest_unsubscribe_capability,
)

_SUBMISSION_CONTEXT = b"praviar:weekly-digest-submission:v1"
_INITIAL_RECONCILIATION_DELAY = timedelta(minutes=2)
_RECONCILIATION_BACKOFF = (
    timedelta(minutes=2),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
    timedelta(hours=6),
    timedelta(days=1),
)
_RECONCILIATION_ALERT_ATTEMPTS = 6


@dataclass(frozen=True)
class WeeklyDigestDispatchClaim:
    """Committed provider-attempt identity and its transient raw capability."""

    delivery_id: uuid.UUID
    submission_id: str
    unsubscribe_token: str


def _operation_key() -> bytes:
    keyring = ExternalReportDeliveryKeyRing.from_secret(
        get_settings().external_report_delivery_keyring_secret.get_secret_value()
    )
    return hmac.new(
        keyring.operation_hmac_key,
        _SUBMISSION_CONTEXT,
        hashlib.sha256,
    ).digest()


def weekly_digest_submission_id(
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    window_start: datetime,
) -> str:
    """Return a mailbox-free deterministic identity for one user/window."""
    if window_start.tzinfo is None:
        raise ValueError("weekly digest window_start must be timezone-aware")
    message = (
        f"{org_id}\x00{user_id}\x00{window_start.astimezone(UTC).isoformat(timespec='seconds')}"
    ).encode()
    return hmac.new(_operation_key(), message, hashlib.sha256).hexdigest()


def lock_weekly_digest_delivery(
    db: Session,
    *,
    delivery_id: uuid.UUID,
    org_id: uuid.UUID,
) -> WeeklyDigestDelivery | None:
    """Lock one tenant-scoped delivery row for a state transition."""
    return db.execute(
        select(WeeklyDigestDelivery)
        .where(
            WeeklyDigestDelivery.id == delivery_id,
            WeeklyDigestDelivery.org_id == org_id,
        )
        .with_for_update()
    ).scalar_one_or_none()


def get_or_create_weekly_digest_delivery(
    db: Session,
    *,
    user: User,
    period_start: datetime,
    period_end: datetime,
) -> WeeklyDigestDelivery:
    """Return the single durable delivery identity for this user and period.

    The caller holds a lock on ``user`` before invoking this function. That
    serializes concurrent sweeps for the same recipient without holding any
    database lock across provider network I/O.
    """
    if period_start.tzinfo is None or period_end.tzinfo is None:
        raise ValueError("weekly digest period must be timezone-aware")
    if period_end != period_start + timedelta(days=7):
        raise ValueError("weekly digest period must span exactly seven days")

    existing = db.execute(
        select(WeeklyDigestDelivery)
        .where(
            WeeklyDigestDelivery.org_id == user.org_id,
            WeeklyDigestDelivery.user_id == user.id,
            WeeklyDigestDelivery.period_start == period_start,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if existing is not None:
        if existing.period_end != period_end:
            raise RuntimeError("weekly digest period identity has conflicting bounds")
        return existing

    delivery = WeeklyDigestDelivery(
        org_id=user.org_id,
        user_id=user.id,
        period_start=period_start,
        period_end=period_end,
        state="prepared",
        submission_id=weekly_digest_submission_id(
            user_id=user.id,
            org_id=user.org_id,
            window_start=period_start,
        ),
    )
    db.add(delivery)
    db.flush()
    return delivery


def claim_weekly_digest_dispatch(
    delivery: WeeklyDigestDelivery,
    *,
    recipient_email: str,
    now: datetime,
) -> WeeklyDigestDispatchClaim | None:
    """Cross the durable at-most-once boundary before any provider HTTP call."""
    if delivery.state != "prepared":
        return None
    if now.tzinfo is None:
        raise ValueError("weekly digest dispatch time must be timezone-aware")
    capability: DigestUnsubscribeCapability = create_digest_unsubscribe_capability(now=now)
    delivery.state = "dispatching"
    delivery.recipient_email = recipient_email
    delivery.unsubscribe_token_digest = capability.token_digest
    delivery.unsubscribe_expires_at = capability.expires_at
    delivery.provider_attempt_started_at = now
    delivery.reconciliation_next_attempt_at = now + _INITIAL_RECONCILIATION_DELAY
    delivery.last_error_code = None
    return WeeklyDigestDispatchClaim(
        delivery_id=delivery.id,
        submission_id=delivery.submission_id,
        unsubscribe_token=capability.token,
    )


def cancel_weekly_digest_before_submission(
    delivery: WeeklyDigestDelivery,
    *,
    now: datetime,
    reason: str,
) -> None:
    """Cancel a claimed delivery after a final preference/membership recheck."""
    if delivery.state != "dispatching":
        return
    delivery.state = "cancelled"
    delivery.terminal_at = now
    delivery.last_error_code = reason[:64]
    delivery.recipient_email = None
    delivery.unsubscribe_token_digest = None
    delivery.unsubscribe_expires_at = None
    delivery.reconciliation_next_attempt_at = None


def record_weekly_digest_submission(
    delivery: WeeklyDigestDelivery,
    *,
    result: DeliverySubmissionResult,
    now: datetime,
) -> None:
    """Persist the one and only provider POST outcome."""
    if delivery.state != "dispatching":
        raise RuntimeError("weekly digest provider result arrived for a non-dispatching row")
    if result.status == "accepted":
        if not result.message_id:
            raise RuntimeError("accepted weekly digest submission is missing a message id")
        delivery.state = "provider_accepted"
        delivery.provider_message_id = result.message_id
        delivery.provider_accepted_at = now
        delivery.recipient_email = None
        delivery.reconciliation_next_attempt_at = None
        delivery.last_error_code = None
        return
    if result.status == "rejected":
        delivery.state = "rejected"
        delivery.terminal_at = now
        delivery.recipient_email = None
        delivery.unsubscribe_token_digest = None
        delivery.unsubscribe_expires_at = None
        delivery.reconciliation_next_attempt_at = None
        delivery.last_error_code = "provider_rejected"
        return

    # A timeout, connection failure, malformed success, or provider 5xx may
    # have reached Postmark. Never POST this submission again.
    delivery.state = "outcome_unknown"
    delivery.last_error_code = "provider_outcome_unknown"
    delivery.reconciliation_next_attempt_at = now + _INITIAL_RECONCILIATION_DELAY


def record_weekly_digest_submission_exception(
    delivery: WeeklyDigestDelivery,
    *,
    now: datetime,
) -> None:
    """Classify an unexpected transport exception as permanently ambiguous."""
    record_weekly_digest_submission(
        delivery,
        result=DeliverySubmissionResult(
            status="outcome_unknown",
            error="provider submission raised unexpectedly",
        ),
        now=now,
    )


def _next_reconciliation_at(*, now: datetime, attempt_count: int) -> datetime:
    index = min(max(attempt_count - 1, 0), len(_RECONCILIATION_BACKOFF) - 1)
    return now + _RECONCILIATION_BACKOFF[index]


def record_weekly_digest_reconciliation(
    delivery: WeeklyDigestDelivery,
    *,
    result: DeliveryLookupResult,
    now: datetime,
) -> None:
    """Apply an exact broadcasts-stream lookup without ever resubmitting."""
    if delivery.state not in {"dispatching", "outcome_unknown"}:
        return
    delivery.reconciliation_attempt_count += 1
    if result.status == "found":
        if not result.message_id:
            raise RuntimeError("found weekly digest lookup is missing a message id")
        delivery.state = "provider_accepted"
        delivery.provider_message_id = result.message_id
        delivery.provider_accepted_at = now
        delivery.recipient_email = None
        delivery.reconciliation_next_attempt_at = None
        delivery.last_error_code = None
        return

    delivery.state = "outcome_unknown"
    delivery.last_error_code = f"reconcile_{result.status}"[:64]
    delivery.reconciliation_next_attempt_at = _next_reconciliation_at(
        now=now,
        attempt_count=delivery.reconciliation_attempt_count,
    )
    if (
        delivery.reconciliation_attempt_count >= _RECONCILIATION_ALERT_ATTEMPTS
        and delivery.reconciliation_alerted_at is None
    ):
        delivery.reconciliation_alerted_at = now
