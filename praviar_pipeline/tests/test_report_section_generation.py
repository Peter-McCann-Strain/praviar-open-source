from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.models.report_sections import ReportSection
from praviar_pipeline.pipeline.report.section_generation import _generate_sections_unified


@pytest.mark.asyncio
async def test_generate_sections_unified_preserves_definition_order_and_rolls_tokens() -> None:
    settings = SimpleNamespace(
        report_section_concurrency=3,
        s1_tokens=101,
        s2_tokens=202,
        s3_tokens=303,
    )
    section_defs = [
        ("executive_summary", "Executive", "s1.txt", "s1_tokens"),
        ("key_patents", "Key Patents", "s2.txt", "s2_tokens"),
        ("recommendations", "Recommendations", "s3.txt", "s3_tokens"),
    ]
    captured_max_tokens: dict[str, int] = {}

    async def _generate(
        claude,
        section_id: str,
        section_title: str,
        prompt_file: str,
        max_tokens: int,
        toolkit,
        context: str,
    ) -> ReportSection:
        del claude, prompt_file, toolkit, context
        delays = {
            "executive_summary": 0.02,
            "key_patents": 0.0,
            "recommendations": 0.01,
        }
        captured_max_tokens[section_id] = max_tokens
        await asyncio.sleep(delays[section_id])
        return ReportSection(
            section_id=section_id,
            section_title=section_title,
            content=f"{section_id} content",
            word_count=5,
            input_tokens=max_tokens,
            output_tokens=max_tokens // 2,
        )

    result = await _generate_sections_unified(
        claude=object(),
        settings=settings,
        toolkit=object(),
        context="context",
        section_defs=section_defs,
        generate_section_fn=_generate,
    )

    assert [section.section_id for section in result.sections] == [
        "executive_summary",
        "key_patents",
        "recommendations",
    ]
    assert captured_max_tokens == {
        "executive_summary": 101,
        "key_patents": 202,
        "recommendations": 303,
    }
    assert result.total_input == 606
    assert result.total_output == 302


@pytest.mark.asyncio
async def test_generate_sections_unified_raises_for_failed_section() -> None:
    settings = SimpleNamespace(
        report_section_concurrency=2,
        s1_tokens=111,
        s2_tokens=222,
    )
    section_defs = [
        ("executive_summary", "Executive", "s1.txt", "s1_tokens"),
        ("key_patents", "Key Patents", "s2.txt", "s2_tokens"),
    ]

    async def _generate(
        claude,
        section_id: str,
        section_title: str,
        prompt_file: str,
        max_tokens: int,
        toolkit,
        context: str,
    ) -> ReportSection:
        del claude, prompt_file, max_tokens, toolkit, context
        if section_id == "key_patents":
            raise RuntimeError("boom")
        return ReportSection(
            section_id=section_id,
            section_title=section_title,
            content="success",
            word_count=3,
            input_tokens=90,
            output_tokens=45,
        )

    with pytest.raises(SourceUnavailableError) as exc_info:
        await _generate_sections_unified(
            claude=object(),
            settings=settings,
            toolkit=object(),
            context="context",
            section_defs=section_defs,
            generate_section_fn=_generate,
        )

    assert str(exc_info.value) == "report_section unavailable: section generation failed"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


@pytest.mark.asyncio
async def test_generate_sections_unified_cancels_sibling_sections_after_failure() -> None:
    settings = SimpleNamespace(
        report_section_concurrency=2,
        s1_tokens=111,
        s2_tokens=222,
    )
    section_defs = [
        ("executive_summary", "Executive", "s1.txt", "s1_tokens"),
        ("key_patents", "Key Patents", "s2.txt", "s2_tokens"),
    ]
    cancelled_sections: list[str] = []

    async def _generate(
        claude,
        section_id: str,
        section_title: str,
        prompt_file: str,
        max_tokens: int,
        toolkit,
        context: str,
    ) -> ReportSection:
        del claude, section_title, prompt_file, max_tokens, toolkit, context
        if section_id == "key_patents":
            raise RuntimeError("boom")
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled_sections.append(section_id)
            raise
        raise AssertionError("sibling section was not cancelled")

    with pytest.raises(SourceUnavailableError):
        await _generate_sections_unified(
            claude=object(),
            settings=settings,
            toolkit=object(),
            context="context",
            section_defs=section_defs,
            generate_section_fn=_generate,
        )

    assert cancelled_sections == ["executive_summary"]
