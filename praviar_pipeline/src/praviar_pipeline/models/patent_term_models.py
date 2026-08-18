"""Patent term and regulatory-linked support models."""

from __future__ import annotations

import datetime
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PTABreakdown(BaseModel):
    """Detailed Patent Term Adjustment breakdown (A/B/C components)."""

    model_config = ConfigDict(extra="forbid")

    a_delay_days: int = Field(default=0, description="USPTO delay: failure to act within 14 months")
    b_delay_days: int = Field(default=0, description="USPTO delay: failure to issue within 3 years")
    c_delay_days: int = Field(default=0, description="USPTO delay: interference/appeal/injunction")
    overlap_days: int = Field(default=0, description="Overlap between A/B/C components")
    applicant_delay_days: int = Field(default=0, description="Days of applicant-caused delay")
    total_days: int = Field(default=0, description="Net PTA = A+B+C - overlap - applicant delay")


class PatentTermInfo(BaseModel):
    """Computed patent term information for a US patent."""

    model_config = ConfigDict(extra="forbid")

    patent_id: str
    effective_filing_date: date | None = None
    grant_date: date | None = None
    base_expiry: date | None = None
    pta_days: int = 0
    pta_breakdown: PTABreakdown | None = None
    pte_days: int = 0
    terminal_disclaimer: bool = False
    td_linked_patent: str = ""
    td_linked_expiry: date | None = None
    pte_extension_base_expiry: date | None = Field(
        default=None,
        description=(
            "Original expiry from which 35 U.S.C. 156 PTE runs, after PTA is capped "
            "by any applicable terminal disclaimer"
        ),
    )
    maintenance_fee_status: Literal[
        "paid",
        "lapsed",
        "grace_period",
        "not_yet_due",
        "not_applicable",
        "unknown",
    ] = "unknown"
    maintenance_fee_next_due: date | None = None
    adjusted_expiry: date | None = None
    calculation_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    calculation_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _compute_adjusted_expiry(self) -> PatentTermInfo:
        """Compute PTA, terminal-disclaimer cap, then PTE in statutory order."""
        if self.base_expiry is None:
            return self

        pta_adjusted_expiry = self.base_expiry + datetime.timedelta(days=self.pta_days)
        if self.terminal_disclaimer:
            if self.td_linked_expiry is None:
                return self
            pte_base = min(pta_adjusted_expiry, self.td_linked_expiry)
        else:
            pte_base = pta_adjusted_expiry

        if self.pte_extension_base_expiry is None:
            self.pte_extension_base_expiry = pte_base
        elif self.pte_extension_base_expiry != pte_base:
            raise ValueError("pte_extension_base_expiry conflicts with statutory term order")

        expected_adjusted = pte_base + datetime.timedelta(days=self.pte_days)
        if self.adjusted_expiry is None:
            self.adjusted_expiry = expected_adjusted
        elif self.adjusted_expiry != expected_adjusted:
            raise ValueError("adjusted_expiry conflicts with statutory term order")
        return self


class OrangeBookExclusivity(BaseModel):
    """One FDA Orange Book exclusivity code/date record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1)
    expiration_date: str = Field(min_length=1)

    @field_validator("expiration_date")
    @classmethod
    def _validate_expiration_date(cls, value: str) -> str:
        try:
            datetime.datetime.strptime(value, "%b %d, %Y")
        except ValueError:
            raise ValueError("expiration_date must use FDA Orange Book date format") from None
        return value


class OrangeBookInfo(BaseModel):
    """FDA Orange Book regulatory-listing data for a patent.

    A listing is a regulatory linkage signal.  It is not, by itself, evidence
    that a target product practices any claim.
    """

    model_config = ConfigDict(extra="forbid")

    is_listed: bool = False
    nda_numbers: list[str] = Field(default_factory=list)
    product_names: list[str] = Field(default_factory=list)
    active_ingredients: list[str] = Field(default_factory=list)
    dosage_forms_routes: list[str] = Field(default_factory=list)
    reference_listed_drug: bool = False
    reference_standard: bool = False
    drug_substance_patent: bool = False
    drug_product_patent: bool = False
    patent_use_codes: list[str] = Field(default_factory=list)
    exclusivities: list[OrangeBookExclusivity] = Field(default_factory=list)
    exclusivity_codes: list[str] = Field(default_factory=list)
    exclusivity_expiration_dates: list[str] = Field(default_factory=list)
    pediatric_exclusivity: bool = False
    delist_requested: bool = False
    regulatory_linkage_only: bool = True

    @model_validator(mode="after")
    def _preserve_exclusivity_pairs(self) -> OrangeBookInfo:
        """Keep compatibility projections consistent with the paired records."""
        if not self.exclusivities:
            if self.exclusivity_codes or self.exclusivity_expiration_dates:
                raise ValueError("Orange Book exclusivity codes and dates require paired records")
            return self

        projected_codes = sorted({record.code for record in self.exclusivities})
        projected_dates = sorted({record.expiration_date for record in self.exclusivities})
        if self.exclusivity_codes and self.exclusivity_codes != projected_codes:
            raise ValueError("exclusivity_codes conflict with paired records")
        if (
            self.exclusivity_expiration_dates
            and self.exclusivity_expiration_dates != projected_dates
        ):
            raise ValueError("exclusivity_expiration_dates conflict with paired records")
        self.exclusivity_codes = projected_codes
        self.exclusivity_expiration_dates = projected_dates
        return self
