"""Bibliography builder + report assembler — deterministic, no LLM."""

import structlog

from praviar_pipeline.models.report_sections import BibliographyEntry, ReportSection
from praviar_pipeline.pipeline.report_bibliography_helpers import (
    assemble_report_text,
    build_patent_entries,
    build_prior_art_entries,
    build_ptab_entries,
    collect_mentioned_patent_ids,
    doi_url,
    format_appendix,
    google_patents_url,
    normalize_patent_id,
    ptab_url,
)
from praviar_pipeline.pipeline.report_data_store import ReportDataStore

logger = structlog.get_logger()
_normalize_patent_id = normalize_patent_id
_google_patents_url = google_patents_url
_doi_url = doi_url
_ptab_url = ptab_url


class BibliographyBuilder:
    """Builds a reference appendix from pipeline data for patents mentioned in the report."""

    def __init__(self, data_store: ReportDataStore) -> None:
        self._store = data_store

    def build(
        self,
        sections: list[ReportSection],
    ) -> tuple[str, list[BibliographyEntry]]:
        """Scan sections for references, build formatted appendix.

        Returns (appendix_text, entries_list).
        """
        mentioned_patent_ids = collect_mentioned_patent_ids(sections)

        entries: list[BibliographyEntry] = []
        patent_entries = build_patent_entries(self._store, mentioned_patent_ids)
        entries.extend(patent_entries)
        prior_art_entries = build_prior_art_entries(self._store, mentioned_patent_ids)
        entries.extend(prior_art_entries)
        ptab_entries = build_ptab_entries(self._store, mentioned_patent_ids)
        entries.extend(ptab_entries)
        appendix_text = format_appendix(entries)

        logger.info(
            "bibliography_built",
            patent_refs=len(patent_entries),
            prior_art_refs=len(prior_art_entries),
            ptab_refs=len(ptab_entries),
            total=len(entries),
        )

        return appendix_text, entries


def assemble_report(
    sections: list[ReportSection],
    bibliography_text: str,
    compound_name: str,
    verification_score: float | None = None,
) -> str:
    """Concatenate all sections into the final report text."""
    return assemble_report_text(
        sections=sections,
        bibliography_text=bibliography_text,
        compound_name=compound_name,
        verification_score=verification_score,
    )
