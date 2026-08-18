"""Tests for Fix 2: EPO OPS patent ID DOCDB format conversion.

The regex now handles both compact (US7851188B2) and hyphenated (US-2024294466-A1)
patent ID formats, which is critical for EPO OPS enrichment to succeed.
"""

from __future__ import annotations

from praviar_pipeline.clients.epo_ops import _to_docdb_format


class TestDocdbFormatCompact:
    """Standard compact patent IDs (the original working case)."""

    def test_us_granted(self):
        assert _to_docdb_format("US7851188B2") == "US.7851188.B2"

    def test_us_application(self):
        assert _to_docdb_format("US20240294466A1") == "US.20240294466.A1"

    def test_ep_patent(self):
        assert _to_docdb_format("EP1234567A1") == "EP.1234567.A1"

    def test_wo_application(self):
        assert _to_docdb_format("WO2024123456A1") == "WO.2024123456.A1"

    def test_jp_patent(self):
        assert _to_docdb_format("JP6789012B2") == "JP.6789012.B2"

    def test_cn_patent(self):
        assert _to_docdb_format("CN112345678A") == "CN.112345678.A"

    def test_kind_code_single_letter(self):
        assert _to_docdb_format("EP3456789A") == "EP.3456789.A"


class TestDocdbFormatHyphenated:
    """Hyphenated format from PubChem/BigQuery (US-2024294466-A1).

    This was the root cause of 0 EPO enrichment — 200 patents silently
    failed DOCDB conversion because the old regex couldn't handle hyphens.
    """

    def test_us_hyphenated_application(self):
        assert _to_docdb_format("US-2024294466-A1") == "US.2024294466.A1"

    def test_us_hyphenated_granted(self):
        assert _to_docdb_format("US-7851188-B2") == "US.7851188.B2"

    def test_ep_hyphenated(self):
        assert _to_docdb_format("EP-1234567-A1") == "EP.1234567.A1"

    def test_wo_hyphenated(self):
        assert _to_docdb_format("WO-2024123456-A1") == "WO.2024123456.A1"

    def test_cn_hyphenated(self):
        assert _to_docdb_format("CN-112345678-A") == "CN.112345678.A"


class TestDocdbFormatEdgeCases:
    """Edge cases and passthrough behavior."""

    def test_whitespace_stripped(self):
        assert _to_docdb_format("  US7851188B2  ") == "US.7851188.B2"

    def test_already_docdb_format(self):
        """If already in DOCDB format, passthrough."""
        result = _to_docdb_format("US.7851188.B2")
        # Should not match regex, passes through
        assert result == "US.7851188.B2"

    def test_plain_unknown_passthrough(self):
        assert _to_docdb_format("unknown") == "unknown"

    def test_empty_string(self):
        assert _to_docdb_format("") == ""

    def test_real_semaglutide_patent_ids(self):
        """Real patent IDs from the semaglutide pipeline run that failed."""
        # These all come from PubChem SDQ in hyphenated format
        test_cases = [
            ("US-2025074964-A1", "US.2025074964.A1"),
            ("US-2023023012-A1", "US.2023023012.A1"),
            ("US-2024294466-A1", "US.2024294466.A1"),
            ("US-2023295077-A1", "US.2023295077.A1"),
        ]
        for patent_id, expected_docdb in test_cases:
            result = _to_docdb_format(patent_id)
            assert result == expected_docdb, f"{patent_id} → {result}, expected {expected_docdb}"
