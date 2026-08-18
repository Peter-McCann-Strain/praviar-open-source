"""Contracts for external-source identity without invented public mailboxes."""

from __future__ import annotations

import pytest

from praviar_pipeline.clients.http_identity import (
    normalize_source_contact_email,
    optional_contact_parameter,
    source_user_agent,
)


def test_source_user_agent_has_no_unconfigured_mailbox() -> None:
    user_agent = source_user_agent("")

    assert user_agent == "PraviarResearchPreview/0.1.0"
    assert "@" not in user_agent
    assert optional_contact_parameter("") == {}


def test_source_identity_uses_explicit_operator_contact() -> None:
    user_agent = source_user_agent("operator@example.org")

    assert user_agent.endswith("contact=operator@example.org)")
    assert optional_contact_parameter("operator@example.org") == {"email": "operator@example.org"}


@pytest.mark.parametrize(
    "contact_email",
    [
        "x)@example.org",
        "x(@example.org",
        "x\\@example.org",
        "x\x00@example.org",
        f"{'a' * 65}@example.org",
    ],
)
def test_source_identity_rejects_header_unsafe_mailboxes(contact_email: str) -> None:
    with pytest.raises(ValueError, match="source_contact_email"):
        normalize_source_contact_email(contact_email)
    with pytest.raises(ValueError, match="source_contact_email"):
        source_user_agent(contact_email)
