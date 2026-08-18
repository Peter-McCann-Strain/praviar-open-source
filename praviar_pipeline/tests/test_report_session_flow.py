from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from praviar_pipeline.models.report_sections import ReportSection, VerificationReport
from praviar_pipeline.pipeline.report.retry_flow import ValidationRetryFlowResult
from praviar_pipeline.pipeline.report.section_generation import GeneratedSectionsResult
from praviar_pipeline.pipeline.report.session_flow import _run_report_session_flow
from praviar_pipeline.pipeline.report.verification_flow import VerificationFlowResult


@pytest.mark.asyncio
async def test_run_report_session_flow_rolls_tokens_and_models() -> None:
    section = ReportSection(
        section_id="executive_summary",
        section_title="Executive Summary",
        content="Section text",
        word_count=2,
        input_tokens=100,
        output_tokens=50,
    )
    verification_report = VerificationReport(
        total_claims_checked=10,
        claims_correct=9,
        claims_incorrect=1,
        factual_accuracy_rate=0.9,
        overall_assessment="PASS_WITH_CORRECTIONS",
    )

    claude = AsyncMock()
    claude._models = SimpleNamespace(
        triage="claude-haiku-4-5-20251001",
        analysis="claude-sonnet-4-6",
        deep="claude-opus-4-6",
    )
    claude.__aenter__.return_value = claude
    claude.__aexit__.return_value = False

    result = await _run_report_session_flow(
        claude_factory=lambda: claude,
        settings=SimpleNamespace(),
        toolkit=object(),
        context="context",
        data_store=object(),
        section_defs=[
            ("executive_summary", "Executive Summary", "prompt.txt", "report_s1_max_tokens")
        ],
        generate_section_fn=AsyncMock(),
        validation_fn=lambda sections, data_store: [],
        collect_validation_issue_descriptions_fn=lambda results: [],
        group_validation_issues_by_section_fn=lambda results: {},
        sections_needing_retry_fn=lambda grouped: set(),
        build_retry_context_fn=lambda context, issues, retry_attempt: context,
        apply_corrections_fn=lambda sections, results: sections,
        generate_sections_fn=AsyncMock(
            return_value=GeneratedSectionsResult(
                sections=[section],
                total_input=100,
                total_output=50,
            )
        ),
        validation_retry_fn=AsyncMock(
            return_value=ValidationRetryFlowResult(
                sections=[section],
                validation_issues=["issue"],
                total_input=130,
                total_output=65,
            )
        ),
        verification_flow_fn=AsyncMock(
            return_value=VerificationFlowResult(
                verification_report=verification_report,
                verify_input=40,
                verify_output=20,
                total_input=170,
                total_output=85,
            )
        ),
        total_input=10,
        total_output=5,
    )

    assert result.sections == [section]
    assert result.validation_issues == ["issue"]
    assert result.verification_report == verification_report
    assert result.verify_input == 40
    assert result.verify_output == 20
    assert result.total_input == 170
    assert result.total_output == 85
    assert result.llm_models_used == {
        "triage": "claude-haiku-4-5-20251001",
        "analysis": "claude-sonnet-4-6",
        "deep": "claude-opus-4-6",
    }
