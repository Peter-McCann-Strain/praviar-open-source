"""Authoritative organization setup readiness assembly."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import (
    Analysis,
    AnalysisReviewStatus,
    AnalysisStatus,
    ExportJob,
    ExportStatus,
    Organization,
    ReviewStatus,
    User,
    UserRole,
)
from api.errors import APIError
from api.schemas.configs import SetOrgDefaultsRequest
from api.schemas.setup_readiness import (
    SetupReadinessItem,
    SetupReadinessItemId,
    SetupReadinessItemStatus,
    SetupReadinessOverallStatus,
    SetupReadinessResponse,
)
from api.services.billing_queries import (
    AnalysisCapacitySnapshot,
    get_available_analysis_capacity,
)
from api.services.configs import org_default_config_from_settings
from api.services.risk_access import risk_ratings_restricted_for_role
from api.services.sso_freshness import sso_status_is_fresh


def _item(
    *,
    item_id: SetupReadinessItemId,
    label: str,
    description: str,
    status: SetupReadinessItemStatus,
    owner: str,
    recovery_label: str,
    recovery_href: str | None,
    evidence: str,
) -> SetupReadinessItem:
    return SetupReadinessItem(
        id=item_id,
        label=label,
        description=description,
        status=status,
        owner=owner,
        recovery_label=recovery_label,
        recovery_href=recovery_href,
        evidence=evidence,
    )


def _evidence_policy_is_configured(default_config: dict[str, Any]) -> bool:
    """Require validated source, jurisdiction, and review-limit defaults."""
    try:
        normalized = SetOrgDefaultsRequest.model_validate(default_config).normalized_config()
    except (ValidationError, ValueError):
        return False

    jurisdictions = normalized.get("search_jurisdictions")
    valid_jurisdictions = (
        isinstance(jurisdictions, list)
        and bool(jurisdictions)
        and all(isinstance(code, str) and re.fullmatch(r"[A-Z]{2}", code) for code in jurisdictions)
    )
    source_enabled = any(
        normalized.get(key) is True
        for key in (
            "enable_pubchem",
            "enable_bigquery",
            "enable_surechembl",
            "enable_patcid",
        )
    )
    return bool(valid_jurisdictions and source_enabled and normalized.get("max_analysis_patents"))


def _primary_us_status_collection_readiness() -> Any:
    """Return deployment capability for mandatory US primary-status evidence."""
    from praviar_pipeline.clients.primary_legal_status import (
        primary_legal_status_setup_readiness,
    )
    from praviar_pipeline.config import get_settings as get_pipeline_settings

    return primary_legal_status_setup_readiness(get_pipeline_settings())


@dataclass(frozen=True)
class _PersistedSetupEvidence:
    collaborator_count: int
    review_capable_count: int
    analysis_count: int
    completed_analysis_count: int
    has_review_handoff: bool
    has_share_or_export: bool


@dataclass(frozen=True)
class _SetupContext:
    user: User
    evidence: _PersistedSetupEvidence
    primary_status_readiness: Any
    evidence_policy_valid: bool
    evidence_policy_configured: bool
    sso_required: bool
    sso_status_fresh: bool
    sso_configured: bool
    sso_domain_count: int
    available_capacity: int
    identity_complete: bool
    collaborators_complete: bool
    is_admin: bool
    can_manage_evidence_policy: bool
    can_create_analysis: bool
    can_record_review: bool
    can_deliver_report: bool


async def _load_organization(db: AsyncSession, *, user: User) -> Organization:
    result = await db.execute(select(Organization).where(Organization.id == user.org_id))
    organization = result.scalar_one_or_none()
    if organization is None:
        raise APIError(404, "Not Found", "Organization not found")
    return organization


async def _load_persisted_setup_evidence(
    db: AsyncSession,
    *,
    user: User,
) -> _PersistedSetupEvidence:
    result = await db.execute(
        select(
            select(func.count(User.id))
            .where(
                User.org_id == user.org_id,
                User.membership_active.is_(True),
                User.membership_deleted_at.is_(None),
                User.membership_permission_denied_at.is_(None),
            )
            .scalar_subquery()
            .label("collaborator_count"),
            select(func.count(User.id))
            .where(
                User.org_id == user.org_id,
                User.membership_active.is_(True),
                User.membership_deleted_at.is_(None),
                User.membership_permission_denied_at.is_(None),
                User.role.in_((UserRole.ADMIN, UserRole.ATTORNEY)),
            )
            .scalar_subquery()
            .label("review_capable_count"),
            select(func.count(Analysis.id))
            .where(Analysis.org_id == user.org_id)
            .scalar_subquery()
            .label("analysis_count"),
            select(func.count(Analysis.id))
            .where(
                Analysis.org_id == user.org_id,
                Analysis.status == AnalysisStatus.COMPLETED,
                Analysis.report_data.is_not(None),
            )
            .scalar_subquery()
            .label("completed_analysis_count"),
            exists(
                select(AnalysisReviewStatus.id)
                .join(Analysis, Analysis.id == AnalysisReviewStatus.analysis_id)
                .where(
                    AnalysisReviewStatus.org_id == user.org_id,
                    AnalysisReviewStatus.status == ReviewStatus.APPROVED,
                    AnalysisReviewStatus.reviewed_at.is_not(None),
                    Analysis.org_id == user.org_id,
                    Analysis.status == AnalysisStatus.COMPLETED,
                    Analysis.report_data.is_not(None),
                    Analysis.flagged_for_review.is_(False),
                )
            ).label("has_review_handoff"),
            exists(
                select(Analysis.id).where(
                    Analysis.org_id == user.org_id,
                    Analysis.status == AnalysisStatus.COMPLETED,
                    Analysis.report_data.is_not(None),
                    Analysis.share_active_grant_count > 0,
                    Analysis.share_active_until > datetime.now(UTC),
                )
            ).label("has_share"),
            exists(
                select(ExportJob.id)
                .join(Analysis, Analysis.id == ExportJob.analysis_id)
                .where(
                    ExportJob.org_id == user.org_id,
                    ExportJob.status == ExportStatus.COMPLETED,
                    Analysis.org_id == user.org_id,
                    Analysis.status == AnalysisStatus.COMPLETED,
                    Analysis.report_data.is_not(None),
                )
            ).label("has_export"),
        )
    )
    evidence = result.one()
    return _PersistedSetupEvidence(
        collaborator_count=int(evidence.collaborator_count or 0),
        review_capable_count=int(evidence.review_capable_count or 0),
        analysis_count=int(evidence.analysis_count or 0),
        completed_analysis_count=int(evidence.completed_analysis_count or 0),
        has_review_handoff=bool(evidence.has_review_handoff),
        has_share_or_export=bool(evidence.has_share or evidence.has_export),
    )


def _build_setup_context(
    *,
    organization: Organization,
    user: User,
    capacity: AnalysisCapacitySnapshot,
    evidence: _PersistedSetupEvidence,
) -> _SetupContext:
    default_config = org_default_config_from_settings(organization.settings or {})
    evidence_policy_valid = _evidence_policy_is_configured(default_config)
    configured_jurisdictions = default_config.get("search_jurisdictions", [])
    primary_us_status_required = (
        isinstance(configured_jurisdictions, list) and "US" in configured_jurisdictions
    )
    primary_status_readiness = (
        _primary_us_status_collection_readiness() if primary_us_status_required else None
    )
    primary_us_status_ready = bool(
        primary_status_readiness is None or primary_status_readiness.ready
    )
    sso_required = organization.sso_required is True
    sso_status_fresh = sso_status_is_fresh(
        available=organization.sso_status_available is True,
        last_synced_at=organization.sso_last_synced_at,
    )
    sso_configured = bool(
        sso_status_fresh and organization.sso_enabled and organization.sso_domains
    )
    can_export_report = user.role in (
        UserRole.ADMIN,
        UserRole.ATTORNEY,
        UserRole.SCIENTIST,
    ) and not risk_ratings_restricted_for_role(user.role)
    can_share_report = user.role in (UserRole.ADMIN, UserRole.ATTORNEY)
    return _SetupContext(
        user=user,
        evidence=evidence,
        primary_status_readiness=primary_status_readiness,
        evidence_policy_valid=evidence_policy_valid,
        evidence_policy_configured=bool(evidence_policy_valid and primary_us_status_ready),
        sso_required=sso_required,
        sso_status_fresh=sso_status_fresh,
        sso_configured=sso_configured,
        sso_domain_count=len(organization.sso_domains),
        available_capacity=capacity.available,
        identity_complete=bool(
            organization.name.strip()
            and organization.clerk_org_id.strip()
            and user.email.strip()
            and user.clerk_user_id.strip()
        ),
        collaborators_complete=(
            evidence.collaborator_count >= 2 and evidence.review_capable_count >= 1
        ),
        is_admin=user.role == UserRole.ADMIN,
        can_manage_evidence_policy=user.role in (UserRole.ADMIN, UserRole.ATTORNEY),
        can_create_analysis=user.role in (UserRole.ADMIN, UserRole.ATTORNEY, UserRole.SCIENTIST),
        can_record_review=user.role in (UserRole.ADMIN, UserRole.ATTORNEY),
        can_deliver_report=can_export_report or can_share_report,
    )


def _identity_item(context: _SetupContext) -> SetupReadinessItem:
    return _item(
        item_id=SetupReadinessItemId.IDENTITY,
        label="Identity and organization",
        description="Confirm the signed-in user, tenant workspace, and role boundary.",
        status=(
            SetupReadinessItemStatus.COMPLETE
            if context.identity_complete
            else SetupReadinessItemStatus.ACTION_REQUIRED
        ),
        owner="Workspace administrator",
        recovery_label=(
            "Review workspace settings" if context.is_admin else "Ask a workspace administrator"
        ),
        recovery_href="/settings" if context.is_admin else None,
        evidence=(
            "Authenticated identity and organization membership are persisted; "
            f"role {context.user.role.value}."
            if context.identity_complete
            else "The persisted identity or organization record is incomplete."
        ),
    )


def _collaborators_item(context: _SetupContext) -> SetupReadinessItem:
    evidence = context.evidence
    return _item(
        item_id=SetupReadinessItemId.COLLABORATORS,
        label="Collaborators and roles",
        description="Add a second collaborator and retain an administrator or attorney.",
        status=(
            SetupReadinessItemStatus.COMPLETE
            if context.collaborators_complete
            else SetupReadinessItemStatus.ACTION_REQUIRED
        ),
        owner="Workspace administrator",
        recovery_label=(
            "Manage team roles" if context.is_admin else "Ask a workspace administrator"
        ),
        recovery_href="/admin?tab=users" if context.is_admin else None,
        evidence=(
            f"{evidence.collaborator_count} members; "
            f"{evidence.review_capable_count} can administer or review."
        ),
    )


def _evidence_policy_item(context: _SetupContext) -> SetupReadinessItem:
    readiness = context.primary_status_readiness
    if context.evidence_policy_configured:
        evidence = (
            "Source, jurisdiction, and review-limit defaults are validated and "
            "persisted; required US primary-status collection and signing are ready."
        )
    elif context.evidence_policy_valid and readiness is not None and not readiness.ready:
        evidence = "Required US primary-status evidence is not operational: " + " ".join(
            readiness.failure_reasons
        )
    else:
        evidence = "No complete validated source, jurisdiction, and review-limit default was found."
    return _item(
        item_id=SetupReadinessItemId.EVIDENCE_POLICY,
        label="Default evidence policy",
        description="Set enabled patent sources, jurisdictions, and review limits.",
        status=(
            SetupReadinessItemStatus.COMPLETE
            if context.evidence_policy_configured
            else SetupReadinessItemStatus.ACTION_REQUIRED
        ),
        owner="Attorney or workspace administrator",
        recovery_label=(
            "Set analysis defaults"
            if context.can_manage_evidence_policy
            else "Ask an attorney or workspace administrator"
        ),
        recovery_href="/config" if context.can_manage_evidence_policy else None,
        evidence=evidence,
    )


def _billing_item(context: _SetupContext) -> SetupReadinessItem:
    return _item(
        item_id=SetupReadinessItemId.BILLING,
        label="Billing capacity",
        description="Keep at least one analysis slot or report credit available.",
        status=(
            SetupReadinessItemStatus.COMPLETE
            if context.available_capacity > 0
            else SetupReadinessItemStatus.ACTION_REQUIRED
        ),
        owner="Workspace administrator",
        recovery_label=(
            "Review billing capacity" if context.is_admin else "Ask a workspace administrator"
        ),
        recovery_href="/billing" if context.is_admin else None,
        evidence=f"{context.available_capacity} analysis slot(s) currently available.",
    )


def _sso_item(context: _SetupContext) -> SetupReadinessItem:
    if not context.sso_required:
        status = SetupReadinessItemStatus.NOT_REQUIRED
        evidence = "SSO is not required by the persisted workspace policy."
    elif context.sso_configured:
        status = SetupReadinessItemStatus.COMPLETE
        evidence = f"SSO is enabled for {context.sso_domain_count} enrolled domain(s)."
    else:
        status = SetupReadinessItemStatus.ACTION_REQUIRED
        evidence = (
            "Live SSO status is unavailable or stale; cached identity data "
            "does not satisfy workspace readiness."
            if not context.sso_status_fresh
            else "Workspace policy requires SSO, but no enabled domain was found."
        )
    return _item(
        item_id=SetupReadinessItemId.SSO,
        label="Single sign-on",
        description="Complete SSO enrollment when required by workspace policy.",
        status=status,
        owner="Workspace administrator",
        recovery_label=(
            "Review sign-on controls" if context.is_admin else "Ask a workspace administrator"
        ),
        recovery_href="/settings#single-sign-on" if context.is_admin else None,
        evidence=evidence,
    )


def _first_analysis_item(context: _SetupContext) -> SetupReadinessItem:
    evidence = context.evidence
    completed = evidence.completed_analysis_count > 0
    return _item(
        item_id=SetupReadinessItemId.FIRST_ANALYSIS,
        label="First analysis",
        description="Run the first compound through the governed FTO workflow.",
        status=(
            SetupReadinessItemStatus.COMPLETE
            if completed
            else SetupReadinessItemStatus.ACTION_REQUIRED
        ),
        owner="Analysis team",
        recovery_label=(
            "Start an analysis" if context.can_create_analysis else "Ask the analysis team"
        ),
        recovery_href="/analyses/new" if context.can_create_analysis else None,
        evidence=(
            f"{evidence.completed_analysis_count} completed organization-scoped "
            "analysis record(s) found."
            if completed
            else (
                f"No completed analysis found; {evidence.analysis_count} total "
                "analysis record(s) exist."
            )
        ),
    )


def _review_handoff_item(context: _SetupContext) -> SetupReadinessItem:
    evidence = context.evidence
    has_completed_analysis = evidence.completed_analysis_count > 0
    return _item(
        item_id=SetupReadinessItemId.REVIEW_HANDOFF,
        label="Counsel review approval",
        description="Record approved report-level counsel review before relying on outputs.",
        status=(
            SetupReadinessItemStatus.COMPLETE
            if evidence.has_review_handoff
            else (
                SetupReadinessItemStatus.ACTION_REQUIRED
                if has_completed_analysis
                else SetupReadinessItemStatus.BLOCKED
            )
        ),
        owner="Reviewer or counsel",
        recovery_label=(
            "Open review queue" if context.can_record_review else "Ask a reviewer or counsel"
        ),
        recovery_href="/reviews" if context.can_record_review else None,
        evidence=(
            "An approved, timestamped review for a completed report was found."
            if evidence.has_review_handoff
            else (
                "A completed analysis is available, but no approved counsel review is recorded."
                if has_completed_analysis
                else "Complete an analysis before recording the review handoff."
            )
        ),
    )


def _share_export_item(context: _SetupContext) -> SetupReadinessItem:
    evidence = context.evidence
    has_completed_analysis = evidence.completed_analysis_count > 0
    return _item(
        item_id=SetupReadinessItemId.SHARE_EXPORT,
        label="Share or export",
        description="Prove the governed delivery path with a persisted share or completed export.",
        status=(
            SetupReadinessItemStatus.COMPLETE
            if evidence.has_share_or_export
            else (
                SetupReadinessItemStatus.ACTION_REQUIRED
                if has_completed_analysis
                else SetupReadinessItemStatus.BLOCKED
            )
        ),
        owner="Attorney or authorized delivery owner",
        recovery_label=(
            "Open completed analyses"
            if context.can_deliver_report
            else "Ask an attorney or authorized delivery owner"
        ),
        recovery_href="/analyses?status=completed" if context.can_deliver_report else None,
        evidence=(
            "A persisted share link or completed export was found."
            if evidence.has_share_or_export
            else (
                "A completed analysis exists, but delivery evidence has not been recorded."
                if has_completed_analysis
                else "Complete an analysis before verifying share or export delivery."
            )
        ),
    )


def _build_readiness_items(context: _SetupContext) -> list[SetupReadinessItem]:
    return [
        _identity_item(context),
        _collaborators_item(context),
        _evidence_policy_item(context),
        _billing_item(context),
        _sso_item(context),
        _first_analysis_item(context),
        _review_handoff_item(context),
        _share_export_item(context),
    ]


async def get_setup_readiness(
    db: AsyncSession,
    *,
    user: User,
) -> SetupReadinessResponse:
    """Build a fail-closed setup snapshot from tenant-scoped persisted records."""
    organization = await _load_organization(db, user=user)
    capacity = await get_available_analysis_capacity(db, org=organization)
    evidence = await _load_persisted_setup_evidence(db, user=user)
    context = _build_setup_context(
        organization=organization,
        user=user,
        capacity=capacity,
        evidence=evidence,
    )
    items = _build_readiness_items(context)

    applicable_items = [
        item for item in items if item.status != SetupReadinessItemStatus.NOT_REQUIRED
    ]
    completed_items = sum(
        item.status == SetupReadinessItemStatus.COMPLETE for item in applicable_items
    )
    overall_status = (
        SetupReadinessOverallStatus.READY
        if completed_items == len(applicable_items)
        else SetupReadinessOverallStatus.ACTION_REQUIRED
    )
    return SetupReadinessResponse(
        overall_status=overall_status,
        current_user_role=user.role.value,
        completed_items=completed_items,
        applicable_items=len(applicable_items),
        items=items,
        observed_at=datetime.now(UTC),
    )
