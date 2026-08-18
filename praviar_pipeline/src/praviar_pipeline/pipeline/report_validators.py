"""Deterministic validators for report fact-checking."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import structlog

from praviar_pipeline.pipeline.report_validation.common import (
    extract_patent_ids as _extract_patent_ids,
)
from praviar_pipeline.pipeline.report_validation.common import (
    normalize_assignee as _normalize_assignee,
)
from praviar_pipeline.pipeline.report_validation.common import (
    normalize_patent_id as _normalize_patent_id,
)
from praviar_pipeline.pipeline.report_validation.corrections import apply_corrections
from praviar_pipeline.pipeline.report_validation.patent_checks import (
    AssigneeValidator,
    DateValidator,
    HighRiskCompletenessValidator,
    PatentIdValidator,
    PtabFormatValidator,
)
from praviar_pipeline.pipeline.report_validation.risk_checks import (
    CrossSectionRiskConsistencyValidator,
    DisclaimerValidator,
    OverallRiskValidator,
    RiskLevelValidator,
    WordCountValidator,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.report_sections import ValidationResult
    from praviar_pipeline.pipeline.report_data_store import ReportDataStore

logger = structlog.get_logger()

__all__ = [
    "ALL_VALIDATORS",
    "AssigneeValidator",
    "CrossSectionRiskConsistencyValidator",
    "DateValidator",
    "DisclaimerValidator",
    "HighRiskCompletenessValidator",
    "OverallRiskValidator",
    "PatentIdValidator",
    "PtabFormatValidator",
    "RiskLevelValidator",
    "WordCountValidator",
    "_extract_patent_ids",
    "_normalize_assignee",
    "_normalize_patent_id",
    "apply_corrections",
    "run_deterministic_validators",
]


class ReportValidator(Protocol):
    def validate(
        self,
        sections: list,
        data_store: ReportDataStore,
    ) -> ValidationResult: ...


ALL_VALIDATORS: list[ReportValidator] = [
    PatentIdValidator(),
    HighRiskCompletenessValidator(),
    OverallRiskValidator(),
    DisclaimerValidator(),
    WordCountValidator(),
    PtabFormatValidator(),
    RiskLevelValidator(),
    CrossSectionRiskConsistencyValidator(),
    DateValidator(),
    AssigneeValidator(),
]


def run_deterministic_validators(
    sections: list,
    data_store: ReportDataStore,
) -> list[ValidationResult]:
    """Run all deterministic validators on the generated sections."""
    results = []
    for validator in ALL_VALIDATORS:
        result = validator.validate(sections, data_store)
        if not result.passed:
            logger.warning(
                "report_validation_failed",
                validator=result.validator_name,
                issues_count=len(result.issues),
            )
        results.append(result)

    passed = sum(1 for result in results if result.passed)
    total = len(results)
    logger.info(
        "report_validation_complete",
        passed=passed,
        total=total,
        all_passed=passed == total,
    )

    return results
