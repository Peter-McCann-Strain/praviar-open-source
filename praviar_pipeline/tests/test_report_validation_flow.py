"""Tests for unified report validation retry flow."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from praviar_pipeline.errors import ReportIntegrityError
from praviar_pipeline.models.report_sections import (
    ReportSection,
    ValidationIssue,
    ValidationResult,
)
from praviar_pipeline.pipeline.report.retry_flow import _run_validation_retry_flow
from praviar_pipeline.pipeline.report.validation_flow import (
    _build_retry_context,
    _collect_validation_issue_descriptions,
    _group_validation_issues_by_section,
    _sections_needing_retry,
)

from .helpers import make_claude_client_mock


class TestValidationRetryFlow:
    async def test_retries_failed_sections_and_counts_retry_tokens(self):
        claude = make_claude_client_mock()
        settings = SimpleNamespace(
            report_max_section_retries=1,
            report_s1_max_tokens=2048,
            report_s2_max_tokens=4096,
        )
        sections = [
            ReportSection(
                section_id="executive_summary",
                section_title="1. EXECUTIVE SUMMARY",
                content="initial summary",
                word_count=2,
                input_tokens=70,
                output_tokens=30,
            ),
            ReportSection(
                section_id="key_patents",
                section_title="2. KEY PATENT ANALYSIS",
                content="stable content",
                word_count=2,
                input_tokens=30,
                output_tokens=20,
            ),
        ]
        section_defs = [
            (
                "executive_summary",
                "1. EXECUTIVE SUMMARY",
                "report_s1_executive.txt",
                "report_s1_max_tokens",
            ),
            (
                "key_patents",
                "2. KEY PATENT ANALYSIS",
                "report_s2_key_patents.txt",
                "report_s2_max_tokens",
            ),
        ]
        retry_contexts: list[str] = []
        validation_calls = 0

        async def _generate_section(
            claude_arg,
            section_id,
            section_title,
            prompt_file,
            max_tokens,
            toolkit,
            context,
        ):
            retry_contexts.append(context)
            assert claude_arg is claude
            assert section_id == "executive_summary"
            assert section_title == "1. EXECUTIVE SUMMARY"
            assert prompt_file == "report_s1_executive.txt"
            assert max_tokens == 2048
            assert toolkit is not None
            return ReportSection(
                section_id=section_id,
                section_title=section_title,
                content="repaired summary",
                word_count=3,
                input_tokens=11,
                output_tokens=7,
            )

        def _validate(sections_arg, data_store_arg):
            nonlocal validation_calls
            validation_calls += 1
            assert data_store_arg is not None
            # Calls 1 and 2: initial validation and post-correction re-validate both
            # return errors so the retry is triggered (corrections did not fix it).
            # Call 3 (post-retry): passes — the retried section fixed the problem.
            if validation_calls <= 2:
                return [
                    ValidationResult(
                        validator_name="risk-check",
                        passed=False,
                        issues=[
                            ValidationIssue(
                                validator_name="risk-check",
                                section_id="executive_summary",
                                description="Missing risk level in summary.",
                                severity="error",
                            ),
                        ],
                    )
                ]
            return [
                ValidationResult(
                    validator_name="risk-check",
                    passed=True,
                    issues=[],
                )
            ]

        result = await _run_validation_retry_flow(
            claude=claude,
            settings=settings,
            toolkit=SimpleNamespace(),
            context="Compound: test compound",
            sections=sections,
            data_store=SimpleNamespace(),
            section_defs=section_defs,
            generate_section_fn=_generate_section,
            validation_fn=_validate,
            collect_validation_issue_descriptions_fn=_collect_validation_issue_descriptions,
            group_validation_issues_by_section_fn=_group_validation_issues_by_section,
            sections_needing_retry_fn=_sections_needing_retry,
            build_retry_context_fn=_build_retry_context,
            apply_corrections_fn=lambda current_sections, validation_results: current_sections,
            total_input=100,
            total_output=50,
        )

        # 3 calls: initial, post-correction re-validate, post-retry.
        assert validation_calls == 3
        assert len(retry_contexts) == 1
        assert "Missing risk level in summary." in retry_contexts[0]
        assert "attempt 2" in retry_contexts[0]
        assert result.sections[0].content == "repaired summary"
        assert result.sections[1].content == "stable content"
        assert result.total_input == 111
        assert result.total_output == 57
        assert result.validation_issues == []

    async def test_residual_error_validation_issue_fails_closed_after_retries(self):
        claude = make_claude_client_mock()
        settings = SimpleNamespace(
            report_max_section_retries=0,
            report_s1_max_tokens=2048,
        )
        sections = [
            ReportSection(
                section_id="executive_summary",
                section_title="1. EXECUTIVE SUMMARY",
                content="bad summary",
                word_count=2,
            )
        ]

        def _validate(_sections_arg, _data_store_arg):
            return [
                ValidationResult(
                    validator_name="risk-check",
                    passed=False,
                    issues=[
                        ValidationIssue(
                            validator_name="risk-check",
                            severity="error",
                            section_id="executive_summary",
                            description="Missing HIGH risk patent from summary.",
                        )
                    ],
                )
            ]

        with pytest.raises(ReportIntegrityError, match="validation failed closed"):
            await _run_validation_retry_flow(
                claude=claude,
                settings=settings,
                toolkit=SimpleNamespace(),
                context="Compound: test compound",
                sections=sections,
                data_store=SimpleNamespace(),
                section_defs=[],
                generate_section_fn=None,
                validation_fn=_validate,
                collect_validation_issue_descriptions_fn=_collect_validation_issue_descriptions,
                group_validation_issues_by_section_fn=_group_validation_issues_by_section,
                sections_needing_retry_fn=_sections_needing_retry,
                build_retry_context_fn=_build_retry_context,
                apply_corrections_fn=lambda current_sections, _validation_results: current_sections,
                total_input=0,
                total_output=0,
            )

    async def test_residual_warning_validation_issue_remains_nonfatal(self):
        claude = make_claude_client_mock()
        settings = SimpleNamespace(
            report_max_section_retries=0,
            report_s1_max_tokens=2048,
        )
        sections = [
            ReportSection(
                section_id="executive_summary",
                section_title="1. EXECUTIVE SUMMARY",
                content="wordy summary",
                word_count=2,
            )
        ]

        def _validate(_sections_arg, _data_store_arg):
            return [
                ValidationResult(
                    validator_name="style-check",
                    passed=False,
                    issues=[
                        ValidationIssue(
                            validator_name="style-check",
                            severity="warning",
                            section_id="executive_summary",
                            description="Summary is longer than preferred.",
                        )
                    ],
                )
            ]

        result = await _run_validation_retry_flow(
            claude=claude,
            settings=settings,
            toolkit=SimpleNamespace(),
            context="Compound: test compound",
            sections=sections,
            data_store=SimpleNamespace(),
            section_defs=[],
            generate_section_fn=None,
            validation_fn=_validate,
            collect_validation_issue_descriptions_fn=_collect_validation_issue_descriptions,
            group_validation_issues_by_section_fn=_group_validation_issues_by_section,
            sections_needing_retry_fn=_sections_needing_retry,
            build_retry_context_fn=_build_retry_context,
            apply_corrections_fn=lambda current_sections, _validation_results: current_sections,
            total_input=0,
            total_output=0,
        )

        assert result.sections == sections
        assert result.validation_issues == ["Summary is longer than preferred."]
