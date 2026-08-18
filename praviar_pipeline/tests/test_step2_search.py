"""Tests for Step 2: Patent Search — mock all external APIs."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from praviar_pipeline.config import clear_settings_cache
from praviar_pipeline.errors import AllSourcesFailedError, SearchSourceFailedError
from praviar_pipeline.models.patent import PatentSource


@pytest.fixture(autouse=True)
def _mock_global_sources():
    """Auto-mock global search sources and enrichment functions.

    These are always called in search_patents and need mocking to avoid real API calls.
    """
    with (
        patch(
            "praviar_pipeline.pipeline.step2_search._search_kipris",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "praviar_pipeline.pipeline.step2_search._search_patentscope",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "praviar_pipeline.pipeline.step2_search._search_bigquery_translated",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "praviar_pipeline.pipeline.step2_search._search_patentsview",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "praviar_pipeline.pipeline.step2_search._search_pubchem_similar",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "praviar_pipeline.pipeline.step2_search._search_pubchem_genus",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "praviar_pipeline.pipeline.step2_search._enrich_legal_status",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "praviar_pipeline.pipeline.step2_search._expand_families",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "praviar_pipeline.pipeline.step2_search._enrich_patent_term",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "praviar_pipeline.pipeline.step2_search._enrich_application_data",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "praviar_pipeline.pipeline.step2_search._enrich_epo_register",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "praviar_pipeline.pipeline.step2_search._enrich_ptab_proceedings",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "praviar_pipeline.pipeline.step2_search._enrich_orange_book",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch(
            "praviar_pipeline.pipeline.step2_search._expand_continuations",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        yield


def _make_sdq_patent(pub_num: str, title: str = "", **kwargs) -> dict:
    """Helper to create a minimal SDQ result dict."""
    pat = {"publicationnumber": pub_num, "title": title}
    pat.update(kwargs)
    return pat


class TestSearchPatents:
    async def test_search_with_sdq_and_ranking(self, succinic_acid, mock_settings):
        """SDQ results should be ranked and converted to PatentHit objects."""
        from praviar_pipeline.pipeline.step2_search import search_patents

        sdq_results = [
            _make_sdq_patent("US7851188B2", "Methods for producing succinic acid"),
            _make_sdq_patent("US6265190B1", "Succinic acid production"),
        ]
        surechembl_results = [("US7851188B2", PatentSource.SURECHEMBL)]

        # rank_patents returns the SDQ dicts it receives (identity for this test)
        with (
            patch(
                "praviar_pipeline.pipeline.step2_search._search_pubchem_sdq",
                new_callable=AsyncMock,
                return_value=sdq_results,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_surechembl",
                new_callable=AsyncMock,
                return_value=surechembl_results,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_annotations",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_patcid",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search.rank_patents",
                return_value=sdq_results,
            ),
        ):
            hits, health, _funnel = await search_patents(succinic_acid)

        patent_ids = {h.patent_id for h in hits}
        assert "US7851188B2" in patent_ids
        assert "US6265190B1" in patent_ids

        # US7851188B2 found by both PubChem and SureChEMBL → higher confidence
        for h in hits:
            if h.patent_id == "US7851188B2":
                assert h.confidence_score >= 0.6
                assert PatentSource.PUBCHEM in h.sources
                assert PatentSource.SURECHEMBL in h.sources

        # Source health should track all sources as OK
        assert health.primary_succeeded
        assert not health.any_failed

    async def test_search_passes_multi_source_ids_to_ranking(self, succinic_acid, mock_settings):
        """Multi-source IDs should be passed to rank_patents."""
        from praviar_pipeline.pipeline.step2_search import search_patents

        sdq_results = [_make_sdq_patent("US1234567B2")]
        surechembl_results = [("US1234567B2", PatentSource.SURECHEMBL)]
        patcid_results = [("US7777777B1", PatentSource.PATCID)]
        bigquery_rows = [{"publication_number": "US9999999B2", "title": "BQ patent"}]

        captured_kwargs = {}

        def mock_rank(sdq, compound, multi_source_ids=None, max_results=None, collect_audit=False):
            captured_kwargs["multi_source_ids"] = multi_source_ids
            return sdq

        with (
            patch(
                "praviar_pipeline.pipeline.step2_search._search_pubchem_sdq",
                new_callable=AsyncMock,
                return_value=sdq_results,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_surechembl",
                new_callable=AsyncMock,
                return_value=surechembl_results,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery",
                new_callable=AsyncMock,
                return_value=bigquery_rows,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_annotations",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_patcid",
                new_callable=AsyncMock,
                return_value=patcid_results,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search.rank_patents",
                side_effect=mock_rank,
            ),
        ):
            await search_patents(succinic_acid)

        ids = captured_kwargs["multi_source_ids"]
        assert len(ids) >= 3  # SureChEMBL, PatCID, BigQuery each contributed one

    async def test_search_includes_bigquery_only_patents(self, succinic_acid, mock_settings):
        """Patents found only by BigQuery (not in SDQ) should be supplemented."""
        from praviar_pipeline.pipeline.step2_search import search_patents

        sdq_results = [_make_sdq_patent("US1111111B2")]
        bigquery_rows = [
            {"publication_number": "US2222222B1", "title": "BQ-only patent", "abstract": "..."},
        ]

        with (
            patch(
                "praviar_pipeline.pipeline.step2_search._search_pubchem_sdq",
                new_callable=AsyncMock,
                return_value=sdq_results,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_surechembl",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery",
                new_callable=AsyncMock,
                return_value=bigquery_rows,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_annotations",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_patcid",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search.rank_patents",
                return_value=sdq_results,
            ),
        ):
            hits, _health, _funnel = await search_patents(succinic_acid)

        patent_ids = {h.patent_id for h in hits}
        assert "US1111111B2" in patent_ids  # From SDQ
        assert "US2222222B1" in patent_ids  # Supplemented from BigQuery

    async def test_search_empty(self, succinic_acid, mock_settings):
        """All sources returning empty should yield empty results (not raise)."""
        from praviar_pipeline.pipeline.step2_search import search_patents

        with (
            patch(
                "praviar_pipeline.pipeline.step2_search._search_pubchem_sdq",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_surechembl",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_annotations",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_patcid",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search.rank_patents",
                return_value=[],
            ),
        ):
            hits, health, _funnel = await search_patents(succinic_acid)

        assert hits == []
        assert not health.all_failed  # Empty is OK, not FAILED

    async def test_search_fails_closed_when_sdq_raises_under_fail_fast(
        self, succinic_acid, mock_settings, monkeypatch
    ):
        """Fail-fast policy preserves strict required-source behavior."""
        from praviar_pipeline.pipeline.step2_search import search_patents

        monkeypatch.setenv("SOURCE_FAILURE_POLICY", "fail_fast")
        clear_settings_cache()

        bigquery_rows = [{"publication_number": "US3333333B1", "title": "Fallback patent"}]

        try:
            with (
                patch(
                    "praviar_pipeline.pipeline.step2_search._search_pubchem_sdq",
                    new_callable=AsyncMock,
                    side_effect=RuntimeError("SDQ down"),
                ),
                patch(
                    "praviar_pipeline.pipeline.step2_search._search_surechembl",
                    new_callable=AsyncMock,
                    return_value=[],
                ),
                patch(
                    "praviar_pipeline.pipeline.step2_search._search_bigquery",
                    new_callable=AsyncMock,
                    return_value=bigquery_rows,
                ),
                patch(
                    "praviar_pipeline.pipeline.step2_search._search_bigquery_annotations",
                    new_callable=AsyncMock,
                    return_value=[],
                ),
                patch(
                    "praviar_pipeline.pipeline.step2_search._search_patcid",
                    new_callable=AsyncMock,
                    return_value=[],
                ),
                patch(
                    "praviar_pipeline.pipeline.step2_search.rank_patents",
                    return_value=[],
                ),
                pytest.raises(SearchSourceFailedError),
            ):
                await search_patents(succinic_acid)
        finally:
            clear_settings_cache()

    async def test_all_sources_fail_raises(self, succinic_acid, mock_settings):
        """If every search source fails, AllSourcesFailedError should be raised."""
        from praviar_pipeline.pipeline.step2_search import search_patents

        with (
            patch(
                "praviar_pipeline.pipeline.step2_search._search_pubchem_sdq",
                new_callable=AsyncMock,
                side_effect=RuntimeError("SDQ down"),
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_surechembl",
                new_callable=AsyncMock,
                side_effect=RuntimeError("SureChEMBL down"),
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery",
                new_callable=AsyncMock,
                side_effect=RuntimeError("BigQuery down"),
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_annotations",
                new_callable=AsyncMock,
                side_effect=RuntimeError("BQ annotations down"),
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_patcid",
                new_callable=AsyncMock,
                side_effect=RuntimeError("PatCID down"),
            ),
            # All scheduled global sources must also fail for AllSourcesFailedError
            patch(
                "praviar_pipeline.pipeline.step2_search._search_kipris",
                new_callable=AsyncMock,
                side_effect=RuntimeError("KIPRIS down"),
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_patentscope",
                new_callable=AsyncMock,
                side_effect=RuntimeError("PatentScope down"),
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_translated",
                new_callable=AsyncMock,
                side_effect=RuntimeError("BQ translated down"),
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_patentsview",
                new_callable=AsyncMock,
                side_effect=RuntimeError("PatentsView down"),
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_pubchem_similar",
                new_callable=AsyncMock,
                side_effect=RuntimeError("PubChem similar down"),
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_pubchem_genus",
                new_callable=AsyncMock,
                side_effect=RuntimeError("PubChem genus down"),
            ),
            pytest.raises(AllSourcesFailedError),
        ):
            await search_patents(succinic_acid)


class TestNormalizePatentId:
    """Option C semantics: kind codes collapse within tier, tiers are distinct."""

    def test_collapses_kind_codes_within_tier(self):
        from praviar_pipeline.pipeline.step2_search import _normalize_patent_id

        assert _normalize_patent_id("US7851188B2") == "US7851188B"
        assert _normalize_patent_id("US7851188A1") == "US7851188A"

    def test_application_and_grant_are_distinct(self):
        from praviar_pipeline.pipeline.step2_search import _normalize_patent_id

        assert _normalize_patent_id("US7851188B2") != _normalize_patent_id("US7851188A1")

    def test_strips_punctuation(self):
        from praviar_pipeline.pipeline.step2_search import _normalize_patent_id

        assert _normalize_patent_id("US-7,851,188-B2") == "US7851188B"

    def test_uppercase(self):
        from praviar_pipeline.pipeline.step2_search import _normalize_patent_id

        assert _normalize_patent_id("us7851188b2") == "US7851188B"


class TestComputeConfidence:
    def test_single_source(self, mock_settings):
        from praviar_pipeline.pipeline.step2_search import _compute_confidence

        assert _compute_confidence([PatentSource.PUBCHEM]) == 0.30

    def test_two_sources(self, mock_settings):
        from praviar_pipeline.pipeline.step2_search import _compute_confidence

        assert _compute_confidence([PatentSource.PUBCHEM, PatentSource.SURECHEMBL]) == 0.60

    def test_three_sources(self, mock_settings):
        from praviar_pipeline.pipeline.step2_search import _compute_confidence

        sources = [PatentSource.PUBCHEM, PatentSource.SURECHEMBL, PatentSource.BIGQUERY]
        assert _compute_confidence(sources) == 0.85

    def test_four_sources(self, mock_settings):
        from praviar_pipeline.pipeline.step2_search import _compute_confidence

        sources = [
            PatentSource.PUBCHEM,
            PatentSource.SURECHEMBL,
            PatentSource.BIGQUERY,
            PatentSource.PATCID,
        ]
        assert _compute_confidence(sources) == 0.95
