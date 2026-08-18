"""Business logic for batch analysis lifecycle management."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass

import structlog
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import write_audit_log
from api.db.models import Analysis, AnalysisStatus, BatchAnalysis, Organization
from api.errors import APIError, problem_type_uri
from api.schemas.analyses import (
    AnalysisConfigSchema,
    CreateAnalysisRequest,
    detect_submitted_input_type,
)
from api.schemas.batch import CreateBatchRequest
from api.services.analysis_dispatch import reserve_pipeline_reconciliation
from api.services.batch_queries import (
    load_batch_analyses_for_update,
    load_batch_by_launch_key,
    load_batch_for_org,
    load_batch_page,
    load_cancelable_analyses,
    load_child_analysis_counts,
)
from api.services.batch_serialization import (
    serialize_batch as serialize_batch_impl,
)
from api.services.batch_serialization import (
    serialize_batch_page as serialize_batch_page_impl,
)
from api.services.batch_status import recompute_batch_status
from api.services.batch_types import BatchPage
from api.services.billing_queries import (
    AnalysisCreditReservation,
    consume_analysis_credits,
    refund_cancelled_analysis_credits,
    reserve_analysis_capacity,
)
from api.services.configs import load_org_default_config

logger = structlog.get_logger()

__all__ = [
    "BatchCreationResult",
    "BatchPage",
    "serialize_batch",
    "serialize_batch_page",
    "recompute_batch_status",
    "create_batch",
    "list_batches_page",
    "get_batch_with_live_status",
    "cancel_batch",
]


@dataclass(frozen=True)
class BatchCreationResult:
    batch: BatchAnalysis
    replayed: bool


def _validate_launch_idempotency_key(value: str) -> str:
    if not 16 <= len(value) <= 128 or any(
        ord(character) < 0x21 or ord(character) > 0x7E for character in value
    ):
        raise APIError(
            422,
            "Validation Error",
            "Idempotency-Key must contain 16 to 128 visible ASCII characters",
        )
    return value


def _launch_idempotency_key_digest(
    *,
    org_id: uuid.UUID,
    idempotency_key: str,
) -> str:
    return hashlib.sha256(
        b"praviar:batch-launch:idempotency:v1\0"
        + org_id.bytes
        + b"\0"
        + idempotency_key.encode("ascii")
    ).hexdigest()


def _launch_payload_digest(body: CreateBatchRequest) -> str:
    canonical_payload = json.dumps(
        body.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


async def _lock_batch_launch_org(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
) -> None:
    result = await db.execute(
        select(Organization.id).where(Organization.id == org_id).with_for_update()
    )
    if result.scalar_one_or_none() is None:
        raise APIError(404, "Not Found", "Organization not found")


async def _dispatch_batch_children(
    analyses: list[Analysis],
    *,
    org_id: uuid.UUID,
    reconciliation_keys: dict[uuid.UUID, str] | None = None,
) -> None:
    """Attempt every queue boundary and preserve receipts on ambiguous errors."""
    from api.services.task_dispatcher import build_dispatcher

    dispatcher = build_dispatcher()
    dispatch_failures: list[tuple[uuid.UUID, Exception]] = []
    for analysis in analyses:
        reconciliation_key = (
            reconciliation_keys.get(analysis.id) if reconciliation_keys is not None else None
        )
        try:
            await dispatcher.dispatch_pipeline_run(
                analysis_id=str(analysis.id),
                org_id=str(org_id),
                reconciliation_key=reconciliation_key,
            )
        except Exception as exc:
            dispatch_failures.append((analysis.id, exc))
            logger.error(
                "batch_pipeline_dispatch_outcome_unknown",
                analysis_id=str(analysis.id),
                org_id=str(org_id),
                reconciliation_key=reconciliation_key,
                error_type=type(exc).__name__,
                exc_info=True,
            )

    if dispatch_failures:
        # A timeout/error at the queue boundary is not authoritative rejection:
        # the task may already be durable. Keep the PENDING child receipts and
        # their credit bindings so same-key replay or the stale sweep can
        # reconcile them with deterministic repair generations.
        raise APIError(
            503,
            "Service Unavailable",
            "One or more pipeline dispatch outcomes could not be confirmed",
        ) from dispatch_failures[0][1]


async def _redrive_pending_batch(
    db: AsyncSession,
    batch: BatchAnalysis,
    *,
    org_id: uuid.UUID,
) -> None:
    analyses = await load_batch_analyses_for_update(
        db,
        batch_id=batch.id,
        org_id=org_id,
    )
    pending_analyses: list[Analysis] = []
    reconciliation_keys: dict[uuid.UUID, str] = {}
    for analysis in analyses:
        reservation = reserve_pipeline_reconciliation(analysis)
        if reservation is None:
            continue
        if reservation.exhausted:
            await db.rollback()
            raise APIError(
                503,
                "Service Unavailable",
                "Pipeline dispatch reconciliation attempts are exhausted",
            )
        pending_analyses.append(analysis)
        reconciliation_keys[analysis.id] = reservation.task_key

    if not pending_analyses:
        return

    # Persist repair generations before crossing the queue boundary.
    await db.commit()
    await _dispatch_batch_children(
        pending_analyses,
        org_id=org_id,
        reconciliation_keys=reconciliation_keys,
    )


async def _consume_batch_credit_reservations(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    batch_id: uuid.UUID,
    analyses: list[Analysis],
    reservations: list[AnalysisCreditReservation],
) -> None:
    """Bind each purchased credit to one child for exact cancellation refunds."""
    total_credits = sum(reservation.credits for reservation in reservations)
    if total_credits > len(analyses):
        raise RuntimeError("Batch credit reservation exceeds child analysis count")
    credited_analyses = iter(analyses[len(analyses) - total_credits :])
    for reservation in reservations:
        for credit_index in range(reservation.credits):
            analysis = next(credited_analyses)
            await consume_analysis_credits(
                db,
                org_id=org_id,
                credits=1,
                analysis_id=analysis.id,
                details={
                    "requested_analyses": len(analyses),
                    "source": "batch.create",
                    "batch_id": str(batch_id),
                },
                reservation_id=f"{reservation.reservation_id}:{credit_index}",
            )


def serialize_batch(batch: BatchAnalysis) -> dict:
    return serialize_batch_impl(batch)


def serialize_batch_page(page: BatchPage) -> dict:
    return serialize_batch_page_impl(page)


async def create_batch(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    body: CreateBatchRequest,
    request: Request,
    idempotency_key: str,
) -> BatchCreationResult:
    normalized_idempotency_key = _validate_launch_idempotency_key(idempotency_key)
    key_digest = _launch_idempotency_key_digest(
        org_id=org_id,
        idempotency_key=normalized_idempotency_key,
    )
    payload_digest = _launch_payload_digest(body)

    await _lock_batch_launch_org(db, org_id=org_id)
    existing_batch = await load_batch_by_launch_key(
        db,
        org_id=org_id,
        key_digest=key_digest,
    )
    if existing_batch is not None:
        if existing_batch.launch_payload_digest != payload_digest:
            raise APIError(
                409,
                "Conflict",
                "Idempotency-Key was already used with a different batch launch request",
            )
        await _redrive_pending_batch(db, existing_batch, org_id=org_id)
        return BatchCreationResult(batch=existing_batch, replayed=True)

    credit_reservation_id = str(uuid.uuid4())
    credit_reservations: list[AnalysisCreditReservation] = []
    within_limit, used, limit = await reserve_analysis_capacity(
        db,
        org_id,
        requested_analyses=len(body.compounds),
        reservation_id=credit_reservation_id,
        reservation_details={"source": "batch.create"},
        credit_reservations=credit_reservations,
        defer_credit_consumption=True,
    )
    if not within_limit:
        raise APIError(
            429,
            "Too Many Requests",
            "No FTO report request capacity remains this period. "
            f"{used} of {limit} report requests used.",
            type_uri=problem_type_uri("analysis-capacity-exhausted"),
        )

    batch = BatchAnalysis(
        org_id=org_id,
        user_id=user_id,
        name=body.name,
        total_compounds=len(body.compounds),
        status=AnalysisStatus.PENDING,
        launch_idempotency_key_digest=key_digest,
        launch_payload_digest=payload_digest,
    )
    db.add(batch)
    await db.flush()

    org_default_config = await load_org_default_config(db, org_id=org_id)
    analyses: list[Analysis] = []
    analysis_ids: list[str] = []
    for compound_input in body.compounds:
        submitted_input_type = detect_submitted_input_type(compound_input)
        analysis_request = CreateAnalysisRequest(
            compound_input=compound_input,
            input_type=submitted_input_type,
            submitted_identity_confirmed=True,
            submitted_identity_value=compound_input,
            config=body.config if body.config else AnalysisConfigSchema(),
        )
        analysis = Analysis(
            id=uuid.uuid4(),
            org_id=org_id,
            compound_input=analysis_request.compound_input,
            input_type=submitted_input_type,
            submitted_identity_confirmed=True,
            submitted_identity_value=analysis_request.submitted_identity_value,
            config=analysis_request.runtime_config(org_default_config=org_default_config),
            initiated_by=user_id,
            status=AnalysisStatus.PENDING,
            batch_id=batch.id,
        )
        db.add(analysis)
        analyses.append(analysis)
        analysis_ids.append(str(analysis.id))

    await db.flush()
    batch.analysis_ids = analysis_ids
    try:
        await _consume_batch_credit_reservations(
            db,
            org_id=org_id,
            batch_id=batch.id,
            analyses=analyses,
            reservations=credit_reservations,
        )
        await write_audit_log(
            db,
            org_id=org_id,
            user_id=user_id,
            action="batch.created",
            details={
                "batch_id": str(batch.id),
                "name": body.name,
                "compound_count": len(body.compounds),
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
        await db.refresh(batch)
    except Exception:
        await db.rollback()
        raise

    await _dispatch_batch_children(analyses, org_id=org_id)

    logger.info(
        "batch_created",
        batch_id=str(batch.id),
        user_id=str(user_id),
        compound_count=len(body.compounds),
    )
    return BatchCreationResult(batch=batch, replayed=False)


async def list_batches_page(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    page: int,
    per_page: int,
) -> BatchPage:
    return await load_batch_page(db, org_id=org_id, page=page, per_page=per_page)


async def get_batch_with_live_status(
    db: AsyncSession,
    *,
    batch_id: uuid.UUID,
    org_id: uuid.UUID,
) -> BatchAnalysis:
    # Lock the row so a concurrent cancel_batch cannot overwrite the status we
    # compute and commit below (lost-update race: GET recomputes RUNNING over a
    # freshly-committed CANCELLED from a concurrent DELETE).
    batch = await load_batch_for_org(db, batch_id=batch_id, org_id=org_id, with_for_update=True)
    if not batch:
        raise APIError(404, "Not Found", "Batch not found")

    # A cancelled batch is terminal — never recompute its status from child
    # analyses (some may have completed before the cancel signal reached them).
    if batch.status == AnalysisStatus.CANCELLED:
        return batch

    if batch.analysis_ids:
        (
            completed_count,
            failed_count,
            running_count,
            cancelled_count,
        ) = await load_child_analysis_counts(
            db,
            analysis_ids=batch.analysis_ids,
            org_id=org_id,
        )

        batch.completed_count = completed_count
        batch.failed_count = failed_count
        # The row lock acquired above prevents a concurrent cancellation from
        # changing this batch until this transaction commits.
        batch.status = recompute_batch_status(
            total_compounds=batch.total_compounds,
            completed_count=completed_count,
            failed_count=failed_count,
            running_count=running_count,
            cancelled_count=cancelled_count,
        )
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        await db.refresh(batch)

    return batch


async def cancel_batch(
    db: AsyncSession,
    *,
    batch_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request | None = None,
) -> BatchAnalysis:
    batch = await load_batch_for_org(db, batch_id=batch_id, org_id=org_id, with_for_update=True)
    if not batch:
        raise APIError(404, "Not Found", "Batch not found")

    terminal_statuses = {
        AnalysisStatus.CANCELLED,
        AnalysisStatus.COMPLETED,
        AnalysisStatus.FAILED,
    }
    if batch.status in terminal_statuses:
        return batch

    batch.status = AnalysisStatus.CANCELLED

    cancelable_analyses: list[Analysis] = []
    refunded_credits = 0
    if batch.analysis_ids:
        cancelable_analyses = await load_cancelable_analyses(
            db,
            analysis_ids=batch.analysis_ids,
            org_id=org_id,
        )
        for analysis in cancelable_analyses:
            refunded_credits += await refund_cancelled_analysis_credits(
                db,
                org_id=org_id,
                analysis_id=analysis.id,
                details={
                    "source": "batch.cancel",
                    "batch_id": str(batch.id),
                },
            )
            analysis.status = AnalysisStatus.CANCELLED

    try:
        await write_audit_log(
            db,
            org_id=org_id,
            user_id=user_id,
            action="batch.cancelled",
            details={
                "batch_id": str(batch.id),
                "cancelled_analysis_count": len(cancelable_analyses),
                "refunded_purchased_credits": refunded_credits,
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return batch
