"""Pure helper logic for the agentic search loop."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from praviar_pipeline.models.search import ExpandedSearchQueries
from praviar_pipeline.models.triage import Relevance

if TYPE_CHECKING:
    from praviar_pipeline.models.patent import PatentHit
    from praviar_pipeline.models.triage import TriageResult


def compute_search_stats(patent_hits: list[PatentHit]) -> str:
    """Compute statistics about search results for coverage assessment."""
    if not patent_hits:
        return "No patents found."

    assignee_counter: Counter[str] = Counter()
    for hit in patent_hits:
        for assignee in hit.assignees:
            assignee_counter[assignee] += 1
    assignee_lines = [f"  {name}: {count}" for name, count in assignee_counter.most_common(15)]

    cpc_counter: Counter[str] = Counter()
    for hit in patent_hits:
        for code in hit.cpc_codes:
            subclass = code[:4] if len(code) >= 4 else code
            cpc_counter[subclass] += 1
    cpc_lines = [f"  {code}: {count}" for code, count in cpc_counter.most_common(15)]

    source_counter: Counter[str] = Counter()
    for hit in patent_hits:
        for source in hit.sources:
            source_counter[source.value] += 1
    source_lines = [f"  {src}: {count}" for src, count in source_counter.most_common()]

    filing_dates = [hit.filing_date for hit in patent_hits if hit.filing_date]
    date_range = ""
    if filing_dates:
        earliest = min(filing_dates)
        latest = max(filing_dates)
        date_range = f"Filing date range: {earliest} to {latest}"

    high = sum(1 for hit in patent_hits if hit.confidence_score >= 0.8)
    medium = sum(1 for hit in patent_hits if 0.5 <= hit.confidence_score < 0.8)
    low = sum(1 for hit in patent_hits if hit.confidence_score < 0.5)

    jurisdiction_counter: Counter[str] = Counter()
    for hit in patent_hits:
        if hit.patent_id and len(hit.patent_id) >= 2:
            jurisdiction_counter[hit.patent_id[:2]] += 1
    jurisdiction_lines = [f"  {cc}: {count}" for cc, count in jurisdiction_counter.most_common()]

    parts = [
        f"Total unique patents: {len(patent_hits)}",
        f"\nConfidence distribution: high={high}, medium={medium}, low={low}",
        f"\n{date_range}" if date_range else "",
        f"\nAssignee distribution ({len(assignee_counter)} unique):",
        "\n".join(assignee_lines) if assignee_lines else "  (none)",
        f"\nCPC subclass distribution ({len(cpc_counter)} unique):",
        "\n".join(cpc_lines) if cpc_lines else "  (none)",
        "\nSource distribution:",
        "\n".join(source_lines) if source_lines else "  (none)",
        "\nJurisdiction distribution:",
        "\n".join(jurisdiction_lines) if jurisdiction_lines else "  (none)",
    ]
    return "\n".join(parts)


def compute_triage_stats(
    triage_results: list[TriageResult],
    all_triage: list[TriageResult],
) -> str:
    """Compute triage statistics for coverage assessment."""
    if not all_triage:
        return "No patents triaged yet."

    relevant = sum(1 for triage in all_triage if triage.relevance == Relevance.RELEVANT)
    possibly = sum(1 for triage in all_triage if triage.relevance == Relevance.POSSIBLY_RELEVANT)
    not_rel = sum(1 for triage in all_triage if triage.relevance == Relevance.NOT_RELEVANT)

    relevant_confs = [
        triage.confidence for triage in all_triage if triage.relevance == Relevance.RELEVANT
    ]
    avg_conf = sum(relevant_confs) / len(relevant_confs) if relevant_confs else 0.0

    new_relevant_count = sum(
        1
        for triage in triage_results
        if triage.relevance in (Relevance.RELEVANT, Relevance.POSSIBLY_RELEVANT)
    )

    parts = [
        f"Total triaged: {len(all_triage)}",
        f"  Relevant: {relevant}",
        f"  Possibly relevant: {possibly}",
        f"  Not relevant: {not_rel}",
        f"  Average confidence (relevant): {avg_conf:.2f}",
        (
            f"New in this iteration: {len(triage_results)} triaged, "
            f"{new_relevant_count} relevant/possibly"
        ),
    ]
    return "\n".join(parts)


def merge_queries(
    base: ExpandedSearchQueries,
    new: ExpandedSearchQueries,
) -> ExpandedSearchQueries:
    """Merge two ExpandedSearchQueries, deduplicating terms while preserving order."""
    return ExpandedSearchQueries(
        patent_synonyms=list(dict.fromkeys(base.patent_synonyms + new.patent_synonyms)),
        cpc_codes=list(dict.fromkeys(base.cpc_codes + new.cpc_codes)),
        key_assignees=list(dict.fromkeys(base.key_assignees + new.key_assignees)),
        process_keywords=list(dict.fromkeys(base.process_keywords + new.process_keywords)),
        compound_class_terms=list(
            dict.fromkeys(base.compound_class_terms + new.compound_class_terms),
        ),
        provenance=(new.provenance if new.provenance.origin != "unknown" else base.provenance),
    )
