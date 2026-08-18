"""Attorney-only claimed-use counsel receipt routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from api.config import get_settings
from api.db.models import User
from api.deps import DBSession, require_permission
from api.ratelimit import limiter
from api.schemas.claimed_use_receipts import (
    ClaimedUseReceiptIssueRequest,
    ClaimedUseReceiptListResponse,
    ClaimedUseReceiptOut,
    ClaimedUseReceiptRevokeRequest,
)
from api.services.claimed_use_ledger_client import call_claimed_use_ledger
from api.services.claimed_use_receipts import (
    issue_claimed_use_receipt,
    list_claimed_use_receipts,
    revoke_claimed_use_receipt,
)

router = APIRouter()


@router.get(
    "/analyses/{analysis_id}/claimed-use-receipts",
    response_model=ClaimedUseReceiptListResponse,
)
async def list_receipts(
    analysis_id: uuid.UUID,
    user: Annotated[User, Depends(require_permission("claimed_use_receipt.view"))],
    db: DBSession,
) -> ClaimedUseReceiptListResponse:
    """List current eligible uses and immutable receipt history."""
    if get_settings().app_env == "prod":
        payload = await call_claimed_use_ledger(
            operation="list",
            payload={
                "analysis_id": str(analysis_id),
                "actor_user_id": str(user.id),
                "org_id": str(user.org_id),
            },
        )
        return ClaimedUseReceiptListResponse.model_validate(payload)
    return await list_claimed_use_receipts(
        db,
        analysis_id=analysis_id,
        user=user,
    )


@router.post(
    "/analyses/{analysis_id}/claimed-use-receipts",
    response_model=ClaimedUseReceiptOut,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
async def issue_receipt(
    analysis_id: uuid.UUID,
    body: ClaimedUseReceiptIssueRequest,
    user: Annotated[User, Depends(require_permission("claimed_use_receipt.issue"))],
    db: DBSession,
    request: Request,
) -> ClaimedUseReceiptOut:
    """Issue an attorney affirmation from current server-resolved evidence."""
    if get_settings().app_env == "prod":
        payload = await call_claimed_use_ledger(
            operation="issue",
            payload={
                "analysis_id": str(analysis_id),
                "actor_user_id": str(user.id),
                "org_id": str(user.org_id),
                "body": body.model_dump(mode="json"),
            },
        )
        return ClaimedUseReceiptOut.model_validate(payload)
    return await issue_claimed_use_receipt(
        db,
        analysis_id=analysis_id,
        user=user,
        body=body,
        request=request,
    )


@router.post(
    "/analyses/{analysis_id}/claimed-use-receipts/{receipt_id}/revoke",
    response_model=ClaimedUseReceiptOut,
)
@limiter.limit("20/minute")
async def revoke_receipt(
    analysis_id: uuid.UUID,
    receipt_id: uuid.UUID,
    body: ClaimedUseReceiptRevokeRequest,
    user: Annotated[User, Depends(require_permission("claimed_use_receipt.revoke"))],
    db: DBSession,
    request: Request,
) -> ClaimedUseReceiptOut:
    """Append a reasoned revocation without deleting the signed receipt."""
    if get_settings().app_env == "prod":
        payload = await call_claimed_use_ledger(
            operation="revoke",
            payload={
                "analysis_id": str(analysis_id),
                "receipt_id": str(receipt_id),
                "actor_user_id": str(user.id),
                "org_id": str(user.org_id),
                "reason": body.reason,
            },
        )
        return ClaimedUseReceiptOut.model_validate(payload)
    return await revoke_claimed_use_receipt(
        db,
        analysis_id=analysis_id,
        receipt_id=receipt_id,
        user=user,
        reason=body.reason,
        request=request,
    )
