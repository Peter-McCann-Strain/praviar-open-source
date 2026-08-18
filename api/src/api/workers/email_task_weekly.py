"""Weekly digest orchestration with a durable at-most-once delivery ledger."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from api.db.session import bind_org_to_sync_session
from api.services.email_models import DeliveryLookupResult
from api.services.risk_access import risk_ratings_restricted_for_role
from api.services.weekly_digest_delivery import (
    cancel_weekly_digest_before_submission,
    claim_weekly_digest_dispatch,
    get_or_create_weekly_digest_delivery,
    lock_weekly_digest_delivery,
    record_weekly_digest_reconciliation,
    record_weekly_digest_submission,
    record_weekly_digest_submission_exception,
)
from api.workers.celery_app import run_async
from api.workers.email_task_digest import build_top_risks_payload, weekly_digest_enabled
from api.workers.email_task_payloads import build_weekly_digest_send_kwargs, weekly_digest_cutoff
from api.workers.email_task_runtime import get_sync_engine, send_email_async

logger = structlog.get_logger()

DIGEST_RECONCILIATION_RETRY_AFTER_SECONDS = 120
_RECONCILIATION_BATCH_SIZE = 500
_UNRESOLVED_STATES = ("dispatching", "outcome_unknown")


def _weekly_digest_recipient_eligible(user) -> bool:
    """Return whether the current membership may receive organization activity."""
    return bool(
        getattr(user, "membership_active", False)
        and getattr(user, "membership_deleted_at", None) is None
        and getattr(user, "membership_permission_denied_at", None) is None
    )


def _lock_digest_user(db: Session, *, user_id, org_id):
    """Refetch current membership, role, mailbox, and preferences under a lock."""
    from api.db.models import User

    return db.execute(
        select(User)
        .where(
            User.id == user_id,
            User.org_id == org_id,
        )
        .with_for_update()
    ).scalar_one_or_none()


def _aggregate_user_activity(
    db: Session,
    *,
    period_start: datetime,
    period_end: datetime,
    org_ids: set[Any],
) -> dict[Any, dict[str, Any]]:
    """Aggregate tenant activity inside one closed-open weekly period."""
    from api.db.models import Analysis, AnalysisStatus, Monitor, MonitorAlert

    aggregated: dict[Any, dict[str, Any]] = {}
    for org_id in org_ids:
        if not org_id:
            continue
        bind_org_to_sync_session(db, org_id)

        completed_filter = (
            (Analysis.org_id == org_id)
            & (Analysis.status == AnalysisStatus.COMPLETED)
            & (Analysis.completed_at >= period_start)
            & (Analysis.completed_at < period_end)
        )

        analyses_count = (
            db.execute(select(func.count(Analysis.id)).where(completed_filter)).scalar_one_or_none()
            or 0
        )

        alerts_count = (
            db.execute(
                select(func.count(MonitorAlert.id))
                .join(Monitor, MonitorAlert.monitor_id == Monitor.id)
                .where(
                    MonitorAlert.org_id == org_id,
                    MonitorAlert.created_at >= period_start,
                    MonitorAlert.created_at < period_end,
                )
            ).scalar_one_or_none()
            or 0
        )

        risk_priority = case(
            (Analysis.overall_risk == "HIGH", 0),
            (Analysis.overall_risk == "MEDIUM", 1),
            (Analysis.overall_risk == "LOW", 2),
            (Analysis.overall_risk == "MINIMAL", 3),
            else_=4,
        )
        top_risks = (
            db.execute(
                select(Analysis)
                .where(completed_filter, Analysis.overall_risk.isnot(None))
                .order_by(risk_priority, Analysis.completed_at.desc())
                .limit(5)
            )
            .scalars()
            .all()
        )

        aggregated[org_id] = {
            "analyses_count": int(analyses_count),
            "alerts_count": int(alerts_count),
            "top_risks": list(top_risks),
        }
        db.commit()
    return aggregated


def _lookup_weekly_digest(*, submission_id: str, recipient_email: str):
    async def _lookup(client):
        return await client.lookup_weekly_digest_submission(
            submission_id=submission_id,
            expected_to=recipient_email,
        )

    return run_async(send_email_async(_lookup))


def _submit_weekly_digest(*, payload: dict[str, Any]):
    async def _send(client):
        return await client.submit_weekly_digest_once(**payload)

    return run_async(send_email_async(_send))


def _reconcile_due_deliveries(
    db: Session,
    *,
    org_ids: list[Any],
    now: datetime,
) -> dict[str, int]:
    """Reconcile ambiguous provider attempts without issuing another POST."""
    from api.db.models import WeeklyDigestDelivery

    recovered = 0
    pending = 0
    errors = 0

    for org_id in org_ids:
        bind_org_to_sync_session(db, org_id)
        due = list(
            db.execute(
                select(
                    WeeklyDigestDelivery.id,
                    WeeklyDigestDelivery.submission_id,
                    WeeklyDigestDelivery.recipient_email,
                )
                .where(
                    WeeklyDigestDelivery.org_id == org_id,
                    WeeklyDigestDelivery.state.in_(_UNRESOLVED_STATES),
                    or_(
                        WeeklyDigestDelivery.reconciliation_next_attempt_at.is_(None),
                        WeeklyDigestDelivery.reconciliation_next_attempt_at <= now,
                    ),
                )
                .order_by(
                    WeeklyDigestDelivery.reconciliation_next_attempt_at.asc().nullsfirst(),
                    WeeklyDigestDelivery.created_at,
                )
                .limit(_RECONCILIATION_BATCH_SIZE)
            ).all()
        )
        db.commit()

        for delivery_id, submission_id, recipient_email in due:
            if not recipient_email:
                lookup = DeliveryLookupResult(
                    status="alert",
                    detail="durable recipient identity is missing",
                )
            else:
                try:
                    lookup = _lookup_weekly_digest(
                        submission_id=submission_id,
                        recipient_email=recipient_email,
                    )
                except Exception:
                    logger.error(
                        "weekly_digest_reconciliation_lookup_failed",
                        delivery_id=str(delivery_id),
                        org_id=str(org_id),
                        exc_info=True,
                    )
                    lookup = DeliveryLookupResult(
                        status="unavailable",
                        detail="provider lookup raised unexpectedly",
                    )

            bind_org_to_sync_session(db, org_id)
            delivery = lock_weekly_digest_delivery(
                db,
                delivery_id=delivery_id,
                org_id=org_id,
            )
            if delivery is None or delivery.state not in _UNRESOLVED_STATES:
                db.commit()
                continue
            record_weekly_digest_reconciliation(
                delivery,
                result=lookup,
                now=datetime.now(UTC),
            )
            db.commit()

            if lookup.status == "found":
                recovered += 1
                logger.info(
                    "weekly_digest_reconciliation_recovered",
                    delivery_id=str(delivery_id),
                    org_id=str(org_id),
                    provider_message_id=lookup.message_id,
                )
            else:
                pending += 1
                if lookup.status in {"alert", "unavailable"}:
                    errors += 1
                logger.warning(
                    "weekly_digest_reconciliation_pending",
                    delivery_id=str(delivery_id),
                    org_id=str(org_id),
                    lookup_status=lookup.status,
                    detail=lookup.detail,
                )

    return {"recovered": recovered, "pending": pending, "errors": errors}


def _count_unresolved_deliveries(db: Session, *, org_ids: list[Any]) -> int:
    """Count unresolved rows explicitly per tenant for retry signaling."""
    from api.db.models import WeeklyDigestDelivery

    total = 0
    for org_id in org_ids:
        bind_org_to_sync_session(db, org_id)
        total += int(
            db.execute(
                select(func.count(WeeklyDigestDelivery.id)).where(
                    WeeklyDigestDelivery.org_id == org_id,
                    WeeklyDigestDelivery.state.in_(_UNRESOLVED_STATES),
                )
            ).scalar_one()
        )
        db.commit()
    return total


def _process_digest_recipient(
    db: Session,
    *,
    listed_user,
    period_start: datetime,
    period_end: datetime,
    analyses_count: int,
    alerts_count: int,
    top_risks: list[dict[str, str]],
) -> str:
    """Process one recipient independently and return a structured outcome."""
    bind_org_to_sync_session(db, listed_user.org_id)
    user = _lock_digest_user(
        db,
        user_id=listed_user.id,
        org_id=listed_user.org_id,
    )
    if user is None or not _weekly_digest_recipient_eligible(user):
        db.commit()
        return "skipped"
    if not weekly_digest_enabled(user.preferences):
        db.commit()
        return "skipped"

    delivery = get_or_create_weekly_digest_delivery(
        db,
        user=user,
        period_start=period_start,
        period_end=period_end,
    )
    if delivery.state == "provider_accepted":
        db.commit()
        return "already_sent"
    if delivery.state in _UNRESOLVED_STATES:
        db.commit()
        return "pending"
    if delivery.state in {"rejected", "cancelled"}:
        db.commit()
        return "terminal"

    dispatch_now = datetime.now(UTC)
    claim = claim_weekly_digest_dispatch(
        delivery,
        recipient_email=user.email,
        now=dispatch_now,
    )
    if claim is None:
        db.commit()
        return "pending"
    # This commit is the at-most-once boundary. If the worker dies afterwards,
    # reconciliation may recover a provider acceptance but no retry may POST
    # the same delivery again.
    db.commit()

    # Final authority recheck after the durable boundary, immediately before
    # provider I/O. A concurrent unsubscribe, membership revocation, deletion,
    # permission denial, or mailbox replacement cancels the unsent attempt.
    bind_org_to_sync_session(db, listed_user.org_id)
    user = _lock_digest_user(
        db,
        user_id=listed_user.id,
        org_id=listed_user.org_id,
    )
    locked_delivery = lock_weekly_digest_delivery(
        db,
        delivery_id=claim.delivery_id,
        org_id=listed_user.org_id,
    )
    if locked_delivery is None:
        db.rollback()
        return "error"
    if (
        user is None
        or not _weekly_digest_recipient_eligible(user)
        or not weekly_digest_enabled(user.preferences)
        or user.email.casefold() != (locked_delivery.recipient_email or "").casefold()
    ):
        cancel_weekly_digest_before_submission(
            locked_delivery,
            now=datetime.now(UTC),
            reason="recipient_authority_changed",
        )
        db.commit()
        return "skipped"
    if locked_delivery.state != "dispatching":
        db.commit()
        return "pending"

    risk_restricted = risk_ratings_restricted_for_role(getattr(user, "role", None))
    payload = build_weekly_digest_send_kwargs(
        user=user,
        analyses_completed=analyses_count,
        alerts_count=alerts_count,
        top_risks=top_risks,
        unsubscribe_token=claim.unsubscribe_token,
        risk_restricted=risk_restricted,
    )
    payload["submission_id"] = claim.submission_id
    db.commit()

    try:
        submission = _submit_weekly_digest(payload=payload)
    except Exception:
        logger.error(
            "weekly_digest_submission_raised",
            delivery_id=str(claim.delivery_id),
            org_id=str(listed_user.org_id),
            exc_info=True,
        )
        bind_org_to_sync_session(db, listed_user.org_id)
        locked_delivery = lock_weekly_digest_delivery(
            db,
            delivery_id=claim.delivery_id,
            org_id=listed_user.org_id,
        )
        if locked_delivery is not None and locked_delivery.state == "dispatching":
            record_weekly_digest_submission_exception(
                locked_delivery,
                now=datetime.now(UTC),
            )
            db.commit()
        else:
            db.rollback()
        return "pending"

    bind_org_to_sync_session(db, listed_user.org_id)
    locked_delivery = lock_weekly_digest_delivery(
        db,
        delivery_id=claim.delivery_id,
        org_id=listed_user.org_id,
    )
    if locked_delivery is None:
        db.rollback()
        return "error"
    # A concurrent reconciliation cannot run until the initial two-minute due
    # time, so dispatching remains authoritative for this immediate result.
    record_weekly_digest_submission(
        locked_delivery,
        result=submission,
        now=datetime.now(UTC),
    )
    db.commit()
    if submission.status == "accepted":
        return "sent"
    if submission.status == "rejected":
        return "terminal"
    return "pending"


def send_weekly_digest_task(task) -> dict:  # noqa: ARG001
    """Send the fixed prior-week digest and reconcile older ambiguous sends."""
    logger.info("weekly_digest_starting")
    engine = get_sync_engine()
    sent_count = 0
    terminal_error_count = 0
    skipped_count = 0
    skipped_already_sent = 0
    recipient_pending = 0

    try:
        with Session(engine) as db:
            from api.db.models import Organization, User

            period_start = weekly_digest_cutoff()
            period_end = period_start + timedelta(days=7)
            org_ids = list(db.execute(select(Organization.id).order_by(Organization.id)).scalars())
            db.commit()

            reconciliation = _reconcile_due_deliveries(
                db,
                org_ids=org_ids,
                now=datetime.now(UTC),
            )

            users = list(
                db.execute(
                    select(User)
                    .where(
                        User.membership_active.is_(True),
                        User.membership_deleted_at.is_(None),
                        User.membership_permission_denied_at.is_(None),
                    )
                    .order_by(User.created_at)
                ).scalars()
            )
            db.commit()
            active_org_ids = {u.org_id for u in users if getattr(u, "org_id", None)}
            aggregated = _aggregate_user_activity(
                db,
                period_start=period_start,
                period_end=period_end,
                org_ids=active_org_ids,
            )

            for listed_user in users:
                org_activity = aggregated.get(listed_user.org_id, {})
                analyses_count = int(org_activity.get("analyses_count", 0) or 0)
                alerts_count = int(org_activity.get("alerts_count", 0) or 0)
                if analyses_count == 0 and alerts_count == 0:
                    skipped_count += 1
                    continue
                top_risks = build_top_risks_payload(org_activity.get("top_risks", []))

                try:
                    outcome = _process_digest_recipient(
                        db,
                        listed_user=listed_user,
                        period_start=period_start,
                        period_end=period_end,
                        analyses_count=analyses_count,
                        alerts_count=alerts_count,
                        top_risks=top_risks,
                    )
                except Exception:
                    db.rollback()
                    terminal_error_count += 1
                    logger.error(
                        "weekly_digest_recipient_failed",
                        user_id=str(listed_user.id),
                        org_id=str(listed_user.org_id),
                        exc_info=True,
                    )
                    continue

                if outcome == "sent":
                    sent_count += 1
                elif outcome == "already_sent":
                    skipped_already_sent += 1
                elif outcome == "pending":
                    recipient_pending += 1
                elif outcome in {"terminal", "error"}:
                    terminal_error_count += 1
                else:
                    skipped_count += 1

            unresolved = _count_unresolved_deliveries(db, org_ids=org_ids)

        result = {
            "sent": sent_count,
            "reconciled": reconciliation["recovered"],
            "errors": terminal_error_count + reconciliation["errors"],
            "skipped": skipped_count,
            "skipped_already_sent": skipped_already_sent,
            "pending": unresolved,
        }
        logger.info("weekly_digest_completed", **result)
        if unresolved or recipient_pending:
            return {
                "status": "retry_later",
                "reason": "digest_delivery_reconciliation_pending",
                "retry_after_seconds": DIGEST_RECONCILIATION_RETRY_AFTER_SECONDS,
                **result,
            }
        return {"status": "completed", **result}
    except Exception as exc:
        logger.error("weekly_digest_failed", error=str(exc), exc_info=True)
        return {"status": "failed", "error": str(exc)}
