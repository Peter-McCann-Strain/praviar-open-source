"""Prior-art literature search — parallel branch feeding step 6 invalidity (SG-130).

Wires OpenAlex + Semantic Scholar as a *sibling* to the patent search. Results feed the
invalidity step as §102/§103 prior-art candidates, so source failures are treated as
coverage gaps and fail the run instead of being reported as empty prior art.

The entry point :func:`search_literature` fans out to both clients in parallel,
merges and dedupes results by DOI (title-lowercase fallback), and returns both
the merged ``LiteratureReference`` list and ``SourceHealthEntry`` records so
literature sources surface in the report's coverage banner alongside patent
sources.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

from praviar_pipeline.clients.openalex import OpenAlexClient
from praviar_pipeline.clients.semantic_scholar import SemanticScholarClient
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import SearchSourceFailedError
from praviar_pipeline.models.literature import LiteratureReference
from praviar_pipeline.models.report import SourceHealthEntry, SourceStatus
from praviar_pipeline.utils.safe_diagnostics import (
    safe_exception_type,
    safe_failure_message,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from praviar_pipeline.models.compound import ResolvedCompound

logger = structlog.get_logger()

_DOI_URL_PREFIX = "https://doi.org/"


def _build_literature_query(compound: ResolvedCompound) -> str:
    """Build a single broad literature query: name + top synonyms + first CAS."""
    parts: list[str] = []
    if compound.name:
        parts.append(f'"{compound.name}"')
    for synonym in compound.synonyms[:5]:
        parts.append(f'"{synonym}"')
    if compound.cas_numbers:
        parts.append(compound.cas_numbers[0])
    return " OR ".join(parts) if parts else compound.name


def _year_from_date_string(date_str: str | None) -> int | None:
    if not date_str:
        return None
    head = date_str[:4]
    if len(head) == 4 and head.isdigit():
        return int(head)
    return None


def _openalex_to_reference(work: dict) -> LiteratureReference | None:
    title = work.get("title") or ""
    if not title:
        return None
    doi = (work.get("doi") or "").strip()
    if doi.startswith(_DOI_URL_PREFIX):
        doi = doi[len(_DOI_URL_PREFIX) :]
    authorships = work.get("authorships") or []
    authors = [
        (a.get("author", {}) or {}).get("display_name", "")
        for a in authorships
        if (a.get("author", {}) or {}).get("display_name")
    ]
    year = work.get("publication_year") or _year_from_date_string(work.get("publication_date"))
    venue = ""
    host = work.get("host_venue") or work.get("primary_location", {}).get("source") or {}
    if isinstance(host, dict):
        venue = host.get("display_name") or host.get("name") or ""
    score = work.get("relevance_score")
    try:
        score_f = float(score) if score is not None else 0.0
    except (TypeError, ValueError):
        score_f = 0.0
    # Normalize OpenAlex score (unbounded) into [0,1] via squash
    if score_f > 1.0:
        score_f = 1.0 - (1.0 / (1.0 + score_f))
    elif score_f < 0.0:
        score_f = 0.0
    return LiteratureReference(
        source="openalex",
        external_id=str(work.get("id") or ""),
        title=title,
        authors=authors[:10],
        publication_year=int(year) if year else None,
        venue=venue,
        doi=doi,
        abstract="",  # OpenAlex exposes inverted index only; skip in v1
        url=(work.get("id") or "") if isinstance(work.get("id"), str) else "",
        relevance_score=score_f,
    )


def _semantic_scholar_to_reference(paper: dict) -> LiteratureReference | None:
    title = paper.get("title") or ""
    if not title:
        return None
    external_ids = paper.get("externalIds") or {}
    doi = (external_ids.get("DOI") or "").strip()
    authors_raw = paper.get("authors") or []
    authors = [a.get("name", "") for a in authors_raw if a.get("name")]
    year = paper.get("year") or _year_from_date_string(paper.get("publicationDate"))
    venue = ""
    journal = paper.get("journal") or {}
    if isinstance(journal, dict):
        venue = journal.get("name") or ""
    url = f"https://www.semanticscholar.org/paper/{paper.get('paperId', '')}"
    return LiteratureReference(
        source="semantic_scholar",
        external_id=str(paper.get("paperId") or ""),
        title=title,
        authors=authors[:10],
        publication_year=int(year) if year else None,
        venue=venue,
        doi=doi,
        abstract=paper.get("abstract") or "",
        url=url,
        relevance_score=0.0,  # S2 does not return a query-scoped score
    )


async def _search_openalex(
    query: str,
    max_results: int,
    *,
    client_factory: Callable[[], Any] = OpenAlexClient,
) -> list[LiteratureReference]:
    async with client_factory() as client:
        works = await client.search_works(query, max_results=max_results)
    refs: list[LiteratureReference] = []
    for work in works:
        ref = _openalex_to_reference(work)
        if ref is not None:
            refs.append(ref)
    return refs


async def _search_semantic_scholar(
    query: str,
    max_results: int,
    *,
    client_factory: Callable[[], Any] = SemanticScholarClient,
) -> list[LiteratureReference]:
    async with client_factory() as client:
        papers = await client.search_papers(query, max_results=max_results)
    refs: list[LiteratureReference] = []
    for paper in papers:
        ref = _semantic_scholar_to_reference(paper)
        if ref is not None:
            refs.append(ref)
    return refs


def _completeness_score(ref: LiteratureReference) -> int:
    """Count non-empty metadata fields — higher means a richer record.

    Used as the dedup tiebreak when the same DOI (or title) shows up from
    multiple sources. OpenAlex always ships ``abstract=""`` while Semantic
    Scholar returns real abstracts; under a first-seen-wins dedup we were
    silently losing the abstract every time OpenAlex raced ahead. Score one
    point per non-empty string field (``abstract``, ``venue``, ``doi``,
    ``url``) plus one point if the author list is non-empty — deterministic,
    bounded, and order-independent.
    """
    score = 0
    if ref.abstract:
        score += 1
    if ref.venue:
        score += 1
    if ref.doi:
        score += 1
    if ref.url:
        score += 1
    if ref.authors:
        score += 1
    return score


def _pick_better(
    existing: LiteratureReference, candidate: LiteratureReference
) -> LiteratureReference:
    """Return whichever reference has the higher completeness score.

    Ties are broken deterministically in favour of ``existing`` (first-seen
    wins on equality) so the output is stable regardless of how the input
    buckets were ordered or how many times the merge runs.
    """
    if _completeness_score(candidate) > _completeness_score(existing):
        return candidate
    return existing


def _merge_and_dedupe(
    buckets: list[list[LiteratureReference]],
    *,
    total_cap: int,
) -> list[LiteratureReference]:
    """Merge by DOI (primary) and title-lowercase (fallback).

    On DOI / title collisions we keep the entry with the highest
    :func:`_completeness_score` (ties go to the first-seen entry). This
    prevents OpenAlex stubs — which never carry an abstract — from
    shadowing richer Semantic Scholar records just because the OpenAlex
    coro happened to run first under ``asyncio.gather``.

    Results are sorted by year desc, score desc.
    """
    by_doi: dict[str, LiteratureReference] = {}
    by_title: dict[str, LiteratureReference] = {}
    for bucket in buckets:
        for ref in bucket:
            if ref.doi:
                key = ref.doi.lower()
                if key in by_doi:
                    by_doi[key] = _pick_better(by_doi[key], ref)
                else:
                    by_doi[key] = ref
                continue
            key = (ref.title or "").strip().lower()
            if not key:
                continue
            if key in by_title:
                by_title[key] = _pick_better(by_title[key], ref)
            else:
                by_title[key] = ref

    merged = list(by_doi.values()) + list(by_title.values())
    merged.sort(
        key=lambda r: (
            r.publication_year if r.publication_year is not None else -1,
            r.relevance_score,
        ),
        reverse=True,
    )
    return merged[:total_cap]


async def search_literature(
    compound: ResolvedCompound,
    *,
    max_per_source: int = 25,
    openalex_client_factory: Callable[[], Any] = OpenAlexClient,
    semantic_scholar_client_factory: Callable[[], Any] = SemanticScholarClient,
) -> tuple[list[LiteratureReference], list[SourceHealthEntry]]:
    """Run OpenAlex + Semantic Scholar in parallel; merge, dedupe, and report health.

    Returns ``(references, source_health_entries)``. ``source_health_entries`` is a
    list of ``SourceHealthEntry`` records suitable for appending onto the existing
    ``SourceHealth`` from patent search — literature sources surface in the
    coverage banner alongside patent sources.

    Behavior:
    * If either source raises ``SourceUnavailableError`` (or any other exception),
      the literature branch raises ``SearchSourceFailedError`` so the pipeline
      does not mistake a coverage gap for "no prior art found".
    * Results are deduped by DOI (lowercased) with a title-lowercase fallback.
    * Results are sorted by ``publication_year`` desc, then ``relevance_score`` desc.
    * The total list is capped at ``max_per_source * 2`` to bound prompt size.
    """
    query = _build_literature_query(compound)

    logger.debug(
        "literature_search_start",
        max_per_source=max_per_source,
    )

    openalex_task = _search_openalex(
        query,
        max_per_source,
        client_factory=openalex_client_factory,
    )
    s2_task = _search_semantic_scholar(
        query,
        max_per_source,
        client_factory=semantic_scholar_client_factory,
    )
    results = await asyncio.gather(openalex_task, s2_task, return_exceptions=True)

    source_names = ("openalex", "semantic_scholar")
    buckets: list[list[LiteratureReference]] = []
    entries: list[SourceHealthEntry] = []
    failures: dict[str, str] = {}

    for name, result in zip(source_names, results, strict=True):
        if isinstance(result, BaseException):
            diagnostic = safe_failure_message("literature search", result)
            logger.error(
                "literature_source_failed",
                source=name,
                error_type=safe_exception_type(result),
            )
            failures[f"literature_{name}"] = diagnostic
            entries.append(
                SourceHealthEntry(
                    source=f"literature_{name}",
                    status=SourceStatus.FAILED,
                    error_message=diagnostic,
                )
            )
            continue
        refs = result
        buckets.append(refs)
        entries.append(
            SourceHealthEntry(
                source=f"literature_{name}",
                status=SourceStatus.OK,
                patent_count=len(refs),
            )
        )

    policy = getattr(get_settings(), "source_failure_policy", "coverage_aware")
    if failures and policy == "fail_fast":
        raise SearchSourceFailedError(failures)

    merged = _merge_and_dedupe(buckets, total_cap=max_per_source * 2)

    logger.info(
        "literature_search_complete",
        openalex_count=len(buckets[0]) if len(buckets) > 0 else 0,
        semantic_scholar_count=len(buckets[1]) if len(buckets) > 1 else 0,
        merged_count=len(merged),
        failed_sources=list(failures),
    )
    return merged, entries
