"""Tests for the USPTO PTE data client (praviar_pipeline.clients.pte_data)."""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from praviar_pipeline.clients.pte_data import (
    PTE_ALL_TIME_URL,
    PTE_CERTIFICATE_COVERAGE_SCOPE,
    PTE_MAX_WORKBOOK_BYTES,
    PTE_OFFICIAL_PAGE_URL,
    PTE_PAST_5_YEARS_URL,
    _parse_pte_workbook_from_rows,
    fetch_pte_applications_last_five_years,
    fetch_pte_certificate_dataset,
    fetch_pte_certificates,
    search_pte_federal_register,
)
from praviar_pipeline.errors import SourceUnavailableError

# ---------------------------------------------------------------------------
# FIX 2 / test 1: URL constant is correct
# ---------------------------------------------------------------------------


def test_pte_all_time_url_is_correct():
    assert PTE_ALL_TIME_URL == "https://www.uspto.gov/sites/default/files/documents/pte_certs.xls"


# ---------------------------------------------------------------------------
# FIX 2 / test 5: No references to the old developer.uspto.gov domain
# ---------------------------------------------------------------------------


def test_no_old_developer_uspto_url():
    """The file must not reference the deprecated developer.uspto.gov endpoint."""
    import inspect

    import praviar_pipeline.clients.pte_data as _mod

    source = inspect.getsource(_mod)
    assert "developer.uspto.gov" not in source, (
        "Found reference to deprecated developer.uspto.gov in pte_data.py"
    )


# ---------------------------------------------------------------------------
# Helpers for building minimal XLSX bytes in-memory with openpyxl
# ---------------------------------------------------------------------------


def _make_xlsx_bytes(rows: list[tuple[Any, ...]]) -> bytes:
    """Return in-memory XLSX content with the given rows (header + data)."""
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_SAMPLE_ROWS = [
    ("Patent Number", "Product Name", "NDA/BLA Number", "Extension (days)", "Status"),
    ("US7654321", "TestDrug", "NDA012345", "365", "Granted"),
    ("US1234567", "OtherDrug", "BLA678901", "180", "Pending"),
]


def _streaming_client(body: bytes, *, headers: dict[str, str] | None = None):
    response = MagicMock(headers=headers or {})
    response.raise_for_status = MagicMock()
    response.body_iterated = False

    async def _aiter_bytes():
        response.body_iterated = True
        yield body

    response.aiter_bytes = _aiter_bytes
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.stream = MagicMock(return_value=response)
    return client, response


# ---------------------------------------------------------------------------
# FIX 2 / test 2: fetch_pte_certificates returns a list of dicts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_pte_certificates_returns_list():
    """Certificate API must use the USPTO all-time issued-certificate workbook.

    Primary source: PTE_OFFICIAL_PAGE_URL, which separately labels the five-year
    workbook as applications and the all-time workbook as certificates issued.
    """
    xlsx_bytes = _make_xlsx_bytes(_SAMPLE_ROWS)

    mock_client, _mock_response = _streaming_client(
        xlsx_bytes,
        headers={"last-modified": "Fri, 08 May 2026 12:00:00 GMT"},
    )

    with patch("praviar_pipeline.clients.pte_data.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_pte_certificates()

    assert isinstance(result, list)
    assert len(result) == 2
    assert {record["status"] for record in result} == {"issued"}
    mock_client.stream.assert_called_once_with("GET", PTE_ALL_TIME_URL)


@pytest.mark.asyncio
async def test_certificate_dataset_records_coverage_and_freshness():
    xlsx_bytes = _make_xlsx_bytes(_SAMPLE_ROWS[:2])
    mock_client, _mock_response = _streaming_client(
        xlsx_bytes,
        headers={"last-modified": "Fri, 08 May 2026 12:00:00 GMT"},
    )

    with patch("praviar_pipeline.clients.pte_data.httpx.AsyncClient", return_value=mock_client):
        dataset = await fetch_pte_certificate_dataset()

    assert dataset.source_url == PTE_ALL_TIME_URL
    assert dataset.official_page_url == PTE_OFFICIAL_PAGE_URL
    assert dataset.coverage_scope == PTE_CERTIFICATE_COVERAGE_SCOPE
    assert "interim" in dataset.coverage_note
    assert dataset.publisher_last_modified == "Fri, 08 May 2026 12:00:00 GMT"
    assert dataset.retrieved_at.tzinfo is not None


@pytest.mark.asyncio
async def test_recent_applications_remain_applications_and_filter_by_status():
    """Recent application disposition is filterable but is not certificate evidence."""
    xlsx_bytes = _make_xlsx_bytes(_SAMPLE_ROWS)
    mock_client, _mock_response = _streaming_client(xlsx_bytes)

    with patch("praviar_pipeline.clients.pte_data.httpx.AsyncClient", return_value=mock_client):
        applications = await fetch_pte_applications_last_five_years(statuses=frozenset({"granted"}))

    assert [record["patent_number"] for record in applications] == ["US7654321"]
    assert applications[0]["status"] == "Granted"
    mock_client.stream.assert_called_once_with("GET", PTE_PAST_5_YEARS_URL)


@pytest.mark.asyncio
async def test_pte_workbook_rejects_declared_oversize_before_read():
    mock_client, response = _streaming_client(
        b"not-read",
        headers={"Content-Length": str(PTE_MAX_WORKBOOK_BYTES + 1)},
    )

    with (
        patch("praviar_pipeline.clients.pte_data.httpx.AsyncClient", return_value=mock_client),
        pytest.raises(SourceUnavailableError, match="byte limit"),
    ):
        await fetch_pte_certificates()

    assert response.body_iterated is False


@pytest.mark.asyncio
async def test_pte_workbook_rejects_streamed_body_one_byte_over_cap(monkeypatch):
    monkeypatch.setattr("praviar_pipeline.clients.pte_data.PTE_MAX_WORKBOOK_BYTES", 5)
    mock_client, response = _streaming_client(b"123456")

    with (
        patch("praviar_pipeline.clients.pte_data.httpx.AsyncClient", return_value=mock_client),
        pytest.raises(SourceUnavailableError, match="byte limit"),
    ):
        await fetch_pte_certificates()

    assert response.body_iterated is True


# ---------------------------------------------------------------------------
# FIX 2 / test 3: parsed entry contains patent_number field
# ---------------------------------------------------------------------------


def test_pte_entry_has_patent_number():
    """_parse_pte_workbook_from_rows should produce records with patent_number."""
    records = _parse_pte_workbook_from_rows(list(_SAMPLE_ROWS))
    assert len(records) >= 1
    for record in records:
        assert "patent_number" in record
        assert record["patent_number"]  # non-empty


def test_pte_parser_skips_publisher_preamble_and_normalizes_xls_numbers():
    records = _parse_pte_workbook_from_rows(
        [
            ("USPTO patent terms extended under 35 U.S.C. 156",),
            ("Updated quarterly",),
            _SAMPLE_ROWS[0],
            (7654321.0, "TestDrug", 12345.0, 365.0, "Issued"),
        ]
    )

    assert records == [
        {
            "patent_number": "7654321",
            "product_name": "TestDrug",
            "nda_bla_number": "12345",
            "extension_days": "365",
            "status": "Issued",
        }
    ]


# ---------------------------------------------------------------------------
# FIX 2 / test 4: search_pte_federal_register sends correct conditions to FR API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_federal_register_query_params():
    """Verify search_pte_federal_register passes expected params to the FR API."""
    captured_params: dict = {}

    async def _fake_get(url: str, params: dict | None = None, **kwargs: Any):
        captured_params.update(params or {})
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"results": []})
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = _fake_get

    with patch("praviar_pipeline.clients.pte_data.httpx.AsyncClient", return_value=mock_client):
        await search_pte_federal_register("aspirin", max_results=5)

    # The search term must contain "patent term extension" and the drug name.
    term = captured_params.get("conditions[term]", "")
    assert "patent term extension" in term.lower()
    assert "aspirin" in term.lower()

    # Must filter to FDA notices.
    assert captured_params.get("conditions[agencies][]") == "food-and-drug-administration"
    assert captured_params.get("conditions[type][]") == "Notice"
    assert captured_params.get("per_page") == 5
