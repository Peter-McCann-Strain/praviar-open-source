"""Retry-flow helpers for unified report pipeline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.errors import ReportIntegrityError
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from praviar_pipeline.agents.tools.report_data_tools import ReportDataToolkit
    from praviar_pipeline.clients.claude import ClaudeClient
    from praviar_pipeline.config import Settings
    from praviar_pipeline.models.report_sections import ReportSection, ValidationResult
    from praviar_pipeline.pipeline.report_data_store import ReportDataStore

logger = structlog.get_logger()


@dataclass(slots=True)
class ValidationRetryFlowResult:
    sections: list[ReportSection]
    validation_issues: list[str]
    total_input: int
    total_output: int


def _residual_error_issue_descriptions(validation_results: list[ValidationResult]) -> list[str]:
    return [
        issue.description
        for validation_result in validation_results
        for issue in validation_result.issues
        if issue.severity == "error"
    ]


async def _run_validation_retry_flow(
    *,
    claude: ClaudeClient,
    settings: Settings,
    toolkit: ReportDataToolkit,
    context: str,
    sections: list[ReportSection],
    data_store: ReportDataStore,
    section_defs: Sequence[tuple[str, str, str, str]],
    generate_section_fn: Callable[
        [ClaudeClient, str, str, str, int, ReportDataToolkit, str],
        Awaitable[ReportSection],
    ],
    validation_fn: Callable[[list[ReportSection], ReportDataStore], list[ValidationResult]],
    collect_validation_issue_descriptions_fn: Callable[[list[ValidationResult]], list[str]],
    group_validation_issues_by_section_fn: Callable[
        [list[ValidationResult]],
        dict[str, list[str]],
    ],
    sections_needing_retry_fn: Callable[[dict[str, list[str]]], set[str]],
    build_retry_context_fn: Callable[[str, list[str], int], str],
    apply_corrections_fn: Callable[
        [list[ReportSection], list[ValidationResult]],
        list[ReportSection],
    ],
    total_input: int,
    total_output: int,
) -> ValidationRetryFlowResult:
    """Run deterministic validation and retry failed sections if needed."""
    validation_results = validation_fn(sections, data_store)
    validation_issues = collect_validation_issue_descriptions_fn(validation_results)

    logger.info(
        "unified_report_stage2_initial",
        validators_passed=sum(1 for vr in validation_results if vr.passed),
        validators_total=len(validation_results),
    )

    if validation_issues:
        sections = apply_corrections_fn(sections, validation_results)

    max_retries = settings.report_max_section_retries
    if max_retries > 0 and validation_issues:
        # Re-validate after corrections so retry targets only sections that corrections
        # could not fix — avoids retrying sections whose issues were already resolved,
        # which would throw away correct content and risk introducing new errors.
        post_correction_results = validation_fn(sections, data_store)
        validation_issues = collect_validation_issue_descriptions_fn(post_correction_results)
        section_issues = group_validation_issues_by_section_fn(post_correction_results)
        sections_needing_retry = sections_needing_retry_fn(section_issues)

        for retry_attempt in range(max_retries):
            if not sections_needing_retry:
                break

            logger.warning(
                "unified_report_section_retry",
                attempt=retry_attempt + 1,
                max_retries=max_retries,
                sections=list(sections_needing_retry),
            )

            retry_tasks = []
            retry_indices = []
            for i, section in enumerate(sections):
                if section.section_id not in sections_needing_retry:
                    continue

                issues_for_section = section_issues.get(section.section_id, [])
                retry_context = build_retry_context_fn(
                    context,
                    issues_for_section,
                    retry_attempt,
                )

                sec_def = next(
                    (
                        definition
                        for definition in section_defs
                        if definition[0] == section.section_id
                    ),
                    None,
                )
                if sec_def is None:
                    continue

                _, title, prompt_file, config_key = sec_def
                max_tokens = getattr(settings, config_key, 16384)
                retry_tasks.append(
                    generate_section_fn(
                        claude,
                        section.section_id,
                        title,
                        prompt_file,
                        max_tokens,
                        toolkit,
                        retry_context,
                    )
                )
                retry_indices.append(i)

            retry_results = await asyncio.gather(*retry_tasks, return_exceptions=True)

            for idx, result in zip(retry_indices, retry_results, strict=False):
                if isinstance(result, BaseException):
                    logger.error(
                        "section_retry_failed",
                        section=sections[idx].section_id,
                        error_type=safe_exception_type(result),
                    )
                else:
                    total_input += result.input_tokens
                    total_output += result.output_tokens
                    sections[idx] = result

            validation_results = validation_fn(sections, data_store)
            validation_issues = collect_validation_issue_descriptions_fn(validation_results)
            section_issues = group_validation_issues_by_section_fn(validation_results)

            if validation_issues:
                sections = apply_corrections_fn(sections, validation_results)

            sections_needing_retry = sections_needing_retry_fn(section_issues)

    # Corrections are applied AFTER the last validation pass (either in the loop or at
    # line 82 above). Re-validate on the corrected sections so the error check below
    # reflects the true post-correction state rather than stale pre-correction results.
    if validation_issues:
        validation_results = validation_fn(sections, data_store)
        validation_issues = collect_validation_issue_descriptions_fn(validation_results)

    if validation_issues:
        logger.warning(
            "unified_report_validation_residual_issues",
        )
    residual_error_issues = _residual_error_issue_descriptions(validation_results)
    if residual_error_issues:
        raise ReportIntegrityError(
            "report validation failed closed after retries",
            violations=[
                {
                    "check_name": "report_section_validation",
                    "severity": "block",
                    "detail": issue,
                }
                for issue in residual_error_issues
            ],
            step="step8_unified_report_validation",
        )

    logger.info(
        "unified_report_stage2_complete",
        validators_passed=sum(1 for vr in validation_results if vr.passed),
        validators_total=len(validation_results),
    )

    return ValidationRetryFlowResult(
        sections=sections,
        validation_issues=validation_issues,
        total_input=total_input,
        total_output=total_output,
    )
