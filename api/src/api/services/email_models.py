"""Shared models for transactional email delivery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class DeliveryResult:
    """Result of an email send attempt."""

    success: bool
    message_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class DeliverySubmissionResult:
    """Result of one non-retried provider submission.

    ``outcome_unknown`` means bytes may have reached the provider and must
    never be submitted again without a provider-side lookup primitive.
    """

    status: Literal["accepted", "rejected", "outcome_unknown"]
    message_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class DeliveryLookupResult:
    """Validated Postmark outbound lookup for one submission metadata digest."""

    status: Literal["found", "not_found", "alert", "unavailable"]
    message_id: str | None = None
    detail: str | None = None
