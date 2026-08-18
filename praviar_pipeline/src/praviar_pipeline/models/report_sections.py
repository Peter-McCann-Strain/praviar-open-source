"""Unified report pipeline models: sections, bibliography, and verification."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReportSection(BaseModel):
    """Output of a single section generation call."""

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(description="e.g. 'executive_summary', 'key_patents'")
    section_title: str = Field(description="Human-readable section heading")
    content: str = Field(description="Markdown text of the section")
    patents_referenced: list[str] = Field(
        default_factory=list,
        description="Patent IDs mentioned in this section",
    )
    word_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls_made: int = 0


class BibliographyEntry(BaseModel):
    """A single reference in the report bibliography."""

    model_config = ConfigDict(extra="forbid")

    ref_type: Literal["patent", "prior_art", "ptab", "case_law", "regulatory"] = "patent"

    # Patent fields
    patent_id: str = ""
    title: str = ""
    assignee: str = ""
    filing_date: str = ""
    grant_date: str = ""
    expiry_date: str = ""

    # Scholarly / prior art fields
    authors: str = ""
    journal: str = ""
    doi: str = ""
    publication_date: str = ""

    # PTAB fields
    proceeding_number: str = ""
    proceeding_type: str = ""
    proceeding_status: str = ""

    # Link
    url: str = ""


class ValidationIssue(BaseModel):
    """A single issue found by a deterministic validator."""

    model_config = ConfigDict(extra="forbid")

    validator_name: str
    severity: Literal["error", "warning"] = "error"
    section_id: str = ""
    description: str = ""
    patent_id: str = ""
    expected: str = ""
    actual: str = ""


class ValidationResult(BaseModel):
    """Output of a single deterministic validator."""

    model_config = ConfigDict(extra="forbid")

    validator_name: str
    passed: bool = True
    issues: list[ValidationIssue] = Field(default_factory=list)


class CorrectionEntry(BaseModel):
    """A factual correction identified by the verification agent."""

    model_config = ConfigDict(extra="ignore")

    section_id: str = ""
    claim_text: str = ""
    incorrect_value: str = ""
    correct_value: str = ""
    correction_type: str = Field(
        default="",
        description="risk_level, date, assignee, element_status, other",
    )


class DeterministicViolation(BaseModel):
    """A single violation from a deterministic (rule-based) integrity check."""

    model_config = ConfigDict(extra="forbid")

    check_name: str
    severity: Literal["redact", "warn", "block"] = "warn"
    detail: str = ""
    location: str = Field(
        default="",
        description="Section id, sentence, or patent_id where the violation occurred",
    )


class DeterministicCheckResult(BaseModel):
    """Result of a single deterministic integrity check."""

    model_config = ConfigDict(extra="forbid")

    check_name: str
    passed: bool = True
    violations: list[DeterministicViolation] = Field(default_factory=list)


class VerificationReport(BaseModel):
    """Output of the LLM verification agent."""

    model_config = ConfigDict(extra="ignore")

    total_claims_checked: int = Field(default=0, ge=0)
    claims_correct: int = Field(default=0, ge=0)
    claims_incorrect: int = Field(default=0, ge=0)
    claims_unverifiable: int = Field(default=0, ge=0)
    factual_accuracy_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
    )
    corrections_needed: list[CorrectionEntry] = Field(default_factory=list)
    omissions_found: list[str] = Field(default_factory=list)
    overall_assessment: str = Field(
        default="",
        description="PASS, PASS_WITH_CORRECTIONS, or FAIL",
    )
    deterministic_check_results: list[DeterministicCheckResult] = Field(
        default_factory=list,
        description="Rule-based post-LLM integrity checks (see SG-123)",
    )

    @model_validator(mode="after")
    def _validate_claim_counts(self) -> VerificationReport:
        observed_claims = self.claims_correct + self.claims_incorrect + self.claims_unverifiable
        if observed_claims != self.total_claims_checked:
            raise ValueError(
                "verification categorized claim counts must equal total_claims_checked"
            )

        supplied_assessment = str(self.overall_assessment or "").strip().upper()
        if supplied_assessment == "SKIPPED" and self.total_claims_checked == 0:
            # Verification-disabled runs are an explicit non-production sentinel.
            self.factual_accuracy_rate = 1.0
            self.overall_assessment = "SKIPPED"
            return self

        self.factual_accuracy_rate = (
            self.claims_correct / self.total_claims_checked if self.total_claims_checked else 0.0
        )
        if self.total_claims_checked == 0:
            derived_assessment = "ERROR"
        elif self.claims_incorrect or self.claims_unverifiable or self.corrections_needed:
            derived_assessment = "FAIL"
        else:
            derived_assessment = "PASS"

        # Never let model-supplied prose make the deterministic assessment more
        # optimistic. Preserve explicit conservative outcomes such as ERROR.
        severity = {
            "PASS": 0,
            "PASS_WITH_CORRECTIONS": 1,
            "FAIL": 2,
            "ERROR": 3,
            "SKIPPED": 3,
        }
        if supplied_assessment not in severity:
            supplied_assessment = "ERROR"
        supplied_severity = severity[supplied_assessment]
        self.overall_assessment = (
            supplied_assessment
            if supplied_severity > severity[derived_assessment]
            else derived_assessment
        )
        return self
