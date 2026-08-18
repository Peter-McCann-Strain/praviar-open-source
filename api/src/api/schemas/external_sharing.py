"""Typed organization policy for recipient-bound external sharing."""

from __future__ import annotations

from typing import Literal

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ExternalSharingPolicyMode = Literal["open", "approved_domains_only"]


def normalize_external_sharing_domain(value: str) -> str:
    """Return one exact lower-case IDNA domain, never a wildcard or suffix rule."""
    candidate = value.strip().rstrip(".").casefold()
    if (
        not candidate
        or "*" in candidate
        or candidate.startswith(".")
        or "://" in candidate
        or "@" in candidate
        or "/" in candidate
        or "\\" in candidate
    ):
        raise ValueError("Enter an exact domain without wildcards, email addresses, or URLs")
    try:
        validated = validate_email(
            f"policy@{candidate}",
            check_deliverability=False,
            allow_smtputf8=False,
        )
        normalized = (validated.ascii_domain or "").casefold()
    except EmailNotValidError as exc:
        raise ValueError("Enter a valid exact domain") from exc
    if len(normalized) > 253 or "." not in normalized:
        raise ValueError("Enter a fully qualified domain")
    return normalized


class ExternalSharingPolicyValues(BaseModel):
    """Normalized exact-domain policy values."""

    model_config = ConfigDict(extra="forbid")

    mode: ExternalSharingPolicyMode = "approved_domains_only"
    approved_domains: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("approved_domains")
    @classmethod
    def normalize_domains(cls, values: list[str]) -> list[str]:
        return sorted({normalize_external_sharing_domain(value) for value in values})

    @model_validator(mode="after")
    def open_mode_has_no_allowlist(self) -> ExternalSharingPolicyValues:
        if self.mode == "open" and self.approved_domains:
            raise ValueError("Open sharing cannot include approved domains")
        return self


class ExternalSharingPolicy(ExternalSharingPolicyValues):
    """Versioned organization policy returned by the server."""

    version: int = Field(default=1, ge=1)


class ExternalSharingPolicyUpdateRequest(ExternalSharingPolicyValues):
    """Optimistic, explicitly confirmed policy mutation."""

    expected_version: int = Field(ge=1)
    confirm_destructive: bool
    proposal_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ExternalSharingPolicyImpact(BaseModel):
    """Authoritative current grants affected by one normalized proposal."""

    model_config = ConfigDict(extra="forbid")

    active_grant_count: int = Field(ge=0)
    pending_grant_count: int = Field(ge=0)
    total_grant_count: int = Field(ge=0)


class ExternalSharingPolicyUpdateResponse(ExternalSharingPolicy):
    """Applied policy or server-bound destructive confirmation preview."""

    status: Literal["confirmation_required", "applied"]
    impact: ExternalSharingPolicyImpact
    proposal_digest: str | None = None
    revoked_grant_count: int = Field(default=0, ge=0)


__all__ = [
    "ExternalSharingPolicy",
    "ExternalSharingPolicyImpact",
    "ExternalSharingPolicyMode",
    "ExternalSharingPolicyUpdateRequest",
    "ExternalSharingPolicyUpdateResponse",
    "normalize_external_sharing_domain",
]
