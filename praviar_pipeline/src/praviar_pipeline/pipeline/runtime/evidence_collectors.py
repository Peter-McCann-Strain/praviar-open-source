"""Evidence collector run builders for the runtime substrate.

This module consolidates the collector target helpers, the live
collector-attempt reconciliation, the collector-run builders and the
public collector entry points.
"""

from __future__ import annotations

from praviar_pipeline.models.report import (
    CollectionAttempt,
    CollectionTarget,
    EvidenceCollectionState,
    EvidenceCollectorDefinition,
    EvidenceCollectorRun,
)
from praviar_pipeline.models.report_common import SourceStatus
from praviar_pipeline.pipeline.report.evidence_index_shared import unique_strings
from praviar_pipeline.pipeline.runtime.evidence_artifacts import adapter_definition_for


def jurisdiction_for_patent_id(patent_id: str) -> str:
    if len(patent_id) < 2:
        return ""
    return patent_id[:2].upper()


def directive_ids_for_adapter(adapter_name: str, directives: list) -> list[str]:
    return unique_strings(
        [
            directive.directive_id
            for directive in directives
            if adapter_name in getattr(directive, "recommended_adapters", [])
        ]
    )


def target_patent_ids_for_adapter(result, directives: list) -> list[str]:
    artifact_targets = [
        getattr(artifact, "patent_id", "")
        for artifact in getattr(result, "artifacts", []) or []
        if getattr(artifact, "patent_id", "")
    ]
    directive_targets = [
        patent_id
        for directive in directives
        if result.adapter_name in getattr(directive, "recommended_adapters", [])
        for patent_id in getattr(directive, "target_patent_ids", [])
    ]
    return unique_strings(
        list(getattr(result, "target_patent_ids", []) or [])
        + list(getattr(result, "covered_patent_ids", []) or [])
        + list(getattr(result, "missing_patent_ids", []) or [])
        + artifact_targets
        + directive_targets
    )


def collector_target_state(
    *,
    covered_patent_ids: list[str],
    missing_patent_ids: list[str],
    expected_components: list[str],
    covered_components: list[str],
    missing_components: list[str],
    required_before_clear: bool,
):
    return type(
        "_CollectorTargetState",
        (),
        {
            "covered_patent_ids": covered_patent_ids,
            "missing_patent_ids": missing_patent_ids,
            "expected_components": expected_components,
            "covered_components": covered_components,
            "missing_components": missing_components,
            "required_before_clear": required_before_clear,
        },
    )()


def collection_targets(result, target_patent_ids: list[str]) -> list[CollectionTarget]:
    targets: list[CollectionTarget] = []
    covered_patent_ids = set(getattr(result, "covered_patent_ids", []) or [])
    missing_patent_ids = set(getattr(result, "missing_patent_ids", []) or [])
    expected_components = list(getattr(result, "expected_components", []) or [])
    covered_components = list(getattr(result, "covered_components", []) or [])
    missing_components = list(getattr(result, "missing_components", []) or [])

    for patent_id in target_patent_ids:
        targets.append(
            CollectionTarget(
                patent_id=patent_id,
                jurisdiction=jurisdiction_for_patent_id(patent_id),
                required_components=expected_components,
                covered_components=(covered_components if patent_id in covered_patent_ids else []),
                missing_components=(missing_components if patent_id in missing_patent_ids else []),
                required_before_clear=bool(getattr(result, "required_before_clear", False)),
            )
        )
    return targets


def collection_state_for_attempt(
    *,
    status: SourceStatus,
    covered_patent_ids: list[str],
    missing_patent_ids: list[str],
) -> EvidenceCollectionState:
    if status == SourceStatus.FAILED:
        return EvidenceCollectionState.FAILED
    if status == SourceStatus.SKIPPED:
        return EvidenceCollectionState.MISSING
    if covered_patent_ids and missing_patent_ids:
        return EvidenceCollectionState.PARTIAL
    if missing_patent_ids:
        return EvidenceCollectionState.MISSING
    return EvidenceCollectionState.COLLECTED


def record_live_collector_attempts_impl(
    *,
    collector_runs: list[EvidenceCollectorRun] | None,
    evidence_collection_plan: list,
    attempt_records: list,
) -> list[EvidenceCollectorRun]:
    runs_by_name = {
        run.definition.collector_name: run.model_copy(deep=True)
        for run in list(collector_runs or [])
    }

    for record in attempt_records:
        collector_name = str(getattr(record, "collector_name", "") or "")
        if not collector_name:
            continue

        target_patent_ids = unique_strings(list(getattr(record, "target_patent_ids", []) or []))
        covered_patent_ids = unique_strings(list(getattr(record, "covered_patent_ids", []) or []))
        missing_patent_ids = unique_strings(
            list(getattr(record, "missing_patent_ids", []) or [])
            + [patent_id for patent_id in target_patent_ids if patent_id not in covered_patent_ids]
        )
        collection_state = collection_state_for_attempt(
            status=getattr(record, "status", SourceStatus.OK),
            covered_patent_ids=covered_patent_ids,
            missing_patent_ids=missing_patent_ids,
        )

        run = runs_by_name.get(collector_name)
        if run is None:
            definition = adapter_definition_for(collector_name)
            triggered_directive_ids = directive_ids_for_adapter(
                collector_name,
                evidence_collection_plan,
            )
            expected_components = list(definition.expected_components)
            run = EvidenceCollectorRun(
                definition=EvidenceCollectorDefinition(
                    collector_name=definition.adapter_name,
                    adapter_kind=definition.adapter_kind,
                    authority_tier=definition.default_authority_tier,
                    supports_authoritative_findings=definition.supports_authoritative_findings,
                    expected_components=expected_components,
                ),
                collection_state=collection_state,
                required_before_clear=bool(
                    getattr(record, "required_before_clear", False) or triggered_directive_ids
                ),
                target_patent_ids=target_patent_ids,
                covered_patent_ids=covered_patent_ids,
                missing_patent_ids=missing_patent_ids,
                expected_components=expected_components,
                covered_components=expected_components if covered_patent_ids else [],
                missing_components=expected_components if missing_patent_ids else [],
                retry_budget_remaining=1 if missing_patent_ids else 0,
                freshness_note=str(
                    getattr(record, "freshness_note", "") or definition.freshness_note
                ),
                triggered_directive_ids=triggered_directive_ids,
                collection_targets=collection_targets(
                    collector_target_state(
                        covered_patent_ids=covered_patent_ids,
                        missing_patent_ids=missing_patent_ids,
                        expected_components=expected_components,
                        covered_components=expected_components if covered_patent_ids else [],
                        missing_components=expected_components if missing_patent_ids else [],
                        required_before_clear=bool(
                            getattr(record, "required_before_clear", False)
                            or triggered_directive_ids
                        ),
                    ),
                    target_patent_ids,
                ),
                attempts=[],
            )
            runs_by_name[collector_name] = run

        run.target_patent_ids = unique_strings(list(run.target_patent_ids) + target_patent_ids)
        run.covered_patent_ids = unique_strings(list(run.covered_patent_ids) + covered_patent_ids)
        run.missing_patent_ids = unique_strings(
            list(run.missing_patent_ids)
            + [
                patent_id
                for patent_id in missing_patent_ids
                if patent_id not in run.covered_patent_ids
            ]
        )
        run.collection_state = collection_state
        run.required_before_clear = bool(
            run.required_before_clear or getattr(record, "required_before_clear", False)
        )
        if run.covered_patent_ids and run.expected_components:
            run.covered_components = list(run.expected_components)
        if run.missing_patent_ids and run.expected_components:
            run.missing_components = list(run.expected_components)
        elif not run.missing_patent_ids:
            run.missing_components = []
        if getattr(record, "freshness_note", ""):
            run.freshness_note = str(record.freshness_note)
        run.retry_budget_remaining = 1 if run.missing_patent_ids else 0
        run.collection_targets = collection_targets(
            collector_target_state(
                covered_patent_ids=list(run.covered_patent_ids),
                missing_patent_ids=list(run.missing_patent_ids),
                expected_components=list(run.expected_components),
                covered_components=list(run.covered_components),
                missing_components=list(run.missing_components),
                required_before_clear=run.required_before_clear,
            ),
            list(run.target_patent_ids),
        )

        run.attempts.append(
            CollectionAttempt(
                attempt_number=len(run.attempts) + 1,
                status=getattr(record, "status", SourceStatus.OK),
                collection_state=collection_state,
                artifact_count=int(getattr(record, "patent_count", 0) or 0),
                warnings=list(getattr(record, "warnings", []) or []),
                summary=str(getattr(record, "summary", "") or ""),
            )
        )

    return list(runs_by_name.values())


def attempt_summary(result, target_patent_ids: list[str]) -> str:
    state = getattr(result, "collection_state", None)
    if state is not None and getattr(state, "value", "") == "failed":
        return "Collector attempt failed and left required record targets unresolved."
    if state is not None and getattr(state, "value", "") == "missing":
        return "Collector has not yet satisfied all required targets."
    if state is not None and getattr(state, "value", "") == "partial":
        return "Collector covered some targets but material record gaps remain."
    if target_patent_ids:
        return "Collector satisfied the currently targeted matter records."
    return "Collector has no active material targets in the current matter."


def build_evidence_collector_runs_impl(
    *,
    evidence_adapter_results: list,
    evidence_collection_plan: list,
) -> list[EvidenceCollectorRun]:
    collector_runs: list[EvidenceCollectorRun] = []
    for result in evidence_adapter_results:
        target_patent_ids = target_patent_ids_for_adapter(result, evidence_collection_plan)
        covered_patent_ids = unique_strings(getattr(result, "covered_patent_ids", []) or [])
        missing_patent_ids = unique_strings(
            list(getattr(result, "missing_patent_ids", []) or [])
            + [patent_id for patent_id in target_patent_ids if patent_id not in covered_patent_ids]
        )
        triggered_directive_ids = directive_ids_for_adapter(
            result.adapter_name,
            evidence_collection_plan,
        )
        retry_budget_remaining = 1 if triggered_directive_ids and missing_patent_ids else 0
        collector_runs.append(
            EvidenceCollectorRun(
                definition=EvidenceCollectorDefinition(
                    collector_name=result.adapter_name,
                    adapter_kind=result.adapter_kind,
                    authority_tier=result.authority_tier,
                    supports_authoritative_findings=bool(
                        getattr(result, "supports_authoritative_findings", False)
                    ),
                    expected_components=list(getattr(result, "expected_components", []) or []),
                ),
                collection_state=result.collection_state,
                required_before_clear=bool(getattr(result, "required_before_clear", False)),
                target_patent_ids=target_patent_ids,
                covered_patent_ids=covered_patent_ids,
                missing_patent_ids=missing_patent_ids,
                expected_components=list(getattr(result, "expected_components", []) or []),
                covered_components=list(getattr(result, "covered_components", []) or []),
                missing_components=list(getattr(result, "missing_components", []) or []),
                retry_budget_remaining=retry_budget_remaining,
                freshness_note=str(getattr(result, "freshness_note", "") or ""),
                triggered_directive_ids=triggered_directive_ids,
                collection_targets=collection_targets(result, target_patent_ids),
                attempts=[
                    CollectionAttempt(
                        attempt_number=1,
                        status=result.status,
                        collection_state=result.collection_state,
                        artifact_count=int(getattr(result, "artifact_count", 0) or 0),
                        warnings=list(getattr(result, "warnings", []) or []),
                        rate_limit_remaining=getattr(result, "rate_limit_remaining", None),
                        retry_after_seconds=getattr(result, "retry_after_seconds", None),
                        summary=attempt_summary(result, target_patent_ids),
                    )
                ],
            )
        )
    return collector_runs


def merge_evidence_collector_runs_impl(
    *,
    existing_collector_runs: list[EvidenceCollectorRun] | None,
    latest_collector_runs: list[EvidenceCollectorRun],
) -> list[EvidenceCollectorRun]:
    existing_by_name = {
        run.definition.collector_name: run for run in list(existing_collector_runs or [])
    }
    merged: list[EvidenceCollectorRun] = []

    for run in latest_collector_runs:
        existing = existing_by_name.pop(run.definition.collector_name, None)
        if existing is None:
            merged.append(run)
            continue
        merged.append(
            run.model_copy(
                update={
                    "attempts": list(existing.attempts or run.attempts),
                    "triggered_directive_ids": unique_strings(
                        list(existing.triggered_directive_ids or [])
                        + list(run.triggered_directive_ids or [])
                    ),
                }
            )
        )

    for run in existing_by_name.values():
        if run.attempts:
            merged.append(run)

    return merged


def build_evidence_collector_runs(
    *,
    evidence_adapter_results: list,
    evidence_collection_plan: list,
) -> list[EvidenceCollectorRun]:
    return build_evidence_collector_runs_impl(
        evidence_adapter_results=evidence_adapter_results,
        evidence_collection_plan=evidence_collection_plan,
    )


def merge_evidence_collector_runs(
    *,
    existing_collector_runs: list[EvidenceCollectorRun] | None,
    latest_collector_runs: list[EvidenceCollectorRun],
) -> list[EvidenceCollectorRun]:
    return merge_evidence_collector_runs_impl(
        existing_collector_runs=existing_collector_runs,
        latest_collector_runs=latest_collector_runs,
    )


def record_live_collector_attempts(
    *,
    collector_runs: list[EvidenceCollectorRun] | None,
    evidence_collection_plan: list,
    attempt_records: list,
) -> list[EvidenceCollectorRun]:
    return record_live_collector_attempts_impl(
        collector_runs=collector_runs,
        evidence_collection_plan=evidence_collection_plan,
        attempt_records=attempt_records,
    )
