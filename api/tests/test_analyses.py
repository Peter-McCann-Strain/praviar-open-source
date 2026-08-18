"""Tests for /api/v1/analyses endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_analysis_mock, make_paginated_result

from api.db.models import AnalysisStatus
from api.schemas.analyses import detect_submitted_input_type

ANALYSIS_LAUNCH_HEADERS = {"Idempotency-Key": "analysis-launch-route-test-123"}


def _launch_payload(compound_input: str, **overrides) -> dict:
    return {
        "compound_input": compound_input,
        "input_type": detect_submitted_input_type(compound_input),
        "submitted_identity_confirmed": True,
        "submitted_identity_value": compound_input,
        **overrides,
    }


@pytest.fixture(autouse=True)
def _mock_empty_launch_receipt():
    with (
        patch("api.services.analyses._lock_analysis_launch_org", new=AsyncMock()),
        patch(
            "api.services.analyses._get_analysis_by_launch_key",
            new=AsyncMock(return_value=None),
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# POST /api/v1/analyses — create
# ---------------------------------------------------------------------------


class TestCreateAnalysis:
    """POST /api/v1/analyses"""

    @pytest.mark.asyncio
    async def test_create_success_as_scientist(self, scientist_client):
        c, db = scientist_client

        with (
            patch(
                "api.services.analyses.check_usage_limit",
                new=AsyncMock(return_value=(True, 1, 10)),
            ),
            patch("api.workers.tasks.run_fto_pipeline") as mock_task,
        ):
            mock_task.delay = MagicMock()
            resp = await c.post(
                "/api/v1/analyses",
                json=_launch_payload("aspirin"),
                headers=ANALYSIS_LAUNCH_HEADERS,
            )

        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["compound_input"] == "aspirin"
        assert data["input_type"] == "name"
        assert data["submitted_identity_confirmed"] is True
        assert data["submitted_identity_value"] == "aspirin"
        assert data["status"] == "pending"
        assert resp.headers["Idempotency-Replayed"] == "false"
        assert db.add.call_count == 2  # Analysis + AuditLog
        assert db.commit.await_count == 1  # analysis + fail-closed audit before dispatch
        mock_task.delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_requires_idempotency_key(self, scientist_client):
        c, _db = scientist_client

        resp = await c.post(
            "/api/v1/analyses",
            json=_launch_payload("aspirin"),
        )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_rejects_declared_input_type_mismatch(self, scientist_client):
        c, db = scientist_client

        resp = await c.post(
            "/api/v1/analyses",
            json=_launch_payload("aspirin", input_type="smiles"),
            headers=ANALYSIS_LAUNCH_HEADERS,
        )

        assert resp.status_code == 422
        assert "Declared input_type does not match" in resp.text
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_requires_explicit_identity_confirmation(self, scientist_client):
        c, _db = scientist_client

        resp = await c.post(
            "/api/v1/analyses",
            json={"compound_input": "aspirin"},
            headers=ANALYSIS_LAUNCH_HEADERS,
        )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_with_custom_config(self, attorney_client):
        c, db = attorney_client

        with (
            patch(
                "api.services.analyses.check_usage_limit",
                new=AsyncMock(return_value=(True, 0, 10)),
            ),
            patch("api.workers.tasks.run_fto_pipeline") as mock_task,
        ):
            mock_task.delay = MagicMock()
            resp = await c.post(
                "/api/v1/analyses",
                json=_launch_payload(
                    "CC(=O)Oc1ccccc1C(=O)O",
                    config={
                        "search_max_ranked_results": 100,
                        "search_tanimoto_threshold": 0.7,
                        "search_jurisdictions": ["EP", "WO"],
                    },
                ),
                headers=ANALYSIS_LAUNCH_HEADERS,
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["compound_input"] == "CC(=O)Oc1ccccc1C(=O)O"

    @pytest.mark.asyncio
    async def test_create_response_includes_safe_launch_context(self, scientist_client):
        c, _db = scientist_client

        with (
            patch(
                "api.services.analyses.check_usage_limit",
                new=AsyncMock(return_value=(True, 0, 10)),
            ),
            patch("api.workers.tasks.run_fto_pipeline") as mock_task,
        ):
            mock_task.delay = MagicMock()
            resp = await c.post(
                "/api/v1/analyses",
                json=_launch_payload(
                    "ibuprofen",
                    trust_mode="counsel",
                    jurisdiction_bundle="custom",
                    target_jurisdictions=["US", "EP"],
                    development_stage="clinical",
                    asset_type_hint="formulation",
                    intended_actions=["formulation_review"],
                    product_context={
                        "product_name": "PRV-142 oral tablet",
                        "dosage_form": "Film-coated tablet",
                        "route_of_administration": "Oral",
                        "owned_or_licensed_ip": "Internal option agreement",
                    },
                ),
                headers=ANALYSIS_LAUNCH_HEADERS,
            )

        assert resp.status_code == 201
        data = resp.json()
        launch_context = data["launch_context"]
        assert launch_context["trust_mode"] == "counsel"
        assert launch_context["jurisdiction_bundle"] == "custom"
        assert launch_context["target_jurisdictions"] == ["US", "EP"]
        assert launch_context["development_stage"] == "clinical"
        assert launch_context["asset_type_hint"] == "formulation"
        assert launch_context["matter_type"] == "formulation"
        assert launch_context["intended_actions"] == ["formulation_review"]
        assert launch_context["product_context"]["product_name"] == "PRV-142 oral tablet"
        assert launch_context["product_context"]["dosage_form"] == "Film-coated tablet"
        assert launch_context["product_context"]["route_of_administration"] == "Oral"
        assert "owned_or_licensed_ip" not in launch_context["product_context"]

    @pytest.mark.asyncio
    async def test_create_rejects_unknown_config_keys(self, attorney_client):
        c, _db = attorney_client

        resp = await c.post(
            "/api/v1/analyses",
            json=_launch_payload(
                "aspirin",
                config={
                    "search_max_ranked_results": 100,
                    "jurisdiction": "EP",
                },
            ),
            headers=ANALYSIS_LAUNCH_HEADERS,
        )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_forbidden_for_client_role(self, client_role_client):
        c, _db = client_role_client
        resp = await c.post(
            "/api/v1/analyses",
            json=_launch_payload("aspirin"),
            headers=ANALYSIS_LAUNCH_HEADERS,
        )
        assert resp.status_code == 403
        assert "Insufficient permissions" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_empty_compound_rejected(self, scientist_client):
        c, _db = scientist_client
        resp = await c.post(
            "/api/v1/analyses",
            json=_launch_payload(""),
            headers=ANALYSIS_LAUNCH_HEADERS,
        )
        assert resp.status_code == 422  # validation error

    @pytest.mark.asyncio
    async def test_create_whitespace_compound_rejected_before_capacity_check(
        self, scientist_client
    ):
        c, _db = scientist_client

        with patch(
            "api.services.analyses.check_usage_limit",
            new=AsyncMock(return_value=(True, 1, 10)),
        ) as check_usage_limit:
            resp = await c.post(
                "/api/v1/analyses",
                json=_launch_payload("   "),
                headers=ANALYSIS_LAUNCH_HEADERS,
            )

        assert resp.status_code == 422
        check_usage_limit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_rejected_when_monthly_limit_reached(self, scientist_client):
        """POST /analyses returns 429 with billing message when org is at its plan limit."""
        c, _db = scientist_client

        # Simulate org at limit: check_usage_limit returns (within_limit=False, used=2, limit=2)
        with patch(
            "api.services.analyses.check_usage_limit",
            new=AsyncMock(return_value=(False, 2, 2)),
        ):
            resp = await c.post(
                "/api/v1/analyses",
                json=_launch_payload("ibuprofen"),
                headers=ANALYSIS_LAUNCH_HEADERS,
            )

        assert resp.status_code == 429
        data = resp.json()
        assert "No FTO report request capacity remains" in data["detail"]
        assert "2 of 2 report requests used" in data["detail"]
        assert data["type"] == ("https://problems.praviar.invalid/analysis-capacity-exhausted")


# ---------------------------------------------------------------------------
# GET /api/v1/analyses — list
# ---------------------------------------------------------------------------


class TestListAnalyses:
    """GET /api/v1/analyses"""

    @pytest.mark.asyncio
    async def test_list_returns_items(self, scientist_client):
        c, db = scientist_client
        analyses = [make_analysis_mock(), make_analysis_mock()]
        count_result, items_result = make_paginated_result(2, analyses)
        status_count_result = MagicMock()
        status_count_result.all.return_value = [(AnalysisStatus.COMPLETED, 2)]
        db.execute = AsyncMock(
            side_effect=[
                status_count_result,
                count_result,
                items_result,
            ]
        )

        resp = await c.get("/api/v1/analyses")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["status_counts"]["all"] == 2
        assert data["status_counts"]["completed"] == 2
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["per_page"] == 20
        assert data["items"][0]["review_status"]["status"] == "pending"
        assert data["items"][0]["review_status"]["is_persisted"] is False
        assert data["items"][0]["overall_risk"] is None
        assert data["items"][0]["blocking_patents_count"] is None
        assert data["items"][0]["risk_ratings_restricted"] is True

    @pytest.mark.asyncio
    async def test_list_rejects_risk_filters_for_restricted_roles(self, scientist_client):
        c, db = scientist_client

        resp = await c.get("/api/v1/analyses?risk_filter=high")

        assert resp.status_code == 403
        assert "restricted to attorney-role users" in resp.json()["detail"]
        assert resp.json()["type"] == ("https://problems.praviar.invalid/risk-query-restricted")
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cursor_list_uses_same_restricted_risk_query_contract(
        self,
        scientist_client,
    ):
        c, db = scientist_client

        resp = await c.get("/api/v1/analyses/cursor?risk_filter=high")

        assert resp.status_code == 403
        assert resp.json()["type"] == ("https://problems.praviar.invalid/risk-query-restricted")
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_empty(self, scientist_client):
        c, db = scientist_client
        count_result, items_result = make_paginated_result(0, [])
        status_count_result = MagicMock()
        status_count_result.all.return_value = []
        db.execute = AsyncMock(side_effect=[status_count_result, count_result, items_result])

        resp = await c.get("/api/v1/analyses")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["status_counts"]["all"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_list_pagination_params(self, scientist_client):
        c, db = scientist_client
        count_result, items_result = make_paginated_result(50, [make_analysis_mock()])
        status_count_result = MagicMock()
        status_count_result.all.return_value = [(AnalysisStatus.COMPLETED, 50)]
        db.execute = AsyncMock(
            side_effect=[
                status_count_result,
                count_result,
                items_result,
            ]
        )

        resp = await c.get("/api/v1/analyses?page=3&per_page=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 3
        assert data["per_page"] == 10

    @pytest.mark.asyncio
    async def test_list_available_to_client_role(self, client_role_client):
        """Clients can list analyses (no role restriction on GET)."""
        c, db = client_role_client
        count_result, items_result = make_paginated_result(0, [])
        status_count_result = MagicMock()
        status_count_result.all.return_value = []
        db.execute = AsyncMock(side_effect=[status_count_result, count_result, items_result])

        resp = await c.get("/api/v1/analyses")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/analyses/{id} — detail
# ---------------------------------------------------------------------------


class TestGetAnalysis:
    """GET /api/v1/analyses/{id}"""

    @pytest.mark.asyncio
    async def test_get_found(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(id=analysis_id)

        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        db.execute = AsyncMock(return_value=analysis_result)

        resp = await c.get(f"/api/v1/analyses/{analysis_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(analysis_id)
        assert data["review_status"]["status"] == "pending"
        assert data["review_status"]["is_persisted"] is False
        assert data["overall_risk"] is None
        assert data["blocking_patents_count"] is None
        assert data["risk_ratings_restricted"] is True

    @pytest.mark.asyncio
    async def test_get_not_found(self, scientist_client):
        c, db = scientist_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.get(f"/api/v1/analyses/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert "Analysis not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_hides_persisted_review_summary_from_scientist(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(id=analysis_id)

        analysis_result = MagicMock()
        analysis_result.scalar_one_or_none.return_value = analysis
        db.execute = AsyncMock(return_value=analysis_result)

        resp = await c.get(f"/api/v1/analyses/{analysis_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["review_status"]["status"] == "pending"
        assert data["review_status"]["is_persisted"] is False
        assert data["review_status"]["note"] is None
        assert data["review_status"]["reviewer_name"] is None


# ---------------------------------------------------------------------------
# DELETE /api/v1/analyses/{id}
# ---------------------------------------------------------------------------


class TestDeleteAnalysis:
    """DELETE /api/v1/analyses/{id}"""

    @pytest.mark.asyncio
    async def test_delete_completed_analysis(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(id=analysis_id, status=AnalysisStatus.COMPLETED)
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.delete(f"/api/v1/analyses/{analysis_id}")
        assert resp.status_code == 204
        # Soft delete: status changed to DELETED (not hard-deleted)
        assert analysis.status == AnalysisStatus.DELETED
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancel_running_analysis(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(id=analysis_id, status=AnalysisStatus.RUNNING)
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.delete(f"/api/v1/analyses/{analysis_id}")
        assert resp.status_code == 204
        assert analysis.status == AnalysisStatus.CANCELLED
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancel_pending_analysis(self, attorney_client):
        c, db = attorney_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(id=analysis_id, status=AnalysisStatus.PENDING)
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.delete(f"/api/v1/analyses/{analysis_id}")
        assert resp.status_code == 204
        assert analysis.status == AnalysisStatus.CANCELLED
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, attorney_client):
        c, db = attorney_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.delete(f"/api/v1/analyses/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_forbidden_for_scientist(self, scientist_client):
        c, _db = scientist_client
        resp = await c.delete(f"/api/v1/analyses/{uuid.uuid4()}")
        assert resp.status_code == 403
        assert "Insufficient permissions" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_forbidden_for_client(self, client_role_client):
        c, _db = client_role_client
        resp = await c.delete(f"/api/v1/analyses/{uuid.uuid4()}")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_allowed_for_admin(self, admin_client):
        c, db = admin_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(id=analysis_id, status=AnalysisStatus.COMPLETED)
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.delete(f"/api/v1/analyses/{analysis_id}")
        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# POST /api/v1/analyses/{id}/flag
# ---------------------------------------------------------------------------


class TestFlagAnalysis:
    """POST /api/v1/analyses/{id}/flag"""

    @pytest.mark.asyncio
    async def test_flag_success(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(id=analysis_id)
        analysis.flagged_for_review = False
        analysis.flagged_by = None

        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.post(f"/api/v1/analyses/{analysis_id}/flag")
        assert resp.status_code == 200
        assert resp.json()["status"] == "flagged"
        assert analysis.flagged_for_review is True
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_flag_not_found(self, scientist_client):
        c, db = scientist_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.post(f"/api/v1/analyses/{uuid.uuid4()}/flag")
        assert resp.status_code == 404
