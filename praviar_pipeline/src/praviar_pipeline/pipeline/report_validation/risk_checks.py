"""Risk and narrative deterministic report validators."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from praviar_pipeline.models.report_sections import ValidationIssue, ValidationResult
from praviar_pipeline.pipeline.report_validation.common import (
    extract_patent_risk_pairs,
    find_analysis_by_normalized_patent_id,
    normalize_patent_id,
)

if TYPE_CHECKING:
    from typing import ClassVar

    from praviar_pipeline.pipeline.report_data_store import ReportDataStore


class OverallRiskValidator:
    """Check that stated overall risk matches computed risk."""

    name = "overall_risk_match"
    _VERDICT_RE = re.compile(
        r"(?im)^\s*(?:overall\s+risk(?:\s+assessment)?|risk\s+level)\s*"
        r"[:\-—]\s*(HIGH|MEDIUM|LOW|CLEAR)\b"
    )
    _NEGATED_CLEAR_RE = re.compile(r"\b(?:NOT|NEVER)\s+CLEAR\b", re.IGNORECASE)
    _MATTER_RISK_RE = re.compile(
        r"\boverall\s+risk(?:\s+(?:is|remains))?\s*[:\-—]?\s*"
        r"(HIGH|MEDIUM|LOW|CLEAR)\b",
        re.IGNORECASE,
    )

    def validate(
        self,
        sections: list,
        data_store: ReportDataStore,
    ) -> ValidationResult:
        executive_summary = next((s for s in sections if s.section_id == "executive_summary"), None)
        if executive_summary is None:
            return ValidationResult(
                validator_name=self.name,
                passed=False,
                issues=[
                    ValidationIssue(
                        validator_name=self.name,
                        severity="error",
                        description="No executive summary section found",
                    )
                ],
            )

        expected = data_store.overall_risk.value.upper()
        stated = [match.upper() for match in self._VERDICT_RE.findall(executive_summary.content)]
        contradiction = expected == "CLEAR" and self._NEGATED_CLEAR_RE.search(
            executive_summary.content
        )
        matter_bands = {
            match.upper() for match in self._MATTER_RISK_RE.findall(executive_summary.content)
        }
        if len(stated) != 1 or stated[0] != expected or contradiction or matter_bands != {expected}:
            return ValidationResult(
                validator_name=self.name,
                passed=False,
                issues=[
                    ValidationIssue(
                        validator_name=self.name,
                        severity="error",
                        section_id="executive_summary",
                        description=(
                            "Executive summary must contain exactly one anchored "
                            f"'Overall Risk: {expected}' verdict without contradiction"
                        ),
                        expected=expected,
                        actual=", ".join(stated) or "missing",
                    )
                ],
            )

        return ValidationResult(validator_name=self.name, passed=True)


class DisclaimerValidator:
    """Check that the mandatory disclaimer is present."""

    name = "disclaimer_present"

    def validate(
        self,
        sections: list,
        _data_store: ReportDataStore,
    ) -> ValidationResult:
        all_text = "\n".join(section.content for section in sections)
        key_phrases = [
            "does not constitute legal advice",
            "should not be relied upon as a substitute",
        ]

        for phrase in key_phrases:
            if phrase.lower() in all_text.lower():
                return ValidationResult(validator_name=self.name, passed=True)

        return ValidationResult(
            validator_name=self.name,
            passed=False,
            issues=[
                ValidationIssue(
                    validator_name=self.name,
                    severity="error",
                    description="Mandatory legal disclaimer is missing from the report sections",
                )
            ],
        )


class WordCountValidator:
    """Check per-section word counts are within bounds."""

    name = "word_count_bounds"

    _MIN_WORDS: ClassVar[dict[str, int]] = {
        "executive_summary": 100,
        "key_patents": 50,
        "damages_injunction": 30,
        "invalidity": 30,
        "recommendations": 50,
        "data_quality": 30,
    }

    def validate(
        self,
        sections: list,
        _data_store: ReportDataStore,
    ) -> ValidationResult:
        issues = []
        for section in sections:
            min_words = self._MIN_WORDS.get(section.section_id, 30)
            if section.word_count < min_words:
                issues.append(
                    ValidationIssue(
                        validator_name=self.name,
                        severity="warning",
                        section_id=section.section_id,
                        description=(
                            f"Section '{section.section_id}' has {section.word_count} words "
                            f"(minimum {min_words})"
                        ),
                        expected=str(min_words),
                        actual=str(section.word_count),
                    )
                )

        return ValidationResult(
            validator_name=self.name,
            passed=len(issues) == 0,
            issues=issues,
        )


class RiskLevelValidator:
    """Check that risk levels stated near patent IDs match pipeline data."""

    name = "risk_level_match"

    def validate(
        self,
        sections: list,
        data_store: ReportDataStore,
    ) -> ValidationResult:
        issues = []

        for section in sections:
            for raw_patent_id, stated_risk in extract_patent_risk_pairs(section.content):
                normalized_patent_id = normalize_patent_id(raw_patent_id)
                analysis = find_analysis_by_normalized_patent_id(data_store, normalized_patent_id)
                if analysis is None:
                    continue

                actual_risk = analysis.risk_level.value.upper()
                if stated_risk != actual_risk:
                    issues.append(
                        ValidationIssue(
                            validator_name=self.name,
                            severity="error",
                            section_id=section.section_id,
                            description=(
                                f"Patent {raw_patent_id} stated as {stated_risk} risk "
                                f"but pipeline data shows {actual_risk}"
                            ),
                            patent_id=normalized_patent_id,
                            expected=actual_risk,
                            actual=stated_risk,
                        )
                    )

        return ValidationResult(
            validator_name=self.name,
            passed=len(issues) == 0,
            issues=issues,
        )


class CrossSectionRiskConsistencyValidator:
    """Check that the same patent isn't rated differently across sections."""

    name = "cross_section_risk_consistency"

    def validate(
        self,
        sections: list,
        data_store: ReportDataStore,
    ) -> ValidationResult:
        patent_risk_mentions: dict[str, dict[str, set[str]]] = {}

        for section in sections:
            for raw_patent_id, stated_risk in extract_patent_risk_pairs(section.content):
                normalized_patent_id = normalize_patent_id(raw_patent_id)
                section_risks = patent_risk_mentions.setdefault(normalized_patent_id, {})
                section_risks.setdefault(section.section_id, set()).add(stated_risk)

        issues = []
        for normalized_patent_id, section_risks in patent_risk_mentions.items():
            all_risks: set[str] = set()
            for risks in section_risks.values():
                all_risks |= risks

            if len(all_risks) > 1:
                # Look up canonical risk so we only flag WRONG sections, not every section
                # that mentions the patent.  Previously `len(all_risks) > 1` created issues
                # for ALL sections (including correct ones), causing unnecessary retries.
                analysis = find_analysis_by_normalized_patent_id(data_store, normalized_patent_id)
                canonical = analysis.risk_level.value.upper() if analysis else None

                sections_str = ", ".join(
                    f"{section_id}={list(risks)}" for section_id, risks in section_risks.items()
                )
                for section_id, risks in section_risks.items():
                    # Flag section if it has internal inconsistency (multiple risk levels
                    # for the same patent) OR if any of its stated risks are non-canonical.
                    has_internal_inconsistency = len(risks) > 1
                    has_non_canonical = canonical is not None and any(r != canonical for r in risks)
                    if has_internal_inconsistency or has_non_canonical:
                        issues.append(
                            ValidationIssue(
                                validator_name=self.name,
                                severity="error",
                                section_id=section_id,
                                description=(
                                    f"Patent {normalized_patent_id} has inconsistent risk levels "
                                    f"across sections: {sections_str}"
                                ),
                                patent_id=normalized_patent_id,
                            )
                        )

        return ValidationResult(
            validator_name=self.name,
            passed=len(issues) == 0,
            issues=issues,
        )
