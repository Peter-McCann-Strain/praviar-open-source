from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from praviar_pipeline.errors import ReportIntegrityError
from praviar_pipeline.models.report_sections import (
    CorrectionEntry,
    ReportSection,
    VerificationReport,
)
from praviar_pipeline.pipeline.report.verification_flow import (
    _raise_if_verification_failed,
    _run_report_verification_flow,
)


def _unchecked_verification_report(**overrides) -> VerificationReport:
    values = {
        "overall_assessment": "PASS",
        "total_claims_checked": 10,
        "claims_correct": 10,
        "claims_incorrect": 0,
        "claims_unverifiable": 0,
        "factual_accuracy_rate": 1.0,
        "corrections_needed": [],
        "omissions_found": [],
        "deterministic_check_results": [],
    }
    values.update(overrides)
    return VerificationReport.model_construct(**values)


@pytest.mark.asyncio
async def test_run_report_verification_flow_rolls_tokens_and_skips_empty_sections() -> None:
    sections = [
        ReportSection(
            section_id="executive_summary",
            section_title="Executive",
            content="First section content",
            word_count=3,
        ),
        ReportSection(
            section_id="data_quality",
            section_title="Data Quality",
            content="",
            word_count=0,
        ),
        ReportSection(
            section_id="recommendations",
            section_title="Recommendations",
            content="Second section content",
            word_count=3,
        ),
    ]
    verification_report = VerificationReport(
        overall_assessment="PASS",
        total_claims_checked=10,
        claims_correct=10,
        factual_accuracy_rate=1.0,
    )
    claude = object()
    data_store = object()

    with (
        patch(
            "praviar_pipeline.pipeline.report.verification_flow.verify_report",
            new=AsyncMock(return_value=(verification_report, 120, 45)),
        ) as verify_report_mock,
        patch(
            "praviar_pipeline.pipeline.report.verification_flow.run_deterministic_checks",
            return_value=[],
        ) as deterministic_checks_mock,
    ):
        result = await _run_report_verification_flow(
            claude,
            sections,
            data_store,
            total_input=1000,
            total_output=500,
        )

    verify_report_mock.assert_awaited_once_with(
        claude,
        "First section content\n\nSecond section content",
        data_store,
    )
    deterministic_checks_mock.assert_called_once_with(sections, data_store)
    assert result.verification_report is verification_report
    assert result.verify_input == 120
    assert result.verify_output == 45
    assert result.total_input == 1120
    assert result.total_output == 545


@pytest.mark.parametrize(
    ("verification_report", "expected_detail"),
    [
        (
            VerificationReport(
                overall_assessment="ERROR",
                total_claims_checked=10,
                claims_correct=10,
                factual_accuracy_rate=1.0,
            ),
            "assessment",
        ),
        (
            VerificationReport(
                overall_assessment="FAIL",
                total_claims_checked=10,
                claims_correct=10,
                factual_accuracy_rate=1.0,
            ),
            "assessment",
        ),
        (
            VerificationReport(
                overall_assessment="SKIPPED",
                total_claims_checked=10,
                claims_correct=10,
                factual_accuracy_rate=1.0,
            ),
            "assessment",
        ),
        (
            VerificationReport(
                overall_assessment="PASS_WITH_CORRECTIONS",
                total_claims_checked=10,
                claims_correct=9,
                claims_incorrect=1,
                factual_accuracy_rate=0.9,
            ),
            "accuracy",
        ),
        (
            VerificationReport(
                overall_assessment="PASS",
                total_claims_checked=10,
                claims_correct=9,
                claims_unverifiable=1,
                factual_accuracy_rate=1.0,
            ),
            "unverifiable",
        ),
        (
            VerificationReport(
                overall_assessment="PASS",
                total_claims_checked=0,
                claims_correct=0,
                factual_accuracy_rate=1.0,
            ),
            "zero claims",
        ),
        (
            VerificationReport(
                overall_assessment="PASS",
                total_claims_checked=10,
                claims_correct=9,
                claims_incorrect=1,
                factual_accuracy_rate=1.0,
            ),
            "incorrect claims",
        ),
        (
            VerificationReport(
                overall_assessment="PASS",
                total_claims_checked=10,
                claims_correct=10,
                factual_accuracy_rate=1.0,
                corrections_needed=[
                    CorrectionEntry(
                        section_id="executive_summary",
                        claim_text="bad claim",
                        correct_value="correct claim",
                    )
                ],
            ),
            "unapplied corrections",
        ),
    ],
)
def test_raise_if_verification_failed_blocks_unpublishable_reports(
    verification_report: VerificationReport,
    expected_detail: str,
) -> None:
    with pytest.raises(ReportIntegrityError) as exc_info:
        _raise_if_verification_failed(
            verification_report,
            prelim_text="Customer visible report text.",
        )

    assert expected_detail in str(exc_info.value.violations)


@pytest.mark.parametrize(
    "verification_kwargs",
    [
        {
            "overall_assessment": "PASS",
            "total_claims_checked": 10,
            "claims_correct": 10,
            "factual_accuracy_rate": float("nan"),
        },
        {
            "overall_assessment": "PASS",
            "total_claims_checked": 10,
            "claims_correct": 10,
            "factual_accuracy_rate": float("inf"),
        },
        {
            "overall_assessment": "PASS",
            "total_claims_checked": 10,
            "claims_correct": 10,
            "factual_accuracy_rate": 1.1,
        },
        {
            "overall_assessment": "PASS",
            "total_claims_checked": 10,
            "claims_correct": -10,
            "factual_accuracy_rate": 1.0,
        },
        {
            "overall_assessment": "PASS",
            "total_claims_checked": 10,
            "claims_correct": 999,
            "factual_accuracy_rate": 1.0,
        },
    ],
)
def test_verification_report_rejects_impossible_numeric_evidence(
    verification_kwargs: dict,
) -> None:
    with pytest.raises(ValidationError):
        VerificationReport(**verification_kwargs)


def test_verification_report_requires_complete_claim_categorization() -> None:
    with pytest.raises(ValidationError, match="categorized claim counts"):
        VerificationReport(
            overall_assessment="PASS",
            total_claims_checked=10,
            claims_correct=9,
            factual_accuracy_rate=0.9,
        )


def test_verification_report_recomputes_accuracy_and_fail_closed_assessment() -> None:
    report = VerificationReport(
        overall_assessment="PASS",
        total_claims_checked=10,
        claims_correct=9,
        claims_incorrect=1,
        factual_accuracy_rate=1.0,
    )

    assert report.factual_accuracy_rate == 0.9
    assert report.overall_assessment == "FAIL"


def test_verification_report_maps_unknown_assessment_to_error() -> None:
    report = VerificationReport(
        overall_assessment="MODEL_UNCERTAIN",
        total_claims_checked=1,
        claims_correct=1,
        factual_accuracy_rate=1.0,
    )

    assert report.factual_accuracy_rate == 1.0
    assert report.overall_assessment == "ERROR"


@pytest.mark.parametrize(
    ("verification_report", "expected_detail"),
    [
        (
            _unchecked_verification_report(factual_accuracy_rate=float("nan")),
            "finite value",
        ),
        (
            _unchecked_verification_report(factual_accuracy_rate=float("inf")),
            "finite value",
        ),
        (
            _unchecked_verification_report(factual_accuracy_rate=1.1),
            "between 0 and 1",
        ),
        (
            _unchecked_verification_report(claims_correct=-10),
            "non-negative integers",
        ),
        (
            _unchecked_verification_report(claims_correct=999),
            "exactly partition",
        ),
        (
            _unchecked_verification_report(
                total_claims_checked=10,
                claims_correct=9,
                factual_accuracy_rate=0.9,
            ),
            "exactly partition",
        ),
        (
            _unchecked_verification_report(
                total_claims_checked=10,
                claims_correct=9,
                factual_accuracy_rate=1.0,
            ),
            "does not match claim counts",
        ),
    ],
)
def test_raise_if_verification_failed_blocks_impossible_numeric_evidence(
    verification_report: VerificationReport,
    expected_detail: str,
) -> None:
    with pytest.raises(ReportIntegrityError) as exc_info:
        _raise_if_verification_failed(
            verification_report,
            prelim_text="Customer visible report text.",
        )

    assert expected_detail in str(exc_info.value.violations)


@pytest.mark.asyncio
async def test_run_report_verification_flow_blocks_failed_llm_verification_before_checks() -> None:
    sections = [
        ReportSection(
            section_id="executive_summary",
            section_title="Executive",
            content="Customer-visible report text.",
            word_count=3,
        )
    ]
    verification_report = VerificationReport(
        overall_assessment="ERROR",
        total_claims_checked=0,
        claims_correct=0,
        factual_accuracy_rate=0.0,
    )

    with (
        patch(
            "praviar_pipeline.pipeline.report.verification_flow.verify_report",
            new=AsyncMock(return_value=(verification_report, 12, 4)),
        ),
        patch(
            "praviar_pipeline.pipeline.report.verification_flow.run_deterministic_checks"
        ) as deterministic_checks,
        pytest.raises(ReportIntegrityError, match="verification failed closed"),
    ):
        await _run_report_verification_flow(
            object(),
            sections,
            object(),
            total_input=100,
            total_output=50,
        )

    deterministic_checks.assert_not_called()
