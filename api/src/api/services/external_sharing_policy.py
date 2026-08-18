"""Fail-closed organization policy for recipient-bound external sharing."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from hmac import compare_digest

from pydantic import ValidationError
from sqlalchemy import and_, case, func, or_, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import Analysis, ExternalReportGrant, Organization
from api.errors import APIError
from api.schemas.external_sharing import (
    ExternalSharingPolicy,
    ExternalSharingPolicyImpact,
    ExternalSharingPolicyUpdateRequest,
)


@dataclass(frozen=True)
class PolicyRevokedGrant:
    id: uuid.UUID
    analysis_id: uuid.UUID
    recipient_domain: str
    invitation_sent_at: datetime | None


@dataclass(frozen=True)
class ExternalSharingPolicyUpdate:
    previous_policy: ExternalSharingPolicy
    policy: ExternalSharingPolicy
    impacted_grants: tuple[PolicyRevokedGrant, ...]
    impact: ExternalSharingPolicyImpact
    proposal_digest: str
    confirmation_required: bool


def _proposal_digest(
    *,
    org_id: uuid.UUID,
    current_version: int,
    mode: str,
    approved_domains: list[str],
    impacted_grants: tuple[PolicyRevokedGrant, ...],
) -> str:
    """Bind confirmation to tenant, version, normalized policy, and exact impact."""
    payload = {
        "org_id": str(org_id),
        "current_version": current_version,
        "mode": mode,
        "approved_domains": approved_domains,
        "impacted_grant_ids": sorted(str(grant.id) for grant in impacted_grants),
        "impacted_grant_count": len(impacted_grants),
        "active_grant_ids": sorted(
            str(grant.id) for grant in impacted_grants if grant.invitation_sent_at is not None
        ),
        "pending_grant_ids": sorted(
            str(grant.id) for grant in impacted_grants if grant.invitation_sent_at is None
        ),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def _policy_from_organization(organization: Organization) -> ExternalSharingPolicy:
    """Read dedicated columns; absent values resolve to deny-all, never open."""
    mode = getattr(organization, "external_sharing_policy_mode", None)
    domains = getattr(organization, "external_sharing_approved_domains", None)
    version = getattr(organization, "external_sharing_policy_version", None)
    if mode is None and domains is None and version is None:
        return ExternalSharingPolicy()
    try:
        return ExternalSharingPolicy.model_validate(
            {
                "mode": mode,
                "approved_domains": domains,
                "version": version,
            }
        )
    except ValidationError as exc:
        raise APIError(
            500,
            "External sharing policy unavailable",
            "External sharing is blocked until an administrator repairs the organization policy",
        ) from exc


async def _load_organization(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    for_update: bool,
) -> Organization:
    statement = select(Organization).where(Organization.id == org_id)
    if for_update:
        statement = statement.with_for_update()
    result = await db.execute(statement)
    organization = result.scalar_one_or_none()
    if organization is None:
        raise APIError(404, "Not Found", "Organization not found")
    return organization


async def get_external_sharing_policy(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    for_update: bool = False,
) -> ExternalSharingPolicy:
    organization = await _load_organization(db, org_id=org_id, for_update=for_update)
    return _policy_from_organization(organization)


def require_recipient_domain_allowed(
    policy: ExternalSharingPolicy,
    *,
    recipient_domain: str,
) -> None:
    if policy.mode == "approved_domains_only" and recipient_domain not in policy.approved_domains:
        raise APIError(
            403,
            "Recipient domain not approved",
            "An organization administrator must approve this exact recipient domain before sharing",
        )


async def _refresh_affected_analysis_share_state(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    analysis_ids: set[uuid.UUID],
    now: datetime,
) -> None:
    for analysis_id in sorted(analysis_ids, key=str):
        analysis_result = await db.execute(
            select(Analysis)
            .where(Analysis.id == analysis_id, Analysis.org_id == org_id)
            .with_for_update()
        )
        analysis = analysis_result.scalar_one_or_none()
        if analysis is None:
            continue
        count_result = await db.execute(
            select(
                func.count(ExternalReportGrant.id),
                func.max(ExternalReportGrant.expires_at),
            ).where(
                ExternalReportGrant.analysis_id == analysis_id,
                ExternalReportGrant.org_id == org_id,
                ExternalReportGrant.revoked_at.is_(None),
                ExternalReportGrant.invitation_sent_at.is_not(None),
                ExternalReportGrant.expires_at > now,
                ExternalReportGrant.view_count < ExternalReportGrant.max_views,
            )
        )
        active_count, active_until = count_result.one()
        analysis.share_active_grant_count = int(active_count or 0)
        analysis.share_active_until = active_until


async def update_external_sharing_policy(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    request: ExternalSharingPolicyUpdateRequest,
    now_fn=datetime.now,
) -> ExternalSharingPolicyUpdate:
    """Lock the org, persist policy, and revoke disallowed access atomically."""
    organization = await _load_organization(db, org_id=org_id, for_update=True)
    current = _policy_from_organization(organization)
    if current.version != request.expected_version:
        raise APIError(
            409,
            "Policy version conflict",
            "External sharing policy changed in another administrator session; "
            "reload before retrying",
        )

    now = now_fn(UTC)
    impacted_grants: tuple[PolicyRevokedGrant, ...] = ()
    if request.mode == "approved_domains_only":
        domain_filter = (
            ExternalReportGrant.recipient_domain.not_in(request.approved_domains)
            if request.approved_domains
            else true()
        )
        candidate_result = await db.execute(
            select(
                ExternalReportGrant.id,
                ExternalReportGrant.analysis_id,
                ExternalReportGrant.recipient_domain,
                ExternalReportGrant.invitation_sent_at,
            )
            .where(
                ExternalReportGrant.org_id == org_id,
                ExternalReportGrant.revoked_at.is_(None),
                ExternalReportGrant.expires_at > now,
                ExternalReportGrant.view_count < ExternalReportGrant.max_views,
                or_(
                    and_(
                        ExternalReportGrant.delivery_state == "active",
                        ExternalReportGrant.invitation_sent_at.is_not(None),
                    ),
                    and_(
                        ExternalReportGrant.delivery_state.in_(
                            (
                                "prepared",
                                "dispatching",
                                "provider_accepted",
                                "outcome_unknown",
                            )
                        ),
                        ExternalReportGrant.invitation_sent_at.is_(None),
                    ),
                ),
                domain_filter,
            )
            .with_for_update()
        )
        impacted_grants = tuple(
            PolicyRevokedGrant(
                id=row.id,
                analysis_id=row.analysis_id,
                recipient_domain=row.recipient_domain,
                invitation_sent_at=row.invitation_sent_at,
            )
            for row in candidate_result.all()
        )
    impact = ExternalSharingPolicyImpact(
        active_grant_count=sum(grant.invitation_sent_at is not None for grant in impacted_grants),
        pending_grant_count=sum(grant.invitation_sent_at is None for grant in impacted_grants),
        total_grant_count=len(impacted_grants),
    )
    proposal_digest = _proposal_digest(
        org_id=org_id,
        current_version=current.version,
        mode=request.mode,
        approved_domains=request.approved_domains,
        impacted_grants=impacted_grants,
    )
    if impacted_grants and not request.confirm_destructive:
        return ExternalSharingPolicyUpdate(
            previous_policy=current,
            policy=ExternalSharingPolicy(
                mode=request.mode,
                approved_domains=request.approved_domains,
                version=current.version,
            ),
            impacted_grants=impacted_grants,
            impact=impact,
            proposal_digest=proposal_digest,
            confirmation_required=True,
        )
    if request.confirm_destructive and (
        request.proposal_digest is None
        or not compare_digest(request.proposal_digest, proposal_digest)
    ):
        raise APIError(
            409,
            "Policy proposal changed",
            "The current grant impact no longer matches the reviewed proposal; "
            "reload and review again",
        )

    if request.mode == "approved_domains_only":
        if impacted_grants:
            await db.execute(
                update(ExternalReportGrant)
                .where(
                    ExternalReportGrant.org_id == org_id,
                    ExternalReportGrant.id.in_(tuple(grant.id for grant in impacted_grants)),
                )
                .values(
                    revoked_at=now,
                    delivery_state=case(
                        (
                            ExternalReportGrant.invitation_sent_at.is_(None),
                            "cancelled",
                        ),
                        else_=ExternalReportGrant.delivery_state,
                    ),
                    delivery_terminal_at=case(
                        (
                            ExternalReportGrant.invitation_sent_at.is_(None),
                            now,
                        ),
                        else_=ExternalReportGrant.delivery_terminal_at,
                    ),
                    delivery_terminal_reason=case(
                        (
                            ExternalReportGrant.invitation_sent_at.is_(None),
                            "policy",
                        ),
                        else_=ExternalReportGrant.delivery_terminal_reason,
                    ),
                    delivery_token_ciphertext=None,
                    verification_code_hash=None,
                    verification_expires_at=None,
                    verification_sent_at=None,
                    verification_consumed_at=None,
                    access_secret_hash=None,
                    access_expires_at=None,
                )
            )
        await _refresh_affected_analysis_share_state(
            db,
            org_id=org_id,
            analysis_ids={grant.analysis_id for grant in impacted_grants},
            now=now,
        )

    next_version = current.version + 1
    organization.external_sharing_policy_mode = request.mode
    organization.external_sharing_approved_domains = request.approved_domains
    organization.external_sharing_policy_version = next_version
    policy = ExternalSharingPolicy(
        mode=request.mode,
        approved_domains=request.approved_domains,
        version=next_version,
    )

    return ExternalSharingPolicyUpdate(
        previous_policy=current,
        policy=policy,
        impacted_grants=impacted_grants,
        impact=impact,
        proposal_digest=proposal_digest,
        confirmation_required=False,
    )


__all__ = [
    "ExternalSharingPolicyUpdate",
    "PolicyRevokedGrant",
    "get_external_sharing_policy",
    "require_recipient_domain_allowed",
    "update_external_sharing_policy",
]
