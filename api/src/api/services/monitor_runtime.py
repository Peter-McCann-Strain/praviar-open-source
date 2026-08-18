"""Low-cost monitor execution orchestration.

This module is intentionally thin: it holds the cross-cutting orchestration
(``execute_monitor_run``, ``hydrate_monitor_from_source_analysis``, and
``load_due_monitor_ids``) and re-exports the public surface that callers
have historically imported from this module. Implementation details live
in three sibling modules:

* ``monitor_query_strategy`` — watch-target derivation, query planning
* ``monitor_delta_computation`` — snapshot + delta diff
* ``monitor_alert_factory`` — alert row construction
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import Analysis, Monitor, MonitorAlert, MonitorSchedule
from api.errors import APIError
from api.schemas.monitors import MonitorConclusionImpact, MonitorRunResponse
from api.services.monitor_alert_factory import alert_warranted, build_monitor_alert
from api.services.monitor_conclusion_dependencies import merge_stale_conclusions
from api.services.monitor_delta_computation import (
    MonitorRunDelta,
    build_run_summary,
    build_snapshot,
    diff_snapshot,
)
from api.services.monitor_query_strategy import (
    AUTO_FULL_REFRESH_DAYS,
    MONITOR_STRATEGY_VERSION,
    QUERY_CAPS,
    build_monitor_queries,
    build_monitor_seed_from_report,
    build_monitor_watch_targets,
    build_monitoring_strategy,
    dedupe_strings,
)
from api.services.monitor_reassessment_lifecycle import (
    record_monitor_conclusion_invalidations,
)
from api.services.report_access import (
    normalize_report_trust_mode,
    require_completed_report_payload,
)
from api.services.report_evidence_search import search_external_evidence_impl

logger = structlog.get_logger()

MAX_DUE_MONITOR_DISPATCH_BATCH = 500
MONITOR_SNAPSHOT_SCHEMA_VERSION = "2026-07-monitor-snapshot-v2"
MONITOR_EVIDENCE_VERSION = "2026-07-monitor-evidence-v1"


class _ExternalEvidenceSearch(Protocol):
    async def __call__(
        self,
        report: dict[str, Any],
        query_text: str,
        *,
        org_id: str | uuid.UUID | None = None,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class _MonitorRunPlan:
    now: datetime
    report_data: dict[str, Any]
    run_mode: str
    all_queries: list[dict[str, Any]]
    queries: list[dict[str, Any]]
    plan_sha256: str
    previous_snapshot: dict[str, Any]
    accumulator: dict[str, Any]
    cursor: int


@dataclass(frozen=True)
class _MonitorRunPage:
    provider_names: list[str]
    snapshot: dict[str, Any]
    next_cursor: int
    coverage_complete: bool


__all__ = [
    "MONITOR_STRATEGY_VERSION",
    "MAX_DUE_MONITOR_DISPATCH_BATCH",
    "MonitorRunDelta",
    "build_monitor_seed_from_report",
    "build_monitor_watch_targets",
    "build_monitoring_strategy",
    "execute_monitor_run",
    "get_monitor_for_run",
    "hydrate_monitor_from_source_analysis",
    "load_due_monitor_ids",
    "load_due_monitor_refs",
]


def _text(value: object) -> str:
    return str(value or "").strip()


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _completed_snapshot(last_snapshot: object) -> dict[str, Any]:
    if not isinstance(last_snapshot, dict):
        return {}
    if last_snapshot.get("schema_version") == MONITOR_SNAPSHOT_SCHEMA_VERSION:
        completed = last_snapshot.get("completed_snapshot")
        return dict(completed) if isinstance(completed, dict) else {}
    return dict(last_snapshot)


def _coverage_progress(last_snapshot: object) -> dict[str, Any]:
    if (
        isinstance(last_snapshot, dict)
        and last_snapshot.get("schema_version") == MONITOR_SNAPSHOT_SCHEMA_VERSION
        and isinstance(last_snapshot.get("coverage_progress"), dict)
    ):
        return dict(last_snapshot["coverage_progress"])
    return {}


def _merge_signal_rows(
    existing: object,
    current: object,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for raw in [
        *(existing if isinstance(existing, list) else []),
        *(current if isinstance(current, list) else []),
    ]:
        if not isinstance(raw, dict):
            continue
        signal_id = _text(raw.get("signal_id"))
        if not signal_id:
            continue
        prior = merged.setdefault(signal_id, dict(raw))
        prior["jurisdictions"] = dedupe_strings(
            [
                *(prior.get("jurisdictions") or []),
                *(raw.get("jurisdictions") or []),
            ]
        )
        prior["conclusion_ids"] = dedupe_strings(
            [
                *(prior.get("conclusion_ids") or []),
                *(raw.get("conclusion_ids") or []),
            ]
        )
    return list(merged.values())


def _merge_snapshot_pages(
    existing: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    if not existing:
        return copy.deepcopy(current)
    merged = copy.deepcopy(existing)
    merged["generated_at"] = current.get("generated_at")
    merged["run_mode"] = current.get("run_mode")
    for key in (
        "provider_names",
        "watch_target_ids",
        "completed_coverage_keys",
        "observed_patent_ids",
        "observed_event_ids",
    ):
        merged[key] = dedupe_strings(
            [
                *(merged.get(key) or []),
                *(current.get(key) or []),
            ]
        )
    for key in (
        "observed_patent_signals",
        "observed_event_signals",
        "observed_record_signals",
    ):
        merged[key] = _merge_signal_rows(merged.get(key), current.get(key))
    existing_fingerprints = merged.get("observed_record_fingerprints")
    current_fingerprints = current.get("observed_record_fingerprints")
    merged["observed_record_fingerprints"] = {
        **(existing_fingerprints if isinstance(existing_fingerprints, dict) else {}),
        **(current_fingerprints if isinstance(current_fingerprints, dict) else {}),
    }
    existing_receipts = merged.get("provider_execution_receipts")
    current_receipts = current.get("provider_execution_receipts")
    merged["provider_execution_receipts"] = [
        *(existing_receipts if isinstance(existing_receipts, list) else []),
        *(current_receipts if isinstance(current_receipts, list) else []),
    ]
    jurisdiction_deltas: dict[str, dict[str, int]] = {}
    for source in (merged.get("jurisdiction_deltas"), current.get("jurisdiction_deltas")):
        if not isinstance(source, dict):
            continue
        for jurisdiction, counts in source.items():
            if not isinstance(counts, dict):
                continue
            target = jurisdiction_deltas.setdefault(
                str(jurisdiction),
                {"result_count": 0, "patent_count": 0, "event_count": 0},
            )
            for count_key in target:
                target[count_key] += int(counts.get(count_key) or 0)
    merged["jurisdiction_deltas"] = jurisdiction_deltas
    return merged


def _bind_impact_evidence(
    impacts: list[dict[str, Any]],
    *,
    snapshot: dict[str, Any],
    alert_id: uuid.UUID,
) -> None:
    """Bind impacts to the exact alert and completed execution receipt set."""

    observed_at = _text(snapshot.get("generated_at"))
    receipt_sha256 = _canonical_sha256(snapshot.get("provider_execution_receipts") or [])
    for impact in impacts:
        material = {
            "alert_id": str(alert_id),
            "conclusion_id": impact.get("conclusion_id"),
            "dependency_fingerprint": impact.get("dependency_fingerprint"),
            "source_report_id": impact.get("source_report_id"),
            "invalidated_at": impact.get("invalidated_at"),
            "reason_codes": impact.get("reason_codes") or [],
            "trigger_patent_ids": impact.get("trigger_patent_ids") or [],
            "trigger_event_ids": impact.get("trigger_event_ids") or [],
            "jurisdictions": impact.get("jurisdictions") or [],
            "provider_execution_receipts_sha256": receipt_sha256,
            "evidence_version": MONITOR_EVIDENCE_VERSION,
            "evidence_observed_at": observed_at,
        }
        impact["alert_id"] = str(alert_id)
        impact["evidence_digest"] = _canonical_sha256(material)
        impact["evidence_version"] = MONITOR_EVIDENCE_VERSION
        impact["evidence_observed_at"] = observed_at


def _synthesized_monitor_report(monitor: Monitor) -> dict[str, Any]:
    return {
        "trust_mode": "monitor",
        "compound": {
            "name": monitor.compound_name,
            "canonical_smiles": monitor.compound_smiles,
        },
        "target_jurisdictions": list(monitor.target_jurisdictions or []),
        "jurisdiction_bundle": _text(monitor.jurisdiction_bundle or "custom") or "custom",
        "routing_profile": {
            "modality": (_text((monitor.monitoring_strategy or {}).get("modality")) or "unknown"),
            "capability_profile": "monitor_budgeted",
        },
        "jurisdiction_matrix": [
            {
                "jurisdiction": target.get("jurisdiction"),
                "lane_status": target.get("lane_status") or "monitor_only",
                "local_review_required": True,
                "authority_grade": "public_monitoring",
            }
            for target in monitor.watch_targets or []
            if isinstance(target, dict) and _text(target.get("jurisdiction"))
        ],
        "search_loop_result": {
            "final_assessment": {
                "suggested_queries": (monitor.monitoring_strategy or {}).get("search_terms", {}),
            }
        },
    }


async def hydrate_monitor_from_source_analysis(
    db: AsyncSession,
    *,
    monitor: Monitor,
) -> dict[str, Any]:
    if monitor.source_analysis_id is None:
        return _synthesized_monitor_report(monitor)

    result = await db.execute(
        select(Analysis).where(
            Analysis.id == monitor.source_analysis_id,
            Analysis.org_id == monitor.org_id,
        )
    )
    analysis = result.scalar_one_or_none()
    if analysis is None:
        raise APIError(
            409,
            "Conflict",
            "The source analysis is unavailable, so this report-linked monitor "
            "cannot establish current conclusion state.",
        )

    try:
        source_report = require_completed_report_payload(analysis)
    except APIError as exc:
        logger.warning(
            "monitor_source_report_failed_provenance",
            monitor_id=str(monitor.id),
            source_analysis_id=str(monitor.source_analysis_id),
        )
        raise APIError(
            409,
            "Conflict",
            "The source report no longer satisfies completed-report provenance. "
            "The monitoring run was refused without changing conclusion currency.",
        ) from exc

    report_data = copy.deepcopy(source_report)
    report_data["trust_mode"] = "monitor"
    strategy, watch_targets, jurisdictions, jurisdiction_bundle = build_monitor_seed_from_report(
        report_data,
        schedule=str(monitor.schedule),
        compound_name=monitor.compound_name
        or _text((report_data.get("compound") or {}).get("name")),
    )
    monitor.source_report_id = _text(report_data.get("report_id"))
    monitor.source_trust_mode = normalize_report_trust_mode(source_report)
    monitor.monitoring_strategy = strategy
    monitor.strategy_version = strategy["version"]
    monitor.watch_targets = watch_targets
    monitor.target_jurisdictions = jurisdictions
    monitor.jurisdiction_bundle = jurisdiction_bundle
    return report_data


def _determine_run_mode(
    monitor: Monitor,
    *,
    now: datetime,
    force_full_refresh: bool,
) -> str:
    progress = _coverage_progress(monitor.last_snapshot)
    if progress and progress.get("complete") is False:
        pending_mode = _text(progress.get("run_mode"))
        if pending_mode in {"bootstrap", "diff_only", "targeted_refresh", "full_refresh"}:
            return pending_mode
    if force_full_refresh:
        return "full_refresh"
    if not monitor.last_snapshot:
        return "bootstrap"
    if monitor.last_full_refresh_at is None:
        return "targeted_refresh"
    if now - monitor.last_full_refresh_at >= timedelta(days=AUTO_FULL_REFRESH_DAYS):
        return "full_refresh"
    return "diff_only"


def _provider_receipts(response: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_receipts = response.get("provider_executions")
    if not isinstance(raw_receipts, list):
        raise APIError(
            503,
            "Monitor provider coverage incomplete",
            "External evidence retrieval did not return explicit execution/completeness receipts.",
        )
    receipts_by_provider: dict[str, dict[str, Any]] = {}
    for raw_receipt in raw_receipts:
        if not isinstance(raw_receipt, dict):
            continue
        provider_name = _text(raw_receipt.get("provider_name"))
        if provider_name:
            receipts_by_provider[provider_name] = raw_receipt
    return receipts_by_provider


def _require_complete_provider_coverage(
    query_spec: dict[str, Any],
    receipts_by_provider: dict[str, dict[str, Any]],
) -> None:
    required_providers = dedupe_strings(query_spec.get("required_provider_names") or [])
    missing_providers = [
        provider for provider in required_providers if provider not in receipts_by_provider
    ]
    failed_providers = [
        provider
        for provider, receipt in receipts_by_provider.items()
        if receipt.get("status") != "succeeded"
        or (
            int(receipt.get("result_count") or 0) == 0
            and receipt.get("explicit_zero_results") is not True
        )
    ]
    if missing_providers or failed_providers:
        raise APIError(
            503,
            "Monitor provider coverage incomplete",
            "Required provider execution was incomplete; "
            f"missing={missing_providers}, failed={sorted(failed_providers)}.",
        )


def _monitor_evidence_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in (response.get("results") or [])
        if isinstance(item, dict)
        and _text(item.get("artifact_type")) != "provider_notice"
        and _text(item.get("section")) != "external_provider_notice"
        and _text(item.get("authority_tier")) != "governance"
    ]


def _query_result(
    query_spec: dict[str, Any],
    response: dict[str, Any],
    receipts_by_provider: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "jurisdiction": query_spec["jurisdiction"],
        "query": query_spec["query"],
        "reason": query_spec["reason"],
        "watch_target_ids": list(query_spec.get("watch_target_ids") or []),
        "coverage_keys": list(query_spec.get("coverage_keys") or []),
        "affected_conclusion_ids": list(query_spec.get("affected_conclusion_ids") or []),
        "execution_receipts": list(receipts_by_provider.values()),
        "response": {**response, "results": _monitor_evidence_rows(response)},
    }


async def _execute_queries(
    report_data: dict[str, Any],
    *,
    queries: list[dict[str, Any]],
    org_id: uuid.UUID,
    external_search_fn: _ExternalEvidenceSearch = search_external_evidence_impl,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    provider_names: list[str] = []
    execution_receipts: list[dict[str, Any]] = []
    for query_spec in queries:
        response = await external_search_fn(
            report_data,
            query_spec["query"],
            org_id=org_id,
        )
        receipts_by_provider = _provider_receipts(response)
        _require_complete_provider_coverage(query_spec, receipts_by_provider)
        for provider_name, receipt in receipts_by_provider.items():
            provider_names.append(provider_name)
            execution_receipts.append(
                {
                    **receipt,
                    "jurisdiction": query_spec["jurisdiction"],
                    "coverage_keys": list(query_spec.get("coverage_keys") or []),
                    "query_sha256": _canonical_sha256(query_spec["query"]),
                }
            )
        results.append(_query_result(query_spec, response, receipts_by_provider))
    return results, dedupe_strings(provider_names), execution_receipts


def _initialize_monitor_strategy(
    monitor: Monitor,
    report_data: dict[str, Any],
) -> None:
    if monitor.monitoring_strategy:
        return
    strategy, watch_targets, jurisdictions, jurisdiction_bundle = build_monitor_seed_from_report(
        report_data,
        schedule=str(monitor.schedule),
        compound_name=monitor.compound_name,
    )
    monitor.monitoring_strategy = strategy
    monitor.watch_targets = watch_targets
    monitor.target_jurisdictions = jurisdictions
    monitor.jurisdiction_bundle = jurisdiction_bundle


def _monitor_plan_material(all_queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "jurisdiction": query.get("jurisdiction"),
            "query": query.get("query"),
            "coverage_keys": query.get("coverage_keys") or [],
            "required_provider_names": query.get("required_provider_names") or [],
            "affected_conclusion_ids": query.get("affected_conclusion_ids") or [],
        }
        for query in all_queries
    ]


def _build_monitor_run_plan(
    monitor: Monitor,
    *,
    report_data: dict[str, Any],
    now: datetime,
    force_full_refresh: bool,
) -> _MonitorRunPlan:
    run_mode = _determine_run_mode(
        monitor,
        now=now,
        force_full_refresh=force_full_refresh,
    )
    planning_mode = "full_refresh" if run_mode == "bootstrap" else run_mode
    all_queries = build_monitor_queries(
        monitor,
        report_data=report_data,
        run_mode=planning_mode,
    )
    if not all_queries:
        raise APIError(
            409,
            "Monitor coverage plan empty",
            "The monitor has no executable target coverage plan and cannot be marked current.",
        )

    plan_sha256 = _canonical_sha256(_monitor_plan_material(all_queries))
    prior_state = dict(monitor.last_snapshot or {})
    previous_snapshot = _completed_snapshot(prior_state)
    prior_progress = _coverage_progress(prior_state)
    continuing_progress = bool(
        prior_progress.get("complete") is False
        and prior_progress.get("plan_sha256") == plan_sha256
        and prior_progress.get("run_mode") == run_mode
    )
    cursor = int(prior_progress.get("cursor") or 0) if continuing_progress else 0
    accumulator = (
        dict(prior_progress.get("accumulator") or {})
        if continuing_progress and isinstance(prior_progress.get("accumulator"), dict)
        else {}
    )
    query_cap = QUERY_CAPS.get(planning_mode, QUERY_CAPS["diff_only"])
    queries = all_queries[cursor : cursor + query_cap]
    if not queries:
        raise APIError(
            409,
            "Monitor coverage cursor invalid",
            "The persisted monitor coverage cursor no longer matches its sealed plan.",
        )
    return _MonitorRunPlan(
        now=now,
        report_data=report_data,
        run_mode=run_mode,
        all_queries=all_queries,
        queries=queries,
        plan_sha256=plan_sha256,
        previous_snapshot=previous_snapshot,
        accumulator=accumulator,
        cursor=cursor,
    )


async def _execute_monitor_page(
    monitor: Monitor,
    plan: _MonitorRunPlan,
    *,
    external_search_fn: _ExternalEvidenceSearch,
) -> _MonitorRunPage:
    try:
        query_results, provider_names, execution_receipts = await asyncio.wait_for(
            _execute_queries(
                plan.report_data,
                queries=plan.queries,
                org_id=monitor.org_id,
                external_search_fn=external_search_fn,
            ),
            timeout=60.0,
        )
    except TimeoutError as exc:
        raise APIError(
            503,
            "Monitor run timed out",
            "External evidence providers did not respond within 60s.",
        ) from exc
    page_snapshot = build_snapshot(
        run_mode=plan.run_mode,
        query_results=query_results,
        provider_names=provider_names,
        watch_targets=list(monitor.watch_targets or []),
        now=plan.now,
    )
    page_snapshot["provider_execution_receipts"] = execution_receipts
    snapshot = _merge_snapshot_pages(plan.accumulator, page_snapshot)
    next_cursor = plan.cursor + len(plan.queries)
    return _MonitorRunPage(
        provider_names=provider_names,
        snapshot=snapshot,
        next_cursor=next_cursor,
        coverage_complete=next_cursor >= len(plan.all_queries),
    )


def _validate_coverage_manifest(monitor: Monitor, page: _MonitorRunPage) -> None:
    coverage_manifest = [
        item
        for item in (monitor.monitoring_strategy or {}).get("coverage_manifest", [])
        if isinstance(item, dict)
    ]
    required_coverage_keys = {
        _text(item.get("coverage_key"))
        for item in coverage_manifest
        if _text(item.get("coverage_key"))
    }
    completed_coverage_keys = {
        _text(value) for value in page.snapshot.get("completed_coverage_keys") or [] if _text(value)
    }
    if page.coverage_complete and not required_coverage_keys.issubset(completed_coverage_keys):
        missing_coverage = sorted(required_coverage_keys - completed_coverage_keys)
        raise APIError(
            500,
            "Monitor coverage manifest mismatch",
            f"The query plan did not cover required targets: {missing_coverage}.",
        )


async def _persist_partial_monitor_run(
    db: AsyncSession,
    *,
    monitor: Monitor,
    plan: _MonitorRunPlan,
    page: _MonitorRunPage,
) -> MonitorRunResponse:
    partial_summary = (
        f"Completed {page.next_cursor} of {len(plan.all_queries)} sealed monitor queries. "
        "Conclusion currency remains unavailable until every target and provider "
        "receipt is complete."
    )
    monitor.last_run_at = None
    monitor.last_run_mode = plan.run_mode
    monitor.last_run_status = "coverage_incomplete"
    monitor.last_run_summary = partial_summary
    monitor.conclusion_status = (
        "review_required" if list(monitor.stale_conclusions or []) else "coverage_incomplete"
    )
    monitor.last_snapshot = {
        "schema_version": MONITOR_SNAPSHOT_SCHEMA_VERSION,
        "completed_snapshot": plan.previous_snapshot,
        "coverage_progress": {
            "plan_sha256": plan.plan_sha256,
            "run_mode": plan.run_mode,
            "cursor": page.next_cursor,
            "total_queries": len(plan.all_queries),
            "complete": False,
            "accumulator": page.snapshot,
        },
    }
    monitor.scan_execution_id = None
    monitor.scan_lease_expires_at = None
    await db.commit()
    await db.refresh(monitor)
    return MonitorRunResponse(
        monitor_id=monitor.id,
        run_mode=plan.run_mode,
        status="partial",
        summary=partial_summary,
        query_count=len(plan.queries),
        alert_created=False,
        new_patent_count=0,
        next_recommended_mode=plan.run_mode,
        provider_names=page.provider_names,
        conclusion_status=monitor.conclusion_status,
        stale_conclusion_count=len(monitor.stale_conclusions or []),
        coverage_complete=False,
        coverage_cursor=page.next_cursor,
        coverage_total=len(plan.all_queries),
    )


def _monitor_conclusion_dependencies(monitor: Monitor) -> list[dict[str, Any]]:
    return [
        dependency
        for dependency in (monitor.monitoring_strategy or {}).get("conclusion_dependencies", [])
        if isinstance(dependency, dict)
    ]


def _monitor_stale_conclusions(monitor: Monitor) -> list[dict[str, Any]]:
    stale_conclusions = getattr(monitor, "stale_conclusions", None)
    return list(stale_conclusions) if isinstance(stale_conclusions, list) else []


async def _lock_monitor_for_completion(
    db: AsyncSession,
    *,
    monitor: Monitor,
    delta: MonitorRunDelta,
) -> Monitor:
    if not _monitor_stale_conclusions(monitor) and not delta.affected_conclusions:
        return monitor
    # Re-lock and refresh the mutable lifecycle state after external I/O. This
    # serializes persistence with counsel reassessment without holding a lock
    # during provider calls. Both identifiers are required for tenant safety.
    locked_result = await db.execute(
        select(Monitor)
        .where(Monitor.id == monitor.id, Monitor.org_id == monitor.org_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    locked_monitor = locked_result.scalar_one_or_none()
    if locked_monitor is None:
        raise APIError(404, "Not Found", "Monitor not found")
    return locked_monitor


async def _link_monitor_reassessments(
    db: AsyncSession,
    *,
    monitor: Monitor,
    delta: MonitorRunDelta,
) -> None:
    reassessment_records = await record_monitor_conclusion_invalidations(
        db,
        monitor=monitor,
        impacts=delta.affected_conclusions,
    )
    reassessment_by_conclusion = {record.conclusion_id: record for record in reassessment_records}
    for impact in delta.affected_conclusions:
        record = reassessment_by_conclusion.get(_text(impact.get("conclusion_id")))
        if record is not None:
            impact["reassessment_id"] = str(record.id)
            record.trigger_evidence = {
                **dict(record.trigger_evidence or {}),
                "reassessment_id": str(record.id),
            }


async def _create_monitor_alert(
    db: AsyncSession,
    *,
    monitor: Monitor,
    delta: MonitorRunDelta,
    summary: str,
    run_mode: str,
    run_at: datetime,
    alert_id: uuid.UUID | None,
) -> MonitorAlert | None:
    if alert_id is None:
        return None
    alert = build_monitor_alert(
        monitor,
        delta=delta,
        summary=summary,
        run_mode=run_mode,
        run_at=run_at,
    )
    alert.id = alert_id
    db.add(alert)
    await db.flush()
    return alert


def _apply_completed_monitor_state(
    monitor: Monitor,
    *,
    plan: _MonitorRunPlan,
    page: _MonitorRunPage,
    conclusion_dependencies: list[dict[str, Any]],
    stale_conclusions: list[dict[str, Any]],
    summary: str,
) -> None:
    monitor.last_run_at = plan.now
    if plan.run_mode == "full_refresh":
        monitor.last_full_refresh_at = plan.now
    monitor.last_run_mode = plan.run_mode
    monitor.conclusion_status = (
        "review_required"
        if stale_conclusions
        else ("fresh" if conclusion_dependencies else "unbound")
    )
    monitor.stale_conclusions = stale_conclusions
    monitor.last_run_status = (
        "review_required" if monitor.conclusion_status == "review_required" else "ok"
    )
    monitor.last_run_summary = summary
    monitor.cached_patent_ids = list(page.snapshot.get("observed_patent_ids") or [])
    monitor.last_patent_count = len(monitor.cached_patent_ids)
    monitor.last_snapshot = {
        "schema_version": MONITOR_SNAPSHOT_SCHEMA_VERSION,
        "completed_snapshot": page.snapshot,
        "coverage_progress": {
            "plan_sha256": plan.plan_sha256,
            "run_mode": plan.run_mode,
            "cursor": len(plan.all_queries),
            "total_queries": len(plan.all_queries),
            "complete": True,
        },
    }
    monitor.scan_execution_id = None
    monitor.scan_lease_expires_at = None


async def _dispatch_monitor_alert_email(
    monitor: Monitor,
    alert: MonitorAlert | None,
) -> None:
    if alert is not None and monitor.user_id is not None:
        try:
            from api.services.task_dispatcher import build_dispatcher

            await build_dispatcher().dispatch_monitor_alert_email(
                user_id=str(monitor.user_id),
                monitor_id=str(monitor.id),
                alert_id=str(alert.id),
                org_id=str(monitor.org_id),
            )
        except Exception:
            logger.exception(
                "monitor_alert_email_dispatch_failed",
                monitor_id=str(monitor.id),
                alert_id=str(alert.id),
            )
    elif alert is not None:
        # monitor.user_id is nullable (ondelete=SET NULL): the creator was
        # removed. Dispatching with user_id="None" would enqueue a Cloud Task
        # whose email worker can never resolve a recipient and would burn its
        # entire retry budget. The alert row is still persisted; we only skip
        # the doomed email notification.
        logger.warning(
            "monitor_alert_email_skipped_no_recipient",
            monitor_id=str(monitor.id),
            alert_id=str(alert.id),
            org_id=str(monitor.org_id),
        )


def _completed_monitor_response(
    monitor: Monitor,
    *,
    plan: _MonitorRunPlan,
    page: _MonitorRunPage,
    delta: MonitorRunDelta,
    stale_conclusions: list[dict[str, Any]],
    summary: str,
    alert: MonitorAlert | None,
) -> MonitorRunResponse:
    return MonitorRunResponse(
        monitor_id=monitor.id,
        run_mode=plan.run_mode,
        status="ok",
        summary=summary,
        query_count=len(plan.queries),
        alert_created=alert is not None,
        alert_id=alert.id if alert is not None else None,
        new_patent_count=len(delta.new_patent_ids),
        new_patent_ids=delta.new_patent_ids,
        new_event_ids=delta.new_event_ids,
        next_recommended_mode=(
            "targeted_refresh" if plan.run_mode in {"bootstrap", "diff_only"} else "diff_only"
        ),
        provider_names=page.provider_names,
        conclusion_status=monitor.conclusion_status,
        affected_conclusions=[
            MonitorConclusionImpact.model_validate(impact) for impact in delta.affected_conclusions
        ],
        stale_conclusion_count=len(stale_conclusions),
        coverage_complete=True,
        coverage_cursor=len(plan.all_queries),
        coverage_total=len(plan.all_queries),
    )


async def _complete_monitor_run(
    db: AsyncSession,
    *,
    monitor: Monitor,
    plan: _MonitorRunPlan,
    page: _MonitorRunPage,
) -> MonitorRunResponse:
    conclusion_dependencies = _monitor_conclusion_dependencies(monitor)
    delta = diff_snapshot(
        plan.previous_snapshot,
        page.snapshot,
        # The first run establishes the observation baseline. Treating every
        # already-known patent as a new invalidating change would immediately
        # stale the report merely because monitoring was enabled.
        conclusion_dependencies=(conclusion_dependencies if plan.previous_snapshot else []),
    )
    monitor = await _lock_monitor_for_completion(db, monitor=monitor, delta=delta)
    should_alert = alert_warranted(
        previous_snapshot=plan.previous_snapshot,
        delta=delta,
    )
    alert_id = uuid.uuid4() if should_alert else None
    if alert_id is not None and delta.affected_conclusions:
        _bind_impact_evidence(
            delta.affected_conclusions,
            snapshot=page.snapshot,
            alert_id=alert_id,
        )
    await _link_monitor_reassessments(db, monitor=monitor, delta=delta)
    stale_conclusions = merge_stale_conclusions(
        _monitor_stale_conclusions(monitor),
        delta.affected_conclusions,
    )
    summary = build_run_summary(
        run_mode=plan.run_mode,
        delta=delta,
        provider_names=page.provider_names,
    )
    if should_alert:
        assert alert_id is not None
    alert = await _create_monitor_alert(
        db,
        monitor=monitor,
        delta=delta,
        summary=summary,
        run_mode=plan.run_mode,
        run_at=plan.now,
        alert_id=alert_id,
    )
    _apply_completed_monitor_state(
        monitor,
        plan=plan,
        page=page,
        conclusion_dependencies=conclusion_dependencies,
        stale_conclusions=stale_conclusions,
        summary=summary,
    )
    await db.commit()
    await db.refresh(monitor)
    await _dispatch_monitor_alert_email(monitor, alert)
    return _completed_monitor_response(
        monitor,
        plan=plan,
        page=page,
        delta=delta,
        stale_conclusions=stale_conclusions,
        summary=summary,
        alert=alert,
    )


async def execute_monitor_run(
    db: AsyncSession,
    *,
    monitor: Monitor,
    force_full_refresh: bool = False,
    external_search_fn: _ExternalEvidenceSearch = search_external_evidence_impl,
) -> MonitorRunResponse:
    now = datetime.now(UTC)
    report_data = await hydrate_monitor_from_source_analysis(db, monitor=monitor)
    _initialize_monitor_strategy(monitor, report_data)
    plan = _build_monitor_run_plan(
        monitor,
        report_data=report_data,
        now=now,
        force_full_refresh=force_full_refresh,
    )
    page = await _execute_monitor_page(
        monitor,
        plan,
        external_search_fn=external_search_fn,
    )
    _validate_coverage_manifest(monitor, page)
    if not page.coverage_complete:
        return await _persist_partial_monitor_run(
            db,
            monitor=monitor,
            plan=plan,
            page=page,
        )
    return await _complete_monitor_run(db, monitor=monitor, plan=plan, page=page)


async def load_due_monitor_ids(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = MAX_DUE_MONITOR_DISPATCH_BATCH,
) -> list[uuid.UUID]:
    return [
        monitor_id for monitor_id, _org_id in await load_due_monitor_refs(db, now=now, limit=limit)
    ]


async def load_due_monitor_refs(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = MAX_DUE_MONITOR_DISPATCH_BATCH,
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    current_time = now or datetime.now(UTC)
    capped_limit = max(1, min(int(limit), MAX_DUE_MONITOR_DISPATCH_BATCH))
    result = await db.execute(
        select(Monitor.id, Monitor.org_id)
        .where(
            Monitor.is_active.is_(True),
            # Exclude monitors with an active (non-expired) scan lease so a
            # running scan is not re-dispatched until the lease expires.
            or_(
                Monitor.scan_lease_expires_at.is_(None),
                Monitor.scan_lease_expires_at <= current_time,
            ),
            or_(
                Monitor.last_run_at.is_(None),
                and_(
                    Monitor.schedule == MonitorSchedule.DAILY,
                    Monitor.last_run_at <= current_time - timedelta(days=1),
                ),
                and_(
                    Monitor.schedule == MonitorSchedule.WEEKLY,
                    Monitor.last_run_at <= current_time - timedelta(days=7),
                ),
                and_(
                    Monitor.schedule == MonitorSchedule.MONTHLY,
                    Monitor.last_run_at <= current_time - timedelta(days=30),
                ),
            ),
        )
        .order_by(Monitor.last_run_at.is_not(None), Monitor.last_run_at, Monitor.created_at)
        .limit(capped_limit)
    )
    return [(monitor_id, org_id) for monitor_id, org_id in result.all()]


async def get_monitor_for_run(
    db: AsyncSession,
    *,
    monitor_id: uuid.UUID,
    org_id: uuid.UUID,
) -> Monitor:
    result = await db.execute(
        select(Monitor).where(Monitor.id == monitor_id, Monitor.org_id == org_id)
    )
    monitor = result.scalar_one_or_none()
    if monitor is None:
        raise APIError(404, "Not Found", "Monitor not found")
    return monitor
