"""Tests for prompt-versioning: stable hashes, audit-trail integration.

Covers:
- ``PromptHasher`` stability and isolation
- ``load_prompt`` recording into the global hasher
- ``PipelineAuditTrail.prompt_hashes`` field
- ``build_pipeline_audit_trail`` threading hashes into the trail
- ``finalize_report_output`` integrating prompt hashes end-to-end
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from certification_keyring_fixtures import TEST_CHECKPOINT_INTEGRITY_KEYS

from praviar_pipeline.manifest import PromptHasher, get_prompt_hasher
from praviar_pipeline.models.audit import PipelineAuditTrail
from praviar_pipeline.models.report import ClearanceOutcome
from praviar_pipeline.pipeline.runtime.audit import build_pipeline_audit_trail

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_global_hasher():
    """Each test starts with a clean global PromptHasher."""
    get_prompt_hasher().reset()
    yield
    get_prompt_hasher().reset()


# ---------------------------------------------------------------------------
# PromptHasher stability
# ---------------------------------------------------------------------------


def test_prompt_hash_is_stable_across_two_recordings(tmp_path: Path) -> None:
    """Hashing the same file content twice must return identical digests."""
    content = "stable prompt content for triage step\n"
    hasher = PromptHasher()

    digest_a = hasher.record("triage.txt", content)
    digest_b = hasher.record("triage.txt", content)

    assert digest_a == digest_b
    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert digest_a == expected


def test_prompt_hash_changes_on_single_byte_difference() -> None:
    """Any change to the file content must produce a different digest."""
    hasher = PromptHasher()
    digest_a = hasher.record("p.txt", "Alpha")
    digest_b = hasher.record("p.txt", "alpha")
    assert digest_a != digest_b


def test_two_hasher_instances_agree_on_same_content() -> None:
    """Independent PromptHasher instances must produce identical snapshots."""
    content = "deterministic content"
    h1, h2 = PromptHasher(), PromptHasher()
    h1.record("f.txt", content)
    h2.record("f.txt", content)
    assert h1.snapshot() == h2.snapshot()


def test_load_prompt_records_into_global_hasher() -> None:
    """``load_prompt`` must populate the singleton hasher with a correct hash."""
    from praviar_pipeline.clients.claude_prompting import PROMPTS_DIR, load_prompt

    prompt_file = next(PROMPTS_DIR.glob("*.txt"))
    text = load_prompt(prompt_file.name)
    snapshot = get_prompt_hasher().snapshot()

    assert prompt_file.name in snapshot
    expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert snapshot[prompt_file.name] == expected


def test_load_prompt_cached_hash_is_stable(tmp_path: Path) -> None:
    """The digest stored by ``load_prompt`` must match the on-disk content."""
    from praviar_pipeline.clients.claude_prompting import PROMPTS_DIR, load_prompt

    prompt_file = next(PROMPTS_DIR.glob("*.txt"))
    raw = (PROMPTS_DIR / prompt_file.name).read_text(encoding="utf-8")
    load_prompt(prompt_file.name)

    snapshot = get_prompt_hasher().snapshot()
    assert snapshot[prompt_file.name] == hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# PipelineAuditTrail.prompt_hashes field
# ---------------------------------------------------------------------------


def test_pipeline_audit_trail_has_prompt_hashes_field() -> None:
    """PipelineAuditTrail must accept and persist a prompt_hashes dict."""
    hashes = {"triage.txt": "a" * 64, "analysis.txt": "b" * 64}
    trail = PipelineAuditTrail(prompt_hashes=hashes)
    assert trail.prompt_hashes == hashes


def test_pipeline_audit_trail_prompt_hashes_default_empty() -> None:
    """Existing serialised trails without prompt_hashes must still load."""
    trail = PipelineAuditTrail()
    assert trail.prompt_hashes == {}


def test_pipeline_audit_trail_prompt_hashes_serialisation_round_trip() -> None:
    """prompt_hashes must survive JSON serialisation and deserialisation."""
    hashes = {"step3.txt": "c" * 64}
    trail = PipelineAuditTrail(prompt_hashes=hashes)
    data = trail.model_dump(mode="json")
    restored = PipelineAuditTrail.model_validate(data)
    assert restored.prompt_hashes == hashes


# ---------------------------------------------------------------------------
# build_pipeline_audit_trail threads prompt_hashes into PipelineAuditTrail
# ---------------------------------------------------------------------------


def test_build_pipeline_audit_trail_records_prompt_hashes() -> None:
    """build_pipeline_audit_trail must pass prompt_hashes through to the model."""
    hashes = {"triage_system.txt": "d" * 64}
    trail = build_pipeline_audit_trail(
        search_funnel=[],
        triage_audit=[],
        analysis_audit=[],
        timing_data=[],
        patent_hits=[],
        triage_results=[],
        analyses=[],
        prompt_hashes=hashes,
    )
    assert trail.prompt_hashes == hashes


def test_build_pipeline_audit_trail_defaults_to_empty_hashes() -> None:
    """When prompt_hashes is omitted the trail must use an empty dict."""
    trail = build_pipeline_audit_trail(
        search_funnel=[],
        triage_audit=[],
        analysis_audit=[],
        timing_data=[],
        patent_hits=[],
        triage_results=[],
        analyses=[],
    )
    assert trail.prompt_hashes == {}


def test_build_pipeline_audit_trail_does_not_double_count_search_funnel() -> None:
    patents = [object(), object()]
    trail = build_pipeline_audit_trail(
        search_funnel=[{"patent_id": "US1"}, {"patent_id": "US2"}],
        triage_audit=[],
        analysis_audit=[],
        timing_data=[],
        patent_hits=patents,
        triage_results=[],
        analyses=[],
    )

    assert trail.total_patents_discovered == 2


def test_build_pipeline_audit_trail_prompt_hashes_match_manifest(succinic_acid) -> None:
    """The prompt_hashes in the audit trail and the ReportManifest must agree.

    Both are sourced from the same PromptHasher singleton snapshot taken in
    ``finalize_report_output``; this test verifies end-to-end consistency.
    """
    from types import SimpleNamespace

    from praviar_pipeline.manifest import build_manifest

    # Seed the global hasher with a known hash
    hasher = get_prompt_hasher()
    hasher.record("analysis_system.txt", "some analysis prompt")

    trail = build_pipeline_audit_trail(
        search_funnel=[],
        triage_audit=[],
        analysis_audit=[],
        timing_data=[],
        patent_hits=[],
        triage_results=[],
        analyses=[],
        prompt_hashes=hasher.snapshot(),
    )

    fake_settings = SimpleNamespace(
        claude_triage_model="t",
        claude_analysis_model="a",
        claude_deep_model="d",
    )
    manifest = build_manifest(
        compound_query="aspirin",
        source_health=None,
        settings=fake_settings,
    )

    assert trail.prompt_hashes == manifest.prompt_hashes


@pytest.mark.asyncio
async def test_finalize_report_output_records_report_generation_prompt_hashes() -> None:
    """Report prompts loaded in step 8 must be retained in both provenance stores."""
    from praviar_pipeline.pipeline.runtime.flow_finalize import finalize_report_output

    hasher = get_prompt_hasher()
    hasher.record("triage_system.txt", "triage prompt")
    pre_report_hashes = hasher.snapshot()

    report = SimpleNamespace(
        report_id="report_123",
        risk_summary=SimpleNamespace(
            overall_risk=SimpleNamespace(value="low"),
            total_patents_analyzed=0,
            executive_summary="No material blocking claim overlap was identified.",
        ),
        total_input_tokens=10,
        total_output_tokens=5,
        estimated_cost_usd=0.25,
        patent_analyses=[],
        data_limitations=[],
        action_items=[],
        audit_trail=None,
    )

    async def generate_report_fn(**kwargs):
        assert kwargs["audit_trail"].prompt_hashes == pre_report_hashes
        hasher.record("report_system.txt", "report prompt")
        report.audit_trail = kwargs["audit_trail"]
        return report

    async def write_outputs_fn(report, _output_format):
        return {
            "audit_hashes": report.audit_trail.prompt_hashes,
            "manifest_hashes": report.manifest.prompt_hashes,
        }

    result = await finalize_report_output(
        settings=SimpleNamespace(
            matter_type="small_molecule",
            jurisdiction_policy="us_ep_core",
            clearance_threshold_profile="world_class_us_ep",
            source_authority_policy="official_plus_licensed",
            required_record_components=[],
            claude_triage_model="triage-model",
            claude_analysis_model="analysis-model",
            claude_deep_model="deep-model",
            checkpoint_integrity_keys=TEST_CHECKPOINT_INTEGRITY_KEYS,
        ),
        compound=SimpleNamespace(name="aspirin", original_input="aspirin"),
        analyses=[],
        doe_assessments=[],
        invalidity_assessments=[],
        verification=SimpleNamespace(),
        patent_hits=[],
        source_health=SimpleNamespace(entries=[]),
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
        audit_trail_builder=build_pipeline_audit_trail,
        prior_step_tokens_builder=lambda **_kwargs: [],
        generate_report_fn=generate_report_fn,
        write_pipeline_outputs_fn=write_outputs_fn,
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
            "authority_coverage": {},
            "record_completeness": {},
            "run_observability": {},
            "commercial_exposure": {},
        },
        user_input="aspirin",
    )

    assert result["audit_hashes"] == result["manifest_hashes"]
    assert set(result["audit_hashes"]) == {"triage_system.txt", "report_system.txt"}
