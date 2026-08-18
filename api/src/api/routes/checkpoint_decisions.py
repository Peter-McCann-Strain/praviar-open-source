"""Routes for human decisions on pipeline checkpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Path, Request, status

from api.audit import write_audit_log
from api.db.models import AnalysisCheckpointDecision, User
from api.deps import DBSession, require_permission
from api.metrics import record_checkpoint_decision
from api.schemas.checkpoint_decisions import CheckpointDecisionIn, CheckpointDecisionOut
from api.services.checkpoint_decisions import (
    fetch_checkpoint_decision,
    upsert_checkpoint_decision,
)

logger = structlog.get_logger()
router = APIRouter()


@router.post(
    "/analyses/{analysis_id}/checkpoints/{checkpoint_id}/decision",
    response_model=CheckpointDecisionOut,
    status_code=status.HTTP_201_CREATED,
)
async def submit_checkpoint_decision(
    analysis_id: uuid.UUID,
    checkpoint_id: Annotated[str, Path(max_length=128)],
    body: CheckpointDecisionIn,
    user: Annotated[User, Depends(require_permission("checkpoint_decision.create"))],
    db: DBSession,
    request: Request,
) -> AnalysisCheckpointDecision:
    try:
        decision, audit_action = await upsert_checkpoint_decision(
            db,
            analysis_id=analysis_id,
            checkpoint_id=checkpoint_id,
            user=user,
            body=body,
        )
        await db.flush()
        await write_audit_log(
            db,
            org_id=user.org_id,
            user_id=user.id,
            analysis_id=analysis_id,
            action=audit_action,
            details={
                "checkpoint_id": checkpoint_id,
                "checkpoint_type": body.checkpoint_type,
                "decision": body.decision,
                "review_payload_sha256": body.review_payload_sha256,
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    record_checkpoint_decision(body.checkpoint_type, body.decision)
    logger.info(
        "checkpoint_decision_saved",
        analysis_id=str(analysis_id),
        checkpoint_id=checkpoint_id,
        checkpoint_type=body.checkpoint_type,
        decision=body.decision,
        reviewer_id=str(user.id),
    )
    return decision


@router.get(
    "/analyses/{analysis_id}/checkpoints/{checkpoint_id}/decision",
    response_model=CheckpointDecisionOut,
)
async def get_checkpoint_decision(
    analysis_id: uuid.UUID,
    checkpoint_id: str,
    user: Annotated[User, Depends(require_permission("analysis.view"))],
    db: DBSession,
) -> AnalysisCheckpointDecision:
    return await fetch_checkpoint_decision(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
        checkpoint_id=checkpoint_id,
    )
