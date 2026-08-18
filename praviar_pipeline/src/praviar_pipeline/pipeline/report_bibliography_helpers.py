"""Helper functions for deterministic bibliography assembly."""

from __future__ import annotations

from datetime import UTC, datetime

from praviar_pipeline.models.report import REPORT_DISCLAIMER
from praviar_pipeline.models.report_sections import BibliographyEntry, ReportSection
from praviar_pipeline.pipeline.report_validation.common import (
    extract_patent_ids,
    normalize_patent_id,
)


def google_patents_url(patent_id: str) -> str:
    """Build a Google Patents URL for a patent ID."""
    normalized = normalize_patent_id(patent_id)
    return f"https://patents.google.com/patent/{normalized}"


def doi_url(doi: str) -> str:
    """Build a DOI link."""
    if not doi:
        return ""
    return f"https://doi.org/{doi}"


def ptab_url(proceeding_number: str) -> str:
    """Build a PTAB case URL."""
    if not proceeding_number:
        return ""
    return f"https://ptab.uspto.gov/#/case/{proceeding_number}"


def collect_mentioned_patent_ids(sections: list[ReportSection]) -> set[str]:
    """Collect unique patent IDs mentioned in report sections."""
    mentioned_patent_ids: set[str] = set()
    for section in sections:
        mentioned_patent_ids.update(extract_patent_ids(section.content))
    return mentioned_patent_ids


def build_patent_entries(store, mentioned_ids: set[str]) -> list[BibliographyEntry]:
    """Build bibliography entries for mentioned patents."""
    entries = []
    for normalized_id in sorted(mentioned_ids):
        analysis = None
        detail = None
        for patent_id in store.all_patent_ids():
            if normalize_patent_id(patent_id) == normalized_id:
                analysis = store.get_analysis(patent_id)
                detail = store.get_patent_detail(patent_id)
                break

        entry = BibliographyEntry(
            ref_type="patent",
            patent_id=analysis.patent_id if analysis else normalized_id,
            title=analysis.title if analysis else "",
            assignee=analysis.assignee if analysis else "",
            expiry_date=str(analysis.expiry_date) if analysis and analysis.expiry_date else "",
            url=google_patents_url(normalized_id),
        )

        if detail:
            entry.filing_date = detail.get("filing_date", "")
            entry.grant_date = detail.get("grant_date", "")

        entries.append(entry)

    return entries


def build_prior_art_entries(store, mentioned_ids: set[str]) -> list[BibliographyEntry]:
    """Build bibliography entries for prior art references."""
    entries = []
    seen_titles: set[str] = set()

    for patent_id in store.all_patent_ids():
        if normalize_patent_id(patent_id) not in mentioned_ids:
            continue

        invalidity = store.get_invalidity(patent_id)
        if invalidity is None or not hasattr(invalidity, "prior_art"):
            continue

        for ref in invalidity.prior_art:
            title_key = ref.title[:100].lower().strip()
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            doi = ref.doi if hasattr(ref, "doi") else ""
            publication_date = (
                str(ref.publication_date)
                if hasattr(ref, "publication_date") and ref.publication_date
                else ""
            )

            entries.append(
                BibliographyEntry(
                    ref_type="prior_art",
                    title=ref.title[:300],
                    doi=doi,
                    publication_date=publication_date,
                    url=doi_url(doi),
                )
            )

    return entries


def build_ptab_entries(store, mentioned_ids: set[str]) -> list[BibliographyEntry]:
    """Build bibliography entries for PTAB proceedings."""
    entries = []
    seen_proceedings: set[str] = set()

    for patent_id in store.all_patent_ids():
        if normalize_patent_id(patent_id) not in mentioned_ids:
            continue

        invalidity = store.get_invalidity(patent_id)
        if invalidity is None or not hasattr(invalidity, "ptab") or invalidity.ptab is None:
            continue

        for proceeding in invalidity.ptab.proceedings:
            if proceeding.proceeding_number in seen_proceedings:
                continue
            seen_proceedings.add(proceeding.proceeding_number)

            entries.append(
                BibliographyEntry(
                    ref_type="ptab",
                    proceeding_number=proceeding.proceeding_number,
                    proceeding_type=proceeding.type,
                    proceeding_status=proceeding.status,
                    url=ptab_url(proceeding.proceeding_number),
                )
            )

    return entries


def format_appendix(entries: list[BibliographyEntry]) -> str:
    """Format entries as a professional reference appendix."""
    lines = [
        "═══════════════════════════════════════════════════════════════════",
        "REFERENCE APPENDIX",
        "═══════════════════════════════════════════════════════════════════",
    ]

    patent_entries = [entry for entry in entries if entry.ref_type == "patent"]
    if patent_entries:
        lines.append("\nPATENT REFERENCES:")
        for entry in patent_entries:
            parts = [f"  {entry.patent_id}"]
            if entry.assignee:
                parts.append(f"— {entry.assignee}")
            if entry.title:
                parts.append(f'— "{entry.title[:150]}"')
            line = " ".join(parts)
            dates = []
            if entry.filing_date:
                dates.append(f"Filed: {entry.filing_date}")
            if entry.grant_date:
                dates.append(f"Granted: {entry.grant_date}")
            if entry.expiry_date:
                dates.append(f"Expires: {entry.expiry_date}")
            if dates:
                line += f"\n    {' | '.join(dates)}"
            if entry.url:
                line += f"\n    {entry.url}"
            lines.append(line)

    prior_art_entries = [entry for entry in entries if entry.ref_type == "prior_art"]
    if prior_art_entries:
        lines.append("\nPRIOR ART REFERENCES:")
        for entry in prior_art_entries:
            parts = [f"  {entry.title[:200]}"]
            if entry.publication_date:
                parts.append(f"({entry.publication_date})")
            if entry.doi:
                parts.append(f"DOI: {entry.doi}")
            line = " ".join(parts)
            if entry.url:
                line += f"\n    {entry.url}"
            lines.append(line)

    ptab_entries = [entry for entry in entries if entry.ref_type == "ptab"]
    if ptab_entries:
        lines.append("\nPTAB PROCEEDINGS:")
        for entry in ptab_entries:
            line = (
                f"  {entry.proceeding_number} ({entry.proceeding_type}): {entry.proceeding_status}"
            )
            if entry.url:
                line += f"\n    {entry.url}"
            lines.append(line)

    return "\n".join(lines)


def assemble_report_text(
    sections: list[ReportSection],
    bibliography_text: str,
    compound_name: str,
    verification_score: float | None = None,
) -> str:
    """Concatenate report sections into the final report text."""
    now = datetime.now(UTC).strftime("%Y-%m-%d")

    header_lines = [
        "═══════════════════════════════════════════════════════════════════",
        f"FREEDOM-TO-OPERATE ANALYSIS — {compound_name.upper()}",
        f"Generated: {now} | Praviar FTO Analysis",
    ]
    if verification_score is not None:
        header_lines[-1] += f" | Verified: {verification_score:.0%}"
    header_lines.append("═══════════════════════════════════════════════════════════════════")

    parts = ["\n".join(header_lines)]
    parts.extend(section.content for section in sections)

    if bibliography_text:
        parts.append(bibliography_text)

    parts.append(
        "\n═══════════════════════════════════════════════════════════════════\n"
        "DISCLAIMER\n"
        "═══════════════════════════════════════════════════════════════════\n" + REPORT_DISCLAIMER
    )
    return "\n\n".join(parts)
