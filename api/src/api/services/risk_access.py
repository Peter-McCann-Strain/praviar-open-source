"""Role-aware access policy for restricted risk conclusions."""

from __future__ import annotations

from api.config import get_settings
from api.db.models import UserRole

COUNSEL_ROLES = frozenset({UserRole.ADMIN, UserRole.ATTORNEY})
RISK_RESTRICTION_SUMMARY = (
    "Risk ratings and clearance conclusions are restricted to attorney-role users. "
    "Contact your organization's patent counsel for the governed assessment."
)


def risk_ratings_restricted_for_role(role: UserRole | str | None) -> bool:
    """Return whether the configured attorney-only risk gate applies to ``role``."""
    if not getattr(
        get_settings(),
        "require_attorney_role_for_risk_ratings",
        False,
    ):
        return False

    try:
        normalized_role = role if isinstance(role, UserRole) else UserRole(str(role or ""))
    except ValueError:
        return True
    return normalized_role not in COUNSEL_ROLES
