"""Pure data-shaping helpers for chart generation."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from praviar_pipeline.models.analysis import PatentAnalysis, RiskLevel
from praviar_pipeline.rendering.design import RISK_LABEL

if TYPE_CHECKING:
    from praviar_pipeline.models.audit import PipelineAuditTrail


def fmt_duration(seconds: float) -> str:
    """Format a duration in seconds to a human-readable string."""
    if seconds < 0.1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    remaining = seconds - minutes * 60
    return f"{minutes}m {remaining:.0f}s"


def build_funnel_chart_data(audit_trail: PipelineAuditTrail) -> tuple[list[str], list[int]]:
    """Return funnel chart labels and counts."""
    stages = [
        "Discovered",
        "After Filters",
        "After Ranking",
        "After Triage",
        "Analyzed",
    ]
    counts = [
        audit_trail.total_patents_discovered,
        audit_trail.patents_after_hard_filter,
        audit_trail.patents_after_ranking,
        audit_trail.patents_after_triage,
        audit_trail.patents_analyzed,
    ]
    return stages, counts


def build_risk_distribution_series(
    analyses: list[PatentAnalysis],
) -> list[tuple[RiskLevel, str, int]]:
    """Return risk levels, labels, and counts in the display order."""
    risk_order = [RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW, RiskLevel.CLEAR]
    counts_map: dict[RiskLevel, int] = Counter(a.risk_level for a in analyses)

    series: list[tuple[RiskLevel, str, int]] = []
    for level in risk_order:
        count = counts_map.get(level, 0)
        if count > 0:
            series.append((level, RISK_LABEL.get(level, level.value.upper()), count))
    return series


def build_patent_timeline_entries(
    analyses: list[PatentAnalysis],
    patent_details: dict[str, dict[str, Any]] | None = None,
) -> list[tuple[str, date, date, RiskLevel]]:
    """Return ordered patent timeline entries with filing/expiry dates."""
    patent_details = patent_details or {}
    default_term = timedelta(days=20 * 365)

    entries: list[tuple[str, date, date, RiskLevel]] = []
    for analysis in analyses:
        expiry = analysis.expiry_date
        if expiry is None:
            continue

        detail = patent_details.get(analysis.patent_id, {})
        filing = detail.get("filing_date")
        if filing is None:
            filing = expiry - default_term

        entries.append((analysis.patent_id, filing, expiry, analysis.risk_level))

    entries.sort(key=lambda entry: entry[2])
    return entries


def build_assignee_series(analyses: list[PatentAnalysis]) -> list[tuple[str, int]]:
    """Return the top assignee counts in chart order."""
    assignee_counts: Counter[str] = Counter()
    for analysis in analyses:
        name = (analysis.assignee or "Unknown").strip()
        if name:
            assignee_counts[name] += 1

    top_10 = assignee_counts.most_common(10)
    top_10.reverse()
    return top_10


def build_timing_series(audit_trail: PipelineAuditTrail) -> list[tuple[str, float]]:
    """Return step names and durations for the timing waterfall."""
    return [(step.step_name, step.duration_seconds) for step in audit_trail.timing_data]


def normalize_source_entries(source_entries: list[Any]) -> list[tuple[str, str, int]]:
    """Return source entries as ``(name, status, count)`` tuples."""
    normalized: list[tuple[str, str, int]] = []
    for entry in source_entries:
        if isinstance(entry, dict):
            name = entry.get("source", "Unknown")
            status = entry.get("status", "OK")
            count = entry.get("patent_count", 0)
        else:
            name = getattr(entry, "source", "Unknown")
            status = getattr(entry, "status", "OK")
            count = getattr(entry, "patent_count", 0)

        normalized.append((name, str(status).upper(), count))

    normalized.reverse()
    return normalized
