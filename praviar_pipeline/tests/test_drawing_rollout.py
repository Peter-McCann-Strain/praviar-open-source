from __future__ import annotations

from types import SimpleNamespace

import pytest
from certification_keyring_fixtures import TEST_CHECKPOINT_INTEGRITY_KEYS

from praviar_pipeline.models.drawing import DrawingGovernanceProvenance
from praviar_pipeline.models.report import ClearanceOutcome
from praviar_pipeline.pipeline.drawing_rollout import (
    build_drawing_governance_provenance,
    drawing_evidence_can_influence,
    drawing_evidence_for_decisions,
    drawing_evidence_gate_passed,
    drawing_rollout_state,
    drawing_specialist_rollout_state,
    drawing_specialist_tool_can_emit,
    filter_patents_by_drawing_jurisdiction,
    markush_scope_agent_can_run,
)


def test_unknown_rollout_state_fails_closed_to_shadow() -> None:
    settings = SimpleNamespace(drawing_analysis_rollout_state="surprise")

    assert drawing_rollout_state(settings) == "shadow"
    assert drawing_evidence_gate_passed(settings) is False
    assert drawing_evidence_can_influence(settings) is False
    assert drawing_evidence_for_decisions(settings, object()) is None


def test_shadow_drawing_provenance_is_explicitly_non_influential() -> None:
    provenance = build_drawing_governance_provenance(
        SimpleNamespace(
            drawing_analysis_rollout_state="shadow",
            drawing_analysis_jurisdictions=["US", "EP"],
        )
    )

    assert provenance.rollout_state == "shadow"
    assert provenance.influence_permitted is False
    assert provenance.evidence_gate_passed is False
    assert provenance.jurisdictions == ("US", "EP")


def test_live_drawing_provenance_rejects_missing_release_bindings() -> None:
    with pytest.raises(ValueError, match="SHA-256 bindings"):
        DrawingGovernanceProvenance(
            rollout_state="production",
            influence_permitted=True,
            evidence_gate_passed=True,
            calibration_artifact_id="calibration-v1",
            calibration_artifact_revision=1,
            worker_image_digest="sha256:" + "a" * 64,
            jurisdictions=("US",),
            verified_at="2026-07-31T12:00:00Z",
        )


def test_missing_rollout_state_fails_closed_even_when_legacy_shadow_off() -> None:
    evidence = object()
    settings = SimpleNamespace(
        drawing_analysis_shadow_mode=False,
        drawing_analysis_evidence_gate_passed=True,
    )

    assert drawing_rollout_state(settings) == "shadow"
    assert drawing_evidence_gate_passed(settings) is True
    assert drawing_evidence_can_influence(settings) is False
    assert drawing_evidence_for_decisions(settings, evidence) is None


def test_markush_scope_agent_is_shadow_only() -> None:
    settings = SimpleNamespace(
        drawing_markush_scope_agent_enabled=True,
        drawing_analysis_rollout_state="shadow",
    )
    assert markush_scope_agent_can_run(settings) is True

    settings.drawing_analysis_rollout_state = "production"
    assert markush_scope_agent_can_run(settings) is False

    settings.drawing_markush_scope_agent_enabled = False
    settings.drawing_analysis_rollout_state = "shadow"
    assert markush_scope_agent_can_run(settings) is False


def test_live_rollouts_without_evidence_gate_fail_closed() -> None:
    evidence = object()

    for state in ("beta", "production"):
        settings = SimpleNamespace(drawing_analysis_rollout_state=state)
        assert drawing_rollout_state(settings) == state
        assert drawing_evidence_gate_passed(settings) is False
        assert drawing_evidence_can_influence(settings) is False
        assert drawing_evidence_for_decisions(settings, evidence) is None


def test_beta_and_production_rollouts_require_verified_calibration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from praviar_pipeline.ocsr import calibration_contract

    evidence = object()

    for state in ("beta", "production"):
        settings = SimpleNamespace(
            drawing_analysis_rollout_state=state,
            drawing_analysis_evidence_gate_passed=True,
            drawing_analysis_jurisdictions=["US"],
        )
        assert drawing_evidence_gate_passed(settings) is True
        assert drawing_evidence_can_influence(settings) is False

    monkeypatch.setattr(calibration_contract, "calibration_is_verified", lambda _settings: True)
    for state in ("beta", "production"):
        settings = SimpleNamespace(
            drawing_analysis_rollout_state=state,
            drawing_analysis_evidence_gate_passed=True,
            drawing_analysis_jurisdictions=["US"],
        )
        assert drawing_evidence_can_influence(settings) is True
        assert drawing_evidence_for_decisions(settings, evidence) is evidence


def test_specialist_shadow_can_emit_only_before_global_drawing_is_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from praviar_pipeline.ocsr import calibration_contract

    monkeypatch.setattr(calibration_contract, "calibration_is_verified", lambda _settings: True)
    settings = SimpleNamespace(
        drawing_analysis_rollout_state="shadow",
        drawing_analysis_evidence_gate_passed=False,
        drawing_markush_rollout_state="shadow",
    )

    assert drawing_specialist_rollout_state(settings, "drawing_markush_rollout_state") == "shadow"
    assert drawing_specialist_tool_can_emit(settings, "drawing_markush_rollout_state") is True

    settings.drawing_analysis_rollout_state = "beta"
    settings.drawing_analysis_evidence_gate_passed = True
    settings.drawing_analysis_jurisdictions = ["US"]

    assert drawing_specialist_tool_can_emit(settings, "drawing_markush_rollout_state") is False

    settings.drawing_markush_rollout_state = "beta"
    assert drawing_specialist_tool_can_emit(settings, "drawing_markush_rollout_state") is True


def test_unknown_specialist_rollout_state_fails_closed_when_global_drawing_is_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from praviar_pipeline.ocsr import calibration_contract

    monkeypatch.setattr(calibration_contract, "calibration_is_verified", lambda _settings: True)
    settings = SimpleNamespace(
        drawing_analysis_rollout_state="production",
        drawing_analysis_evidence_gate_passed=True,
        drawing_analysis_jurisdictions=["US"],
        drawing_markush_rollout_state="surprise",
    )

    assert drawing_specialist_rollout_state(settings, "drawing_markush_rollout_state") == "shadow"
    assert drawing_specialist_tool_can_emit(settings, "drawing_markush_rollout_state") is False


def test_empty_jurisdiction_allowlist_fails_closed() -> None:
    patents = [SimpleNamespace(patent_id="US1"), SimpleNamespace(patent_id="EP2")]
    settings = SimpleNamespace(
        drawing_analysis_rollout_state="production",
        drawing_analysis_evidence_gate_passed=True,
    )

    assert filter_patents_by_drawing_jurisdiction(patents, settings) == []
    assert drawing_evidence_can_influence(settings) is False
    assert drawing_evidence_for_decisions(settings, object()) is None


def test_jurisdiction_filter_keeps_allowlisted_prefixes() -> None:
    patents = [
        SimpleNamespace(patent_id="US1"),
        SimpleNamespace(patent_id="EP2"),
        SimpleNamespace(patent_id="JP3"),
    ]
    settings = SimpleNamespace(drawing_analysis_jurisdictions=["us", "JP"])

    filtered = filter_patents_by_drawing_jurisdiction(patents, settings)

    assert [patent.patent_id for patent in filtered] == ["US1", "JP3"]


@pytest.mark.asyncio
async def test_shadow_rollout_strips_drawing_evidence_from_runtime_decision_stages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from praviar_pipeline.pipeline.runtime import run_execution

    sentinel = object()
    seen: dict[str, object | None] = {}

    async def fake_triage_step(**kwargs):
        seen["triage"] = kwargs["drawing_evidence"]
        return SimpleNamespace(
            triage_results=[SimpleNamespace(patent_id="US1")],
            triage_input_tokens=0,
            triage_output_tokens=0,
            triage_failed=0,
            all_triage=[SimpleNamespace(patent_id="US1")],
        )

    async def fake_analysis_step(**kwargs):
        seen["analysis"] = kwargs["drawing_evidence"]
        return SimpleNamespace(
            analyses=[SimpleNamespace(patent_id="US1")],
            analysis_failures=[],
            reasoning_traces=[],
            prosecution_cache={},
        )

    async def fake_doe_assessment(**kwargs):
        seen["doe"] = kwargs["drawing_evidence"]
        return [], 0, 0

    async def fake_invalidity_assessment(**kwargs):
        seen["invalidity"] = kwargs["drawing_evidence"]
        return [], 0, 0

    monkeypatch.setattr(run_execution, "run_triage_step", fake_triage_step)
    monkeypatch.setattr(run_execution, "run_analysis_step", fake_analysis_step)
    monkeypatch.setattr(run_execution, "run_doe_assessment", fake_doe_assessment)
    monkeypatch.setattr(run_execution, "run_invalidity_assessment", fake_invalidity_assessment)
    monkeypatch.setattr(run_execution, "run_critic_review", None)
    monkeypatch.setattr(run_execution, "load_orange_book_if_available", lambda: _async_value(None))
    monkeypatch.setattr(
        run_execution,
        "run_verification_step",
        lambda **_kwargs: SimpleNamespace(checks=[]),
    )
    monkeypatch.setattr(run_execution, "build_triage_audit", lambda *_args: [])
    monkeypatch.setattr(run_execution, "build_analysis_audit", lambda *_args: [])
    monkeypatch.setattr(
        run_execution,
        "map_relevant_patents",
        lambda patent_hits, _triage_results: patent_hits,
    )

    state = SimpleNamespace(
        completed_step=0,
        settings=SimpleNamespace(
            drawing_analysis_rollout_state="shadow",
            drawing_analysis_enabled=False,
            critic_enabled=False,
        ),
        patent_hits=[SimpleNamespace(patent_id="US1")],
        compound=SimpleNamespace(name="compound"),
        drawing_evidence=sentinel,
        timing_data=[],
        triage_results=[],
        triage_in=0,
        triage_out=0,
        triage_failed=0,
        all_triage=[],
        execution_profile="world_class_adaptive",
        analysis_escalation_reasons=[],
        analyses=[],
        analysis_failures=[],
        reasoning_traces=[],
        prosecution_cache={},
        critic_report=None,
        critic_in=0,
        critic_out=0,
        doe_assessments=[],
        doe_in=0,
        doe_out=0,
        invalidity_assessments=[],
        inv_in=0,
        inv_out=0,
        verification=None,
    )
    callbacks = SimpleNamespace(
        raise_if_cancelled=lambda *_args: None,
        notify=lambda *_args: None,
        save_checkpoint=lambda *_args: None,
        make_timing=lambda *_args: SimpleNamespace(),
    )

    await run_execution.execute_analysis_to_verification_flow(
        state=state,
        callbacks=callbacks,
    )

    assert seen == {
        "triage": None,
        "analysis": None,
        "doe": None,
        "invalidity": None,
    }


async def _async_value(value):
    return value


@pytest.mark.asyncio
async def test_shadow_rollout_strips_drawing_evidence_from_report_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from praviar_pipeline.manifest import get_prompt_hasher
    from praviar_pipeline.pipeline.runtime.flow_finalize import finalize_report_output

    hasher = get_prompt_hasher()
    hasher.reset()
    hasher.record("triage_system.txt", "triage prompt")
    sentinel = object()
    seen: dict[str, object | None] = {}

    async def fake_generate_report(**kwargs):
        seen["report"] = kwargs["drawing_evidence"]
        return SimpleNamespace(
            data_limitations=[],
            action_items=[],
            report_id="report-1",
            risk_summary=SimpleNamespace(
                overall_risk=SimpleNamespace(value="LOW"),
                total_patents_analyzed=0,
                executive_summary=(
                    "No drawing-derived evidence influenced this shadow-mode report."
                ),
            ),
            patent_analyses=[],
            total_input_tokens=0,
            total_output_tokens=0,
            estimated_cost_usd=0.0,
            audit_trail=kwargs["audit_trail"],
        )

    async def fake_write_outputs(report, output_format):
        return {"report_id": report.report_id, "format": output_format}

    monkeypatch.setenv("PRAVIAR_PIPELINE_VERSION", "a" * 40)

    result = await finalize_report_output(
        settings=SimpleNamespace(
            drawing_analysis_rollout_state="shadow",
            claude_triage_model="triage",
            claude_analysis_model="analysis",
            claude_deep_model="deep",
            checkpoint_integrity_keys=TEST_CHECKPOINT_INTEGRITY_KEYS,
        ),
        compound=SimpleNamespace(name="compound", original_input="compound"),
        analyses=[],
        doe_assessments=[],
        invalidity_assessments=[],
        verification=SimpleNamespace(),
        patent_hits=[],
        source_health=SimpleNamespace(entries=[]),
        analysis_failures=[],
        prosecution_cache={},
        critic_report=None,
        drawing_evidence=sentinel,
        timing_data=[],
        execution_profile="world_class_adaptive",
        reasoning_traces=[],
        triage_audit=[],
        analysis_audit=[],
        search_funnel=[],
        triage_results=[],
        triage_in=0,
        triage_out=0,
        critic_in=0,
        critic_out=0,
        search_loop_result=None,
        doe_in=0,
        doe_out=0,
        inv_in=0,
        inv_out=0,
        audit_trail_builder=lambda **_kwargs: SimpleNamespace(timing_data=[]),
        prior_step_tokens_builder=lambda **_kwargs: SimpleNamespace(),
        generate_report_fn=fake_generate_report,
        write_pipeline_outputs_fn=fake_write_outputs,
        notify_fn=lambda *_args: None,
        raise_if_cancelled_fn=lambda *_args: None,
        save_checkpoint_fn=lambda *_args: None,
        make_timing_fn=lambda *_args: SimpleNamespace(),
        pipeline_start=0.0,
        output_format="json",
        logger=SimpleNamespace(info=lambda *_args, **_kwargs: None),
        clearance_outputs_builder=lambda *_args, **_kwargs: {
            "clearance_decision": SimpleNamespace(
                decision=ClearanceOutcome.UNCLEAR,
                decision_audit=SimpleNamespace(
                    claim_program_summary=SimpleNamespace(
                        blocking_patent_ids=[],
                        blocking_claim_ids=[],
                    )
                ),
            ),
            "jurisdiction_decisions": [],
            "decision_scope": SimpleNamespace(jurisdictions=[]),
            "supporting_scope": SimpleNamespace(jurisdictions=[]),
            "certification_scope": SimpleNamespace(jurisdictions=[]),
            "prosecution_findings": [],
            "claim_construction_record": {},
            "future_risk": {},
            "commercial_exposure": {},
        },
        user_input="compound",
    )

    assert seen["report"] is None
    assert result == {"report_id": "report-1", "format": "json"}
