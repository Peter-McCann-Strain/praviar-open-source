"""Verification models — output of Step 7 (deterministic checks)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VerificationCheck(BaseModel):
    """A single verification check result."""

    model_config = ConfigDict(extra="forbid")

    check_name: str
    passed: bool
    severity: Literal["pass", "warning", "fail"] = Field(
        default="pass",
        description=("pass=check passed, warning=vacuous pass or advisory, fail=check failed"),
    )
    details: str = Field(default="", description="What was checked and what was found")


class VerificationResult(BaseModel):
    """Complete verification output — all deterministic checks against source data."""

    model_config = ConfigDict(extra="forbid")

    # Individual checks
    checks: list[VerificationCheck] = Field(default_factory=list)

    # Summary booleans
    all_citations_valid: bool = Field(
        default=False,
        description="Every patent_id cited in analysis exists in search results",
    )
    all_claims_grounded: bool = Field(
        default=False,
        description="Quoted claim text matches source documents",
    )
    all_entities_valid: bool = Field(
        default=False,
        description="Every SMILES string in output parses in RDKit",
    )
    dates_consistent: bool = Field(
        default=False,
        description="Expiry dates are filing_date + 20 years (within PTA tolerance)",
    )
    risk_levels_justified: bool = Field(
        default=False,
        description="HIGH risk requires at least one BLOCKS claim",
    )

    # Issues found
    issues: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_minimum_checks(self) -> VerificationResult:
        """Warn if verification ran with fewer than expected checks."""
        if len(self.checks) < 3:
            import structlog

            structlog.get_logger().warning(
                "verification_insufficient_checks",
                check_count=len(self.checks),
            )
        return self

    @property
    def all_passed(self) -> bool:
        summary_passed = (
            self.all_citations_valid
            and self.all_claims_grounded
            and self.all_entities_valid
            and self.dates_consistent
            and self.risk_levels_justified
        )
        if self.checks:
            return summary_passed and all(c.passed for c in self.checks)
        return summary_passed
