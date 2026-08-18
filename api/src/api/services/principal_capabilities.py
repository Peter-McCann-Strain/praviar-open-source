"""Derive one authoritative application-role capability snapshot."""

from __future__ import annotations

from api.config import get_settings
from api.db.models import User
from api.deps import PERMISSION_MATRIX
from api.schemas.principal import PrincipalCapabilitiesResponse
from api.services.comments_crud import ASSIGNER_ROLES, REVIEW_QUEUE_ROLES
from api.services.risk_access import risk_ratings_restricted_for_role

REVIEW_RESOLVE_ROLES = PERMISSION_MATRIX["reviewer_decision.create"]
PATENT_WORKSPACE_ROLES = PERMISSION_MATRIX["report.view_full"]


def build_principal_capabilities(user: User) -> PrincipalCapabilitiesResponse:
    """Return capabilities that mirror server authorization and policy gates."""
    role = user.role
    risk_restricted = risk_ratings_restricted_for_role(role)
    can_export_report = role in PERMISSION_MATRIX["report.export"] and not risk_restricted
    can_share_report = role in PERMISSION_MATRIX["report.share"]

    return PrincipalCapabilitiesResponse(
        role=role.value,
        can_create_analysis=role in PERMISSION_MATRIX["analysis.create"],
        can_view_patents=role in PATENT_WORKSPACE_ROLES,
        can_manage_monitors=role in PERMISSION_MATRIX["monitor.manage"],
        can_view_review_queue=role in REVIEW_QUEUE_ROLES,
        can_assign_review=role in ASSIGNER_ROLES,
        can_resolve_review=role in REVIEW_RESOLVE_ROLES,
        can_escalate_review=role in ASSIGNER_ROLES,
        can_create_batch=role in PERMISSION_MATRIX["batch.create"],
        can_manage_config=role in PERMISSION_MATRIX["config.manage"],
        can_export_report=can_export_report,
        can_share_report=can_share_report,
        can_deliver_report=can_export_report or can_share_report,
        can_view_billing=role in PERMISSION_MATRIX["billing.view"],
        can_manage_billing=role in PERMISSION_MATRIX["billing.manage"],
        can_manage_api_keys=role in PERMISSION_MATRIX["apikey.manage"],
        can_view_platform_admin=role in PERMISSION_MATRIX["admin.view"],
        risk_ratings_restricted=risk_restricted,
        api_key_report_export_scope_available=(
            not get_settings().require_attorney_role_for_risk_ratings
        ),
    )
