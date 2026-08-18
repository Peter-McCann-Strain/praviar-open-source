"""Tests for the FDA Paragraph IV certification client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from pytest_httpx import HTTPXMock

from praviar_pipeline.clients.paragraph_iv import (
    PARAGRAPH_IV_MAX_PDF_BYTES,
    ParagraphIVEntry,
    _extract_row,
    _find_header_row,
    _normalise_exclusivity,
    _normalise_submission_count,
    fetch_paragraph_iv_pdf,
    lookup_paragraph_iv_status,
    parse_paragraph_iv_pdf,
)
from praviar_pipeline.errors import ConfigurationError, SourceUnavailableError

# ---------------------------------------------------------------------------
# Helpers to build a minimal mock pdfplumber PDF
# ---------------------------------------------------------------------------

_SAMPLE_HEADERS = [
    "Drug Name",
    "Dosage Form",
    "Strength",
    "NDA",
    "Number of ANDA",
    "First Filing Date",
    "Patent Expiry",
    "180-Day",
]

_SAMPLE_ROWS = [
    ["Ibuprofen", "Tablet", "400 mg", "N018281", "3", "2023-01-15", "2026-06-30", "Y"],
    ["Metformin", "Capsule", "500 mg", "N021343", "7", "2022-05-01", "2025-12-31", "N"],
    ["Aspirin", "Tablet", "81 mg", "N019458", "1", "", "", ""],
    # Row with no drug name -- should be skipped
    ["", "", "", "", "", "", "", ""],
]


def _make_mock_pdf_bytes(tables_per_page: list[list[list[list[str]]]]) -> bytes:
    """Return a sentinel bytes object; pdfplumber is mocked in tests that use this."""
    return b"%PDF-1.4 mock"


def _build_mock_pdfplumber(tables_per_page: list[list[list[list[str]]]]):
    """Construct a pdfplumber mock whose pages return the supplied tables."""
    mock_pages = []
    for page_tables in tables_per_page:
        mock_page = MagicMock()
        mock_page.extract_tables.return_value = page_tables
        mock_pages.append(mock_page)

    mock_pdf = MagicMock()
    mock_pdf.pages = mock_pages
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)
    return mock_pdf


# ---------------------------------------------------------------------------
# Unit tests -- low-level helpers
# ---------------------------------------------------------------------------


class TestNormaliseSubmissionCount:
    def test_plain_integer(self):
        assert _normalise_submission_count("3") == 3

    def test_integer_with_comma(self):
        assert _normalise_submission_count("1,234") == 1234

    def test_empty_string(self):
        assert _normalise_submission_count("") is None

    def test_dash_placeholder(self):
        assert _normalise_submission_count("-") is None

    def test_whitespace_only(self):
        assert _normalise_submission_count("   ") is None

    def test_non_numeric(self):
        assert _normalise_submission_count("n/a") is None


class TestNormaliseExclusivity:
    @pytest.mark.parametrize("raw", ["Y", "y", "Yes", "yes", "x", "X", "1", "true"])
    def test_truthy_values(self, raw):
        assert _normalise_exclusivity(raw) is True

    @pytest.mark.parametrize("raw", ["N", "n", "No", "no", "0", "", "false"])
    def test_falsy_values(self, raw):
        assert _normalise_exclusivity(raw) is False


class TestFindHeaderRow:
    def test_finds_header_in_first_row(self):
        table = [
            _SAMPLE_HEADERS,
            _SAMPLE_ROWS[0],
        ]
        assert _find_header_row(table) == 0

    def test_finds_header_in_second_row(self):
        table = [
            ["Page 1 of 3", "", "", "", "", "", "", ""],
            _SAMPLE_HEADERS,
            _SAMPLE_ROWS[0],
        ]
        assert _find_header_row(table) == 1

    def test_returns_none_when_no_header(self):
        table = [
            ["foo", "bar", "baz"],
            ["1", "2", "3"],
        ]
        assert _find_header_row(table) is None

    def test_empty_table(self):
        assert _find_header_row([]) is None


class TestExtractRow:
    def test_extracts_complete_row(self):
        entry = _extract_row(_SAMPLE_ROWS[0], _SAMPLE_HEADERS)
        assert entry is not None
        assert entry.drug_name == "Ibuprofen"
        assert entry.dosage_form == "Tablet"
        assert entry.strength == "400 mg"
        assert entry.nda_number == "N018281"
        assert entry.submission_count == 3
        assert entry.first_filing_date == "2023-01-15"
        assert entry.patent_expiry_date == "2026-06-30"
        assert entry.has_180_day_exclusivity is True

    def test_extracts_row_without_exclusivity(self):
        entry = _extract_row(_SAMPLE_ROWS[1], _SAMPLE_HEADERS)
        assert entry is not None
        assert entry.drug_name == "Metformin"
        assert entry.has_180_day_exclusivity is False

    def test_extracts_row_with_empty_optional_fields(self):
        entry = _extract_row(_SAMPLE_ROWS[2], _SAMPLE_HEADERS)
        assert entry is not None
        assert entry.drug_name == "Aspirin"
        assert entry.first_filing_date is None
        assert entry.patent_expiry_date is None

    def test_returns_none_for_blank_row(self):
        assert _extract_row(_SAMPLE_ROWS[3], _SAMPLE_HEADERS) is None

    def test_returns_none_when_row_shorter_than_headers(self):
        # Only the drug-name cell present; everything else is absent.
        assert _extract_row([""], _SAMPLE_HEADERS) is None

    def test_handles_row_longer_than_headers(self):
        long_row = _SAMPLE_ROWS[0] + ["extra", "cells"]
        entry = _extract_row(long_row, _SAMPLE_HEADERS)
        assert entry is not None
        assert entry.drug_name == "Ibuprofen"


# ---------------------------------------------------------------------------
# Integration-style tests -- parse_paragraph_iv_pdf
# ---------------------------------------------------------------------------


@pytest.fixture
def pdfplumber_available():
    return pytest.importorskip(
        "pdfplumber",
        reason="Paragraph IV PDF table parsing tests require optional pdfplumber dependency",
    )


class TestParseParagraphIVPdf:
    def _make_table(self) -> list[list[str]]:
        return [_SAMPLE_HEADERS, *_SAMPLE_ROWS]

    def test_returns_entries_from_single_page_table(self, pdfplumber_available):
        tables = [[self._make_table()]]
        mock_pdf = _build_mock_pdfplumber(tables)

        with patch("pdfplumber.open", return_value=mock_pdf):
            entries = parse_paragraph_iv_pdf(b"%PDF mock")

        # 3 real rows + 1 blank row (skipped) = 3 entries
        assert len(entries) == 3
        drug_names = [e.drug_name for e in entries]
        assert "Ibuprofen" in drug_names
        assert "Metformin" in drug_names
        assert "Aspirin" in drug_names

    def test_skips_table_without_recognised_header(self, pdfplumber_available):
        no_header_table = [
            ["Column A", "Column B"],
            ["value1", "value2"],
        ]
        mock_pdf = _build_mock_pdfplumber([[no_header_table]])

        with patch("pdfplumber.open", return_value=mock_pdf):
            entries = parse_paragraph_iv_pdf(b"%PDF mock")

        assert entries == []

    def test_handles_multi_page_pdf(self, pdfplumber_available):
        page1_tables = [[_SAMPLE_HEADERS, *_SAMPLE_ROWS[:2]]]
        page2_tables = [[_SAMPLE_HEADERS, *_SAMPLE_ROWS[2:]]]
        mock_pdf = _build_mock_pdfplumber([page1_tables, page2_tables])

        with patch("pdfplumber.open", return_value=mock_pdf):
            entries = parse_paragraph_iv_pdf(b"%PDF mock")

        # Page 1: 2 entries; page 2: 1 real entry + 1 blank (skipped)
        assert len(entries) == 3

    def test_parse_error_fails_closed(self, pdfplumber_available):
        with patch("pdfplumber.open", side_effect=Exception("corrupt PDF")):
            with pytest.raises(SourceUnavailableError):
                parse_paragraph_iv_pdf(b"not a pdf")

    def test_handles_page_with_no_tables(self, pdfplumber_available):
        mock_page = MagicMock()
        mock_page.extract_tables.return_value = []
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("pdfplumber.open", return_value=mock_pdf):
            entries = parse_paragraph_iv_pdf(b"%PDF mock")

        assert entries == []

    def test_entries_are_pydantic_models(self, pdfplumber_available):
        tables = [[self._make_table()]]
        mock_pdf = _build_mock_pdfplumber(tables)

        with patch("pdfplumber.open", return_value=mock_pdf):
            entries = parse_paragraph_iv_pdf(b"%PDF mock")

        for entry in entries:
            assert isinstance(entry, ParagraphIVEntry)


class TestParseParagraphIVPdfDependencyGate:
    """Missing evidence parsers fail closed rather than reporting zero rows."""

    def test_missing_pdfplumber_raises_configuration_error(self, caplog):
        import sys

        # Temporarily hide pdfplumber from the import machinery.
        real_module = sys.modules.pop("pdfplumber", None)
        try:
            with patch.dict(sys.modules, {"pdfplumber": None}):
                with pytest.raises(ConfigurationError):
                    parse_paragraph_iv_pdf(b"%PDF mock")
        finally:
            if real_module is not None:
                sys.modules["pdfplumber"] = real_module


# ---------------------------------------------------------------------------
# lookup_paragraph_iv_status
# ---------------------------------------------------------------------------


class TestLookupParagraphIVStatus:
    @pytest.fixture
    def sample_entries(self) -> list[ParagraphIVEntry]:
        return [
            ParagraphIVEntry(drug_name="Ibuprofen", nda_number="N018281"),
            ParagraphIVEntry(drug_name="Metformin", nda_number="N021343"),
            ParagraphIVEntry(drug_name="Aspirin", nda_number="N019458"),
            # Duplicate NDA number -- both should be returned.
            ParagraphIVEntry(drug_name="Ibuprofen Extended", nda_number="N018281"),
        ]

    def test_returns_matching_entries(self, sample_entries):
        result = lookup_paragraph_iv_status("N018281", sample_entries)
        assert len(result) == 2
        assert all(e.nda_number == "N018281" for e in result)

    def test_returns_empty_list_when_not_found(self, sample_entries):
        result = lookup_paragraph_iv_status("N999999", sample_entries)
        assert result == []

    def test_matching_is_case_insensitive(self, sample_entries):
        result = lookup_paragraph_iv_status("n021343", sample_entries)
        assert len(result) == 1
        assert result[0].drug_name == "Metformin"

    def test_strips_leading_n_prefix(self, sample_entries):
        # 'N021343' and '021343' should match the same record.
        result_with_prefix = lookup_paragraph_iv_status("N021343", sample_entries)
        result_without_prefix = lookup_paragraph_iv_status("021343", sample_entries)
        assert len(result_with_prefix) == len(result_without_prefix) == 1

    def test_strips_leading_zeros(self, sample_entries):
        result = lookup_paragraph_iv_status("018281", sample_entries)
        assert len(result) == 2

    def test_empty_nda_number_returns_empty(self, sample_entries):
        assert lookup_paragraph_iv_status("", sample_entries) == []

    def test_empty_entries_list(self):
        assert lookup_paragraph_iv_status("N018281", []) == []

    def test_entry_with_none_nda_number_is_skipped(self):
        entries = [
            ParagraphIVEntry(drug_name="Orphan Drug", nda_number=None),
            ParagraphIVEntry(drug_name="Ibuprofen", nda_number="N018281"),
        ]
        result = lookup_paragraph_iv_status("N018281", entries)
        assert len(result) == 1
        assert result[0].drug_name == "Ibuprofen"


# ---------------------------------------------------------------------------
# fetch_paragraph_iv_pdf -- HTTP layer
# ---------------------------------------------------------------------------


class TestFetchParagraphIVPdf:
    async def test_returns_pdf_bytes_on_success(self, httpx_mock: HTTPXMock):
        fake_pdf = b"%PDF-1.4 fake content"
        httpx_mock.add_response(
            url="https://www.fda.gov/media/12345/download",
            content=fake_pdf,
            status_code=200,
        )

        result = await fetch_paragraph_iv_pdf("https://www.fda.gov/media/12345/download")

        assert result == fake_pdf

    async def test_raises_on_404(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="https://www.fda.gov/media/99999/download",
            status_code=404,
        )

        with pytest.raises(httpx.HTTPStatusError):
            await fetch_paragraph_iv_pdf("https://www.fda.gov/media/99999/download")

    async def test_raises_on_500(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="https://www.fda.gov/media/99999/download",
            status_code=500,
        )

        with pytest.raises(httpx.HTTPStatusError):
            await fetch_paragraph_iv_pdf("https://www.fda.gov/media/99999/download")

    async def test_follows_redirects(self, httpx_mock: HTTPXMock):
        fake_pdf = b"%PDF-1.4 redirected"
        httpx_mock.add_response(
            url="https://www.fda.gov/media/12345/download",
            status_code=301,
            headers={"Location": "https://downloads.fda.gov/para4.pdf"},
        )
        httpx_mock.add_response(
            url="https://downloads.fda.gov/para4.pdf",
            content=fake_pdf,
            status_code=200,
        )

        result = await fetch_paragraph_iv_pdf("https://www.fda.gov/media/12345/download")
        assert result == fake_pdf

    async def test_rejects_declared_body_one_byte_over_cap(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="https://www.fda.gov/media/12345/download",
            content=b"x",
            headers={"Content-Length": str(PARAGRAPH_IV_MAX_PDF_BYTES + 1)},
        )

        with pytest.raises(SourceUnavailableError, match="byte limit"):
            await fetch_paragraph_iv_pdf("https://www.fda.gov/media/12345/download")

    def test_parser_rejects_direct_oversize_body(self):
        with pytest.raises(SourceUnavailableError, match="byte limit"):
            parse_paragraph_iv_pdf(b"x" * (PARAGRAPH_IV_MAX_PDF_BYTES + 1))
