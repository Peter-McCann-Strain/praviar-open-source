"""Tests for scholarly search improvements — exact phrase matching + relevance filtering."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from praviar_pipeline.errors import SearchSourceFailedError
from praviar_pipeline.models.analysis import PatentAnalysis, RiskLevel
from praviar_pipeline.models.compound import ResolvedCompound
from praviar_pipeline.pipeline.step6_invalid import (
    _build_scholarly_queries,
    _is_relevant_paper,
    _search_scholarly_prior_art,
)

pytestmark = pytest.mark.usefixtures("mock_settings")


def _make_compound(
    name: str = "itaconic acid",
    synonyms: list[str] | None = None,
    cas_numbers: list[str] | None = None,
) -> ResolvedCompound:
    return ResolvedCompound(
        name=name,
        canonical_smiles="OC(=O)/C=C\\CC(=O)O",
        inchi="InChI=1S/C5H6O4/c1(6)5(7,8)3-2-4(9)10/h2H,3H2,(H,6)(H,9,10)",
        inchi_key="LVHBHZANLOWSRM-UHFFFAOYSA-N",
        pubchem_cid=811,
        synonyms=synonyms or ["methylenesuccinic acid", "2-methylidenebutanedioic acid"],
        cas_numbers=cas_numbers or ["97-65-4"],
        original_input="itaconic acid",
        input_type="name",
    )


class TestBuildScholarlyQueries:
    def test_primary_query_uses_exact_phrase(self):
        compound = _make_compound()
        queries = _build_scholarly_queries(compound)
        assert queries[0] == '"itaconic acid"'

    def test_synonym_query_if_available(self):
        compound = _make_compound(synonyms=["methylenesuccinic acid"])
        queries = _build_scholarly_queries(compound)
        assert len(queries) >= 2
        assert queries[1] == '"methylenesuccinic acid"'

    def test_cas_query_if_available(self):
        compound = _make_compound(cas_numbers=["97-65-4"])
        queries = _build_scholarly_queries(compound)
        assert "97-65-4" in queries

    def test_no_synonym_no_cas(self):
        compound = ResolvedCompound(
            name="itaconic acid",
            canonical_smiles="OC(=O)/C=C\\CC(=O)O",
            inchi="InChI=1S/C5H6O4",
            inchi_key="LVHBHZANLOWSRM-UHFFFAOYSA-N",
            pubchem_cid=811,
            synonyms=[],
            cas_numbers=[],
            original_input="itaconic acid",
            input_type="name",
        )
        queries = _build_scholarly_queries(compound)
        assert queries[0] == '"itaconic acid"'
        # InChIKey prefix is also added as a broadening query
        assert "LVHBHZANLOWSRM" in queries

    def test_does_not_include_generic_terms(self):
        """Regression: old query was '{name} synthesis production' — too generic."""
        compound = _make_compound()
        queries = _build_scholarly_queries(compound)
        for q in queries:
            assert "synthesis production" not in q


class TestIsRelevantPaper:
    def test_relevant_when_name_in_title(self):
        compound = _make_compound()
        assert _is_relevant_paper(
            "Production of itaconic acid by Aspergillus terreus",
            "",
            compound,
        )

    def test_relevant_when_name_in_abstract(self):
        compound = _make_compound()
        assert _is_relevant_paper(
            "Organic acid production",
            "We studied the biosynthesis of itaconic acid from glucose.",
            compound,
        )

    def test_relevant_when_synonym_in_title(self):
        compound = _make_compound()
        assert _is_relevant_paper(
            "Methylenesuccinic acid biosynthesis review",
            "",
            compound,
        )

    def test_relevant_when_cas_in_abstract(self):
        compound = _make_compound()
        assert _is_relevant_paper(
            "Chemical production review",
            "Compound 97-65-4 was studied for polymer applications.",
            compound,
        )

    def test_not_relevant_unrelated_paper(self):
        compound = _make_compound()
        assert not _is_relevant_paper(
            "Fatty acid synthesis in mammalian cells",
            "We review the de novo synthesis of long-chain fatty acids.",
            compound,
        )

    def test_case_insensitive(self):
        compound = _make_compound()
        assert _is_relevant_paper(
            "ITACONIC ACID Production",
            "",
            compound,
        )

    def test_empty_abstract(self):
        compound = _make_compound()
        assert not _is_relevant_paper(
            "Unrelated title",
            "",
            compound,
        )


@pytest.mark.asyncio
async def test_search_scholarly_prior_art_includes_pubmed_results(monkeypatch):
    from praviar_pipeline.pipeline.invalidity import scholarly

    patent = PatentAnalysis(
        patent_id="US1234567B2",
        title="Itaconic acid process",
        assignee="Praviar",
        risk_level=RiskLevel.HIGH,
        risk_summary="Blocking",
        claims_analyzed=[],
    )
    compound = _make_compound()

    semantic_scholar = MagicMock()
    semantic_scholar.search_papers = AsyncMock(return_value=[])
    semantic_scholar.__aenter__ = AsyncMock(return_value=semantic_scholar)
    semantic_scholar.__aexit__ = AsyncMock(return_value=False)

    openalex = MagicMock()
    openalex.search_works = AsyncMock(return_value=[])
    openalex.__aenter__ = AsyncMock(return_value=openalex)
    openalex.__aexit__ = AsyncMock(return_value=False)

    pubmed = MagicMock()
    pubmed.search_compound_literature = AsyncMock(
        return_value=[
            {
                "pmid": "12345",
                "title": "Itaconic acid fermentation process optimization",
                "authors": ["A. Chemist"],
                "journal": "Journal of Fermentation",
                "publication_date": "2010-06-01",
                "doi": "10.1000/pubmed-itaconic",
            }
        ]
    )
    pubmed.__aenter__ = AsyncMock(return_value=pubmed)
    pubmed.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(scholarly, "SemanticScholarClient", lambda: semantic_scholar)
    monkeypatch.setattr(scholarly, "OpenAlexClient", lambda: openalex)
    monkeypatch.setattr(scholarly, "PubMedClient", lambda: pubmed)

    prior_art = await _search_scholarly_prior_art(
        patent,
        compound,
        date(2015, 1, 1),
    )

    assert len(prior_art) == 1
    assert prior_art[0].source_database == "pubmed"
    assert prior_art[0].reference_id == "12345"


@pytest.mark.asyncio
async def test_search_scholarly_prior_art_fails_closed_on_source_failure(monkeypatch):
    """Any configured scholarly source failure invalidates the evidence collection."""
    from praviar_pipeline.pipeline.invalidity import scholarly

    patent = PatentAnalysis(
        patent_id="US1234567B2",
        title="Itaconic acid process",
        assignee="Praviar",
        risk_level=RiskLevel.HIGH,
        risk_summary="Blocking",
        claims_analyzed=[],
    )
    compound = _make_compound()
    secret = "secret-token-must-not-escape"
    logger = MagicMock()

    async def fail_source(*args, **kwargs):
        raise RuntimeError(f"https://api.example.invalid?api_key={secret}")

    monkeypatch.setattr(scholarly, "logger", logger)
    monkeypatch.setattr(scholarly, "_search_s2_multi_query", fail_source)
    monkeypatch.setattr(scholarly, "_search_oa_multi_query", AsyncMock(return_value=({}, [])))
    monkeypatch.setattr(scholarly, "_search_pubmed_prior_art", AsyncMock(return_value=({}, [])))

    with pytest.raises(SearchSourceFailedError) as exc_info:
        await _search_scholarly_prior_art(
            patent,
            compound,
            date(2015, 1, 1),
        )

    assert exc_info.value.failures == {"scholarly_semantic_scholar": "RuntimeError"}
    assert secret not in str(exc_info.value)
    assert secret not in repr(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    for call in logger.warning.call_args_list:
        assert secret not in repr((call.args, call.kwargs))
        assert "exc_info" not in call.kwargs


@pytest.mark.asyncio
async def test_search_scholarly_prior_art_fails_closed_when_all_sources_fail(monkeypatch):
    """When all scholarly sources fail, SearchSourceFailedError is raised."""
    from praviar_pipeline.pipeline.invalidity import scholarly

    patent = PatentAnalysis(
        patent_id="US1234567B2",
        title="Itaconic acid process",
        assignee="Praviar",
        risk_level=RiskLevel.HIGH,
        risk_summary="Blocking",
        claims_analyzed=[],
    )
    compound = _make_compound()

    async def fail_source(*args, **kwargs):
        raise RuntimeError("source outage")

    monkeypatch.setattr(scholarly, "_search_s2_multi_query", fail_source)
    monkeypatch.setattr(scholarly, "_search_oa_multi_query", fail_source)
    monkeypatch.setattr(scholarly, "_search_pubmed_prior_art", fail_source)

    with pytest.raises(SearchSourceFailedError) as exc_info:
        await _search_scholarly_prior_art(
            patent,
            compound,
            date(2015, 1, 1),
        )

    assert "scholarly_semantic_scholar" in exc_info.value.failures
