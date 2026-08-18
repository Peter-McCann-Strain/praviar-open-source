"""Stage 3 verification helpers for unified report pipeline."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.errors import ReportIntegrityError
from praviar_pipeline.pipeline.report.deterministic_checks import run_deterministic_checks
from praviar_pipeline.pipeline.report_verifier import verify_report

if TYPE_CHECKING:
    from praviar_pipeline.clients.claude import ClaudeClient
    from praviar_pipeline.models.report_sections import ReportSection, VerificationReport
    from praviar_pipeline.pipeline.report_data_store import ReportDataStore

logger = structlog.get_logger()

MIN_VERIFICATION_ACCURACY = 0.95
PASSING_VERIFICATION_ASSESSMENTS = {"PASS", "PASS_WITH_CORRECTIONS"}


@dataclass(slots=True)
class VerificationFlowResult:
    verification_report: VerificationReport
    verify_input: int
    verify_output: int
    total_input: int
    total_output: int


def _raise_if_verification_failed(
    verification_report: VerificationReport,
    *,
    prelim_text: str,
) -> None:
    """Fail closed on verifier output that cannot safely publish."""
    assessment = str(verification_report.overall_assessment or "").strip().upper()
    violations: list[dict[str, object]] = []

    def add_violation(reason: str, value: object) -> None:
        violations.append(
            {
                "check_name": "llm_report_verification_gate",
                "severity": "block",
                "detail": reason,
                "location": "verification_report",
                "actual": value,
            }
        )

    count_values = {
        "total_claims_checked": verification_report.total_claims_checked,
        "claims_correct": verification_report.claims_correct,
        "claims_incorrect": verification_report.claims_incorrect,
        "claims_unverifiable": verification_report.claims_unverifiable,
    }
    counts_are_valid = True
    for name, value in count_values.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            counts_are_valid = False
            add_violation(
                "verification claim counts must be non-negative integers",
                {name: value},
            )

    accuracy_rate = verification_report.factual_accuracy_rate
    accuracy_is_valid = (
        isinstance(accuracy_rate, int | float)
        and not isinstance(accuracy_rate, bool)
        and math.isfinite(float(accuracy_rate))
        and 0.0 <= float(accuracy_rate) <= 1.0
    )
    if not accuracy_is_valid:
        add_violation(
            "verification factual accuracy must be a finite value between 0 and 1",
            accuracy_rate,
        )

    if counts_are_valid:
        component_total = (
            verification_report.claims_correct
            + verification_report.claims_incorrect
            + verification_report.claims_unverifiable
        )
        if component_total != verification_report.total_claims_checked:
            add_violation(
                "verification claim counts must exactly partition total claims checked",
                {
                    "total_claims_checked": verification_report.total_claims_checked,
                    "component_total": component_total,
                },
            )
        if verification_report.total_claims_checked > 0 and accuracy_is_valid:
            expected_accuracy = (
                verification_report.claims_correct / verification_report.total_claims_checked
            )
            if abs(float(accuracy_rate) - expected_accuracy) > 0.001:
                add_violation(
                    "verification factual accuracy does not match claim counts",
                    {
                        "factual_accuracy_rate": accuracy_rate,
                        "expected_accuracy_rate": expected_accuracy,
                    },
                )

    if assessment not in PASSING_VERIFICATION_ASSESSMENTS:
        add_violation("verification assessment is not publishable", assessment or "<empty>")
    if accuracy_is_valid and float(accuracy_rate) < MIN_VERIFICATION_ACCURACY:
        add_violation(
            "verification factual accuracy is below publish threshold",
            accuracy_rate,
        )
    if prelim_text.strip() and verification_report.total_claims_checked <= 0:
        add_violation(
            "verification checked zero claims for non-empty report text",
            verification_report.total_claims_checked,
        )
    if verification_report.claims_unverifiable > 0:
        add_violation(
            "verification left claims unverifiable",
            verification_report.claims_unverifiable,
        )
    if verification_report.claims_incorrect > 0:
        add_violation(
            "verification found incorrect claims that are not applied before publish",
            verification_report.claims_incorrect,
        )
    if verification_report.corrections_needed:
        add_violation(
            "verification returned unapplied corrections",
            len(verification_report.corrections_needed),
        )

    if violations:
        logger.error(
            "unified_report_verification_failed_closed",
            factual_accuracy_rate=verification_report.factual_accuracy_rate,
            total_claims_checked=verification_report.total_claims_checked,
            claims_incorrect=verification_report.claims_incorrect,
            claims_unverifiable=verification_report.claims_unverifiable,
            corrections_needed=len(verification_report.corrections_needed),
        )
        raise ReportIntegrityError(
            "Report verification failed closed; refusing to publish.",
            violations=violations,
        )


async def _run_report_verification_flow(
    claude: ClaudeClient,
    sections: list[ReportSection],
    data_store: ReportDataStore,
    *,
    total_input: int,
    total_output: int,
) -> VerificationFlowResult:
    """Run LLM verification over the assembled report sections.

    After the LLM verifier returns, a deterministic rule-based layer runs
    (see ``deterministic_checks``). Blocking violations propagate as
    ``ReportIntegrityError``; warn/redact violations are attached to the
    returned ``VerificationReport`` for the audit trail.
    """
    prelim_text = "\n\n".join(section.content for section in sections if section.word_count > 0)
    verification_report, verify_input, verify_output = await verify_report(
        claude,
        prelim_text,
        data_store,
    )
    total_input += verify_input
    total_output += verify_output
    _raise_if_verification_failed(verification_report, prelim_text=prelim_text)

    # Deterministic post-LLM integrity checks (SG-123). Raises
    # ReportIntegrityError on block-severity violations.
    deterministic_results = run_deterministic_checks(sections, data_store)
    verification_report.deterministic_check_results = deterministic_results

    violation_count = sum(len(r.violations) for r in deterministic_results)
    logger.info(
        "unified_report_stage3_complete",
        accuracy=verification_report.factual_accuracy_rate,
        corrections=len(verification_report.corrections_needed),
        deterministic_checks_run=len(deterministic_results),
        deterministic_violations=violation_count,
    )

    return VerificationFlowResult(
        verification_report=verification_report,
        verify_input=verify_input,
        verify_output=verify_output,
        total_input=total_input,
        total_output=total_output,
    )
