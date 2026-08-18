"""Focused unit tests for the literature search module (SG-130).

Covers ``praviar_pipeline.pipeline.search.literature_sources.search_literature`` and
``praviar_pipeline.models.literature.LiteratureReference``. External clients
(OpenAlex, Semantic Scholar) are mocked at the client-factory boundary; no
network calls are made.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from praviar_pipeline.config import clear_settings_cache
from praviar_pipeline.errors import SearchSourceFailedError, SourceUnavailableError
from praviar_pipeline.models.literature import LiteratureReference
from praviar_pipeline.models.report import SourceStatus
from praviar_pipeline.pipeline.search.literature_sources import search_literature

if TYPE_CHECKING:
    from praviar_pipeline.models.compound import ResolvedCompound

# ---------------------------------------------------------------------------
# Helpers — build fake async client factories that mimic an async-context
# manager exposing ``search_works`` / ``search_papers``.
# ---------------------------------------------------------------------------


def _make_openalex_factory(
    works: list[dict] | None = None,
    *,
    raises: BaseException | None = None,
):
    """Return a zero-arg callable producing an async-context-manager client.

    The client exposes ``search_works(query, max_results=...)`` which either
    returns ``works`` or raises ``raises``.
    """

    def factory() -> Any:
        client = MagicMock()
        if raises is not None:
            client.search_works = AsyncMock(side_effect=raises)
        else:
            client.search_works = AsyncMock(return_value=list(works or []))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        return client

    return factory


def _make_s2_factory(
    papers: list[dict] | None = None,
    *,
    raises: BaseException | None = None,
):
    def factory() -> Any:
        client = MagicMock()
        if raises is not None:
            client.search_papers = AsyncMock(side_effect=raises)
        else:
            client.search_papers = AsyncMock(return_value=list(papers or []))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        return client

    return factory


def _oa_work(
    *,
    wid: str,
    title: str,
    doi: str = "",
    year: int | None = None,
    score: float | None = None,
) -> dict:
    work: dict[str, Any] = {"id": wid, "title": title}
    if doi:
        work["doi"] = f"https://doi.org/{doi}"
    if year is not None:
        work["publication_year"] = year
    if score is not None:
        work["relevance_score"] = score
    return work


def _s2_paper(
    *,
    paper_id: str,
    title: str,
    doi: str = "",
    year: int | None = None,
    abstract: str = "",
) -> dict:
    paper: dict[str, Any] = {"paperId": paper_id, "title": title}
    if doi:
        paper["externalIds"] = {"DOI": doi}
    if year is not None:
        paper["year"] = year
    if abstract:
        paper["abstract"] = abstract
    return paper


# ---------------------------------------------------------------------------
# Tests for search_literature
# ---------------------------------------------------------------------------


class TestSearchLiteratureHappyPath:
    async def test_both_sources_return_results_are_merged(
        self,
        succinic_acid: ResolvedCompound,
    ) -> None:
        oa_works = [
            _oa_work(wid=f"W{i}", title=f"OA paper {i}", doi=f"10.1000/oa{i}", year=2020 + i)
            for i in range(3)
        ]
        s2_papers = [
            _s2_paper(paper_id=f"P{i}", title=f"S2 paper {i}", doi=f"10.2000/s2{i}", year=2010 + i)
            for i in range(3)
        ]

        refs, health = await search_literature(
            succinic_acid,
            openalex_client_factory=_make_openalex_factory(oa_works),
            semantic_scholar_client_factory=_make_s2_factory(s2_papers),
        )

        assert len(refs) == 6
        sources = {r.source for r in refs}
        assert sources == {"openalex", "semantic_scholar"}
        # Both health entries OK
        assert len(health) == 2
        assert all(e.status == SourceStatus.OK for e in health)
        assert {e.source for e in health} == {"literature_openalex", "literature_semantic_scholar"}


class TestDeduplication:
    async def test_doi_dedup_across_sources(
        self,
        succinic_acid: ResolvedCompound,
    ) -> None:
        shared_doi = "10.1234/abc"
        oa_works = [
            _oa_work(
                wid="W1",
                title="Shared paper (OA variant)",
                doi=shared_doi,
                year=2021,
            )
        ]
        s2_papers = [
            _s2_paper(
                paper_id="P1",
                title="Shared paper (S2 variant)",
                doi=shared_doi,
                year=2021,
                abstract="Full abstract from S2",
            )
        ]

        refs, _ = await search_literature(
            succinic_acid,
            openalex_client_factory=_make_openalex_factory(oa_works),
            semantic_scholar_client_factory=_make_s2_factory(s2_papers),
        )

        # Dedup collapses to a single entry; the richer record (S2 carries
        # the abstract) wins over the OpenAlex stub.
        assert len(refs) == 1
        assert refs[0].doi.lower() == shared_doi.lower()
        assert refs[0].source == "semantic_scholar"
        assert refs[0].abstract == "Full abstract from S2"

    async def test_title_fallback_dedup_when_no_doi(
        self,
        succinic_acid: ResolvedCompound,
    ) -> None:
        title = "A Catalytic Synthesis Route"
        oa_works = [_oa_work(wid="W1", title=title, year=2019)]
        s2_papers = [_s2_paper(paper_id="P1", title=title, year=2019)]

        refs, _ = await search_literature(
            succinic_acid,
            openalex_client_factory=_make_openalex_factory(oa_works),
            semantic_scholar_client_factory=_make_s2_factory(s2_papers),
        )

        assert len(refs) == 1
        assert refs[0].title == title


class TestSourceFailure:
    async def test_openalex_failure_returns_partial_refs_with_failed_health(
        self,
        succinic_acid: ResolvedCompound,
    ) -> None:
        s2_papers = [
            _s2_paper(paper_id="P1", title="S2 only", doi="10.2000/only", year=2022),
            _s2_paper(paper_id="P2", title="S2 only 2", doi="10.2000/only2", year=2021),
        ]

        refs, health = await search_literature(
            succinic_acid,
            openalex_client_factory=_make_openalex_factory(
                raises=SourceUnavailableError("openalex", "boom", status_code=503),
            ),
            semantic_scholar_client_factory=_make_s2_factory(s2_papers),
        )

        assert len(refs) == 2
        failed = [entry for entry in health if entry.status == SourceStatus.FAILED]
        assert [entry.source for entry in failed] == ["literature_openalex"]

    async def test_s2_failure_returns_partial_refs_with_failed_health(
        self,
        succinic_acid: ResolvedCompound,
    ) -> None:
        oa_works = [
            _oa_work(wid="W1", title="OA only", doi="10.1000/only", year=2022),
        ]

        refs, health = await search_literature(
            succinic_acid,
            openalex_client_factory=_make_openalex_factory(oa_works),
            semantic_scholar_client_factory=_make_s2_factory(
                raises=SourceUnavailableError("semantic_scholar", "timeout"),
            ),
        )

        assert len(refs) == 1
        failed = [entry for entry in health if entry.status == SourceStatus.FAILED]
        assert [entry.source for entry in failed] == ["literature_semantic_scholar"]

    async def test_both_sources_fail_returns_empty_refs_and_failed_health(
        self,
        succinic_acid: ResolvedCompound,
    ) -> None:
        refs, health = await search_literature(
            succinic_acid,
            openalex_client_factory=_make_openalex_factory(
                raises=SourceUnavailableError("openalex", "down"),
            ),
            semantic_scholar_client_factory=_make_s2_factory(
                raises=SourceUnavailableError("semantic_scholar", "down"),
            ),
        )

        assert refs == []
        assert {entry.source for entry in health if entry.status == SourceStatus.FAILED} == {
            "literature_openalex",
            "literature_semantic_scholar",
        }

    async def test_fail_fast_policy_raises_on_source_failure(
        self,
        succinic_acid: ResolvedCompound,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:

        monkeypatch.setenv("SOURCE_FAILURE_POLICY", "fail_fast")
        clear_settings_cache()
        try:
            with pytest.raises(SearchSourceFailedError) as exc_info:
                await search_literature(
                    succinic_acid,
                    openalex_client_factory=_make_openalex_factory(
                        raises=SourceUnavailableError("openalex", "down"),
                    ),
                    semantic_scholar_client_factory=_make_s2_factory([]),
                )
        finally:
            clear_settings_cache()

        assert "literature_openalex" in exc_info.value.failures


class TestSortOrder:
    async def test_sorted_by_year_desc_then_score_desc(
        self,
        succinic_acid: ResolvedCompound,
    ) -> None:
        # Mix years + provide two 2020 OpenAlex papers with differing scores
        # to exercise the tie-break. Use raw scores <=1 to stay as-is through
        # the squash logic (>1 triggers normalisation).
        oa_works = [
            _oa_work(wid="W-old", title="Old OA", doi="10.1/old", year=2015, score=0.9),
            _oa_work(
                wid="W-tie-low", title="2020 low-score", doi="10.1/tlow", year=2020, score=0.2
            ),
            _oa_work(
                wid="W-tie-high", title="2020 high-score", doi="10.1/thigh", year=2020, score=0.9
            ),
            _oa_work(wid="W-new", title="New OA", doi="10.1/new", year=2024, score=0.5),
        ]
        s2_papers: list[dict] = []

        refs, _ = await search_literature(
            succinic_acid,
            openalex_client_factory=_make_openalex_factory(oa_works),
            semantic_scholar_client_factory=_make_s2_factory(s2_papers),
        )

        years = [r.publication_year for r in refs]
        assert years == sorted(years, key=lambda y: -(y or -1))
        assert years[0] == 2024
        assert years[-1] == 2015

        # Within the 2020 group, higher score first.
        refs_2020 = [r for r in refs if r.publication_year == 2020]
        assert len(refs_2020) == 2
        assert refs_2020[0].relevance_score > refs_2020[1].relevance_score


class TestCap:
    async def test_total_capped_at_max_per_source_times_two(
        self,
        succinic_acid: ResolvedCompound,
    ) -> None:
        # Produce more than max_per_source from each side with unique DOIs
        # so dedup doesn't reduce count below the cap.
        max_per = 5
        oa_works = [
            _oa_work(wid=f"W{i}", title=f"OA {i}", doi=f"10.1000/oa{i}", year=2020 + i)
            for i in range(max_per + 3)
        ]
        s2_papers = [
            _s2_paper(paper_id=f"P{i}", title=f"S2 {i}", doi=f"10.2000/s2{i}", year=2000 + i)
            for i in range(max_per + 3)
        ]

        refs, _ = await search_literature(
            succinic_acid,
            max_per_source=max_per,
            openalex_client_factory=_make_openalex_factory(oa_works),
            semantic_scholar_client_factory=_make_s2_factory(s2_papers),
        )

        assert len(refs) == max_per * 2


# ---------------------------------------------------------------------------
# Tests for the LiteratureReference pydantic model
# ---------------------------------------------------------------------------


class TestDedupeCompleteness:
    """DOI / title collisions should keep the richer record, not first-seen.

    Regression coverage for the OpenAlex-stubs-out-Semantic-Scholar bug:
    OpenAlex always ships ``abstract=""``, and because the OpenAlex coro runs
    first in ``asyncio.gather`` we used to lose the S2 abstract on every
    collision. ``_merge_and_dedupe`` now keeps the entry with the higher
    completeness score (ties fall back to first-seen for determinism).
    """

    async def test_second_seen_with_richer_abstract_wins(
        self,
        succinic_acid: ResolvedCompound,
    ) -> None:
        shared_doi = "10.1234/richer"
        oa_works = [
            # OpenAlex: no abstract, no venue — a bare stub.
            _oa_work(wid="W1", title="Shared paper", doi=shared_doi, year=2021),
        ]
        s2_papers = [
            # Semantic Scholar: real abstract.
            _s2_paper(
                paper_id="P1",
                title="Shared paper",
                doi=shared_doi,
                year=2021,
                abstract="Full abstract from Semantic Scholar",
            ),
        ]

        refs, _ = await search_literature(
            succinic_acid,
            openalex_client_factory=_make_openalex_factory(oa_works),
            semantic_scholar_client_factory=_make_s2_factory(s2_papers),
        )

        assert len(refs) == 1
        # Winner is the S2 record because it carries the abstract.
        assert refs[0].source == "semantic_scholar"
        assert refs[0].abstract == "Full abstract from Semantic Scholar"

    async def test_equally_complete_records_first_seen_wins(
        self,
        succinic_acid: ResolvedCompound,
    ) -> None:
        shared_doi = "10.1234/tied"
        # Both records have: doi + url + venue + authors + abstract.
        # For OpenAlex, ``abstract`` is always "" in our converter, so we
        # construct both sides to have matching completeness (no abstract on
        # either, both have doi+url+venue+authors = 4 points each). The
        # first-seen should win (OpenAlex runs first in the gather order).
        oa_works = [
            {
                "id": "https://openalex.org/W1",
                "title": "Shared paper",
                "doi": f"https://doi.org/{shared_doi}",
                "publication_year": 2021,
                "host_venue": {"display_name": "Nature"},
                "authorships": [{"author": {"display_name": "Alice"}}],
            }
        ]
        s2_papers = [
            {
                "paperId": "P1",
                "title": "Shared paper",
                "externalIds": {"DOI": shared_doi},
                "year": 2021,
                "journal": {"name": "Nature"},
                "authors": [{"name": "Alice"}],
                # No abstract — keeps completeness tied with OA.
            }
        ]

        refs, _ = await search_literature(
            succinic_acid,
            openalex_client_factory=_make_openalex_factory(oa_works),
            semantic_scholar_client_factory=_make_s2_factory(s2_papers),
        )

        assert len(refs) == 1
        # Tiebreak: OpenAlex (first-seen) wins.
        assert refs[0].source == "openalex"

    async def test_richer_abstract_beats_more_authors(
        self,
        succinic_acid: ResolvedCompound,
    ) -> None:
        """Document the chosen tiebreak: completeness is a simple field count.

        Authors contribute one point regardless of list length, so a record
        with 50 authors scores the same on that axis as a record with one
        author. Adding an abstract (another +1) therefore beats "more
        authors" — that is the intended behaviour. This test pins it down
        so future changes have to re-open the debate.
        """
        shared_doi = "10.1234/abs-beats-authors"
        # OpenAlex: 5 authors, no abstract -> authors(+1) + doi(+1) + url(+1)
        # = 3 points (no venue in this fixture).
        oa_works = [
            {
                "id": "https://openalex.org/W1",
                "title": "Shared paper",
                "doi": f"https://doi.org/{shared_doi}",
                "publication_year": 2021,
                "authorships": [{"author": {"display_name": f"Author {i}"}} for i in range(5)],
            }
        ]
        # S2: 1 author + abstract -> authors(+1) + doi(+1) + url(+1) +
        # abstract(+1) = 4 points. Include authors explicitly (the
        # ``_s2_paper`` helper omits them by default).
        s2_papers = [
            {
                "paperId": "P1",
                "title": "Shared paper",
                "externalIds": {"DOI": shared_doi},
                "year": 2021,
                "abstract": "S2 abstract",
                "authors": [{"name": "Solo Author"}],
            }
        ]

        refs, _ = await search_literature(
            succinic_acid,
            openalex_client_factory=_make_openalex_factory(oa_works),
            semantic_scholar_client_factory=_make_s2_factory(s2_papers),
        )

        assert len(refs) == 1
        # S2 wins because abstract bumps completeness from 3 -> 4.
        assert refs[0].source == "semantic_scholar"
        assert refs[0].abstract == "S2 abstract"

    async def test_title_fallback_uses_completeness(
        self,
        succinic_acid: ResolvedCompound,
    ) -> None:
        """Title-collision fallback path uses the same completeness tiebreak.

        Both records have no DOI, so they collide on lowercased title. The
        richer (S2, with abstract) should win, same as DOI collisions.
        """
        title = "A Catalytic Synthesis Route"
        oa_works = [_oa_work(wid="W1", title=title, year=2019)]
        s2_papers = [
            _s2_paper(
                paper_id="P1",
                title=title,
                year=2019,
                abstract="S2 abstract on title-only match",
            )
        ]

        refs, _ = await search_literature(
            succinic_acid,
            openalex_client_factory=_make_openalex_factory(oa_works),
            semantic_scholar_client_factory=_make_s2_factory(s2_papers),
        )

        assert len(refs) == 1
        assert refs[0].source == "semantic_scholar"
        assert refs[0].abstract == "S2 abstract on title-only match"

    async def test_completeness_tiebreak_is_deterministic_across_runs(
        self,
        succinic_acid: ResolvedCompound,
    ) -> None:
        """Same inputs produce the same winner every time — no flaky ordering.

        Runs the merge three times against identical inputs. If ordering
        inside ``_merge_and_dedupe`` leaked a non-determinism (e.g. relying
        on dict iteration order for ties), the winner could flip between
        runs. It must not.
        """
        shared_doi = "10.1234/determ"
        oa_works = [_oa_work(wid="W1", title="Shared", doi=shared_doi, year=2021)]
        s2_papers = [
            _s2_paper(
                paper_id="P1",
                title="Shared",
                doi=shared_doi,
                year=2021,
                abstract="S2 abstract",
            )
        ]

        winners: set[str] = set()
        for _ in range(3):
            refs, _health = await search_literature(
                succinic_acid,
                openalex_client_factory=_make_openalex_factory(oa_works),
                semantic_scholar_client_factory=_make_s2_factory(s2_papers),
            )
            assert len(refs) == 1
            winners.add(refs[0].source)

        assert winners == {"semantic_scholar"}


class TestLiteratureReferenceModel:
    def test_minimal_construction_only_required_fields(self) -> None:
        ref = LiteratureReference(
            source="openalex",
            external_id="W1",
            title="A paper",
        )
        assert ref.source == "openalex"
        assert ref.external_id == "W1"
        assert ref.title == "A paper"
        # Defaults
        assert ref.authors == []
        assert ref.publication_year is None
        assert ref.venue == ""
        assert ref.doi == ""
        assert ref.abstract == ""
        assert ref.url == ""
        assert ref.relevance_score == 0.0

    def test_rejects_unknown_source_value(self) -> None:
        with pytest.raises(ValidationError):
            LiteratureReference(
                source="arxiv",  # type: ignore[arg-type]
                external_id="X1",
                title="Rejected",
            )

    @pytest.mark.parametrize("bad_score", [-0.1, 1.1])
    def test_relevance_score_bounds(self, bad_score: float) -> None:
        with pytest.raises(ValidationError):
            LiteratureReference(
                source="openalex",
                external_id="W1",
                title="t",
                relevance_score=bad_score,
            )
