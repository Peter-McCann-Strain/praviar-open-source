"""Tests for praviar_pipeline.utils.dates — date parsing from various API formats."""

from datetime import date

from praviar_pipeline.utils.dates import parse_date


class TestParseDate:
    """Tests for parse_date()."""

    # ── ISO 8601 format ──────────────────────────────────────────────

    def test_iso_format(self):
        assert parse_date("2024-01-15") == date(2024, 1, 15)

    def test_iso_with_timezone_suffix_truncated(self):
        # Input > 10 chars is truncated to first 10
        assert parse_date("2024-01-15T12:00:00Z") == date(2024, 1, 15)

    def test_iso_leap_day(self):
        assert parse_date("2024-02-29") == date(2024, 2, 29)

    def test_iso_end_of_year(self):
        assert parse_date("2024-12-31") == date(2024, 12, 31)

    def test_iso_start_of_year(self):
        assert parse_date("2024-01-01") == date(2024, 1, 1)

    # ── Compact YYYYMMDD format ──────────────────────────────────────

    def test_compact_format(self):
        assert parse_date("20240115") == date(2024, 1, 15)

    def test_compact_leap_day(self):
        assert parse_date("20240229") == date(2024, 2, 29)

    # ── US slash MM/DD/YYYY format ───────────────────────────────────

    def test_us_slash_format(self):
        assert parse_date("01/15/2024") == date(2024, 1, 15)

    def test_us_slash_december(self):
        assert parse_date("12/25/2024") == date(2024, 12, 25)

    # ── YYYY/MM/DD format ────────────────────────────────────────────

    def test_yyyy_mm_dd_slash(self):
        assert parse_date("2024/01/15") == date(2024, 1, 15)

    # ── None / empty / invalid ───────────────────────────────────────

    def test_none_returns_none(self):
        assert parse_date(None) is None

    def test_empty_string_returns_none(self):
        assert parse_date("") is None

    def test_whitespace_only_returns_none(self):
        assert parse_date("   ") is None

    def test_garbage_returns_none(self):
        assert parse_date("not-a-date") is None

    def test_invalid_month_returns_none(self):
        assert parse_date("2024-13-01") is None

    def test_invalid_day_returns_none(self):
        assert parse_date("2024-01-32") is None

    def test_non_leap_feb_29_returns_none(self):
        assert parse_date("2023-02-29") is None

    # ── Edge cases ───────────────────────────────────────────────────

    def test_leading_trailing_whitespace_stripped(self):
        assert parse_date("  2024-01-15  ") == date(2024, 1, 15)

    def test_integer_input_coerced_to_string(self):
        # parse_date calls str(date_str) so int should work for compact
        assert parse_date(20240115) == date(2024, 1, 15)

    def test_iso_with_extra_chars_beyond_10(self):
        # Truncation to 10 chars means "2024-01-15EXTRA" → "2024-01-15"
        assert parse_date("2024-01-15EXTRA") == date(2024, 1, 15)
