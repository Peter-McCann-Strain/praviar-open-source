from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from praviar_pipeline.checkpoint import CheckpointIntegrityKeyRing
from praviar_pipeline.config import Settings
from praviar_pipeline.errors import RuntimeBudgetExceededError
from praviar_pipeline.manifest import get_prompt_hasher
from praviar_pipeline.models.hitl import CheckpointDecision, CheckpointType
from praviar_pipeline.models.report import (
    CertificationScope,
    ClearanceOutcome,
    DecisionScope,
    FTOReport,
    JurisdictionDecision,
)
from praviar_pipeline.pipeline.runtime.config import apply_analysis_config_overrides
from praviar_pipeline.pipeline.runtime.flow import bootstrap_run_context, finalize_report_output
from praviar_pipeline.pipeline.runtime.flow_bootstrap import (
    _initial_adaptive_escalation_reasons,
    _install_response_cache,
)
from praviar_pipeline.pipeline.runtime.flow_helpers import _opinion_readiness
from praviar_pipeline.pipeline.runtime.run_execution import (
    RunCallbacks,
    execute_analysis_to_verification_flow,
)
from praviar_pipeline.response_cache import (
    CacheMode,
    ResponseCache,
    get_current_cache,
    set_current_cache,
)
from praviar_pipeline.run import run_pipeline

TEST_INTEGRITY_KEYS = CheckpointIntegrityKeyRing(
    active_key_id="test-v1",
    _keys={"test-v1": b"test-runtime-flow-integrity-key-0001"},
)


@pytest.mark.asyncio
@pytest.mark.parametrize("completed_step", [6, 12])
async def test_zero_hit_resume_never_enters_empty_analysis_stages(completed_step: int) -> None:
    callbacks = RunCallbacks(
        notify=MagicMock(),
        raise_if_cancelled=MagicMock(),
        save_checkpoint=MagicMock(),
        make_timing=MagicMock(),
    )
    state = SimpleNamespace(completed_step=completed_step, patent_hits=[])

    result = await execute_analysis_to_verification_flow(
        state=state,
        callbacks=callbacks,
    )

    assert result == ([], [])
    callbacks.raise_if_cancelled.assert_not_called()
    callbacks.notify.assert_not_called()
    callbacks.save_checkpoint.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rollout_state", "expected_error"),
    [
        ("shadow", "analysis reached"),
        ("internal", "analysis reached"),
        ("beta", "drawing failed"),
        ("production", "drawing failed"),
    ],
)
async def test_drawing_enrichment_failures_are_fatal_for_every_live_rollout(
    rollout_state: str,
    expected_error: str,
) -> None:
    state = SimpleNamespace(
        completed_step=6,
        patent_hits=[SimpleNamespace(patent_id="US1")],
        all_triage=[],
        triage_results=[],
        settings=SimpleNamespace(
            drawing_analysis_enabled=True,
            drawing_analysis_rollout_state=rollout_state,
            # Exercise the formerly unsafe state explicitly: live rollout with
            # a missing evidence gate must still fail closed.
            drawing_analysis_evidence_gate_passed=False,
        ),
        drawing_evidence=None,
        compound=SimpleNamespace(name="Example Molecule Alpha"),
        timing_data=[],
        analysis_escalation_reasons=[],
        execution_profile="world_class_adaptive",
    )
    callbacks = RunCallbacks(
        notify=MagicMock(),
        raise_if_cancelled=MagicMock(),
        save_checkpoint=MagicMock(),
        make_timing=MagicMock(),
    )

    with (
        patch(
            "praviar_pipeline.pipeline.runtime.run_execution.map_relevant_patents",
            return_value=state.patent_hits,
        ),
        patch(
            "praviar_pipeline.pipeline.runtime.run_execution.run_post_triage_drawing_enrichment",
            new=AsyncMock(side_effect=RuntimeError("drawing failed")),
        ),
        patch(
            "praviar_pipeline.pipeline.runtime.run_execution.run_analysis_step",
            new=AsyncMock(side_effect=RuntimeError("analysis reached")),
        ),
        pytest.raises(RuntimeError, match=expected_error),
    ):
        await execute_analysis_to_verification_flow(state=state, callbacks=callbacks)


@pytest.mark.asyncio
@pytest.mark.parametrize("decision_action", ["reject", "review_required"])
async def test_analysis_review_is_reenforced_when_resuming_step_eight(
    decision_action: str,
) -> None:
    state = SimpleNamespace(
        completed_step=8,
        patent_hits=[SimpleNamespace(patent_id="US1")],
        all_triage=[],
        triage_results=[],
        triage_failed=0,
        analyses=[
            SimpleNamespace(
                patent_id="US1",
                risk_level=SimpleNamespace(value="medium"),
                analysis_quality_gate_failures=[],
            )
        ],
        analysis_failures=[],
        settings=SimpleNamespace(
            drawing_analysis_enabled=False,
            drawing_analysis_rollout_state="shadow",
            drawing_analysis_evidence_gate_passed=False,
            hitl_enabled=True,
            hitl_checkpoints=["analysis_review"],
            hitl_auto_skip_minutes=1,
        ),
        drawing_evidence=None,
        compound=SimpleNamespace(name="Example Molecule Alpha"),
        timing_data=[],
        analysis_escalation_reasons=[],
        execution_profile="world_class_adaptive",
    )

    def decision_provider(*_args):
        return CheckpointDecision(
            checkpoint_type=CheckpointType.ANALYSIS_REVIEW,
            action=decision_action,
            reviewer_id="reviewer-1",
        )

    callbacks = RunCallbacks(
        notify=MagicMock(),
        raise_if_cancelled=MagicMock(),
        save_checkpoint=MagicMock(),
        make_timing=MagicMock(),
        checkpoint_decision_provider=decision_provider,
        checkpoint_poll_interval_seconds=0,
    )

    with (
        patch(
            "praviar_pipeline.pipeline.runtime.run_execution.map_relevant_patents",
            return_value=state.patent_hits,
        ),
        pytest.raises(RuntimeError, match=r"rejected|persisted human review"),
    ):
        await execute_analysis_to_verification_flow(state=state, callbacks=callbacks)

    checkpoint_events = [
        call
        for call in callbacks.notify.call_args_list
        if call.args[2] in {"checkpoint", "review_required"}
    ]
    assert checkpoint_events
    assert checkpoint_events[0].args[3]["checkpoint_type"] == "analysis_review"


def test_opinion_readiness_authorizes_only_verified_complete_counsel_lanes() -> None:
    report = SimpleNamespace(
        decision_scope=DecisionScope(
            matter_type="small_molecule",
            jurisdictions=["US", "EP"],
            supports_positive_clearance=True,
        ),
        certification_scope=CertificationScope(
            current_matter_type_certified=True,
            evidence_verified=True,
        ),
        jurisdiction_decisions=[
            JurisdictionDecision(
                jurisdiction=jurisdiction,
                evidence_sufficient_for_clearance=True,
            )
            for jurisdiction in ("US", "EP")
        ],
    )
    settings = SimpleNamespace(
        trust_mode="counsel",
        target_jurisdictions=["US", "EP"],
    )

    readiness = _opinion_readiness(report, settings)

    assert readiness.export_ready is True
    assert readiness.trust_mode == "counsel"
    assert readiness.jurisdictions_blocking_export == []
    assert readiness.gate_failures == []
    assert readiness.attorney_supervision_required is True


def test_opinion_readiness_fails_closed_for_unverified_or_incomplete_lane() -> None:
    report = SimpleNamespace(
        decision_scope=DecisionScope(
            matter_type="small_molecule",
            jurisdictions=["US", "EP"],
        ),
        certification_scope=CertificationScope(
            current_matter_type_certified=False,
            evidence_verified=False,
        ),
        jurisdiction_decisions=[
            JurisdictionDecision(
                jurisdiction="US",
                evidence_sufficient_for_clearance=True,
            ),
            JurisdictionDecision(
                jurisdiction="EP",
                evidence_sufficient_for_clearance=True,
                local_review_required=True,
            ),
        ],
    )
    settings = SimpleNamespace(
        trust_mode="explorer",
        target_jurisdictions=["US", "EP"],
    )

    readiness = _opinion_readiness(report, settings)

    assert readiness.export_ready is False
    assert readiness.jurisdictions_blocking_export == ["EP"]
    assert readiness.gate_failures == [
        "counsel_trust_mode_required",
        "release_certification_receipt_invalid_or_missing",
        "matter_type_not_certified",
        "selected_jurisdiction_lanes_incomplete",
    ]


def test_fto_report_contract_defaults_opinion_readiness_to_fail_closed() -> None:
    readiness_field = FTOReport.model_fields["opinion_readiness"]

    readiness = readiness_field.default_factory()

    assert readiness.export_ready is False
    assert readiness.trust_mode == "explorer"


def _seed_prompt_hashes() -> None:
    hasher = get_prompt_hasher()
    hasher.reset()
    hasher.record("triage_system.txt", "triage prompt")


def test_install_response_cache_records_to_private_run_directory(tmp_path: Path) -> None:
    settings = SimpleNamespace(
        resolved_output_dir=tmp_path,
        response_cache_mode="record",
        response_cache_dir="",
        response_cache_expected_digest="",
        response_cache_expected_hmac="",
        response_cache_expected_key_id="",
    )
    context = SimpleNamespace(
        run_id="run_123",
        checkpoint_integrity_keys=TEST_INTEGRITY_KEYS,
    )

    _install_response_cache(context=context, settings=settings, resume_from=None)
    cache = get_current_cache()

    assert cache is not None
    assert cache.mode == CacheMode.RECORD
    assert cache.cache_path == tmp_path / ".replay-cache/run_123/responses.jsonl"
    assert cache.manifest_reference == ".replay-cache/run_123/responses.jsonl"
    set_current_cache(None)


def test_install_response_cache_preserves_explicit_dry_run_boundary(tmp_path: Path) -> None:
    dry_run_cache = ResponseCache(cache_dir=tmp_path / "dry", mode=CacheMode.DRY_RUN)
    set_current_cache(dry_run_cache)

    _install_response_cache(
        context=SimpleNamespace(run_id="run_123"),
        settings=SimpleNamespace(
            resolved_output_dir=tmp_path,
            response_cache_mode="record",
            response_cache_dir="",
        ),
        resume_from=None,
    )

    assert get_current_cache() is dry_run_cache
    set_current_cache(None)


def test_install_response_cache_replay_requires_matching_authentication(tmp_path: Path) -> None:
    recorded = ResponseCache(cache_dir=tmp_path / "cache", mode=CacheMode.RECORD)
    expected_digest = recorded.digest()
    expected_hmac = recorded.authenticated_digest(key=TEST_INTEGRITY_KEYS.active_key())
    settings = SimpleNamespace(
        resolved_output_dir=tmp_path,
        response_cache_mode="replay",
        response_cache_dir=str(tmp_path / "cache"),
        response_cache_expected_digest=expected_digest,
        response_cache_expected_hmac=expected_hmac,
        response_cache_expected_key_id=TEST_INTEGRITY_KEYS.active_key_id,
    )
    context = SimpleNamespace(
        run_id="run_123",
        checkpoint_integrity_keys=TEST_INTEGRITY_KEYS,
    )

    _install_response_cache(context=context, settings=settings, resume_from=None)
    assert get_current_cache() is not None
    assert get_current_cache().mode == CacheMode.REPLAY

    settings.response_cache_expected_hmac = "0" * 64
    with pytest.raises(RuntimeError, match="authentication"):
        _install_response_cache(context=context, settings=settings, resume_from=None)
    set_current_cache(None)


def test_bootstrap_run_context_restores_resume_state(tmp_path):
    compound = SimpleNamespace(name="aspirin", pubchem_cid=2244)
    resume_state = SimpleNamespace(
        completed_step=4,
        run_id="run_123",
        execution_profile="world_class_adaptive",
        analysis_escalation_reasons=["complex_matter_type"],
        started_at_epoch=123.0,
        deadline_epoch=456.0,
        compound_input="aspirin",
        compound=compound,
        expanded_queries={"cpc_codes": []},
        patent_hits=["hit"],
        source_health="health",
        search_funnel=["funnel"],
        matter_graph="graph",
        matter_graph_summary="graph_summary",
        matter_store="matter_store",
        collector_runs=["collector"],
        drawing_evidence="drawings",
        triage_results=["triage"],
        all_triage_results=["all-triage"],
        triage_input_tokens=10,
        triage_output_tokens=20,
        triage_failed=1,
        analyses=["analysis"],
        analysis_failures=["failure"],
        prosecution_cache={"US123": {"office_actions": "- [CTNF] OA"}},
        reasoning_traces=["trace"],
        critic_report="critic",
        critic_input_tokens=30,
        critic_output_tokens=40,
        search_loop_result="loop_result",
        doe_assessments=["doe"],
        doe_input_tokens=50,
        doe_output_tokens=60,
        invalidity_assessments=["invalidity"],
        inv_input_tokens=70,
        inv_output_tokens=80,
        verification="verification",
        timing_data=["timing"],
    )
    bind_compound_context_fn = MagicMock()
    logger = MagicMock()

    context = bootstrap_run_context(
        user_input="aspirin",
        resume_from=str(tmp_path / "resume"),
        config_overrides={"search_max_ranked_results": 10},
        get_settings_fn=lambda: SimpleNamespace(
            resolved_checkpoint_dir=Path(tmp_path),
            max_run_duration_hours=24,
            checkpoint_integrity_keys=TEST_INTEGRITY_KEYS,
        ),
        apply_analysis_config_overrides_fn=lambda settings, _overrides: settings,
        bind_pipeline_context_fn=lambda compound_input: "run_initial",
        bind_compound_context_fn=bind_compound_context_fn,
        restore_runtime_state_fn=lambda path, *, integrity_keys: resume_state,
        logger=logger,
    )

    assert context.run_id == "run_123"
    assert context.execution_profile == "world_class_adaptive"
    assert context.analysis_escalation_reasons == ["complex_matter_type"]
    assert context.checkpoint_dir == Path(tmp_path) / "run_123"
    assert context.started_at_epoch == 123.0
    assert context.deadline_epoch == 456.0
    assert context.patent_hits == ["hit"]
    assert context.matter_graph == "graph"
    assert context.matter_graph_summary == "graph_summary"
    assert context.matter_store == "matter_store"
    assert context.collector_runs == ["collector"]
    assert context.search_loop_result == "loop_result"
    assert context.prosecution_cache == {"US123": {"office_actions": "- [CTNF] OA"}}
    bind_compound_context_fn.assert_called_once_with(name="aspirin", cid=2244)
    logger.info.assert_called_once()


def test_bootstrap_run_context_sets_deadline_for_new_run(tmp_path):
    bind_compound_context_fn = MagicMock()
    logger = MagicMock()

    context = bootstrap_run_context(
        user_input="aspirin",
        resume_from=None,
        config_overrides=None,
        get_settings_fn=lambda: SimpleNamespace(
            resolved_checkpoint_dir=Path(tmp_path),
            max_run_duration_hours=12,
            checkpoint_integrity_keys=TEST_INTEGRITY_KEYS,
            trust_mode="counsel",
            clearance_threshold_profile="world_class_us_ep",
        ),
        apply_analysis_config_overrides_fn=lambda settings, _overrides: settings,
        bind_pipeline_context_fn=lambda compound_input: "run_initial",
        bind_compound_context_fn=bind_compound_context_fn,
        restore_runtime_state_fn=lambda path, *, integrity_keys: None,
        logger=logger,
    )

    assert context.execution_profile == "world_class_adaptive"
    assert context.analysis_escalation_reasons
    assert context.deadline_epoch is not None
    assert context.deadline_epoch > context.started_at_epoch
    assert pytest.approx(context.deadline_epoch - context.started_at_epoch, rel=0.001) == 43200.0


def test_launch_action_enums_trigger_initial_adaptive_escalation():
    reasons = _initial_adaptive_escalation_reasons(
        SimpleNamespace(
            matter_type="small_molecule",
            asset_type_hint="small_molecule",
            clearance_threshold_profile="screening",
            trust_mode="explorer",
            intended_actions=["commercial_launch"],
            target_jurisdictions=["US", "EP"],
            required_record_components=[],
            search_citation_traversal_enabled=False,
        )
    )

    assert "commercial_or_filing_action" in reasons


def test_analysis_config_overrides_preserve_product_context():
    settings = Settings(_env_file=None)

    overridden = apply_analysis_config_overrides(
        settings,
        {
            "product_context": {
                "dosage_form": "Film-coated tablet",
                "route_of_administration": "Oral",
            }
        },
    )

    assert overridden is not settings
    assert settings.product_context == {}
    assert overridden.product_context == {
        "dosage_form": "Film-coated tablet",
        "route_of_administration": "Oral",
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_analysis_patents": 0},
        {"max_run_duration_hours": "not-a-number"},
        {"unknown_policy_typo": "ignored"},
        {"enable_pubchem": "false"},
    ],
)
def test_analysis_config_overrides_reject_invalid_payload_atomically(overrides):
    settings = Settings(_env_file=None)
    snapshot = settings.model_dump()

    with pytest.raises(ValidationError):
        apply_analysis_config_overrides(settings, overrides)

    assert settings.model_dump() == snapshot


@pytest.mark.asyncio
async def test_finalize_report_output_attaches_execution_profile_and_reasoning_traces():
    _seed_prompt_hashes()
    completion_events: list[str] = []
    report = MagicMock()
    report.report_id = "report_123"
    report.risk_summary.overall_risk.value = "high"
    report.total_input_tokens = 100
    report.total_output_tokens = 50
    report.estimated_cost_usd = 1.25
    compound = SimpleNamespace(name="aspirin")
    patent_hit = SimpleNamespace(sources=[SimpleNamespace(value="pubchem")])
    trace = SimpleNamespace(model_dump=lambda mode="json": {"agent": "claim_analysis"})
    notify_fn = MagicMock()
    raise_if_cancelled_fn = MagicMock()
    save_checkpoint_fn = MagicMock(
        side_effect=lambda step: completion_events.append(f"checkpoint:{step}")
    )
    logger = MagicMock()

    async def write_outputs_after_recording(*_args, **_kwargs):
        completion_events.append("output_written")
        return {"status": "ok"}

    write_outputs = AsyncMock(side_effect=write_outputs_after_recording)
    generate_report = AsyncMock(return_value=report)
    search_loop_result = SimpleNamespace(total_input_tokens=7, total_output_tokens=3)
    clearance_outputs_builder = MagicMock(
        return_value={
            "clearance_decision": SimpleNamespace(
                decision=ClearanceOutcome.UNCLEAR,
                decision_audit=SimpleNamespace(
                    claim_program_summary=SimpleNamespace(
                        blocking_patent_ids=[],
                        blocking_claim_ids=[],
                    )
                ),
            ),
            "jurisdiction_decisions": [{"jurisdiction": "US"}],
            "decision_scope": SimpleNamespace(jurisdictions=[]),
            "supporting_scope": SimpleNamespace(jurisdictions=[]),
            "certification_scope": SimpleNamespace(jurisdictions=["US"]),
            "prosecution_findings": [{"patent_id": "US123"}],
            "claim_construction_record": {"standard": "Phillips"},
            "future_risk": [{"risk_type": "pending_family"}],
            "claim_program_decisions": [
                SimpleNamespace(
                    claim_number=1,
                    jurisdiction="US",
                    patent_id="US123",
                    evidence_sufficient=False,
                    missing_components=["claims_text"],
                )
            ],
            "evidence_artifacts": [{"artifact_id": "artifact-1"}],
            "evidence_adapter_results": [{"adapter_name": "pubchem_sdq"}],
            "collector_runs": [{"definition": {"collector_name": "pubchem_sdq"}, "attempts": []}],
            "coverage_gaps": [{"gap_type": "missing_claims_text"}],
            "matter_graph": {"nodes": [{"node_id": "compound:aspirin"}], "edges": []},
            "matter_graph_summary": {"node_count": 4},
            "matter_store": {"matter_graph_summary": {"node_count": 4}},
            "authority_coverage": {"policy": "official_plus_licensed"},
            "record_completeness": {"profile": "world_class_us_ep"},
            "commercial_exposure": {"business_severity": "high"},
        }
    )

    result = await finalize_report_output(
        settings=SimpleNamespace(
            matter_type="small_molecule",
            jurisdiction_policy="us_ep_core",
            clearance_threshold_profile="world_class_us_ep",
            source_authority_policy="official_plus_licensed",
            required_record_components=[],
            checkpoint_integrity_keys=TEST_INTEGRITY_KEYS,
        ),
        compound=compound,
        analyses=["analysis"],
        doe_assessments=[],
        invalidity_assessments=[],
        verification="verification",
        patent_hits=[patent_hit],
        source_health="health",
        analysis_failures=[],
        prosecution_cache={"US123": {"office_actions": "summary"}},
        critic_report="critic_report",
        drawing_evidence=None,
        timing_data=[],
        execution_profile="world_class_adaptive",
        reasoning_traces=[trace],
        triage_audit="triage_audit",
        analysis_audit="analysis_audit",
        search_funnel=[],
        triage_results=[],
        triage_in=10,
        triage_out=20,
        critic_in=1,
        critic_out=2,
        search_loop_result=search_loop_result,
        doe_in=3,
        doe_out=4,
        inv_in=5,
        inv_out=6,
        audit_trail_builder=MagicMock(return_value="audit_trail"),
        prior_step_tokens_builder=MagicMock(return_value="prior_tokens"),
        generate_report_fn=generate_report,
        write_pipeline_outputs_fn=write_outputs,
        notify_fn=notify_fn,
        raise_if_cancelled_fn=raise_if_cancelled_fn,
        save_checkpoint_fn=save_checkpoint_fn,
        make_timing_fn=MagicMock(return_value="timing"),
        pipeline_start=0.0,
        output_format="json",
        logger=logger,
        clearance_outputs_builder=clearance_outputs_builder,
    )

    assert "pipeline_mode" not in vars(report)
    assert "analysis_depth" not in vars(report)
    assert report.execution_profile == "world_class_adaptive"
    assert report.reasoning_traces == [{"agent": "claim_analysis"}]
    assert report.search_loop_result is search_loop_result
    assert report.clearance_decision.decision.value == "unclear"
    assert report.jurisdiction_decisions == [{"jurisdiction": "US"}]
    assert report.claim_program_decisions[0].claim_number == 1
    assert report.evidence_artifacts == [{"artifact_id": "artifact-1"}]
    assert report.evidence_adapter_results == [{"adapter_name": "pubchem_sdq"}]
    assert report.collector_runs == [
        {"definition": {"collector_name": "pubchem_sdq"}, "attempts": []}
    ]
    assert report.coverage_gaps == [{"gap_type": "missing_claims_text"}]
    assert report.matter_graph == {"nodes": [{"node_id": "compound:aspirin"}], "edges": []}
    assert report.matter_store == {"matter_graph_summary": {"node_count": 4}}
    assert result == {"status": "ok"}
    assert write_outputs.await_count == 1
    generate_report.assert_awaited_once()
    assert generate_report.await_args.kwargs["prosecution_cache"] == {
        "US123": {"office_actions": "summary"}
    }
    notify_fn.assert_called_once_with(8, "report", "started", {"description": "Generating report"})
    report.audit_trail.timing_data.append.assert_called_once_with("timing")
    save_checkpoint_fn.assert_called_once_with(13)
    assert completion_events == ["output_written", "checkpoint:13"]


@pytest.mark.asyncio
async def test_finalize_report_output_injects_runtime_budget_limitation():
    _seed_prompt_hashes()
    report = MagicMock()
    report.report_id = "report_123"
    report.risk_summary.overall_risk.value = "medium"
    report.total_input_tokens = 10
    report.total_output_tokens = 5
    report.estimated_cost_usd = 0.5
    report.data_limitations = []
    report.action_items = []

    result = await finalize_report_output(
        settings=SimpleNamespace(
            matter_type="small_molecule",
            jurisdiction_policy="us_ep_core",
            clearance_threshold_profile="world_class_us_ep",
            source_authority_policy="official_plus_licensed",
            required_record_components=[],
            checkpoint_integrity_keys=TEST_INTEGRITY_KEYS,
        ),
        compound=SimpleNamespace(name="aspirin"),
        analyses=[],
        doe_assessments=[],
        invalidity_assessments=[],
        verification="verification",
        patent_hits=[],
        source_health="health",
        analysis_failures=[],
        prosecution_cache={},
        critic_report=None,
        drawing_evidence=None,
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
        audit_trail_builder=MagicMock(return_value="audit_trail"),
        prior_step_tokens_builder=MagicMock(return_value="prior_tokens"),
        generate_report_fn=AsyncMock(return_value=report),
        write_pipeline_outputs_fn=AsyncMock(return_value={"status": "ok"}),
        notify_fn=MagicMock(),
        raise_if_cancelled_fn=MagicMock(),
        save_checkpoint_fn=MagicMock(),
        make_timing_fn=MagicMock(return_value="timing"),
        pipeline_start=0.0,
        output_format="json",
        logger=MagicMock(),
        clearance_outputs_builder=MagicMock(
            return_value={
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
                "future_risk": [],
                "claim_program_decisions": [],
                "evidence_artifacts": [],
                "evidence_adapter_results": [],
                "evidence_collection_plan": [],
                "coverage_gaps": [],
                "matter_graph": {},
                "matter_graph_summary": {},
                "authority_coverage": {},
                "record_completeness": {},
                "run_observability": {},
                "commercial_exposure": {},
            }
        ),
        runtime_termination=SimpleNamespace(
            reason="runtime_budget_exceeded",
            step="analyze",
            description="Run stopped during analysis because the runtime budget expired.",
            impact="The record is incomplete.",
            action_description="Resume the run.",
            action_reasoning="Budget expired before completion.",
        ),
    )

    assert result == {"status": "ok"}
    assert report.data_limitations[0].category == "runtime_budget_exceeded"
    assert report.action_items[0].action_type.value == "halt"


@pytest.mark.asyncio
async def test_finalize_report_output_no_evidence_produces_needs_review_not_crash():
    # Elements with empty evidence now map to needs_review (flagged for attorney
    # review in the report) rather than crashing the pipeline. The fail-closed gate
    # only fires for explicitly "unsupported" entries injected by other code paths.
    from praviar_pipeline.cost_tracker import CostTracker, get_current_tracker, set_current_tracker

    _seed_prompt_hashes()
    set_current_tracker(CostTracker())
    no_evidence_element = SimpleNamespace(
        element_number=1,
        element_text="a compound comprising X",
        status="met",
        reasoning="X maps to the target substituent",
        evidence="",
        spec_citation="",
    )
    analysis_with_no_evidence = SimpleNamespace(
        patent_id="US1234567B2",
        risk_level="high",
        claims_analyzed=[
            SimpleNamespace(claim_number=1, elements=[no_evidence_element]),
        ],
    )

    report = MagicMock()
    report.report_id = "report-no-evidence-test"
    report.risk_summary.overall_risk.value = "medium"
    report.risk_summary.executive_summary = (
        "Claim evidence is incomplete and requires attorney review."
    )
    report.total_input_tokens = 0
    report.total_output_tokens = 0
    report.estimated_cost_usd = 0.0
    report.patent_analyses = [analysis_with_no_evidence]
    report.data_limitations = []
    report.action_items = []

    write_outputs = AsyncMock(return_value={"json": "{}"})
    save_checkpoint = MagicMock()

    _clearance_outputs = {
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
        "future_risk": [],
        "claim_program_decisions": [],
        "evidence_artifacts": [],
        "evidence_adapter_results": [],
        "collector_runs": [],
        "evidence_collection_plan": [],
        "coverage_gaps": [],
        "matter_graph": {},
        "matter_graph_summary": {},
        "matter_store": {},
        "commercial_exposure": {},
    }

    # Must NOT raise — missing evidence → needs_review, not a hard failure.
    await finalize_report_output(
        settings=SimpleNamespace(
            matter_type="small_molecule",
            jurisdiction_policy="us_ep_core",
            clearance_threshold_profile="world_class_us_ep",
            source_authority_policy="official_plus_licensed",
            required_record_components=[],
            checkpoint_integrity_keys=TEST_INTEGRITY_KEYS,
        ),
        compound=SimpleNamespace(name="piracetam"),
        analyses=[],
        doe_assessments=[],
        invalidity_assessments=[],
        verification="verification",
        patent_hits=[],
        source_health="health",
        analysis_failures=[],
        prosecution_cache={},
        critic_report=None,
        drawing_evidence=None,
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
        audit_trail_builder=MagicMock(return_value=SimpleNamespace(prompt_hashes={})),
        prior_step_tokens_builder=MagicMock(return_value=[]),
        generate_report_fn=AsyncMock(return_value=report),
        write_pipeline_outputs_fn=write_outputs,
        notify_fn=MagicMock(),
        raise_if_cancelled_fn=MagicMock(),
        save_checkpoint_fn=save_checkpoint,
        make_timing_fn=MagicMock(return_value="timing"),
        pipeline_start=0.0,
        output_format="json",
        logger=MagicMock(),
        clearance_outputs_builder=MagicMock(return_value=_clearance_outputs),
    )

    write_outputs.assert_awaited_once()
    assert report.claim_source_span_map.needs_review_count == 1
    assert report.claim_source_span_map.unsupported_customer_visible_claim_count == 0
    assert get_current_tracker() is None


@pytest.mark.asyncio
async def test_run_pipeline_finalizes_partial_report_when_runtime_budget_exceeded():
    state = SimpleNamespace(
        settings=SimpleNamespace(
            checkpoint_enabled=False,
            max_run_duration_hours=1,
            matter_type="small_molecule",
            jurisdiction_policy="us_ep_core",
            clearance_threshold_profile="world_class_us_ep",
            source_authority_policy="official_plus_licensed",
            required_record_components=[],
        ),
        execution_profile="world_class_adaptive",
        analysis_escalation_reasons=["complex_matter_type"],
        user_input="aspirin",
        run_id="run_123",
        checkpoint_dir=Path("/tmp/run_123"),
        started_at_epoch=100.0,
        deadline_epoch=110.0,
        completed_step=0,
        timing_data=[],
        reasoning_traces=[],
        compound=SimpleNamespace(name="aspirin"),
        expanded_queries=None,
        patent_hits=[],
        source_health=None,
        search_funnel=[],
        triage_results=[],
        all_triage=[],
        triage_in=0,
        triage_out=0,
        triage_failed=0,
        analyses=[],
        analysis_failures=[],
        prosecution_cache={},
        critic_report=None,
        critic_in=0,
        critic_out=0,
        search_loop_result=None,
        doe_assessments=[],
        doe_in=0,
        doe_out=0,
        invalidity_assessments=[],
        inv_in=0,
        inv_out=0,
        verification=None,
        drawing_evidence=None,
    )

    with (
        patch("praviar_pipeline.run.bootstrap_run_context", return_value=state),
        patch("praviar_pipeline.run.execute_resolution_to_search_flow", new=AsyncMock()),
        patch(
            "praviar_pipeline.run.execute_analysis_to_verification_flow",
            new=AsyncMock(
                side_effect=RuntimeBudgetExceededError(
                    "budget exceeded",
                    step="analyze",
                    deadline_epoch=110.0,
                    elapsed_seconds=15.0,
                )
            ),
        ),
        patch(
            "praviar_pipeline.run.finalize_report_output",
            new=AsyncMock(return_value={"status": "ok"}),
        ) as finalize_mock,
        patch("praviar_pipeline.run.build_triage_audit", return_value=[]),
        patch("praviar_pipeline.run.build_analysis_audit", return_value=[]),
        patch("praviar_pipeline.run.map_relevant_patents", return_value=[]),
    ):
        result = await run_pipeline("aspirin")

    assert result == {"status": "ok"}
    assert (
        finalize_mock.await_args.kwargs["runtime_termination"].reason == "runtime_budget_exceeded"
    )
    assert finalize_mock.await_args.kwargs["verification"].all_passed is False
    assert finalize_mock.await_args.kwargs["source_health"].entries == []
