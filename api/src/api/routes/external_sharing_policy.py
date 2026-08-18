"""Administrator controls for recipient-domain external sharing policy."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from api.audit import write_audit_log
from api.db.models import User
from api.deps import DBSession, require_permission
from api.schemas.external_sharing import (
    ExternalSharingPolicy,
    ExternalSharingPolicyUpdateRequest,
    ExternalSharingPolicyUpdateResponse,
)
from api.services.external_sharing_policy import (
    get_external_sharing_policy,
    update_external_sharing_policy,
)

router = APIRouter()

ExternalSharingAdmin = Annotated[User, Depends(require_permission("admin.view"))]
ExternalSharingManager = Annotated[
    User,
    Depends(require_permission("admin.manage_users")),
]


@router.get(
    "/admin/external-sharing-policy",
    response_model=ExternalSharingPolicy,
    summary="Get external sharing policy",
)
async def get_policy(
    user: ExternalSharingAdmin,
    db: DBSession,
) -> ExternalSharingPolicy:
    """Return the typed policy for only the caller's organization."""
    return await get_external_sharing_policy(db, org_id=user.org_id)


@router.patch(
    "/admin/external-sharing-policy",
    response_model=ExternalSharingPolicyUpdateResponse,
    summary="Update external sharing policy",
)
async def patch_policy(
    body: ExternalSharingPolicyUpdateRequest,
    user: ExternalSharingManager,
    db: DBSession,
    request: Request,
) -> ExternalSharingPolicyUpdateResponse:
    """Apply an org-locked policy change with fail-closed revocation auditing."""
    try:
        updated = await update_external_sharing_policy(
            db,
            org_id=user.org_id,
            request=body,
        )
        if updated.confirmation_required:
            await db.rollback()
            return ExternalSharingPolicyUpdateResponse(
                **updated.policy.model_dump(),
                status="confirmation_required",
                impact=updated.impact,
                proposal_digest=updated.proposal_digest,
                revoked_grant_count=0,
            )
        for grant in updated.impacted_grants:
            await write_audit_log(
                db,
                org_id=user.org_id,
                user_id=user.id,
                analysis_id=grant.analysis_id,
                action="report.share.grant_revoked_by_policy",
                details={
                    "external_grant_id": str(grant.id),
                    "recipient_domain": grant.recipient_domain,
                    "policy_mode": updated.policy.mode,
                    "policy_version": updated.policy.version,
                },
                request=request,
                fail_closed=True,
            )
        await write_audit_log(
            db,
            org_id=user.org_id,
            user_id=user.id,
            action="organization.external_sharing_policy.updated",
            details={
                "previous_policy": updated.previous_policy.model_dump(),
                "new_policy": updated.policy.model_dump(),
                "version_transition": {
                    "from": updated.previous_policy.version,
                    "to": updated.policy.version,
                },
                "normalized_diff": {
                    "mode_changed": updated.previous_policy.mode != updated.policy.mode,
                    "approved_domains_added": sorted(
                        set(updated.policy.approved_domains)
                        - set(updated.previous_policy.approved_domains)
                    ),
                    "approved_domains_removed": sorted(
                        set(updated.previous_policy.approved_domains)
                        - set(updated.policy.approved_domains)
                    ),
                },
                "impact": {
                    **updated.impact.model_dump(),
                    "revoked_grant_count": len(updated.impacted_grants),
                },
                "confirmation": {
                    "destructive_confirmed": body.confirm_destructive,
                    "proposal_digest": body.proposal_digest,
                },
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return ExternalSharingPolicyUpdateResponse(
        **updated.policy.model_dump(),
        status="applied",
        impact=updated.impact,
        proposal_digest=None,
        revoked_grant_count=len(updated.impacted_grants),
    )


__all__ = ["router"]
