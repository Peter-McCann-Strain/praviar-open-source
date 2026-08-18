"""Two-actor PATENTSCOPE Markush evidence import and verification routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from praviar_pipeline.checkpoint import CheckpointIntegrityKeyRing
from praviar_pipeline.models.markush_evidence import MarkushEvidenceReceipt

from api.audit import write_audit_log
from api.config import get_settings
from api.db.models import User
from api.deps import DBSession, require_permission
from api.errors import APIError
from api.ratelimit import limiter
from api.schemas.markush_evidence import (
    MarkushEvidenceImportRequest,
    MarkushEvidenceVerifyRequest,
)
from api.services.markush_evidence import (
    build_analyst_markush_draft,
    verify_analyst_markush_draft,
)

router = APIRouter()


def _markush_integrity_keys() -> CheckpointIntegrityKeyRing:
    return CheckpointIntegrityKeyRing.from_secret(
        get_settings().pipeline_checkpoint_hmac_secret.get_secret_value()
    )


@router.post(
    "/markush-evidence/import",
    response_model=MarkushEvidenceReceipt,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/minute")
async def import_markush_evidence(
    body: MarkushEvidenceImportRequest,
    user: Annotated[User, Depends(require_permission("analysis.create"))],
    db: DBSession,
    request: Request,
) -> MarkushEvidenceReceipt:
    """Hash an analyst's original PATENTSCOPE export into a reviewable draft."""
    try:
        receipt = build_analyst_markush_draft(
            body,
            analyst_user_id=user.clerk_user_id,
            analyst_org_id=str(user.org_id),
            integrity_keys=_markush_integrity_keys(),
        )
    except ValueError as exc:
        raise APIError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Invalid Markush evidence import",
            str(exc),
        ) from exc
    try:
        await write_audit_log(
            db,
            org_id=user.org_id,
            user_id=user.id,
            action="markush_evidence.import",
            details={
                "receipt_sha256": receipt.receipt_sha256,
                "artifact_sha256": receipt.imported_artifact_sha256,
                "result_count": receipt.result_count,
                "selected_publication_count": len(receipt.selected_publication_ids),
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return receipt


@router.post(
    "/markush-evidence/verify",
    response_model=MarkushEvidenceReceipt,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/minute")
async def verify_markush_evidence(
    body: MarkushEvidenceVerifyRequest,
    user: Annotated[User, Depends(require_permission("reviewer_decision.create"))],
    db: DBSession,
    request: Request,
) -> MarkushEvidenceReceipt:
    """Re-hash and independently verify an analyst's draft receipt."""
    try:
        receipt = verify_analyst_markush_draft(
            body,
            reviewer_user_id=user.clerk_user_id,
            reviewer_org_id=str(user.org_id),
            integrity_keys=_markush_integrity_keys(),
        )
    except ValueError as exc:
        raise APIError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Invalid Markush evidence verification",
            str(exc),
        ) from exc
    try:
        await write_audit_log(
            db,
            org_id=user.org_id,
            user_id=user.id,
            action="markush_evidence.verify",
            details={
                "receipt_sha256": receipt.receipt_sha256,
                "artifact_sha256": receipt.imported_artifact_sha256,
                "analyst_identity": receipt.analyst_identity,
                "reviewer_identity": receipt.reviewer_identity,
                "result_count": receipt.result_count,
                "selected_publication_count": len(receipt.selected_publication_ids),
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return receipt
