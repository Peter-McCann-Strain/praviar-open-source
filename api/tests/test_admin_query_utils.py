"""Tests for shared admin query utilities."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from conftest import make_mock_db

from api.db.models import Organization
from api.services.admin_query_utils import build_page_window, execute_paged_query, load_id_map


def test_build_page_window_returns_offset_and_limit():
    assert build_page_window(page=3, per_page=25) == (50, 25)


@pytest.mark.asyncio
async def test_execute_paged_query_applies_shared_window():
    db = make_mock_db()
    count_result = SimpleNamespace(scalar_one=lambda: 9)
    rows_result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: ["row-1", "row-2"]))
    db.execute.side_effect = [count_result, rows_result]

    base_query = MagicMock()
    base_query.order_by.return_value = base_query
    base_query.offset.return_value = base_query
    base_query.limit.return_value = base_query
    count_query = MagicMock()

    total, rows = await execute_paged_query(
        db,
        base_query=base_query,
        count_query=count_query,
        order_by="created_at.desc()",
        page=2,
        per_page=4,
    )

    assert total == 9
    assert rows == ["row-1", "row-2"]
    base_query.order_by.assert_called_once_with("created_at.desc()")
    base_query.offset.assert_called_once_with(4)
    base_query.limit.assert_called_once_with(4)
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_load_id_map_skips_empty_ids():
    db = make_mock_db()

    result = await load_id_map(
        db,
        model=object(),
        id_column=object(),
        value_column=object(),
        ids=set(),
    )

    assert result == {}
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_load_id_map_returns_mapping():
    db = make_mock_db()
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    db.execute.return_value = SimpleNamespace(
        all=lambda: [(first_id, "alpha"), (second_id, "beta")]
    )

    result = await load_id_map(
        db,
        model=Organization,
        id_column=Organization.id,
        value_column=Organization.name,
        ids={first_id, second_id},
    )

    assert result == {first_id: "alpha", second_id: "beta"}
    db.execute.assert_awaited_once()
