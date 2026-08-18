from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from praviar_pipeline.errors import SearchSourceFailedError
from praviar_pipeline.models.analysis import PatentAnalysis, RiskLevel
from praviar_pipeline.models.search_loop import SearchLoopResult
from praviar_pipeline.pipeline.runtime.pipeline_steps import (
    run_analysis_step,
    run_search_step,
)


@pytest.mark.asyncio
async def test_run_search_step_uses_search_loop_when_flag_enabled() -> None:
    search_loop_result = SearchLoopResult(iterations_completed=2)
    run_search_loop_fn = AsyncMock(
        return_value=(
            ["US123"],
            SimpleNamespace(entries=[]),
            {"hard_filter": 1},
            [],
            0,
            0,
            0,
            [],
            search_loop_result,
        )
    )
    search_patents_fn = AsyncMock()
    events: list[tuple[int, str, str, dict]] = []
    timing_data: list[tuple[str, int, int]] = []

    result = await run_search_step(
        compound=SimpleNamespace(name="test_compound"),
        expanded_queries=SimpleNamespace(),
        settings=SimpleNamespace(search_loop_enabled=True),
        timing_data=timing_data,
        notify=lambda step, name, event, payload: events.append((step, name, event, payload)),
        make_timing=lambda step_name, _start, items_in, items_out: (
            step_name,
            items_in,
            items_out,
        ),
        run_search_loop_fn=run_search_loop_fn,
        search_patents_fn=search_patents_fn,
    )

    assert result.patent_hits == ["US123"]
    assert result.search_loop_result is search_loop_result
    run_search_loop_fn.assert_awaited_once()
    search_patents_fn.assert_not_called()
    assert events[0][1:] == ("search", "started", {"description": "Searching patent databases"})
    assert events[1][1:] == (
        "search",
        "completed",
        {"patents_found": 1, "literature_refs": 0},
    )
    assert timing_data == [("step2_search", 0, 1)]


@pytest.mark.asyncio
async def test_run_search_step_uses_basic_search_when_flag_disabled() -> None:
    run_search_loop_fn = AsyncMock()
    search_patents_fn = AsyncMock(
        return_value=(["EP456"], SimpleNamespace(entries=[]), {"hard_filter": 1})
    )

    result = await run_search_step(
        compound=SimpleNamespace(name="test_compound"),
        expanded_queries=SimpleNamespace(),
        settings=SimpleNamespace(search_loop_enabled=False),
        timing_data=[],
        notify=lambda *_args: None,
        make_timing=lambda *_args: None,
        run_search_loop_fn=run_search_loop_fn,
        search_patents_fn=search_patents_fn,
    )

    assert result.patent_hits == ["EP456"]
    assert result.search_loop_result is None
    run_search_loop_fn.assert_not_called()
    search_patents_fn.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_search_step_fails_closed_when_literature_branch_crashes() -> None:
    search_patents_fn = AsyncMock(
        return_value=(["EP456"], SimpleNamespace(entries=[]), {"hard_filter": 1})
    )
    literature_search_fn = AsyncMock(side_effect=RuntimeError("provider-secret"))

    with pytest.raises(SearchSourceFailedError) as exc_info:
        await run_search_step(
            compound=SimpleNamespace(name="confidential-compound"),
            expanded_queries=SimpleNamespace(),
            settings=SimpleNamespace(
                search_loop_enabled=False,
                literature_search_enabled=True,
                literature_max_per_source=25,
            ),
            timing_data=[],
            notify=lambda *_args: None,
            make_timing=lambda *_args: None,
            run_search_loop_fn=AsyncMock(),
            search_patents_fn=search_patents_fn,
            search_literature_fn=literature_search_fn,
        )

    assert "provider-secret" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


@pytest.mark.asyncio
async def test_run_analysis_step_returns_context_and_records_timing() -> None:
    analyze_patents_with_context_fn = AsyncMock(
        return_value=(
            [
                PatentAnalysis(
                    patent_id="US123",
                    risk_level=RiskLevel.CLEAR,
                    risk_summary="clear",
                    input_tokens=12,
                    output_tokens=8,
                )
            ],
            [],
            ["reasoning-trace"],
            {"US123": {"events": []}},
        )
    )
    timing_data: list[tuple[str, int, int]] = []
    notifications: list[tuple[int, str, str, dict]] = []

    result = await run_analysis_step(
        relevant_patents=[SimpleNamespace(patent_id="US123")],
        compound=SimpleNamespace(),
        triage_results=[SimpleNamespace(patent_id="US123")],
        global_escalation_reasons=[],
        drawing_evidence=None,
        timing_data=timing_data,
        notify=lambda step, name, event, payload: notifications.append(
            (step, name, event, payload)
        ),
        make_timing=lambda step_name, _start, items_in, items_out: (
            step_name,
            items_in,
            items_out,
        ),
        analyze_patents_with_context_fn=analyze_patents_with_context_fn,
    )

    assert [analysis.patent_id for analysis in result.analyses] == ["US123"]
    assert result.reasoning_traces == ["reasoning-trace"]
    assert result.prosecution_cache == {"US123": {"events": []}}
    assert analyze_patents_with_context_fn.await_args.kwargs["global_escalation_reasons"] == []
    assert timing_data == [("step4_analyze", 1, 1)]
    assert notifications[0][1:] == (
        "analyze",
        "started",
        {"description": "Deep claim analysis", "total": 1},
    )
    assert notifications[1][1:] == (
        "analyze",
        "completed",
        {"analyzed": 1, "total": 1},
    )
