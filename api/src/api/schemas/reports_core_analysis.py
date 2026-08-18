"""Core patent analysis and invalidity response models."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.reports_types import (
    DoEConfidenceBand,
    EnablementScope,
    InvalidityStrength,
    PriorArtReferenceType,
    PTABProceedingType,
    RiskLevel,
    SourceDatabase,
)


class PatentAnalysisResponse(BaseModel):
    """Top-level patent analysis payload.

    Nested claim-analysis details remain permissive for now, but the core
    per-patent summary fields are explicitly typed.
    """

    model_config = ConfigDict(extra="allow")

    patent_id: str
    title: str = ""
    assignee: str = ""
    expiry_date: date | None = None
    claims_analyzed: list[dict[str, Any]] = Field(default_factory=list)
    risk_level: RiskLevel | None = None
    risk_summary: str = ""
    design_around_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    orange_book_info: dict[str, Any] | None = None
    model_used: str = ""
    thinking_text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    perspective_analyses: list[dict[str, Any]] = Field(default_factory=list)
    multi_perspective_synthesis: dict[str, Any] | None = None


class ChemicalEquivalenceContextResponse(BaseModel):
    """Chemical relationship context used in DoE analysis."""

    structural_relationship: str = "none"
    relationship_reasoning: str = ""
    known_interchangeability: bool = False
    interchangeability_evidence: str = ""


class FWRAssessmentResponse(BaseModel):
    """Function-way-result analysis for one claim element."""

    same_function: bool
    function_reasoning: str
    same_way: bool
    way_reasoning: str
    same_result: bool
    result_reasoning: str
    equivalent: bool
    chemical_context: ChemicalEquivalenceContextResponse | None = None


class EstoppelResultResponse(BaseModel):
    """Prosecution-history estoppel summary for DoE analysis."""

    amendments_found: list[str] = Field(default_factory=list)
    estoppel_applies: bool = False
    surrendered_scope: str = ""
    file_wrapper_available: bool = False
    rejections_found: list[str] = Field(default_factory=list)
    prosecution_narrowing_count: int = 0


class DoEAssessmentResponse(BaseModel):
    """Doctrine of equivalents assessment for one non-literal element."""

    patent_id: str
    claim_number: int
    element_number: int
    element_text: str = ""
    estoppel: EstoppelResultResponse = Field(default_factory=EstoppelResultResponse)
    fwr: FWRAssessmentResponse | None = None
    overall_equivalent: bool = False
    confidence: float = 0.0
    confidence_band: DoEConfidenceBand = "LOW"
    reasoning: str = ""


class ClaimChartEntryResponse(BaseModel):
    """Maps one claim element to one prior-art disclosure."""

    element_number: int
    element_text: str
    prior_art_reference_id: str
    prior_art_disclosure: str
    citation_location: str = ""
    disclosed: str
    notes: str = ""


class ClaimChartResponse(BaseModel):
    """Claim chart against one prior-art reference."""

    patent_id: str
    claim_number: int
    prior_art_reference_id: str
    entries: list[ClaimChartEntryResponse] = Field(default_factory=list)
    all_elements_disclosed: bool = False
    chart_summary: str = ""


class GrahamFactorsResponse(BaseModel):
    """Graham-factor obviousness analysis."""

    scope_and_content: str
    differences_from_prior_art: str
    level_of_ordinary_skill: str
    commercial_success: str = ""
    long_felt_need: str = ""
    failure_of_others: str = ""
    unexpected_results: str = ""
    overall_obviousness_assessment: str


class EnablementScreeningResponse(BaseModel):
    """Enablement screening including genus-claim flags."""

    genus_claim_detected: bool = False
    genus_indicators: list[str] = Field(default_factory=list)
    specification_enables_full_scope: EnablementScope = "unclear"
    amgen_v_sanofi_flags: list[str] = Field(default_factory=list)
    reasoning: str = ""


class PriorArtReferenceResponse(BaseModel):
    """One prior-art reference used in invalidity screening."""

    reference_id: str
    title: str = ""
    publication_date: date | None = None
    relevance: str = ""
    anticipation_score: float = 0.0
    obviousness_score: float = 0.0
    reference_type: PriorArtReferenceType = "patent"
    authors: list[str] = Field(default_factory=list)
    journal: str = ""
    doi: str = ""
    url: str = ""
    abstract: str = ""
    source_database: SourceDatabase = ""


class InvalidityPTABProceedingResponse(BaseModel):
    """One PTAB proceeding in invalidity screening."""

    proceeding_number: str
    type: PTABProceedingType
    status: str
    filing_date: date | None = None
    decision_date: date | None = None
    claims_challenged: list[int] = Field(default_factory=list)
    claims_cancelled: list[int] = Field(default_factory=list)
    claims_survived: list[int] = Field(default_factory=list)
    outcome_summary: str = ""


class PTABResultResponse(BaseModel):
    """Aggregated PTAB history for a patent."""

    has_been_challenged: bool = False
    proceedings: list[InvalidityPTABProceedingResponse] = Field(default_factory=list)
    all_claims_cancelled: list[int] = Field(default_factory=list)


class InvalidityAssessmentResponse(BaseModel):
    """Top-level invalidity screening payload."""

    patent_id: str
    claim_numbers: list[int] = Field(default_factory=list)
    ptab: PTABResultResponse = Field(default_factory=PTABResultResponse)
    prior_art: list[PriorArtReferenceResponse] = Field(default_factory=list)
    written_description_issues: list[str] = Field(default_factory=list)
    claim_charts: list[ClaimChartResponse] = Field(default_factory=list)
    graham_factors: GrahamFactorsResponse | None = None
    enablement_screening: EnablementScreeningResponse | None = None
    overall_invalidity_strength: InvalidityStrength = ""
    reasoning: str = ""
    confidence: float = 0.0
    confidence_band: DoEConfidenceBand = "LOW"
    screening_disclaimer: str = ""


__all__ = [
    "ChemicalEquivalenceContextResponse",
    "ClaimChartEntryResponse",
    "ClaimChartResponse",
    "DoEAssessmentResponse",
    "EnablementScreeningResponse",
    "EstoppelResultResponse",
    "FWRAssessmentResponse",
    "GrahamFactorsResponse",
    "InvalidityAssessmentResponse",
    "InvalidityPTABProceedingResponse",
    "PTABResultResponse",
    "PatentAnalysisResponse",
    "PriorArtReferenceResponse",
]
