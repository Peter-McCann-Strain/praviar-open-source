"""Service layer for pipeline checkpoint decisions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError  # noqa: F401 — used in upsert_checkpoint_decision
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import AnalysisCheckpointDecision, User
from api.errors import APIError
from api.schemas.checkpoint_decisions import (
    REPORT_REVIEW_CHECKPOINT_ID,
    CheckpointDecisionIn,
)
from api.services.reviewer_decisions import assert_analysis_in_org


def _apply_existing_decision(
    existing: AnalysisCheckpointDecision,
    *,
    user: User,
    body: CheckpointDecisionIn,
) -> tuple[AnalysisCheckpointDecision, str]:
    """Apply a mutable decision, keeping identity/report attestations immutable."""
    integrity_bound = existing.checkpoint_type in {
        "identity_review",
        "report_review",
    } or body.checkpoint_type in {"identity_review", "report_review"}
    if integrity_bound:
        if (
            existing.checkpoint_type == body.checkpoint_type
            and existing.decision == body.decision
            and existing.note == body.note
        ):
            return existing, "checkpoint_decision.replay"
        raise APIError(
            409,
            "Conflict",
            (
                "An integrity-bound checkpoint decision is immutable. Launch a new "
                "analysis or digest-bound report checkpoint to review a different "
                "identity, payload, or decision."
            ),
        )

    existing.checkpoint_type = body.checkpoint_type
    existing.decision = body.decision
    existing.note = body.note
    existing.reviewer_id = user.id
    existing.reviewed_at = datetime.now(UTC)
    return existing, "checkpoint_decision.update"


def _validate_checkpoint_binding(
    *,
    checkpoint_id: str,
    body: CheckpointDecisionIn,
) -> None:
    """Reject type/digest ambiguity before a decision can enter persistence."""

    report_match = REPORT_REVIEW_CHECKPOINT_ID.fullmatch(checkpoint_id)
    if body.checkpoint_type == "report_review":
        if report_match is None:
            raise APIError(
                422,
                "Invalid checkpoint binding",
                "Report review checkpoint_id must bind a review payload digest.",
            )
        if body.decision == "approve":
            assert body.review_payload_sha256 is not None
            if report_match.group("digest_prefix") != body.review_payload_sha256[:16]:
                raise APIError(
                    422,
                    "Invalid checkpoint binding",
                    "Report review checkpoint_id does not match review_payload_sha256.",
                )
    elif ":report_review:" in checkpoint_id:
        raise APIError(
            422,
            "Invalid checkpoint binding",
            "Report review checkpoint_id cannot be used for another checkpoint type.",
        )


async def fetch_checkpoint_decision(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    checkpoint_id: str,
) -> AnalysisCheckpointDecision:
    await assert_analysis_in_org(db, analysis_id=analysis_id, org_id=org_id)
    result = await db.execute(
        select(AnalysisCheckpointDecision).where(
            AnalysisCheckpointDecision.analysis_id == analysis_id,
            AnalysisCheckpointDecision.org_id == org_id,
            AnalysisCheckpointDecision.checkpoint_id == checkpoint_id,
        )
    )
    decision = result.scalar_one_or_none()
    if decision is None:
        raise APIError(404, "Not Found", "Checkpoint decision not found")
    return decision


async def upsert_checkpoint_decision(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    checkpoint_id: str,
    user: User,
    body: CheckpointDecisionIn,
) -> tuple[AnalysisCheckpointDecision, str]:
    _validate_checkpoint_binding(checkpoint_id=checkpoint_id, body=body)
    await assert_analysis_in_org(db, analysis_id=analysis_id, org_id=user.org_id)
    result = await db.execute(
        select(AnalysisCheckpointDecision)
        .where(
            AnalysisCheckpointDecision.analysis_id == analysis_id,
            AnalysisCheckpointDecision.org_id == user.org_id,
            AnalysisCheckpointDecision.checkpoint_id == checkpoint_id,
        )
        .with_for_update()
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return _apply_existing_decision(existing, user=user, body=body)

    decision = AnalysisCheckpointDecision(
        analysis_id=analysis_id,
        org_id=user.org_id,
        checkpoint_id=checkpoint_id,
        checkpoint_type=body.checkpoint_type,
        decision=body.decision,
        note=body.note,
        reviewer_id=user.id,
    )
    db.add(decision)
    try:
        await db.flush()
        return decision, "checkpoint_decision.create"
    except IntegrityError:
        await db.rollback()
        result = await db.execute(
            select(AnalysisCheckpointDecision)
            .where(
                AnalysisCheckpointDecision.analysis_id == analysis_id,
                AnalysisCheckpointDecision.org_id == user.org_id,
                AnalysisCheckpointDecision.checkpoint_id == checkpoint_id,
            )
            .with_for_update()
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            raise
        return _apply_existing_decision(existing, user=user, body=body)
