"""Internal routes — invoked by Cloud Tasks via OIDC token, not by end users.

The /internal/run-pipeline endpoint is the target for the Cloud Tasks queue:
Cloud Tasks signs HTTP requests with an OIDC token whose service account
(`praviar-tasks-invoker`) has `roles/run.invoker` on the workers Cloud Run
service. This module validates the OIDC token and triggers a pipeline run.

Per 10-gcp-architecture.md §5 wk3 + §11.

Security model:
    - Cloud Run workers service has ingress=INTERNAL_ONLY (set by Terraform).
    - Only authenticated callers with `roles/run.invoker` reach this endpoint.
    - We further validate the OIDC `aud` claim matches the workers service URL
      to defend against confused-deputy.
    - We validate the OIDC issuer is Google.
    - Authenticated tasks dispatcher SA is logged for audit.
"""

from __future__ import annotations

from datetime import datetime
from importlib import import_module
from typing import Any
from uuid import UUID

import jwt
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from api.config import get_settings
from api.db.claimed_use_privileged import claimed_use_privileged_session
from api.db.models import Analysis, User, UserRole
from api.db.session import bind_current_org_to_session
from api.deps import DBSession
from api.errors import APIError
from api.schemas.claimed_use_receipts import ClaimedUseReceiptIssueRequest
from api.services.claimed_use_receipts import (
    issue_claimed_use_receipt,
    list_claimed_use_receipts,
    revoke_claimed_use_receipt,
)
from api.services.offboarding import (
    ClaimedUseErasureAuthorization,
    execute_org_erasure,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


class PipelineRunRequest(BaseModel):
    """Body posted by Cloud Tasks dispatcher."""

    analysis_id: UUID
    org_id: UUID
    params: dict[str, Any] = Field(default_factory=dict)


class ExportRunRequest(BaseModel):
    """Body posted by Cloud Tasks dispatcher for export rendering."""

    export_job_id: str
    org_id: str


class FaithfulnessRunRequest(BaseModel):
    """Body posted by Cloud Tasks dispatcher for shadow faithfulness scoring."""

    analysis_id: str
    org_id: str


class MonitorScanRunRequest(BaseModel):
    """Body posted by Cloud Tasks dispatcher for monitor scans."""

    monitor_id: str
    org_id: str
    force_full_refresh: bool = False


class MonitorAlertEmailRunRequest(BaseModel):
    """Body posted by Cloud Tasks dispatcher for monitor alert emails."""

    user_id: str
    monitor_id: str
    alert_id: str
    org_id: str


class WeeklyDigestRunRequest(BaseModel):
    """Body posted by Cloud Tasks dispatcher for weekly digest sweeps."""

    dedupe_key: str | None = None


class WorkerReleaseCanaryRequest(BaseModel):
    """Digest-bound no-op used only to prove the candidate worker data plane."""

    release_sha: str = Field(pattern=r"^[0-9a-f]{40}$")


class ExternalReportDeliveryReconciliationRequest(BaseModel):
    """Body posted by one tenant-scoped reconciliation Cloud Task."""

    org_id: UUID
    dedupe_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    continuation: int = Field(default=0, ge=0, le=10000)


class ExternalReportDeliverySweepRequest(BaseModel):
    """Durable cursor carried by a bounded reconciliation continuation task."""

    cursor: UUID
    sweep_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class ClaimedUseLedgerActorRequest(BaseModel):
    analysis_id: UUID
    actor_user_id: UUID
    org_id: UUID


class ClaimedUseLedgerIssueRequest(ClaimedUseLedgerActorRequest):
    body: ClaimedUseReceiptIssueRequest


class ClaimedUseLedgerRevokeRequest(ClaimedUseLedgerActorRequest):
    receipt_id: UUID
    reason: str = Field(min_length=10, max_length=2000)


class ClaimedUseLedgerEraseRequest(BaseModel):
    authorization_id: UUID
    request_id: UUID
    org_id: UUID
    actor_user_id: UUID
    authorized_at: datetime
    capability_secret: str = Field(min_length=32, max_length=256)


WORKER_FAILURE_STATUSES = frozenset({"failed", "blocked", "retry_later"})
WORKER_TERMINAL_STATUSES = frozenset({"blocked"})


def _worker_failure_detail(result: Any) -> str | None:
    """Return a worker failure detail when Cloud Tasks should retry the delivery.

    Returns None for terminal (non-retryable) statuses so the route returns 202
    and Cloud Tasks stops retrying.
    """
    if not isinstance(result, dict):
        return None
    status_value = result.get("status")
    if status_value in WORKER_TERMINAL_STATUSES:
        return None
    if status_value in WORKER_FAILURE_STATUSES or "error" in result:
        return str(
            result.get("error")
            or result.get("reason")
            or result.get("message")
            or status_value
            or "worker_failed"
        )
    return None


def _raise_for_failed_worker_result(
    result: Any,
    *,
    worker_name: str,
    resource_id: str,
) -> None:
    detail = _worker_failure_detail(result)
    if detail is None:
        return
    raise RuntimeError(f"{worker_name} failed for {resource_id}: {detail}")


async def _verify_oidc_token(
    request: Request,
    *,
    expected_caller_email: str,
) -> str:
    """Verify the OIDC bearer token signed by Cloud Tasks.

    Returns the verified service account email of the caller. Raises 401 if
    the token is missing, invalid, or not from an authorized issuer.

    This is a thin wrapper around google-auth's id_token verification.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing OIDC bearer token",
        )

    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty OIDC bearer token",
        )
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC token header is invalid",
        ) from exc
    if header.get("alg") != "RS256":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unexpected OIDC token algorithm",
        )

    settings = get_settings()
    configured_audience = str(settings.workers_service_url or "").strip()
    if not configured_audience:
        logger.error("internal.oidc_audience_unset")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OIDC audience is not configured",
        )
    expected_audience = configured_audience

    # google.auth is only required when running on Cloud Run; import_module is
    # hoisted to module level so tests can patch api.routes.internal.import_module.
    try:
        id_token_module = import_module("google.oauth2.id_token")
        requests_module = import_module("google.auth.transport.requests")

        request_obj = requests_module.Request()
        claims = id_token_module.verify_oauth2_token(
            token,
            request_obj,
            audience=expected_audience,
        )
    except Exception as exc:
        logger.warning("internal.oidc_verify_failed", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC token verification failed",
        ) from exc

    issuer = claims.get("iss", "")
    if issuer not in ("https://accounts.google.com", "accounts.google.com"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Unexpected OIDC issuer: {issuer}",
        )
    audience_claim = claims.get("aud")
    if isinstance(audience_claim, list):
        audience_matches = expected_audience in audience_claim
    else:
        audience_matches = audience_claim == expected_audience
    if not audience_matches:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unexpected OIDC audience",
        )
    if claims.get("email_verified") is not True:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC caller email is not verified",
        )

    caller_email = claims.get("email", "")
    if not caller_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC token missing email claim",
        )
    expected_email = expected_caller_email
    if not expected_email:
        if settings.app_env == "prod":
            logger.error("internal.oidc_caller_unset_prod")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OIDC caller is not configured",
            )
        logger.warning("internal.oidc_caller_unset_non_prod")
    elif caller_email != expected_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unexpected OIDC caller",
        )

    return str(caller_email)


async def verify_oidc_token(request: Request) -> str:
    """Verify the dedicated Cloud Tasks invoker identity."""
    return await _verify_oidc_token(
        request,
        expected_caller_email=get_settings().tasks_invoker_sa_email,
    )


async def verify_ledger_oidc_token(request: Request) -> str:
    """Verify the public API workload identity for ledger-only operations."""
    return await _verify_oidc_token(
        request,
        expected_caller_email=get_settings().ledger_invoker_sa_email,
    )


@router.post("/release-canary", status_code=status.HTTP_200_OK)
async def worker_release_canary(
    body: WorkerReleaseCanaryRequest,
    request: Request,
    caller_email: str = Depends(verify_oidc_token),
) -> dict[str, Any]:
    """Prove an authenticated request reached the exact candidate worker."""
    settings = get_settings()
    if settings.service_role != "worker":
        raise APIError(404, "Not Found", "Worker release canary is worker-only")
    if body.release_sha != settings.release_version:
        raise APIError(
            409,
            "Conflict",
            "Worker release identity does not match the canary request",
        )
    cloud_task_name = request.headers.get("X-CloudTasks-TaskName", "").strip()
    if not cloud_task_name:
        raise APIError(
            400,
            "Bad Request",
            "Worker release canary requires a Cloud Tasks delivery identity",
        )
    logger.info(
        "worker_release_canary_passed",
        caller=caller_email,
        cloud_task_name=cloud_task_name,
        release_sha=body.release_sha,
    )
    return {
        "accepted": True,
        "cloud_task_name": cloud_task_name,
        "release_sha": settings.release_version,
    }


async def _load_ledger_actor(
    db: DBSession,
    *,
    actor_user_id: UUID,
    org_id: UUID,
) -> User:
    if get_settings().service_role != "worker":
        raise APIError(404, "Not Found", "Ledger endpoint is worker-only")
    await db.execute(select(func.set_config("app.current_org_id", str(org_id), True)))
    actor = (
        await db.execute(
            select(User).where(
                User.id == actor_user_id,
                User.org_id == org_id,
                User.membership_active.is_(True),
                User.membership_deleted_at.is_(None),
                User.membership_permission_denied_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if actor is None:
        raise APIError(403, "Forbidden", "Ledger actor is not an active tenant member")
    return actor


@router.post("/claimed-use/list")
async def claimed_use_ledger_list(
    body: ClaimedUseLedgerActorRequest,
    db: DBSession,
    _caller: str = Depends(verify_ledger_oidc_token),
) -> dict[str, Any]:
    actor = await _load_ledger_actor(
        db,
        actor_user_id=body.actor_user_id,
        org_id=body.org_id,
    )
    if actor.role not in {UserRole.ADMIN, UserRole.ATTORNEY}:
        raise APIError(403, "Forbidden", "Ledger actor cannot view counsel receipts")
    response = await list_claimed_use_receipts(
        db,
        analysis_id=body.analysis_id,
        user=actor,
    )
    return response.model_dump(mode="json")


@router.post("/claimed-use/issue", status_code=status.HTTP_201_CREATED)
async def claimed_use_ledger_issue(
    body: ClaimedUseLedgerIssueRequest,
    db: DBSession,
    _caller: str = Depends(verify_ledger_oidc_token),
) -> dict[str, Any]:
    actor = await _load_ledger_actor(
        db,
        actor_user_id=body.actor_user_id,
        org_id=body.org_id,
    )
    if actor.role != UserRole.ATTORNEY:
        raise APIError(403, "Forbidden", "Ledger actor cannot issue counsel receipts")
    async with claimed_use_privileged_session(
        "writer",
        org_id=body.org_id,
    ) as writer_db:
        response = await issue_claimed_use_receipt(
            writer_db,
            analysis_id=body.analysis_id,
            user=actor,
            body=body.body,
            use_database_boundary=True,
        )
    return response.model_dump(mode="json")


@router.post("/claimed-use/revoke")
async def claimed_use_ledger_revoke(
    body: ClaimedUseLedgerRevokeRequest,
    db: DBSession,
    _caller: str = Depends(verify_ledger_oidc_token),
) -> dict[str, Any]:
    actor = await _load_ledger_actor(
        db,
        actor_user_id=body.actor_user_id,
        org_id=body.org_id,
    )
    if actor.role not in {UserRole.ADMIN, UserRole.ATTORNEY}:
        raise APIError(403, "Forbidden", "Ledger actor cannot revoke counsel receipts")
    async with claimed_use_privileged_session(
        "writer",
        org_id=body.org_id,
    ) as writer_db:
        response = await revoke_claimed_use_receipt(
            writer_db,
            analysis_id=body.analysis_id,
            receipt_id=body.receipt_id,
            user=actor,
            reason=body.reason,
            use_database_boundary=True,
        )
    return response.model_dump(mode="json")


@router.post("/claimed-use/erase-org")
async def claimed_use_ledger_erase_org(
    body: ClaimedUseLedgerEraseRequest,
    db: DBSession,
    _caller: str = Depends(verify_ledger_oidc_token),
) -> dict[str, Any]:
    actor = await _load_ledger_actor(
        db,
        actor_user_id=body.actor_user_id,
        org_id=body.org_id,
    )
    if actor.role != UserRole.ADMIN:
        raise APIError(403, "Forbidden", "Ledger actor cannot execute org erasure")
    authorization = ClaimedUseErasureAuthorization(
        authorization_id=body.authorization_id,
        request_id=body.request_id,
        org_id=body.org_id,
        actor_kind="platform_superadmin",
        actor_user_id=actor.id,
        actor_email=actor.email,
        authorized_at=body.authorized_at,
        capability_secret=body.capability_secret,
    )
    return await execute_org_erasure(
        db,
        org_id=body.org_id,
        authorization=authorization,
        use_database_boundary=True,
    )


def _execute_export_background(*, export_job_id: str, org_id: str) -> Any:
    """Run an export job for the current Cloud Tasks delivery."""
    try:
        tasks_module = import_module("api.workers.tasks")
        result = tasks_module.execute_export_job(
            export_job_id=export_job_id,
            org_id=org_id,
        )
        _raise_for_failed_worker_result(
            result,
            worker_name="Export worker",
            resource_id=export_job_id,
        )
    except Exception as exc:
        logger.error(
            "internal.run_export.execution_failed",
            export_job_id=export_job_id,
            error=str(exc),
            exc_info=True,
        )
        raise
    logger.info(
        "internal.run_export.execution_completed",
        export_job_id=export_job_id,
        result=result,
    )
    return result


def _execute_faithfulness_background(*, analysis_id: str, org_id: str) -> Any:
    """Run shadow faithfulness scoring for the current Cloud Tasks delivery."""
    try:
        tasks_module = import_module("api.workers.tasks")
        result = tasks_module.execute_faithfulness_scores(
            analysis_id=analysis_id,
            org_id=org_id,
        )
        _raise_for_failed_worker_result(
            result,
            worker_name="Faithfulness worker",
            resource_id=analysis_id,
        )
    except Exception as exc:
        logger.error(
            "internal.run_faithfulness.execution_failed",
            analysis_id=analysis_id,
            error=str(exc),
            exc_info=True,
        )
        raise
    logger.info(
        "internal.run_faithfulness.execution_completed",
        analysis_id=analysis_id,
        result=result,
    )
    return result


def _execute_monitor_scan_background(
    *,
    monitor_id: str,
    org_id: str,
    force_full_refresh: bool,
) -> Any:
    """Run one monitor scan for the current Cloud Tasks delivery."""
    try:
        monitor_tasks_module = import_module("api.workers.monitor_tasks")
        result = monitor_tasks_module.execute_monitor_scan(
            monitor_id=monitor_id,
            org_id=org_id,
            force_full_refresh=force_full_refresh,
        )
        _raise_for_failed_worker_result(
            result,
            worker_name="Monitor scan worker",
            resource_id=monitor_id,
        )
    except Exception as exc:
        logger.error(
            "internal.run_monitor_scan.execution_failed",
            monitor_id=monitor_id,
            org_id=org_id,
            force_full_refresh=force_full_refresh,
            error=str(exc),
            exc_info=True,
        )
        raise
    logger.info(
        "internal.run_monitor_scan.execution_completed",
        monitor_id=monitor_id,
        org_id=org_id,
        force_full_refresh=force_full_refresh,
        result=result,
    )
    return result


def _execute_monitor_alert_email_background(
    *,
    user_id: str,
    monitor_id: str,
    alert_id: str,
    org_id: str,
) -> Any:
    """Send one monitor alert email for the current Cloud Tasks delivery."""
    try:
        email_tasks_module = import_module("api.workers.email_tasks")
        result = email_tasks_module.execute_monitor_alert_email(
            user_id=user_id,
            monitor_id=monitor_id,
            alert_id=alert_id,
            org_id=org_id,
        )
        _raise_for_failed_worker_result(
            result,
            worker_name="Monitor alert email worker",
            resource_id=alert_id,
        )
    except Exception as exc:
        logger.error(
            "internal.run_monitor_alert_email.execution_failed",
            user_id=user_id,
            monitor_id=monitor_id,
            alert_id=alert_id,
            org_id=org_id,
            error=str(exc),
            exc_info=True,
        )
        raise
    logger.info(
        "internal.run_monitor_alert_email.execution_completed",
        user_id=user_id,
        monitor_id=monitor_id,
        alert_id=alert_id,
        org_id=org_id,
        result=result,
    )
    return result


def _execute_weekly_digest_background(*, dedupe_key: str | None = None) -> Any:
    """Run the weekly digest sweep for the current Cloud Tasks delivery."""
    try:
        email_tasks_module = import_module("api.workers.email_tasks")
        result = email_tasks_module.execute_weekly_digest()
        _raise_for_failed_worker_result(
            result,
            worker_name="Weekly digest worker",
            resource_id=dedupe_key or "weekly-digest",
        )
    except Exception as exc:
        logger.error(
            "internal.run_weekly_digest.execution_failed",
            dedupe_key=dedupe_key,
            error=str(exc),
            exc_info=True,
        )
        raise
    logger.info(
        "internal.run_weekly_digest.execution_completed",
        dedupe_key=dedupe_key,
        result=result,
    )
    return result


@router.post("/run-pipeline", status_code=status.HTTP_202_ACCEPTED)
async def run_pipeline(
    body: PipelineRunRequest,
    db: DBSession,
    caller_email: str = Depends(verify_oidc_token),
) -> dict[str, Any]:
    """Persist and launch one durable Cloud Run Job pipeline execution.

    This endpoint is invoked by Cloud Tasks dispatched via
    `api.services.task_dispatcher.CloudTasksDispatcher`. It performs only the
    short control-plane handoff. The Job data plane must present the persisted
    execution ID before it can claim the analysis row.
    """
    from api.services.pipeline_job_launcher import build_pipeline_job_launcher
    from api.services.pipeline_launch import reserve_pipeline_job_execution

    logger.info(
        "internal.run_pipeline.received",
        analysis_id=str(body.analysis_id),
        caller=caller_email,
    )

    await bind_current_org_to_session(db, body.org_id)
    result = await db.execute(
        select(Analysis)
        .where(
            Analysis.id == body.analysis_id,
            Analysis.org_id == body.org_id,
        )
        .with_for_update()
    )
    analysis = result.scalar_one_or_none()
    if analysis is None:
        await db.rollback()
        return {
            "accepted": False,
            "analysis_id": str(body.analysis_id),
            "execution": "not_found",
        }

    reservation = reserve_pipeline_job_execution(analysis)
    if not reservation.launchable:
        await db.rollback()
        return {
            "accepted": False,
            "analysis_id": str(body.analysis_id),
            "execution": reservation.status,
        }

    await db.commit()
    execution_id = str(reservation.execution_id)
    receipt = await build_pipeline_job_launcher().launch(
        analysis_id=str(body.analysis_id),
        org_id=str(body.org_id),
        execution_id=execution_id,
    )

    return {
        "accepted": True,
        "analysis_id": str(body.analysis_id),
        "execution": "job_accepted",
        "execution_id": execution_id,
        "reservation_reused": reservation.reused,
        "operation_name": receipt.operation_name,
    }


@router.post("/run-monitor-scan", status_code=status.HTTP_202_ACCEPTED)
async def run_monitor_scan(
    body: MonitorScanRunRequest,
    caller_email: str = Depends(verify_oidc_token),
) -> dict[str, Any]:
    """Trigger one monitor scan from Cloud Tasks."""
    logger.info(
        "internal.run_monitor_scan.received",
        monitor_id=body.monitor_id,
        org_id=body.org_id,
        force_full_refresh=body.force_full_refresh,
        caller=caller_email,
    )

    result = await run_in_threadpool(
        _execute_monitor_scan_background,
        monitor_id=body.monitor_id,
        org_id=body.org_id,
        force_full_refresh=body.force_full_refresh,
    )
    _raise_for_failed_worker_result(
        result,
        worker_name="Monitor scan worker",
        resource_id=body.monitor_id,
    )

    return {
        "accepted": True,
        "monitor_id": body.monitor_id,
        "execution": "completed",
    }


@router.post("/run-due-monitor-dispatch", status_code=status.HTTP_202_ACCEPTED)
async def run_due_monitor_dispatch(
    caller_email: str = Depends(verify_oidc_token),
) -> dict[str, Any]:
    """Trigger the scheduled due-monitor sweep from Cloud Scheduler."""
    logger.info(
        "internal.run_due_monitor_dispatch.received",
        caller=caller_email,
    )

    # Run dispatch directly in the uvicorn event loop to avoid asyncpg cross-loop
    # errors that occur when monitor_tasks.run_async() submits to the Celery event
    # loop while the asyncpg pool is bound to the uvicorn loop.
    monitor_tasks_module = import_module("api.workers.monitor_tasks")
    result = await monitor_tasks_module._dispatch_due_monitors_async()
    logger.info(
        "internal.run_due_monitor_dispatch.execution_completed",
        result=result,
    )

    return {
        "accepted": True,
        "execution": "completed",
    }


@router.post(
    "/run-external-report-delivery-reconciliation",
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_external_report_delivery_reconciliation(
    caller_email: str = Depends(verify_oidc_token),
    body: ExternalReportDeliverySweepRequest | None = None,
) -> dict[str, Any]:
    """Fan out tenant-scoped invitation reconciliation Cloud Tasks."""
    logger.info(
        "internal.run_external_report_delivery_reconciliation.received",
        caller=caller_email,
    )
    tasks_module = import_module("api.workers.tasks")
    result = await tasks_module._dispatch_external_report_delivery_reconciliation_async(
        cursor=str(body.cursor) if body is not None else None,
        sweep_id=body.sweep_id if body is not None else None,
    )
    logger.info(
        "internal.run_external_report_delivery_reconciliation.completed",
        result=result,
    )
    return {"accepted": True, "execution": "completed", "result": result}


@router.post(
    "/run-external-report-delivery-reconciliation-org",
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_external_report_delivery_reconciliation_org(
    body: ExternalReportDeliveryReconciliationRequest,
    caller_email: str = Depends(verify_oidc_token),
) -> dict[str, Any]:
    """Reconcile one tenant without granting the task cross-tenant scope."""
    logger.info(
        "internal.run_external_report_delivery_reconciliation_org.received",
        org_id=body.org_id,
        dedupe_key=body.dedupe_key,
        caller=caller_email,
    )
    tasks_module = import_module("api.workers.tasks")
    result = await tasks_module._reconcile_external_report_deliveries_for_org(
        str(body.org_id),
        dedupe_key=body.dedupe_key,
        continuation=body.continuation,
    )
    logger.info(
        "internal.run_external_report_delivery_reconciliation_org.completed",
        org_id=body.org_id,
        dedupe_key=body.dedupe_key,
        result=result,
    )
    return {"accepted": True, "execution": "completed", "result": result}


@router.post("/run-monitor-alert-email", status_code=status.HTTP_202_ACCEPTED)
async def run_monitor_alert_email(
    body: MonitorAlertEmailRunRequest,
    caller_email: str = Depends(verify_oidc_token),
) -> dict[str, Any]:
    """Trigger one monitor alert email from Cloud Tasks."""
    logger.info(
        "internal.run_monitor_alert_email.received",
        user_id=body.user_id,
        monitor_id=body.monitor_id,
        alert_id=body.alert_id,
        org_id=body.org_id,
        caller=caller_email,
    )

    result = await run_in_threadpool(
        _execute_monitor_alert_email_background,
        user_id=body.user_id,
        monitor_id=body.monitor_id,
        alert_id=body.alert_id,
        org_id=body.org_id,
    )
    _raise_for_failed_worker_result(
        result,
        worker_name="Monitor alert email worker",
        resource_id=body.alert_id,
    )

    return {
        "accepted": True,
        "alert_id": body.alert_id,
        "execution": "completed",
    }


@router.post("/run-weekly-digest", status_code=status.HTTP_202_ACCEPTED)
async def run_weekly_digest(
    body: WeeklyDigestRunRequest,
    caller_email: str = Depends(verify_oidc_token),
) -> dict[str, Any]:
    """Trigger the weekly digest sweep from Cloud Tasks."""
    logger.info(
        "internal.run_weekly_digest.received",
        dedupe_key=body.dedupe_key,
        caller=caller_email,
    )

    result = await run_in_threadpool(
        _execute_weekly_digest_background,
        dedupe_key=body.dedupe_key,
    )
    _raise_for_failed_worker_result(
        result,
        worker_name="Weekly digest worker",
        resource_id=body.dedupe_key or "weekly-digest",
    )

    return {
        "accepted": True,
        "execution": "completed",
        "dedupe_key": body.dedupe_key,
    }


@router.post("/run-export", status_code=status.HTTP_202_ACCEPTED)
async def run_export(
    body: ExportRunRequest,
    caller_email: str = Depends(verify_oidc_token),
) -> dict[str, Any]:
    """Trigger an export job from Cloud Tasks."""
    logger.info(
        "internal.run_export.received",
        export_job_id=body.export_job_id,
        caller=caller_email,
    )

    result = await run_in_threadpool(
        _execute_export_background,
        export_job_id=body.export_job_id,
        org_id=body.org_id,
    )
    _raise_for_failed_worker_result(
        result,
        worker_name="Export worker",
        resource_id=body.export_job_id,
    )

    return {
        "accepted": True,
        "export_job_id": body.export_job_id,
        "execution": "completed",
    }


@router.post("/run-faithfulness", status_code=status.HTTP_202_ACCEPTED)
async def run_faithfulness(
    body: FaithfulnessRunRequest,
    caller_email: str = Depends(verify_oidc_token),
) -> dict[str, Any]:
    """Trigger shadow faithfulness scoring from Cloud Tasks."""
    logger.info(
        "internal.run_faithfulness.received",
        analysis_id=body.analysis_id,
        caller=caller_email,
    )

    result = await run_in_threadpool(
        _execute_faithfulness_background,
        analysis_id=body.analysis_id,
        org_id=body.org_id,
    )
    _raise_for_failed_worker_result(
        result,
        worker_name="Faithfulness worker",
        resource_id=body.analysis_id,
    )

    return {
        "accepted": True,
        "analysis_id": body.analysis_id,
        "execution": "completed",
    }


@router.post("/run-pending-erasures", status_code=status.HTTP_202_ACCEPTED)
async def run_pending_erasures(
    caller_email: str = Depends(verify_oidc_token),
) -> dict[str, Any]:
    """Trigger the GDPR pending org erasure sweep from Cloud Scheduler.

    Finds all orgs with deletion_status='pending' whose deletion_scheduled_at
    is in the past and executes the erasure for each. Idempotent — already-
    erased orgs are skipped silently.
    """
    logger.info("internal.run_pending_erasures.received", caller=caller_email)
    offboarding_module = import_module("api.services.offboarding")
    result = await offboarding_module.process_pending_erasures_async()
    logger.info(
        "internal.run_pending_erasures.execution_completed",
        erased_count=result.get("erased_count"),
        error_count=result.get("error_count"),
    )
    return {"accepted": True, "execution": "completed", **result}


@router.post("/run-stale-analysis-sweep", status_code=status.HTTP_202_ACCEPTED)
async def run_stale_analysis_sweep(
    caller_email: str = Depends(verify_oidc_token),
) -> dict[str, Any]:
    """Redrive orphaned PENDING analyses and expired RUNNING leases safely.

    Eligible analyses older than 2 hours are dispatched again with the same
    analysis identity and a rotated execution fence. If bounded reconciliation
    is exhausted, any purchased-credit reservation is refunded before the
    receipt is terminalized.
    """
    logger.info("internal.run_stale_analysis_sweep.received", caller=caller_email)
    maintenance_module = import_module("api.services.analysis_maintenance")
    result = await maintenance_module.mark_stale_analyses_failed_async()
    logger.info(
        "internal.run_stale_analysis_sweep.execution_completed",
        marked_count=result.get("marked_count"),
        redriven_count=result.get("redriven_count"),
        refunded_credits=result.get("refunded_credits"),
        orgs_checked=result.get("orgs_checked"),
        error_count=result.get("error_count"),
    )
    error_count = int(result.get("error_count") or 0)
    if error_count:
        raise APIError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Stale Analysis Sweep Incomplete",
            f"Stale analysis reconciliation completed with {error_count} retryable error(s).",
            retry_after_seconds=60,
        )
    return {"accepted": True, "execution": "completed", **result}
