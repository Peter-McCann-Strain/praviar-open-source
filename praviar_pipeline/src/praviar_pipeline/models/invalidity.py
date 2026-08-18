"""Patent invalidity analysis models — output of Step 6."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_VALID_STRENGTHS = {"weak", "moderate", "strong"}
_NO_INVALIDITY_VALUES = {"none", "n/a", "no", "nothing", "nil", "null"}
_COMPOUND_STRENGTH_MAP = {
    "moderate-strong": "strong",
    "moderate_strong": "strong",
    "strong-moderate": "strong",
    "strong_moderate": "strong",
    "weak-moderate": "moderate",
    "weak_moderate": "moderate",
    "moderate-weak": "moderate",
    "moderate_weak": "moderate",
}


def _normalize_strength(v: str) -> str:
    """Normalise a raw strength string from LLM output.

    - Empty / explicit-no-argument values (e.g. "none", "n/a") → ""
    - Compound/hyphenated forms (e.g. "moderate-strong") → canonical value
    - Unknown junk → "weak" (smallest valid signal, never fabricates a missing one)
    """
    v = v.strip().lower()
    if not v or v in _NO_INVALIDITY_VALUES:
        return ""
    v = _COMPOUND_STRENGTH_MAP.get(v, v)
    if v not in _VALID_STRENGTHS:
        return "weak"
    return v


INVALIDITY_SCREENING_DISCLAIMER = (
    "This is an automated screening assessment, not a legal opinion. "
    "Invalidity arguments require detailed claim construction, full prior art review, "
    "and expert declaration to be actionable. Claim charts are illustrative and must be "
    "verified against the actual patent specification and prior art documents. "
    "Confidence bands reflect evidence availability, not litigation outcome probability."
)


# ── Claim Chart Models ──────────────────────────────────────────────────────


class ClaimChartEntry(BaseModel):
    """Maps a single claim element to a prior art disclosure."""

    model_config = ConfigDict(extra="forbid")

    element_number: int = Field(ge=1)
    element_text: str
    prior_art_reference_id: str
    prior_art_disclosure: str
    citation_location: str = ""  # page, column, paragraph
    disclosed: Literal["yes", "no", "partial"]
    notes: str = ""


class ClaimChart(BaseModel):
    """Complete claim chart mapping one claim against one prior art reference."""

    model_config = ConfigDict(extra="forbid")

    patent_id: str
    claim_number: int
    prior_art_reference_id: str
    entries: list[ClaimChartEntry] = Field(default_factory=list)
    all_elements_disclosed: bool = False
    chart_summary: str = ""

    @model_validator(mode="after")
    def _auto_check_coverage(self) -> ClaimChart:
        """Auto-compute all_elements_disclosed from entries."""
        if self.entries:
            self.all_elements_disclosed = all(e.disclosed == "yes" for e in self.entries)
        return self

    @model_validator(mode="after")
    def _check_entries_present(self) -> ClaimChart:
        """Warn if claim chart has no entries (possible LLM failure)."""
        if not self.entries:
            import structlog

            structlog.get_logger().warning(
                "claim_chart_empty_entries",
            )
        return self


class GrahamFactors(BaseModel):
    """Graham v. John Deere four-factor obviousness analysis."""

    model_config = ConfigDict(extra="forbid")

    scope_and_content: str
    differences_from_prior_art: str
    level_of_ordinary_skill: str
    commercial_success: str = ""
    long_felt_need: str = ""
    failure_of_others: str = ""
    unexpected_results: str = ""
    overall_obviousness_assessment: str


class EnablementScreening(BaseModel):
    """35 USC 112 enablement screening, including Amgen v. Sanofi genus claim analysis."""

    model_config = ConfigDict(extra="forbid")

    genus_claim_detected: bool = False
    genus_indicators: list[str] = Field(default_factory=list)
    specification_enables_full_scope: Literal["yes", "no", "unclear"] = "unclear"
    amgen_v_sanofi_flags: list[str] = Field(default_factory=list)
    reasoning: str = ""


class PriorArtReference(BaseModel):
    """A prior art reference that may invalidate blocking claims."""

    model_config = ConfigDict(extra="forbid")

    reference_id: str = Field(description="Patent number or publication ID")
    title: str = ""
    publication_date: date | None = None
    relevance: str = Field(default="", description="How this reference relates to blocking claims")
    anticipation_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Likelihood this reference anticipates (102) the blocking claim",
    )
    obviousness_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Likelihood this reference renders obvious (103) the blocking claim",
    )

    # Scholarly reference fields
    reference_type: Literal["patent", "journal_article", "conference_paper", "preprint"] = Field(
        default="patent",
        description="patent, journal_article, conference_paper, preprint",
    )
    authors: list[str] = Field(default_factory=list)
    journal: str = ""
    doi: str = ""
    url: str = ""
    abstract: str = ""
    source_database: Literal["semantic_scholar", "openalex", "lens", "bigquery", "pubmed", ""] = (
        Field(
            default="",
            description="Where this reference was found",
        )
    )
    ipr_eligible_printed_publication: bool = Field(
        default=False,
        description=(
            "True only when counsel-verified evidence establishes a patent or "
            "printed publication usable under 35 U.S.C. § 311(b)."
        ),
    )
    ipr_eligibility_basis: str = ""

    @field_validator("reference_type", mode="before")
    @classmethod
    def _coerce_reference_type(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip().lower().replace(" ", "_").replace("-", "_")
            valid = {"patent", "journal_article", "conference_paper", "preprint"}
            if v not in valid:
                return "patent"
        return v

    @field_validator("source_database", mode="before")
    @classmethod
    def _coerce_source_database(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip().lower().replace(" ", "_")
            valid = {"semantic_scholar", "openalex", "lens", "bigquery", "pubmed", ""}
            if v not in valid:
                return ""
        return v


class PTABProceeding(BaseModel):
    """A PTAB proceeding (IPR/PGR/CBM) against the patent."""

    model_config = ConfigDict(extra="forbid")

    proceeding_number: str = Field(description="e.g. IPR2019-00123")
    type: Literal["IPR", "PGR", "CBM"] = Field(description="IPR, PGR, or CBM")
    status: str = Field(description="Instituted, Final Written Decision, Settled, etc.")
    filing_date: date | None = None
    decision_date: date | None = None
    claims_challenged: list[int] = Field(default_factory=list)
    claims_reported_cancelled: list[int] = Field(
        default_factory=list,
        description="Provider-reported cancellations before independent finality verification.",
    )
    claims_cancelled: list[int] = Field(
        default_factory=list,
        description="Claims with an independently supported effective cancellation record.",
    )
    claims_survived: list[int] = Field(default_factory=list)
    outcome_summary: str = ""
    final_written_decision_verified: bool = False
    cancellation_certificate_verified: bool = False
    review_and_appeal_posture: str = ""


class PTABResult(BaseModel):
    """Aggregated PTAB history for a patent."""

    model_config = ConfigDict(extra="forbid")

    has_been_challenged: bool = False
    proceedings: list[PTABProceeding] = Field(default_factory=list)
    all_claims_cancelled: list[int] = Field(
        default_factory=list,
        description=(
            "Union of claims with an independently supported effective cancellation "
            "record; provider-reported cancellation alone is excluded."
        ),
    )

    @model_validator(mode="after")
    def _bind_effective_cancellations_to_proceedings(self) -> PTABResult:
        if self.has_been_challenged != bool(self.proceedings):
            raise ValueError("PTAB challenge state must match the retained proceeding records")
        effective_claims = sorted(
            {
                claim_number
                for proceeding in self.proceedings
                if proceeding.final_written_decision_verified
                and proceeding.cancellation_certificate_verified
                and proceeding.status.strip().casefold() == "final written decision"
                and proceeding.review_and_appeal_posture.strip()
                for claim_number in proceeding.claims_cancelled
            }
        )
        if sorted(set(self.all_claims_cancelled)) != effective_claims:
            raise ValueError("effective PTAB cancellations must derive from verified proceedings")
        self.all_claims_cancelled = effective_claims
        return self


class InvalidityArgument(BaseModel):
    """A single invalidity argument identified by the LLM."""

    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "anticipation",
        "obviousness",
        "enablement",
        "written_description",
        "odp",
    ] = Field(
        description=(
            "anticipation, obviousness, enablement, written_description, or "
            "obviousness-type double patenting"
        ),
    )
    statute: str = Field(default="", description="e.g. 35 U.S.C. § 102")
    strength: str = Field(description="weak, moderate, or strong")
    key_evidence: list[str] = Field(
        description="Specific references or facts supporting this argument",
    )
    counterarguments: list[str] = Field(
        default_factory=list,
        description="How the patent holder might respond",
    )
    reasoning: str = Field(description="Detailed reasoning for the strength assessment")

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip().lower().replace(" ", "_").replace("-", "_")
            valid = {
                "anticipation",
                "obviousness",
                "enablement",
                "written_description",
                "odp",
            }
            if v not in valid:
                return "obviousness"
        return v

    @field_validator("strength", mode="before")
    @classmethod
    def _coerce_strength(cls, v: str) -> str:
        if isinstance(v, str):
            return _normalize_strength(v)
        return v


class InvalidityLLMResponse(BaseModel):
    """Structured LLM response for invalidity assessment."""

    model_config = ConfigDict(extra="forbid")

    arguments: list[InvalidityArgument] = Field(
        description="Each invalidity argument identified",
    )
    overall_strength: str = Field(description="weak, moderate, or strong")
    overall_reasoning: str = Field(description="Summary of the invalidity case")
    written_description_issues: list[str] = Field(default_factory=list)
    claim_charts: list[ClaimChart] = Field(default_factory=list)
    graham_factors: GrahamFactors | None = None
    enablement_screening: EnablementScreening | None = None

    @field_validator("overall_strength", mode="before")
    @classmethod
    def _coerce_overall_strength(cls, v: str) -> str:
        if isinstance(v, str):
            return _normalize_strength(v)
        return v


class InvalidityAssessment(BaseModel):
    """Complete invalidity assessment for a blocking patent."""

    model_config = ConfigDict(extra="forbid")

    patent_id: str
    claim_numbers: list[int] = Field(
        default_factory=list,
        description="Which claims are being assessed for invalidity",
    )

    # PTAB history (deterministic)
    ptab: PTABResult = Field(default_factory=PTABResult)

    # Prior art search (LLM-assisted)
    prior_art: list[PriorArtReference] = Field(default_factory=list)
    arguments: list[InvalidityArgument] = Field(
        default_factory=list,
        description="Ground-specific screening arguments retained from the model response.",
    )

    # Written description / enablement issues
    written_description_issues: list[str] = Field(default_factory=list)

    # Claim charts and structured analysis
    claim_charts: list[ClaimChart] = Field(default_factory=list)
    graham_factors: GrahamFactors | None = None
    enablement_screening: EnablementScreening | None = None
    ipr_prior_art_scope_verified: bool = Field(
        default=False,
        description=(
            "Every proposed IPR ground is limited to §102/103 patents or printed publications."
        ),
    )
    ipr_timing_verified: bool = False
    ipr_estoppel_and_rpi_verified: bool = False
    ipr_discretionary_denial_reviewed: bool = False
    ipr_eligibility_reasoning: str = ""

    # Overall
    overall_invalidity_strength: str = Field(
        default="",
        description="weak, moderate, strong — how likely these claims are invalid",
    )
    reasoning: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_band: Literal["HIGH", "MODERATE", "LOW"] = "LOW"
    screening_disclaimer: str = Field(default=INVALIDITY_SCREENING_DISCLAIMER)

    @field_validator("overall_invalidity_strength", mode="before")
    @classmethod
    def _coerce_strength(cls, v: str) -> str:
        if isinstance(v, str):
            return _normalize_strength(v)
        return v
