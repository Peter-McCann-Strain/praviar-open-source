"""Conclusion provenance and invalidation helpers for report-seeded monitors.

Patent-monitoring products traditionally stop at record deltas.  These helpers
bind the conclusions in a completed report to the patents, jurisdictions, and
sources they depend on so a later delta can identify which prior conclusions
are no longer safe to rely on without review.

The data is intentionally JSON-compatible.  Dependencies live in the monitor's
versioned strategy snapshot; unresolved impacts live on the monitor itself and
therefore survive later no-change scans.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from typing import Any

CONCLUSION_DEPENDENCY_VERSION = "2026-07-conclusion-dependency-v1"

_AGGREGATE_CONCLUSION_TYPES = {
    "clearance_decision",
    "jurisdiction_clearance",
}


def _text(value: object) -> str:
    return str(value or "").strip()


def _mapping(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _mappings(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dedupe(values: Iterable[object]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _jurisdiction(value: object) -> str:
    return _text(value).upper()


def _fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _patent_record_jurisdictions(report_data: dict[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    evidence_index = _mapping(report_data.get("matter_evidence_index"))
    for record in _mappings(evidence_index.get("patent_records")):
        patent_id = _text(record.get("patent_id"))
        jurisdiction = _jurisdiction(record.get("jurisdiction"))
        if patent_id and jurisdiction:
            result.setdefault(patent_id, set()).add(jurisdiction)
    return result


def _source_names(report_data: dict[str, Any]) -> list[str]:
    decision = _mapping(report_data.get("clearance_decision"))
    audit = _mapping(decision.get("decision_audit"))
    coverage = _mapping(audit.get("coverage_summary"))
    values: list[object] = []
    for key in (
        "queried_source_names",
        "successful_source_names",
        "failed_source_names",
        "authoritative_source_names",
        "supporting_source_names",
    ):
        values.extend(coverage.get(key) or [])

    span_map = _mapping(report_data.get("claim_source_span_map"))
    for span in _mapping(span_map.get("spans")).values():
        if isinstance(span, dict):
            values.append(span.get("source_name"))
    return _dedupe(values)


def _top_line_patent_ids(report_data: dict[str, Any]) -> list[str]:
    decision = _mapping(report_data.get("clearance_decision"))
    audit = _mapping(decision.get("decision_audit"))
    coverage = _mapping(audit.get("coverage_summary"))
    values: list[object] = []
    for key in (
        "reviewed_patent_ids",
        "reviewed_us_patent_ids",
        "reviewed_ep_patent_ids",
        "failed_analysis_patent_ids",
        "clearance_grade_ready_patent_ids",
        "incomplete_patent_ids",
    ):
        values.extend(coverage.get(key) or [])
    for reference in _mappings(audit.get("decisive_references")):
        values.append(reference.get("patent_id"))
    for analysis in _mappings(report_data.get("patent_analyses")):
        values.append(analysis.get("patent_id"))
    evidence_index = _mapping(report_data.get("matter_evidence_index"))
    for record in _mappings(evidence_index.get("patent_records")):
        values.append(record.get("patent_id"))
    return _dedupe(values)


def _add_dependency(
    dependencies: list[dict[str, Any]],
    *,
    conclusion_id: str,
    conclusion_type: str,
    label: str,
    outcome: str,
    source_report_id: str,
    source_report_generated_at: str,
    jurisdictions: Sequence[object],
    patent_ids: Sequence[object],
    claim_ids: Sequence[object] = (),
    source_names: Sequence[object] = (),
) -> None:
    if not conclusion_id or not outcome:
        return
    dependency = {
        "conclusion_id": conclusion_id,
        "conclusion_type": conclusion_type,
        "label": label,
        "outcome": outcome,
        "source_report_id": source_report_id,
        "source_report_generated_at": source_report_generated_at,
        "jurisdictions": _dedupe(_jurisdiction(value) for value in jurisdictions),
        "patent_ids": _dedupe(patent_ids),
        "claim_ids": _dedupe(claim_ids),
        "source_names": _dedupe(source_names),
    }
    dependency["dependency_fingerprint"] = _fingerprint(dependency)
    dependencies.append(dependency)


def build_conclusion_dependencies(report_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a deterministic dependency ledger from a completed FTO report.

    Only conclusions actually present in the report are emitted.  A manually
    created compound monitor has no prior opinion to invalidate and therefore
    gets an empty ledger rather than a synthetic legal conclusion.
    """

    dependencies: list[dict[str, Any]] = []
    source_report_id = _text(report_data.get("report_id"))
    source_report_generated_at = _text(report_data.get("generated_at"))
    source_names = _source_names(report_data)
    patent_jurisdictions = _patent_record_jurisdictions(report_data)

    clearance = _mapping(report_data.get("clearance_decision"))
    clearance_outcome = _text(clearance.get("decision")).lower()
    if clearance_outcome:
        _add_dependency(
            dependencies,
            conclusion_id="clearance:global",
            conclusion_type="clearance_decision",
            label="Overall FTO clearance",
            outcome=clearance_outcome,
            source_report_id=source_report_id,
            source_report_generated_at=source_report_generated_at,
            jurisdictions=[
                *(_mapping(report_data.get("decision_scope")).get("jurisdictions") or []),
                *[
                    decision.get("jurisdiction")
                    for decision in _mappings(report_data.get("jurisdiction_decisions"))
                ],
            ],
            patent_ids=_top_line_patent_ids(report_data),
            source_names=source_names,
        )

    for decision in _mappings(report_data.get("jurisdiction_decisions")):
        jurisdiction = _jurisdiction(decision.get("jurisdiction"))
        outcome = _text(decision.get("decision")).lower()
        if not jurisdiction or not outcome:
            continue
        patent_ids = _dedupe(
            [
                *(decision.get("reviewed_patent_ids") or []),
                *(decision.get("blocking_patent_ids") or []),
                *[
                    patent_id
                    for patent_id, jurisdictions in patent_jurisdictions.items()
                    if jurisdiction in jurisdictions
                ],
            ]
        )
        _add_dependency(
            dependencies,
            conclusion_id=f"clearance:{jurisdiction}",
            conclusion_type="jurisdiction_clearance",
            label=f"{jurisdiction} FTO clearance",
            outcome=outcome,
            source_report_id=source_report_id,
            source_report_generated_at=source_report_generated_at,
            jurisdictions=[jurisdiction],
            patent_ids=patent_ids,
            source_names=source_names,
        )

    claim_ids_by_patent: dict[str, list[str]] = {}
    for decision in _mappings(report_data.get("claim_program_decisions")):
        patent_id = _text(decision.get("patent_id"))
        claim_number = _text(decision.get("claim_number"))
        if patent_id and claim_number:
            claim_ids_by_patent.setdefault(patent_id, []).append(f"{patent_id}#claim{claim_number}")

    for analysis in _mappings(report_data.get("patent_analyses")):
        patent_id = _text(analysis.get("patent_id"))
        outcome = _text(analysis.get("risk_level")).lower()
        if not patent_id or not outcome:
            continue
        jurisdictions = sorted(patent_jurisdictions.get(patent_id, set()))
        _add_dependency(
            dependencies,
            conclusion_id=f"patent-risk:{patent_id}",
            conclusion_type="patent_risk",
            label=f"{patent_id} infringement risk",
            outcome=outcome,
            source_report_id=source_report_id,
            source_report_generated_at=source_report_generated_at,
            jurisdictions=jurisdictions,
            patent_ids=[patent_id],
            claim_ids=claim_ids_by_patent.get(patent_id, []),
            source_names=source_names,
        )

    return dependencies


def aggregate_conclusion_ids_for_jurisdiction(
    dependencies: Sequence[dict[str, Any]],
    jurisdiction: str,
) -> list[str]:
    """Return aggregate conclusions affected by a landscape change in a lane."""

    normalized_jurisdiction = _jurisdiction(jurisdiction)
    return _dedupe(
        dependency.get("conclusion_id")
        for dependency in dependencies
        if _text(dependency.get("conclusion_type")) in _AGGREGATE_CONCLUSION_TYPES
        and (
            dependency.get("conclusion_type") == "clearance_decision"
            or normalized_jurisdiction
            in {_jurisdiction(value) for value in dependency.get("jurisdictions") or []}
        )
    )


def bind_watch_targets_to_conclusions(
    watch_targets: Sequence[dict[str, Any]],
    dependencies: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach precise conclusion IDs to each monitor watch target."""

    bound: list[dict[str, Any]] = []
    for raw_target in watch_targets:
        target = dict(raw_target)
        jurisdiction = _jurisdiction(target.get("jurisdiction"))
        target_type = _text(target.get("target_type"))
        target_id = _text(target.get("target_id"))
        patent_id = target_id.split(":", 1)[0] if target_id else ""
        conclusion_ids = aggregate_conclusion_ids_for_jurisdiction(
            dependencies,
            jurisdiction,
        )

        if target_type != "compound" and patent_id:
            conclusion_ids = _dedupe(
                [
                    *conclusion_ids,
                    *[
                        dependency.get("conclusion_id")
                        for dependency in dependencies
                        if patent_id in set(dependency.get("patent_ids") or [])
                    ],
                ]
            )

        target["affected_conclusion_ids"] = conclusion_ids
        bound.append(target)
    return bound


def merge_stale_conclusions(
    existing: Sequence[dict[str, Any]],
    current: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge new impacts without ever clearing an unresolved stale conclusion."""

    merged: dict[str, dict[str, Any]] = {}
    ordered_ids: list[str] = []
    for impact in [*existing, *current]:
        conclusion_id = _text(impact.get("conclusion_id"))
        if not conclusion_id:
            continue
        if conclusion_id not in merged:
            merged[conclusion_id] = dict(impact)
            ordered_ids.append(conclusion_id)
            continue

        prior = merged[conclusion_id]
        incoming = dict(impact)
        prior_reason_codes = list(prior.get("reason_codes") or [])
        prior_patent_ids = list(prior.get("trigger_patent_ids") or [])
        prior_event_ids = list(prior.get("trigger_event_ids") or [])
        prior_jurisdictions = list(prior.get("jurisdictions") or [])
        first_invalidated_at = _text(prior.get("invalidated_at")) or _text(
            incoming.get("invalidated_at")
        )
        prior.update(incoming)
        prior["invalidated_at"] = first_invalidated_at
        prior["reason_codes"] = _dedupe(
            [
                *prior_reason_codes,
                *(impact.get("reason_codes") or []),
            ]
        )
        prior["trigger_patent_ids"] = _dedupe(
            [
                *prior_patent_ids,
                *(impact.get("trigger_patent_ids") or []),
            ]
        )
        prior["trigger_event_ids"] = _dedupe(
            [
                *prior_event_ids,
                *(impact.get("trigger_event_ids") or []),
            ]
        )
        prior["jurisdictions"] = _dedupe(
            [
                *prior_jurisdictions,
                *(impact.get("jurisdictions") or []),
            ]
        )

    return [merged[conclusion_id] for conclusion_id in ordered_ids]
