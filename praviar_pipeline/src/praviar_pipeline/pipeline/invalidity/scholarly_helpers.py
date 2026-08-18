"""Pure helper functions for scholarly prior-art search."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.config import get_settings
from praviar_pipeline.models.invalidity import PriorArtReference
from praviar_pipeline.utils.dates import parse_date as _parse_date

if TYPE_CHECKING:
    from datetime import date

    from praviar_pipeline.models.compound import ResolvedCompound

_DOI_URL_PREFIX = "https://doi.org/"


def is_relevant_paper(
    paper_title: str,
    paper_abstract: str,
    compound: ResolvedCompound,
) -> bool:
    """Check if a paper is relevant by requiring compound name or synonym in title/abstract."""
    text = (paper_title + " " + paper_abstract).lower()
    if compound.name.lower() in text:
        return True
    for synonym in compound.synonyms:
        if synonym.lower() in text:
            return True
    return any(cas in text for cas in compound.cas_numbers)


def build_scholarly_queries(compound: ResolvedCompound) -> list[str]:
    """Build a list of search queries for scholarly prior art, ordered by specificity."""
    settings = get_settings()
    queries = [f'"{compound.name}"']

    for synonym in compound.synonyms[: settings.scholarly_max_synonyms]:
        queries.append(f'"{synonym}"')

    if compound.cas_numbers:
        queries.append(compound.cas_numbers[0])

    if compound.inchi_key and "-" in compound.inchi_key:
        queries.append(compound.inchi_key.split("-")[0])

    if (
        compound.molecular_weight
        and compound.molecular_weight > settings.molecular_weight_broadening_threshold
        and compound.functional_groups
    ):
        queries.append(f'"{compound.name}" {" ".join(compound.functional_groups[:3])}')

    return queries


def build_semantic_scholar_reference(paper: dict) -> PriorArtReference:
    settings = get_settings()
    external_ids = paper.get("externalIds", {}) or {}
    return PriorArtReference(
        reference_id=paper.get("paperId", ""),
        title=paper.get("title", ""),
        publication_date=_parse_date(paper.get("publicationDate")),
        reference_type="journal_article",
        authors=[
            author.get("name", "")
            for author in paper.get("authors", [])[: settings.invalidity_authors_max]
        ],
        journal=(paper.get("journal") or {}).get("name", ""),
        doi=external_ids.get("DOI", ""),
        abstract=paper.get("abstract", "") or "",
        source_database="semantic_scholar",
    )


def build_openalex_reference(work: dict) -> PriorArtReference:
    settings = get_settings()
    doi = work.get("doi", "") or ""
    if doi.startswith(_DOI_URL_PREFIX):
        doi = doi[len(_DOI_URL_PREFIX) :]

    return PriorArtReference(
        reference_id=work.get("id", ""),
        title=work.get("title", ""),
        publication_date=_parse_date(work.get("publication_date")),
        reference_type="journal_article",
        authors=[
            authorship.get("author", {}).get("display_name", "")
            for authorship in work.get("authorships", [])[: settings.invalidity_authors_max]
        ],
        doi=doi,
        source_database="openalex",
    )


def build_lens_reference(work: dict) -> PriorArtReference:
    doi = ""
    for ext_id in work.get("external_ids", []):
        if ext_id.get("type") == "doi":
            doi = ext_id.get("value", "")
            break

    return PriorArtReference(
        reference_id=work.get("lens_id", ""),
        title=work.get("title", ""),
        publication_date=_parse_date(work.get("date_published")),
        reference_type="journal_article",
        doi=doi,
        source_database="lens",
    )


def build_pubmed_reference(paper: dict) -> PriorArtReference:
    return PriorArtReference(
        reference_id=paper.get("pmid", ""),
        title=paper.get("title", ""),
        publication_date=_parse_date(paper.get("publication_date")),
        reference_type="journal_article",
        authors=paper.get("authors", [])[:5],
        journal=paper.get("journal", ""),
        doi=paper.get("doi", ""),
        source_database="pubmed",
    )


def collect_reference(
    reference: PriorArtReference,
    refs_by_doi: dict[str, PriorArtReference],
    refs_no_doi: list[PriorArtReference],
) -> None:
    if reference.doi:
        refs_by_doi.setdefault(reference.doi, reference)
        return
    refs_no_doi.append(reference)


def filter_references_before_priority_date(
    references: list[PriorArtReference],
    priority_date: date,
) -> tuple[list[PriorArtReference], int]:
    filtered: list[PriorArtReference] = []
    skipped_post_priority = 0

    for reference in references:
        if reference.publication_date and reference.publication_date >= priority_date:
            skipped_post_priority += 1
            continue
        filtered.append(reference)

    return filtered, skipped_post_priority


def combine_scholarly_references(
    result_buckets: list[tuple[dict[str, PriorArtReference], list[PriorArtReference]]],
    priority_date: date,
) -> tuple[list[PriorArtReference], int, int, int, int]:
    """Merge scholarly result buckets and filter out post-priority publications."""
    refs_by_doi: dict[str, PriorArtReference] = {}
    refs_no_doi: list[PriorArtReference] = []

    for by_doi, no_doi in result_buckets:
        for doi, reference in by_doi.items():
            refs_by_doi.setdefault(doi, reference)
        refs_no_doi.extend(no_doi)

    all_references = list(refs_by_doi.values()) + refs_no_doi
    filtered_references, skipped_post_priority = filter_references_before_priority_date(
        all_references,
        priority_date,
    )
    return (
        filtered_references,
        skipped_post_priority,
        len(all_references),
        len(refs_by_doi),
        len(refs_no_doi),
    )
