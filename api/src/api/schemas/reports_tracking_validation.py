"""Bibliography and verification report models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from api.schemas.reports_types import BibliographyReferenceType, ValidationSeverity


class BibliographyEntryResponse(BaseModel):
    """A single bibliography/reference entry from unified report."""

    ref_type: BibliographyReferenceType = "patent"
    patent_id: str = ""
    title: str = ""
    assignee: str = ""
    filing_date: str = ""
    grant_date: str = ""
    expiry_date: str = ""
    authors: str = ""
    journal: str = ""
    doi: str = ""
    publication_date: str = ""
    proceeding_number: str = ""
    proceeding_type: str = ""
    proceeding_status: str = ""
    url: str = ""


class ValidationIssueResponse(BaseModel):
    """A single deterministic validation issue."""

    validator_name: str
    severity: ValidationSeverity = "error"
    section_id: str = ""
    description: str = ""
    patent_id: str = ""
    expected: str = ""
    actual: str = ""


class ValidationResultResponse(BaseModel):
    """Output of one deterministic validator."""

    validator_name: str
    passed: bool = True
    issues: list[ValidationIssueResponse] = Field(default_factory=list)


class CorrectionEntryResponse(BaseModel):
    """A single factual correction from the unified verification stage."""

    section_id: str = ""
    claim_text: str = ""
    incorrect_value: str = ""
    correct_value: str = ""
    correction_type: str = ""


class VerificationSummaryResponse(BaseModel):
    """LLM verification summary from unified report pipeline."""

    total_claims_checked: int = 0
    claims_correct: int = 0
    claims_incorrect: int = 0
    claims_unverifiable: int = 0
    factual_accuracy_rate: float = 0.0
    corrections_needed: list[CorrectionEntryResponse] = Field(default_factory=list)
    omissions_found: list[str] = Field(default_factory=list)
    overall_assessment: str = ""
