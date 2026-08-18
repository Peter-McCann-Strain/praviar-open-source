from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from praviar_pipeline.models.analysis import (
    AnalysisEvaluation,
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    EvaluationIssue,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.reasoning import ReasoningTrace
from praviar_pipeline.pipeline.analysis.orchestration_helpers import (
    AnalysisBatchContext,
    build_analysis_timeout,
    collect_batch_results,
    run_patent_analysis_task,
)


def _make_analysis(
    *,
    patent_id: str = "US7851188B2",
    risk_level: RiskLevel = RiskLevel.HIGH,
) -> PatentAnalysis:
    return PatentAnalysis(
        patent_id=patent_id,
        title="Methods for producing succinic acid from fermentation",
        assignee="BioAmber Inc.",
        claims_analyzed=[
            ClaimAnalysis(
                claim_number=1,
                claim_type="independent",
                elements=[
                    ClaimElement(
                        element_number=1,
                        element_text="producing succinic acid",
                        status=ElementStatus.MET,
                        reasoning="Exact match",
                        confidence=0.95,
                    ),
                ],
                overall_status=ElementStatus.MET,
                overall_confidence=0.95,
            ),
        ],
        risk_level=risk_level,
        risk_summary="Test summary",
    )


@pytest.mark.asyncio
async def test_run_patent_analysis_task_applies_fixes_and_perspectives() -> None:
    patent = SimpleNamespace(
        patent_id="US7851188B2",
        title="Methods for producing succinic acid from fermentation",
        abstract="Abstract",
        claims_text="1. A method for producing succinic acid...",
    )
    compound = SimpleNamespace(name="succinic acid")
    triage = SimpleNamespace(relevance=SimpleNamespace(value="relevant"))
    analysis = _make_analysis()
    trace = ReasoningTrace(agent_type="claim_analysis", patent_id=patent.patent_id)
    tracker = SimpleNamespace(mark_complete=Mock())

    analyze_single_pass = AsyncMock()
    analyze_agentic = AsyncMock(return_value=(analysis, trace))
    evaluate_analysis = AsyncMock(
        return_value=AnalysisEvaluation(
            issues=[
                EvaluationIssue(
                    issue_type="risk_claim_mismatch",
                    description="HIGH risk but no claim elements met",
                    suggested_fix="Change risk to LOW",
                    severity="critical",
                ),
            ],
            overall_quality="needs_revision",
            revised_risk_level="low",
        ),
    )
    apply_evaluation_fixes = Mock(
        side_effect=lambda current, _evaluation: current.model_copy(
            update={"risk_level": RiskLevel.LOW}
        )
    )
    run_perspectives = AsyncMock(return_value=[{"perspective": "patent_attorney"}])
    synthesize_perspectives = AsyncMock(
        return_value=SimpleNamespace(disagreements=["scope"]),
    )

    context = AnalysisBatchContext(
        claude=object(),
        compound=compound,
        settings=SimpleNamespace(
            analysis_title_log_max_chars=40,
            multi_perspective_enabled=True,
            product_context={},
            intended_actions=[],
            target_jurisdictions=[],
        ),
        system_prompt="system",
        evaluator_prompt="evaluator",
        global_escalation_reasons=["high_risk_triage"],
        triage_map={patent.patent_id: triage},
        spec_text_cache={},
        prosecution_cache={},
        toolkit=None,
        drawing_evidence=None,
        analyze_single_pass=analyze_single_pass,
        analyze_agentic=analyze_agentic,
        evaluate_analysis=evaluate_analysis,
        apply_evaluation_fixes=apply_evaluation_fixes,
        run_perspectives=run_perspectives,
        synthesize_perspectives=synthesize_perspectives,
        format_compound_for_analysis=lambda resolved: f"compound:{resolved.name}",
        format_patent_for_analysis=lambda patent_hit, _triage: f"patent:{patent_hit.patent_id}",
        tracker=tracker,
    )

    result_analysis, result_trace = await run_patent_analysis_task(
        patent=patent,
        context=context,
        semaphore=asyncio.Semaphore(1),
    )

    assert result_trace is trace
    assert result_analysis.risk_level == RiskLevel.LOW
    assert analyze_single_pass.await_count == 0
    assert analyze_agentic.await_count == 1
    assert result_analysis.analysis_execution_plan["escalation_required"] is True
    assert evaluate_analysis.await_count == 1
    assert apply_evaluation_fixes.call_count == 1
    assert run_perspectives.await_count == 1
    assert synthesize_perspectives.await_count == 1
    assert tracker.mark_complete.call_args.kwargs["success"] is True
    assert tracker.mark_complete.call_args.kwargs["patent_id"] == patent.patent_id
    assert tracker.mark_complete.call_args.kwargs["risk_level"] == "low"


@pytest.mark.asyncio
async def test_run_patent_analysis_task_reanalyzes_after_poor_evaluation() -> None:
    patent = SimpleNamespace(
        patent_id="US6265190B1",
        title="Succinic acid production and purification",
        abstract="Abstract",
        claims_text="1. A method...",
    )
    compound = SimpleNamespace(name="succinic acid")
    analysis_one = _make_analysis(patent_id=patent.patent_id, risk_level=RiskLevel.HIGH)
    analysis_two = _make_analysis(patent_id=patent.patent_id, risk_level=RiskLevel.CLEAR)
    tracker = SimpleNamespace(mark_complete=Mock())

    trace = ReasoningTrace(agent_type="claim_analysis", patent_id=patent.patent_id)
    analyze_single_pass = AsyncMock(return_value=analysis_one)
    analyze_agentic = AsyncMock(return_value=(analysis_two, trace))
    evaluate_analysis = AsyncMock(
        side_effect=[
            AnalysisEvaluation(issues=[], overall_quality="poor"),
            AnalysisEvaluation(issues=[], overall_quality="good", revised_risk_level="medium"),
        ],
    )
    apply_evaluation_fixes = Mock(
        side_effect=lambda current, _evaluation: current.model_copy(
            update={"risk_level": RiskLevel.MEDIUM}
        ),
    )

    context = AnalysisBatchContext(
        claude=object(),
        compound=compound,
        settings=SimpleNamespace(
            analysis_title_log_max_chars=40,
            multi_perspective_enabled=False,
            product_context={},
            intended_actions=[],
            target_jurisdictions=[],
        ),
        system_prompt="system",
        evaluator_prompt="evaluator",
        global_escalation_reasons=[],
        triage_map={},
        spec_text_cache={},
        prosecution_cache={},
        toolkit=None,
        drawing_evidence=None,
        analyze_single_pass=analyze_single_pass,
        analyze_agentic=analyze_agentic,
        evaluate_analysis=evaluate_analysis,
        apply_evaluation_fixes=apply_evaluation_fixes,
        run_perspectives=AsyncMock(),
        synthesize_perspectives=AsyncMock(),
        format_compound_for_analysis=lambda resolved: f"compound:{resolved.name}",
        format_patent_for_analysis=lambda patent_hit, _triage: f"patent:{patent_hit.patent_id}",
        tracker=tracker,
    )

    result_analysis, result_trace = await run_patent_analysis_task(
        patent=patent,
        context=context,
        semaphore=asyncio.Semaphore(1),
    )

    assert result_trace is None
    assert result_analysis.risk_level == RiskLevel.MEDIUM
    assert analyze_single_pass.await_count == 1
    assert analyze_agentic.await_count == 1
    assert evaluate_analysis.await_count == 2
    assert apply_evaluation_fixes.call_count == 1
    assert tracker.mark_complete.call_args.kwargs["success"] is True


@pytest.mark.asyncio
async def test_evaluator_failure_marks_analysis_review_required() -> None:
    patent = SimpleNamespace(
        patent_id="US1234567B2",
        title="Succinic acid method",
        abstract="Abstract",
        claims_text="1. A method...",
    )
    compound = SimpleNamespace(name="succinic acid")
    analysis = _make_analysis(patent_id=patent.patent_id, risk_level=RiskLevel.HIGH)
    tracker = SimpleNamespace(mark_complete=Mock())

    context = AnalysisBatchContext(
        claude=object(),
        compound=compound,
        settings=SimpleNamespace(
            analysis_title_log_max_chars=40,
            multi_perspective_enabled=False,
            product_context={},
            intended_actions=[],
            target_jurisdictions=[],
        ),
        system_prompt="system",
        evaluator_prompt="evaluator",
        global_escalation_reasons=[],
        triage_map={},
        spec_text_cache={},
        prosecution_cache={},
        toolkit=None,
        drawing_evidence=None,
        analyze_single_pass=AsyncMock(return_value=analysis),
        analyze_agentic=AsyncMock(),
        evaluate_analysis=AsyncMock(side_effect=RuntimeError("provider payload")),
        apply_evaluation_fixes=Mock(),
        run_perspectives=AsyncMock(),
        synthesize_perspectives=AsyncMock(),
        format_compound_for_analysis=lambda resolved: f"compound:{resolved.name}",
        format_patent_for_analysis=lambda patent_hit, _triage: f"patent:{patent_hit.patent_id}",
        tracker=tracker,
    )

    result_analysis, result_trace = await run_patent_analysis_task(
        patent=patent,
        context=context,
        semaphore=asyncio.Semaphore(1),
    )

    assert result_trace is None
    assert result_analysis.analysis_review_required is True
    assert result_analysis.analysis_quality_gate_failures == ["evaluator_initial_evaluation_failed"]
    assert result_analysis.analysis_execution_plan["review_required"] is True
    assert result_analysis.analysis_execution_plan["quality_gate_failures"] == [
        "evaluator_initial_evaluation_failed"
    ]


@pytest.mark.asyncio
async def test_perspective_failure_marks_analysis_review_required() -> None:
    patent = SimpleNamespace(
        patent_id="US7654321B2",
        title="Succinic acid formulation",
        abstract="Abstract",
        claims_text="1. A formulation...",
    )
    compound = SimpleNamespace(name="succinic acid")
    analysis = _make_analysis(patent_id=patent.patent_id, risk_level=RiskLevel.HIGH)
    tracker = SimpleNamespace(mark_complete=Mock())

    context = AnalysisBatchContext(
        claude=object(),
        compound=compound,
        settings=SimpleNamespace(
            analysis_title_log_max_chars=40,
            multi_perspective_enabled=True,
            product_context={},
            intended_actions=[],
            target_jurisdictions=[],
        ),
        system_prompt="system",
        evaluator_prompt="evaluator",
        global_escalation_reasons=[],
        triage_map={},
        spec_text_cache={},
        prosecution_cache={},
        toolkit=None,
        drawing_evidence=None,
        analyze_single_pass=AsyncMock(return_value=analysis),
        analyze_agentic=AsyncMock(),
        evaluate_analysis=AsyncMock(
            return_value=AnalysisEvaluation(issues=[], overall_quality="good")
        ),
        apply_evaluation_fixes=Mock(),
        run_perspectives=AsyncMock(side_effect=RuntimeError("provider payload")),
        synthesize_perspectives=AsyncMock(),
        format_compound_for_analysis=lambda resolved: f"compound:{resolved.name}",
        format_patent_for_analysis=lambda patent_hit, _triage: f"patent:{patent_hit.patent_id}",
        tracker=tracker,
    )

    result_analysis, _result_trace = await run_patent_analysis_task(
        patent=patent,
        context=context,
        semaphore=asyncio.Semaphore(1),
    )

    assert result_analysis.analysis_review_required is True
    assert result_analysis.analysis_quality_gate_failures == ["perspective_review_failed"]
    assert result_analysis.analysis_execution_plan["quality_gate_failures"] == [
        "perspective_review_failed"
    ]


def test_collect_batch_results_splits_failures_and_traces() -> None:
    patent_ok = SimpleNamespace(patent_id="US1")
    patent_failed = SimpleNamespace(patent_id="US2")
    analysis = _make_analysis(patent_id="US1", risk_level=RiskLevel.HIGH)
    trace = ReasoningTrace(agent_type="claim_analysis", patent_id="US1")
    tracker = SimpleNamespace(mark_complete=Mock())

    analyses, failures, traces = collect_batch_results(
        results=[(analysis, trace), TimeoutError("timeout timeout timeout")],
        patents_to_analyze=[patent_ok, patent_failed],
        tracker=tracker,
        settings=SimpleNamespace(analysis_error_msg_max_chars=7),
        compound_name="succinic acid",
    )

    assert analyses == [analysis]
    assert traces == [trace]
    assert len(failures) == 1
    assert failures[0].patent_id == "US2"
    assert failures[0].error_type == "TimeoutError"
    assert failures[0].error_message == "patent "
    assert failures[0].recoverable is True
    assert tracker.mark_complete.call_args.kwargs["success"] is False
    assert tracker.mark_complete.call_args.kwargs["patent_id"] == "US2"


def test_build_analysis_timeout_scales_http_timeout() -> None:
    settings = SimpleNamespace(http_timeout_long=12.5)

    assert build_analysis_timeout(settings) == 62.5
