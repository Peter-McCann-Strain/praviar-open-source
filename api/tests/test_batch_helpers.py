"""Direct tests for batch helper modules."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import make_mock_db

from api.db.models import AnalysisStatus
from api.services.batch import BatchPage
from api.services.batch_queries import load_batch_for_org, load_batch_page
from api.services.batch_serialization import serialize_batch, serialize_batch_page
from api.services.batch_status import recompute_batch_status


def make_service_batch_mock(**kw) -> MagicMock:
    batch = MagicMock()
    batch.id = kw.get("id", uuid.uuid4())
    batch.org_id = kw.get("org_id", uuid.uuid4())
    batch.user_id = kw.get("user_id", uuid.uuid4())
    batch.name = kw.get("name", "Batch Test")
    batch.total_compounds = kw.get("total_compounds", 3)
    batch.completed_count = kw.get("completed_count", 0)
    batch.failed_count = kw.get("failed_count", 0)
    batch.status = kw.get("status", AnalysisStatus.PENDING)
    batch.analysis_ids = kw.get("analysis_ids", [])
    batch.created_at = kw.get("created_at", datetime.now(UTC))
    batch.updated_at = kw.get("updated_at", datetime.now(UTC))
    return batch


def test_serialize_batch_and_page():
    batch = make_service_batch_mock(
        id=uuid.uuid4(),
        name="Batch Test",
        total_compounds=4,
        completed_count=1,
        failed_count=0,
        status=AnalysisStatus.RUNNING,
        analysis_ids=["a", "b"],
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    page = BatchPage(items=[batch], total=1)

    serialized = serialize_batch(batch)
    serialized_page = serialize_batch_page(page)

    assert serialized["name"] == "Batch Test"
    assert serialized["status"] == "running"
    assert serialized_page == {"items": [serialized], "total": 1}


def test_recompute_batch_status_matrix():
    cases = [
        (2, 2, 0, 0, AnalysisStatus.COMPLETED),
        (2, 1, 0, 1, AnalysisStatus.RUNNING),
        (2, 0, 2, 0, AnalysisStatus.FAILED),
        (2, 0, 1, 0, AnalysisStatus.RUNNING),
        (2, 0, 0, 0, AnalysisStatus.PENDING),
    ]

    for total, completed, failed, running, expected in cases:
        assert (
            recompute_batch_status(
                total_compounds=total,
                completed_count=completed,
                failed_count=failed,
                running_count=running,
            )
            == expected
        )


@pytest.mark.asyncio
async def test_load_batch_page_returns_batch_page():
    db = make_mock_db()
    batch_one = make_service_batch_mock(name="Batch 1")
    batch_two = make_service_batch_mock(name="Batch 2")
    count_result = MagicMock()
    count_result.scalar_one.return_value = 2
    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = [batch_one, batch_two]
    db.execute = AsyncMock(side_effect=[count_result, items_result])

    page = await load_batch_page(db, org_id=batch_one.org_id, page=1, per_page=20)

    assert isinstance(page, BatchPage)
    assert page.total == 2
    assert page.items == [batch_one, batch_two]


@pytest.mark.asyncio
async def test_load_batch_for_org_returns_batch():
    db = make_mock_db()
    batch = make_service_batch_mock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = batch
    db.execute = AsyncMock(return_value=result)

    loaded = await load_batch_for_org(db, batch_id=batch.id, org_id=batch.org_id)

    assert loaded is batch
