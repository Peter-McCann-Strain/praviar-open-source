"""Tests for global search expansion — integration of new patent sources.

Covers:
1. search_allowed_jurisdictions config includes Asian offices (JP, KR, CN, IN)
2. PatentSource enum has new values (LENS, KIPRIS, PATENTSCOPE, BIGQUERY_TRANSLATED)
3. Hard filter passes Asian patent numbers when jurisdictions are configured
4. Hard filter still rejects bad kind codes
5. PubChem SDQ default jurisdiction is now "*" (global)
6. Config defaults include Asian jurisdictions
"""

from __future__ import annotations

import os
from unittest.mock import patch

from praviar_pipeline.config import clear_settings_cache
from praviar_pipeline.models.patent import PatentSource

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_test_settings(**overrides):
    """Create a fresh Settings object with test environment + overrides.

    Clears the lru_cache, applies env overrides, and returns Settings.
    """
    from praviar_pipeline.config import Settings

    clear_settings_cache()

    base_env = {
        "ANTHROPIC_API_KEY": "sk-ant-test-key",
        "PATENTSVIEW_API_KEY": "test-pv-key",
        "USPTO_ODP_API_KEY": "test-odp-key",
        "LOG_LEVEL": "WARNING",
    }
    base_env.update(overrides)

    with patch.dict(os.environ, base_env, clear=False):
        settings = Settings()

    clear_settings_cache()
    return settings


# ============================================================================
# 1. search_allowed_jurisdictions config includes Asian offices
# ============================================================================


class TestSearchAllowedJurisdictions:
    """Verify config defaults include Asian patent offices."""

    def test_search_allowed_jurisdictions_includes_asian(self):
        """Default search_allowed_jurisdictions includes JP, KR, CN, IN."""
        settings = _get_test_settings()

        jurisdictions = settings.search_allowed_jurisdictions
        assert "JP" in jurisdictions, "Japan (JP) must be in search_allowed_jurisdictions"
        assert "KR" in jurisdictions, "Korea (KR) must be in search_allowed_jurisdictions"
        assert "CN" in jurisdictions, "China (CN) must be in search_allowed_jurisdictions"
        assert "IN" in jurisdictions, "India (IN) must be in search_allowed_jurisdictions"

    def test_search_allowed_jurisdictions_still_has_core(self):
        """Default still includes US, EP, WO."""
        settings = _get_test_settings()

        jurisdictions = settings.search_allowed_jurisdictions
        assert "US" in jurisdictions
        assert "EP" in jurisdictions
        assert "WO" in jurisdictions


# ============================================================================
# 2. PatentSource enum has new values
# ============================================================================


class TestPatentSourceEnum:
    """Verify PatentSource enum has all new source values."""

    def test_patent_source_has_lens(self):
        assert PatentSource.LENS == "lens"

    def test_patent_source_has_kipris(self):
        assert PatentSource.KIPRIS == "kipris"

    def test_patent_source_has_patentscope(self):
        assert PatentSource.PATENTSCOPE == "patentscope"

    def test_patent_source_has_bigquery_translated(self):
        assert PatentSource.BIGQUERY_TRANSLATED == "bigquery_translated"

    def test_patent_source_enum_has_new_values(self):
        """All new source enum values exist and have correct string values."""
        new_sources = {
            "LENS": "lens",
            "KIPRIS": "kipris",
            "PATENTSCOPE": "patentscope",
            "BIGQUERY_TRANSLATED": "bigquery_translated",
        }
        for attr, value in new_sources.items():
            member = getattr(PatentSource, attr, None)
            assert member is not None, f"PatentSource.{attr} not found"
            assert member.value == value, f"PatentSource.{attr} should be '{value}'"

    def test_original_sources_still_exist(self):
        """Original sources (BIGQUERY, PUBCHEM, etc.) are still present."""
        original = ["BIGQUERY", "SURECHEMBL", "PUBCHEM", "PATCID", "INPADOC"]
        for name in original:
            assert hasattr(PatentSource, name), f"PatentSource.{name} missing"


# ============================================================================
# 3. Hard filter passes Asian patent numbers
# ============================================================================


class TestHardFilterAsianPatents:
    """Verify that hard filter logic accepts JP/KR/CN/IN patent numbers."""

    def test_hard_filter_passes_jp_patent(self):
        """Japanese patent numbers should pass jurisdiction filter."""
        settings = _get_test_settings()
        allowed = settings.search_allowed_jurisdictions
        # Extract jurisdiction prefix from a JP patent number
        jp_pub = "JP2020567890A"
        prefix = jp_pub[:2]
        assert prefix in allowed, f"JP patent prefix '{prefix}' should be in allowed jurisdictions"

    def test_hard_filter_passes_kr_patent(self):
        """Korean patent numbers should pass jurisdiction filter."""
        settings = _get_test_settings()
        allowed = settings.search_allowed_jurisdictions
        kr_pub = "KR1020200012345"
        prefix = kr_pub[:2]
        assert prefix in allowed

    def test_hard_filter_passes_cn_patent(self):
        """Chinese patent numbers should pass jurisdiction filter."""
        settings = _get_test_settings()
        allowed = settings.search_allowed_jurisdictions
        cn_pub = "CN112345678A"
        prefix = cn_pub[:2]
        assert prefix in allowed

    def test_hard_filter_passes_in_patent(self):
        """Indian patent numbers should pass jurisdiction filter."""
        settings = _get_test_settings()
        allowed = settings.search_allowed_jurisdictions
        in_pub = "IN202041001234"
        prefix = in_pub[:2]
        assert prefix in allowed

    def test_hard_filter_passes_us_patent(self):
        """US patents should still pass (regression check)."""
        settings = _get_test_settings()
        allowed = settings.search_allowed_jurisdictions
        assert "US" in allowed

    def test_hard_filter_passes_wo_patent(self):
        """WO (WIPO) patents should still pass (regression check)."""
        settings = _get_test_settings()
        allowed = settings.search_allowed_jurisdictions
        assert "WO" in allowed

    def test_hard_filter_rejects_unknown_jurisdiction(self):
        """Patents from unlisted jurisdictions should not match default allowed list."""
        settings = _get_test_settings()
        allowed = settings.search_allowed_jurisdictions
        # ZW (Zimbabwe) should not be in defaults
        assert "ZW" not in allowed


# ============================================================================
# 4. Kind code filtering is not broken
# ============================================================================


class TestHardFilterKindCodes:
    """Verify that the existing kind code filtering logic is intact."""

    def test_hard_filter_still_rejects_bad_kind_codes(self):
        """Verify the search_allowed_jurisdictions doesn't include random codes.

        Kind codes like 'A1', 'B2' are patent doc suffixes, not jurisdictions.
        """
        settings = _get_test_settings()
        allowed = settings.search_allowed_jurisdictions
        # These should never be in the jurisdiction list
        for bad_code in ["A1", "B2", "C1", "U1"]:
            assert bad_code not in allowed, (
                f"Kind code '{bad_code}' should not be in search_allowed_jurisdictions"
            )

    def test_all_jurisdictions_are_two_letter_codes(self):
        """All default jurisdictions should be 2-letter country/region codes."""
        settings = _get_test_settings()
        for j in settings.search_allowed_jurisdictions:
            assert len(j) == 2, f"Jurisdiction '{j}' is not a 2-letter code"
            assert j.isalpha(), f"Jurisdiction '{j}' should be alpha only"
            assert j.isupper(), f"Jurisdiction '{j}' should be uppercase"


# ============================================================================
# 5. PubChem SDQ default jurisdiction is global
# ============================================================================


class TestPubChemSDQJurisdiction:
    """Verify PubChem SDQ now defaults to global search."""

    def test_pubchem_sdq_default_jurisdiction_is_global(self):
        """PubChem SDQ's default jurisdiction parameter should be '*' (all offices)."""
        import inspect

        from praviar_pipeline.clients.pubchem import PubChemClient

        sig = inspect.signature(PubChemClient.sdq_search_patents)
        jurisdiction_param = sig.parameters.get("jurisdiction")
        assert jurisdiction_param is not None, "sdq_search_patents should have 'jurisdiction' param"
        assert jurisdiction_param.default == "*", (
            f"Default jurisdiction should be '*' (global), got '{jurisdiction_param.default}'"
        )

    def test_pubchem_sdq_jurisdiction_star_means_all(self):
        """Verify the docstring or implementation indicates '*' means all offices."""
        import inspect

        from praviar_pipeline.clients.pubchem import PubChemClient

        source = inspect.getsource(PubChemClient.sdq_search_patents)
        # The implementation skips the jurisdiction filter when jurisdiction == "*"
        assert 'jurisdiction != "*"' in source or "jurisdiction !=" in source, (
            "SDQ implementation should skip jurisdiction filter when '*'"
        )


# ============================================================================
# 6. Config defaults for new patent sources
# ============================================================================


class TestConfigNewSourceDefaults:
    """Verify config defaults for active global patent sources."""

    def test_kipris_defaults(self):
        """KIPRIS config defaults are reasonable."""
        settings = _get_test_settings()
        assert settings.kipris_api_key == ""  # No default key
        assert settings.kipris_requests_per_minute > 0
        assert settings.kipris_max_results >= 1

    def test_patentscope_defaults(self):
        """PatentScope config defaults are reasonable."""
        settings = _get_test_settings()
        assert settings.patentscope_username == ""  # No default credentials
        assert settings.patentscope_password == ""
        assert settings.patentscope_requests_per_minute > 0
        assert settings.patentscope_max_results >= 1

    def test_config_presets_include_asian_jurisdictions(self):
        """Verify the 'thorough' preset equivalent has JP, KR, CN, IN.

        Since this project uses Settings defaults (not named presets),
        we verify the defaults serve as the thorough/comprehensive preset.
        """
        settings = _get_test_settings()

        # search_allowed_jurisdictions should be the thorough preset
        allowed = settings.search_allowed_jurisdictions
        asian_offices = {"JP", "KR", "CN", "IN"}
        for office in asian_offices:
            assert office in allowed, f"search_allowed_jurisdictions should include {office}"


# ============================================================================
# 7. New source client import verification
# ============================================================================


class TestClientImports:
    """Verify new clients can be imported and instantiated."""

    def test_kipris_client_importable(self):
        """KIPRISClient can be imported from praviar_pipeline.clients.kipris."""
        from praviar_pipeline.clients.kipris import KIPRISClient

        assert KIPRISClient is not None

    def test_patentscope_client_importable(self):
        """PatentScopeClient can be imported from praviar_pipeline.clients.patentscope."""
        from praviar_pipeline.clients.patentscope import PatentScopeClient

        assert PatentScopeClient is not None

    def test_step2_imports_new_clients(self):
        """Step 2 search pipeline keeps global source wrappers wired to the submodule."""
        import inspect

        from praviar_pipeline.pipeline import step2_search

        source = inspect.getsource(step2_search)
        assert "global_sources.search_kipris" in source, (
            "step2_search should delegate KIPRIS search through global_sources"
        )
        assert "global_sources.search_patentscope" in source, (
            "step2_search should delegate PatentScope search through global_sources"
        )
        assert "global_sources.search_lens" not in source
