"""Deterministic policy helpers for report generation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import InsufficientDataError
from praviar_pipeline.models.analysis import PatentAnalysis, RiskLevel
from praviar_pipeline.models.report import (
    ActionItem,
    ActionPriority,
    ActionType,
    DataLimitation,
    SourceHealth,
    SourceStatus,
)
from praviar_pipeline.output_safety import safe_source_error_detail

if TYPE_CHECKING:
    from praviar_pipeline.models.equivalents import DoEAssessment
    from praviar_pipeline.models.invalidity import InvalidityAssessment

logger = structlog.get_logger()

# SG-112: refuse to render a report when too many data sources failed.
# Below this ratio (failed / queried, ignoring skipped), we continue with a
# degraded-confidence report; at or above, we raise InsufficientDataError so
# the pipeline never quietly ships an incomplete answer.
SOURCE_FAILURE_ABORT_THRESHOLD = 0.6
REGULATORY_SOURCE_HEALTH_SOURCES = frozenset(
    {
        "paragraph_iv",
        "pte_data",
        "purple_book",
        "orange_book",
    }
)


def _patent_search_source_entries(source_health: SourceHealth) -> list:
    return [
        entry
        for entry in source_health.entries
        if entry.source not in REGULATORY_SOURCE_HEALTH_SOURCES
    ]


def _source_entry_failed(entry) -> bool:
    return entry.status in {SourceStatus.FAILED, SourceStatus.NOT_CONFIGURED}


def _extract_action_items(
    analyses: list[PatentAnalysis],
    invalidity_assessments: list[InvalidityAssessment],
    *,
    patent_hits: list | None = None,
    intended_actions: list[str] | None = None,
    product_context: object = None,
) -> list[ActionItem]:
    """Create conservative pre-governance tasks from claim-coverage screens.

    Final mitigation actions are rebuilt after deterministic clearance governance.
    This early stage must never suggest licensing, design-around, challenge, halt,
    or risk acceptance from raw LLM risk labels.
    """
    _ = (
        invalidity_assessments,
        patent_hits,
        intended_actions,
        product_context,
    )
    items: list[ActionItem] = []
    for analysis in analyses:
        if analysis.risk_level not in {RiskLevel.HIGH, RiskLevel.MEDIUM}:
            continue
        items.append(
            ActionItem(
                action_type=ActionType.MONITOR,
                priority=(
                    ActionPriority.HIGH
                    if analysis.risk_level == RiskLevel.HIGH
                    else ActionPriority.MEDIUM
                ),
                description=(
                    f"Retain {analysis.patent_id} for deterministic claim, status, "
                    "jurisdiction, accused-act, territory, timing, and evidence governance."
                ),
                patent_ids=[analysis.patent_id],
                reasoning=(
                    "This is an upstream claim-coverage screen only. Final mitigation "
                    "is withheld until governed clearance reconciliation."
                ),
            )
        )
    return items


def _validate_data_sufficiency(source_health: SourceHealth) -> None:
    """Raise if we don't have enough data to produce a reliable report.

    NOT_CONFIGURED sources are expected absences (no API key configured) and
    are excluded from the failure ratio — they are already captured in
    data_limitations for the report consumer. Only sources that were actively
    queried and then returned an unexpected error count toward the threshold.
    """
    search_entries = _patent_search_source_entries(source_health)
    # Only count sources that were actually attempted, not merely unconfigured.
    queried = [
        e
        for e in search_entries
        if e.status not in {SourceStatus.SKIPPED, SourceStatus.NOT_CONFIGURED}
    ]
    failed = [e for e in queried if e.status == SourceStatus.FAILED]
    failed_sources = [e.source for e in failed]

    if queried and len(failed) == len(queried):
        raise InsufficientDataError(
            f"All search sources failed: {failed_sources}. Cannot produce a reliable FTO report.",
            step="report",
        )

    if not queried:
        raise InsufficientDataError(
            "No queried search sources are available. Cannot produce a reliable FTO report.",
            step="report",
        )
    if not failed:
        return
    failure_ratio = len(failed) / len(queried)
    if failure_ratio >= SOURCE_FAILURE_ABORT_THRESHOLD:
        raise InsufficientDataError(
            f"Too many search sources failed ({len(failed)}/{len(queried)} = "
            f"{failure_ratio:.0%}, threshold {SOURCE_FAILURE_ABORT_THRESHOLD:.0%}). "
            f"Failed sources: {failed_sources}. "
            "Cannot produce a reliable FTO report.",
            step="report",
        )


def _determine_overall_risk(
    analyses: list[PatentAnalysis],
    doe_assessments: list[DoEAssessment],
    source_health: SourceHealth | None = None,
) -> RiskLevel:
    """Determine overall risk level from individual patent analyses."""
    if any(a.risk_level == RiskLevel.HIGH for a in analyses):
        return RiskLevel.HIGH

    doe_equivalents = {
        (d.patent_id, d.claim_number)
        for d in doe_assessments
        if (
            d.overall_equivalent is True
            and d.confidence_band == "HIGH"
            and d.estoppel.estoppel_applies is False
            and d.estoppel.file_wrapper_available
            and d.fwr is not None
            and all(
                value is True
                for value in (
                    d.fwr.same_function,
                    d.fwr.same_way,
                    d.fwr.same_result,
                )
            )
        )
    }
    for a in analyses:
        if a.risk_level == RiskLevel.MEDIUM:
            for claim in a.claims_analyzed:
                if (a.patent_id, claim.claim_number) in doe_equivalents:
                    return RiskLevel.HIGH

    if any(a.risk_level == RiskLevel.MEDIUM for a in analyses):
        return RiskLevel.MEDIUM

    if any(a.risk_level == RiskLevel.LOW for a in analyses):
        return RiskLevel.LOW

    # Source-health downgrade on CLEAR: if any queried source failed, we refuse
    # to report "all clear" — the coverage is by definition incomplete, so the
    # floor is LOW. This matches the PDF coverage banner's "Confidence impact"
    # text, which previously was informational only while the risk rollup
    # silently stayed at CLEAR.
    # Only clamps CLEAR; MEDIUM/HIGH results earned by real analyses are
    # never downgraded (handled by the returns above).
    # ``SourceHealth(entries=[])`` is treated as "no signal" (same as None)
    # because no queries were recorded at all — ``any_failed`` is already
    # False in that case so we naturally fall through.
    if source_health is not None:
        search_entries = _patent_search_source_entries(source_health)
        any_failed = any(_source_entry_failed(entry) for entry in search_entries)
        primary_succeeded = any(
            entry.source == "pubchem_sdq" and entry.status == SourceStatus.OK
            for entry in search_entries
        )
        # A source that returned zero patents is a data gap, not evidence of
        # clearance — we cannot distinguish "nothing relevant exists" from
        # "the source is silently empty / mis-configured".  The floor is LOW
        # whenever any non-failed, non-skipped source returned 0 patents.
        zero_result_sources = [
            entry.source
            for entry in search_entries
            if not _source_entry_failed(entry)
            and entry.status != SourceStatus.SKIPPED
            and entry.patent_count == 0
        ]
        any_zero_results = bool(zero_result_sources)
        if search_entries and (any_failed or not primary_succeeded or any_zero_results):
            floor_reasons: list[str] = []
            if any_failed:
                floor_reasons.append("source_failure")
            if not primary_succeeded:
                floor_reasons.append("primary_source_not_ok")
            if any_zero_results:
                floor_reasons.append("zero_result_data_gap")
            logger.warning(
                "risk_floor_applied",
                floor=RiskLevel.LOW.value,
                zero_result_sources=zero_result_sources,
                failed_sources=[e.source for e in search_entries if _source_entry_failed(e)],
            )
            return RiskLevel.LOW

    return RiskLevel.CLEAR


def _identify_key_risks(analyses: list[PatentAnalysis]) -> list[str]:
    """Extract key risk points for executive summary."""
    settings = get_settings()
    risks = []
    for a in analyses:
        if a.risk_level in (RiskLevel.HIGH, RiskLevel.MEDIUM):
            risks.append(
                f"{a.patent_id} ({a.assignee}): {a.risk_level.value} risk — {a.risk_summary}"
            )
    return risks[: settings.invalidity_display_top_n]


def _build_data_limitations(
    source_health: SourceHealth | None,
    invalidity_assessments: list[InvalidityAssessment],
    analyses: list[PatentAnalysis],
) -> list[DataLimitation]:
    """Collect data-quality limitations from source failures and coverage gaps."""
    limitations: list[DataLimitation] = []

    if source_health and source_health.any_failed:
        for entry in source_health.entries:
            if entry.status in {SourceStatus.FAILED, SourceStatus.NOT_CONFIGURED}:
                category = (
                    "source_not_configured"
                    if entry.status == SourceStatus.NOT_CONFIGURED
                    else "source_unavailable"
                )
                limitations.append(
                    DataLimitation(
                        category=category,
                        description=(
                            f"{entry.source} search incomplete: "
                            f"{safe_source_error_detail(entry.error_message, status=entry.status)}"
                        ),
                        impact=f"Patents from {entry.source} may be missing from results",
                    )
                )

    if not invalidity_assessments and any(
        a.risk_level in (RiskLevel.HIGH, RiskLevel.MEDIUM) for a in analyses
    ):
        limitations.append(
            DataLimitation(
                category="enrichment_gap",
                description="No invalidity assessments produced for blocking patents",
                impact="Potential invalidity arguments not evaluated",
            )
        )

    return limitations
