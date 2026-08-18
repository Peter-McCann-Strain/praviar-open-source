"""Tests for /api/v1/analyses/{analysis_id}/review-status endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_analysis_mock, make_user, valid_report_data, valid_report_data_for_patents

from api.db.models import AnalysisReviewerDecision, AnalysisReviewStatus, ReviewStatus
from api.services.report_access import report_payload_fingerprint
from api.services.review_status import (
    invalidate_approved_review_status_if_export_blocked,
    update_analysis_review_status_impl,
)


def _make_review_status_mock(**kw) -> MagicMock:
    row = MagicMock(spec=AnalysisReviewStatus)
    row.id = kw.get("id", uuid.uuid4())
    row.analysis_id = kw.get("analysis_id", uuid.uuid4())
    row.org_id = kw.get("org_id", uuid.uuid4())
    row.status = kw.get("status", "under_review")
    row.note = kw.get("note", "Initial legal review in progress")
    row.reviewer_user_id = kw.get("reviewer_user_id", "clerk_test_user")
    row.reviewer_name = kw.get("reviewer_name", "Ada Lovelace")
    row.reviewer_email = kw.get("reviewer_email", "ada@example.com")
    row.reviewed_at = kw.get("reviewed_at", datetime.now(UTC))
    row.updated_at = kw.get("updated_at", datetime.now(UTC))
    return row


def _make_decision_mock(**kw) -> MagicMock:
    row = MagicMock(spec=AnalysisReviewerDecision)
    row.analysis_id = kw.get("analysis_id", uuid.uuid4())
    row.org_id = kw.get("org_id", uuid.uuid4())
    row.finding_type = kw.get("finding_type", "patent")
    row.finding_ref = kw.get("finding_ref", "US-12345-B2")
    row.report_fingerprint = kw.get("report_fingerprint", "")
    row.decision = kw.get("decision", "accept")
    row.reviewer_user_id = kw.get("reviewer_user_id", "clerk_reviewer_1")
    return row


class TestGetAnalysisReviewStatus:
    @pytest.mark.asyncio
    async def test_rejects_scientist_review_metadata_access(self, scientist_client):
        c, db = scientist_client

        resp = await c.get(f"/api/v1/analyses/{uuid.uuid4()}/review-status")

        assert resp.status_code == 403
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_default_pending_snapshot_without_status_row(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(
            id=analysis_id,
            flagged_for_review=False,
            report_data=valid_report_data_for_patents(
                [
                    {"patent_id": "US93000002A1"},
                    {"patent_id": "US93000003A1"},
                    {"patent_id": "US93000004A1"},
                ]
            ),
        )

        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = None
        decisions_result = MagicMock()
        decisions_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(
            side_effect=[analysis_result, review_status_result, decisions_result]
        )

        resp = await c.get(f"/api/v1/analyses/{analysis_id}/review-status")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["analysis_id"] == str(analysis_id)
        assert data["status"] == "pending"
        assert data["decision_counts"] == {"accept": 0, "reject": 0, "edit": 0}
        assert data["findings_total"] == 3
        assert data["findings_reviewed"] == 0
        assert data["completion_pct"] == 0.0
        assert data["note"] is None
        assert data["reviewer_name"] is None

    @pytest.mark.asyncio
    async def test_progress_metrics_ignore_unpublishable_report_payload(
        self,
        attorney_client,
    ):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(
            id=analysis_id,
            flagged_for_review=True,
            report_data={
                "patent_analyses": [
                    {"patent_id": "US93000002A1"},
                    {"patent_id": "US93000003A1"},
                ]
            },
        )
        review_status = _make_review_status_mock(
            analysis_id=analysis_id,
            status="under_review",
        )
        decisions = [
            _make_decision_mock(analysis_id=analysis_id, finding_ref="US93000002A1"),
            _make_decision_mock(analysis_id=analysis_id, finding_ref="US93000003A1"),
        ]

        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = review_status
        decisions_result = MagicMock()
        decisions_result.scalars.return_value.all.return_value = decisions
        db.execute = AsyncMock(
            side_effect=[analysis_result, review_status_result, decisions_result]
        )

        resp = await c.get(f"/api/v1/analyses/{analysis_id}/review-status")

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "under_review"
        assert data["decision_counts"] == {"accept": 0, "reject": 0, "edit": 0}
        assert data["findings_total"] == 0
        assert data["findings_reviewed"] == 0
        assert data["completion_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_returns_persisted_status_with_progress_metrics(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        report_data = valid_report_data_for_patents(
            [
                {"patent_id": "US93000002A1"},
                {"patent_id": "US93000003A1"},
                {"patent_id": "US93000004A1"},
                {"patent_id": "US93000005A1"},
            ]
        )
        analysis = make_analysis_mock(
            id=analysis_id,
            flagged_for_review=True,
            report_data=report_data,
        )
        report_fingerprint = report_payload_fingerprint(analysis.report_data)
        review_status = _make_review_status_mock(
            analysis_id=analysis_id,
            status="changes_requested",
            note="Please resolve the remaining claim gaps.",
        )
        decisions = [
            _make_decision_mock(
                analysis_id=analysis_id,
                finding_ref="US93000002A1",
                decision="accept",
                report_fingerprint=report_fingerprint,
            ),
            _make_decision_mock(
                analysis_id=analysis_id,
                finding_ref="US93000003A1",
                decision="edit",
                report_fingerprint=report_fingerprint,
            ),
            _make_decision_mock(
                analysis_id=analysis_id,
                finding_ref="US93000003A1",
                decision="reject",
                report_fingerprint=report_fingerprint,
            ),
        ]

        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = review_status
        decisions_result = MagicMock()
        decisions_result.scalars.return_value.all.return_value = decisions
        db.execute = AsyncMock(
            side_effect=[analysis_result, review_status_result, decisions_result]
        )

        resp = await c.get(f"/api/v1/analyses/{analysis_id}/review-status")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "changes_requested"
        assert data["note"] == "Please resolve the remaining claim gaps."
        assert data["decision_counts"] == {"accept": 1, "reject": 1, "edit": 1}
        assert data["findings_total"] == 4
        assert data["findings_reviewed"] == 2
        assert data["completion_pct"] == 50.0
        stmt_sql = str(db.execute.call_args_list[2].args[0]).lower()
        assert "join" in stmt_sql
        assert "users" in stmt_sql
        assert "role" in stmt_sql
        assert "users.membership_active is true" in stmt_sql
        assert "users.membership_deleted_at is null" in stmt_sql
        assert "users.membership_permission_denied_at is null" in stmt_sql

    @pytest.mark.asyncio
    async def test_progress_counts_review_required_claim_source_span_entries(
        self,
        attorney_client,
    ):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        report_data = valid_report_data_for_patents(
            [
                {"patent_id": "US93000002A1"},
                {"patent_id": "US93000003A1"},
            ]
        )
        report_data["claim_source_span_map"]["entries"].append(
            {
                "assertion_id": "assertion-needs-review-1",
                "patent_id": "US93000002A1",
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
        analysis = make_analysis_mock(
            id=analysis_id,
            flagged_for_review=True,
            report_data=report_data,
        )
        report_fingerprint = report_payload_fingerprint(analysis.report_data)
        review_status = _make_review_status_mock(
            analysis_id=analysis_id,
            status="under_review",
        )
        decisions = [
            _make_decision_mock(
                analysis_id=analysis_id,
                finding_ref="US93000002A1",
                report_fingerprint=report_fingerprint,
            ),
            _make_decision_mock(
                analysis_id=analysis_id,
                finding_type="claim_element",
                finding_ref="assertion-needs-review-1",
                report_fingerprint=report_fingerprint,
            ),
        ]

        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = review_status
        decisions_result = MagicMock()
        decisions_result.scalars.return_value.all.return_value = decisions
        db.execute = AsyncMock(
            side_effect=[analysis_result, review_status_result, decisions_result]
        )

        resp = await c.get(f"/api/v1/analyses/{analysis_id}/review-status")

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["findings_total"] == 3
        assert data["findings_reviewed"] == 2
        assert data["completion_pct"] == 66.6667

    @pytest.mark.asyncio
    async def test_progress_ignores_decisions_for_unknown_findings(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(
            id=analysis_id,
            flagged_for_review=True,
            report_data=valid_report_data_for_patents(
                [
                    {"patent_id": "US93000002A1"},
                    {"patent_id": "US93000003A1"},
                ]
            ),
        )
        review_status = _make_review_status_mock(
            analysis_id=analysis_id,
            status="under_review",
        )
        decisions = [
            _make_decision_mock(analysis_id=analysis_id, finding_ref="BOGUS-1"),
            _make_decision_mock(analysis_id=analysis_id, finding_ref="BOGUS-2"),
        ]

        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = review_status
        decisions_result = MagicMock()
        decisions_result.scalars.return_value.all.return_value = decisions
        db.execute = AsyncMock(
            side_effect=[analysis_result, review_status_result, decisions_result]
        )

        resp = await c.get(f"/api/v1/analyses/{analysis_id}/review-status")

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["decision_counts"] == {"accept": 0, "reject": 0, "edit": 0}
        assert data["findings_total"] == 2
        assert data["findings_reviewed"] == 0
        assert data["completion_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_approved_status_downgrades_when_current_findings_lack_current_decisions(
        self,
        attorney_client,
    ):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        report_data = valid_report_data_for_patents(
            [{"patent_id": "US91000008A1", "risk_level": "high"}],
            trust_mode="counsel",
            opinion_readiness={
                "export_ready": True,
                "jurisdictions_blocking_export": [],
            },
        )
        analysis = make_analysis_mock(
            id=analysis_id,
            flagged_for_review=False,
            report_data=report_data,
        )
        review_status = _make_review_status_mock(
            analysis_id=analysis_id,
            status=ReviewStatus.APPROVED,
            note="Previously approved.",
        )
        decisions = [
            _make_decision_mock(
                analysis_id=analysis_id,
                finding_ref="US91000008A1",
                report_fingerprint="old-report-fingerprint",
            ),
            _make_decision_mock(
                analysis_id=analysis_id,
                finding_ref="US91000009A1",
                report_fingerprint=report_payload_fingerprint(report_data),
            ),
        ]

        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = review_status
        decisions_result = MagicMock()
        decisions_result.scalars.return_value.all.return_value = decisions
        db.execute = AsyncMock(
            side_effect=[analysis_result, review_status_result, decisions_result]
        )

        resp = await c.get(f"/api/v1/analyses/{analysis_id}/review-status")

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "changes_requested"
        assert data["decision_counts"] == {"accept": 0, "reject": 0, "edit": 0}
        assert data["findings_total"] == 1
        assert data["findings_reviewed"] == 0


class TestUpdateAnalysisReviewStatus:
    @pytest.mark.asyncio
    async def test_update_locks_analysis_before_review_status_row(self):
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()
        analysis = make_analysis_mock(id=analysis_id, org_id=org_id)
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = None
        decisions_result = MagicMock()
        decisions_result.scalars.return_value.all.return_value = []
        db = AsyncMock()
        db.add = MagicMock()
        db.execute = AsyncMock(
            side_effect=[
                analysis_result,
                review_status_result,
                decisions_result,
            ]
        )
        user = make_user(org_id=org_id)

        with patch(
            "api.services.review_status.write_audit_log",
            new=AsyncMock(),
        ):
            await update_analysis_review_status_impl(
                db,
                analysis_id=analysis_id,
                org_id=org_id,
                user=user,
                body=MagicMock(status="under_review", note="Starting review."),
            )

        statements = [str(call.args[0]) for call in db.execute.await_args_list[:2]]
        assert "FROM analyses" in statements[0]
        assert "FOR UPDATE" in statements[0]
        assert "analysis_review_statuses" in statements[1]
        assert "FOR UPDATE" in statements[1]

    @pytest.mark.asyncio
    async def test_scientist_cannot_set_review_status(self, scientist_client):
        """review-status requires reviewer_decision.create — scientists are excluded."""
        c, _db = scientist_client
        analysis_id = uuid.uuid4()

        resp = await c.put(
            f"/api/v1/analyses/{analysis_id}/review-status",
            json={"status": "under_review", "note": "Escalating for counsel review."},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_attorney_can_mark_under_review(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(id=analysis_id, flagged_for_review=False)

        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = None
        decisions_result = MagicMock()
        decisions_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(
            side_effect=[analysis_result, review_status_result, decisions_result]
        )

        resp = await c.put(
            f"/api/v1/analyses/{analysis_id}/review-status",
            json={"status": "under_review", "note": "Escalating for counsel review."},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "under_review"
        assert data["note"] == "Escalating for counsel review."
        assert analysis.flagged_for_review is True
        added_types = {type(call.args[0]).__name__ for call in db.add.call_args_list}
        assert "AnalysisReviewStatus" in added_types
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_status_update_rolls_back_when_audit_fails(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(id=analysis_id, flagged_for_review=False)

        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(side_effect=[analysis_result, review_status_result])

        with (
            patch(
                "api.services.review_status.write_audit_log",
                new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
            ) as audit_log,
            pytest.raises(RuntimeError, match="audit unavailable"),
        ):
            await c.put(
                f"/api/v1/analyses/{analysis_id}/review-status",
                json={"status": "under_review", "note": "Escalating for counsel review."},
            )

        assert audit_log.await_args is not None
        assert audit_log.await_args.kwargs["fail_closed"] is True
        db.commit.assert_not_awaited()
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_attorney_can_approve_and_clear_flag(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(
            id=analysis_id,
            flagged_for_review=True,
            report_data=valid_report_data(
                trust_mode="counsel",
                opinion_readiness={
                    "export_ready": True,
                    "jurisdictions_blocking_export": [],
                },
            ),
        )
        existing_status = _make_review_status_mock(analysis_id=analysis_id, status="under_review")

        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = existing_status
        approval_decisions_result = MagicMock()
        approval_decisions_result.scalars.return_value.all.return_value = []
        no_open_reassessments_result = MagicMock()
        no_open_reassessments_result.scalar_one_or_none.return_value = None
        decisions_result = MagicMock()
        decisions_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(
            side_effect=[
                analysis_result,
                review_status_result,
                approval_decisions_result,
                no_open_reassessments_result,
                decisions_result,
            ]
        )

        resp = await c.put(
            f"/api/v1/analyses/{analysis_id}/review-status",
            json={"status": "approved", "note": "Ready for export."},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "approved"
        assert data["note"] == "Ready for export."
        assert analysis.flagged_for_review is False
        assert existing_status.status == "approved"
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_attorney_cannot_approve_until_required_findings_are_reviewed(
        self,
        attorney_client,
    ):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(
            id=analysis_id,
            flagged_for_review=True,
            report_data=valid_report_data_for_patents(
                [
                    {"patent_id": "US91000017A1", "risk_level": "high"},
                    {"patent_id": "US91000018A1", "risk_level": "medium"},
                ],
                trust_mode="counsel",
                opinion_readiness={
                    "export_ready": True,
                    "jurisdictions_blocking_export": [],
                },
            ),
        )
        report_fingerprint = report_payload_fingerprint(analysis.report_data)
        existing_status = _make_review_status_mock(analysis_id=analysis_id, status="under_review")

        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = existing_status
        approval_decisions_result = MagicMock()
        approval_decisions_result.scalars.return_value.all.return_value = [
            _make_decision_mock(
                analysis_id=analysis_id,
                finding_ref="US91000017A1",
                reviewer_user_id="clerk_reviewer_1",
                report_fingerprint=report_fingerprint,
            ),
        ]
        db.execute = AsyncMock(
            side_effect=[analysis_result, review_status_result, approval_decisions_result]
        )

        resp = await c.put(
            f"/api/v1/analyses/{analysis_id}/review-status",
            json={"status": "approved", "note": "Ready for export."},
        )

        assert resp.status_code == 409, resp.text
        assert "requires dual review" in resp.json()["detail"]
        assert "US91000018A1 has no reviewer decision" in resp.json()["detail"]
        assert existing_status.status == "under_review"
        db.flush.assert_not_awaited()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_attorney_cannot_approve_until_claim_source_span_is_reviewed(
        self,
        attorney_client,
    ):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
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
        analysis = make_analysis_mock(
            id=analysis_id,
            flagged_for_review=True,
            report_data=report_data,
        )
        existing_status = _make_review_status_mock(analysis_id=analysis_id, status="under_review")

        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = existing_status
        approval_decisions_result = MagicMock()
        approval_decisions_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(
            side_effect=[analysis_result, review_status_result, approval_decisions_result]
        )

        resp = await c.put(
            f"/api/v1/analyses/{analysis_id}/review-status",
            json={"status": "approved", "note": "Ready for export."},
        )

        assert resp.status_code == 409, resp.text
        assert "assertion-needs-review-1 has no reviewer decision" in resp.json()["detail"]
        assert existing_status.status == "under_review"
        db.flush.assert_not_awaited()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_attorney_can_approve_after_required_findings_are_reviewed(
        self,
        attorney_client,
    ):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        report_data = valid_report_data_for_patents(
            [
                {"patent_id": "US91000017A1", "risk_level": "high"},
                {"patent_id": "US91000018A1", "risk_level": "medium"},
            ],
            trust_mode="counsel",
            opinion_readiness={
                "export_ready": True,
                "jurisdictions_blocking_export": [],
            },
        )
        analysis = make_analysis_mock(
            id=analysis_id,
            flagged_for_review=True,
            report_data=report_data,
        )
        report_fingerprint = report_payload_fingerprint(analysis.report_data)
        existing_status = _make_review_status_mock(analysis_id=analysis_id, status="under_review")
        approval_decisions = [
            _make_decision_mock(
                analysis_id=analysis_id,
                finding_ref="US91000017A1",
                reviewer_user_id="clerk_reviewer_1",
                report_fingerprint=report_fingerprint,
            ),
            _make_decision_mock(
                analysis_id=analysis_id,
                finding_ref="US91000017A1",
                reviewer_user_id="clerk_reviewer_2",
                report_fingerprint=report_fingerprint,
            ),
            _make_decision_mock(
                analysis_id=analysis_id,
                finding_ref="US91000018A1",
                reviewer_user_id="clerk_reviewer_1",
                report_fingerprint=report_fingerprint,
            ),
        ]

        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = existing_status
        approval_decisions_result = MagicMock()
        approval_decisions_result.scalars.return_value.all.return_value = approval_decisions
        no_open_reassessments_result = MagicMock()
        no_open_reassessments_result.scalar_one_or_none.return_value = None
        decisions_result = MagicMock()
        decisions_result.scalars.return_value.all.return_value = approval_decisions
        db.execute = AsyncMock(
            side_effect=[
                analysis_result,
                review_status_result,
                approval_decisions_result,
                no_open_reassessments_result,
                decisions_result,
            ]
        )

        resp = await c.put(
            f"/api/v1/analyses/{analysis_id}/review-status",
            json={"status": "approved", "note": "Ready for export."},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "approved"
        assert resp.json()["findings_reviewed"] == 2
        assert existing_status.status == "approved"
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_scientist_cannot_approve(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(id=analysis_id, flagged_for_review=True)

        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        db.execute = AsyncMock(side_effect=[analysis_result])

        resp = await c.put(
            f"/api/v1/analyses/{analysis_id}/review-status",
            json={"status": "approved", "note": "Ready for export."},
        )
        assert resp.status_code == 403, resp.text


class TestInvalidateApprovedReviewStatus:
    @pytest.mark.asyncio
    async def test_downgrades_approval_when_report_payload_is_unpublishable(self):
        db = AsyncMock()
        analysis_id = uuid.uuid4()
        org_id = uuid.uuid4()
        report_data = valid_report_data()
        report_data["verification_summary"]["claims_incorrect"] = 1
        analysis = make_analysis_mock(
            id=analysis_id,
            org_id=org_id,
            flagged_for_review=False,
            report_data=report_data,
        )
        review_status = _make_review_status_mock(
            analysis_id=analysis_id,
            org_id=org_id,
            status=ReviewStatus.APPROVED,
            note="Ready for export.",
        )

        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = review_status
        db.execute = AsyncMock(side_effect=[analysis_result, review_status_result])

        blockers = await invalidate_approved_review_status_if_export_blocked(
            db,
            analysis_id=analysis_id,
            org_id=org_id,
            user=make_user(org_id=org_id),
        )

        assert blockers == ["Analysis report payload is not publishable."]
        assert review_status.status == ReviewStatus.CHANGES_REQUESTED
        assert analysis.flagged_for_review is True
