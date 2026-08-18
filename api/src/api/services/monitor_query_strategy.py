"""Watch-target derivation, monitoring strategy, and query planning.

Pure data-shaping over a hydrated report dict and a Monitor row. No DB
writes or outbound provider calls happen in this module.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from api.db.models import Monitor
from api.services.monitor_conclusion_dependencies import (
    CONCLUSION_DEPENDENCY_VERSION,
    aggregate_conclusion_ids_for_jurisdiction,
    bind_watch_targets_to_conclusions,
    build_conclusion_dependencies,
)

MONITOR_STRATEGY_VERSION = "2026-07-monitor-v2"
AUTO_FULL_REFRESH_DAYS = 30
DEFAULT_MONITOR_JURISDICTIONS = ["US", "EP", "UK"]
QUERY_CAPS = {
    "diff_only": 4,
    "targeted_refresh": 6,
    "full_refresh": 10,
}
JURISDICTION_PROVIDER_PLAN = {
    "US": ["uspto_odp", "patentsview", "ptab", "orange_book", "purple_book"],
    "EP": ["epo_ops", "patentscope"],
    "UK": ["patentscope"],
}

_TARGET_PRIORITY = {
    "patent": 0,
    "application": 1,
    "ep_register_status": 2,
    "ep_opposition": 2,
    "ep_unitary_effect": 2,
    "ep_upc_opt_out": 2,
    "uk_validation_state": 2,
    "risk_signal": 3,
    "family": 4,
    "compound": 5,
}


def _text(value: object) -> str:
    return str(value or "").strip()


def watch_target_coverage_key(target: dict[str, Any]) -> str:
    """Return the stable lane/type/target identity used by coverage receipts."""

    return "|".join(
        [
            _text(target.get("jurisdiction")).upper() or "GLOBAL",
            _text(target.get("target_type")),
            _text(target.get("target_id")),
        ]
    )


def build_monitor_coverage_manifest(
    watch_targets: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Persist every target/conclusion edge; no query budget may truncate it."""

    manifest = [
        {
            "coverage_key": watch_target_coverage_key(target),
            "jurisdiction": _text(target.get("jurisdiction")).upper() or "GLOBAL",
            "target_type": _text(target.get("target_type")),
            "target_id": _text(target.get("target_id")),
            "affected_conclusion_ids": dedupe_strings(target.get("affected_conclusion_ids") or []),
            "priority": _TARGET_PRIORITY.get(
                _text(target.get("target_type")),
                99,
            ),
        }
        for target in watch_targets
        if _text(target.get("target_id"))
    ]
    return sorted(
        manifest,
        key=lambda item: (
            item["priority"],
            item["jurisdiction"],
            item["target_type"],
            item["target_id"],
        ),
    )


def dedupe_strings(values: Sequence[object]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def schedule_interval_days(schedule: str) -> int:
    normalized = _text(schedule).lower()
    if normalized == "daily":
        return 1
    if normalized == "monthly":
        return 30
    return 7


def selected_jurisdictions(report_data: dict[str, Any]) -> list[str]:
    values: list[object] = []
    values.extend(report_data.get("target_jurisdictions", []) or [])
    for entry in report_data.get("jurisdiction_matrix", []) or []:
        if isinstance(entry, dict):
            values.append(entry.get("jurisdiction"))
    if not values:
        values.extend(DEFAULT_MONITOR_JURISDICTIONS)
    return dedupe_strings(values)


def _report_search_terms(report_data: dict[str, Any]) -> dict[str, str]:
    final_assessment = (report_data.get("search_loop_result") or {}).get("final_assessment") or {}
    suggested_queries = final_assessment.get("suggested_queries") or {}
    terms: dict[str, str] = {}
    for key in ("key_assignees", "cpc_codes", "compound_class_terms", "process_keywords"):
        values = suggested_queries.get(key) or []
        if values:
            first = _text(values[0])
            if first:
                terms[key] = first
    if "key_assignees" not in terms:
        assignees = dedupe_strings(
            [
                analysis.get("assignee")
                for analysis in report_data.get("patent_analyses", []) or []
                if isinstance(analysis, dict)
            ]
        )
        if assignees:
            terms["key_assignees"] = assignees[0]
    return terms


@dataclass
class _WatchTargetAccumulator:
    targets: list[dict[str, Any]] = field(default_factory=list)
    seen: set[tuple[str, str, str]] = field(default_factory=set)

    def add(
        self,
        *,
        jurisdiction: str,
        target_type: str,
        target_id: str,
        label: str,
        check_kind: str,
        source: str,
        lane_status: str = "",
    ) -> None:
        key = (jurisdiction, target_type, target_id)
        if not jurisdiction or not target_id or key in self.seen:
            return
        self.seen.add(key)
        self.targets.append(
            {
                "jurisdiction": jurisdiction,
                "target_type": target_type,
                "target_id": target_id,
                "label": label,
                "check_kind": check_kind,
                "source": source,
                "lane_status": lane_status or "screening_only",
            }
        )


def _jurisdiction_matrix(report_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        _text(entry.get("jurisdiction")).upper(): entry
        for entry in report_data.get("jurisdiction_matrix", []) or []
        if isinstance(entry, dict) and _text(entry.get("jurisdiction"))
    }


def _lane_status(matrix_by_jurisdiction: dict[str, dict[str, Any]], jurisdiction: str) -> str:
    return _text(matrix_by_jurisdiction.get(jurisdiction, {}).get("lane_status"))


def _add_ep_and_uk_register_targets(
    accumulator: _WatchTargetAccumulator,
    patent_record: dict[str, Any],
    *,
    jurisdiction: str,
    patent_id: str,
    matrix_by_jurisdiction: dict[str, dict[str, Any]],
) -> None:
    source = "matter_evidence_index.patent_records"
    if jurisdiction == "EP":
        register_status = _text(patent_record.get("ep_register_status"))
        if register_status:
            accumulator.add(
                jurisdiction="EP",
                target_type="ep_register_status",
                target_id=f"{patent_id}:ep_register_status:{register_status}",
                label=f"{patent_id} EP register status",
                check_kind="event_delta",
                source=source,
                lane_status=_lane_status(matrix_by_jurisdiction, "EP"),
            )
        if bool(patent_record.get("has_opposition_events")):
            accumulator.add(
                jurisdiction="EP",
                target_type="ep_opposition",
                target_id=f"{patent_id}:ep_opposition",
                label=f"{patent_id} EP opposition",
                check_kind="event_delta",
                source=source,
                lane_status=_lane_status(matrix_by_jurisdiction, "EP"),
            )
        event_specs = (
            (
                "ep_unitary_effect",
                _text(patent_record.get("ep_unitary_effect_status")),
                "unitary effect",
            ),
            (
                "ep_upc_opt_out",
                _text(patent_record.get("ep_upc_opt_out_status")),
                "UPC opt-out",
            ),
        )
        for target_type, status, label_suffix in event_specs:
            if status:
                accumulator.add(
                    jurisdiction="EP",
                    target_type=target_type,
                    target_id=f"{patent_id}:{target_type}:{status}",
                    label=f"{patent_id} {label_suffix}",
                    check_kind="event_delta",
                    source=source,
                    lane_status=_lane_status(matrix_by_jurisdiction, "EP"),
                )

    ep_validation_states = {
        _text(value).upper()
        for value in (patent_record.get("ep_validation_states") or [])
        if _text(value)
    }
    if "UK" in ep_validation_states:
        accumulator.add(
            jurisdiction="UK",
            target_type="uk_validation_state",
            target_id=f"{patent_id}:uk_validation_state",
            label=f"{patent_id} UK validation",
            check_kind="event_delta",
            source=source,
            lane_status=_lane_status(matrix_by_jurisdiction, "UK"),
        )


def _add_indexed_patent_targets(
    accumulator: _WatchTargetAccumulator,
    report_data: dict[str, Any],
    matrix_by_jurisdiction: dict[str, dict[str, Any]],
) -> set[str]:
    indexed_patent_ids: set[str] = set()
    for patent_record in (report_data.get("matter_evidence_index") or {}).get(
        "patent_records"
    ) or []:
        if not isinstance(patent_record, dict):
            continue
        jurisdiction = _text(patent_record.get("jurisdiction")).upper()
        patent_id = _text(patent_record.get("patent_id"))
        if not jurisdiction or not patent_id:
            continue
        indexed_patent_ids.add(patent_id)
        source = "matter_evidence_index.patent_records"
        lane_status = _lane_status(matrix_by_jurisdiction, jurisdiction)
        accumulator.add(
            jurisdiction=jurisdiction,
            target_type="patent",
            target_id=patent_id,
            label=_text(patent_record.get("title") or patent_id),
            check_kind="exact_identifier",
            source=source,
            lane_status=lane_status,
        )
        family_id = _text(patent_record.get("family_id"))
        if family_id:
            accumulator.add(
                jurisdiction=jurisdiction,
                target_type="family",
                target_id=family_id,
                label=f"Family {family_id}",
                check_kind="family_delta",
                source=source,
                lane_status=lane_status,
            )
        _add_ep_and_uk_register_targets(
            accumulator,
            patent_record,
            jurisdiction=jurisdiction,
            patent_id=patent_id,
            matrix_by_jurisdiction=matrix_by_jurisdiction,
        )
    return indexed_patent_ids


def _add_unindexed_patent_targets(
    accumulator: _WatchTargetAccumulator,
    report_data: dict[str, Any],
    indexed_patent_ids: set[str],
) -> None:
    for patent_analysis in report_data.get("patent_analyses", []) or []:
        if not isinstance(patent_analysis, dict):
            continue
        patent_id = _text(patent_analysis.get("patent_id"))
        if not patent_id or patent_id in indexed_patent_ids:
            continue
        accumulator.add(
            jurisdiction="GLOBAL",
            target_type="patent",
            target_id=patent_id,
            label=_text(patent_analysis.get("title") or patent_id),
            check_kind="exact_identifier",
            source="patent_analyses",
            lane_status="screening_only",
        )


def _add_report_finding_targets(
    accumulator: _WatchTargetAccumulator,
    report_data: dict[str, Any],
    matrix_by_jurisdiction: dict[str, dict[str, Any]],
) -> None:
    for finding in report_data.get("future_risk", []) or []:
        if not isinstance(finding, dict):
            continue
        jurisdiction = _text(finding.get("jurisdiction")).upper()
        patent_id = _text(finding.get("patent_id"))
        risk_type = _text(finding.get("risk_type"))
        if jurisdiction and patent_id:
            accumulator.add(
                jurisdiction=jurisdiction,
                target_type="risk_signal",
                target_id=f"{patent_id}:{risk_type or 'risk'}",
                label=f"{patent_id} {risk_type or 'risk'}",
                check_kind="event_delta",
                source="future_risk",
                lane_status=_lane_status(matrix_by_jurisdiction, jurisdiction),
            )

    for finding in report_data.get("prosecution_findings", []) or []:
        if not isinstance(finding, dict):
            continue
        jurisdiction = _text(finding.get("jurisdiction")).upper()
        patent_id = _text(finding.get("patent_id"))
        application_number = _text(finding.get("application_number"))
        if jurisdiction and application_number:
            accumulator.add(
                jurisdiction=jurisdiction,
                target_type="application",
                target_id=application_number,
                label=f"{patent_id or application_number} prosecution",
                check_kind="dossier_delta",
                source="prosecution_findings",
                lane_status=_lane_status(matrix_by_jurisdiction, jurisdiction),
            )


def build_monitor_watch_targets(
    report_data: dict[str, Any],
    *,
    compound_name: str,
) -> list[dict[str, Any]]:
    """Derive bounded, low-cost watch targets from a completed report."""
    accumulator = _WatchTargetAccumulator()
    matrix_by_jurisdiction = _jurisdiction_matrix(report_data)
    indexed_patent_ids = _add_indexed_patent_targets(
        accumulator, report_data, matrix_by_jurisdiction
    )

    # Some completed reports retain the decision-grade patent set without a
    # hydrated matter-evidence index. Preserve those exact identifiers as
    # global targets so every jurisdiction lane can prioritize them instead of
    # silently degrading to compound-only monitoring.
    _add_unindexed_patent_targets(accumulator, report_data, indexed_patent_ids)
    _add_report_finding_targets(accumulator, report_data, matrix_by_jurisdiction)

    jurisdictions = selected_jurisdictions(report_data)
    for jurisdiction in jurisdictions:
        if compound_name:
            accumulator.add(
                jurisdiction=jurisdiction,
                target_type="compound",
                target_id=f"{jurisdiction}:{compound_name}",
                label=f"{compound_name} {jurisdiction}",
                check_kind="jurisdiction_refresh",
                source="compound",
                lane_status=_lane_status(matrix_by_jurisdiction, jurisdiction),
            )

    return accumulator.targets


def build_monitoring_strategy(
    report_data: dict[str, Any],
    *,
    schedule: str,
    compound_name: str,
) -> dict[str, Any]:
    jurisdictions = selected_jurisdictions(report_data)
    search_terms = _report_search_terms(report_data)
    risk_summary = report_data.get("risk_summary") or {}
    overall_risk = _text(risk_summary.get("overall_risk")).lower() or "unknown"

    return {
        "version": MONITOR_STRATEGY_VERSION,
        "execution_model": "conclusion_aware_event_first",
        "default_run_mode": "diff_only",
        "schedule": _text(schedule).lower() or "weekly",
        "full_refresh_cadence_days": AUTO_FULL_REFRESH_DAYS,
        "auto_bigquery_enabled": False,
        "targeted_refresh_on_change": True,
        "query_caps": copy.deepcopy(QUERY_CAPS),
        "query_budget_note": (
            "Automatic monitor runs avoid full landscape reruns and keep BigQuery "
            "out of the default loop."
        ),
        "compound_name": compound_name,
        "overall_risk": overall_risk,
        "jurisdictions": jurisdictions,
        "providers_preferred": [
            provider
            for jurisdiction in jurisdictions
            for provider in JURISDICTION_PROVIDER_PLAN.get(jurisdiction, [])
        ],
        "search_terms": search_terms,
    }


def build_monitor_seed_from_report(
    report_data: dict[str, Any],
    *,
    schedule: str,
    compound_name: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str], str]:
    strategy = build_monitoring_strategy(
        report_data,
        schedule=schedule,
        compound_name=compound_name,
    )
    conclusion_dependencies = build_conclusion_dependencies(report_data)
    strategy["conclusion_dependency_version"] = CONCLUSION_DEPENDENCY_VERSION
    strategy["conclusion_dependencies"] = conclusion_dependencies
    watch_targets = bind_watch_targets_to_conclusions(
        build_monitor_watch_targets(report_data, compound_name=compound_name),
        conclusion_dependencies,
    )
    strategy["coverage_manifest"] = build_monitor_coverage_manifest(watch_targets)
    jurisdictions = selected_jurisdictions(report_data)
    jurisdiction_bundle = _text(report_data.get("jurisdiction_bundle") or "custom") or "custom"
    return strategy, watch_targets, jurisdictions, jurisdiction_bundle


def lane_targets(watch_targets: list[dict[str, Any]], jurisdiction: str) -> list[dict[str, Any]]:
    return sorted(
        [
            target
            for target in watch_targets
            if _text(target.get("jurisdiction")).upper() in {jurisdiction.upper(), "GLOBAL"}
        ],
        key=lambda target: (
            _TARGET_PRIORITY.get(_text(target.get("target_type")), 99),
            _text(target.get("target_id")),
        ),
    )


def build_monitor_queries(
    monitor: Monitor,
    *,
    report_data: dict[str, Any],
    run_mode: str,
) -> list[dict[str, Any]]:
    watch_targets = list(monitor.watch_targets or [])
    strategy = dict(monitor.monitoring_strategy or {})
    jurisdictions = list(monitor.target_jurisdictions or strategy.get("jurisdictions") or [])
    compound_name = _text(
        ((report_data.get("compound") or {}).get("name")) or monitor.compound_name
    )
    search_terms = dict(strategy.get("search_terms") or {})

    conclusion_dependencies = [
        dependency
        for dependency in strategy.get("conclusion_dependencies") or []
        if isinstance(dependency, dict)
    ]
    queries: list[dict[str, Any]] = []

    def add_query(
        jurisdiction: str,
        query: str,
        reason: str,
        *,
        watch_target_ids: Sequence[object] = (),
        coverage_keys: Sequence[object] = (),
        affected_conclusion_ids: Sequence[object] = (),
    ) -> None:
        normalized = (jurisdiction.upper(), query.strip().lower())
        if not query.strip():
            return
        existing = next(
            (
                item
                for item in queries
                if (
                    _text(item.get("jurisdiction")).upper(),
                    _text(item.get("query")).lower(),
                )
                == normalized
            ),
            None,
        )
        if existing is not None:
            existing["watch_target_ids"] = dedupe_strings(
                [*(existing.get("watch_target_ids") or []), *watch_target_ids]
            )
            existing["affected_conclusion_ids"] = dedupe_strings(
                [
                    *(existing.get("affected_conclusion_ids") or []),
                    *affected_conclusion_ids,
                ]
            )
            existing["coverage_keys"] = dedupe_strings(
                [*(existing.get("coverage_keys") or []), *coverage_keys]
            )
            return
        queries.append(
            {
                "jurisdiction": jurisdiction.upper(),
                "query": query.strip(),
                "reason": reason,
                "watch_target_ids": dedupe_strings(watch_target_ids),
                "coverage_keys": dedupe_strings(coverage_keys),
                "affected_conclusion_ids": dedupe_strings(affected_conclusion_ids),
                "required_provider_names": list(
                    JURISDICTION_PROVIDER_PLAN.get(jurisdiction.upper(), [])
                ),
            }
        )

    for jurisdiction in jurisdictions:
        for target in lane_targets(watch_targets, jurisdiction):
            target_type = _text(target.get("target_type"))
            target_id = _text(target.get("target_id"))
            affected_conclusion_ids = dedupe_strings(
                [
                    *(target.get("affected_conclusion_ids") or []),
                    *aggregate_conclusion_ids_for_jurisdiction(
                        conclusion_dependencies,
                        jurisdiction,
                    ),
                ]
            )
            coverage_key = watch_target_coverage_key(target)
            if target_type in {"patent", "application"}:
                add_query(
                    jurisdiction,
                    target_id,
                    f"Exact identifier monitor check for {target_type}.",
                    watch_target_ids=[target_id],
                    coverage_keys=[coverage_key],
                    affected_conclusion_ids=affected_conclusion_ids,
                )
            elif target_type in {
                "ep_register_status",
                "ep_opposition",
                "ep_unitary_effect",
                "ep_upc_opt_out",
                "uk_validation_state",
            }:
                patent_id = target_id.split(":", 1)[0]
                add_query(
                    jurisdiction,
                    patent_id,
                    f"Post-grant register monitor check for {target_type}.",
                    watch_target_ids=[target_id],
                    coverage_keys=[coverage_key],
                    affected_conclusion_ids=affected_conclusion_ids,
                )
            elif target_type == "family":
                add_query(
                    jurisdiction,
                    f"{compound_name} {jurisdiction} family {target_id}".strip(),
                    "Family delta monitor check.",
                    watch_target_ids=[target_id],
                    coverage_keys=[coverage_key],
                    affected_conclusion_ids=affected_conclusion_ids,
                )
            elif target_type == "risk_signal":
                add_query(
                    jurisdiction,
                    target_id.split(":", 1)[0],
                    "Bound future-risk signal monitor check.",
                    watch_target_ids=[target_id],
                    coverage_keys=[coverage_key],
                    affected_conclusion_ids=affected_conclusion_ids,
                )
            elif target_type == "compound":
                add_query(
                    jurisdiction,
                    f"{compound_name} {jurisdiction} patent".strip(),
                    "Jurisdiction compound watch coverage.",
                    watch_target_ids=[target_id],
                    coverage_keys=[coverage_key],
                    affected_conclusion_ids=affected_conclusion_ids,
                )

    if run_mode in {"targeted_refresh", "full_refresh"} and compound_name:
        for jurisdiction in jurisdictions:
            aggregate_conclusion_ids = aggregate_conclusion_ids_for_jurisdiction(
                conclusion_dependencies,
                jurisdiction,
            )
            add_query(
                jurisdiction,
                f"{compound_name} {jurisdiction} patent",
                "Jurisdiction-scoped targeted refresh.",
                affected_conclusion_ids=aggregate_conclusion_ids,
            )
            if search_terms.get("key_assignees"):
                assignee_query = (
                    f'{compound_name} assignee "{search_terms["key_assignees"]}" {jurisdiction}'
                ).strip()
                add_query(
                    jurisdiction,
                    assignee_query,
                    "Assignee-targeted refresh query.",
                    affected_conclusion_ids=aggregate_conclusion_ids,
                )
            if run_mode == "full_refresh" and search_terms.get("cpc_codes"):
                add_query(
                    jurisdiction,
                    f"{compound_name} CPC {search_terms['cpc_codes']} {jurisdiction}".strip(),
                    "Bounded full-refresh CPC query.",
                    affected_conclusion_ids=aggregate_conclusion_ids,
                )

    return queries
