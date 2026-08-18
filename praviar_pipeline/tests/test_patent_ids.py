"""Tests for praviar_pipeline.utils.patent_ids — patent ID normalization."""

import pytest

from praviar_pipeline.utils.patent_ids import (
    clean_patent_number_for_api,
    normalize_patent_id,
    publication_jurisdiction,
    strip_kind_code,
)


class TestNormalizePatentId:
    """Tests for normalize_patent_id().

    Option C semantics: kind codes are collapsed *within* tier so that minor
    variants of the same document deduplicate (A1/A2→A, B1/B2→B, C1/C2→C),
    but the application/grant boundary is preserved (A-tier ≠ B-tier).
    """

    # --- basic normalisation ---

    def test_already_normalized_no_kind_code(self):
        # No kind code → treated as B-tier (common for older granted patents).
        assert normalize_patent_id("US7851188") == "US7851188B"

    def test_b2_kind_code_collapses_to_b(self):
        assert normalize_patent_id("US7851188B2") == "US7851188B"

    def test_b1_kind_code_collapses_to_b(self):
        assert normalize_patent_id("US7851188B1") == "US7851188B"

    def test_a1_kind_code_collapses_to_a(self):
        assert normalize_patent_id("US20200123456A1") == "US20200123456A"

    def test_a2_kind_code_collapses_to_a(self):
        assert normalize_patent_id("US20200123456A2") == "US20200123456A"

    def test_ep_b1_collapses_to_b(self):
        assert normalize_patent_id("EP2000000B1") == "EP2000000B"

    def test_c1_kind_code_collapses_to_c(self):
        assert normalize_patent_id("US1234567C1") == "US1234567C"

    def test_c2_kind_code_collapses_to_c(self):
        assert normalize_patent_id("US1234567C2") == "US1234567C"

    # --- FTO correctness: A-tier and B-tier must NOT deduplicate ---

    def test_application_and_grant_distinct(self):
        """Core FTO correctness: A1 and B1 of the same family must not share a dedup key."""
        a_key = normalize_patent_id("EP1234567A1")
        b_key = normalize_patent_id("EP1234567B1")
        assert a_key != b_key, (
            "EP1234567A1 (application) and EP1234567B1 (grant) must produce "
            "different dedup keys for FTO correctness"
        )

    def test_a1_and_a2_deduplicate(self):
        """Within the same tier, A1 and A2 should share a dedup key."""
        assert normalize_patent_id("EP1234567A1") == normalize_patent_id("EP1234567A2")

    def test_b1_and_b2_deduplicate(self):
        """Within the same tier, B1 and B2 should share a dedup key."""
        assert normalize_patent_id("EP1234567B1") == normalize_patent_id("EP1234567B2")

    def test_no_kind_code_deduplicates_with_b1(self):
        """A bare number (no kind code) is treated as B-tier and deduplicates with B1."""
        assert normalize_patent_id("US7851188") == normalize_patent_id("US7851188B1")

    # --- formatting / punctuation ---

    def test_uppercase_conversion(self):
        assert normalize_patent_id("us7851188b2") == "US7851188B"

    def test_removes_commas(self):
        assert normalize_patent_id("US7,851,188") == "US7851188B"

    def test_removes_spaces(self):
        assert normalize_patent_id("US 7851188 B2") == "US7851188B"

    def test_removes_hyphens(self):
        assert normalize_patent_id("EP-2000000-B1") == "EP2000000B"

    def test_combined_punctuation(self):
        assert normalize_patent_id("US 7,851-188 B2") == "US7851188B"

    # --- country prefixes ---

    def test_wo_patent_application(self):
        assert normalize_patent_id("WO2024000001A1") == "WO2024000001A"

    def test_jp_patent_application(self):
        assert normalize_patent_id("JP2024000001A") == "JP2024000001A"

    def test_cn_patent_grant(self):
        assert normalize_patent_id("CN115000001B") == "CN115000001B"

    # --- edge cases ---

    def test_empty_string(self):
        assert normalize_patent_id("") == "B"

    def test_no_country_prefix_b2(self):
        assert normalize_patent_id("7851188B2") == "7851188B"

    def test_no_country_prefix_a1(self):
        assert normalize_patent_id("7851188A1") == "7851188A"

    # --- non-standard kind codes kept verbatim ---

    def test_e_kind_code_kept_verbatim(self):
        # E (reissue) is not A/B/C tier — kept as-is.
        assert normalize_patent_id("US1234567E") == "US1234567E"

    def test_s_kind_code_kept_verbatim(self):
        # S (design) is kept as-is.
        assert normalize_patent_id("US1234567S") == "US1234567S"

    def test_h_kind_code_kept_verbatim(self):
        # H (statutory invention registration) is kept as-is.
        assert normalize_patent_id("US1234567H") == "US1234567H"


class TestStripKindCode:
    """Tests for strip_kind_code() — unchanged semantics, still strips entirely."""

    def test_strips_b2(self):
        assert strip_kind_code("US7851188B2") == "US7851188"

    def test_strips_a1(self):
        assert strip_kind_code("US20200123456A1") == "US20200123456"

    def test_no_kind_code(self):
        assert strip_kind_code("US7851188") == "US7851188"

    def test_preserves_hyphens(self):
        # strip_kind_code only strips the code, preserves rest
        assert strip_kind_code("EP-2000000-B1") == "EP-2000000-"

    def test_strips_whitespace(self):
        assert strip_kind_code("  US7851188B2  ") == "US7851188"

    def test_strips_s_kind_code(self):
        assert strip_kind_code("US1234567S") == "US1234567"

    def test_strips_p1_kind_code(self):
        assert strip_kind_code("US1234567P1") == "US1234567"

    def test_strips_h_kind_code(self):
        assert strip_kind_code("US1234567H") == "US1234567"


class TestCleanPatentNumberForApi:
    """Tests for clean_patent_number_for_api() — unchanged semantics, strips entirely."""

    def test_removes_us_prefix_and_kind_code(self):
        assert clean_patent_number_for_api("US7851188B2") == "7851188"

    def test_removes_us_prefix_application(self):
        assert clean_patent_number_for_api("US20200123456A1") == "20200123456"

    def test_lowercase_input(self):
        assert clean_patent_number_for_api("us7851188b2") == "7851188"

    def test_no_us_prefix(self):
        assert clean_patent_number_for_api("7851188B2") == "7851188"

    def test_ep_prefix_preserved(self):
        # EP prefix is not stripped — only US is
        assert clean_patent_number_for_api("EP2000000B1") == "EP2000000"

    def test_removes_commas_and_spaces(self):
        assert clean_patent_number_for_api("US 7,851,188 B2") == "7851188"

    def test_empty_string(self):
        assert clean_patent_number_for_api("") == ""


class TestPublicationJurisdiction:
    @pytest.mark.parametrize(
        ("patent_id", "expected"),
        [
            ("AT123456A1", "AT"),
            ("AU2020123456A1", "AU"),
            ("BE123456A1", "BE"),
            ("BR10201234567A2", "BR"),
            ("CA1234567A1", "CA"),
            ("CH123456A1", "CH"),
            ("CN115000001B", "CN"),
            ("CZ123456A3", "CZ"),
            ("DE102012345678A1", "DE"),
            ("DK123456A1", "DK"),
            ("EA123456A1", "EA"),
            ("EP1234567B1", "EP"),
            ("ES1234567A1", "ES"),
            ("FI123456A1", "FI"),
            ("FR1234567A1", "FR"),
            ("GB1234567B", "GB"),
            ("GR123456A1", "GR"),
            ("HK1234567A1", "HK"),
            ("HU123456A1", "HU"),
            ("IE123456A1", "IE"),
            ("IL123456A", "IL"),
            ("IN202011012345A", "IN"),
            ("IT102020123456A1", "IT"),
            ("JPH06123456A", "JP"),
            ("KR1020201234567A", "KR"),
            ("MX2020012345A1", "MX"),
            ("MY2020012345A", "MY"),
            ("NL1234567C", "NL"),
            ("NO123456A1", "NO"),
            ("NZ123456A", "NZ"),
            ("PL123456A1", "PL"),
            ("PT123456A", "PT"),
            ("RU20201234567A", "RU"),
            ("SE123456A1", "SE"),
            ("SG2020012345A1", "SG"),
            ("SK123456A3", "SK"),
            ("TR2020012345A1", "TR"),
            ("TW2020123456A", "TW"),
            ("US20240123456A1", "US"),
            ("WO2024123456A1", "WO"),
            ("ZA2020012345A", "ZA"),
        ],
    )
    def test_every_supported_office_has_a_valid_application_and_kind_shape(
        self,
        patent_id: str,
        expected: str,
    ) -> None:
        assert publication_jurisdiction(patent_id) == expected

    @pytest.mark.parametrize(
        ("patent_id", "expected"),
        [
            ("US20240123456A1", "US"),
            ("US D123456 S1", "US"),
            ("USRE12345E", "US"),
            ("EP1234567B1", "EP"),
            ("WO2024123456A1", "WO"),
            ("JPH06123456A", "JP"),
            ("CN115000001B", "CN"),
        ],
    )
    def test_supported_publication_formats(self, patent_id: str, expected: str) -> None:
        assert publication_jurisdiction(patent_id) == expected

    @pytest.mark.parametrize(
        "patent_id",
        ["PCT/US2024/012345", "XX1234567A1", "US-not-a-publication", "12345678"],
    )
    def test_rejects_unknown_or_nonpublication_identifiers(self, patent_id: str) -> None:
        with pytest.raises(ValueError, match="unsupported"):
            publication_jurisdiction(patent_id)

    @pytest.mark.parametrize(
        "patent_id",
        [
            "EP-not-a-publication1",
            "WOHELLO1",
            "CNABCDEF1",
            "JPZZZZZ1",
            "KRnotapatent9",
        ],
    )
    def test_rejects_allowlisted_office_with_nonpublication_body(self, patent_id: str) -> None:
        with pytest.raises(ValueError, match="unsupported"):
            publication_jurisdiction(patent_id)

    @pytest.mark.parametrize(
        "patent_id",
        [
            "AT123456Z9",
            "AU2020123456Z9",
            "BE123456Z9",
            "BR10201234567Z9",
            "CA1234567Z9",
            "CH123456Z9",
            "CN115000001Z9",
            "CZ123456Z9",
            "DE102012345678Z9",
            "DK123456Z9",
            "EA123456Z9",
            "EP1234567Z9",
            "ES1234567Z9",
            "FI123456Z9",
            "FR1234567Z9",
            "GB1234567Z9",
            "GR123456Z9",
            "HK1234567Z9",
            "HU123456Z9",
            "IE123456Z9",
            "IL123456Z9",
            "IN202011012345Z9",
            "IT102020123456Z9",
            "JPH06123456Z9",
            "KR1020201234567Z9",
            "MX2020012345Z9",
            "MY2020012345Z9",
            "NL1234567Z9",
            "NO123456Z9",
            "NZ123456Z9",
            "PL123456Z9",
            "PT123456Z9",
            "RU20201234567Z9",
            "SE123456Z9",
            "SG2020012345Z9",
            "SK123456Z9",
            "TR2020012345Z9",
            "TW2020123456Z9",
            "US20240123456Z9",
            "WO2024123456Z9",
            "ZA2020012345Z9",
        ],
    )
    def test_every_supported_office_rejects_unallowlisted_kind_code(
        self,
        patent_id: str,
    ) -> None:
        with pytest.raises(ValueError, match="unsupported"):
            publication_jurisdiction(patent_id)

    @pytest.mark.parametrize(
        "patent_id",
        [
            "EP12345A1",
            "CN12345A",
            "KR12345A",
            "WO202412345A1",
            "WO1900123456A1",
            "JPH99123456A",
        ],
    )
    def test_rejects_office_specific_too_short_document_numbers(
        self,
        patent_id: str,
    ) -> None:
        with pytest.raises(ValueError, match="unsupported"):
            publication_jurisdiction(patent_id)
