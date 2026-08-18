"""Tests for Purple Book client -- biologic product data."""

from __future__ import annotations

import pytest

from praviar_pipeline.clients.purple_book import (
    PurpleBookEntry,
    PurpleBookIndex,
    PurpleBookRecord,
    _parse_purple_book_csv,
    _parse_purple_book_csv_to_records,
    fetch_purple_book_data,
    load_purple_book,
    lookup_biologic_exclusivity,
    reset_purple_book_cache,
)

# Sample CSV content mimicking the real Purple Book format.
# Row 1: report title, Row 2: blank, Row 3: section label, Row 4: column headers, Row 5+: data.
SAMPLE_CSV = """\
Purple Book Monthly Historical Data Changes Report - March 2026,,,,,,,,,,,,,,,,,,,,,,,,
,,,,,,,,,,,,,,,,,,,,,,,,
Newly Approved Products (N)  / Products Added in Current Release (R) / Updated Products (U),,,,,,,,,,,,,,,,,,,,,,,,
N/R/U,Applicant,BLA Number,Proprietary Name,Proper Name,BLA Type,Strength,Dosage Form,Route of Administration,Product Presentation,Marketing Status,Licensure,Approval Date,Ref. Product Proper Name,Ref. Product Proprietary Name,Supplement Number,Submission Type,License Number,Product Number,Center,Date of First Licensure,Exclusivity Expiration Date,First Interchangeable Exclusivity Exp. Date,Ref. Product Exclusivity Exp. Date,Orphan Exclusivity Exp. Date
,AbbVie Inc.,125057,Humira,adalimumab,351(a),40MG/0.8ML,Injection,Subcutaneous,Autoinjector,Rx,Licensed,31-Dec-02,N/A,N/A,,Original,1889,1,CDER,01-Jan-03,,,,24-Feb-28
,Amgen Inc.,761024,Amjevita,adalimumab-atto,351(k) Interchangeable,40MG/0.8ML,Injection,Subcutaneous,Pre-Filled Syringe,Rx,Licensed,23-Sep-16,adalimumab,Humira,,Original,1080,1,CDER,,,,,
,"Genentech, Inc.",103792,Herceptin,trastuzumab,351(a),420MG,For Injection,Intravenous,Multi-Dose Vial,Rx,Licensed,25-Sep-98,N/A,N/A,,Original,1048,1,CDER,,,,,20-Oct-17
"""

# Minimal CSV using the extended column set (with Ref. Product Exclusivity Exp. Date and
# Date of First Licensure) for testing fetch_purple_book_data / lookup_biologic_exclusivity.
EXTENDED_CSV = """\
Purple Book Monthly Historical Data Changes Report - January 2026,,,,,,,,,,,,,,,,,,,,,,,,
,,,,,,,,,,,,,,,,,,,,,,,,
,,,,,,,,,,,,,,,,,,,,,,,,
N/R/U,Applicant,BLA Number,Proprietary Name,Proper Name,BLA Type,Strength,Dosage Form,Route of Administration,Product Presentation,Marketing Status,Licensure,Approval Date,Ref. Product Proper Name,Ref. Product Proprietary Name,Supplement Number,Submission Type,License Number,Product Number,Center,Date of First Licensure,Exclusivity Expiration Date,First Interchangeable Exclusivity Exp. Date,Ref. Product Exclusivity Exp. Date,Orphan Exclusivity Exp. Date
,AbbVie Inc.,125057,Humira,adalimumab,351(a),40MG/0.8ML,Injection,Subcutaneous,Autoinjector,Rx,Licensed,31-Dec-02,N/A,N/A,,Original,1889,1,CDER,01-Jan-03,,,24-Feb-28,
,Amgen Inc.,761024,Amjevita,adalimumab-atto,351(k) Interchangeable,40MG/0.8ML,Injection,Subcutaneous,Pre-Filled Syringe,Rx,Licensed,23-Sep-16,adalimumab,Humira,,Original,1080,1,CDER,,,,,
"""


class TestParseCSV:
    def test_parse_finds_header_row(self):
        entries = _parse_purple_book_csv(SAMPLE_CSV)
        assert len(entries) == 3

    def test_parse_extracts_bla_numbers(self):
        entries = _parse_purple_book_csv(SAMPLE_CSV)
        bla_numbers = [e.bla_number for e in entries]
        assert "125057" in bla_numbers
        assert "761024" in bla_numbers
        assert "103792" in bla_numbers

    def test_parse_extracts_proper_names(self):
        entries = _parse_purple_book_csv(SAMPLE_CSV)
        names = [e.proper_name for e in entries]
        assert "adalimumab" in names
        assert "trastuzumab" in names

    def test_parse_extracts_bla_types(self):
        entries = _parse_purple_book_csv(SAMPLE_CSV)
        types = {e.bla_number: e.bla_type for e in entries}
        assert types["125057"] == "351(a)"
        assert "351(k)" in types["761024"]


class TestParseCSVToRecords:
    """Tests for the snake_case record parser used by fetch_purple_book_data."""

    def test_returns_list_of_dicts(self):
        records = _parse_purple_book_csv_to_records(SAMPLE_CSV)
        assert isinstance(records, list)
        assert all(isinstance(r, dict) for r in records)

    def test_snake_case_keys(self):
        records = _parse_purple_book_csv_to_records(SAMPLE_CSV)
        assert len(records) > 0
        expected_keys = {
            "bla_number",
            "proper_name",
            "proprietary_name",
            "applicant",
            "bla_type",
            "exclusivity_expiration",
            "ref_product_exclusivity_expiry",
            "date_of_first_licensure",
        }
        assert expected_keys.issubset(set(records[0].keys()))

    def test_extracts_bla_number(self):
        records = _parse_purple_book_csv_to_records(SAMPLE_CSV)
        blas = [r["bla_number"] for r in records]
        assert "125057" in blas

    def test_no_patent_numbers_present(self):
        # Purple Book does not contain patent numbers -- confirm no such key
        records = _parse_purple_book_csv_to_records(SAMPLE_CSV)
        for record in records:
            assert "patent_number" not in record


class TestPurpleBookRecord:
    """Tests for the Pydantic PurpleBookRecord model."""

    def test_valid_construction(self):
        rec = PurpleBookRecord(bla_number="125057", bla_type="351(a)")
        assert rec.bla_number == "125057"
        assert rec.is_reference_product is True
        assert rec.is_biosimilar is False

    def test_biosimilar(self):
        rec = PurpleBookRecord(bla_number="761024", bla_type="351(k) Interchangeable")
        assert rec.is_biosimilar is True
        assert rec.is_reference_product is False

    def test_defaults_are_empty_strings(self):
        rec = PurpleBookRecord(bla_number="999999")
        assert rec.proper_name == ""
        assert rec.exclusivity_expiration == ""
        assert rec.ref_product_exclusivity_expiry == ""


class TestPurpleBookEntry:
    def test_is_reference_product(self):
        entry = PurpleBookEntry(bla_number="125057", bla_type="351(a)")
        assert entry.is_reference_product is True
        assert entry.is_biosimilar is False

    def test_is_biosimilar(self):
        entry = PurpleBookEntry(bla_number="761024", bla_type="351(k) Interchangeable")
        assert entry.is_biosimilar is True
        assert entry.is_reference_product is False


class TestPurpleBookIndex:
    @pytest.fixture
    def index(self) -> PurpleBookIndex:
        entries = _parse_purple_book_csv(SAMPLE_CSV)
        return PurpleBookIndex(entries)

    def test_product_count(self, index: PurpleBookIndex):
        assert index.product_count == 3

    def test_lookup_by_proper_name(self, index: PurpleBookIndex):
        result = index.lookup_biologic("adalimumab")
        assert result is not None
        assert result["bla_number"] == "125057"
        assert result["product_name"] == "Humira"

    def test_lookup_by_proprietary_name(self, index: PurpleBookIndex):
        result = index.lookup_biologic("Humira")
        assert result is not None
        assert result["proper_name"] == "adalimumab"
        assert result["bla_number"] == "125057"

    def test_lookup_by_bla_number(self, index: PurpleBookIndex):
        result = index.lookup_biologic("125057")
        assert result is not None
        assert result["proper_name"] == "adalimumab"

    def test_lookup_case_insensitive(self, index: PurpleBookIndex):
        result = index.lookup_biologic("ADALIMUMAB")
        assert result is not None
        assert result["bla_number"] == "125057"

    def test_lookup_not_found(self, index: PurpleBookIndex):
        result = index.lookup_biologic("nonexistent_drug")
        assert result is None

    def test_lookup_empty_query(self, index: PurpleBookIndex):
        result = index.lookup_biologic("")
        assert result is None

    def test_lookup_returns_reference_product(self, index: PurpleBookIndex):
        result = index.lookup_biologic("adalimumab")
        assert result is not None
        # Reference product is 351(a), not the biosimilar
        assert result["bla_type"] == "351(a)"

    def test_biosimilar_count(self, index: PurpleBookIndex):
        result = index.lookup_biologic("adalimumab")
        assert result is not None
        assert result["biosimilar_count"] == 1  # adalimumab-atto

    def test_lookup_trastuzumab(self, index: PurpleBookIndex):
        result = index.lookup_biologic("trastuzumab")
        assert result is not None
        assert result["product_name"] == "Herceptin"
        assert result["bla_number"] == "103792"
        assert result["biosimilar_count"] == 0

    def test_substring_match_proper_name(self, index: PurpleBookIndex):
        result = index.lookup_biologic("adalimumab-atto")
        assert result is not None


class TestLoadPurpleBook:
    @pytest.fixture(autouse=True)
    def _reset_cache(self):
        reset_purple_book_cache()
        yield
        reset_purple_book_cache()

    async def test_load_real_csv(self, tmp_path):
        csv_file = tmp_path / "test_purple_book.csv"
        csv_file.write_text(SAMPLE_CSV, encoding="utf-8")
        index = await load_purple_book(csv_path=csv_file)
        assert index.product_count == 3

    async def test_load_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.csv"
        index = await load_purple_book(csv_path=missing)
        assert index.product_count == 0

    async def test_load_caches_result(self, tmp_path):
        csv_file = tmp_path / "test_purple_book.csv"
        csv_file.write_text(SAMPLE_CSV, encoding="utf-8")
        index1 = await load_purple_book(csv_path=csv_file)
        index2 = await load_purple_book(csv_path=csv_file)
        assert index1 is index2


class TestFetchPurpleBookData:
    """Tests for the HTTP-download path using mocked responses."""

    async def test_fetch_returns_list_of_dicts(self, httpx_mock):
        httpx_mock.add_response(
            url="https://purplebooksearch.fda.gov/files/2026/purplebook-search-march-data-download.csv",
            text=EXTENDED_CSV,
        )
        records = await fetch_purple_book_data(year=2026, month=3)
        assert isinstance(records, list)
        assert len(records) == 2

    async def test_fetch_snake_case_keys(self, httpx_mock):
        httpx_mock.add_response(
            url="https://purplebooksearch.fda.gov/files/2026/purplebook-search-march-data-download.csv",
            text=EXTENDED_CSV,
        )
        records = await fetch_purple_book_data(year=2026, month=3)
        assert records[0]["bla_number"] == "125057"
        assert "proper_name" in records[0]

    async def test_fetch_invalid_month(self):
        with pytest.raises(ValueError, match="month must be 1-12"):
            await fetch_purple_book_data(year=2026, month=13)

    async def test_fetch_invalid_month_zero(self):
        with pytest.raises(ValueError, match="month must be 1-12"):
            await fetch_purple_book_data(year=2026, month=0)

    async def test_fetch_url_uses_month_name(self, httpx_mock):
        # Month 1 -> "january"
        httpx_mock.add_response(
            url="https://purplebooksearch.fda.gov/files/2025/purplebook-search-january-data-download.csv",
            text=EXTENDED_CSV,
        )
        records = await fetch_purple_book_data(year=2025, month=1)
        assert isinstance(records, list)

    async def test_fetch_http_error_propagates(self, httpx_mock):
        import httpx

        httpx_mock.add_response(
            url="https://purplebooksearch.fda.gov/files/2026/purplebook-search-march-data-download.csv",
            status_code=404,
        )
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_purple_book_data(year=2026, month=3)

    async def test_fetch_no_patent_numbers(self, httpx_mock):
        httpx_mock.add_response(
            url="https://purplebooksearch.fda.gov/files/2026/purplebook-search-march-data-download.csv",
            text=EXTENDED_CSV,
        )
        records = await fetch_purple_book_data(year=2026, month=3)
        for record in records:
            assert "patent_number" not in record


class TestLookupBiologicExclusivity:
    """Tests for the exclusivity lookup helper (HTTP path)."""

    async def test_lookup_found(self, httpx_mock):
        httpx_mock.add_response(
            url="https://purplebooksearch.fda.gov/files/2026/purplebook-search-march-data-download.csv",
            text=EXTENDED_CSV,
        )
        result = await lookup_biologic_exclusivity("adalimumab", year=2026, month=3)
        assert result is not None
        assert result["bla_number"] == "125057"
        assert result["proper_name"] == "adalimumab"

    async def test_lookup_prefers_reference_product(self, httpx_mock):
        # EXTENDED_CSV has both 351(a) and 351(k) for adalimumab
        httpx_mock.add_response(
            url="https://purplebooksearch.fda.gov/files/2026/purplebook-search-march-data-download.csv",
            text=EXTENDED_CSV,
        )
        result = await lookup_biologic_exclusivity("adalimumab", year=2026, month=3)
        assert result is not None
        assert "351(a)" in result["bla_type"]

    async def test_lookup_returns_exclusivity_fields(self, httpx_mock):
        httpx_mock.add_response(
            url="https://purplebooksearch.fda.gov/files/2026/purplebook-search-march-data-download.csv",
            text=EXTENDED_CSV,
        )
        result = await lookup_biologic_exclusivity("adalimumab", year=2026, month=3)
        assert result is not None
        expected_keys = {
            "bla_number",
            "proper_name",
            "proprietary_name",
            "bla_type",
            "ref_product_exclusivity_expiry",
            "date_of_first_licensure",
            "exclusivity_expiration",
            "orphan_exclusivity_expiration",
        }
        assert expected_keys.issubset(set(result.keys()))

    async def test_lookup_not_found_returns_none(self, httpx_mock):
        httpx_mock.add_response(
            url="https://purplebooksearch.fda.gov/files/2026/purplebook-search-march-data-download.csv",
            text=EXTENDED_CSV,
        )
        result = await lookup_biologic_exclusivity("nonexistentmab", year=2026, month=3)
        assert result is None

    async def test_lookup_case_insensitive(self, httpx_mock):
        httpx_mock.add_response(
            url="https://purplebooksearch.fda.gov/files/2026/purplebook-search-march-data-download.csv",
            text=EXTENDED_CSV,
        )
        result = await lookup_biologic_exclusivity("ADALIMUMAB", year=2026, month=3)
        assert result is not None
        assert result["bla_number"] == "125057"


class TestRealPurpleBookCSV:
    """Integration tests against the real Purple Book CSV file."""

    @pytest.fixture(autouse=True)
    def _reset_cache(self):
        reset_purple_book_cache()
        yield
        reset_purple_book_cache()

    @pytest.fixture
    def real_csv_path(self):
        from pathlib import Path

        csv_path = (
            Path(__file__).resolve().parent.parent.parent
            / "validation"
            / "external-datasets"
            / "purple-book"
            / "purplebook-search-march-2026.csv"
        )
        if not csv_path.exists():
            pytest.skip("Real Purple Book CSV not available")
        return csv_path

    async def test_real_csv_loads(self, real_csv_path):
        index = await load_purple_book(csv_path=real_csv_path)
        assert index.product_count > 1000

    async def test_real_adalimumab(self, real_csv_path):
        index = await load_purple_book(csv_path=real_csv_path)
        result = index.lookup_biologic("adalimumab")
        assert result is not None
        assert result["bla_number"] == "125057"
        assert result["product_name"] == "Humira"
        assert result["biosimilar_count"] > 5

    async def test_real_trastuzumab(self, real_csv_path):
        index = await load_purple_book(csv_path=real_csv_path)
        result = index.lookup_biologic("trastuzumab")
        assert result is not None
        assert result["product_name"] == "Herceptin"

    async def test_real_rituximab(self, real_csv_path):
        index = await load_purple_book(csv_path=real_csv_path)
        result = index.lookup_biologic("rituximab")
        assert result is not None
        assert result["product_name"] == "Rituxan"

    async def test_real_humira_by_proprietary_name(self, real_csv_path):
        index = await load_purple_book(csv_path=real_csv_path)
        result = index.lookup_biologic("Humira")
        assert result is not None
        assert result["proper_name"] == "adalimumab"

    async def test_real_nonexistent_drug(self, real_csv_path):
        index = await load_purple_book(csv_path=real_csv_path)
        result = index.lookup_biologic("fakemab_xyz123")
        assert result is None
