"""Service-layer tests for report export and sharing."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import (
    make_analysis_mock,
    make_mock_db,
    valid_report_data,
    valid_report_data_for_patents,
)

from api.db.models import AnalysisStatus, ExportFormat, ExportJob, ExportStatus
from api.errors import APIError
from api.services.export_receipts import export_manifest_hash, export_manifest_signature
from api.services.report_access import report_payload_fingerprint, reviewable_finding_keys
from api.services.reports import (
    MAX_EXPORT_DOWNLOAD_BYTES,
    build_blocker_family_contract_blockers,
    build_drawing_governance_blockers,
    build_reviewer_decision_blockers,
    delete_export_job,
    ensure_analysis_export_ready,
    get_export_job_for_org,
    iter_prepared_export_download,
    prepare_export_download,
    queue_export_job,
    resolve_export_download,
)


def _added_export_job(db) -> ExportJob:
    for call in db.add.call_args_list:
        obj = call.args[0]
        if isinstance(obj, ExportJob):
            return obj
    raise AssertionError("expected ExportJob to be added")


def _attach_valid_export_receipt(job: object) -> None:
    completed_at = datetime.now(UTC)
    report_payload_sha256 = "c" * 64
    artifact_sha256 = str(job.artifact_sha256)
    file_url = str(job.file_url)
    manifest = {
        "version": "export-manifest-v1",
        "generated_at": completed_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "job": {
            "id": str(job.id),
            "analysis_id": str(job.analysis_id),
        },
        "artifact": {
            "file_size_bytes": job.file_size_bytes,
            "format": job.format.value,
            "sha256": artifact_sha256,
            "storage_locator_hash": hashlib.sha256(file_url.encode()).hexdigest(),
        },
        "report": {"fingerprint": report_payload_sha256},
    }
    job.completed_at = completed_at
    job.manifest_schema_version = "export-manifest-v1"
    job.manifest_snapshot = manifest
    job.manifest_hash = export_manifest_hash(manifest)
    job.manifest_signature = export_manifest_signature(job.manifest_hash)
    job.report_payload_sha256 = report_payload_sha256


def test_drawing_governance_blocks_unbound_customer_visible_structures() -> None:
    blockers = build_drawing_governance_blockers(
        {
            "drawing_analyses": [
                {
                    "patent_id": "US123A1",
                    "structures": [{"canonical_smiles": "CCO"}],
                }
            ]
        }
    )

    assert blockers == ["Drawing evidence for US123A1 has no governance provenance."]


def test_drawing_governance_accepts_hashed_shadow_evidence() -> None:
    digest = "a" * 64
    blockers = build_drawing_governance_blockers(
        {
            "drawing_analyses": [
                {
                    "patent_id": "US123A1",
                    "governance_provenance": {
                        "rollout_state": "shadow",
                        "influence_permitted": False,
                        "evidence_gate_passed": False,
                    },
                    "structures": [
                        {
                            "canonical_smiles": "CCO",
                            "input_image_sha256": digest,
                            "source_page_image_sha256": digest,
                        }
                    ],
                }
            ]
        }
    )

    assert blockers == []


def test_blocked_decision_requires_canonical_blocker_family_records() -> None:
    report = valid_report_data()
    report["clearance_decision"]["decision"] = "blocked"
    report["clearance_decision"]["decision_audit"]["claim_program_summary"][
        "blocking_claim_ids"
    ] = ["US12345678A1#claim1"]
    report["clearance_decision"]["decision_audit"]["claim_program_summary"][
        "blocking_patent_ids"
    ] = ["US12345678A1"]

    assert build_blocker_family_contract_blockers(report) == [
        "The blocked decision has no canonical blocker-family records."
    ]


def test_canonical_blocker_family_contract_is_accepted() -> None:
    report = valid_report_data_for_patents(
        [
            {
                "patent_id": "US12345678A1",
                "risk_level": "high",
            }
        ]
    )

    assert build_blocker_family_contract_blockers(report) == []


def test_blocker_family_contract_rejects_projection_not_rebuilt_from_evidence() -> None:
    report = valid_report_data_for_patents(
        [
            {
                "patent_id": "US12345678A1",
                "risk_level": "high",
            }
        ]
    )
    blocker_claim = report["clearance_decision"]["decision_audit"]["blocker_families"][0][
        "blocking_claims"
    ][0]
    blocker_claim["record_basis"] = [
        "fixture_verified_claim_text",
        "tampered_but_well_formed_basis",
    ]

    assert build_blocker_family_contract_blockers(report) == [
        "The blocker-family decision contract does not match its canonical claim "
        "and family evidence."
    ]


@pytest.mark.asyncio
async def test_queue_export_job_dispatches_through_configured_dispatcher():
    db = make_mock_db()
    analysis = make_analysis_mock(id=uuid.uuid4())
    result = MagicMock()
    result.scalar_one_or_none.return_value = analysis
    db.execute.return_value = result
    dispatcher = SimpleNamespace(dispatch_export_job=AsyncMock(return_value="task-1"))

    with patch("api.services.reports.build_dispatcher", return_value=dispatcher):
        queued = await queue_export_job(
            db,
            analysis_id=analysis.id,
            org_id=analysis.org_id,
            user_id=uuid.uuid4(),
            export_format=ExportFormat.PDF,
            sections=[],
        )

    job = _added_export_job(db)
    assert queued.job_id == job.id
    assert queued.status == "pending"
    dispatcher.dispatch_export_job.assert_awaited_once_with(
        export_job_id=str(job.id),
        org_id=str(analysis.org_id),
    )
    assert db.commit.await_count == 1


@pytest.mark.asyncio
async def test_queue_export_job_writes_fail_closed_audit_log():
    db = make_mock_db()
    analysis = make_analysis_mock(id=uuid.uuid4())
    result = MagicMock()
    result.scalar_one_or_none.return_value = analysis
    db.execute.return_value = result
    user_id = uuid.uuid4()
    dispatcher = SimpleNamespace(dispatch_export_job=AsyncMock(return_value="task-1"))

    with (
        patch("api.services.reports.build_dispatcher", return_value=dispatcher),
        patch("api.services.reports.write_audit_log", new=AsyncMock()) as audit_log,
    ):
        queued = await queue_export_job(
            db,
            analysis_id=analysis.id,
            org_id=analysis.org_id,
            user_id=user_id,
            export_format=ExportFormat.DOCX,
            sections=["executive", "claims"],
            audience="counsel",
        )

    audit_log.assert_awaited_once()
    assert audit_log.await_args is not None
    audit_kwargs = audit_log.await_args.kwargs
    assert audit_kwargs["fail_closed"] is True
    assert audit_kwargs["org_id"] == analysis.org_id
    assert audit_kwargs["user_id"] == user_id
    assert audit_kwargs["analysis_id"] == analysis.id
    assert audit_kwargs["action"] == "report.export.queued"
    assert audit_kwargs["details"] == {
        "job_id": str(queued.job_id),
        "analysis_id": str(analysis.id),
        "user_id": str(user_id),
        "format": "docx",
        "audience": "counsel",
        "sections": ["executive", "claims"],
    }


@pytest.mark.asyncio
async def test_queue_export_job_marks_failed_if_dispatch_fails():
    db = make_mock_db()
    analysis = make_analysis_mock(id=uuid.uuid4())
    result = MagicMock()
    result.scalar_one_or_none.return_value = analysis
    db.execute.return_value = result

    dispatcher = SimpleNamespace(
        dispatch_export_job=AsyncMock(side_effect=RuntimeError("dispatcher unavailable"))
    )

    with (
        patch("api.services.reports.build_dispatcher", return_value=dispatcher),
        patch("api.services.reports.logger") as report_logger,
        pytest.raises(Exception) as exc_info,
    ):
        await queue_export_job(
            db,
            analysis_id=analysis.id,
            org_id=analysis.org_id,
            user_id=uuid.uuid4(),
            export_format=ExportFormat.PDF,
            sections=[],
        )

    assert "Export dispatch failed" in str(exc_info.value)
    job = _added_export_job(db)
    assert job.status == ExportStatus.FAILED
    report_logger.error.assert_called_once_with(
        "export_dispatch_failed",
        job_id=str(job.id),
        error_type="RuntimeError",
    )
    dispatcher.dispatch_export_job.assert_awaited_once_with(
        export_job_id=str(job.id),
        org_id=str(analysis.org_id),
    )
    assert db.commit.await_count == 2


@pytest.mark.asyncio
async def test_queue_export_job_rolls_back_and_skips_dispatch_when_audit_fails():
    db = make_mock_db()
    analysis = make_analysis_mock(id=uuid.uuid4())
    result = MagicMock()
    result.scalar_one_or_none.return_value = analysis
    db.execute.return_value = result
    dispatcher = SimpleNamespace(dispatch_export_job=AsyncMock(return_value="task-1"))

    with (
        patch("api.services.reports.build_dispatcher", return_value=dispatcher),
        patch(
            "api.services.reports.write_audit_log",
            new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
        ) as audit_log,
        pytest.raises(RuntimeError, match="audit unavailable"),
    ):
        await queue_export_job(
            db,
            analysis_id=analysis.id,
            org_id=analysis.org_id,
            user_id=uuid.uuid4(),
            export_format=ExportFormat.PDF,
            sections=[],
        )

    audit_log.assert_awaited_once()
    db.rollback.assert_awaited_once()
    dispatcher.dispatch_export_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_export_job_rolls_back_when_initial_commit_fails():
    db = make_mock_db()
    analysis = make_analysis_mock(id=uuid.uuid4())
    result = MagicMock()
    result.scalar_one_or_none.return_value = analysis
    db.execute.return_value = result
    db.commit.side_effect = RuntimeError("commit failed")
    dispatcher = SimpleNamespace(dispatch_export_job=AsyncMock(return_value="task-1"))

    with (
        patch("api.services.reports.build_dispatcher", return_value=dispatcher),
        pytest.raises(RuntimeError, match="commit failed"),
    ):
        await queue_export_job(
            db,
            analysis_id=analysis.id,
            org_id=analysis.org_id,
            user_id=uuid.uuid4(),
            export_format=ExportFormat.PDF,
            sections=[],
        )

    db.rollback.assert_awaited_once()
    dispatcher.dispatch_export_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_export_job_rolls_back_when_dispatch_failure_commit_fails():
    db = make_mock_db()
    analysis = make_analysis_mock(id=uuid.uuid4())
    result = MagicMock()
    result.scalar_one_or_none.return_value = analysis
    db.execute.return_value = result
    db.commit.side_effect = [None, RuntimeError("status commit failed")]
    dispatcher = SimpleNamespace(
        dispatch_export_job=AsyncMock(side_effect=RuntimeError("dispatcher unavailable"))
    )

    with (
        patch("api.services.reports.build_dispatcher", return_value=dispatcher),
        pytest.raises(RuntimeError, match="status commit failed"),
    ):
        await queue_export_job(
            db,
            analysis_id=analysis.id,
            org_id=analysis.org_id,
            user_id=uuid.uuid4(),
            export_format=ExportFormat.PDF,
            sections=[],
        )

    job = _added_export_job(db)
    assert job.status == ExportStatus.FAILED
    db.rollback.assert_awaited_once()
    dispatcher.dispatch_export_job.assert_awaited_once_with(
        export_job_id=str(job.id),
        org_id=str(analysis.org_id),
    )


@pytest.mark.asyncio
async def test_ensure_analysis_export_ready_requires_completed_report_payload():
    db = make_mock_db()
    analysis = make_analysis_mock(
        status=AnalysisStatus.RUNNING,
        report_data={
            "trust_mode": "counsel",
            "opinion_readiness": {"export_ready": True},
        },
    )

    with pytest.raises(APIError) as exc_info:
        await ensure_analysis_export_ready(
            db,
            analysis_id=analysis.id,
            org_id=analysis.org_id,
            analysis=analysis,
        )

    assert exc_info.value.status == 409
    assert "completed report payload" in exc_info.value.detail
    db.execute.assert_not_awaited()


def test_reviewer_decision_blockers_include_review_required_claim_source_spans():
    report_data = valid_report_data(
        patent_analyses=[
            {"patent_id": "US91000017A1", "risk_level": "high"},
        ],
    )
    report_data["claim_source_span_map"]["entries"].append(
        {
            "assertion_id": "assertion-needs-review-1",
            "patent_id": "US91000017A1",
            "claim_number": 1,
            "element_number": 2,
            "report_section": "claim_element_analysis",
            "assertion_text": "Claim 1 element 2 was assessed as unclear.",
            "source_span_ids": [],
            "support_status": "needs_review",
            "customer_visible": True,
            "review_required": True,
        }
    )
    report_data["claim_source_span_map"]["needs_review_count"] = 1
    report_fingerprint = report_payload_fingerprint(report_data)

    blockers = build_reviewer_decision_blockers(
        report_data=report_data,
        reviewer_decisions=[
            SimpleNamespace(
                finding_type="patent",
                finding_ref="US91000017A1",
                report_fingerprint=report_fingerprint,
                decision="accept",
                reviewer_user_id="clerk_reviewer_1",
            ),
            SimpleNamespace(
                finding_type="patent",
                finding_ref="US91000017A1",
                report_fingerprint=report_fingerprint,
                decision="accept",
                reviewer_user_id="clerk_reviewer_2",
            ),
        ],
    )

    assert any(
        "assertion-needs-review-1 has no reviewer decision accepting" in blocker
        for blocker in blockers
    )


def test_reviewer_decision_blockers_block_unapplied_claim_element_edit():
    report_data = valid_report_data()
    report_data["claim_source_span_map"]["entries"].append(
        {
            "assertion_id": "assertion-needs-review-1",
            "patent_id": "US91000017A1",
            "claim_number": 1,
            "element_number": 2,
            "report_section": "claim_element_analysis",
            "assertion_text": "Claim 1 element 2 was assessed as unclear.",
            "source_span_ids": [],
            "support_status": "needs_review",
            "customer_visible": True,
            "review_required": True,
        }
    )
    report_data["claim_source_span_map"]["needs_review_count"] = 1
    report_fingerprint = report_payload_fingerprint(report_data)

    blockers = build_reviewer_decision_blockers(
        report_data=report_data,
        reviewer_decisions=[
            SimpleNamespace(
                finding_type="claim_element",
                finding_ref="assertion-needs-review-1",
                report_fingerprint=report_fingerprint,
                decision="edit",
                reviewer_user_id="clerk_reviewer_1",
            )
        ],
    )

    assert blockers == [
        "MEDIUM finding assertion-needs-review-1 has proposed reviewer edits "
        "that are not applied to the current report snapshot."
    ]


@pytest.mark.parametrize(
    ("decisions", "expected_fragment"),
    [
        (
            [
                ("accept", "clerk_reviewer_1"),
                ("reject", "clerk_reviewer_2"),
            ],
            "reviewer rejection that must be resolved",
        ),
        (
            [
                ("edit", "clerk_reviewer_1"),
                ("edit", "clerk_reviewer_2"),
            ],
            "proposed reviewer edits that are not applied",
        ),
    ],
)
def test_reviewer_decision_blockers_require_resolved_common_disposition(
    decisions,
    expected_fragment,
):
    report_data = valid_report_data(
        patent_analyses=[
            {"patent_id": "US91000017A1", "risk_level": "high"},
        ],
    )
    report_fingerprint = report_payload_fingerprint(report_data)

    blockers = build_reviewer_decision_blockers(
        report_data=report_data,
        reviewer_decisions=[
            SimpleNamespace(
                finding_type="patent",
                finding_ref="US91000017A1",
                report_fingerprint=report_fingerprint,
                decision=decision,
                reviewer_user_id=reviewer_user_id,
            )
            for decision, reviewer_user_id in decisions
        ],
    )

    assert len(blockers) == 1
    assert expected_fragment in blockers[0]


def test_reviewer_decision_blockers_reject_stale_report_fingerprints():
    report_data = valid_report_data(
        patent_analyses=[
            {"patent_id": "US91000017A1", "risk_level": "high"},
        ],
    )

    blockers = build_reviewer_decision_blockers(
        report_data=report_data,
        reviewer_decisions=[
            SimpleNamespace(
                finding_type="patent",
                finding_ref="US91000017A1",
                report_fingerprint="old-report-fingerprint",
                decision="accept",
                reviewer_user_id="clerk_reviewer_1",
            ),
            SimpleNamespace(
                finding_type="patent",
                finding_ref="US91000017A1",
                report_fingerprint="old-report-fingerprint",
                decision="accept",
                reviewer_user_id="clerk_reviewer_2",
            ),
        ],
    )

    assert blockers == [
        "HIGH finding US91000017A1 has no reviewer decision accepting the current report snapshot."
    ]


def test_reviewer_decision_blockers_accept_patent_number_refs():
    report_data = valid_report_data(
        patent_analyses=[
            {"patent_number": "US91000005A1", "risk_level": "high"},
        ],
    )
    report_fingerprint = report_payload_fingerprint(report_data)

    blockers = build_reviewer_decision_blockers(
        report_data=report_data,
        reviewer_decisions=[
            SimpleNamespace(
                finding_type="patent",
                finding_ref="US91000005A1",
                report_fingerprint=report_fingerprint,
                decision="accept",
                reviewer_user_id="clerk_reviewer_1",
            ),
            SimpleNamespace(
                finding_type="patent",
                finding_ref="US91000005A1",
                report_fingerprint=report_fingerprint,
                decision="accept",
                reviewer_user_id="clerk_reviewer_2",
            ),
        ],
    )

    assert blockers == []


def test_reviewable_finding_keys_include_patent_number_refs():
    report_data = valid_report_data(
        patent_analyses=[
            {"patent_number": "US91000005A1", "risk_level": "high"},
        ],
    )

    assert ("patent", "US91000005A1") in reviewable_finding_keys(report_data)


@pytest.mark.asyncio
async def test_export_job_lookup_requires_job_and_analysis_org_match():
    db = make_mock_db()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result

    with pytest.raises(APIError):
        await get_export_job_for_org(db, job_id=uuid.uuid4(), org_id=uuid.uuid4())

    (statement,) = db.execute.await_args.args
    compiled = str(statement)
    assert "export_jobs.org_id" in compiled
    assert "analyses.org_id" in compiled


@pytest.mark.asyncio
async def test_delete_export_job_removes_local_artifact_and_record(tmp_path):
    db = make_mock_db()
    artifact = tmp_path / "report.pdf"
    artifact.write_bytes(b"evidence")
    user_id = uuid.uuid4()
    job = MagicMock(
        id=uuid.uuid4(),
        analysis_id=uuid.uuid4(),
        status=ExportStatus.COMPLETED,
        format=ExportFormat.PDF,
        file_url=str(artifact),
        user_id=user_id,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    db.execute.return_value = result
    org_id = uuid.uuid4()

    with (
        patch(
            "api.services.reports.get_settings",
            return_value=SimpleNamespace(
                export_dir=str(tmp_path),
                gcs_bucket_name="",
                gcp_project_id="",
            ),
        ),
        patch("api.services.reports.write_audit_log", new=AsyncMock()) as audit,
    ):
        await delete_export_job(
            db,
            job_id=job.id,
            org_id=org_id,
            user_id=user_id,
        )

    assert not artifact.exists()
    (lookup_statement,) = db.execute.await_args_list[0].args
    assert lookup_statement._for_update_arg is not None
    db.delete.assert_awaited_once_with(job)
    assert db.commit.await_count == 2
    assert audit.await_count == 2
    assert [call.kwargs["action"] for call in audit.await_args_list] == [
        "report.export.deletion_requested",
        "report.export.deleted",
    ]
    assert all(call.kwargs["fail_closed"] is True for call in audit.await_args_list)


@pytest.mark.asyncio
async def test_delete_export_job_rejects_non_owner_without_org_wide_authority():
    db = make_mock_db()
    job = MagicMock(
        id=uuid.uuid4(),
        analysis_id=uuid.uuid4(),
        status=ExportStatus.COMPLETED,
        format=ExportFormat.PDF,
        file_url="",
        user_id=uuid.uuid4(),
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    db.execute.return_value = result

    with pytest.raises(APIError, match="Only the export owner or counsel") as exc_info:
        await delete_export_job(
            db,
            job_id=job.id,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
        )

    assert exc_info.value.status == 403
    db.delete.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_export_job_leaves_artifact_when_intent_audit_fails(tmp_path):
    db = make_mock_db()
    artifact = tmp_path / "report.pdf"
    artifact.write_bytes(b"evidence")
    job = MagicMock(
        id=uuid.uuid4(),
        analysis_id=uuid.uuid4(),
        status=ExportStatus.COMPLETED,
        format=ExportFormat.PDF,
        file_url=str(artifact),
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    db.execute.return_value = result

    with (
        patch(
            "api.services.reports.get_settings",
            return_value=SimpleNamespace(
                export_dir=str(tmp_path),
                gcs_bucket_name="",
                gcp_project_id="",
            ),
        ),
        patch(
            "api.services.reports.write_audit_log",
            new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
        ),
        pytest.raises(RuntimeError, match="audit unavailable"),
    ):
        await delete_export_job(
            db,
            job_id=job.id,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            allow_org_wide=True,
        )

    assert artifact.exists()
    db.commit.assert_not_awaited()
    db.delete.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_export_job_leaves_artifact_when_intent_commit_fails(tmp_path):
    db = make_mock_db()
    artifact = tmp_path / "report.pdf"
    artifact.write_bytes(b"evidence")
    job = MagicMock(
        id=uuid.uuid4(),
        analysis_id=uuid.uuid4(),
        status=ExportStatus.COMPLETED,
        format=ExportFormat.PDF,
        file_url=str(artifact),
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    db.execute.return_value = result
    db.commit.side_effect = RuntimeError("commit unavailable")

    with (
        patch(
            "api.services.reports.get_settings",
            return_value=SimpleNamespace(
                export_dir=str(tmp_path),
                gcs_bucket_name="",
                gcp_project_id="",
            ),
        ),
        patch("api.services.reports.write_audit_log", new=AsyncMock()),
        pytest.raises(RuntimeError, match="commit unavailable"),
    ):
        await delete_export_job(
            db,
            job_id=job.id,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            allow_org_wide=True,
        )

    assert artifact.exists()
    db.delete.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_export_job_retains_audited_intent_when_completion_audit_fails(
    tmp_path,
):
    db = make_mock_db()
    artifact = tmp_path / "report.pdf"
    artifact.write_bytes(b"evidence")
    job = MagicMock(
        id=uuid.uuid4(),
        analysis_id=uuid.uuid4(),
        status=ExportStatus.COMPLETED,
        format=ExportFormat.PDF,
        file_url=str(artifact),
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    db.execute.return_value = result
    audit = AsyncMock(side_effect=[None, RuntimeError("completion audit unavailable")])

    with (
        patch(
            "api.services.reports.get_settings",
            return_value=SimpleNamespace(
                export_dir=str(tmp_path),
                gcs_bucket_name="",
                gcp_project_id="",
            ),
        ),
        patch("api.services.reports.write_audit_log", new=audit),
        pytest.raises(RuntimeError, match="completion audit unavailable"),
    ):
        await delete_export_job(
            db,
            job_id=job.id,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            allow_org_wide=True,
        )

    assert not artifact.exists()
    assert db.commit.await_count == 1
    assert audit.await_args_list[0].kwargs["action"] == "report.export.deletion_requested"
    db.delete.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_export_job_rejects_active_worker_job():
    db = make_mock_db()
    job = MagicMock(
        id=uuid.uuid4(),
        status=ExportStatus.PROCESSING,
        file_url="",
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    db.execute.return_value = result

    with pytest.raises(APIError, match="active export cannot be deleted") as exc_info:
        await delete_export_job(
            db,
            job_id=job.id,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            allow_org_wide=True,
        )

    assert exc_info.value.status == 409
    db.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_export_job_rejects_retryable_failed_job():
    db = make_mock_db()
    job = MagicMock(
        id=uuid.uuid4(),
        status=ExportStatus.FAILED,
        processing_lease_expires_at=object(),
        file_url="",
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    db.execute.return_value = result

    with pytest.raises(APIError, match="active export cannot be deleted") as exc_info:
        await delete_export_job(
            db,
            job_id=job.id,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            allow_org_wide=True,
        )

    assert exc_info.value.status == 409
    db.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_export_job_removes_allowlisted_gcs_artifact():
    db = make_mock_db()
    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    job_id = uuid.uuid4()
    job = MagicMock(
        id=job_id,
        analysis_id=analysis_id,
        status=ExportStatus.COMPLETED,
        format=ExportFormat.PDF,
        file_url=(
            f"gs://praviar-exports/exports/{org_id}/{analysis_id}/{job_id}/execution-a/report.pdf"
        ),
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    db.execute.return_value = result
    storage = MagicMock()
    run_blocking = AsyncMock()

    with (
        patch(
            "api.services.reports.get_settings",
            return_value=SimpleNamespace(
                export_dir="/tmp/praviar-exports",
                gcs_bucket_name="praviar-exports",
                gcp_project_id="praviar-prod",
            ),
        ),
        patch("api.services.reports.ObjectStorage", return_value=storage),
        patch("api.services.reports.run_blocking_sdk_call", run_blocking),
        patch("api.services.reports.write_audit_log", new=AsyncMock()),
    ):
        await delete_export_job(
            db,
            job_id=job.id,
            org_id=org_id,
            user_id=uuid.uuid4(),
            allow_org_wide=True,
        )

    run_blocking.assert_awaited_once()
    assert run_blocking.await_args.args[:3] == (
        "gcs.export.delete",
        storage.delete_blob,
        f"exports/{org_id}/{analysis_id}/{job_id}/execution-a/report.pdf",
    )
    db.delete.assert_awaited_once_with(job)


@pytest.mark.asyncio
async def test_delete_export_job_rejects_cross_job_gcs_object_path():
    db = make_mock_db()
    org_id = uuid.uuid4()
    job = MagicMock(
        id=uuid.uuid4(),
        analysis_id=uuid.uuid4(),
        status=ExportStatus.COMPLETED,
        format=ExportFormat.PDF,
        file_url=(
            "gs://praviar-exports/"
            f"exports/{org_id}/{uuid.uuid4()}/{uuid.uuid4()}/execution-a/report.pdf"
        ),
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    db.execute.return_value = result

    with (
        patch(
            "api.services.reports.get_settings",
            return_value=SimpleNamespace(
                export_dir="/tmp/praviar-exports",
                gcs_bucket_name="praviar-exports",
                gcp_project_id="praviar-prod",
            ),
        ),
        pytest.raises(APIError, match="Invalid export object path") as exc_info,
    ):
        await delete_export_job(
            db,
            job_id=job.id,
            org_id=org_id,
            user_id=uuid.uuid4(),
            allow_org_wide=True,
        )

    assert exc_info.value.status == 403
    db.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_export_download_returns_authorized_gcs_object_reference(
    monkeypatch: pytest.MonkeyPatch,
):
    db = make_mock_db()
    job_id = uuid.uuid4()
    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    content = b"%PDF-1.7\nverified"
    job = MagicMock()
    job.id = job_id
    job.analysis_id = analysis_id
    job.status = ExportStatus.COMPLETED
    job.file_url = (
        f"gs://praviar-exports/exports/{org_id}/{analysis_id}/{job_id}/execution-a/report.pdf"
    )
    job.format = ExportFormat.PDF
    job.file_size_bytes = len(content)
    job.artifact_sha256 = hashlib.sha256(content).hexdigest()
    _attach_valid_export_receipt(job)
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    db.execute.return_value = result
    monkeypatch.setattr(
        "api.services.reports.get_settings",
        lambda: SimpleNamespace(
            gcs_bucket_name="praviar-exports",
            gcp_project_id="praviar-prod",
            export_dir="/tmp/praviar-exports",
        ),
    )

    download = await resolve_export_download(
        db,
        job_id=job_id,
        org_id=org_id,
    )

    assert download.gcs_uri is not None
    assert download.gcs_uri.bucket == "praviar-exports"
    assert download.gcs_uri.blob_path.endswith("/execution-a/report.pdf")
    assert download.local_path is None
    assert download.filename == "report.pdf"


@pytest.mark.asyncio
async def test_resolve_export_download_rejects_wrong_gcs_bucket(
    monkeypatch: pytest.MonkeyPatch,
):
    db = make_mock_db()
    job_id = uuid.uuid4()
    job = MagicMock()
    job.id = job_id
    job.analysis_id = uuid.uuid4()
    job.status = ExportStatus.COMPLETED
    job.file_url = "gs://attacker-bucket/exports/org-a/analysis-a/job-a/report.pdf"
    job.format = ExportFormat.PDF
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    db.execute.return_value = result
    monkeypatch.setattr(
        "api.services.reports.get_settings",
        lambda: SimpleNamespace(
            gcs_bucket_name="praviar-exports",
            gcp_project_id="praviar-prod",
            export_dir="/tmp/praviar-exports",
        ),
    )

    with pytest.raises(Exception) as exc_info:
        await resolve_export_download(db, job_id=job_id, org_id=uuid.uuid4())

    assert "Invalid export object bucket" in str(exc_info.value)


@pytest.mark.asyncio
async def test_resolve_export_download_rejects_cross_job_gcs_object_path(
    monkeypatch: pytest.MonkeyPatch,
):
    db = make_mock_db()
    job_id = uuid.uuid4()
    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    job = MagicMock()
    job.id = job_id
    job.analysis_id = analysis_id
    job.status = ExportStatus.COMPLETED
    job.file_url = (
        f"gs://praviar-exports/exports/{org_id}/{analysis_id}/{uuid.uuid4()}/execution-a/report.pdf"
    )
    job.format = ExportFormat.PDF
    job.file_size_bytes = 12
    job.artifact_sha256 = "a" * 64
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    db.execute.return_value = result
    monkeypatch.setattr(
        "api.services.reports.get_settings",
        lambda: SimpleNamespace(
            gcs_bucket_name="praviar-exports",
            gcp_project_id="praviar-prod",
            export_dir="/tmp/praviar-exports",
        ),
    )

    with pytest.raises(APIError, match="Invalid export object path") as exc_info:
        await resolve_export_download(db, job_id=job_id, org_id=org_id)

    assert exc_info.value.status == 403


@pytest.mark.parametrize(
    ("file_size_bytes", "artifact_sha256", "expected_detail"),
    [
        (0, "a" * 64, "Export artifact size is invalid"),
        (MAX_EXPORT_DOWNLOAD_BYTES + 1, "a" * 64, "Export artifact size is invalid"),
        (12, "not-a-digest", "Export artifact digest is invalid"),
    ],
)
@pytest.mark.asyncio
async def test_resolve_export_download_rejects_invalid_integrity_metadata(
    monkeypatch: pytest.MonkeyPatch,
    file_size_bytes: int,
    artifact_sha256: str,
    expected_detail: str,
):
    db = make_mock_db()
    job_id = uuid.uuid4()
    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    job = MagicMock(
        id=job_id,
        analysis_id=analysis_id,
        status=ExportStatus.COMPLETED,
        file_url=(
            f"gs://praviar-exports/exports/{org_id}/{analysis_id}/{job_id}/execution-a/report.pdf"
        ),
        format=ExportFormat.PDF,
        file_size_bytes=file_size_bytes,
        artifact_sha256=artifact_sha256,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    db.execute.return_value = result
    monkeypatch.setattr(
        "api.services.reports.get_settings",
        lambda: SimpleNamespace(
            gcs_bucket_name="praviar-exports",
            gcp_project_id="praviar-prod",
            export_dir="/tmp/praviar-exports",
        ),
    )

    with pytest.raises(APIError, match=expected_detail) as exc_info:
        await resolve_export_download(db, job_id=job_id, org_id=org_id)

    assert exc_info.value.status == 409


def test_prepare_export_download_verifies_before_release(
    monkeypatch: pytest.MonkeyPatch,
):
    content = b"%PDF-1.7\nverified"
    storage = MagicMock()
    storage.iter_blob.return_value = iter([content[:5], content[5:]])
    monkeypatch.setattr("api.services.reports.ObjectStorage", MagicMock(return_value=storage))
    monkeypatch.setattr(
        "api.services.reports.get_settings",
        lambda: SimpleNamespace(gcp_project_id="praviar-prod"),
    )
    job = MagicMock(
        file_size_bytes=len(content),
        artifact_sha256=hashlib.sha256(content).hexdigest(),
    )
    download = SimpleNamespace(
        job=job,
        gcs_uri=SimpleNamespace(bucket="praviar-exports", blob_path="exports/report.pdf"),
    )

    prepared = prepare_export_download(download)
    try:
        assert prepared.size == len(content)
        assert b"".join(iter_prepared_export_download(prepared)) == content
        storage.iter_blob.assert_called_once_with("exports/report.pdf")
    finally:
        prepared.close()


@pytest.mark.parametrize("mutation", ["oversize", "truncated", "digest"])
def test_prepare_export_download_fails_closed_on_artifact_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
):
    expected = b"trusted"
    actual = {
        "oversize": b"trusted!",
        "truncated": b"truste",
        "digest": b"untrust",
    }[mutation]
    storage = MagicMock()
    storage.iter_blob.return_value = iter([actual])
    monkeypatch.setattr("api.services.reports.ObjectStorage", MagicMock(return_value=storage))
    monkeypatch.setattr(
        "api.services.reports.get_settings",
        lambda: SimpleNamespace(gcp_project_id="praviar-prod"),
    )
    job = MagicMock(
        file_size_bytes=len(expected),
        artifact_sha256=hashlib.sha256(expected).hexdigest(),
    )
    download = SimpleNamespace(
        job=job,
        gcs_uri=SimpleNamespace(bucket="praviar-exports", blob_path="exports/report.pdf"),
    )

    with pytest.raises(RuntimeError, match="artifact"):
        prepare_export_download(download)
