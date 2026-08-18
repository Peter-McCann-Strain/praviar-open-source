"""Tests for /api/v1/feedback endpoint."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from conftest import make_analysis_mock, valid_report_data, valid_report_data_for_patents

from api.db.models import AnalysisStatus

_QUERY_PLAN_SHA256 = "a" * 64


def relevance_feedback_report(patent_id: str = "US93000001A1") -> dict:
    report = valid_report_data_for_patents([{"patent_id": patent_id}])
    report["audit_trail"]["query_plan"] = {
        "plan_sha256": _QUERY_PLAN_SHA256,
    }
    report["audit_trail"]["search_funnel"] = [
        {
            "patent_id": patent_id,
            "sources_found_in": ["pubchem_sdq"],
            "included_in_triage": True,
        }
    ]
    return report


def mock_publishable_analysis(
    db,
    *,
    analysis_id: uuid.UUID | None = None,
    report_data: dict | None = None,
):
    analysis = make_analysis_mock(
        id=analysis_id or uuid.uuid4(),
        status=AnalysisStatus.COMPLETED,
        report_data=report_data or valid_report_data(),
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = analysis
    db.execute.return_value = result
    return analysis


# ---------------------------------------------------------------------------
# POST /api/v1/feedback
# ---------------------------------------------------------------------------


class TestSubmitFeedback:
    @pytest.mark.asyncio
    async def test_submit_as_attorney(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        mock_publishable_analysis(db, analysis_id=analysis_id)

        resp = await c.post(
            "/api/v1/feedback",
            json={
                "analysis_id": str(analysis_id),
                "overall_accuracy": 0.85,
                "risk_level_correct": True,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        # Two adds: the feedback record plus its fail-closed audit-log row.
        assert db.add.call_count == 2
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_submit_with_corrections(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        report_data = valid_report_data_for_patents([{"patent_id": "US93000001A1"}])
        mock_publishable_analysis(
            db,
            analysis_id=analysis_id,
            report_data=report_data,
        )

        resp = await c.post(
            "/api/v1/feedback",
            json={
                "analysis_id": str(analysis_id),
                "overall_accuracy": 0.6,
                "risk_level_correct": False,
                "corrected_risk": "high",
                "corrections": [
                    {
                        "patent_id": "US93000001A1",
                        "field": "risk_level",
                        "original_value": "low",
                        "corrected_value": "high",
                        "notes": "Missed key claim overlap",
                    }
                ],
            },
        )
        assert resp.status_code == 201
        record = db.add.call_args_list[0].args[0]
        assert record.corrections == [
            {
                "patent_id": "US93000001A1",
                "field": "risk_level",
                "original_value": "low",
                "corrected_value": "high",
                "notes": "Missed key claim overlap",
            }
        ]

    @pytest.mark.asyncio
    async def test_rejects_misnamed_correction_fields_instead_of_losing_rationale(
        self, attorney_client
    ):
        c, _db = attorney_client
        resp = await c.post(
            "/api/v1/feedback",
            json={
                "analysis_id": str(uuid.uuid4()),
                "overall_accuracy": 0.6,
                "risk_level_correct": False,
                "corrected_risk": "high",
                "corrections": [
                    {
                        "patent_id": "US93000001A1",
                        "field": "risk_level",
                        "original": "low",
                        "corrected": "high",
                        "reason": "This must not be silently discarded",
                    }
                ],
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_as_admin(self, admin_client):
        c, db = admin_client
        mock_publishable_analysis(db)
        resp = await c.post(
            "/api/v1/feedback",
            json={
                "analysis_id": str(uuid.uuid4()),
                "overall_accuracy": 0.9,
            },
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_submit_cross_org_rejected(self, attorney_client):
        """Attempting to give feedback on another org's analysis returns 404."""
        c, db = attorney_client
        # Default mock returns None for scalar_one_or_none (no matching analysis)
        resp = await c.post(
            "/api/v1/feedback",
            json={
                "analysis_id": str(uuid.uuid4()),
                "overall_accuracy": 0.8,
            },
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_submit_rejects_unavailable_report_without_persisting(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(
            id=analysis_id,
            status=AnalysisStatus.RUNNING,
            report_data=None,
        )
        result = MagicMock()
        result.scalar_one_or_none.return_value = analysis
        db.execute.return_value = result

        resp = await c.post(
            "/api/v1/feedback",
            json={
                "analysis_id": str(analysis_id),
                "overall_accuracy": 0.8,
            },
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Feedback target report not available"
        db.add.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("risk_level_correct", "corrected_risk"),
        [
            (False, None),
            (False, "critical"),
            (True, "high"),
        ],
    )
    async def test_submit_rejects_contradictory_risk_correction(
        self,
        attorney_client,
        risk_level_correct,
        corrected_risk,
    ):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        mock_publishable_analysis(db, analysis_id=analysis_id)

        resp = await c.post(
            "/api/v1/feedback",
            json={
                "analysis_id": str(analysis_id),
                "overall_accuracy": 0.8,
                "risk_level_correct": risk_level_correct,
                "corrected_risk": corrected_risk,
            },
        )

        assert resp.status_code == 422
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_rejects_correction_for_patent_outside_report(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        mock_publishable_analysis(
            db,
            analysis_id=analysis_id,
            report_data=valid_report_data_for_patents([{"patent_id": "US93000001A1"}]),
        )

        resp = await c.post(
            "/api/v1/feedback",
            json={
                "analysis_id": str(analysis_id),
                "overall_accuracy": 0.8,
                "corrections": [
                    {
                        "patent_id": "US99999999B2",
                        "field": "risk_level",
                        "original_value": "low",
                        "corrected_value": "high",
                    }
                ],
            },
        )

        assert resp.status_code == 422
        assert "outside the governed report" in resp.json()["detail"]
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_forbidden_for_scientist(self, scientist_client):
        c, _db = scientist_client
        resp = await c.post(
            "/api/v1/feedback",
            json={
                "analysis_id": str(uuid.uuid4()),
                "overall_accuracy": 0.5,
            },
        )
        assert resp.status_code == 403
        assert "Only attorneys" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_submit_forbidden_for_client(self, client_role_client):
        c, _db = client_role_client
        resp = await c.post(
            "/api/v1/feedback",
            json={
                "analysis_id": str(uuid.uuid4()),
                "overall_accuracy": 0.5,
            },
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_submit_accuracy_out_of_range(self, attorney_client):
        c, _db = attorney_client
        resp = await c.post(
            "/api/v1/feedback",
            json={
                "analysis_id": str(uuid.uuid4()),
                "overall_accuracy": 1.5,  # > 1.0
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_accuracy_negative(self, attorney_client):
        c, _db = attorney_client
        resp = await c.post(
            "/api/v1/feedback",
            json={
                "analysis_id": str(uuid.uuid4()),
                "overall_accuracy": -0.1,  # < 0.0
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_missing_required_fields(self, attorney_client):
        c, _db = attorney_client
        resp = await c.post(
            "/api/v1/feedback",
            json={},
        )
        assert resp.status_code == 422


class TestSearchRelevanceFeedback:
    @pytest.mark.asyncio
    async def test_attorney_can_submit_plan_bound_relevance_label(self, attorney_client):
        from unittest.mock import AsyncMock

        c, db = attorney_client
        analysis_id = uuid.uuid4()
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = make_analysis_mock(
            id=analysis_id,
            report_data=relevance_feedback_report(),
        )
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(side_effect=[analysis_result, existing_result])

        response = await c.post(
            f"/api/v1/analyses/{analysis_id}/search-relevance-feedback",
            json={
                "patent_id": "US93000001A1",
                "relevance": "relevant",
                "reason_codes": ["direct_claim_match", "structure_match"],
                "note": "Claim 1 maps directly to the launch compound.",
                "suggested_queries": ["assignee:Fictional Legacy aspirin formulation"],
                "expected_query_plan_sha256": _QUERY_PLAN_SHA256,
            },
        )

        assert response.status_code == 201, response.text
        added = [call.args[0] for call in db.add.call_args_list]
        relevance_row = next(
            row for row in added if type(row).__name__ == "AnalysisSearchRelevanceFeedback"
        )
        assert relevance_row.patent_id == "US93000001A1"
        assert relevance_row.query_plan_sha256 == _QUERY_PLAN_SHA256
        assert relevance_row.reason_codes == ["direct_claim_match", "structure_match"]
        assert relevance_row.suggested_queries == ["assignee:Fictional Legacy aspirin formulation"]
        audit_row = next(row for row in added if type(row).__name__ == "AuditLog")
        assert audit_row.action == "search_relevance_feedback.create"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_relevance_feedback_rejects_stale_query_plan(self, attorney_client):
        from unittest.mock import AsyncMock

        c, db = attorney_client
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = make_analysis_mock(
            report_data=relevance_feedback_report(),
        )
        db.execute = AsyncMock(return_value=analysis_result)

        response = await c.post(
            f"/api/v1/analyses/{uuid.uuid4()}/search-relevance-feedback",
            json={
                "patent_id": "US93000001A1",
                "relevance": "not_relevant",
                "reason_codes": ["irrelevant_compound"],
                "expected_query_plan_sha256": "b" * 64,
            },
        )

        assert response.status_code == 409
        assert "query plan changed" in response.json()["detail"]
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_relevance_feedback_rejects_patent_outside_search_funnel(
        self,
        attorney_client,
    ):
        from unittest.mock import AsyncMock

        c, db = attorney_client
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = make_analysis_mock(
            report_data=relevance_feedback_report(),
        )
        db.execute = AsyncMock(return_value=analysis_result)

        response = await c.post(
            f"/api/v1/analyses/{uuid.uuid4()}/search-relevance-feedback",
            json={
                "patent_id": "US99999999B2",
                "relevance": "not_relevant",
                "expected_query_plan_sha256": _QUERY_PLAN_SHA256,
            },
        )

        assert response.status_code == 422
        assert "governed search funnel" in response.json()["detail"]
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_scientist_cannot_submit_search_relevance_feedback(
        self,
        scientist_client,
    ):
        c, db = scientist_client
        response = await c.post(
            f"/api/v1/analyses/{uuid.uuid4()}/search-relevance-feedback",
            json={
                "patent_id": "US93000001A1",
                "relevance": "uncertain",
                "expected_query_plan_sha256": _QUERY_PLAN_SHA256,
            },
        )

        assert response.status_code == 403
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_attorney_can_list_case_scoped_relevance_labels(self, attorney_client):
        from unittest.mock import AsyncMock

        c, db = attorney_client
        analysis_id = uuid.uuid4()
        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = make_analysis_mock(id=analysis_id)

        timestamp = datetime.now(UTC)
        row = MagicMock(
            id=uuid.uuid4(),
            analysis_id=analysis_id,
            patent_id="US93000001A1",
            relevance="relevant",
            reason_codes=["direct_claim_match"],
            note="Reviewed against claim 1.",
            suggested_queries=[],
            query_plan_sha256=_QUERY_PLAN_SHA256,
            report_fingerprint="c" * 64,
            reviewer_name="Patent Counsel",
            reviewer_email="counsel@example.com",
            created_at=timestamp,
            updated_at=timestamp,
        )
        feedback_result = MagicMock()
        feedback_result.scalars.return_value.all.return_value = [row]
        db.execute = AsyncMock(side_effect=[analysis_result, feedback_result])

        response = await c.get(f"/api/v1/analyses/{analysis_id}/search-relevance-feedback")

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["counts"] == {
            "relevant": 1,
            "not_relevant": 0,
            "uncertain": 0,
        }
        assert payload["items"][0]["patent_id"] == "US93000001A1"
        assert payload["items"][0]["query_plan_sha256"] == _QUERY_PLAN_SHA256


# ---------------------------------------------------------------------------
# Service-layer unit tests for ``api.services.feedback``
# ---------------------------------------------------------------------------


class TestFeedbackService:
    @pytest.mark.asyncio
    async def test_assert_analysis_in_org_raises_when_missing(self):
        from unittest.mock import AsyncMock, MagicMock

        from api.errors import APIError
        from api.services.feedback import assert_analysis_in_org

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(APIError) as exc:
            await assert_analysis_in_org(
                db,
                analysis_id=uuid.uuid4(),
                org_id=uuid.uuid4(),
            )
        assert exc.value.status == 404

    @pytest.mark.asyncio
    async def test_submit_attorney_feedback_persists_and_commits(self):
        from unittest.mock import AsyncMock, MagicMock

        from api.schemas.feedback import SubmitFeedbackRequest
        from api.services.feedback import submit_attorney_feedback

        analysis_id = uuid.uuid4()
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = make_analysis_mock(
            id=analysis_id,
            org_id=org_id,
            status=AnalysisStatus.COMPLETED,
            report_data=valid_report_data(),
        )
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)
        added: list[object] = []
        db.add = MagicMock(side_effect=lambda obj: added.append(obj))
        db.commit = AsyncMock()

        body = SubmitFeedbackRequest(
            analysis_id=analysis_id,
            overall_accuracy=0.8,
            risk_level_correct=True,
            corrected_risk=None,
            corrections=[],
        )
        record = await submit_attorney_feedback(
            db,
            user_id=user_id,
            org_id=org_id,
            body=body,
        )
        assert record is not None
        assert added and added[0] is record
        db.commit.assert_awaited_once()

        # Attorney corrections override the system's risk assessment, so the
        # mutation must leave an audit-log row alongside the feedback record.
        from api.db.models import AuditLog

        audit_rows = [obj for obj in added if isinstance(obj, AuditLog)]
        assert len(audit_rows) == 1
        assert audit_rows[0].action == "attorney_feedback.submitted"
        assert audit_rows[0].org_id == org_id
        assert audit_rows[0].user_id == user_id
        assert audit_rows[0].analysis_id == analysis_id
