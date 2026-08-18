"""SG-reviewer (WS-3) — reviewer decisions flow into the Typst export payload.

When an attorney exports a PDF report, each accept / reject / edit decision
captured against an individual finding must be handed to the Typst renderer
so it can be printed in the final PDF appendix. These tests pin that
contract without requiring a real DB or a real Typst binary — they:

1. Call ``render_export_artifact`` directly with a list of decision dicts
   and confirm it forwards them to ``praviar_pipeline.rendering.pdf.render_pdf``
   (i.e. the API boundary does not drop the field).
2. Drive the full ``run_export_job`` loop with a mocked SQLAlchemy Session,
   and confirm that decisions loaded from ``AnalysisReviewerDecision`` rows
   are passed through to the render function (keyword ``reviewer_decisions``).
3. Confirm the empty-decisions path still forwards ``[]`` rather than
   silently dropping the kwarg — the Typst appendix prints a specific
   "no decisions recorded" line and must always receive the list.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from conftest import bind_report_data, valid_report_data, valid_report_data_for_patents

from api.db.models import AnalysisStatus, ExportFormat, ExportStatus, ReviewStatus, UserRole
from api.schemas.reports_fto_io import ExportRequest
from api.services.report_access import report_payload_fingerprint
from api.workers import task_exports


def _decision_row(
    *,
    decision: str = "accept",
    finding_ref: str = "US1234567B2",
    note: str = "",
    edited_text: str = "",
    reviewer_name: str = "Jane Attorney",
    reviewer_email: str = "jane@example.com",
    reviewer_user_id: str = "clerk_reviewer_1",
    report_fingerprint: str = "",
) -> MagicMock:
    row = MagicMock()
    row.finding_type = "patent"
    row.finding_ref = finding_ref
    row.report_fingerprint = report_fingerprint
    row.decision = decision
    row.note = note
    row.edited_text = edited_text
    row.reviewer_user_id = reviewer_user_id
    row.reviewer_name = reviewer_name
    row.reviewer_email = reviewer_email
    row.created_at = datetime(2026, 4, 15, 9, 30, tzinfo=UTC)
    return row


# ---------------------------------------------------------------------------
# render_export_artifact — forwards the field to render_pdf
# ---------------------------------------------------------------------------


def test_export_request_rejects_unknown_section_id():
    with pytest.raises(ValueError):
        ExportRequest.model_validate(
            {
                "format": "pdf",
                "sections": ["executive_summary", "made_up_section"],
                "audience": "full",
            }
        )


def test_org_export_branding_rejects_raw_logo_paths():
    from api.services.export_branding import branding_config_from_org_settings

    with pytest.raises(RuntimeError, match="logo_path is not supported"):
        branding_config_from_org_settings(
            {
                "export_branding": {
                    "firm_name": "Acme Counsel",
                    "logo_path": "/tmp/acme-logo.png",
                }
            }
        )


def test_org_export_branding_cannot_self_authorize_privilege():
    from api.services.export_branding import branding_config_from_org_settings

    branding = branding_config_from_org_settings(
        {
            "export_branding": {
                "privilege_header": "ATTORNEY-CLIENT PRIVILEGED",
                "report_classification": "ATTORNEY WORK PRODUCT",
            }
        }
    )

    assert branding.legal_marking == "CONFIDENTIAL DRAFT"
    assert "PRIVILEGED" not in branding.header_text


def test_branding_manifest_records_rendered_brand_state():
    from praviar_pipeline.rendering.branding import BrandingConfig

    branding = BrandingConfig(
        accent_color="#5FB7A6",
        firm_name="Acme Counsel",
        logo_path="/tmp/acme-logo.png",
        primary_color="#0B1F24",
    )

    manifest = task_exports._branding_manifest(branding)

    assert manifest == {
        "accent_color": "#5FB7A6",
        "display_name": "Acme Counsel",
        "firm_name": "Acme Counsel",
        "has_custom_logo": True,
        "primary_color": "#0B1F24",
        "suppresses_praviar_branding": True,
        "white_label": True,
    }


def test_branding_manifest_uses_default_praviar_state_when_unconfigured():
    assert task_exports._branding_manifest(None) == {
        "accent_color": "#0E6F68",
        "display_name": "Praviar",
        "firm_name": "",
        "has_custom_logo": False,
        "primary_color": "#0B1F24",
        "suppresses_praviar_branding": False,
        "white_label": False,
    }


class TestRenderExportArtifactForwarding:
    def test_pdf_render_receives_reviewer_decisions(self, tmp_path: Path):
        report = MagicMock()
        report.report_id = "abcdef1234567890"
        decisions = [
            {
                "finding_type": "patent",
                "finding_ref": "US1234567B2",
                "decision": "reject",
                "note": "Not blocking — expired",
                "edited_text": "",
                "reviewer_name": "Jane Attorney",
                "reviewer_email": "jane@example.com",
                "created_at": "2026-04-15T09:30:00+00:00",
            }
        ]

        with (
            patch("praviar_pipeline.rendering.pdf.render_pdf") as mock_render,
            patch.object(task_exports, "find_spec", return_value=None),
            patch.object(task_exports, "tempfile") as mock_tempfile,
        ):
            mock_tempfile.gettempdir.return_value = str(tmp_path)
            out = task_exports.render_export_artifact(
                report,
                ExportFormat.PDF,
                ExportFormat,
                reviewer_decisions=decisions,
            )

        assert out is not None
        mock_render.assert_called_once()
        _args, kwargs = mock_render.call_args
        assert kwargs.get("reviewer_decisions") == decisions

    def test_export_filename_sanitizes_report_id_path_segments(self, tmp_path: Path):
        report = MagicMock()
        report.report_id = "../../tenant-b/private-report"
        report.model_dump.return_value = {"report_id": report.report_id}

        with (
            patch.object(task_exports, "find_spec", return_value=None),
            patch.object(task_exports, "tempfile") as mock_tempfile,
        ):
            mock_tempfile.gettempdir.return_value = str(tmp_path)
            out = task_exports.render_export_artifact(
                report,
                ExportFormat.JSON,
                ExportFormat,
                reviewer_decisions=[],
            )

        assert out is not None
        export_dir = tmp_path / "praviar-exports"
        # Artifact renders into a unique per-invocation subdirectory under the
        # export root so concurrent jobs never share an on-disk path, but the
        # customer-facing filename stays clean and sanitized.
        assert out.parent.parent == export_dir
        assert out.resolve().is_relative_to(export_dir.resolve())
        assert ".." not in out.name
        assert "/" not in out.name
        assert out.name == "fto_tenant.json"

    def test_json_export_respects_selected_sections(self, tmp_path: Path):
        report = MagicMock()
        report.report_id = "abcdef1234567890"
        report.model_dump.return_value = {
            "report_id": report.report_id,
            "risk_summary": {"overall_risk": "medium"},
            "patent_analyses": [{"patent_id": "US92000004A1", "claims_analyzed": [{"n": 1}]}],
            "invalidity_assessments": [{"patent_id": "US92000004A1"}],
            "audit_trail": {"steps": []},
            "manifest": {"entries": []},
        }

        with patch.object(task_exports, "find_spec", return_value=None):
            out = task_exports._render_export_artifact(
                report,
                ExportFormat.JSON,
                ExportFormat,
                tempdir_getter=lambda: str(tmp_path),
                sections=["executive_summary"],
                audience="executive",
            )

        assert out is not None
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["export_options"]["audience"] == "executive"
        assert "patent_analyses" not in payload
        assert "invalidity_assessments" not in payload
        assert "audit_trail" not in payload
        assert "manifest" not in payload

    @pytest.mark.parametrize("audience", ["executive", "investor"])
    def test_restricted_json_export_is_recursive_allowlist_projection(
        self,
        tmp_path: Path,
        audience: str,
    ):
        sentinel_patent_id = "US99999999B2"
        report = MagicMock()
        report.report_id = "restricted123456"
        report.model_dump.return_value = {
            "report_id": report.report_id,
            "generated_at": "2026-07-11T00:00:00Z",
            "compound": {"name": "Example", "canonical_smiles": "SECRET-SMILES"},
            "risk_summary": {
                "overall_risk": "clear",
                "blocking_patents_count": 1,
                "total_patents_analyzed": 1,
                "executive_summary": f"Potential conflict with {sentinel_patent_id}",
                "key_risks": [sentinel_patent_id],
            },
            "clearance_decision": {
                "decision": "blocked",
                "decision_confidence": 0.91,
                "evidence_quality": 0.88,
                "decision_reasoning": [sentinel_patent_id],
                "decision_audit": {"blocking_patent_ids": [sentinel_patent_id]},
            },
            "patent_analyses": [
                {
                    "patent_id": sentinel_patent_id,
                    "claims_analyzed": [{"elements": [{"evidence": "SECRET-EVIDENCE"}]}],
                }
            ],
            "patent_details": {sentinel_patent_id: {"claims_text": "SECRET-CLAIM"}},
            "claim_source_span_map": {
                "spans": {"s1": {"patent_id": sentinel_patent_id, "excerpt": "SECRET"}}
            },
            "evidence_artifacts": [{"patent_id": sentinel_patent_id}],
            "matter_evidence_index": {"patent_records": [{"patent_id": sentinel_patent_id}]},
            "jurisdiction_decisions": [
                {
                    "jurisdiction": "US",
                    "decision": "blocked",
                    "blocking_patent_ids": [sentinel_patent_id],
                    "reasoning": [sentinel_patent_id],
                }
            ],
        }

        with patch.object(task_exports, "find_spec", return_value=None):
            out = task_exports._render_export_artifact(
                report,
                ExportFormat.JSON,
                ExportFormat,
                tempdir_getter=lambda: str(tmp_path),
                sections=["executive_summary", "claim_charts", "audit_trail"],
                audience=audience,
            )

        payload = json.loads(out.read_text(encoding="utf-8"))
        serialized = json.dumps(payload, sort_keys=True)
        forbidden_keys = {
            "patent_id",
            "patent_analyses",
            "patent_details",
            "claims_analyzed",
            "claims_text",
            "evidence",
            "claim_source_span_map",
            "evidence_artifacts",
            "matter_evidence_index",
            "blocking_patent_ids",
            "reviewed_patent_ids",
        }

        def keys(value):
            if isinstance(value, dict):
                for key, nested in value.items():
                    yield key
                    yield from keys(nested)
            elif isinstance(value, list):
                for nested in value:
                    yield from keys(nested)

        assert forbidden_keys.isdisjoint(set(keys(payload)))
        assert sentinel_patent_id not in serialized
        assert "SECRET" not in serialized
        assert payload["risk_summary"]["overall_risk"] == "high"
        assert payload["clearance_decision"]["decision"] == "blocked"

    def test_scientist_json_projection_removes_legal_evidence_and_sanitizes_diagnostics(
        self,
        tmp_path: Path,
    ):
        report = MagicMock(report_id="scientist-report")
        report.model_dump.return_value = {
            "report_id": "scientist-report",
            "patent_analyses": [
                {
                    "patent_id": "US1234567B2",
                    "title": "Example",
                    "risk_level": "high",
                    "claims_analyzed": [{"reasoning": "SECRET-LEGAL-MAPPING"}],
                }
            ],
            "patent_details": {"US1234567B2": {"claims_text": "SECRET-CLAIM"}},
            "claim_source_span_map": {"spans": {}},
            "analysis_failures": [{"error_message": "Bearer SUPERSECRET"}],
        }
        with patch.object(task_exports, "find_spec", return_value=None):
            out = task_exports._render_export_artifact(
                report,
                ExportFormat.JSON,
                ExportFormat,
                tempdir_getter=lambda: str(tmp_path),
                audience="scientist",
            )
        payload = json.loads(out.read_text())
        blob = json.dumps(payload)
        assert "patent_details" not in payload
        assert "claim_source_span_map" not in payload
        assert "claims_analyzed" not in blob
        assert "SUPERSECRET" not in blob
        assert "analysis_failures" not in payload
        assert "error_message" not in blob

    def test_pdf_render_receives_empty_list_when_no_decisions(self, tmp_path: Path):
        """The kwarg must always be present so Typst renders the
        'no decisions recorded' line rather than silently skipping."""
        report = MagicMock()
        report.report_id = "abcdef1234567890"

        with (
            patch("praviar_pipeline.rendering.pdf.render_pdf") as mock_render,
            patch.object(task_exports, "find_spec", return_value=None),
            patch.object(task_exports, "tempfile") as mock_tempfile,
        ):
            mock_tempfile.gettempdir.return_value = str(tmp_path)
            task_exports.render_export_artifact(
                report,
                ExportFormat.PDF,
                ExportFormat,
                reviewer_decisions=None,
            )

        mock_render.assert_called_once()
        _args, kwargs = mock_render.call_args
        # None is acceptable at the API boundary; render_pdf normalises to [].
        assert kwargs.get("reviewer_decisions") is None

    @pytest.mark.parametrize(
        ("fmt", "renderer_path"),
        [
            (ExportFormat.PDF, "praviar_pipeline.rendering.pdf.render_pdf"),
            (ExportFormat.DOCX, "praviar_pipeline.rendering.docx_report.render_docx"),
            (ExportFormat.PPTX, "praviar_pipeline.rendering.pptx_report.render_pptx"),
            (ExportFormat.XLSX, "praviar_pipeline.rendering.xlsx.render_xlsx"),
        ],
    )
    def test_visual_renderers_receive_branding_snapshot(
        self,
        fmt: ExportFormat,
        renderer_path: str,
        tmp_path: Path,
    ):
        """Every visual export renderer must receive server-owned branding."""
        report = MagicMock()
        report.report_id = "abcdef1234567890"
        branding = MagicMock()

        with (
            patch(renderer_path) as mock_render,
            patch.object(task_exports, "find_spec", return_value=None),
            patch.object(task_exports, "tempfile") as mock_tempfile,
        ):
            if fmt != ExportFormat.PDF:
                mock_render.return_value = b"PK\x03\x04"
            mock_tempfile.gettempdir.return_value = str(tmp_path)
            out = task_exports.render_export_artifact(
                report,
                fmt,
                ExportFormat,
                reviewer_decisions=[],
                branding=branding,
            )

        assert out is not None
        mock_render.assert_called_once()
        _args, kwargs = mock_render.call_args
        assert kwargs["branding"] is branding

    def test_export_dir_uses_temp_only_when_pipeline_config_package_missing(
        self,
        tmp_path: Path,
    ):
        report = MagicMock()
        report.report_id = "abcdef1234567890"
        report.model_dump.return_value = {"report_id": report.report_id}

        with patch.object(task_exports, "find_spec", return_value=None):
            out = task_exports._render_export_artifact(
                report,
                ExportFormat.JSON,
                ExportFormat,
                tempdir_getter=lambda: str(tmp_path),
            )

        assert out is not None
        # Rendered into a unique subdirectory under the temp export root; the
        # filename is the stable, sanitized slug.
        assert out.parent.parent == tmp_path / "praviar-exports"
        assert out.name == "fto_abcdef12.json"
        assert out.exists()

    def test_concurrent_renders_same_report_format_use_distinct_paths(
        self,
        tmp_path: Path,
    ):
        """Two renders of the same (stable) report_id + format must not collide.

        report_id is generated once per analysis, so without per-invocation
        path isolation two concurrent same-analysis+format export jobs would
        render to the identical path and corrupt each other's artifact.
        """
        report = MagicMock()
        report.report_id = "abcdef1234567890"
        report.model_dump.return_value = {"report_id": report.report_id}

        with patch.object(task_exports, "find_spec", return_value=None):
            out_a = task_exports._render_export_artifact(
                report,
                ExportFormat.JSON,
                ExportFormat,
                tempdir_getter=lambda: str(tmp_path),
            )
            out_b = task_exports._render_export_artifact(
                report,
                ExportFormat.JSON,
                ExportFormat,
                tempdir_getter=lambda: str(tmp_path),
            )

        assert out_a is not None and out_b is not None
        assert out_a != out_b
        assert out_a.name == out_b.name == "fto_abcdef12.json"
        assert out_a.exists() and out_b.exists()

    def test_export_dir_config_loading_errors_are_not_temp_fallbacks(
        self,
        tmp_path: Path,
    ):
        report = MagicMock()
        report.report_id = "abcdef1234567890"

        with (
            patch.object(task_exports, "find_spec", return_value=SimpleNamespace()),
            patch(
                "praviar_pipeline.config.get_settings",
                side_effect=RuntimeError("bad pipeline config"),
            ),
            pytest.raises(RuntimeError, match="bad pipeline config"),
        ):
            task_exports._render_export_artifact(
                report,
                ExportFormat.JSON,
                ExportFormat,
                tempdir_getter=lambda: str(tmp_path),
            )

        assert not (tmp_path / "praviar-exports").exists()


# ---------------------------------------------------------------------------
# run_export_job — loads decisions from DB and forwards them
# ---------------------------------------------------------------------------


class _FakeSessionContext:
    """Fake Session ctx-manager that yields a pre-seeded MagicMock db."""

    def __init__(self, db) -> None:
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *exc) -> None:
        return None


class TestRunExportJobDecisionLoading:
    @pytest.fixture(autouse=True)
    def _stable_export_artifact_hash(self, monkeypatch):
        monkeypatch.setattr(task_exports, "_sha256_file", lambda _path: "f" * 64)

    def _run_export_job(self, *, job, **kwargs):
        return task_exports.run_export_job(org_id=str(job.org_id), **kwargs)

    def _make_db(
        self,
        *,
        decisions,
        analysis_org_id,
        analysis_id,
        job,
        report_data: dict | None = None,
        review_status=None,
        analysis_status=AnalysisStatus.COMPLETED,
        requesting_user_role=UserRole.ATTORNEY,
        requesting_user_org_id=None,
        requesting_user=None,
        org_settings: dict | None = None,
        org_deletion_status: str | None = None,
    ):
        """Build a MagicMock db whose .get(...) + .execute(...) return
        the right shapes for run_export_job's code path."""
        analysis = MagicMock()
        analysis.id = analysis_id
        analysis.org_id = analysis_org_id
        analysis.status = analysis_status
        analysis.report_data = report_data or valid_report_data(
            trust_mode="counsel",
            opinion_readiness={
                "export_ready": True,
                "jurisdictions_blocking_export": [],
            },
        )
        bind_report_data(
            analysis.report_data,
            analysis_id=analysis.id,
            org_id=analysis.org_id,
        )
        job.org_id = analysis_org_id
        job_user_id = getattr(job, "user_id", None)
        if not isinstance(job_user_id, uuid.UUID):
            job_user_id = uuid.uuid4()
            job.user_id = job_user_id
        if requesting_user is None and requesting_user_role is not None:
            requesting_user = SimpleNamespace(
                id=job_user_id,
                org_id=requesting_user_org_id or analysis_org_id,
                role=requesting_user_role,
            )
        organization = SimpleNamespace(
            id=analysis_org_id,
            settings=org_settings or {},
            deletion_status=org_deletion_status,
        )

        db = MagicMock()
        db.get.side_effect = lambda model, ident, **_kwargs: {
            "ExportJob": job,
            "Analysis": analysis,
            "Organization": organization,
            "User": requesting_user,
        }[model.__name__]

        review_status_result = MagicMock()
        if review_status is None:
            review_status = SimpleNamespace(status=ReviewStatus.APPROVED)
        review_status_result.scalar_one_or_none.return_value = review_status

        decisions_result = MagicMock()
        current_fingerprint = report_payload_fingerprint(analysis.report_data)
        for decision in decisions:
            if not getattr(decision, "report_fingerprint", ""):
                decision.report_fingerprint = current_fingerprint
        decisions_result.scalars.return_value.all.return_value = decisions
        bind_result = MagicMock()
        failure_bind_result = MagicMock()
        db.execute.side_effect = [
            bind_result,
            review_status_result,
            decisions_result,
            review_status_result,
            decisions_result,
            failure_bind_result,
        ]

        db.commit.return_value = None
        return db

    def test_decisions_loaded_and_passed_to_render(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()

        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF
        job.status = None
        job.sections = ["executive_summary", "audit_trail"]
        job.audience = "attorney"

        rows = [
            _decision_row(decision="accept", finding_ref="US1111111B2"),
            _decision_row(
                decision="edit",
                finding_ref="EP2222222A1",
                note="Narrow scope to claim 1",
                edited_text="Only claim 1 is arguably infringed.",
            ),
            _decision_row(decision="reject", finding_ref="WO2023333333A1"),
        ]
        db = self._make_db(
            decisions=rows,
            analysis_org_id=org_id,
            analysis_id=analysis_id,
            job=job,
            report_data=valid_report_data_for_patents(
                [
                    {"patent_id": "US1111111B2", "risk_level": "low"},
                    {"patent_id": "EP2222222A1", "risk_level": "low"},
                    {"patent_id": "WO2023333333A1", "risk_level": "low"},
                ],
                trust_mode="counsel",
                opinion_readiness={
                    "export_ready": True,
                    "jurisdictions_blocking_export": [],
                },
            ),
        )

        render_fake = MagicMock()
        render_fake.return_value = Path("/tmp/fake.pdf")

        with (
            patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)),
            patch("pathlib.Path.stat") as mock_stat,
            patch("praviar_pipeline.models.report.FTOReport.model_validate") as mock_validate,
            patch(
                "api.config.get_settings",
                return_value=SimpleNamespace(app_env="test", gcs_bucket_name=""),
            ),
        ):
            mock_stat.return_value = MagicMock(st_size=42)
            mock_validate.return_value = MagicMock()

            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=MagicMock(),
                render_export_fn=render_fake,
            )

        assert result["status"] == "completed"
        assert result["artifact_sha256"] == "f" * 64
        assert result["manifest_hash"] == job.manifest_hash
        assert job.manifest_schema_version == task_exports.EXPORT_MANIFEST_SCHEMA_VERSION
        assert job.artifact_sha256 == "f" * 64
        assert len(job.report_payload_sha256) == 64
        assert len(job.manifest_hash) == 64
        assert job.completed_at is not None
        assert job.manifest_snapshot["version"] == task_exports.EXPORT_MANIFEST_SCHEMA_VERSION
        assert job.manifest_snapshot["artifact"]["sha256"] == "f" * 64
        assert job.manifest_snapshot["artifact"]["sections"] == [
            "executive_summary",
            "audit_trail",
        ]
        assert job.manifest_snapshot["artifact"]["audience_label"] == "Patent Counsel"
        assert job.manifest_snapshot["artifact"]["format_label"] == "PDF Report"
        assert job.manifest_snapshot["artifact"]["title"] == ("Patent Counsel · PDF Report")
        assert job.manifest_snapshot["branding"]["display_name"] == "Praviar"
        assert job.manifest_snapshot["branding"]["white_label"] is False
        assert job.manifest_snapshot["review"]["decision_counts"] == {
            "accept": 1,
            "edit": 1,
            "reject": 1,
        }
        assert job.manifest_snapshot["report"]["fingerprint"] == job.report_payload_sha256
        render_fake.assert_called_once()
        _args, kwargs = render_fake.call_args
        assert kwargs["sections"] == ["executive_summary", "audit_trail"]
        assert kwargs["audience"] == "attorney"
        decisions_passed = kwargs["reviewer_decisions"]
        assert isinstance(decisions_passed, list)
        assert len(decisions_passed) == 3

        kinds = [d["decision"] for d in decisions_passed]
        assert kinds == ["accept", "edit", "reject"]

        edit_row = decisions_passed[1]
        assert edit_row["finding_ref"] == "EP2222222A1"
        assert edit_row["note"] == "Narrow scope to claim 1"
        assert edit_row["edited_text"] == "Only claim 1 is arguably infringed."
        assert edit_row["reviewer_name"] == "Jane Attorney"
        assert edit_row["reviewer_email"] == "jane@example.com"
        # Timestamps come through as ISO-8601 strings so Typst JSON stays clean.
        assert edit_row["created_at"].startswith("2026-04-15T09:30:00")

    def test_worker_rechecks_readiness_after_render_before_persistence(
        self,
        tmp_path,
    ):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()
        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF
        job.status = ExportStatus.PENDING
        db = self._make_db(
            decisions=[],
            analysis_org_id=org_id,
            analysis_id=analysis_id,
            job=job,
        )

        initial_review_result = MagicMock()
        initial_review_result.scalar_one_or_none.return_value = SimpleNamespace(
            status=ReviewStatus.APPROVED
        )
        revoked_review_result = MagicMock()
        revoked_review_result.scalar_one_or_none.return_value = SimpleNamespace(
            status=ReviewStatus.UNDER_REVIEW
        )
        decisions_result = MagicMock()
        decisions_result.scalars.return_value.all.return_value = []
        db.execute.side_effect = [
            MagicMock(),
            initial_review_result,
            decisions_result,
            revoked_review_result,
            decisions_result,
        ]

        artifact = tmp_path / "stale-review.pdf"
        artifact.write_bytes(b"stale review artifact")
        render_fake = MagicMock(return_value=artifact)
        persist = MagicMock()
        logger = MagicMock()

        with (
            patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)),
            patch("praviar_pipeline.models.report.FTOReport.model_validate") as validate,
            patch.object(task_exports, "_persist_export_artifact", persist),
        ):
            validate.return_value = MagicMock()
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=logger,
                render_export_fn=render_fake,
            )

        assert result["status"] == "blocked"
        assert result["error"] == "export_inputs_changed"
        assert any("under_review" in reason for reason in result["reasons"])
        assert job.status == ExportStatus.FAILED
        assert not artifact.exists()
        persist.assert_not_called()
        logger.warning.assert_called_with(
            "export_blocked_final_readiness_recheck",
            job_id=job_id,
            analysis_id=str(analysis_id),
            org_id=str(org_id),
            reasons=result["reasons"],
        )

    def test_worker_loads_org_export_branding_before_rendering(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()

        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF
        job.status = ExportStatus.PENDING

        db = self._make_db(
            decisions=[],
            analysis_org_id=org_id,
            analysis_id=analysis_id,
            job=job,
            org_settings={
                "export_branding": {
                    "firm_name": "Acme Counsel",
                    "hide_praviar_pipeline_branding": True,
                    "disclaimer_text": "Acme counsel review only.",
                }
            },
        )
        render_fake = MagicMock(return_value=Path("/tmp/branded.pdf"))

        with (
            patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)),
            patch("pathlib.Path.stat") as mock_stat,
            patch("praviar_pipeline.models.report.FTOReport.model_validate") as mock_validate,
            patch(
                "api.config.get_settings",
                return_value=SimpleNamespace(app_env="test", gcs_bucket_name=""),
            ),
        ):
            mock_stat.return_value = MagicMock(st_size=42)
            mock_validate.return_value = MagicMock()
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=MagicMock(),
                render_export_fn=render_fake,
            )

        assert result["status"] == "completed"
        _args, kwargs = render_fake.call_args
        branding = kwargs["branding"]
        assert branding.firm_name == "Acme Counsel"
        assert branding.hide_praviar_pipeline_branding is True
        assert branding.disclaimer_text == "Acme counsel review only."

    def test_worker_blocks_invalid_org_export_branding(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()

        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF
        job.status = ExportStatus.PENDING

        db = self._make_db(
            decisions=[],
            analysis_org_id=org_id,
            analysis_id=analysis_id,
            job=job,
            org_settings={"export_branding": {"unknown_key": "not allowed"}},
        )
        render_fake = MagicMock()
        logger = MagicMock()

        with (
            patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)),
            patch("praviar_pipeline.models.report.FTOReport.model_validate") as mock_validate,
            patch(
                "api.services.risk_access.get_settings",
                return_value=SimpleNamespace(
                    require_attorney_role_for_risk_ratings=False,
                ),
            ),
        ):
            mock_validate.return_value = MagicMock()
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=logger,
                render_export_fn=render_fake,
            )

        assert result["status"] == "blocked"
        assert result["error"] == "export_invalid_branding"
        assert job.status == ExportStatus.FAILED
        render_fake.assert_not_called()
        logger.warning.assert_called()

    def test_worker_filters_stale_decisions_before_rendering_pdf(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()

        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF
        job.status = None

        rows = [
            _decision_row(decision="accept", finding_ref="US90000008A1"),
            _decision_row(decision="reject", finding_ref="US90000009A1"),
        ]
        db = self._make_db(
            decisions=rows,
            analysis_org_id=org_id,
            analysis_id=analysis_id,
            job=job,
            report_data=valid_report_data_for_patents(
                [{"patent_id": "US90000008A1", "risk_level": "low"}],
                trust_mode="counsel",
                opinion_readiness={
                    "export_ready": True,
                    "jurisdictions_blocking_export": [],
                },
            ),
        )
        render_fake = MagicMock(return_value=Path("/tmp/current.pdf"))

        with (
            patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)),
            patch("pathlib.Path.stat") as mock_stat,
            patch("praviar_pipeline.models.report.FTOReport.model_validate") as mock_validate,
            patch(
                "api.config.get_settings",
                return_value=SimpleNamespace(app_env="test", gcs_bucket_name=""),
            ),
        ):
            mock_stat.return_value = MagicMock(st_size=42)
            mock_validate.return_value = MagicMock()
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=MagicMock(),
                render_export_fn=render_fake,
            )

        assert result["status"] == "completed"
        _args, kwargs = render_fake.call_args
        assert [d["finding_ref"] for d in kwargs["reviewer_decisions"]] == ["US90000008A1"]

    def test_worker_filters_pipeline_internal_report_keys_before_schema_validation(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()

        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF
        job.status = ExportStatus.PENDING

        report_data = valid_report_data(
            trust_mode="counsel",
            jurisdiction_bundle="us_europe",
            intended_actions=["monitor"],
            opinion_readiness={
                "export_ready": True,
                "jurisdictions_blocking_export": [],
            },
        )
        report_data["pipeline_internal_marker"] = {"not": "part of export schema"}
        db = self._make_db(
            decisions=[],
            analysis_org_id=org_id,
            analysis_id=analysis_id,
            job=job,
            report_data=report_data,
        )
        render_fake = MagicMock(return_value=Path("/tmp/normalized.pdf"))

        with (
            patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)),
            patch("pathlib.Path.stat") as mock_stat,
            patch(
                "api.config.get_settings",
                return_value=SimpleNamespace(app_env="test", gcs_bucket_name=""),
            ),
        ):
            mock_stat.return_value = MagicMock(st_size=42)
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=MagicMock(),
                render_export_fn=render_fake,
            )

        assert result["status"] == "completed"
        render_fake.assert_called_once()

    def test_worker_locks_export_job_before_claiming_processing(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()

        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF
        job.status = ExportStatus.PENDING

        db = self._make_db(decisions=[], analysis_org_id=org_id, analysis_id=analysis_id, job=job)
        render_fake = MagicMock(return_value=Path("/tmp/locked.pdf"))

        with (
            patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)),
            patch("pathlib.Path.stat") as mock_stat,
            patch("praviar_pipeline.models.report.FTOReport.model_validate") as mock_validate,
        ):
            mock_stat.return_value = MagicMock(st_size=42)
            mock_validate.return_value = MagicMock()
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=MagicMock(),
                render_export_fn=render_fake,
            )

        assert result["status"] == "completed"

    @pytest.mark.parametrize(
        "deletion_status",
        ["billing_cancellation_pending", "archive_deletion_pending", "erased"],
    )
    def test_worker_fences_artifact_persistence_once_org_erasure_starts(
        self,
        deletion_status,
        tmp_path,
    ):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()
        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF
        job.status = ExportStatus.PENDING
        db = self._make_db(
            decisions=[],
            analysis_org_id=org_id,
            analysis_id=analysis_id,
            job=job,
            org_deletion_status=deletion_status,
        )
        artifact = tmp_path / "must-not-persist.pdf"
        artifact.write_bytes(b"sensitive report")
        render_fake = MagicMock(return_value=artifact)

        with (
            patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)),
            patch("praviar_pipeline.models.report.FTOReport.model_validate") as validate,
            patch.object(task_exports, "_persist_export_artifact") as persist,
        ):
            validate.return_value = MagicMock()
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=MagicMock(),
                render_export_fn=render_fake,
            )

        assert result["status"] == "blocked"
        assert result["error"] == "organization_erasure_in_progress"
        assert job.status == ExportStatus.FAILED
        assert not artifact.exists()
        persist.assert_not_called()
        assert db.get.call_args_list[0].kwargs == {"with_for_update": True}

    def test_worker_blocks_client_requester_before_rendering_full_export(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()

        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF
        job.status = ExportStatus.PENDING
        job.user_id = uuid.uuid4()

        db = self._make_db(
            decisions=[],
            analysis_org_id=org_id,
            analysis_id=analysis_id,
            job=job,
            requesting_user_role=UserRole.CLIENT,
        )
        render_fake = MagicMock()
        logger = MagicMock()

        with patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)):
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=logger,
                render_export_fn=render_fake,
            )

        expected_message = (
            "Export blocked: Export requesting user is not permitted to render full reports."
        )
        assert result == {
            "status": "blocked",
            "error": "export_requester_not_authorized",
            "message": expected_message,
        }
        assert job.status == ExportStatus.FAILED
        assert job.error_message == result["message"]
        render_fake.assert_not_called()
        logger.error.assert_called_with(
            "export_blocked_requester_not_authorized",
            job_id=job_id,
            org_id=str(org_id),
            user_id=str(job.user_id),
            reason="Export requesting user is not permitted to render full reports.",
        )

    @pytest.mark.parametrize("export_format", [ExportFormat.DOCX, ExportFormat.PPTX])
    def test_worker_blocks_scientist_after_role_downgrade_for_restricted_format(
        self,
        export_format,
    ):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()

        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = export_format
        job.status = ExportStatus.PENDING
        job.user_id = uuid.uuid4()

        db = self._make_db(
            decisions=[],
            analysis_org_id=org_id,
            analysis_id=analysis_id,
            job=job,
            requesting_user_role=UserRole.SCIENTIST,
        )
        render_fake = MagicMock()
        logger = MagicMock()

        with patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)):
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=logger,
                render_export_fn=render_fake,
            )

        assert result == {
            "status": "blocked",
            "error": "export_requester_not_authorized",
            "message": (
                "Export blocked: Export requesting user is not permitted to render full reports."
            ),
        }
        assert job.status == ExportStatus.FAILED
        render_fake.assert_not_called()

    @pytest.mark.parametrize(
        "export_format",
        [
            ExportFormat.PDF,
            ExportFormat.JSON,
            ExportFormat.CSV,
            ExportFormat.XLSX,
        ],
    )
    def test_worker_allows_scientist_after_role_downgrade_for_permitted_format(
        self,
        export_format,
        tmp_path,
    ):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()

        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = export_format
        job.status = ExportStatus.PENDING
        job.user_id = uuid.uuid4()

        db = self._make_db(
            decisions=[],
            analysis_org_id=org_id,
            analysis_id=analysis_id,
            job=job,
            requesting_user_role=UserRole.SCIENTIST,
        )
        artifact = tmp_path / f"allowed.{export_format.value}"
        artifact.write_bytes(b"allowed")
        render_fake = MagicMock(return_value=artifact)

        with (
            patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)),
            patch("praviar_pipeline.models.report.FTOReport.model_validate") as mock_validate,
            patch(
                "api.services.risk_access.get_settings",
                return_value=SimpleNamespace(
                    require_attorney_role_for_risk_ratings=False,
                ),
            ),
        ):
            mock_validate.return_value = MagicMock()
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=MagicMock(),
                render_export_fn=render_fake,
            )

        assert result["status"] == "completed"
        render_fake.assert_called_once()

    def test_worker_blocks_scientist_export_when_attorney_risk_gate_is_enabled(
        self,
    ):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()

        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.JSON
        job.audience = "full"
        job.status = ExportStatus.PENDING
        job.user_id = uuid.uuid4()

        db = self._make_db(
            decisions=[],
            analysis_org_id=org_id,
            analysis_id=analysis_id,
            job=job,
            requesting_user_role=UserRole.SCIENTIST,
        )
        render_fake = MagicMock()

        with (
            patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)),
            patch(
                "api.services.risk_access.get_settings",
                return_value=SimpleNamespace(
                    require_attorney_role_for_risk_ratings=True,
                ),
            ),
        ):
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=MagicMock(),
                render_export_fn=render_fake,
            )

        assert result == {
            "status": "blocked",
            "error": "export_requester_not_authorized",
            "message": (
                "Export blocked: Export requesting user is not permitted to render full reports."
            ),
        }
        assert job.status == ExportStatus.FAILED
        render_fake.assert_not_called()

    def test_worker_blocks_export_when_job_and_analysis_orgs_diverge(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        job_org_id = uuid.uuid4()
        analysis_org_id = uuid.uuid4()

        job = MagicMock()
        job.analysis_id = analysis_id
        job.org_id = job_org_id
        job.format = ExportFormat.PDF
        job.status = ExportStatus.PENDING

        db = self._make_db(
            decisions=[],
            analysis_org_id=analysis_org_id,
            analysis_id=analysis_id,
            job=job,
        )
        job.org_id = job_org_id
        render_fake = MagicMock()
        logger = MagicMock()

        with patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)):
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=logger,
                render_export_fn=render_fake,
            )

        assert result == {
            "status": "blocked",
            "error": "export_tenant_mismatch",
            "message": ("Export blocked: Analysis does not belong to the export job organization."),
        }
        assert job.status == ExportStatus.FAILED
        assert job.error_message == result["message"]
        render_fake.assert_not_called()
        logger.error.assert_called_with(
            "export_blocked_tenant_mismatch",
            job_id=job_id,
            analysis_id=str(analysis_id),
            job_org_id=str(job_org_id),
            analysis_org_id=str(analysis_org_id),
        )

    def test_empty_decisions_still_forwards_empty_list(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()
        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF

        db = self._make_db(decisions=[], analysis_org_id=org_id, analysis_id=analysis_id, job=job)

        render_fake = MagicMock()
        render_fake.return_value = Path("/tmp/empty.pdf")

        with (
            patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)),
            patch("pathlib.Path.stat") as mock_stat,
            patch("praviar_pipeline.models.report.FTOReport.model_validate") as mock_validate,
        ):
            mock_stat.return_value = MagicMock(st_size=42)
            mock_validate.return_value = MagicMock()

            self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=MagicMock(),
                render_export_fn=render_fake,
            )

        _args, kwargs = render_fake.call_args
        assert kwargs["reviewer_decisions"] == []

    def test_worker_blocks_export_when_review_status_is_revoked(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()
        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF
        job.status = None

        db = self._make_db(
            decisions=[],
            analysis_org_id=org_id,
            analysis_id=analysis_id,
            job=job,
            review_status=SimpleNamespace(status=ReviewStatus.UNDER_REVIEW),
        )
        render_fake = MagicMock()
        logger = MagicMock()

        with patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)):
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=logger,
                render_export_fn=render_fake,
            )

        assert result["status"] == "blocked"
        assert result["error"] == "export_not_ready"
        assert result["message"].startswith("Export blocked:")
        assert any("under_review" in reason for reason in result["reasons"])
        assert job.status == ExportStatus.FAILED
        assert job.error_message == result["message"]
        render_fake.assert_not_called()
        logger.warning.assert_called_once()

    def test_worker_blocks_non_completed_analysis_with_report_payload_before_render(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()
        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF
        job.status = None

        db = self._make_db(
            decisions=[],
            analysis_org_id=org_id,
            analysis_id=analysis_id,
            job=job,
            analysis_status=AnalysisStatus.RUNNING,
            report_data=valid_report_data(
                trust_mode="counsel",
                opinion_readiness={
                    "export_ready": True,
                    "jurisdictions_blocking_export": [],
                },
            ),
        )
        render_fake = MagicMock()

        with patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)):
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=MagicMock(),
                render_export_fn=render_fake,
            )

        assert result["status"] == "blocked"
        assert result["error"] == "export_not_ready"
        assert "completed report payload" in result["message"]
        assert job.status == ExportStatus.FAILED
        render_fake.assert_not_called()

    def test_worker_terminally_fails_invalid_report_payload_before_render(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()
        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF
        job.status = ExportStatus.PENDING

        db = self._make_db(
            decisions=[],
            analysis_org_id=org_id,
            analysis_id=analysis_id,
            job=job,
        )
        render_fake = MagicMock()
        logger = MagicMock()

        with (
            patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)),
            patch(
                "praviar_pipeline.models.report.FTOReport.model_validate",
                side_effect=ValueError("bad schema from /private/path"),
            ),
        ):
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=logger,
                render_export_fn=render_fake,
            )

        assert result["status"] == "blocked"
        assert result["error"] == "export_invalid_report"
        assert result["message"] == "Export failed: Report payload failed export schema validation."
        assert job.status == ExportStatus.FAILED
        assert job.processing_execution_id is None
        assert job.processing_lease_expires_at is None
        assert "/private/path" not in job.error_message
        render_fake.assert_not_called()
        logger.error.assert_called_with(
            "export_report_payload_invalid",
            job_id=job_id,
            analysis_id=str(analysis_id),
            org_id=str(org_id),
        )

    def test_worker_blocks_export_when_high_finding_lacks_dual_review(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()
        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF
        job.status = None

        db = self._make_db(
            decisions=[
                _decision_row(
                    finding_ref="US90000001A1",
                    reviewer_user_id="clerk_reviewer_1",
                )
            ],
            analysis_org_id=org_id,
            analysis_id=analysis_id,
            job=job,
            report_data=valid_report_data_for_patents(
                [
                    {"patent_id": "US90000001A1", "risk_level": "high"},
                ],
                trust_mode="counsel",
                opinion_readiness={
                    "export_ready": True,
                    "jurisdictions_blocking_export": [],
                },
            ),
        )
        render_fake = MagicMock()

        with patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)):
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=MagicMock(),
                render_export_fn=render_fake,
            )

        assert result["status"] == "blocked"
        assert any("requires dual review" in reason for reason in result["reasons"])
        assert job.status == ExportStatus.FAILED
        assert "requires dual review" in job.error_message
        render_fake.assert_not_called()

    def test_worker_blocks_export_when_claim_source_span_needs_review(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()
        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF
        job.status = None
        report_data = valid_report_data(
            trust_mode="counsel",
            opinion_readiness={
                "export_ready": True,
                "jurisdictions_blocking_export": [],
            },
        )
        report_data["claim_source_span_map"]["entries"].append(
            {
                "assertion_id": "assertion-needs-review-1",
                "patent_id": "US90000001A1",
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

        db = self._make_db(
            decisions=[],
            analysis_org_id=org_id,
            analysis_id=analysis_id,
            job=job,
            report_data=report_data,
        )
        render_fake = MagicMock()

        with patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)):
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=MagicMock(),
                render_export_fn=render_fake,
            )

        assert result["status"] == "blocked"
        assert result["error"] == "export_not_ready"
        assert any(
            "assertion-needs-review-1 has no reviewer decision" in reason
            for reason in result["reasons"]
        )
        assert job.status == ExportStatus.FAILED
        render_fake.assert_not_called()

    def test_worker_allows_export_when_high_medium_reviews_are_complete(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()
        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF
        job.status = None

        rows = [
            _decision_row(finding_ref="US90000001A1", reviewer_user_id="clerk_reviewer_1"),
            _decision_row(finding_ref="US90000001A1", reviewer_user_id="clerk_reviewer_2"),
            _decision_row(finding_ref="US90000002A1", reviewer_user_id="clerk_reviewer_1"),
        ]
        db = self._make_db(
            decisions=rows,
            analysis_org_id=org_id,
            analysis_id=analysis_id,
            job=job,
            report_data=valid_report_data_for_patents(
                [
                    {"patent_id": "US90000001A1", "risk_level": "high"},
                    {"patent_id": "US90000002A1", "risk_level": "medium"},
                ],
                trust_mode="counsel",
                opinion_readiness={
                    "export_ready": True,
                    "jurisdictions_blocking_export": [],
                },
            ),
        )
        render_fake = MagicMock(return_value=Path("/tmp/complete.pdf"))

        with (
            patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)),
            patch("pathlib.Path.stat") as mock_stat,
            patch("praviar_pipeline.models.report.FTOReport.model_validate") as mock_validate,
        ):
            mock_stat.return_value = MagicMock(st_size=42)
            mock_validate.return_value = MagicMock()
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=MagicMock(),
                render_export_fn=render_fake,
            )

        assert result["status"] == "completed"
        assert job.status == ExportStatus.COMPLETED
        render_fake.assert_called_once()

    def test_worker_exception_persists_retryable_tenant_safe_error_message(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()
        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF
        job.status = None

        db = self._make_db(decisions=[], analysis_org_id=org_id, analysis_id=analysis_id, job=job)
        render_fake = MagicMock(side_effect=RuntimeError("Traceback at /srv/api/private/export.py"))

        with (
            patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)),
            patch("praviar_pipeline.models.report.FTOReport.model_validate") as mock_validate,
        ):
            mock_validate.return_value = MagicMock()
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=MagicMock(),
                render_export_fn=render_fake,
            )

        assert result == {
            "status": "failed",
            "error": "export_failed",
            "retry_after_seconds": 60,
            "message": "Export failed: See worker logs for traceback",
        }
        assert job.status == ExportStatus.FAILED
        assert job.error_message == "Export failed: See worker logs for traceback"
        assert job.processing_lease_expires_at is not None
        assert job.retry_attempts == 1
        assert "Traceback" not in job.error_message
        assert "/srv/api/private/export.py" not in job.error_message

    def test_worker_exception_exhaustion_becomes_terminal_failure(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()
        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF
        job.status = ExportStatus.PENDING
        job.retry_attempts = 2

        db = self._make_db(decisions=[], analysis_org_id=org_id, analysis_id=analysis_id, job=job)
        render_fake = MagicMock(side_effect=RuntimeError("GCS timeout"))

        with (
            patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)),
            patch("praviar_pipeline.models.report.FTOReport.model_validate") as mock_validate,
        ):
            mock_validate.return_value = MagicMock()
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=MagicMock(),
                render_export_fn=render_fake,
            )

        assert result == {
            "status": "blocked",
            "error": "export_retry_exhausted",
            "message": "Export failed: Repeated worker retries were exhausted.",
        }
        assert job.status == ExportStatus.FAILED
        assert job.error_message == "Export failed: Repeated worker retries were exhausted."
        assert job.retry_attempts == 3
        assert job.processing_execution_id is None
        assert job.processing_lease_expires_at is None

    def test_stale_execution_cannot_overwrite_newer_completion_claim(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()

        first_job = MagicMock()
        first_job.analysis_id = analysis_id
        first_job.org_id = org_id
        first_job.format = ExportFormat.PDF
        first_job.status = ExportStatus.PENDING
        first_job.user_id = uuid.uuid4()

        newer_job = MagicMock()
        newer_job.status = ExportStatus.PROCESSING
        newer_job.file_url = "gs://bucket/newer.pdf"
        newer_job.processing_execution_id = uuid.uuid4()
        newer_job.processing_lease_expires_at = datetime.now(UTC) + timedelta(minutes=5)

        analysis = MagicMock()
        analysis.id = analysis_id
        analysis.org_id = org_id
        analysis.status = AnalysisStatus.COMPLETED
        analysis.report_data = valid_report_data(
            trust_mode="counsel",
            opinion_readiness={
                "export_ready": True,
                "jurisdictions_blocking_export": [],
            },
        )
        bind_report_data(
            analysis.report_data,
            analysis_id=analysis.id,
            org_id=analysis.org_id,
        )

        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = SimpleNamespace(
            status=ReviewStatus.APPROVED
        )
        decisions_result = MagicMock()
        decisions_result.scalars.return_value.all.return_value = []

        export_get_calls = 0

        def get_side_effect(model, _ident, **_kwargs):
            nonlocal export_get_calls
            if model.__name__ == "ExportJob":
                export_get_calls += 1
                return first_job if export_get_calls == 1 else newer_job
            if model.__name__ == "Analysis":
                return analysis
            if model.__name__ == "User":
                return SimpleNamespace(
                    id=first_job.user_id,
                    org_id=org_id,
                    role=UserRole.ATTORNEY,
                )
            if model.__name__ == "Organization":
                return SimpleNamespace(id=org_id, settings={})
            raise AssertionError(model.__name__)

        db = MagicMock()
        db.get.side_effect = get_side_effect
        bind_result = MagicMock()
        db.execute.side_effect = [bind_result, review_status_result, decisions_result]
        db.commit.return_value = None

        render_fake = MagicMock(return_value=Path("/tmp/stale.pdf"))
        logger = MagicMock()

        with (
            patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)),
            patch("pathlib.Path.stat") as mock_stat,
            patch("praviar_pipeline.models.report.FTOReport.model_validate") as mock_validate,
        ):
            mock_stat.return_value = MagicMock(st_size=42)
            mock_validate.return_value = MagicMock()
            result = self._run_export_job(
                job=first_job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=logger,
                render_export_fn=render_fake,
            )

        assert result["status"] == "retry_later"
        assert result["reason"] == "stale_execution_lost"
        assert newer_job.status == ExportStatus.PROCESSING
        assert newer_job.file_url != "/tmp/stale.pdf"
        logger.warning.assert_any_call(
            "export_job_stale_execution_lost_before_persistence",
            job_id=job_id,
            execution_id=str(first_job.processing_execution_id),
        )

    def test_stale_execution_exception_does_not_overwrite_newer_claim(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()

        first_job = MagicMock()
        first_job.analysis_id = analysis_id
        first_job.format = ExportFormat.PDF
        first_job.status = ExportStatus.PENDING

        claim_db = self._make_db(
            decisions=[],
            analysis_org_id=org_id,
            analysis_id=analysis_id,
            job=first_job,
        )

        newer_job = SimpleNamespace(
            status=ExportStatus.PROCESSING,
            error_message="newer worker owns this job",
            processing_execution_id=uuid.uuid4(),
            processing_lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        failure_db = MagicMock()
        failure_db.get.return_value = newer_job
        failure_db.commit.return_value = None

        render_fake = MagicMock(side_effect=RuntimeError("storage timeout"))

        with (
            patch.object(
                task_exports,
                "Session",
                side_effect=[
                    _FakeSessionContext(claim_db),
                    _FakeSessionContext(failure_db),
                ],
            ),
            patch("praviar_pipeline.models.report.FTOReport.model_validate") as mock_validate,
        ):
            mock_validate.return_value = MagicMock()
            result = self._run_export_job(
                job=first_job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=MagicMock(),
                render_export_fn=render_fake,
            )

        assert result["status"] == "failed"
        assert newer_job.status == ExportStatus.PROCESSING
        assert newer_job.error_message == "newer worker owns this job"
        failure_db.commit.assert_not_called()

    def test_worker_rolls_back_when_processing_claim_commit_fails(self):
        job_id = str(uuid.uuid4())
        job = MagicMock()
        job.status = ExportStatus.PENDING

        claim_db = MagicMock()
        claim_db.get.return_value = job
        claim_db.commit.side_effect = RuntimeError("commit failed")

        failure_job = SimpleNamespace(
            status=ExportStatus.PENDING,
            error_message="",
            processing_execution_id=None,
            processing_lease_expires_at=None,
        )
        failure_db = MagicMock()
        failure_db.get.return_value = failure_job
        failure_db.commit.return_value = None

        render_fake = MagicMock()

        with patch.object(
            task_exports,
            "Session",
            side_effect=[
                _FakeSessionContext(claim_db),
                _FakeSessionContext(failure_db),
            ],
        ):
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=MagicMock(),
                render_export_fn=render_fake,
            )

        assert result["status"] == "failed"
        claim_db.rollback.assert_called_once()
        failure_db.commit.assert_not_called()
        render_fake.assert_not_called()
        assert failure_job.status == ExportStatus.PENDING
        assert failure_job.processing_lease_expires_at is None

    def test_live_processing_lease_requests_transport_retry(self):
        job_id = str(uuid.uuid4())
        job = MagicMock()
        job.status = ExportStatus.PROCESSING
        job.processing_lease_expires_at = datetime.now(UTC) + timedelta(minutes=10)

        db = MagicMock()
        db.get.return_value = job
        render_fake = MagicMock()
        logger = MagicMock()

        with patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)):
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=logger,
                render_export_fn=render_fake,
            )

        assert result["status"] == "retry_later"
        assert result["job_id"] == job_id
        assert result["reason"] == "processing_lease_active"
        assert result["retry_after_seconds"] >= 1
        render_fake.assert_not_called()
        db.commit.assert_not_called()
        logger.info.assert_called_with(
            "export_job_duplicate_processing",
            job_id=job_id,
            processing_lease_expires_at=job.processing_lease_expires_at,
        )

    def test_expired_processing_lease_is_reclaimed_and_rendered(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()
        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF
        job.status = ExportStatus.PROCESSING
        expired_lease = datetime.now(UTC) - timedelta(minutes=5)
        job.processing_lease_expires_at = expired_lease

        db = self._make_db(decisions=[], analysis_org_id=org_id, analysis_id=analysis_id, job=job)
        render_fake = MagicMock(return_value=Path("/tmp/reclaimed.pdf"))
        logger = MagicMock()

        with (
            patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)),
            patch("pathlib.Path.stat") as mock_stat,
            patch("praviar_pipeline.models.report.FTOReport.model_validate") as mock_validate,
        ):
            mock_stat.return_value = MagicMock(st_size=42)
            mock_validate.return_value = MagicMock()
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=logger,
                render_export_fn=render_fake,
            )

        assert result["status"] == "completed"
        assert job.status == ExportStatus.COMPLETED
        assert job.processing_lease_expires_at is None
        render_fake.assert_called_once()
        assert db.commit.call_count == 2
        logger.warning.assert_any_call(
            "export_job_reclaiming_stale_processing",
            job_id=job_id,
            processing_lease_expires_at=expired_lease,
        )

    def test_retryable_failed_job_with_expired_lease_is_reclaimed(self):
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()
        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF
        job.status = ExportStatus.FAILED
        expired_lease = datetime.now(UTC) - timedelta(minutes=5)
        job.processing_lease_expires_at = expired_lease

        db = self._make_db(decisions=[], analysis_org_id=org_id, analysis_id=analysis_id, job=job)
        render_fake = MagicMock(return_value=Path("/tmp/reclaimed-failed.pdf"))
        logger = MagicMock()

        with (
            patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)),
            patch("pathlib.Path.stat") as mock_stat,
            patch("praviar_pipeline.models.report.FTOReport.model_validate") as mock_validate,
        ):
            mock_stat.return_value = MagicMock(st_size=42)
            mock_validate.return_value = MagicMock()
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=logger,
                render_export_fn=render_fake,
            )

        assert result["status"] == "completed"
        assert job.status == ExportStatus.COMPLETED
        assert job.retry_attempts == 0
        render_fake.assert_called_once()
        logger.warning.assert_any_call(
            "export_job_reclaiming_retryable_failure",
            job_id=job_id,
            processing_lease_expires_at=expired_lease,
        )

    def test_legacy_processing_job_without_lease_is_reclaimed_after_ttl(self):
        job = MagicMock()
        job.processing_lease_expires_at = None
        job.created_at = datetime.now(UTC) - timedelta(hours=2)

        assert task_exports._processing_export_is_reclaimable(
            job,
            now=datetime.now(UTC),
            lease_ttl_seconds=30 * 60,
        )

    def test_prod_export_without_gcs_bucket_fails_closed(self):
        file_path = Path("/tmp/missing-bucket.pdf")
        job = MagicMock()
        job.id = uuid.uuid4()
        job.format = ExportFormat.PDF
        analysis = MagicMock()
        analysis.id = uuid.uuid4()
        analysis.org_id = uuid.uuid4()
        settings = SimpleNamespace(
            app_env="prod", gcs_bucket_name="", gcp_project_id="praviar-prod"
        )

        with pytest.raises(RuntimeError, match="GCS_BUCKET_NAME is required"):
            task_exports._persist_export_artifact(
                file_path=file_path,
                job=job,
                analysis=analysis,
                settings=settings,
                export_format_enum=ExportFormat,
                execution_id=uuid.uuid4(),
                artifact_sha256="a" * 64,
            )

    def test_prod_export_blob_path_is_execution_scoped(self, tmp_path: Path):
        file_path = tmp_path / "report.pdf"
        file_path.write_bytes(b"pdf")

        job = MagicMock()
        job.id = uuid.uuid4()
        job.format = ExportFormat.PDF
        analysis = MagicMock()
        analysis.id = uuid.uuid4()
        analysis.org_id = uuid.uuid4()
        execution_id = uuid.uuid4()
        settings = SimpleNamespace(
            app_env="prod",
            gcs_bucket_name="praviar-exports",
            gcp_project_id="praviar-prod",
        )

        with patch("api.services.object_storage.ObjectStorage") as storage_cls:
            storage = storage_cls.return_value
            storage.upload_file.return_value = "gs://praviar-exports/export.pdf"
            result = task_exports._persist_export_artifact(
                file_path=file_path,
                job=job,
                analysis=analysis,
                settings=settings,
                export_format_enum=ExportFormat,
                execution_id=execution_id,
                artifact_sha256="b" * 64,
            )

        assert result == "gs://praviar-exports/export.pdf"
        blob_path = storage.upload_file.call_args.args[0]
        assert blob_path == (
            f"exports/{analysis.org_id}/{analysis.id}/{job.id}/{execution_id}/report.pdf"
        )
        assert storage.upload_file.call_args.kwargs["metadata"]["export_execution_id"] == str(
            execution_id
        )
        assert storage.upload_file.call_args.kwargs["metadata"]["artifact_sha256"] == "b" * 64

    def test_decisions_query_is_org_scoped(self):
        """Regression guard: the DB query must filter by ``org_id`` so an
        export never leaks decisions from a different tenant."""
        job_id = str(uuid.uuid4())
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()
        job = MagicMock()
        job.analysis_id = analysis_id
        job.format = ExportFormat.PDF

        db = self._make_db(decisions=[], analysis_org_id=org_id, analysis_id=analysis_id, job=job)

        render_fake = MagicMock()
        render_fake.return_value = Path("/tmp/x.pdf")

        with (
            patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)),
            patch("pathlib.Path.stat") as mock_stat,
            patch("praviar_pipeline.models.report.FTOReport.model_validate") as mock_validate,
        ):
            mock_stat.return_value = MagicMock(st_size=42)
            mock_validate.return_value = MagicMock()

            self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=MagicMock(),
                render_export_fn=render_fake,
            )

        # The compiled SELECT must reference both analysis_id and org_id.
        exec_calls = db.execute.call_args_list
        decision_selects = [
            str(call.args[0]).lower()
            for call in exec_calls
            if "analysis_reviewer_decisions" in str(call.args[0]).lower()
        ]
        assert decision_selects
        stmt_sql = decision_selects[-1]
        assert "analysis_id" in stmt_sql
        assert "org_id" in stmt_sql
        assert "membership_active" in stmt_sql
        assert "membership_deleted_at" in stmt_sql
        assert "membership_permission_denied_at" in stmt_sql

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (ExportStatus.COMPLETED, "already_completed"),
            (ExportStatus.PROCESSING, "retry_later"),
            (ExportStatus.FAILED, "already_failed"),
        ],
    )
    def test_duplicate_delivery_skips_non_pending_export_jobs(self, status, expected):
        job_id = str(uuid.uuid4())
        job = MagicMock()
        job.status = status
        job.file_url = "gs://bucket/export.pdf"
        job.file_size_bytes = 123
        job.manifest_hash = "d" * 64
        job.artifact_sha256 = "e" * 64
        if status == ExportStatus.PROCESSING:
            job.processing_lease_expires_at = datetime.now(UTC) + timedelta(minutes=5)
        if status == ExportStatus.FAILED:
            job.processing_lease_expires_at = None
        db = MagicMock()
        db.get.return_value = job
        render_fake = MagicMock()

        with patch.object(task_exports, "Session", return_value=_FakeSessionContext(db)):
            result = self._run_export_job(
                job=job,
                engine=MagicMock(),
                export_job_id=job_id,
                logger=MagicMock(),
                render_export_fn=render_fake,
            )

        assert result["status"] == expected
        if status == ExportStatus.COMPLETED:
            assert result["manifest_hash"] == "d" * 64
            assert result["artifact_sha256"] == "e" * 64
        render_fake.assert_not_called()
        db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Direct loader unit test
# ---------------------------------------------------------------------------


class TestLoadReviewerDecisions:
    def test_rows_serialize_to_dicts(self):
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()
        rows = [
            _decision_row(decision="accept", finding_ref="US0000001B2"),
            _decision_row(
                decision="edit",
                finding_ref="US0000002B2",
                note="x" * 300,
                edited_text="y" * 300,
            ),
        ]
        db = MagicMock()
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = rows
        db.execute.return_value = exec_result

        loaded = task_exports._load_reviewer_decision_rows(
            db, analysis_id=analysis_id, org_id=org_id
        )
        out = task_exports._serialize_reviewer_decisions(loaded)

        assert len(out) == 2
        assert out[0]["decision"] == "accept"
        assert out[0]["finding_ref"] == "US0000001B2"
        assert out[0]["reviewer_name"] == "Jane Attorney"
        # Payload preserves full note/edit text — Typst truncates at render time.
        assert len(out[1]["note"]) == 300
        assert len(out[1]["edited_text"]) == 300

    def test_missing_created_at_yields_empty_string(self):
        row = _decision_row()
        row.created_at = None
        db = MagicMock()
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = [row]
        db.execute.return_value = exec_result

        loaded = task_exports._load_reviewer_decision_rows(
            db, analysis_id=uuid.uuid4(), org_id=uuid.uuid4()
        )
        out = task_exports._serialize_reviewer_decisions(loaded)
        assert out[0]["created_at"] == ""


# ---------------------------------------------------------------------------
# render_pdf signature guard
# ---------------------------------------------------------------------------


def test_render_pdf_accepts_reviewer_decisions_kwarg():
    """If render_pdf's signature drops the kwarg, task_exports breaks
    silently. This test pins the signature so refactors fail loudly here."""
    import inspect

    from praviar_pipeline.rendering import pdf as pdf_mod  # type: ignore[import-not-found]

    sig = inspect.signature(pdf_mod.render_pdf)
    assert "reviewer_decisions" in sig.parameters


# ---------------------------------------------------------------------------
# No-decisions no-op safety
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", [ExportFormat.XLSX, ExportFormat.CSV, ExportFormat.JSON])
def test_non_pdf_formats_ignore_reviewer_decisions(tmp_path: Path, fmt):
    """The reviewer-decisions appendix is PDF-only in v1; other formats
    must not crash when the kwarg is provided."""
    report = MagicMock()
    report.report_id = "abcdef1234567890"
    report.model_dump.return_value = {"report_id": "abcdef1234567890"}

    decisions = [
        {
            "finding_type": "patent",
            "finding_ref": "US1234567B2",
            "decision": "accept",
            "note": "",
            "edited_text": "",
            "reviewer_name": "Jane",
            "reviewer_email": "jane@example.com",
            "created_at": "2026-04-15T09:30:00+00:00",
        }
    ]

    with (
        patch("praviar_pipeline.rendering.xlsx.render_xlsx", return_value=b"xlsx"),
        patch(
            "praviar_pipeline.rendering.csv.render_csv",
            return_value={"summary.csv": "col1\nval1"},
        ),
        patch.object(task_exports, "find_spec", return_value=None),
        patch.object(task_exports, "tempfile") as mock_tempfile,
    ):
        mock_tempfile.gettempdir.return_value = str(tmp_path)
        out = task_exports.render_export_artifact(
            report, fmt, ExportFormat, reviewer_decisions=decisions
        )

    assert out is not None
    assert out.exists()


class TestLocalExportArtifactCleanup:
    """Wave 47: the per-invocation export subdir must not leak after upload."""

    def test_cleanup_removes_file_and_unique_hex_directory(self, tmp_path: Path):
        export_dir = tmp_path / uuid.uuid4().hex
        export_dir.mkdir()
        artifact = export_dir / "fto_report.pdf"
        artifact.write_bytes(b"%PDF-1.7")

        task_exports._cleanup_local_export_artifact(artifact)

        assert not artifact.exists()
        # The unique container directory is removed too — no empty-inode leak.
        assert not export_dir.exists()

    def test_cleanup_preserves_non_hex_parent_directory(self, tmp_path: Path):
        # Defensive: only the disposable uuid4().hex container may be removed,
        # never a misconfigured shared export root.
        shared_root = tmp_path / "praviar-exports"
        shared_root.mkdir()
        artifact = shared_root / "fto_report.pdf"
        artifact.write_bytes(b"%PDF-1.7")

        task_exports._cleanup_local_export_artifact(artifact)

        assert not artifact.exists()
        assert shared_root.exists()

    def test_cleanup_is_noop_safe_when_file_already_gone(self, tmp_path: Path):
        export_dir = tmp_path / uuid.uuid4().hex
        export_dir.mkdir()
        artifact = export_dir / "fto_report.pdf"

        # Must not raise even though the file was never written.
        task_exports._cleanup_local_export_artifact(artifact)
        assert not export_dir.exists()
