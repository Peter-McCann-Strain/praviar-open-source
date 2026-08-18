"""Typed Stripe metadata contract tests."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from api.schemas.billing import CreditPackId, PlanTier
from api.services.billing_metadata import (
    CHECKOUT_METADATA_SCHEMA_VERSION,
    CHECKOUT_PURPOSE_CREDIT_PACK,
    CHECKOUT_PURPOSE_SUBSCRIPTION,
    build_checkout_session_metadata,
    build_credit_pack_checkout_metadata,
    is_credit_pack_checkout_metadata,
    parse_checkout_session_metadata,
    parse_credit_pack_checkout_metadata,
)


def test_checkout_session_metadata_round_trips_as_strings() -> None:
    org_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    user_id = uuid.UUID("22222222-2222-2222-2222-222222222222")

    metadata = build_checkout_session_metadata(
        org_id=org_id,
        user_id=user_id,
        plan_id=PlanTier.PRO,
    )

    assert metadata == {
        "schema_version": CHECKOUT_METADATA_SCHEMA_VERSION,
        "purpose": CHECKOUT_PURPOSE_SUBSCRIPTION,
        "org_id": str(org_id),
        "user_id": str(user_id),
        "plan_id": "pro",
    }
    parsed = parse_checkout_session_metadata(metadata)
    assert parsed.org_id == org_id
    assert parsed.user_id == user_id
    assert parsed.plan_id == PlanTier.PRO


@pytest.mark.parametrize("plan_id", [PlanTier.FREE, PlanTier.ENTERPRISE])
def test_checkout_session_metadata_rejects_non_checkout_plans(plan_id: PlanTier) -> None:
    with pytest.raises(ValidationError, match="starter or pro"):
        build_checkout_session_metadata(
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            plan_id=plan_id,
        )


def test_checkout_session_metadata_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        parse_checkout_session_metadata(
            {
                "schema_version": CHECKOUT_METADATA_SCHEMA_VERSION,
                "purpose": CHECKOUT_PURPOSE_SUBSCRIPTION,
                "org_id": str(uuid.uuid4()),
                "user_id": str(uuid.uuid4()),
                "plan_id": "starter",
                "plan": "starter",
            }
        )


def test_credit_pack_checkout_metadata_round_trips_as_strings() -> None:
    org_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    user_id = uuid.UUID("22222222-2222-2222-2222-222222222222")

    metadata = build_credit_pack_checkout_metadata(
        org_id=org_id,
        user_id=user_id,
        credit_pack_id=CreditPackId.PORTFOLIO_5,
        credits=5,
    )

    assert metadata == {
        "schema_version": CHECKOUT_METADATA_SCHEMA_VERSION,
        "purpose": CHECKOUT_PURPOSE_CREDIT_PACK,
        "org_id": str(org_id),
        "user_id": str(user_id),
        "credit_pack_id": "portfolio_5",
        "credits": "5",
    }
    parsed = parse_credit_pack_checkout_metadata(metadata)
    assert parsed.org_id == org_id
    assert parsed.user_id == user_id
    assert parsed.credit_pack_id == CreditPackId.PORTFOLIO_5
    assert parsed.credits == 5
    assert is_credit_pack_checkout_metadata(metadata) is True
    assert is_credit_pack_checkout_metadata({"purpose": "subscription_checkout"}) is False
