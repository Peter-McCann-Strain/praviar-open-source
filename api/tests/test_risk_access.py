from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.db.models import UserRole
from api.services.risk_access import risk_ratings_restricted_for_role


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.ATTORNEY, "admin", "attorney"])
def test_counsel_roles_retain_risk_access(role):
    with patch(
        "api.services.risk_access.get_settings",
        return_value=SimpleNamespace(require_attorney_role_for_risk_ratings=True),
    ):
        assert risk_ratings_restricted_for_role(role) is False


@pytest.mark.parametrize(
    "role",
    [UserRole.SCIENTIST, UserRole.CLIENT, "scientist", "client", None, "unknown"],
)
def test_non_counsel_and_unknown_roles_fail_closed(role):
    with patch(
        "api.services.risk_access.get_settings",
        return_value=SimpleNamespace(require_attorney_role_for_risk_ratings=True),
    ):
        assert risk_ratings_restricted_for_role(role) is True


def test_disabled_policy_keeps_existing_role_access():
    with patch(
        "api.services.risk_access.get_settings",
        return_value=SimpleNamespace(require_attorney_role_for_risk_ratings=False),
    ):
        assert risk_ratings_restricted_for_role(UserRole.SCIENTIST) is False
