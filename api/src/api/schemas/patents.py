"""Request/response schemas for patents."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.reports import RiskLevel

# ── Claim element models ────────────────────────────────────────────────────


class ClaimElementSchema(BaseModel):
    """Element-by-element analysis of a single claim limitation."""

    element_number: int
    element_text: str = ""
    status: Literal["met", "not_met", "partially_met", "unclear"]
    reasoning: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: str = ""


class ClaimAnalysisSchema(BaseModel):
    """Analysis of a single patent claim."""

    claim_number: int
    claim_type: Literal["independent", "dependent"] = "independent"
    depends_on: int | None = None
    preamble: str = ""
    transitional_phrase: str = ""
    elements: list[ClaimElementSchema] = Field(default_factory=list)
    reasoning: str = ""
    overall_status: Literal["met", "not_met", "partially_met", "unclear"]
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class DesignAroundSuggestionSchema(BaseModel):
    """A suggested modification to avoid infringement."""

    element_avoided: int = Field(..., ge=1)
    suggestion: str = ""
    feasibility: str = ""


# ── Patent analysis (full typed model) ──────────────────────────────────────


class PatentAnalysisBaseSchema(BaseModel):
    """Shared fields in the complete counsel-authorized patent analysis."""

    patent_id: str
    title: str = ""
    assignee: str = ""
    expiry_date: date | None = None
    claims_analyzed: list[ClaimAnalysisSchema] = Field(default_factory=list)
    orange_book_info: dict[str, Any] | None = None
    model_used: str = ""
    thinking_text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class PatentAnalysisSchema(PatentAnalysisBaseSchema):
    """Complete FTO analysis including counsel-governed risk."""

    risk_level: RiskLevel
    risk_summary: str = ""
    design_around_suggestions: list[DesignAroundSuggestionSchema] = Field(
        default_factory=list,
    )


class RiskRestrictedClaimElementSchema(BaseModel):
    """Neutral source claim text without product-to-claim conclusions."""

    model_config = ConfigDict(extra="forbid")

    element_number: int
    element_text: str = ""


class RiskRestrictedClaimAnalysisSchema(BaseModel):
    """Claim identity and source language safe for restricted principals."""

    model_config = ConfigDict(extra="forbid")

    claim_number: int
    claim_type: Literal["independent", "dependent"] = "independent"
    depends_on: int | None = None
    preamble: str = ""
    transitional_phrase: str = ""
    elements: list[RiskRestrictedClaimElementSchema] = Field(default_factory=list)


class RiskRestrictedPatentAnalysisSchema(BaseModel):
    """Neutral patent identity and claim-source evidence only.

    This is intentionally not derived from ``PatentAnalysisBaseSchema``:
    counsel-governed conclusions must be added explicitly to this contract,
    never inherited accidentally when the authorized model grows.
    """

    model_config = ConfigDict(extra="forbid")

    patent_id: str
    title: str = ""
    assignee: str = ""
    expiry_date: date | None = None
    claims_analyzed: list[RiskRestrictedClaimAnalysisSchema] = Field(
        default_factory=list,
    )


# ── DoE assessment schema ──────────────────────────────────────────────────


class DoEAssessmentSchema(BaseModel):
    """Doctrine of equivalents assessment — typed response schema."""

    patent_id: str
    claim_number: int
    element_number: int
    element_text: str = ""
    estoppel: dict[str, Any] = Field(default_factory=dict)
    fwr: dict[str, Any] | None = None
    overall_equivalent: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_band: Literal["HIGH", "MODERATE", "LOW"] = "LOW"
    reasoning: str = ""


class RiskRestrictedDoEAssessmentSchema(BaseModel):
    """DoE target identity without an equivalence or estoppel conclusion."""

    model_config = ConfigDict(extra="forbid")

    patent_id: str
    claim_number: int
    element_number: int
    element_text: str = ""


# ── Invalidity assessment schema ────────────────────────────────────────────


class InvalidityAssessmentSchema(BaseModel):
    """Invalidity assessment — typed response schema."""

    patent_id: str
    claim_numbers: list[int] = Field(default_factory=list)
    ptab: dict[str, Any] = Field(default_factory=dict)
    prior_art: list[dict[str, Any]] = Field(default_factory=list)
    written_description_issues: list[str] = Field(default_factory=list)
    claim_charts: list[dict[str, Any]] = Field(default_factory=list)
    graham_factors: dict[str, Any] | None = None
    enablement_screening: dict[str, Any] | None = None
    overall_invalidity_strength: str = ""
    reasoning: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_band: Literal["HIGH", "MODERATE", "LOW"] = "LOW"
    screening_disclaimer: str = ""


class RiskRestrictedPriorArtReferenceSchema(BaseModel):
    """Bibliographic prior-art source metadata without invalidity scoring."""

    model_config = ConfigDict(extra="forbid")

    reference_id: str
    title: str = ""
    publication_date: date | None = None
    reference_type: Literal[
        "patent",
        "journal_article",
        "conference_paper",
        "preprint",
    ] = "patent"
    authors: list[str] = Field(default_factory=list)
    journal: str = ""
    doi: str = ""
    url: str = ""
    abstract: str = ""
    source_database: Literal[
        "semantic_scholar",
        "openalex",
        "lens",
        "bigquery",
        "pubmed",
        "",
    ] = ""


class RiskRestrictedPTABProceedingSchema(BaseModel):
    """Public PTAB docket facts without an evaluative outcome narrative."""

    model_config = ConfigDict(extra="forbid")

    proceeding_number: str
    type: Literal["IPR", "PGR", "CBM"]
    status: str
    filing_date: date | None = None
    decision_date: date | None = None
    claims_challenged: list[int] = Field(default_factory=list)
    claims_cancelled: list[int] = Field(default_factory=list)
    claims_survived: list[int] = Field(default_factory=list)


class RiskRestrictedPTABResultSchema(BaseModel):
    """Public PTAB history facts safe for restricted principals."""

    model_config = ConfigDict(extra="forbid")

    has_been_challenged: bool = False
    proceedings: list[RiskRestrictedPTABProceedingSchema] = Field(default_factory=list)
    all_claims_cancelled: list[int] = Field(default_factory=list)


class RiskRestrictedInvalidityAssessmentSchema(BaseModel):
    """Neutral invalidity-source inventory without legal conclusions."""

    model_config = ConfigDict(extra="forbid")

    patent_id: str
    claim_numbers: list[int] = Field(default_factory=list)
    ptab: RiskRestrictedPTABResultSchema = Field(
        default_factory=RiskRestrictedPTABResultSchema,
    )
    prior_art: list[RiskRestrictedPriorArtReferenceSchema] = Field(
        default_factory=list,
    )


# ── List / detail response models ───────────────────────────────────────────


class PatentItemBase(BaseModel):
    id: str
    patent_number: str
    title: str
    assignee: str
    cpc_codes: list[str]
    expiry_date: str | None
    analysis_id: str
    compound_name: str


class PatentItem(PatentItemBase):
    risk_level: RiskLevel | str  # May be empty string for missing data


class RiskRestrictedPatentItem(PatentItemBase):
    """Patent-library row with counsel-governed risk omitted."""


class PatentListResponse(BaseModel):
    items: list[PatentItem]
    total: int
    page: int = 1
    per_page: int = 20


class RiskRestrictedPatentListResponse(BaseModel):
    items: list[RiskRestrictedPatentItem]
    total: int
    page: int = 1
    per_page: int = 20


class PatentDetailResponse(BaseModel):
    patent_analysis: PatentAnalysisSchema
    doe_assessment: DoEAssessmentSchema | None
    invalidity_assessment: InvalidityAssessmentSchema | None
    analysis_id: str


class RiskRestrictedPatentDetailResponse(BaseModel):
    patent_analysis: RiskRestrictedPatentAnalysisSchema
    doe_assessment: RiskRestrictedDoEAssessmentSchema | None
    invalidity_assessment: RiskRestrictedInvalidityAssessmentSchema | None
    analysis_id: str
