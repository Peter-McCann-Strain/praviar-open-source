"""Typed Stripe metadata contracts shared by checkout and webhooks."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.schemas.billing import CreditPackId, PlanTier

CHECKOUT_METADATA_SCHEMA_VERSION = "checkout.session.v1"
CHECKOUT_PURPOSE_CREDIT_PACK = "credit_pack_checkout"
CHECKOUT_PURPOSE_SUBSCRIPTION = "subscription_checkout"


class CheckoutSessionMetadata(BaseModel):
    """Metadata attached to Stripe Checkout sessions and required by webhooks."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["checkout.session.v1"] = "checkout.session.v1"
    purpose: Literal["subscription_checkout"] = "subscription_checkout"
    org_id: uuid.UUID
    user_id: uuid.UUID
    plan_id: PlanTier = Field(description="Paid plan requested by checkout")

    @field_validator("plan_id")
    @classmethod
    def paid_checkout_plan_only(cls, value: PlanTier) -> PlanTier:
        if value not in {PlanTier.STARTER, PlanTier.PRO}:
            raise ValueError("checkout metadata plan_id must be starter or pro")
        return value

    def to_stripe_metadata(self) -> dict[str, str]:
        """Serialize as Stripe's string-only metadata dictionary."""
        return {
            "schema_version": self.schema_version,
            "purpose": self.purpose,
            "org_id": str(self.org_id),
            "user_id": str(self.user_id),
            "plan_id": self.plan_id.value,
        }


class CreditPackCheckoutMetadata(BaseModel):
    """Metadata attached to one-time analysis credit-pack Checkout sessions."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["checkout.session.v1"] = "checkout.session.v1"
    purpose: Literal["credit_pack_checkout"] = "credit_pack_checkout"
    org_id: uuid.UUID
    user_id: uuid.UUID
    credit_pack_id: CreditPackId = Field(description="Credit pack requested by checkout")
    credits: int = Field(gt=0, description="Number of analysis credits purchased")

    def to_stripe_metadata(self) -> dict[str, str]:
        """Serialize as Stripe's string-only metadata dictionary."""
        return {
            "schema_version": self.schema_version,
            "purpose": self.purpose,
            "org_id": str(self.org_id),
            "user_id": str(self.user_id),
            "credit_pack_id": self.credit_pack_id.value,
            "credits": str(self.credits),
        }


def build_checkout_session_metadata(
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    plan_id: PlanTier,
) -> dict[str, str]:
    return CheckoutSessionMetadata(
        org_id=org_id,
        user_id=user_id,
        plan_id=plan_id,
    ).to_stripe_metadata()


def build_credit_pack_checkout_metadata(
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    credit_pack_id: CreditPackId,
    credits: int,
) -> dict[str, str]:
    return CreditPackCheckoutMetadata(
        org_id=org_id,
        user_id=user_id,
        credit_pack_id=credit_pack_id,
        credits=credits,
    ).to_stripe_metadata()


def parse_checkout_session_metadata(
    metadata: Mapping[str, Any],
) -> CheckoutSessionMetadata:
    return CheckoutSessionMetadata.model_validate(dict(metadata))


def parse_credit_pack_checkout_metadata(
    metadata: Mapping[str, Any],
) -> CreditPackCheckoutMetadata:
    return CreditPackCheckoutMetadata.model_validate(dict(metadata))


def is_credit_pack_checkout_metadata(metadata: Mapping[str, Any]) -> bool:
    return metadata.get("purpose") == CHECKOUT_PURPOSE_CREDIT_PACK
