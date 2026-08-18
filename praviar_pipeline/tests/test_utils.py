"""Tests for utility modules: dates, formatting, patent_ids."""

from __future__ import annotations

from datetime import date

from praviar_pipeline.utils.dates import parse_date
from praviar_pipeline.utils.patent_ids import (
    clean_patent_number_for_api,
    normalize_patent_id,
    strip_kind_code,
)

# ── Date parsing ──────────────────────────────────────────────────────


class TestParseDate:
    def test_iso_format(self):
        assert parse_date("2024-01-15") == date(2024, 1, 15)

    def test_slash_format(self):
        assert parse_date("2024/01/15") == date(2024, 1, 15)

    def test_yyyymmdd_compact(self):
        assert parse_date("20240115") == date(2024, 1, 15)

    def test_none_returns_none(self):
        assert parse_date(None) is None

    def test_empty_returns_none(self):
        assert parse_date("") is None

    def test_invalid_returns_none(self):
        assert parse_date("not-a-date") is None

    def test_date_passthrough(self):
        d = date(2024, 1, 15)
        assert parse_date(d) == d


# ── Patent ID normalization ───────────────────────────────────────────


class TestNormalizePatentId:
    """Option C semantics: kind codes collapse within tier, tiers are distinct."""

    def test_b2_collapses_to_b(self):
        assert normalize_patent_id("US7851188B2") == "US7851188B"

    def test_b1_collapses_to_b(self):
        assert normalize_patent_id("US6265190B1") == "US6265190B"

    def test_a1_application_collapses_to_a(self):
        assert normalize_patent_id("US20200123456A1") == "US20200123456A"

    def test_uppercase(self):
        assert normalize_patent_id("us7851188b2") == "US7851188B"

    def test_strips_punctuation(self):
        assert normalize_patent_id("US 7,851,188 B2") == "US7851188B"

    def test_bare_number_treated_as_b_tier(self):
        assert normalize_patent_id("US7851188") == "US7851188B"

    def test_ep_patent(self):
        assert normalize_patent_id("EP1234567B1") == "EP1234567B"

    def test_application_and_grant_are_distinct(self):
        """FTO correctness: application and grant must not share a dedup key."""
        assert normalize_patent_id("EP1234567A1") != normalize_patent_id("EP1234567B1")


class TestStripKindCode:
    def test_strips_b2(self):
        assert strip_kind_code("US7851188B2") == "US7851188"

    def test_no_kind_code(self):
        assert strip_kind_code("US7851188") == "US7851188"

    def test_strips_a1(self):
        assert strip_kind_code("US20200123456A1") == "US20200123456"


class TestCleanPatentNumberForApi:
    def test_strips_us_prefix_and_kind(self):
        assert clean_patent_number_for_api("US7851188B2") == "7851188"

    def test_strips_commas(self):
        assert clean_patent_number_for_api("US7,851,188B2") == "7851188"

    def test_non_us_keeps_prefix(self):
        assert clean_patent_number_for_api("EP1234567B1") == "EP1234567"


# ── Formatting ────────────────────────────────────────────────────────


class TestFormatCompoundContext:
    def test_includes_inchi_key(self, succinic_acid):
        from praviar_pipeline.utils.formatting import format_compound_context

        result = format_compound_context(succinic_acid)
        assert "KDYFGRWQOYBRFD-UHFFFAOYSA-N" in result

    def test_includes_name(self, succinic_acid):
        from praviar_pipeline.utils.formatting import format_compound_context

        result = format_compound_context(succinic_acid)
        assert "succinic acid" in result


class TestFormatPatentContext:
    def test_includes_title(self, sample_patent_hit):
        from praviar_pipeline.utils.formatting import format_patent_context

        result = format_patent_context(sample_patent_hit)
        assert "Methods for producing succinic acid" in result

    def test_truncation(self, sample_patent_hit):
        from praviar_pipeline.utils.formatting import format_patent_context

        result = format_patent_context(sample_patent_hit, max_abstract=10)
        # Should be truncated
        assert len(result) < 500

    def test_include_dates(self, sample_patent_hit):
        from praviar_pipeline.utils.formatting import format_patent_context

        result = format_patent_context(sample_patent_hit, include_dates=True)
        assert "2008" in result or "Filing" in result
