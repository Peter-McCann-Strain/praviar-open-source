"""Tests for /api/v1/compounds endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from conftest import bind_report_data, make_compound_mock, valid_report_data_for_patents

from api.services.compounds import MAX_COMPOUND_SEARCH_LENGTH

# ---------------------------------------------------------------------------
# GET /api/v1/compounds
# ---------------------------------------------------------------------------


def _report_with_patents(patent_ids: list[str]) -> dict:
    report = valid_report_data_for_patents([{"patent_id": patent_id} for patent_id in patent_ids])
    report["compound"]["inchi_key"] = ""
    return report


def _compound_row(
    compound=None,
    *,
    display_name: str | None = None,
    first_analyzed_at: datetime | None = None,
    analysis_count: int = 1,
):
    resolved_compound = compound or make_compound_mock()
    return (
        resolved_compound,
        display_name if display_name is not None else resolved_compound.name,
        first_analyzed_at or datetime(2026, 7, 1, tzinfo=UTC),
        analysis_count,
    )


def _list_results(total: int, rows: list[tuple]) -> tuple[MagicMock, MagicMock]:
    count_result = MagicMock()
    count_result.scalar_one.return_value = total
    items_result = MagicMock()
    items_result.all.return_value = rows
    return count_result, items_result


class TestListCompounds:
    @pytest.mark.asyncio
    async def test_list_returns_items(self, scientist_client):
        c, db = scientist_client
        compounds = [make_compound_mock(), make_compound_mock(name="Ibuprofen")]
        count_result, items_result = _list_results(
            2,
            [
                _compound_row(compounds[0], analysis_count=2),
                _compound_row(compounds[1], analysis_count=1),
            ],
        )
        db.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = await c.get("/api/v1/compounds")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert [item["analysis_count"] for item in data["items"]] == [2, 1]

    @pytest.mark.asyncio
    async def test_list_empty(self, scientist_client):
        c, db = scientist_client
        count_result, items_result = _list_results(0, [])
        db.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = await c.get("/api/v1/compounds")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["items"] == []

    @pytest.mark.asyncio
    async def test_list_with_search(self, scientist_client):
        c, db = scientist_client
        compounds = [make_compound_mock(name="Aspirin")]
        count_result, items_result = _list_results(1, [_compound_row(compounds[0])])
        db.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = await c.get("/api/v1/compounds?search=aspirin")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_list_rejects_overlong_search(self, scientist_client):
        c, db = scientist_client

        resp = await c.get(
            "/api/v1/compounds",
            params={"search": "C" * (MAX_COMPOUND_SEARCH_LENGTH + 1)},
        )

        assert resp.status_code == 422
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_pagination(self, scientist_client):
        c, db = scientist_client
        count_result, items_result = _list_results(50, [_compound_row()])
        db.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = await c.get("/api/v1/compounds?page=2&per_page=10")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_accessible_to_client_role(self, client_role_client):
        """No role restriction on listing compounds."""
        c, db = client_role_client
        count_result, items_result = _list_results(0, [])
        db.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = await c.get("/api/v1/compounds")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/compounds/{id}
# ---------------------------------------------------------------------------


class TestGetCompound:
    @pytest.mark.asyncio
    async def test_get_found(self, scientist_client):
        c, db = scientist_client
        cid = uuid.uuid4()
        compound = make_compound_mock(
            id=cid,
            name="Ibuprofen",
            analysis_count=999,
            first_analyzed_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
        local_first_analyzed_at = datetime(2026, 6, 2, tzinfo=UTC)
        db.execute.return_value.one_or_none.return_value = _compound_row(
            compound,
            first_analyzed_at=local_first_analyzed_at,
            analysis_count=2,
        )

        resp = await c.get(f"/api/v1/compounds/{cid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(cid)
        assert data["name"] == "Ibuprofen"
        assert data["analysis_count"] == 2
        assert data["first_analyzed_at"] == "2026-06-02T00:00:00Z"

    @pytest.mark.asyncio
    async def test_get_uses_org_local_display_name_not_global_compound_name(
        self,
        scientist_client,
    ):
        c, db = scientist_client
        cid = uuid.uuid4()
        compound = make_compound_mock(
            id=cid,
            name="Other tenant project codename",
        )
        db.execute.return_value.one_or_none.return_value = _compound_row(
            compound,
            display_name="Aspirin",
        )

        resp = await c.get(f"/api/v1/compounds/{cid}")

        assert resp.status_code == 200
        assert resp.json()["name"] == "Aspirin"
        assert "Other tenant project codename" not in resp.text

    @pytest.mark.asyncio
    async def test_get_not_found(self, scientist_client):
        c, db = scientist_client
        db.execute.return_value.one_or_none.return_value = None

        resp = await c.get(f"/api/v1/compounds/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert "Compound not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /api/v1/compounds/compare
# ---------------------------------------------------------------------------


class TestCompareCompounds:
    @pytest.mark.asyncio
    async def test_compare_success(self, scientist_client):
        c, db = scientist_client
        id1, id2 = uuid.uuid4(), uuid.uuid4()
        compounds = [
            make_compound_mock(id=id1, canonical_smiles="AAA"),
            make_compound_mock(id=id2, canonical_smiles="BBB"),
        ]
        compound_result = MagicMock()
        compound_result.all.return_value = [
            _compound_row(compounds[0], analysis_count=2),
            _compound_row(compounds[1], analysis_count=1),
        ]
        analysis_rows_result = MagicMock()
        analysis_rows_result.all.return_value = [
            (
                id1,
                compounds[0].canonical_smiles,
                bind_report_data(
                    _report_with_patents(["US92000001A1"]),
                    analysis_id=id1,
                ),
            ),
            (
                id2,
                compounds[1].canonical_smiles,
                bind_report_data(
                    _report_with_patents(["US92000001A1", "US92000002A1"]),
                    analysis_id=id2,
                ),
            ),
        ]
        db.execute = AsyncMock(side_effect=[compound_result, analysis_rows_result])

        resp = await c.get(
            "/api/v1/compounds/compare",
            params={"ids": [str(id1), str(id2)]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "compounds" in data
        assert "overlapping_patents" in data
        assert data["overlapping_patents"] == [{"patent_id": "US92000001A1", "compound_count": 2}]

    @pytest.mark.asyncio
    async def test_compare_missing_compound(self, scientist_client):
        c, db = scientist_client
        id1, id2 = uuid.uuid4(), uuid.uuid4()
        # Only return one compound when two were requested
        db.execute.return_value.all.return_value = [_compound_row(make_compound_mock(id=id1))]

        resp = await c.get(
            "/api/v1/compounds/compare",
            params={"ids": [str(id1), str(id2)]},
        )
        assert resp.status_code == 404
        assert "One or more compounds not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_compare_requires_minimum_two(self, scientist_client):
        c, _db = scientist_client
        resp = await c.get(
            "/api/v1/compounds/compare",
            params={"ids": [str(uuid.uuid4())]},
        )
        # FastAPI query validation will reject < 2 ids
        assert resp.status_code == 422
