"""Claude session orchestration for unified report generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from praviar_pipeline.models.report_common import REPORT_DISCLAIMER
from praviar_pipeline.models.report_sections import ReportSection

_DISCLAIMER_SECTION = ReportSection(
    section_id="disclaimer",
    section_title="IMPORTANT DISCLAIMER",
    content=REPORT_DISCLAIMER,
    word_count=len(REPORT_DISCLAIMER.split()),
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from praviar_pipeline.agents.tools.report_data_tools import ReportDataToolkit
    from praviar_pipeline.clients.claude import ClaudeClient
    from praviar_pipeline.config import Settings
    from praviar_pipeline.models.report_sections import (
        ValidationResult,
        VerificationReport,
    )
    from praviar_pipeline.pipeline.report.retry_flow import ValidationRetryFlowResult
    from praviar_pipeline.pipeline.report.section_generation import GeneratedSectionsResult
    from praviar_pipeline.pipeline.report.verification_flow import VerificationFlowResult
    from praviar_pipeline.pipeline.report_data_store import ReportDataStore


@dataclass(slots=True)
class ReportSessionFlowResult:
    sections: list[ReportSection]
    validation_issues: list[str]
    verification_report: VerificationReport
    verify_input: int
    verify_output: int
    total_input: int
    total_output: int
    llm_models_used: dict[str, str]


async def _run_report_session_flow(
    *,
    claude_factory: Callable[[], ClaudeClient],
    settings: Settings,
    toolkit: ReportDataToolkit,
    context: str,
    data_store: ReportDataStore,
    section_defs: Sequence[tuple[str, str, str, str]],
    generate_section_fn: Callable,
    validation_fn: Callable[[list[ReportSection], ReportDataStore], list[ValidationResult]],
    collect_validation_issue_descriptions_fn: Callable,
    group_validation_issues_by_section_fn: Callable,
    sections_needing_retry_fn: Callable,
    build_retry_context_fn: Callable,
    apply_corrections_fn: Callable,
    generate_sections_fn: Callable[..., Awaitable[GeneratedSectionsResult]],
    validation_retry_fn: Callable[..., Awaitable[ValidationRetryFlowResult]],
    verification_flow_fn: Callable[..., Awaitable[VerificationFlowResult]],
    total_input: int,
    total_output: int,
) -> ReportSessionFlowResult:
    """Run the Claude-backed section generation and verification stages."""
    async with claude_factory() as claude:
        generated_sections = await generate_sections_fn(
            claude=claude,
            settings=settings,
            toolkit=toolkit,
            context=context,
            section_defs=section_defs,
            generate_section_fn=generate_section_fn,
        )
        sections = [*generated_sections.sections, _DISCLAIMER_SECTION]
        total_input += generated_sections.total_input
        total_output += generated_sections.total_output

        retry_flow = await validation_retry_fn(
            claude=claude,
            settings=settings,
            toolkit=toolkit,
            context=context,
            sections=sections,
            data_store=data_store,
            section_defs=section_defs,
            generate_section_fn=generate_section_fn,
            validation_fn=validation_fn,
            collect_validation_issue_descriptions_fn=collect_validation_issue_descriptions_fn,
            group_validation_issues_by_section_fn=group_validation_issues_by_section_fn,
            sections_needing_retry_fn=sections_needing_retry_fn,
            build_retry_context_fn=build_retry_context_fn,
            apply_corrections_fn=apply_corrections_fn,
            total_input=total_input,
            total_output=total_output,
        )
        sections = retry_flow.sections
        validation_issues = retry_flow.validation_issues
        total_input = retry_flow.total_input
        total_output = retry_flow.total_output

        verification_flow = await verification_flow_fn(
            claude,
            sections,
            data_store,
            total_input=total_input,
            total_output=total_output,
        )

        return ReportSessionFlowResult(
            sections=sections,
            validation_issues=validation_issues,
            verification_report=verification_flow.verification_report,
            verify_input=verification_flow.verify_input,
            verify_output=verification_flow.verify_output,
            total_input=verification_flow.total_input,
            total_output=verification_flow.total_output,
            llm_models_used={
                "triage": claude._models.triage,
                "analysis": claude._models.analysis,
                "deep": claude._models.deep,
            },
        )
