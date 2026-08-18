from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.errors import PipelineCancelledError, RuntimeBudgetExceededError
from praviar_pipeline.pipeline.runtime.flow import RuntimeTerminationInfo
from praviar_pipeline.pipeline.runtime.run_lifecycle import (
    build_run_lifecycle_adapters,
    build_runtime_budget_termination,
)


def _state(**overrides):
    defaults = dict(
        deadline_epoch=None,
        started_at_epoch=100.0,
        settings=SimpleNamespace(
            checkpoint_enabled=True,
            max_run_duration_hours=2,
        ),
        checkpoint_integrity_keys=object(),
        checkpoint_dir="checkpoint-dir",
        run_id="run-123",
        user_input="aspirin",
        execution_profile="world_class_adaptive",
        analysis_escalation_reasons=[],
        compound=SimpleNamespace(name="aspirin"),
        expanded_queries={"terms": ["aspirin"]},
        patent_hits=["hit-1"],
        source_health="health",
        search_funnel=["funnel"],
        matter_graph=None,
        matter_graph_summary=None,
        matter_store=None,
        evidence_artifacts=[],
        evidence_adapter_results=[],
        collector_runs=[],
        drawing_evidence=None,
        triage_results=["triage"],
        all_triage=["triage-all"],
        triage_in=11,
        triage_out=12,
        triage_failed=0,
        analyses=["analysis"],
        analysis_failures=["failure"],
        prosecution_cache={"US123": {"office_actions": "summary"}},
        reasoning_traces=["trace"],
        critic_report="critic",
        critic_in=13,
        critic_out=14,
        search_loop_result="loop",
        doe_assessments=["doe"],
        doe_in=15,
        doe_out=16,
        invalidity_assessments=["invalidity"],
        inv_in=17,
        inv_out=18,
        verification="verification",
        timing_data=["timing"],
        completed_step=0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_build_run_lifecycle_adapters_notifies_and_cancels():
    events: list[tuple[int, str, str, dict]] = []
    state = _state()
    adapters = build_run_lifecycle_adapters(
        state=state,
        on_progress=lambda step, name, event, payload: events.append((step, name, event, payload)),
        should_cancel=lambda: True,
        build_runtime_evidence_snapshot_fn=lambda **kwargs: None,
        save_runtime_checkpoint_fn=lambda **kwargs: None,
    )

    adapters.notify(3, "triage", "started", {"description": "Triage"})
    assert events == [(3, "triage", "started", {"description": "Triage"})]

    try:
        adapters.raise_if_cancelled(4, "analyze")
    except PipelineCancelledError as exc:
        assert exc.step == "analyze"
    else:
        raise AssertionError("Expected PipelineCancelledError")


def test_build_run_lifecycle_adapters_save_checkpoint_builds_evidence_snapshot():
    state = _state()
    snapshot_calls = []
    checkpoint_calls = []

    def build_snapshot(**kwargs):
        snapshot_calls.append(kwargs)
        return SimpleNamespace(
            matter_graph={"nodes": ["compound:aspirin"]},
            matter_graph_summary={"node_count": 1},
            matter_store={"matter_graph_summary": {"node_count": 1}},
            evidence_artifacts=[{"artifact_id": "artifact-1"}],
            evidence_adapter_results=[{"adapter_name": "pubchem"}],
            collector_runs=[{"definition": {"collector_name": "pubchem"}}],
        )

    def save_checkpoint(**kwargs):
        checkpoint_calls.append(kwargs)

    adapters = build_run_lifecycle_adapters(
        state=state,
        on_progress=None,
        should_cancel=None,
        build_runtime_evidence_snapshot_fn=build_snapshot,
        save_runtime_checkpoint_fn=save_checkpoint,
    )

    adapters.save_checkpoint(6)

    assert state.completed_step == 6
    assert state.matter_graph == {"nodes": ["compound:aspirin"]}
    assert state.matter_graph_summary == {"node_count": 1}
    assert state.matter_store == {"matter_graph_summary": {"node_count": 1}}
    assert state.evidence_artifacts == [{"artifact_id": "artifact-1"}]
    assert state.evidence_adapter_results == [{"adapter_name": "pubchem"}]
    assert state.collector_runs == [{"definition": {"collector_name": "pubchem"}}]
    assert snapshot_calls[0]["compound"].name == "aspirin"
    assert snapshot_calls[0]["existing_collector_runs"] == []
    assert checkpoint_calls[0]["completed_step"] == 6
    assert checkpoint_calls[0]["matter_graph"] == {"nodes": ["compound:aspirin"]}
    assert checkpoint_calls[0]["matter_store"] == {"matter_graph_summary": {"node_count": 1}}
    assert checkpoint_calls[0]["collector_runs"] == [{"definition": {"collector_name": "pubchem"}}]


def test_build_runtime_budget_termination_uses_runtime_budget_context():
    state = _state(settings=SimpleNamespace(max_run_duration_hours=3))
    exc = RuntimeBudgetExceededError(
        "timeout",
        step="invalidity",
        deadline_epoch=200.0,
        elapsed_seconds=14400.0,
    )

    result = build_runtime_budget_termination(state=state, exc=exc)

    assert isinstance(result, RuntimeTerminationInfo)
    assert result.reason == "runtime_budget_exceeded"
    assert result.step == "invalidity"
    assert "3 hour(s)" in result.description
