"""Tests for prompt-versioning in the API layer.

Covers:
- ``write_analysis_completed_audit_impl`` recording prompt hashes
  in the AuditLog ``details`` column
- ``PipelineAuditTrailResponse`` exposing the ``prompt_hashes`` field
- ``task_pipeline.run_pipeline_execution`` wiring: the ``write_audit_fn``
  is called exactly once after a successful run
"""

from __future__ import annotations

import asyncio
import uuid
from inspect import isawaitable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import valid_report_data

from api.schemas.reports_tracking_audit_pipeline import PipelineAuditTrailResponse
from api.workers.task_persistence import write_analysis_completed_audit_impl

# ---------------------------------------------------------------------------
# PipelineAuditTrailResponse schema
# ---------------------------------------------------------------------------


def test_pipeline_audit_trail_response_has_prompt_hashes_field() -> None:
    """PipelineAuditTrailResponse must expose the prompt_hashes field."""
    hashes = {"triage_system.txt": "a" * 64, "evaluator_system.txt": "b" * 64}
    response = PipelineAuditTrailResponse(prompt_hashes=hashes)
    assert response.prompt_hashes == hashes


def test_pipeline_audit_trail_response_prompt_hashes_default_empty() -> None:
    """Existing serialised report payloads without prompt_hashes must load."""
    response = PipelineAuditTrailResponse()
    assert response.prompt_hashes == {}


def test_pipeline_audit_trail_response_serialisation_round_trip() -> None:
    """prompt_hashes must survive JSON serialisation and deserialisation."""
    hashes = {"step3_triage.txt": "c" * 64}
    response = PipelineAuditTrailResponse(prompt_hashes=hashes)
    data = response.model_dump(mode="json")
    restored = PipelineAuditTrailResponse.model_validate(data)
    assert restored.prompt_hashes == hashes


# ---------------------------------------------------------------------------
# write_analysis_completed_audit_impl
# ---------------------------------------------------------------------------


def _valid_manifest(prompt_hashes: dict) -> dict:
    return {
        "pipeline_version": "1" * 40,
        "generated_at": "2026-05-25T00:00:00+00:00",
        "compound_query": "aspirin",
        "prompt_hashes": prompt_hashes,
        "model_versions": {"triage": "claude-test", "analysis": "claude-test"},
        "sampling": {"triage": {"temperature": 0.0}},
        "source_snapshots": {"patentsview": "2026-05-25T00:00:00+00:00"},
        "tool_definition_hashes": {"search_patents": "b" * 64},
        "tool_trace_digest": "c" * 64,
        "tool_call_count": 1,
        "cost_breakdown": {},
        "total_cost_usd": 0.0,
    }


def _valid_claim_source_span_map() -> dict:
    return {
        "generated_from": "pipeline_claim_analysis",
        "entries": [
            {
                "assertion_id": "assertion-1",
                "patent_id": "US92000001A1",
                "claim_number": 1,
                "element_number": 1,
                "report_section": "claim_element_analysis",
                "assertion_text": "Claim 1 element 1 was assessed as present.",
                "source_span_ids": ["span-1"],
                "support_status": "supported",
                "customer_visible": True,
                "review_required": False,
            }
        ],
        "spans": {
            "span-1": {
                "span_id": "span-1",
                "source_type": "element_evidence",
                "patent_id": "US92000001A1",
                "claim_number": 1,
                "element_number": 1,
                "citation": "",
                "excerpt": "claim text",
            }
        },
        "unsupported_customer_visible_claim_count": 0,
        "needs_review_count": 0,
    }


def _empty_claim_source_span_map() -> dict:
    return {
        "generated_from": "pipeline_claim_analysis",
        "entries": [],
        "spans": {},
        "unsupported_customer_visible_claim_count": 0,
        "needs_review_count": 0,
    }


def _make_analysis(
    prompt_hashes: dict | None = None,
    org_id: uuid.UUID | None = None,
    report_overrides: dict | None = None,
):
    """Build a minimal Analysis-like mock with the given prompt hashes."""
    hashes = prompt_hashes or {}
    report_data = valid_report_data()
    report_data["execution_profile"] = "world_class_adaptive"
    report_data["audit_trail"]["prompt_hashes"] = hashes
    report_data["manifest"] = _valid_manifest(hashes)
    if report_overrides:
        report_data.update(report_overrides)
    if report_data.get("total_patents_found") == 0 and report_data.get("patent_analyses") == []:
        report_data["analysis_failures"] = []
        report_data["risk_summary"] = {
            "overall_risk": "clear",
            "blocking_patents_count": 0,
            "total_patents_analyzed": 0,
            "key_risks": [],
            "executive_summary": (
                "Clearance decision: CLEAR. 0 blocking patents identified from 0 analyzed."
            ),
        }
        report_data["clearance_decision"]["decision"] = "clear"
        audit = report_data["clearance_decision"]["decision_audit"]
        audit.update(
            {
                "material_patents_reviewed": 0,
                "material_us_patents": 0,
                "material_ep_patents": 0,
                "patents_with_claims": 0,
                "patents_with_family": 0,
                "us_patents_with_prosecution_context": 0,
                "us_patents_with_file_wrapper_dossier": 0,
                "ep_patents_with_register_context": 0,
                "analysis_failures_count": 0,
                "clearance_grade_ready_patents": 0,
                "incomplete_material_patents": 0,
                "clearance_grade_ready_families": 0,
                "incomplete_material_families": 0,
                "failed_sources": [],
                "evidence_sufficient_for_clearance": True,
                "insufficiency_reasons": [],
                "evidence_warnings": [],
                "decisive_references": [],
            }
        )
        claim_program = audit["claim_program_summary"]
        for field in (
            "blocking_claim_ids",
            "contested_claim_ids",
            "medium_risk_claim_ids",
            "claims_with_strong_invalidity",
            "claims_with_insufficient_evidence",
            "blocking_patent_ids",
            "contested_patent_ids",
            "medium_risk_patent_ids",
        ):
            claim_program[field] = []
        claim_program["total_claim_programs_reviewed"] = 0
        claim_program["patent_level_fallback_count"] = 0
        report_data["claim_program_decisions"] = []
        coverage = audit["coverage_summary"]
        for field in (
            "failed_source_names",
            "reviewed_patent_ids",
            "reviewed_us_patent_ids",
            "reviewed_ep_patent_ids",
            "patents_missing_claims",
            "patents_missing_claim_level_analysis",
            "patents_missing_authoritative_records",
            "patents_missing_family_context",
            "failed_analysis_patent_ids",
            "clearance_grade_ready_patent_ids",
            "incomplete_patent_ids",
            "clearance_grade_ready_family_ids",
            "incomplete_family_ids",
            "verification_gaps",
        ):
            coverage[field] = []
        report_data["jurisdiction_decisions"] = []
        report_data["evidence_artifacts"] = []
        report_data["prosecution_dossiers"] = []
        report_data["matter_evidence_index"]["patent_records"] = []
        report_data["matter_evidence_index"]["family_records"] = []
        report_data["patents_after_triage"] = 0
        report_data["audit_trail"].update(
            {
                "total_patents_discovered": 0,
                "patents_after_hard_filter": 0,
                "patents_after_ranking": 0,
                "patents_after_triage": 0,
                "patents_analyzed": 0,
            }
        )
        for source in report_data["source_health"]["entries"]:
            if source["status"] == "failed":
                source["status"] = "skipped"
    return SimpleNamespace(
        id=uuid.uuid4(),
        org_id=org_id or uuid.uuid4(),
        overall_risk="clear",
        estimated_cost_usd=0.50,
        report_data=report_data,
    )


_AUDIT_LOG_TARGET = "api.db.models_operations.AuditLog"


class TestWriteAnalysisCompletedAuditImpl:
    def test_writes_audit_log_with_prompt_hashes(self) -> None:
        """The function must add an AuditLog row containing the prompt hashes."""
        hashes = {"triage_system.txt": "d" * 64, "analysis_system.txt": "e" * 64}
        analysis = _make_analysis(prompt_hashes=hashes)
        db = MagicMock()

        with patch(_AUDIT_LOG_TARGET) as mock_audit_log:
            mock_entry = MagicMock()
            mock_audit_log.return_value = mock_entry
            write_analysis_completed_audit_impl(db, analysis)

        mock_audit_log.assert_called_once()
        call_kwargs = mock_audit_log.call_args.kwargs
        assert call_kwargs["action"] == "analysis.completed"
        assert call_kwargs["analysis_id"] == analysis.id
        details = call_kwargs["details"]
        assert details["prompt_hashes"] == hashes
        assert details["manifest_pipeline_version"] == "1" * 40
        assert details["model_versions"] == {"triage": "claude-test", "analysis": "claude-test"}
        assert details["tool_definition_hashes"] == {"search_patents": "b" * 64}
        assert details["tool_trace_digest"] == "c" * 64
        assert details["tool_call_count"] == 1
        assert details["source_snapshot_count"] == 1
        assert details["claim_source_span_entry_count"] == 1
        assert details["claim_source_span_count"] == 1
        assert details["unsupported_customer_visible_claim_count"] == 0
        assert details["material_patent_support_count"] == 1
        assert details["decisive_reference_count"] == 1
        assert details["verification_check_count"] == 3
        assert details["factual_accuracy_rate"] == 1.0

        db.add.assert_called_once_with(mock_entry)

    def test_prompt_hashes_in_details_match_audit_trail(self) -> None:
        """Details dict must carry the exact same hashes as the audit trail."""
        hashes = {"report.txt": "f" * 64}
        analysis = _make_analysis(prompt_hashes=hashes)
        db = MagicMock()

        captured_details: dict = {}

        def capture(**kwargs):
            captured_details.update(kwargs.get("details", {}))
            return MagicMock()

        with patch(_AUDIT_LOG_TARGET, side_effect=capture):
            write_analysis_completed_audit_impl(db, analysis)

        assert captured_details["prompt_hashes"] == hashes

    def test_rejects_missing_audit_trail(self) -> None:
        """A completed analysis must not lose prompt provenance silently."""
        analysis = SimpleNamespace(
            id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            overall_risk="high",
            estimated_cost_usd=1.0,
            report_data={"execution_profile": "world_class_adaptive"},
        )
        db = MagicMock()

        with pytest.raises(ValueError, match="audit_trail.prompt_hashes is required"):
            write_analysis_completed_audit_impl(db, analysis)

        db.add.assert_not_called()

    def test_rejects_none_report_data(self) -> None:
        """A completed analysis must have report_data with prompt provenance."""
        analysis = SimpleNamespace(
            id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            overall_risk="",
            estimated_cost_usd=0.0,
            report_data=None,
        )
        db = MagicMock()

        with pytest.raises(ValueError, match="report_data must be a mapping"):
            write_analysis_completed_audit_impl(db, analysis)

        db.add.assert_not_called()

    def test_rejects_empty_prompt_hashes(self) -> None:
        """A completed analysis must carry at least one prompt hash."""
        analysis = _make_analysis(prompt_hashes={})
        db = MagicMock()

        with pytest.raises(ValueError, match="prompt_hashes must be a non-empty mapping"):
            write_analysis_completed_audit_impl(db, analysis)

        db.add.assert_not_called()

    def test_rejects_malformed_prompt_hash_digest(self) -> None:
        """Prompt hashes must be exact SHA-256 hex digests."""
        analysis = _make_analysis(prompt_hashes={"triage_system.txt": "not-a-sha"})
        db = MagicMock()

        with pytest.raises(ValueError, match="lowercase SHA-256 hex digest"):
            write_analysis_completed_audit_impl(db, analysis)

    def test_rejects_unpublishable_verification_metadata(self) -> None:
        """A completed audit must not be written for verifier-failed reports."""
        analysis = _make_analysis(
            prompt_hashes={"triage_system.txt": "d" * 64},
            report_overrides={
                "verification_summary": {
                    "total_claims_checked": 1,
                    "claims_correct": 1,
                    "claims_incorrect": 0,
                    "claims_unverifiable": 0,
                    "factual_accuracy_rate": 1.0,
                    "corrections_needed": [],
                    "overall_assessment": "FAIL",
                }
            },
        )
        db = MagicMock()

        with pytest.raises(ValueError, match="overall_assessment"):
            write_analysis_completed_audit_impl(db, analysis)

        db.add.assert_not_called()

        db.add.assert_not_called()

    def test_rejects_missing_manifest(self) -> None:
        """Completed reports must retain model/tool/source manifest provenance."""
        analysis = _make_analysis(
            prompt_hashes={"triage_system.txt": "a" * 64},
            report_overrides={"manifest": None},
        )
        db = MagicMock()

        with pytest.raises(ValueError, match="report_data.manifest is required"):
            write_analysis_completed_audit_impl(db, analysis)

        db.add.assert_not_called()

    def test_rejects_manifest_prompt_hash_drift(self) -> None:
        """Audit and manifest prompt hashes must describe the same run."""
        hashes = {"triage_system.txt": "a" * 64}
        analysis = _make_analysis(
            prompt_hashes=hashes,
            report_overrides={"manifest": _valid_manifest({"triage_system.txt": "d" * 64})},
        )
        db = MagicMock()

        with pytest.raises(ValueError, match="must match audit_trail.prompt_hashes"):
            write_analysis_completed_audit_impl(db, analysis)

        db.add.assert_not_called()

    def test_rejects_missing_tool_hashes_when_tools_ran(self) -> None:
        """Tool calls without retained tool definitions are not replayable."""
        hashes = {"triage_system.txt": "a" * 64}
        manifest = _valid_manifest(hashes)
        manifest["tool_definition_hashes"] = {}
        analysis = _make_analysis(prompt_hashes=hashes, report_overrides={"manifest": manifest})
        db = MagicMock()

        with pytest.raises(ValueError, match="manifest.tool_definition_hashes"):
            write_analysis_completed_audit_impl(db, analysis)

        db.add.assert_not_called()

    def test_rejects_unsupported_customer_visible_claims(self) -> None:
        """Unsupported customer-visible assertions must fail closed at completion."""
        support_map = _valid_claim_source_span_map()
        support_map["unsupported_customer_visible_claim_count"] = 1
        analysis = _make_analysis(
            prompt_hashes={"triage_system.txt": "a" * 64},
            report_overrides={"claim_source_span_map": support_map},
        )
        db = MagicMock()

        with pytest.raises(ValueError, match="unsupported_customer_visible_claim_count"):
            write_analysis_completed_audit_impl(db, analysis)

        db.add.assert_not_called()

    def test_rejects_supported_claim_without_source_span(self) -> None:
        """A supported customer-visible claim must cite retained source spans."""
        support_map = _valid_claim_source_span_map()
        support_map["entries"][0]["source_span_ids"] = []
        analysis = _make_analysis(
            prompt_hashes={"triage_system.txt": "a" * 64},
            report_overrides={"claim_source_span_map": support_map},
        )
        db = MagicMock()

        with pytest.raises(ValueError, match="source_span_ids"):
            write_analysis_completed_audit_impl(db, analysis)

        db.add.assert_not_called()

    def test_rejects_empty_source_span_map_when_report_has_patents(self) -> None:
        """Completion audit must fail reports access would later reject."""
        analysis = _make_analysis(
            prompt_hashes={"triage_system.txt": "a" * 64},
            report_overrides={
                "claim_source_span_map": _empty_claim_source_span_map(),
                "patent_analyses": [{"patent_id": "US92000001A1"}],
                "total_patents_found": 1,
            },
        )
        db = MagicMock()

        with pytest.raises(ValueError, match="source-span provenance"):
            write_analysis_completed_audit_impl(db, analysis)

        db.add.assert_not_called()

    def test_rejects_no_patent_clear_without_independent_zero_search_contract(self) -> None:
        """Zero search results cannot independently authorize positive clearance."""
        analysis = _make_analysis(
            prompt_hashes={"triage_system.txt": "a" * 64},
            report_overrides={
                "claim_source_span_map": _empty_claim_source_span_map(),
                "patent_analyses": [],
                "total_patents_found": 0,
            },
        )
        db = MagicMock()

        with pytest.raises(ValueError, match="clear conclusion lacks search or patent support"):
            write_analysis_completed_audit_impl(db, analysis)

        db.add.assert_not_called()

    def test_surfaces_unexpected_exceptions_after_logging(self) -> None:
        """Audit failure must keep completion from succeeding without provenance."""
        analysis = _make_analysis(prompt_hashes={"triage_system.txt": "a" * 64})
        db = MagicMock()

        with (
            patch(_AUDIT_LOG_TARGET, side_effect=RuntimeError("boom")),
            patch("api.workers.task_persistence.logger") as logger,
            pytest.raises(RuntimeError, match="boom"),
        ):
            write_analysis_completed_audit_impl(db, analysis)

        logger.error.assert_called_once()


# ---------------------------------------------------------------------------
# task_pipeline.run_pipeline_execution wiring
# ---------------------------------------------------------------------------


def _build_run_kwargs(*, write_audit_fn=None) -> dict:
    """Minimal kwargs for run_pipeline_execution that avoid touching real I/O."""
    report_dict = {
        "report_id": str(uuid.uuid4()),
        "compound": {},
        "audit_trail": {"prompt_hashes": {"triage_system.txt": "a" * 64}},
    }
    analysis = MagicMock()
    analysis.id = uuid.uuid4()
    analysis.org_id = uuid.uuid4()
    analysis.status = None
    analysis.pipeline_execution_id = None
    analysis.pipeline_lease_expires_at = None
    db = MagicMock()

    def fake_is_cancelled(status):
        return False

    def fake_run_async(coro):
        # The pipeline_runner_factory returns a coroutine-like; just return the report
        return report_dict

    def fake_store(a, r, d):
        pass

    def fake_upsert(db, compound, *, org_id, completed_at):
        pass

    def fake_publish(*args, **kwargs):
        pass

    def fake_log(**kwargs):
        pass

    return dict(
        db=db,
        analysis=analysis,
        analysis_id="test-analysis-id",
        pipeline_start=0.0,
        redis_client=MagicMock(),
        lost_event_counts={},
        logger=MagicMock(),
        publish_event_fn=fake_publish,
        is_cancelled_fn=fake_is_cancelled,
        store_pipeline_results_fn=fake_store,
        upsert_compound_fn=fake_upsert,
        run_async_fn=fake_run_async,
        pipeline_runner_factory=lambda on_progress, should_cancel: report_dict,
        log_output_dir_fn=fake_log,
        write_audit_fn=write_audit_fn,
    )


def test_run_pipeline_execution_calls_write_audit_fn() -> None:
    """write_audit_fn must be called exactly once after a successful run."""
    from api.db.models import AnalysisStatus
    from api.workers.task_pipeline import run_pipeline_execution

    write_audit_fn = MagicMock()
    kwargs = _build_run_kwargs(write_audit_fn=write_audit_fn)

    # Patch AnalysisStatus.COMPLETED so the status comparison works
    kwargs["analysis"].status = AnalysisStatus.PENDING

    run_pipeline_execution(**kwargs)

    write_audit_fn.assert_called_once()
    args = write_audit_fn.call_args
    assert args.args[0] is kwargs["db"]
    assert args.args[1] is kwargs["analysis"]


def test_run_pipeline_execution_skips_write_audit_when_none() -> None:
    """No error must occur when write_audit_fn is None (backwards compat)."""
    from api.db.models import AnalysisStatus
    from api.workers.task_pipeline import run_pipeline_execution

    kwargs = _build_run_kwargs(write_audit_fn=None)
    kwargs["analysis"].status = AnalysisStatus.PENDING

    # Must not raise
    run_pipeline_execution(**kwargs)


def test_run_pipeline_execution_rolls_back_when_audit_write_fails() -> None:
    """Completion must fail visibly if prompt-provenance audit persistence fails."""
    from api.db.models import AnalysisStatus
    from api.workers.task_pipeline import run_pipeline_execution

    write_audit_fn = MagicMock(side_effect=RuntimeError("audit failed"))
    kwargs = _build_run_kwargs(write_audit_fn=write_audit_fn)
    kwargs["analysis"].status = AnalysisStatus.PENDING

    with (
        patch("api.workers.task_pipeline.active_analyses_gauge") as gauge,
        patch("api.workers.task_pipeline.record_pipeline_run") as record_pipeline_run,
        pytest.raises(RuntimeError, match="audit failed"),
    ):
        run_pipeline_execution(**kwargs)

    write_audit_fn.assert_called_once_with(kwargs["db"], kwargs["analysis"])
    kwargs["db"].rollback.assert_called_once()
    gauge.dec.assert_called_once()
    record_pipeline_run.assert_called_once()
    assert record_pipeline_run.call_args.kwargs["status"] == "failed"


def test_run_pipeline_execution_dispatches_faithfulness_through_configured_backend() -> None:
    """Shadow faithfulness scoring must not dispatch directly to Celery."""
    from api.db.models import AnalysisStatus
    from api.workers.task_pipeline import run_pipeline_execution

    dispatched: list[object] = []

    async_dispatch = AsyncMock(return_value="faithfulness-task")
    dispatcher = SimpleNamespace(dispatch_faithfulness_scores=async_dispatch)
    kwargs = _build_run_kwargs()
    kwargs["analysis"].status = AnalysisStatus.PENDING

    def fake_run_async(value):
        if isawaitable(value):
            dispatched.append(value)
            return asyncio.run(value)  # type: ignore[arg-type]
        return value

    kwargs["run_async_fn"] = fake_run_async

    with (
        patch("api.services.faithfulness_uq.is_feature_enabled", return_value=True),
        patch("api.services.task_dispatcher.build_dispatcher", return_value=dispatcher),
    ):
        run_pipeline_execution(**kwargs)

    assert len(dispatched) == 1
    async_dispatch.assert_awaited_once_with(
        analysis_id=str(kwargs["analysis"].id),
        org_id=str(kwargs["analysis"].org_id),
    )
