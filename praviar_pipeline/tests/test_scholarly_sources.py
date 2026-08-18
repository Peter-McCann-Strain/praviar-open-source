from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.models.compound import ResolvedCompound
from praviar_pipeline.pipeline.invalidity import scholarly_sources

pytestmark = pytest.mark.usefixtures("mock_settings")

_CREDENTIAL_SENTINEL = "credential-sentinel-must-never-escape"


def _credential_bearing_transport_error(source: str) -> httpx.ConnectError:
    request = httpx.Request(
        "GET",
        f"https://api.example.invalid/{source}?api_key={_CREDENTIAL_SENTINEL}",
    )
    return httpx.ConnectError(
        f"failed request {request.url}",
        request=request,
    )


def _assert_sanitized_source_failure(
    exc: SourceUnavailableError,
    *,
    source: str,
    logger: MagicMock,
) -> None:
    assert str(exc) == f"{source} unavailable: scholarly search failed"
    assert _CREDENTIAL_SENTINEL not in str(exc)
    assert _CREDENTIAL_SENTINEL not in repr(exc)
    assert exc.__cause__ is None
    assert exc.__context__ is None
    assert logger.error.called
    for call in logger.error.call_args_list:
        assert _CREDENTIAL_SENTINEL not in repr((call.args, call.kwargs))
        assert "error" not in call.kwargs
        assert "exc_info" not in call.kwargs


def _make_compound() -> ResolvedCompound:
    return ResolvedCompound(
        name="itaconic acid",
        canonical_smiles="OC(=O)/C=C\\CC(=O)O",
        inchi="InChI=1S/C5H6O4/c1(6)5(7,8)3-2-4(9)10/h2H,3H2,(H,6)(H,9,10)",
        inchi_key="LVHBHZANLOWSRM-UHFFFAOYSA-N",
        pubchem_cid=811,
        synonyms=["methylenesuccinic acid"],
        cas_numbers=["97-65-4"],
        original_input="itaconic acid",
        input_type="name",
    )


@pytest.mark.asyncio
async def test_search_semantic_scholar_multi_query_stops_after_primary_threshold(
    monkeypatch,
):
    client = MagicMock()
    client.search_papers = AsyncMock(
        side_effect=[
            [
                {
                    "paperId": "p1",
                    "title": "Itaconic acid fermentation",
                    "abstract": "Itaconic acid production method.",
                    "publicationDate": "2010-01-01",
                    "externalIds": {"DOI": "10.1000/p1"},
                    "authors": [],
                    "journal": {"name": "J1"},
                },
                {
                    "paperId": "p2",
                    "title": "Methylenesuccinic acid review",
                    "abstract": "",
                    "publicationDate": "2009-01-01",
                    "externalIds": {"DOI": "10.1000/p2"},
                    "authors": [],
                    "journal": {"name": "J2"},
                },
            ],
            [
                {
                    "paperId": "p3",
                    "title": "Should not run",
                    "abstract": "Itaconic acid",
                    "publicationDate": "2008-01-01",
                    "externalIds": {"DOI": "10.1000/p3"},
                    "authors": [],
                    "journal": {"name": "J3"},
                }
            ],
        ]
    )
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(
        scholarly_sources,
        "get_settings",
        lambda: SimpleNamespace(
            scholarly_primary_max_results=10,
            scholarly_secondary_max_results=5,
            scholarly_early_exit_threshold=2,
        ),
    )

    refs_by_doi, refs_no_doi = await scholarly_sources.search_semantic_scholar_multi_query(
        ['"itaconic acid"', '"methylenesuccinic acid"'],
        2015,
        _make_compound(),
        "US123",
        client_factory=lambda: client,
    )

    assert client.search_papers.await_count == 1
    assert sorted(refs_by_doi) == ["10.1000/p1", "10.1000/p2"]
    assert refs_no_doi == []


@pytest.mark.asyncio
async def test_search_pubmed_prior_art_filters_unrelated_papers():
    client = MagicMock()
    client.search_compound_literature = AsyncMock(
        return_value=[
            {
                "pmid": "1",
                "title": "Itaconic acid fermentation process optimization",
                "authors": ["A. Chemist"],
                "journal": "Journal of Fermentation",
                "publication_date": "2010-06-01",
                "doi": "10.1000/pubmed-itaconic",
            },
            {
                "pmid": "2",
                "title": "Fatty acid synthesis in mammalian cells",
                "authors": ["B. Biologist"],
                "journal": "Journal of Lipids",
                "publication_date": "2011-03-01",
                "doi": "10.1000/unrelated",
            },
        ]
    )
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    refs_by_doi, refs_no_doi = await scholarly_sources.search_pubmed_prior_art(
        _make_compound(),
        "US123",
        client_factory=lambda: client,
    )

    assert list(refs_by_doi) == ["10.1000/pubmed-itaconic"]
    assert refs_no_doi == []


@pytest.mark.asyncio
async def test_semantic_scholar_failure_never_exposes_request_credentials(monkeypatch):
    logger = MagicMock()
    monkeypatch.setattr(scholarly_sources, "logger", logger)
    client = MagicMock()
    client.search_papers = AsyncMock(
        side_effect=_credential_bearing_transport_error("semantic-scholar")
    )
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with pytest.raises(SourceUnavailableError) as exc_info:
        await scholarly_sources.search_semantic_scholar_multi_query(
            ['"itaconic acid"'],
            2015,
            _make_compound(),
            "US123",
            client_factory=lambda: client,
        )

    _assert_sanitized_source_failure(
        exc_info.value,
        source="semantic_scholar",
        logger=logger,
    )


@pytest.mark.asyncio
async def test_openalex_failure_never_exposes_request_credentials(monkeypatch):
    logger = MagicMock()
    monkeypatch.setattr(scholarly_sources, "logger", logger)
    client = MagicMock()
    client.search_works = AsyncMock(side_effect=_credential_bearing_transport_error("openalex"))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with pytest.raises(SourceUnavailableError) as exc_info:
        await scholarly_sources.search_openalex_multi_query(
            ['"itaconic acid"'],
            2015,
            _make_compound(),
            "US123",
            client_factory=lambda: client,
        )

    _assert_sanitized_source_failure(
        exc_info.value,
        source="openalex",
        logger=logger,
    )


@pytest.mark.asyncio
async def test_pubmed_failure_never_exposes_request_credentials(monkeypatch):
    logger = MagicMock()
    monkeypatch.setattr(scholarly_sources, "logger", logger)
    client = MagicMock()
    client.search_compound_literature = AsyncMock(
        side_effect=_credential_bearing_transport_error("pubmed")
    )
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with pytest.raises(SourceUnavailableError) as exc_info:
        await scholarly_sources.search_pubmed_prior_art(
            _make_compound(),
            "US123",
            client_factory=lambda: client,
        )

    _assert_sanitized_source_failure(
        exc_info.value,
        source="pubmed",
        logger=logger,
    )
