"""Shared evidence-scope wording for generated report artifacts."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from praviar_pipeline.models.report_common import SourceStatus
from praviar_pipeline.output_safety import safe_source_error_detail

if TYPE_CHECKING:
    from praviar_pipeline.models.report import FTOReport
    from praviar_pipeline.models.report_common import SourceHealthEntry


@dataclass(frozen=True)
class EvidenceScopeSummary:
    """Reader-facing summary of source-health for exports."""

    total_sources: int
    successful_sources: tuple[str, ...]
    unavailable_sources: tuple[str, ...]
    skipped_sources: tuple[str, ...]
    headline: str
    posture: str
    confidence_impact: str
    review_note: str


JURISDICTION_NAMES: dict[str, str] = {
    "US": "United States Patent and Trademark Office",
    "EP": "European Patent Office",
    "WO": "World Intellectual Property Organization",
    "JP": "Japan Patent Office",
    "KR": "Korean Intellectual Property Office",
    "CN": "China National Intellectual Property Administration",
    "IN": "Indian Patent Office",
    "CA": "Canadian Intellectual Property Office",
    "AU": "IP Australia",
    "UK": "United Kingdom Intellectual Property Office",
    "GB": "United Kingdom Intellectual Property Office",
    "DE": "German Patent and Trade Mark Office",
    "FR": "French National Industrial Property Institute",
}

_JURISDICTION_ORDER = tuple(JURISDICTION_NAMES)
_PATENT_PREFIX_RE = re.compile(r"^([A-Z]{2})(?:[/\d])")


def _source_name(entry: SourceHealthEntry) -> str:
    return entry.source.replace("_", " ").strip() or "unknown source"


def _source_status_bucket(entry: SourceHealthEntry) -> str:
    if entry.status == SourceStatus.OK:
        return "successful"
    if entry.status in {SourceStatus.FAILED, SourceStatus.NOT_CONFIGURED}:
        return "unavailable"
    return "skipped"


def source_status_label(entry: SourceHealthEntry) -> str:
    """Return a text-first status label for accessibility and print."""
    if entry.status == SourceStatus.OK:
        return "Successful"
    if entry.status == SourceStatus.NOT_CONFIGURED:
        return "Not configured"
    if entry.status == SourceStatus.FAILED:
        return "Unavailable"
    return "Skipped"


def source_status_detail(entry: SourceHealthEntry) -> str:
    """Return compact source-health detail for generated artifacts."""
    pieces = [source_status_label(entry)]
    if entry.patent_count:
        pieces.append(f"{entry.patent_count:,} patents")
    detail = safe_source_error_detail(entry.error_message, status=entry.status)
    if detail:
        pieces.append(detail)
    return " | ".join(pieces)


def format_source_list(names: tuple[str, ...], *, empty: str) -> str:
    if not names:
        return empty
    if len(names) <= 6:
        return ", ".join(names)
    visible = ", ".join(names[:6])
    return f"{visible}, +{len(names) - 6} more"


def _read_field(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _as_iterable(value: Any) -> Iterable[Any]:
    if value is None or isinstance(value, (str, bytes)):
        return ()
    if isinstance(value, Iterable):
        return value
    return ()


def _normalize_jurisdiction(value: Any) -> str:
    code = str(value or "").strip().upper()
    if not code:
        return ""
    if code in {"GB"}:
        return "UK"
    return code if re.fullmatch(r"[A-Z]{2}", code) else ""


def _jurisdiction_from_patent_id(value: Any) -> str:
    patent_id = str(value or "").strip().upper()
    match = _PATENT_PREFIX_RE.match(patent_id)
    if not match:
        return ""
    return _normalize_jurisdiction(match.group(1))


def _extend_jurisdictions(values: list[str], items: Iterable[Any]) -> None:
    for item in items:
        code = _normalize_jurisdiction(item)
        if code:
            values.append(code)


def _dedupe_jurisdictions(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for preferred in _JURISDICTION_ORDER:
        if preferred in values and preferred not in seen:
            ordered.append(preferred)
            seen.add(preferred)
    for value in values:
        if value and value not in seen:
            ordered.append(value)
            seen.add(value)
    return tuple(ordered)


def collect_reported_jurisdiction_codes(report_data: Mapping[str, Any]) -> tuple[str, ...]:
    """Collect jurisdictions explicitly present in report data.

    This intentionally reports recorded scope signals only. It does not infer
    that every authority in a jurisdiction was exhaustively searched.
    """

    values: list[str] = []
    for scope_key in ("decision_scope", "supporting_scope"):
        scope = _read_field(report_data, scope_key, {}) or {}
        _extend_jurisdictions(values, _as_iterable(_read_field(scope, "jurisdictions", ())))

    certification_scope = _read_field(report_data, "certification_scope", {}) or {}
    for key in (
        "certified_jurisdictions",
        "supported_jurisdictions",
        "supporting_only_jurisdictions",
    ):
        _extend_jurisdictions(
            values,
            _as_iterable(_read_field(certification_scope, key, ())),
        )

    for decision in _as_iterable(_read_field(report_data, "jurisdiction_decisions", ())):
        code = _normalize_jurisdiction(_read_field(decision, "jurisdiction", ""))
        if code:
            values.append(code)

    for directive in _as_iterable(_read_field(report_data, "evidence_collection_plan", ())):
        _extend_jurisdictions(
            values,
            _as_iterable(_read_field(directive, "target_jurisdictions", ())),
        )

    for analysis in _as_iterable(_read_field(report_data, "patent_analyses", ())):
        code = _normalize_jurisdiction(_read_field(analysis, "jurisdiction", ""))
        if not code:
            code = _jurisdiction_from_patent_id(_read_field(analysis, "patent_id", ""))
        if code:
            values.append(code)

    patent_details = _read_field(report_data, "patent_details", {}) or {}
    if isinstance(patent_details, Mapping):
        for patent_id, detail in patent_details.items():
            code = _normalize_jurisdiction(_read_field(detail, "jurisdiction", ""))
            if not code:
                code = _jurisdiction_from_patent_id(_read_field(detail, "patent_id", patent_id))
            if code:
                values.append(code)

    return _dedupe_jurisdictions(values)


def build_evidence_scope_payload(report_data: Mapping[str, Any]) -> dict[str, Any]:
    """Build a renderer-safe payload that avoids overclaiming search scope."""

    source_health = _read_field(report_data, "source_health", {}) or {}
    entries = tuple(_as_iterable(_read_field(source_health, "entries", ())))
    sources_used = tuple(
        str(source).strip()
        for source in _as_iterable(_read_field(report_data, "search_sources_used", ()))
        if str(source).strip()
    )
    ok_entries = tuple(
        entry for entry in entries if _read_field(entry, "status", "") == SourceStatus.OK
    )
    configured_sources = (
        tuple(
            str(_read_field(entry, "source", "")).strip()
            for entry in entries
            if str(_read_field(entry, "source", "")).strip()
        )
        or sources_used
    )

    if entries:
        source_claim = (
            f"{len(ok_entries)} of {len(entries)} configured source requests completed. "
            "Only successful source-health entries are treated as completed-source evidence."
        )
        patent_search_step = (
            "Patents are retrieved from the configured source set recorded in "
            "source-health telemetry; unavailable, not-configured, or skipped "
            "sources remain explicit limitations."
        )
    elif configured_sources:
        source_claim = (
            f"{len(configured_sources)} configured source names were recorded, "
            "but source-health outcomes were not recorded."
        )
        patent_search_step = (
            "Patents are retrieved from recorded configured sources, but this "
            "artifact lacks per-source completion telemetry."
        )
    else:
        source_claim = "No configured patent source telemetry was recorded."
        patent_search_step = (
            "Patent source completion was not recorded in this artifact; review "
            "the run configuration before relying on negative findings."
        )

    jurisdiction_codes = collect_reported_jurisdiction_codes(report_data)
    jurisdiction_items = [
        {
            "code": code,
            "name": JURISDICTION_NAMES.get(code, f"{code} patent authority"),
        }
        for code in jurisdiction_codes
    ]
    if jurisdiction_codes:
        jurisdiction_claim = (
            "Recorded jurisdiction signals in this artifact: "
            f"{', '.join(jurisdiction_codes)}. This is report scope evidence, "
            "not a representation of exhaustive global FTO clearance."
        )
    else:
        jurisdiction_claim = (
            "No jurisdiction scope metadata was recorded; do not infer "
            "jurisdictional clearance from this artifact."
        )

    return {
        "configured_source_count": len(configured_sources),
        "completed_source_count": len(ok_entries),
        "source_claim": source_claim,
        "patent_search_step": patent_search_step,
        "reported_jurisdictions": jurisdiction_items,
        "jurisdiction_claim": jurisdiction_claim,
        "coverage_caveat": (
            "Scope statements describe recorded sources, jurisdictions, and "
            "patent records. They do not certify that all possible patents, "
            "families, continuations, translations, legal events, or local "
            "claim-construction issues were exhausted."
        ),
    }


def summarize_evidence_scope(report: FTOReport) -> EvidenceScopeSummary:
    """Summarize source-health without overstating legal coverage."""
    entries = tuple(report.source_health.entries)
    if not entries:
        fallback_sources = tuple(
            source.replace("_", " ").strip()
            for source in report.search_sources_used
            if source.strip()
        )
        headline = (
            f"{len(fallback_sources)} configured search sources listed"
            if fallback_sources
            else "Source-health telemetry not recorded"
        )
        return EvidenceScopeSummary(
            total_sources=len(fallback_sources),
            successful_sources=(),
            unavailable_sources=(),
            skipped_sources=(),
            headline=headline,
            posture="Evidence scope requires reviewer confirmation",
            confidence_impact=("Source-health telemetry was not included with this artifact."),
            review_note=("Verify the configured source list before relying on risk conclusions."),
        )

    successful = tuple(
        _source_name(entry) for entry in entries if _source_status_bucket(entry) == "successful"
    )
    unavailable = tuple(
        _source_name(entry) for entry in entries if _source_status_bucket(entry) == "unavailable"
    )
    skipped = tuple(
        _source_name(entry) for entry in entries if _source_status_bucket(entry) == "skipped"
    )

    headline = f"{len(successful)} of {len(entries)} configured sources completed"

    if unavailable:
        posture = "Review required before relying on absence-of-risk conclusions"
        confidence_impact = (
            "High: multiple sources were unavailable."
            if len(unavailable) >= 3
            else "Moderate: at least one configured source was unavailable."
        )
        review_note = "Review unavailable sources before relying on the evidence packet."
    elif skipped:
        posture = "Scope limited by configured skips"
        confidence_impact = "Low: some sources were intentionally skipped."
        review_note = "Confirm skipped sources match the matter scope and client risk tolerance."
    else:
        posture = "Configured source requests completed"
        confidence_impact = "No unavailable or skipped configured sources were recorded."
        review_note = "This is still an AI-assisted screening report, not a legal opinion."

    return EvidenceScopeSummary(
        total_sources=len(entries),
        successful_sources=successful,
        unavailable_sources=unavailable,
        skipped_sources=skipped,
        headline=headline,
        posture=posture,
        confidence_impact=confidence_impact,
        review_note=review_note,
    )
