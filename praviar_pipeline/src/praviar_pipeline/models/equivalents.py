"""Doctrine of Equivalents models — output of Step 5."""

from __future__ import annotations

from datetime import date
from typing import Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = structlog.get_logger()


# ── Prosecution History Models ───────────────────────────────────────────────


class ClaimAmendment(BaseModel):
    """A narrowing amendment made during patent prosecution."""

    model_config = ConfigDict(extra="forbid")

    claim_number: int
    amendment_date: date | None = None
    amendment_type: Literal["added", "cancelled", "amended"] = "amended"
    original_text: str = ""
    amended_text: str = ""
    narrowing: bool = False
    response_to_rejection: bool = False
    patentability_related: bool | None = Field(
        default=None,
        description="Whether the complete record establishes a patentability nexus.",
    )
    surrendered_scope: str = Field(
        default="",
        description="Exact territory surrendered by this amendment.",
    )
    festo_rebuttal: Literal[
        "unresolved",
        "not_established",
        "unforeseeable",
        "tangential",
        "other_reason",
    ] = "unresolved"
    festo_rebuttal_reasoning: str = ""


class RejectionRecord(BaseModel):
    """An office action rejection during prosecution."""

    model_config = ConfigDict(extra="forbid")

    rejection_type: Literal["102", "103", "112_a", "112_b", "101", "other"] = "other"
    claims_rejected: list[int] = Field(default_factory=list)
    prior_art_cited: list[str] = Field(default_factory=list)
    rejection_basis: str = ""


class ProsecutionHistory(BaseModel):
    """Parsed prosecution history from USPTO file wrapper."""

    model_config = ConfigDict(extra="forbid")

    patent_id: str
    application_number: str = ""
    filing_date: date | None = None
    grant_date: date | None = None
    rejections: list[RejectionRecord] = Field(default_factory=list)
    amendments: list[ClaimAmendment] = Field(default_factory=list)
    applicant_arguments: list[str] = Field(default_factory=list)
    has_terminal_disclaimer: bool = False
    prosecution_complete: bool = False
    inventor_names: list[str] = Field(default_factory=list)
    examiner_name: str = ""
    attorney_name: str = ""
    current_assignee: str = ""
    total_office_actions: int = 0
    total_responses: int = 0
    prosecution_duration_days: int | None = None


# ── Chemical Equivalence Context ─────────────────────────────────────────────


class ChemicalEquivalenceContext(BaseModel):
    """Chemical structural relationship context for DoE analysis."""

    model_config = ConfigDict(extra="forbid")

    structural_relationship: Literal[
        "bioisostere",
        "homolog",
        "stereoisomer",
        "salt_form",
        "polymorph",
        "prodrug",
        "metabolic_equivalent",
        "none",
        "other",
    ] = "none"
    relationship_reasoning: str = ""
    known_interchangeability: bool = False
    interchangeability_evidence: str = ""


class FWRAssessment(BaseModel):
    """Function-Way-Result test for a single claim element."""

    model_config = ConfigDict(extra="forbid")

    same_function: bool | None = Field(
        description="True, false, or null when the function evidence is unresolved."
    )
    function_reasoning: str
    same_way: bool | None = Field(
        description="True, false, or null when the way evidence is unresolved."
    )
    way_reasoning: str
    same_result: bool | None = Field(
        description="True, false, or null when the result evidence is unresolved."
    )
    result_reasoning: str
    equivalent: bool | None = Field(
        description=(
            "True only when all three prongs are affirmatively met; false when any "
            "prong is affirmatively not met; null when no prong is false but at "
            "least one is unresolved."
        )
    )
    chemical_context: ChemicalEquivalenceContext | None = None

    @field_validator("same_function", "same_way", "same_result", "equivalent", mode="before")
    @classmethod
    def _coerce_bool(cls, v: object) -> bool | None:
        """Preserve uncertainty rather than coercing it into equivalence."""
        if v is None or isinstance(v, bool):
            return v
        if isinstance(v, str):
            lv = v.strip().lower()
            if lv in {"yes", "true", "1"}:
                return True
            if lv in {"no", "false", "0"}:
                return False
            if lv in {"partially", "partial", "maybe", "unclear", "uncertain"}:
                logger.info("doe_prong_preserved_as_uncertain")
                return None
        raise ValueError("FWR prong must be true, false, or uncertain")

    @model_validator(mode="after")
    def _check_fwr_consistency(self) -> FWRAssessment:
        """Ensure equivalent == (same_function and same_way and same_result)."""
        prongs = (self.same_function, self.same_way, self.same_result)
        if False in prongs:
            expected = False
        elif all(value is True for value in prongs):
            expected = True
        else:
            expected = None
        if self.equivalent != expected:
            logger.warning(
                "fwr_consistency_fix",
                expected=expected,
                got=self.equivalent,
            )
            self.equivalent = expected
        return self


class EstoppelResult(BaseModel):
    """Prosecution history estoppel check."""

    model_config = ConfigDict(extra="forbid")

    amendments_found: list[str] = Field(
        default_factory=list,
        description="Narrowing amendments identified in file wrapper",
    )
    estoppel_applies: bool | None = Field(
        default=None,
        description=(
            "True when the complete record establishes an unrebutted surrender, "
            "false when the complete record establishes no bar, and null when "
            "the file wrapper, nexus, scope, or Festo rebuttal record is unresolved."
        ),
    )
    surrendered_scope: str = Field(
        default="",
        description="Description of subject matter surrendered during prosecution",
    )
    file_wrapper_available: bool = Field(
        default=False,
        description="Whether the file wrapper was successfully retrieved",
    )
    rejections_found: list[str] = Field(
        default_factory=list,
        description="Rejection types found in prosecution history",
    )
    prosecution_narrowing_count: int = 0

    @model_validator(mode="after")
    def _flag_missing_file_wrapper(self) -> EstoppelResult:
        """Warn when estoppel defaults to False due to missing file wrapper."""
        if not self.file_wrapper_available and self.estoppel_applies is not None:
            self.estoppel_applies = None
        if self.estoppel_applies is None:
            logger.warning(
                "estoppel_unresolved",
            )
        return self


class DoEAssessment(BaseModel):
    """Doctrine of equivalents assessment for a NOT_MET element."""

    model_config = ConfigDict(extra="forbid")

    patent_id: str
    claim_number: int
    element_number: int
    element_text: str = ""

    # Estoppel (Phase A)
    estoppel: EstoppelResult = Field(default_factory=EstoppelResult)

    # FWR test (Phase B)
    fwr: FWRAssessment | None = Field(
        default=None,
        description="None if estoppel bars DoE analysis",
    )

    # Overall
    overall_equivalent: bool | None = Field(
        default=None,
        description=(
            "True only when FWR is affirmative and estoppel is affirmatively "
            "resolved not to bar the theory; null means the legal result is unresolved."
        ),
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_band: Literal["HIGH", "MODERATE", "LOW"] = "LOW"
    reasoning: str = ""

    @model_validator(mode="after")
    def _check_estoppel_override(self) -> DoEAssessment:
        """If estoppel applies, DoE cannot find equivalence."""
        if self.estoppel.estoppel_applies is True and self.overall_equivalent is not False:
            logger.warning(
                "estoppel_override",
                element=self.element_number,
            )
            self.overall_equivalent = False
        elif self.estoppel.estoppel_applies is None and self.overall_equivalent is True:
            logger.warning(
                "estoppel_uncertainty_blocks_equivalence",
                element=self.element_number,
            )
            self.overall_equivalent = None
        return self
