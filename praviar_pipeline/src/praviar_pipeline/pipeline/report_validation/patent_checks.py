"""Patent-centric deterministic report validators."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from praviar_pipeline.models.analysis import RiskLevel
from praviar_pipeline.models.report_sections import ValidationIssue, ValidationResult
from praviar_pipeline.pipeline.report_validation.common import (
    PATENT_ASSIGNEE_RE,
    PATENT_DATE_RE,
    PTAB_RE,
    extract_patent_ids,
    find_analysis_by_normalized_patent_id,
    normalize_assignee,
    normalize_patent_id,
    strip_kind_code,
)

if TYPE_CHECKING:
    from praviar_pipeline.pipeline.report_data_store import ReportDataStore


class PatentIdValidator:
    """Check that every patent ID in text exists in pipeline data."""

    name = "patent_id_exists"

    def validate(
        self,
        sections: list,
        data_store: ReportDataStore,
    ) -> ValidationResult:
        known_ids = {normalize_patent_id(pid) for pid in data_store.all_patent_ids()}
        # Also build a kind-code-agnostic set so bibliography refs like "US2011178396"
        # match pipeline data that stores "US2011178396A1".
        known_ids_no_kind = {strip_kind_code(pid) for pid in known_ids}
        issues = []

        for section in sections:
            for patent_id in extract_patent_ids(section.content):
                if (
                    patent_id not in known_ids
                    and strip_kind_code(patent_id) not in known_ids_no_kind
                ):
                    issues.append(
                        ValidationIssue(
                            validator_name=self.name,
                            severity="warning",
                            section_id=section.section_id,
                            description=f"Patent ID {patent_id} not found in pipeline data",
                            patent_id=patent_id,
                        )
                    )

        return ValidationResult(
            validator_name=self.name,
            passed=len(issues) == 0,
            issues=issues,
        )


class HighRiskCompletenessValidator:
    """Check that all HIGH-risk patents are mentioned in key sections."""

    name = "high_risk_completeness"

    def validate(
        self,
        sections: list,
        data_store: ReportDataStore,
    ) -> ValidationResult:
        high_patents = data_store.patents_by_risk(RiskLevel.HIGH)
        if not high_patents:
            return ValidationResult(validator_name=self.name, passed=True)

        key_sections = {"executive_summary", "key_patents"}
        mentioned_in_key = set()
        for section in sections:
            if section.section_id in key_sections:
                mentioned_in_key |= extract_patent_ids(section.content)

        issues = []
        for analysis in high_patents:
            normalized_patent_id = normalize_patent_id(analysis.patent_id)
            if normalized_patent_id not in mentioned_in_key:
                issues.append(
                    ValidationIssue(
                        validator_name=self.name,
                        severity="error",
                        section_id="key_patents",
                        description=(
                            f"HIGH-risk patent {analysis.patent_id} not mentioned in "
                            f"executive summary or key patents section"
                        ),
                        patent_id=analysis.patent_id,
                    )
                )

        return ValidationResult(
            validator_name=self.name,
            passed=len(issues) == 0,
            issues=issues,
        )


class PtabFormatValidator:
    """Check PTAB proceeding numbers are valid format and exist in data."""

    name = "ptab_format"

    def validate(
        self,
        sections: list,
        data_store: ReportDataStore,
    ) -> ValidationResult:
        known_ptab = set()
        for patent_id in data_store.all_patent_ids():
            invalidity = data_store.get_invalidity(patent_id)
            if invalidity and hasattr(invalidity, "ptab") and invalidity.ptab:
                for proceeding in invalidity.ptab.proceedings:
                    known_ptab.add(proceeding.proceeding_number)

        issues = []
        for section in sections:
            proceeding_numbers = {match.group(0) for match in PTAB_RE.finditer(section.content)}
            for proceeding_number in proceeding_numbers:
                if known_ptab and proceeding_number not in known_ptab:
                    issues.append(
                        ValidationIssue(
                            validator_name=self.name,
                            severity="warning",
                            section_id=section.section_id,
                            description=(
                                f"PTAB proceeding {proceeding_number} not found in pipeline data"
                            ),
                        )
                    )

        return ValidationResult(
            validator_name=self.name,
            passed=len(issues) == 0,
            issues=issues,
        )


class DateValidator:
    """Check that expiry dates near patent IDs match pipeline data."""

    name = "date_match"

    def validate(
        self,
        sections: list,
        data_store: ReportDataStore,
    ) -> ValidationResult:
        issues = []

        for section in sections:
            for match in PATENT_DATE_RE.finditer(section.content):
                raw_patent_id = match.group(1)
                raw_date = match.group(2)
                normalized_patent_id = normalize_patent_id(raw_patent_id)
                analysis = find_analysis_by_normalized_patent_id(data_store, normalized_patent_id)
                if analysis is None or analysis.expiry_date is None:
                    continue

                try:
                    stated_date = date.fromisoformat(raw_date.replace("/", "-"))
                except ValueError:
                    continue

                actual_date = analysis.expiry_date
                if abs((stated_date - actual_date).days) > 1:
                    issues.append(
                        ValidationIssue(
                            validator_name=self.name,
                            severity="error",
                            section_id=section.section_id,
                            description=(
                                f"Patent {raw_patent_id} expiry stated as {stated_date} "
                                f"but pipeline data shows {actual_date}"
                            ),
                            patent_id=normalized_patent_id,
                            expected=str(actual_date),
                            actual=str(stated_date),
                        )
                    )

        return ValidationResult(
            validator_name=self.name,
            passed=len(issues) == 0,
            issues=issues,
        )


class AssigneeValidator:
    """Check that assignee names near patent IDs match pipeline data."""

    name = "assignee_match"

    def validate(
        self,
        sections: list,
        data_store: ReportDataStore,
    ) -> ValidationResult:
        issues = []

        for section in sections:
            for match in PATENT_ASSIGNEE_RE.finditer(section.content):
                raw_patent_id = match.group(1)
                stated_assignee = match.group(2).strip()
                normalized_patent_id = normalize_patent_id(raw_patent_id)
                analysis = find_analysis_by_normalized_patent_id(data_store, normalized_patent_id)
                if analysis is None:
                    continue

                actual_assignee = analysis.assignee
                normalized_stated = normalize_assignee(stated_assignee)
                normalized_actual = normalize_assignee(actual_assignee)

                if normalized_stated == normalized_actual:
                    continue
                if normalized_stated in normalized_actual or normalized_actual in normalized_stated:
                    continue

                issues.append(
                    ValidationIssue(
                        validator_name=self.name,
                        severity="warning",
                        section_id=section.section_id,
                        description=(
                            f"Patent {raw_patent_id} assignee stated as '{stated_assignee}' "
                            f"but pipeline data shows '{actual_assignee}'"
                        ),
                        patent_id=normalized_patent_id,
                        expected=actual_assignee,
                        actual=stated_assignee,
                    )
                )

        return ValidationResult(
            validator_name=self.name,
            passed=len(issues) == 0,
            issues=issues,
        )
