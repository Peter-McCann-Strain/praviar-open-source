"""Tests for /api/v1/analyses/{analysis_id}/review-handoff."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_analysis_mock, valid_report_data

from api.db.models import AnalysisReviewStatus


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


class TestAnalysisReviewHandoff:
    @pytest.mark.asyncio
    async def test_creates_targeted_comment_and_escalates_pending_review(self, scientist_client):
        client, db = scientist_client
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

        response = await client.post(
            f"/api/v1/analyses/{analysis_id}/review-handoff",
            json={
                "body": "Please review the governed evidence for this patent.",
                "review_note": "Escalating this patent for counsel review.",
                "target_type": "patent",
                "target_id": "US92000001A1",
            },
        )

        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["target_type"] == "patent"
        assert payload["target_id"] == "US92000001A1"
        assert payload["escalated_to_review"] is True
        assert payload["review_status"]["status"] == "under_review"
        assert payload["review_status"]["note"] == "Escalating this patent for counsel review."
        assert analysis.flagged_for_review is True

        added_types = {type(call.args[0]).__name__ for call in db.add.call_args_list}
        assert "Comment" in added_types
        assert "AnalysisReviewStatus" in added_types
        assert "AuditLog" in added_types
        created_comment = next(
            call.args[0]
            for call in db.add.call_args_list
            if type(call.args[0]).__name__ == "Comment"
        )
        assert created_comment.analysis_id == analysis_id
        assert created_comment.target_type == "patent"
        assert created_comment.target_id == "US92000001A1"
        assert created_comment.body == "Please review the governed evidence for this patent."
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handoff_rolls_back_when_audit_fails(self, scientist_client):
        client, db = scientist_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(
            id=analysis_id,
            flagged_for_review=False,
            report_data=valid_report_data(
                trust_mode="counsel",
                opinion_readiness={
                    "export_ready": True,
                    "jurisdictions_blocking_export": [],
                },
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

        with (
            patch(
                "api.services.review_status.write_audit_log",
                new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
            ) as audit_log,
            pytest.raises(RuntimeError, match="audit unavailable"),
        ):
            await client.post(
                f"/api/v1/analyses/{analysis_id}/review-handoff",
                json={
                    "body": "Please review the governed evidence for this patent.",
                    "review_note": "Escalating this patent for counsel review.",
                    "target_type": "patent",
                    "target_id": "US92000001A1",
                },
            )

        assert audit_log.await_args is not None
        assert audit_log.await_args.kwargs["fail_closed"] is True
        db.commit.assert_not_awaited()
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_preserves_non_pending_review_status_without_downgrading(self, scientist_client):
        client, db = scientist_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(
            id=analysis_id,
            flagged_for_review=False,
            report_data=valid_report_data(
                trust_mode="counsel",
                opinion_readiness={
                    "export_ready": True,
                    "jurisdictions_blocking_export": [],
                },
            ),
        )
        review_status = _make_review_status_mock(
            analysis_id=analysis_id,
            status="approved",
            note="Approved for export.",
        )

        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        review_status_result = MagicMock()
        review_status_result.scalar_one_or_none.return_value = review_status
        decisions_result = MagicMock()
        decisions_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(
            side_effect=[analysis_result, review_status_result, decisions_result]
        )

        response = await client.post(
            f"/api/v1/analyses/{analysis_id}/review-handoff",
            json={
                "body": "Opening a discussion thread for an already approved report.",
                "target_type": "analysis",
                "target_id": str(analysis_id),
            },
        )

        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["escalated_to_review"] is False
        assert payload["review_status"]["status"] == "approved"
        assert payload["review_status"]["note"] == "Approved for export."
        assert analysis.flagged_for_review is False

        added_types = [type(call.args[0]).__name__ for call in db.add.call_args_list]
        assert "Comment" in added_types
        assert "AnalysisReviewStatus" not in added_types

    @pytest.mark.asyncio
    async def test_cross_org_handoff_returns_404(self, scientist_client):
        client, db = scientist_client

        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=analysis_result)

        response = await client.post(
            f"/api/v1/analyses/{uuid.uuid4()}/review-handoff",
            json={
                "body": "Cross-org handoff attempt.",
                "target_type": "analysis",
                "target_id": "analysis-404",
            },
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Analysis not found"

    @pytest.mark.asyncio
    async def test_client_role_cannot_create_review_handoff(self, client_role_client):
        client, _db = client_role_client

        response = await client.post(
            f"/api/v1/analyses/{uuid.uuid4()}/review-handoff",
            json={
                "body": "Client attempted review handoff.",
                "target_type": "analysis",
                "target_id": "analysis-client",
            },
        )

        assert response.status_code == 403
