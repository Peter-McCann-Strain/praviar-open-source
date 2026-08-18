"""Tenant offboarding and GDPR data erasure service.

Handles the full lifecycle of org deletion: scheduling, soft-delete of analyses,
cancellation of Stripe subscription, and final erasure marking.

All operations are audit-logged and require platform superadmin authority.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import structlog
from fastapi import Request
from sqlalchemy import case, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import write_audit_log
from api.config import get_settings
from api.db.models import AnalysisStatus, ExportJob, ExportStatus, ExternalReportGrant
from api.db.models_analysis import Analysis
from api.db.models_identity import Organization
from api.errors import APIError
from api.services.blocking_sdk import run_blocking_sdk_call

logger = structlog.get_logger()

_ERASURE_DELAY_DAYS = 30
_BILLING_CANCELLATION_PENDING = "billing_cancellation_pending"
_ARCHIVE_DELETION_PENDING = "archive_deletion_pending"
_BILLING_CANCELLATION_RETRY_SECONDS = 60
_BILLING_CANCELLATION_LEASE_SECONDS = 120
_BILLING_TERMINAL_STATUSES = frozenset({"confirmed", "not_required"})
_ARCHIVE_DELETION_RETRY_SECONDS = 60
_ARCHIVE_DELETION_TIMEOUT_SECONDS = 60.0
_ERASURE_IN_PROGRESS_STATUSES = (
    _BILLING_CANCELLATION_PENDING,
    _ARCHIVE_DELETION_PENDING,
)


@dataclass(frozen=True, slots=True)
class ClaimedUseErasureAuthorization:
    """Central, tenant/time/actor-bound authority passed to the DB boundary."""

    authorization_id: uuid.UUID
    request_id: uuid.UUID
    org_id: uuid.UUID
    actor_kind: Literal["platform_superadmin", "scheduled_system"]
    actor_user_id: uuid.UUID | None
    actor_email: str
    authorized_at: datetime
    capability_secret: str = ""


def authorize_platform_org_erasure(
    *,
    org_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    actor_email: str,
) -> ClaimedUseErasureAuthorization:
    """Create authority only for a centrally configured platform superadmin."""
    if actor_user_id not in set(get_settings().platform_admin_user_ids):
        raise APIError(403, "Forbidden", "Data erasure requires platform admin access")
    return ClaimedUseErasureAuthorization(
        authorization_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        org_id=org_id,
        actor_kind="platform_superadmin",
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        authorized_at=datetime.now(UTC),
        capability_secret=secrets.token_urlsafe(32),
    )


def authorize_scheduled_org_erasure(
    *,
    org_id: uuid.UUID,
) -> ClaimedUseErasureAuthorization:
    """Create narrowly scoped authority for the due-erasure scheduler."""
    return ClaimedUseErasureAuthorization(
        authorization_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        org_id=org_id,
        actor_kind="scheduled_system",
        actor_user_id=None,
        actor_email="system@praviar.internal",
        authorized_at=datetime.now(UTC),
        capability_secret=secrets.token_urlsafe(32),
    )


async def persist_claimed_use_erasure_authorization(
    db: AsyncSession,
    *,
    authorization: ClaimedUseErasureAuthorization,
) -> ClaimedUseErasureAuthorization:
    """Persist an independently issued, opaque, single-use erasure capability."""
    capability_sha256 = hashlib.sha256(authorization.capability_secret.encode("utf-8")).hexdigest()
    authorized_at = (
        await db.execute(
            text(
                "SELECT public.authorize_claimed_use_erasure("
                "CAST(:authorization_id AS uuid), "
                "CAST(:request_id AS uuid), "
                "CAST(:org_id AS uuid), "
                ":actor_kind, "
                "CAST(:actor_user_id AS uuid), "
                ":capability_sha256)"
            ),
            {
                "authorization_id": str(authorization.authorization_id),
                "request_id": str(authorization.request_id),
                "org_id": str(authorization.org_id),
                "actor_kind": authorization.actor_kind,
                "actor_user_id": (
                    str(authorization.actor_user_id)
                    if authorization.actor_user_id is not None
                    else None
                ),
                "capability_sha256": capability_sha256,
            },
        )
    ).scalar_one()
    await db.commit()
    return replace(authorization, authorized_at=authorized_at)


async def _consume_claimed_use_erasure_authorization(
    *,
    authorization: ClaimedUseErasureAuthorization,
) -> int:
    from api.db.claimed_use_privileged import claimed_use_privileged_session

    async with claimed_use_privileged_session(
        "erasure",
        org_id=authorization.org_id,
    ) as erasure_db:
        erased_receipt_count = (
            await erasure_db.execute(
                text(
                    "SELECT public.erase_claimed_use_receipts("
                    "CAST(:authorization_id AS uuid), "
                    "CAST(:request_id AS uuid), "
                    "CAST(:org_id AS uuid), "
                    "CAST(:actor_user_id AS uuid), "
                    ":capability_secret)"
                ),
                {
                    "authorization_id": str(authorization.authorization_id),
                    "request_id": str(authorization.request_id),
                    "org_id": str(authorization.org_id),
                    "actor_user_id": (
                        str(authorization.actor_user_id)
                        if authorization.actor_user_id is not None
                        else None
                    ),
                    "capability_secret": authorization.capability_secret,
                },
            )
        ).scalar_one()
        await erasure_db.commit()
        return int(erased_receipt_count)


def _validate_erasure_authorization(
    authorization: ClaimedUseErasureAuthorization,
    *,
    org_id: uuid.UUID,
) -> None:
    if authorization.org_id != org_id:
        raise APIError(403, "Forbidden", "Erasure authorization is bound to another tenant")
    authorized_at = authorization.authorized_at
    if authorized_at.tzinfo is None:
        raise APIError(403, "Forbidden", "Erasure authorization timestamp must be timezone-aware")
    age_seconds = (datetime.now(UTC) - authorized_at.astimezone(UTC)).total_seconds()
    if age_seconds < -30 or age_seconds > 300:
        raise APIError(403, "Forbidden", "Erasure authorization has expired")
    if authorization.actor_kind == "platform_superadmin":
        if authorization.actor_user_id is None or authorization.actor_user_id not in set(
            get_settings().platform_admin_user_ids
        ):
            raise APIError(
                403,
                "Forbidden",
                "Erasure authorization actor is not a platform superadmin",
            )
    elif authorization.actor_kind != "scheduled_system" or authorization.actor_user_id is not None:
        raise APIError(403, "Forbidden", "Erasure authorization actor is invalid")


class _StripeCancellationUnconfirmedError(RuntimeError):
    """Stripe returned without proving that recurring billing is cancelled."""


def _stripe_subscription_status(result: object) -> str | None:
    status = getattr(result, "status", None)
    if status is None and isinstance(result, Mapping):
        status = result.get("status")
    return status if isinstance(status, str) else None


def _stripe_cancellation_idempotency_key(
    *,
    org_id: uuid.UUID,
    subscription_id: str,
) -> str:
    subscription_digest = hashlib.sha256(subscription_id.encode("utf-8")).hexdigest()[:32]
    return f"org-erasure-{org_id}-{subscription_digest}"


def _billing_confirmation_covers_current_subscription(org: Organization) -> bool:
    status = org.offboarding_billing_cancellation_status
    current_subscription_id = org.stripe_subscription_id
    if status == "not_required":
        return current_subscription_id is None
    if status == "confirmed":
        return current_subscription_id in {
            None,
            org.offboarding_stripe_subscription_id,
        }
    return False


async def _ensure_offboarding_billing_cancelled(
    db: AsyncSession,
    *,
    org: Organization,
    org_id: uuid.UUID,
) -> None:
    """Durably cancel recurring billing before irreversible tenant erasure.

    The provider call sits between two commits. The first commit records an
    immutable subscription locator and retryable attempt before contacting
    Stripe. The second records confirmation. A timeout therefore leaves enough
    durable state to retry with the same Stripe idempotency key, without
    claiming erasure or losing the subscription locator.
    """
    now = datetime.now(UTC)
    status = org.offboarding_billing_cancellation_status
    if status in _BILLING_TERMINAL_STATUSES and (
        _billing_confirmation_covers_current_subscription(org)
    ):
        return
    if status == "pending" and org.offboarding_billing_last_attempt_at is not None:
        lease_started_at = org.offboarding_billing_last_attempt_at
        if lease_started_at.tzinfo is None:
            lease_started_at = lease_started_at.replace(tzinfo=UTC)
        lease_age_seconds = (now - lease_started_at).total_seconds()
        if lease_age_seconds < _BILLING_CANCELLATION_LEASE_SECONDS:
            retry_after = max(
                1,
                round(_BILLING_CANCELLATION_LEASE_SECONDS - lease_age_seconds),
            )
            raise APIError(
                503,
                "Billing cancellation in progress",
                "A Stripe cancellation attempt is already in progress. "
                "Organization data remains intact.",
                retry_after_seconds=retry_after,
            )

    # A new subscription can race an earlier confirmed/not-required boundary.
    # Start a fresh cancellation cycle for the current locator rather than
    # treating proof about the old state as proof about the replacement.
    if status in _BILLING_TERMINAL_STATUSES:
        org.offboarding_billing_cancellation_status = None
        org.offboarding_stripe_subscription_id = None
        org.offboarding_billing_confirmed_at = None
        org.offboarding_billing_last_error_code = None

    subscription_id = org.offboarding_stripe_subscription_id or org.stripe_subscription_id
    if status in {"pending", "retryable"} and subscription_id is None:
        raise APIError(
            500,
            "Billing cancellation state is invalid",
            "Organization erasure cannot continue because its durable Stripe "
            "subscription locator is missing.",
        )

    org.deletion_status = _BILLING_CANCELLATION_PENDING
    if subscription_id is None:
        org.offboarding_billing_cancellation_status = "not_required"
        org.offboarding_billing_confirmed_at = now
        org.offboarding_billing_last_error_code = None
        await db.commit()
        return

    org.offboarding_stripe_subscription_id = subscription_id
    org.offboarding_billing_cancellation_status = "pending"
    org.offboarding_billing_cancellation_attempts += 1
    org.offboarding_billing_last_attempt_at = now
    org.offboarding_billing_confirmed_at = None
    org.offboarding_billing_last_error_code = None
    await db.commit()

    try:
        import stripe

        from api.services.blocking_sdk import run_blocking_sdk_call

        cancellation: Any = await run_blocking_sdk_call(
            "stripe.subscription.cancel",
            stripe.Subscription.cancel,
            subscription_id,
            idempotency_key=_stripe_cancellation_idempotency_key(
                org_id=org_id,
                subscription_id=subscription_id,
            ),
        )
        cancellation_status = _stripe_subscription_status(cancellation)
        if cancellation_status != "canceled":
            raise _StripeCancellationUnconfirmedError(
                "Stripe did not return subscription status 'canceled'"
            )
    except Exception as exc:
        org.offboarding_billing_cancellation_status = "retryable"
        org.offboarding_billing_last_error_code = type(exc).__name__[:128]
        await db.commit()
        logger.error(
            "org_erasure_stripe_subscription_cancellation_pending",
            org_id=str(org_id),
            subscription_id=subscription_id,
            attempt=org.offboarding_billing_cancellation_attempts,
            error_code=org.offboarding_billing_last_error_code,
            exc_info=True,
        )
        raise APIError(
            503,
            "Billing cancellation pending",
            "Stripe has not confirmed subscription cancellation. Organization "
            "data remains intact and erasure will be retried.",
            retry_after_seconds=_BILLING_CANCELLATION_RETRY_SECONDS,
        ) from exc

    org.offboarding_billing_cancellation_status = "confirmed"
    org.offboarding_billing_confirmed_at = datetime.now(UTC)
    org.offboarding_billing_last_error_code = None
    await db.commit()
    logger.info(
        "org_erasure_stripe_subscription_cancelled",
        org_id=str(org_id),
        subscription_id=subscription_id,
        attempt=org.offboarding_billing_cancellation_attempts,
    )


def _delete_local_export_archives(
    *,
    export_root: Path,
    artifact_urls: list[str],
) -> int:
    """Delete only local export files contained by the configured export root."""
    resolved_root = export_root.resolve()
    deleted = 0
    for artifact_url in artifact_urls:
        if artifact_url.startswith("gs://"):
            raise RuntimeError(
                "GCS export artifacts exist but GCS archive deletion is not configured"
            )
        resolved_artifact = Path(artifact_url).resolve()
        if not resolved_artifact.is_relative_to(resolved_root):
            raise RuntimeError("Export artifact is outside the configured export directory")
        existed = resolved_artifact.exists()
        resolved_artifact.unlink(missing_ok=True)
        if existed:
            deleted += 1
    return deleted


async def _prepare_org_archive_deletion(
    db: AsyncSession,
    *,
    org: Organization,
    org_id: uuid.UUID,
    executed_by_user_id: uuid.UUID | None,
    executed_by_email: str,
    request: Request | None,
) -> None:
    """Fence tenant writers before deleting report archives.

    The durable status and terminal export state are committed before external
    storage is touched. Export workers additionally lock this organization
    immediately before upload, so either their upload completes first and is
    included in the prefix deletion, or they observe this fence and abort.
    """
    fenced_at = datetime.now(UTC)
    org.deletion_status = _ARCHIVE_DELETION_PENDING
    await db.execute(
        update(Analysis)
        .where(
            Analysis.org_id == org_id,
            Analysis.status.notin_(
                [AnalysisStatus.DELETED, AnalysisStatus.FAILED, AnalysisStatus.CANCELLED]
            ),
        )
        .values(
            status=AnalysisStatus.DELETED,
            pipeline_execution_id=None,
            pipeline_lease_expires_at=None,
        )
    )
    await db.execute(
        update(ExportJob)
        .where(ExportJob.org_id == org_id)
        .values(
            status=ExportStatus.FAILED,
            processing_execution_id=None,
            processing_lease_expires_at=None,
            error_message="Export cancelled during organization erasure",
        )
    )
    unresolved_delivery = ExternalReportGrant.delivery_state.in_(
        ("prepared", "dispatching", "provider_accepted", "outcome_unknown")
    )
    await db.execute(
        update(ExternalReportGrant)
        .where(ExternalReportGrant.org_id == org_id)
        .values(
            revoked_at=fenced_at,
            delivery_state=case(
                (unresolved_delivery, "cancelled"),
                else_=ExternalReportGrant.delivery_state,
            ),
            delivery_terminal_at=case(
                (unresolved_delivery, fenced_at),
                else_=ExternalReportGrant.delivery_terminal_at,
            ),
            delivery_terminal_reason=case(
                (unresolved_delivery, "user_revoked"),
                else_=ExternalReportGrant.delivery_terminal_reason,
            ),
        )
    )
    await db.execute(
        text("UPDATE api_keys SET revoked = true WHERE org_id = :org_id"),
        {"org_id": str(org_id)},
    )
    await write_audit_log(
        db,
        org_id=org_id,
        user_id=executed_by_user_id,
        analysis_id=None,
        action="org.archive_deletion_started",
        details={
            "executed_by": executed_by_email,
            "started_at": fenced_at.isoformat(),
            "archive_prefix": f"exports/{org_id}/",
        },
        request=request,
        fail_closed=True,
    )
    await db.commit()


async def _delete_and_verify_org_archives(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
) -> tuple[str, int]:
    """Delete the exact tenant archive boundary and return target plus count."""
    settings = get_settings()
    prefix = f"exports/{org_id}/"
    try:
        if settings.gcs_bucket_name:
            from api.services.object_storage import ObjectStorage

            storage = ObjectStorage(
                bucket=settings.gcs_bucket_name,
                project=settings.gcp_project_id or None,
            )
            deleted = await run_blocking_sdk_call(
                "gcs.org_exports.delete_prefix",
                storage.delete_prefix,
                prefix,
                timeout_seconds=_ARCHIVE_DELETION_TIMEOUT_SECONDS,
                max_attempts=1,
                logger_override=logger,
            )
            return f"gs://{settings.gcs_bucket_name}/{prefix}", deleted

        if settings.app_env == "prod":
            raise RuntimeError("GCS_BUCKET_NAME is required for production erasure")

        result = await db.execute(
            select(ExportJob.file_url).where(
                ExportJob.org_id == org_id,
                ExportJob.file_url.isnot(None),
            )
        )
        artifact_urls = [
            artifact_url
            for artifact_url in result.scalars().all()
            if isinstance(artifact_url, str) and artifact_url
        ]
        deleted = await run_blocking_sdk_call(
            "filesystem.org_exports.delete",
            _delete_local_export_archives,
            export_root=Path(settings.export_dir),
            artifact_urls=artifact_urls,
            timeout_seconds=_ARCHIVE_DELETION_TIMEOUT_SECONDS,
            max_attempts=1,
            logger_override=logger,
        )
        return str(Path(settings.export_dir).resolve()), deleted
    except Exception as exc:
        logger.error(
            "org_erasure_archive_deletion_pending",
            org_id=str(org_id),
            prefix=prefix,
            error_code=type(exc).__name__,
            exc_info=True,
        )
        raise APIError(
            503,
            "Report archive deletion pending",
            "Report archive deletion could not be verified. Organization erasure "
            "will be retried and no terminal erasure has been recorded.",
            retry_after_seconds=_ARCHIVE_DELETION_RETRY_SECONDS,
        ) from exc


async def get_org_offboarding_status(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
) -> dict:
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        raise APIError(404, "Not Found", "Organization not found")

    return {
        "org_id": org.id,
        "org_name": org.name,
        "deletion_status": org.deletion_status,
        "deletion_scheduled_at": org.deletion_scheduled_at,
        "deletion_requested_by": org.deletion_requested_by,
        "billing_cancellation_status": org.offboarding_billing_cancellation_status,
        "billing_cancellation_attempts": org.offboarding_billing_cancellation_attempts,
        "billing_cancellation_last_attempt_at": org.offboarding_billing_last_attempt_at,
        "billing_cancellation_confirmed_at": org.offboarding_billing_confirmed_at,
    }


async def schedule_org_deletion(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    requested_by_user_id: uuid.UUID,
    requested_by_email: str,
    request: Request | None = None,
    erasure_delay_days: int = _ERASURE_DELAY_DAYS,
) -> dict:
    """Schedule org deletion with a mandatory 30-day erasure delay.

    The delay gives customers a window to retrieve their data before it is
    permanently removed. The status moves pending → erasing → erased.
    """
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        raise APIError(404, "Not Found", "Organization not found")

    if org.deletion_status == "erased":
        raise APIError(409, "Conflict", "Organization data has already been erased")
    if org.offboarding_billing_cancellation_status in {
        "pending",
        "retryable",
        "confirmed",
    }:
        raise APIError(
            409,
            "Conflict",
            "Organization deletion can no longer be rescheduled because billing "
            "cancellation has started.",
        )

    now = datetime.now(UTC)
    scheduled_at = now + timedelta(days=erasure_delay_days)

    org.deletion_scheduled_at = scheduled_at
    org.deletion_requested_by = requested_by_email
    org.deletion_status = "pending"

    await write_audit_log(
        db,
        org_id=org_id,
        user_id=requested_by_user_id,
        analysis_id=None,
        action="org.deletion_scheduled",
        details={
            "requested_by": requested_by_email,
            "scheduled_erasure_at": scheduled_at.isoformat(),
            "erasure_delay_days": erasure_delay_days,
        },
        request=request,
        fail_closed=True,
    )

    await db.commit()
    logger.warning(
        "org_deletion_scheduled",
        org_id=str(org_id),
        org_name=org.name,
        scheduled_at=scheduled_at.isoformat(),
        requested_by=requested_by_email,
    )

    return {
        "org_id": org_id,
        "deletion_status": "pending",
        "deletion_scheduled_at": scheduled_at,
        "message": (
            f"Organization data will be erased on {scheduled_at.date().isoformat()}. "
            f"This is a {erasure_delay_days}-day grace period — cancel via "
            "DELETE /admin/organizations/{org_id}/offboard before that date."
        ),
    }


async def cancel_org_deletion(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    cancelled_by_user_id: uuid.UUID,
    cancelled_by_email: str,
    request: Request | None = None,
) -> dict:
    """Cancel a pending org deletion during the grace period."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        raise APIError(404, "Not Found", "Organization not found")

    if org.deletion_status != "pending":
        raise APIError(
            409,
            "Conflict",
            f"Cannot cancel deletion: current status is '{org.deletion_status}'",
        )

    org.deletion_scheduled_at = None
    org.deletion_requested_by = None
    org.deletion_status = None

    await write_audit_log(
        db,
        org_id=org_id,
        user_id=cancelled_by_user_id,
        analysis_id=None,
        action="org.deletion_cancelled",
        details={"cancelled_by": cancelled_by_email},
        request=request,
        fail_closed=True,
    )

    await db.commit()
    logger.info(
        "org_deletion_cancelled",
        org_id=str(org_id),
        cancelled_by=cancelled_by_email,
    )
    return {"org_id": org_id, "deletion_status": None, "message": "Deletion cancelled"}


async def execute_org_erasure(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    executed_by_user_id: uuid.UUID | None = None,
    executed_by_email: str = "",
    authorization: ClaimedUseErasureAuthorization | None = None,
    use_database_boundary: bool = False,
    request: Request | None = None,
) -> dict:
    """Execute immediate erasure of all org data (platform superadmin only).

    Cancels recurring billing, fences tenant writers, deletes and verifies
    report archives, clears PII fields, and only then marks the org erased.
    """
    settings = get_settings()
    if authorization is not None:
        _validate_erasure_authorization(authorization, org_id=org_id)
        executed_by_user_id = authorization.actor_user_id
        executed_by_email = authorization.actor_email
    elif settings.app_env == "prod":
        raise RuntimeError("production erasure requires a central ClaimedUseErasureAuthorization")
    if executed_by_user_id is None and authorization is None:
        raise ValueError("executed_by_user_id is required without central authorization")
    if settings.app_env == "prod" and not use_database_boundary:
        raise RuntimeError("production erasure requires the dedicated erasure database boundary")
    result = await db.execute(
        select(Organization).where(Organization.id == org_id).with_for_update()
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise APIError(404, "Not Found", "Organization not found")

    if org.deletion_status == "erased":
        raise APIError(409, "Conflict", "Organization data has already been erased")
    if authorization is not None and authorization.actor_kind == "scheduled_system":
        scheduled_at = org.deletion_scheduled_at
        if (
            org.deletion_status not in {"pending", *_ERASURE_IN_PROGRESS_STATUSES}
            or scheduled_at is None
            or scheduled_at > datetime.now(UTC)
        ):
            raise APIError(403, "Forbidden", "Scheduled erasure is not due")

    await _ensure_offboarding_billing_cancelled(
        db,
        org=org,
        org_id=org_id,
    )

    # The billing boundary commits around the provider call, releasing the
    # original row lock. Re-acquire it and re-check terminal state before
    # starting the one-transaction local erasure.
    result = await db.execute(
        select(Organization).where(Organization.id == org_id).with_for_update()
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise APIError(404, "Not Found", "Organization not found")
    if org.deletion_status == "erased":
        raise APIError(409, "Conflict", "Organization data has already been erased")
    if org.offboarding_billing_cancellation_status not in _BILLING_TERMINAL_STATUSES:
        raise APIError(
            503,
            "Billing cancellation pending",
            "Stripe has not confirmed subscription cancellation. Organization "
            "data remains intact and erasure will be retried.",
            retry_after_seconds=_BILLING_CANCELLATION_RETRY_SECONDS,
        )
    if not _billing_confirmation_covers_current_subscription(org):
        replacement_subscription_id = org.stripe_subscription_id
        org.offboarding_billing_cancellation_status = None
        org.offboarding_stripe_subscription_id = None
        org.offboarding_billing_confirmed_at = None
        org.offboarding_billing_last_error_code = None
        await db.commit()
        logger.error(
            "org_erasure_replacement_subscription_detected",
            org_id=str(org_id),
            subscription_id=replacement_subscription_id,
        )
        raise APIError(
            503,
            "Billing cancellation pending",
            "A new Stripe subscription appeared during cancellation. Organization "
            "data remains intact and the replacement subscription will be cancelled "
            "on retry.",
            retry_after_seconds=_BILLING_CANCELLATION_RETRY_SECONDS,
        )

    # Rebind the session's RLS context to the target org so the UPDATE below
    # actually reaches the target org's analyses (not the caller's).  The
    # caller is a platform superadmin whose own org_id is set in the session;
    # without this rebind the UPDATE matches zero rows and erasure silently
    # no-ops under FORCE ROW LEVEL SECURITY.
    await db.execute(select(func.set_config("app.current_org_id", str(org_id), True)))

    await _prepare_org_archive_deletion(
        db,
        org=org,
        org_id=org_id,
        executed_by_user_id=executed_by_user_id,
        executed_by_email=executed_by_email,
        request=request,
    )
    archive_target, archive_deleted_count = await _delete_and_verify_org_archives(
        db,
        org_id=org_id,
    )

    # The archive fence and provider call commit/release the original lock.
    # Re-lock before local erasure and re-check the billing boundary so a
    # replacement subscription cannot appear while archives are being removed.
    result = await db.execute(
        select(Organization).where(Organization.id == org_id).with_for_update()
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise APIError(404, "Not Found", "Organization not found")
    if org.deletion_status == "erased":
        raise APIError(409, "Conflict", "Organization data has already been erased")
    if not _billing_confirmation_covers_current_subscription(org):
        replacement_subscription_id = org.stripe_subscription_id
        org.deletion_status = _BILLING_CANCELLATION_PENDING
        org.offboarding_billing_cancellation_status = None
        org.offboarding_stripe_subscription_id = None
        org.offboarding_billing_confirmed_at = None
        org.offboarding_billing_last_error_code = None
        await db.commit()
        logger.error(
            "org_erasure_replacement_subscription_detected_after_archive_deletion",
            org_id=str(org_id),
            subscription_id=replacement_subscription_id,
        )
        raise APIError(
            503,
            "Billing cancellation pending",
            "A new Stripe subscription appeared during archive deletion. "
            "It will be cancelled before erasure continues.",
            retry_after_seconds=_BILLING_CANCELLATION_RETRY_SECONDS,
        )
    await db.execute(select(func.set_config("app.current_org_id", str(org_id), True)))
    await write_audit_log(
        db,
        org_id=org_id,
        user_id=executed_by_user_id,
        analysis_id=None,
        action="org.report_archives_deleted",
        details={
            "executed_by": executed_by_email,
            "archive_target": archive_target,
            "deleted_object_count": archive_deleted_count,
            "verified_empty": True,
            "verified_at": datetime.now(UTC).isoformat(),
        },
        request=request,
        fail_closed=True,
    )

    # Claimed-use receipts are an append-only legal ledger during ordinary
    # runtime. The production procedure atomically appends a tenant/actor/time
    # authorization and performs the sole permitted DELETE. The API and worker
    # roles have neither table DML nor EXECUTE on that procedure.
    if use_database_boundary:
        if authorization is None:
            raise RuntimeError("database erasure requires central authorization")
        if settings.app_env == "prod":
            erased_receipt_count = await _consume_claimed_use_erasure_authorization(
                authorization=authorization,
            )
        else:
            erased_receipt_count = (
                await db.execute(
                    text(
                        "SELECT public.erase_claimed_use_receipts("
                        "CAST(:authorization_id AS uuid), "
                        "CAST(:request_id AS uuid), "
                        "CAST(:org_id AS uuid), "
                        "CAST(:actor_user_id AS uuid), "
                        ":capability_secret)"
                    ),
                    {
                        "authorization_id": str(authorization.authorization_id),
                        "request_id": str(authorization.request_id),
                        "org_id": str(org_id),
                        "actor_user_id": (
                            str(authorization.actor_user_id)
                            if authorization.actor_user_id is not None
                            else None
                        ),
                        "capability_secret": authorization.capability_secret,
                    },
                )
            ).scalar_one()
    else:
        # Non-production tests and local development do not provision the
        # dedicated database identities. Production is rejected above.
        await db.execute(
            text("DELETE FROM analysis_claimed_use_receipts WHERE org_id = :org_id"),
            {"org_id": str(org_id)},
        )
        erased_receipt_count = None
    await write_audit_log(
        db,
        org_id=org_id,
        user_id=executed_by_user_id,
        analysis_id=None,
        action="org.claimed_use_receipts_erasure_authorized",
        details={
            "executed_by": executed_by_email,
            "authorized_at": (
                authorization.authorized_at.isoformat()
                if authorization is not None
                else datetime.now(UTC).isoformat()
            ),
            "authorization_id": (
                str(authorization.authorization_id) if authorization is not None else None
            ),
            "request_id": (str(authorization.request_id) if authorization is not None else None),
            "actor_kind": (authorization.actor_kind if authorization is not None else "local_test"),
            "receipt_count": erased_receipt_count,
        },
        request=request,
        fail_closed=True,
    )

    # Soft-delete all non-terminal analyses and clear their pipeline leases so
    # an in-flight worker that was already past the lease-check cannot commit
    # a COMPLETED write that resurrected the erased row (BUG: success-path had
    # no terminal-status guard before the completion write).
    await db.execute(
        update(Analysis)
        .where(
            Analysis.org_id == org_id,
            Analysis.status.notin_(
                [AnalysisStatus.DELETED, AnalysisStatus.FAILED, AnalysisStatus.CANCELLED]
            ),
        )
        .values(
            status=AnalysisStatus.DELETED,
            pipeline_execution_id=None,
            pipeline_lease_expires_at=None,
        )
    )
    erasure_time = datetime.now(UTC)
    unresolved_delivery = ExternalReportGrant.delivery_state.in_(
        ("prepared", "dispatching", "provider_accepted", "outcome_unknown")
    )
    await db.execute(
        update(ExternalReportGrant)
        .where(ExternalReportGrant.org_id == org_id)
        .values(
            recipient_email="[ERASED]@invalid.example",
            recipient_email_normalized="[ERASED]@invalid.example",
            recipient_domain="invalid.example",
            verification_code_hash=None,
            access_secret_hash=None,
            revoked_at=erasure_time,
            delivery_state=case(
                (unresolved_delivery, "cancelled"),
                else_=ExternalReportGrant.delivery_state,
            ),
            delivery_terminal_at=case(
                (unresolved_delivery, erasure_time),
                else_=ExternalReportGrant.delivery_terminal_at,
            ),
            delivery_terminal_reason=case(
                (unresolved_delivery, "user_revoked"),
                else_=ExternalReportGrant.delivery_terminal_reason,
            ),
            delivery_token_ciphertext=None,
        )
    )

    # Redact PII from all analysis records (GDPR Art. 17).  compound_cid is the
    # PubChem CID of the analysed molecule: a public, exact identifier of the
    # FTO subject (the customer's most sensitive business secret), so it must be
    # cleared alongside the name/SMILES — otherwise the precise compound remains
    # resolvable from the retained row after erasure.
    await db.execute(
        update(Analysis)
        .where(Analysis.org_id == org_id)
        .values(
            compound_input="[ERASED]",
            input_type="name",
            submitted_identity_confirmed=False,
            submitted_identity_value=None,
            compound_name="[ERASED]",
            compound_smiles="",
            compound_cid=None,
            report_data=None,
            executive_summary="",
            share_active_grant_count=0,
            share_active_until=None,
        )
    )

    # Remove the exact organization-to-compound association. The globally
    # deduplicated public chemistry identity may remain for other organizations,
    # but the erased organization's subject choices and usage metadata must not.
    await db.execute(
        text("DELETE FROM organization_compounds WHERE org_id = :org_id"),
        {"org_id": str(org_id)},
    )
    # Remove digest recipient snapshots and capability digests. The organization
    # row is retained as a redacted tombstone, so FK CASCADE alone will not run.
    await db.execute(
        text("DELETE FROM weekly_digest_deliveries WHERE org_id = :org_id"),
        {"org_id": str(org_id)},
    )

    # Redact reviewer PII snapshots stored as denormalised columns on
    # collaboration tables.  These rows are NOT cascade-deleted when the
    # parent analysis is soft-deleted, so they must be redacted explicitly.
    # note/edited_text are user free-text (decision rationale, rewritten finding).
    await db.execute(
        text(
            "UPDATE analysis_reviewer_decisions"
            " SET reviewer_email = '', reviewer_name = '', note = '', edited_text = ''"
            " WHERE org_id = :org_id"
        ),
        {"org_id": str(org_id)},
    )
    await db.execute(
        text(
            "UPDATE analysis_review_statuses"
            " SET reviewer_email = '', reviewer_name = '', note = ''"
            " WHERE org_id = :org_id"
        ),
        {"org_id": str(org_id)},
    )
    # Redact checkpoint decision notes — user free-text (reject rationale, ≤4000 chars).
    await db.execute(
        text("UPDATE analysis_checkpoint_decisions SET note = '[ERASED]' WHERE org_id = :org_id"),
        {"org_id": str(org_id)},
    )
    # Redact attorney feedback corrections JSONB and risk override — user
    # free-text (notes, original/corrected values) that does not cascade on
    # analysis soft-delete.
    await db.execute(
        text(
            "UPDATE attorney_feedback"
            " SET corrections = '[]'::jsonb, corrected_risk = NULL"
            " WHERE org_id = :org_id"
        ),
        {"org_id": str(org_id)},
    )
    # Relevance labels preserve exact matter-specific patent and query choices.
    # Delete this derived calibration corpus when the organization is erased.
    await db.execute(
        text("DELETE FROM analysis_search_relevance_feedback WHERE org_id = :org_id"),
        {"org_id": str(org_id)},
    )

    # Redact comment bodies and mention email arrays — body is free-text from
    # users (names, context, chemical detail) and mentions is an ARRAY of
    # email addresses populated directly from user input.
    await db.execute(
        text(
            "UPDATE comments SET body = '[ERASED]', mentions = '{}'::text[] WHERE org_id = :org_id"
        ),
        {"org_id": str(org_id)},
    )
    # Redact notification PII: title and body embed assigner names; data JSONB
    # can hold assigned_by_name and other personal context fields.
    await db.execute(
        text(
            "UPDATE notifications"
            " SET title = '[ERASED]', body = '', data = '{}'::jsonb"
            " WHERE org_id = :org_id"
        ),
        {"org_id": str(org_id)},
    )
    # Redact durable Report Credit request snapshots and administrator notes.
    # Organization erasure retains the org row, so the FK cascade never runs.
    await db.execute(
        text(
            "UPDATE credit_capacity_requests"
            " SET requester_name = '[ERASED]',"
            " resolution_note = CASE"
            " WHEN status = 'declined' THEN '[ERASED]'"
            " ELSE NULL END"
            " WHERE org_id = :org_id"
        ),
        {"org_id": str(org_id)},
    )

    # Redact monitors: compound structures and patent-landscape results are as
    # confidential as the analysis data cleared above; monitors have no
    # ondelete cascade (org row is only marked erased, never deleted).
    await db.execute(
        text(
            "UPDATE monitors SET compound_name = '[ERASED]', compound_smiles = '',"
            " last_run_summary = '', last_snapshot = '{}'::jsonb,"
            " monitoring_strategy = '{}'::jsonb, watch_targets = '[]'::jsonb,"
            " cached_patent_ids = '[]'::jsonb, is_active = false"
            " WHERE org_id = :org_id"
        ),
        {"org_id": str(org_id)},
    )
    # Redact monitor_alerts: derivative FTO data (summary, new patent IDs,
    # jurisdiction deltas) tied to the erased org; cascade does not fire
    # because the parent monitors rows are retained above.
    await db.execute(
        text(
            "UPDATE monitor_alerts SET summary = '', new_patent_ids = '[]'::jsonb,"
            " new_event_ids = '[]'::jsonb, jurisdiction_deltas = '{}'::jsonb"
            " WHERE org_id = :org_id"
        ),
        {"org_id": str(org_id)},
    )
    # Remove faithfulness telemetry rows (claim_sentence, evidence_span are
    # verbatim report text); cascade does not fire on analysis soft-delete.
    await db.execute(
        text("DELETE FROM faithfulness_scores WHERE org_id = :org_id"),
        {"org_id": str(org_id)},
    )

    # Redact pipeline event payloads — the compound name (primary FTO subject)
    # is written into payload on every step.  pipeline_events has no org_id
    # column so the join through analyses is required; analyses is RLS-forced,
    # so the subquery is already scoped to the target org under the rebind.
    await db.execute(
        text(
            "UPDATE pipeline_events SET payload = '{}'::jsonb"
            " WHERE analysis_id IN (SELECT id FROM analyses WHERE org_id = :org_id)"
        ),
        {"org_id": str(org_id)},
    )

    # Revoke all outstanding API keys so that credentials cannot authenticate
    # after erasure.  api_keys.revoked=true is the sole gate checked by
    # authenticate_api_key; the org deletion_status is not checked on the
    # request path.
    await db.execute(
        text("UPDATE api_keys SET revoked = true WHERE org_id = :org_id"),
        {"org_id": str(org_id)},
    )

    # Redact config preset names and batch analysis names — user-supplied
    # free-text that persists under the org after analyses are soft-deleted.
    await db.execute(
        text(
            "UPDATE config_presets"
            " SET name = '[ERASED]', description = '', config = '{}'::jsonb"
            " WHERE org_id = :org_id"
        ),
        {"org_id": str(org_id)},
    )
    await db.execute(
        text("UPDATE batch_analyses SET name = '[ERASED]' WHERE org_id = :org_id"),
        {"org_id": str(org_id)},
    )

    # Redact PII from all user records — anonymise email so the row can be
    # kept for foreign-key integrity while satisfying erasure requirements.
    await db.execute(
        text(
            "UPDATE users"
            " SET email = CONCAT('[erased-', id::text, ']@erased.invalid'),"
            "     full_name = '[ERASED]'"
            " WHERE org_id = :org_id"
        ),
        {"org_id": str(org_id)},
    )
    # Clear PII fields from org record
    org.deletion_status = "erased"
    org.name = f"[ERASED-{org_id}]"
    org.slug = f"erased-{org_id}"
    org.stripe_customer_id = None
    org.stripe_subscription_id = None
    org.offboarding_stripe_subscription_id = None

    await write_audit_log(
        db,
        org_id=org_id,
        user_id=executed_by_user_id,
        analysis_id=None,
        action="org.data_erased",
        details={
            "executed_by": executed_by_email,
            "erased_at": datetime.now(UTC).isoformat(),
        },
        request=request,
        fail_closed=True,
    )

    await db.commit()
    logger.warning(
        "org_data_erased",
        org_id=str(org_id),
        executed_by=executed_by_email,
    )
    return {
        "org_id": org_id,
        "deletion_status": "erased",
        "message": "Organization data and report archives have been erased.",
    }


async def process_pending_erasures_async() -> dict:
    """Sweep due or retryable org erasures and erase them.

    Called by the /internal/run-pending-erasures Cloud Scheduler endpoint.
    Each org is processed in its own session so one failure does not block the rest.
    """
    from api.db.session import async_session_factory

    settings = get_settings()
    use_database_boundary = settings.app_env == "prod"
    session_context = async_session_factory

    now = datetime.now(UTC)
    async with session_context() as db:
        result = await db.execute(
            select(Organization).where(
                Organization.deletion_status.in_(("pending", *_ERASURE_IN_PROGRESS_STATUSES)),
                Organization.deletion_scheduled_at.isnot(None),
                Organization.deletion_scheduled_at <= now,
            )
        )
        pending_orgs = result.scalars().all()

    erased: list[str] = []
    errors: list[dict] = []
    for org in pending_orgs:
        try:
            async with session_context() as db:
                # Re-acquire a row lock and re-check deletion_status. A cancel
                # issued after the snapshot above would set deletion_status=None;
                # without this guard, erasure would proceed on a cancelled org.
                recheck = await db.execute(
                    select(Organization)
                    .where(
                        Organization.id == org.id,
                        Organization.deletion_status.in_(
                            ("pending", *_ERASURE_IN_PROGRESS_STATUSES)
                        ),
                    )
                    .with_for_update()
                )
                if recheck.scalar_one_or_none() is None:
                    logger.info(
                        "pending_erasure_skipped_not_pending",
                        org_id=str(org.id),
                    )
                    continue
                authorization = (
                    authorize_scheduled_org_erasure(org_id=org.id)
                    if use_database_boundary
                    else None
                )
                if authorization is not None:
                    authorization = await persist_claimed_use_erasure_authorization(
                        db,
                        authorization=authorization,
                    )
                await execute_org_erasure(
                    db,
                    org_id=org.id,
                    authorization=authorization,
                    use_database_boundary=use_database_boundary,
                    executed_by_user_id=(None if use_database_boundary else uuid.UUID(int=0)),
                    executed_by_email=("" if use_database_boundary else "system@praviar.internal"),
                )
            erased.append(str(org.id))
        except APIError as exc:
            if exc.status == 409:
                erased.append(str(org.id))
            else:
                errors.append({"org_id": str(org.id), "error": exc.detail})
                logger.error("pending_erasure_failed", org_id=str(org.id), error=exc.detail)
        except Exception as exc:
            errors.append({"org_id": str(org.id), "error": str(exc)})
            logger.error(
                "pending_erasure_unexpected_error",
                org_id=str(org.id),
                error=str(exc),
                exc_info=True,
            )

    logger.info(
        "pending_erasures_processed",
        erased_count=len(erased),
        error_count=len(errors),
    )
    return {
        "erased_count": len(erased),
        "error_count": len(errors),
        "erased_org_ids": erased,
        "errors": errors,
    }
