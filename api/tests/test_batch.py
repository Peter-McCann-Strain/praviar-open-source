"""Tests for /api/v1/batch endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.db.models import AnalysisStatus
from api.services.batch import BatchCreationResult

BATCH_IDEMPOTENCY_HEADERS = {
    "Idempotency-Key": "batch-route-test-key-123456",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_batch_mock(**kw) -> MagicMock:
    """Create a mock BatchAnalysis ORM object."""
    b = MagicMock()
    b.id = kw.get("id", uuid.uuid4())
    b.org_id = kw.get("org_id", uuid.uuid4())
    b.user_id = kw.get("user_id", uuid.uuid4())
    b.name = kw.get("name", "Batch Test")
    b.total_compounds = kw.get("total_compounds", 3)
    b.completed_count = kw.get("completed_count", 0)
    b.failed_count = kw.get("failed_count", 0)
    b.status = kw.get("status", AnalysisStatus.PENDING)
    b.analysis_ids = kw.get("analysis_ids", [])
    b.created_at = kw.get("created_at", datetime.now(UTC))
    b.updated_at = kw.get("updated_at", datetime.now(UTC))
    return b


# ---------------------------------------------------------------------------
# POST /api/v1/batch — create
# ---------------------------------------------------------------------------


class TestCreateBatch:
    """POST /api/v1/batch"""

    @pytest.mark.asyncio
    async def test_create_batch(self, scientist_client):
        c, db = scientist_client
        db.refresh = AsyncMock()

        with (
            patch("api.services.batch._lock_batch_launch_org", new=AsyncMock()),
            patch("api.workers.tasks.run_fto_pipeline") as mock_task,
            patch(
                "api.services.batch.reserve_analysis_capacity",
                new=AsyncMock(return_value=(True, 0, 100)),
            ),
        ):
            mock_task.delay = MagicMock()
            resp = await c.post(
                "/api/v1/batch",
                json={
                    "name": "Aspirin Batch",
                    "compounds": ["aspirin", "ibuprofen", "acetaminophen"],
                },
                headers=BATCH_IDEMPOTENCY_HEADERS,
            )

        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["name"] == "Aspirin Batch"
        assert data["total_compounds"] == 3
        assert data["status"] == "pending"
        assert resp.headers["Idempotency-Replayed"] == "false"
        # 3 compounds + 1 batch + 1 audit log = at least 4 db.add calls
        assert db.add.call_count >= 4

    @pytest.mark.asyncio
    async def test_create_batch_requires_idempotency_key(self, scientist_client):
        c, _db = scientist_client

        resp = await c.post(
            "/api/v1/batch",
            json={"name": "Missing receipt", "compounds": ["aspirin"]},
        )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_batch_uses_capacity_exhausted_problem_type(self, scientist_client):
        c, db = scientist_client

        with (
            patch("api.services.batch._lock_batch_launch_org", new=AsyncMock()),
            patch(
                "api.services.batch.reserve_analysis_capacity",
                new=AsyncMock(return_value=(False, 3, 3)),
            ),
        ):
            resp = await c.post(
                "/api/v1/batch",
                json={"name": "No capacity", "compounds": ["aspirin", "ibuprofen"]},
                headers=BATCH_IDEMPOTENCY_HEADERS,
            )

        assert resp.status_code == 429
        data = resp.json()
        assert data["type"] == ("https://problems.praviar.invalid/analysis-capacity-exhausted")
        assert data["detail"].endswith("3 of 3 report requests used.")
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_batch_marks_same_key_replay(self, scientist_client):
        c, _db = scientist_client
        batch = make_batch_mock(name="Replay-safe batch", total_compounds=1)

        with patch(
            "api.routes.batch.create_batch_service",
            new=AsyncMock(return_value=BatchCreationResult(batch=batch, replayed=True)),
        ):
            resp = await c.post(
                "/api/v1/batch",
                json={"name": "Replay-safe batch", "compounds": ["aspirin"]},
                headers=BATCH_IDEMPOTENCY_HEADERS,
            )

        assert resp.status_code == 201
        assert resp.headers["Idempotency-Replayed"] == "true"
        assert resp.json()["id"] == str(batch.id)

    @pytest.mark.asyncio
    async def test_create_batch_empty_compounds(self, scientist_client):
        c, _db = scientist_client

        resp = await c.post(
            "/api/v1/batch",
            json={"name": "Empty Batch", "compounds": []},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_batch_missing_name(self, scientist_client):
        c, _db = scientist_client

        resp = await c.post(
            "/api/v1/batch",
            json={"compounds": ["aspirin"]},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_batch_rejects_unknown_fields(self, scientist_client):
        c, _db = scientist_client

        resp = await c.post(
            "/api/v1/batch",
            json={
                "name": "Aspirin Batch",
                "compounds": ["aspirin"],
                "unexpected": "field",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_batch_forbidden_for_client(self, client_role_client):
        c, _db = client_role_client

        resp = await c.post(
            "/api/v1/batch",
            json={"name": "Test", "compounds": ["aspirin"]},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_batch_with_config(self, scientist_client):
        c, db = scientist_client
        db.refresh = AsyncMock()

        with (
            patch("api.services.batch._lock_batch_launch_org", new=AsyncMock()),
            patch("api.workers.tasks.run_fto_pipeline") as mock_task,
            patch(
                "api.services.batch.reserve_analysis_capacity",
                new=AsyncMock(return_value=(True, 0, 100)),
            ),
        ):
            mock_task.delay = MagicMock()
            resp = await c.post(
                "/api/v1/batch",
                json={
                    "name": "Config Batch",
                    "compounds": ["aspirin"],
                    "config": {"search_jurisdictions": ["EP"]},
                },
                headers=BATCH_IDEMPOTENCY_HEADERS,
            )

        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# GET /api/v1/batch — list
# ---------------------------------------------------------------------------


class TestListBatches:
    """GET /api/v1/batch"""

    @pytest.mark.asyncio
    async def test_list_batches(self, scientist_client):
        c, db = scientist_client
        batches = [make_batch_mock(), make_batch_mock()]

        count_result = MagicMock()
        count_result.scalar_one.return_value = 2

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = batches

        db.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = await c.get("/api/v1/batch")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_batches_empty(self, scientist_client):
        c, db = scientist_client

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = await c.get("/api/v1/batch")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_list_batches_forbidden_for_client(self, client_role_client):
        c, _db = client_role_client
        resp = await c.get("/api/v1/batch")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/v1/batch/{id} — detail with live status recomputation
# ---------------------------------------------------------------------------


class TestGetBatchStatus:
    """GET /api/v1/batch/{id}"""

    @pytest.mark.asyncio
    async def test_get_batch_status(self, scientist_client):
        c, db = scientist_client
        batch_id = uuid.uuid4()
        analysis_id_1 = str(uuid.uuid4())
        analysis_id_2 = str(uuid.uuid4())
        batch = make_batch_mock(
            id=batch_id,
            analysis_ids=[analysis_id_1, analysis_id_2],
            total_compounds=2,
        )

        # Call sequence: find batch, count completed, count failed, count running, commit, refresh
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch

        completed_result = MagicMock()
        completed_result.scalar_one.return_value = 1

        failed_result = MagicMock()
        failed_result.scalar_one.return_value = 0

        running_result = MagicMock()
        running_result.scalar_one.return_value = 1

        db.execute = AsyncMock(
            side_effect=[batch_result, completed_result, failed_result, running_result]
        )
        db.refresh = AsyncMock()

        resp = await c.get(f"/api/v1/batch/{batch_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(batch_id)

    @pytest.mark.asyncio
    async def test_get_batch_not_found(self, scientist_client):
        c, db = scientist_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.get(f"/api/v1/batch/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert "Batch not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_batch_no_analysis_ids(self, scientist_client):
        """Batch with empty analysis_ids should skip recomputation."""
        c, db = scientist_client
        batch_id = uuid.uuid4()
        batch = make_batch_mock(id=batch_id, analysis_ids=[])

        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        db.execute = AsyncMock(return_value=batch_result)

        resp = await c.get(f"/api/v1/batch/{batch_id}")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# DELETE /api/v1/batch/{id} — cancel
# ---------------------------------------------------------------------------


class TestCancelBatch:
    """DELETE /api/v1/batch/{id}"""

    @pytest.mark.asyncio
    async def test_cancel_batch(self, scientist_client):
        c, db = scientist_client
        batch_id = uuid.uuid4()
        analysis_id = str(uuid.uuid4())
        batch = make_batch_mock(id=batch_id, analysis_ids=[analysis_id])

        # First call: find batch, second call: find pending/running analyses
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch

        pending_analysis = MagicMock()
        pending_analysis.status = AnalysisStatus.PENDING
        cancel_result = MagicMock()
        cancel_result.scalars.return_value.all.return_value = [pending_analysis]

        db.execute = AsyncMock(side_effect=[batch_result, cancel_result])

        with patch(
            "api.services.batch.refund_cancelled_analysis_credits",
            new=AsyncMock(return_value=0),
        ):
            resp = await c.delete(f"/api/v1/batch/{batch_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancelled"
        assert batch.status == AnalysisStatus.CANCELLED
        assert pending_analysis.status == AnalysisStatus.CANCELLED
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_cancel_batch_not_found(self, scientist_client):
        c, db = scientist_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.delete(f"/api/v1/batch/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_batch_no_analyses(self, scientist_client):
        """Cancel batch with empty analysis_ids should still succeed."""
        c, db = scientist_client
        batch_id = uuid.uuid4()
        batch = make_batch_mock(id=batch_id, analysis_ids=[])

        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        db.execute = AsyncMock(return_value=batch_result)

        resp = await c.delete(f"/api/v1/batch/{batch_id}")
        assert resp.status_code == 200
        assert batch.status == AnalysisStatus.CANCELLED


# ---------------------------------------------------------------------------
# Org isolation
# ---------------------------------------------------------------------------


class TestBatchOrgIsolation:
    """Batches from other orgs should not be accessible."""

    @pytest.mark.asyncio
    async def test_batch_org_isolation(self, scientist_client):
        c, db = scientist_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.get(f"/api/v1/batch/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_other_org_batch_404(self, scientist_client):
        c, db = scientist_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.delete(f"/api/v1/batch/{uuid.uuid4()}")
        assert resp.status_code == 404
