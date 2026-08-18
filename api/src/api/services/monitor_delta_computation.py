"""Snapshot construction and delta diffing for monitor runs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from api.services.monitor_query_strategy import dedupe_strings


@dataclass(frozen=True)
class MonitorRunDelta:
    new_patent_ids: list[str]
    new_event_ids: list[str]
    jurisdiction_deltas: dict[str, dict[str, int]]
    affected_conclusions: list[dict[str, Any]] = field(default_factory=list)


def _text(value: object) -> str:
    return str(value or "").strip()


def _as_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _as_dict_list(value: object) -> list[dict[str, Any]]:
    return [item for item in _as_list(value) if isinstance(item, dict)]


def _fingerprint_result(result: dict[str, Any]) -> str:
    """Bind one observed record state to its exact normalized provider payload."""

    encoded = json.dumps(
        result,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _merge_signal(
    signals: dict[str, dict[str, Any]],
    *,
    signal_id: str,
    jurisdiction: str,
    conclusion_ids: list[str],
) -> None:
    if not signal_id:
        return
    existing = signals.setdefault(
        signal_id,
        {
            "signal_id": signal_id,
            "jurisdictions": [],
            "conclusion_ids": [],
        },
    )
    existing["jurisdictions"] = dedupe_strings(
        [*(existing.get("jurisdictions") or []), jurisdiction]
    )
    existing["conclusion_ids"] = dedupe_strings(
        [*(existing.get("conclusion_ids") or []), *conclusion_ids]
    )


def build_snapshot(
    *,
    run_mode: str,
    query_results: list[dict[str, Any]],
    provider_names: list[str],
    watch_targets: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    observed_patent_ids: list[str] = []
    observed_event_ids: list[str] = []
    observed_patent_signals: dict[str, dict[str, Any]] = {}
    observed_event_signals: dict[str, dict[str, Any]] = {}
    observed_record_fingerprints: dict[str, str] = {}
    observed_record_signals: dict[str, dict[str, Any]] = {}
    completed_coverage_keys: list[str] = []
    provider_execution_receipts: list[dict[str, Any]] = []
    jurisdiction_deltas: dict[str, dict[str, int]] = {}

    for result in query_results:
        jurisdiction = _text(result.get("jurisdiction")).upper() or "GLOBAL"
        completed_coverage_keys.extend(dedupe_strings(_as_list(result.get("coverage_keys"))))
        provider_execution_receipts.extend(_as_dict_list(result.get("execution_receipts")))
        affected_conclusion_ids = dedupe_strings(_as_list(result.get("affected_conclusion_ids")))
        jurisdiction_state = jurisdiction_deltas.setdefault(
            jurisdiction,
            {"result_count": 0, "patent_count": 0, "event_count": 0},
        )
        response = result.get("response") or {}
        for item in response.get("results", []) or []:
            if not isinstance(item, dict):
                continue
            if (
                _text(item.get("artifact_type")) == "provider_notice"
                or _text(item.get("section")) == "external_provider_notice"
                or _text(item.get("authority_tier")) == "governance"
            ):
                continue
            jurisdiction_state["result_count"] += 1
            patent_id = _text(item.get("patent_id"))
            result_id = _text(item.get("result_id"))
            if result_id:
                result_fingerprint = _fingerprint_result(item)
                observed_record_fingerprints[result_id] = result_fingerprint
                _merge_signal(
                    observed_record_signals,
                    signal_id=f"{result_id}@sha256:{result_fingerprint}",
                    jurisdiction=jurisdiction,
                    conclusion_ids=affected_conclusion_ids,
                )
            if patent_id:
                observed_patent_ids.append(patent_id)
                _merge_signal(
                    observed_patent_signals,
                    signal_id=patent_id,
                    jurisdiction=jurisdiction,
                    conclusion_ids=affected_conclusion_ids,
                )
                jurisdiction_state["patent_count"] += 1
            else:
                event_id = result_id
                if event_id:
                    observed_event_ids.append(event_id)
                    _merge_signal(
                        observed_event_signals,
                        signal_id=event_id,
                        jurisdiction=jurisdiction,
                        conclusion_ids=affected_conclusion_ids,
                    )
                    jurisdiction_state["event_count"] += 1

    return {
        "generated_at": now.isoformat(),
        "run_mode": run_mode,
        "provider_names": provider_names,
        "watch_target_ids": dedupe_strings(
            [target.get("target_id") for target in watch_targets if isinstance(target, dict)]
        ),
        "completed_coverage_keys": dedupe_strings(completed_coverage_keys),
        "provider_execution_receipts": provider_execution_receipts,
        "observed_patent_ids": dedupe_strings(observed_patent_ids),
        "observed_event_ids": dedupe_strings(observed_event_ids),
        "observed_patent_signals": list(observed_patent_signals.values()),
        "observed_event_signals": list(observed_event_signals.values()),
        "observed_record_fingerprints": observed_record_fingerprints,
        "observed_record_signals": list(observed_record_signals.values()),
        "jurisdiction_deltas": jurisdiction_deltas,
    }


def _build_affected_conclusions(
    *,
    new_patent_ids: list[str],
    new_event_ids: list[str],
    previous: dict[str, Any],
    current: dict[str, Any],
    conclusion_dependencies: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    dependency_by_id = {
        _text(dependency.get("conclusion_id")): dependency
        for dependency in conclusion_dependencies
        if _text(dependency.get("conclusion_id"))
    }
    triggers: dict[str, dict[str, list[str]]] = {}

    def collect(
        signals: list[dict[str, Any]],
        *,
        new_ids: set[str],
        trigger_key: str,
    ) -> None:
        for signal in signals:
            signal_id = _text(signal.get("signal_id"))
            if signal_id not in new_ids:
                continue
            for conclusion_id in dedupe_strings(_as_list(signal.get("conclusion_ids"))):
                if conclusion_id not in dependency_by_id:
                    continue
                trigger = triggers.setdefault(
                    conclusion_id,
                    {
                        "trigger_patent_ids": [],
                        "trigger_event_ids": [],
                        "jurisdictions": [],
                    },
                )
                trigger[trigger_key] = dedupe_strings([*trigger[trigger_key], signal_id])
                trigger["jurisdictions"] = dedupe_strings(
                    [
                        *trigger["jurisdictions"],
                        *_as_list(signal.get("jurisdictions")),
                    ]
                )

    collect(
        _as_dict_list(current.get("observed_patent_signals")),
        new_ids=set(new_patent_ids),
        trigger_key="trigger_patent_ids",
    )
    collect(
        _as_dict_list(current.get("observed_event_signals")),
        new_ids=set(new_event_ids),
        trigger_key="trigger_event_ids",
    )
    collect(
        _as_dict_list(current.get("observed_record_signals")),
        new_ids=set(new_event_ids),
        trigger_key="trigger_event_ids",
    )
    disappearance_ids = {
        event_id[: -len("@disappeared")]
        for event_id in new_event_ids
        if event_id.endswith("@disappeared")
    }
    for signal in _as_dict_list(previous.get("observed_record_signals")):
        prior_signal_id = _text(signal.get("signal_id"))
        result_id = prior_signal_id.split("@sha256:", 1)[0]
        if not result_id or result_id not in disappearance_ids:
            continue
        synthetic_signal = {
            **signal,
            "signal_id": f"{result_id}@disappeared",
        }
        collect(
            [synthetic_signal],
            new_ids=set(new_event_ids),
            trigger_key="trigger_event_ids",
        )
    disappeared_patent_ids = {
        event_id[len("patent:") : -len("@disappeared")]
        for event_id in new_event_ids
        if event_id.startswith("patent:") and event_id.endswith("@disappeared")
    }
    for signal in _as_dict_list(previous.get("observed_patent_signals")):
        patent_id = _text(signal.get("signal_id"))
        if patent_id not in disappeared_patent_ids:
            continue
        synthetic_signal = {
            **signal,
            "signal_id": f"patent:{patent_id}@disappeared",
        }
        collect(
            [synthetic_signal],
            new_ids=set(new_event_ids),
            trigger_key="trigger_event_ids",
        )

    impacts: list[dict[str, Any]] = []
    invalidated_at = _text(current.get("generated_at"))
    for conclusion_id, dependency in dependency_by_id.items():
        trigger = triggers.get(conclusion_id)
        if trigger is None:
            continue
        reason_codes: list[str] = []
        if trigger["trigger_patent_ids"]:
            reason_codes.append("new_patent_candidate")
        if trigger["trigger_event_ids"]:
            reason_codes.append("monitored_record_event")
        impacts.append(
            {
                "conclusion_id": conclusion_id,
                "conclusion_type": _text(dependency.get("conclusion_type")),
                "label": _text(dependency.get("label")),
                "previous_outcome": _text(dependency.get("outcome")),
                "status": "review_required",
                "source_report_id": _text(dependency.get("source_report_id")),
                "dependency_fingerprint": _text(dependency.get("dependency_fingerprint")),
                "invalidated_at": invalidated_at,
                "latest_observed_at": invalidated_at,
                "reason_codes": reason_codes,
                "trigger_patent_ids": trigger["trigger_patent_ids"],
                "trigger_event_ids": trigger["trigger_event_ids"],
                "jurisdictions": trigger["jurisdictions"],
            }
        )
    return impacts


def diff_snapshot(
    previous: dict[str, Any],
    current: dict[str, Any],
    *,
    conclusion_dependencies: list[dict[str, Any]] | None = None,
) -> MonitorRunDelta:
    previous_patents = set(_as_list(previous.get("observed_patent_ids")))
    previous_events = set(_as_list(previous.get("observed_event_ids")))
    current_patents = dedupe_strings(_as_list(current.get("observed_patent_ids")))
    current_events = dedupe_strings(_as_list(current.get("observed_event_ids")))
    previous_record_fingerprints = previous.get("observed_record_fingerprints")
    current_record_fingerprints = current.get("observed_record_fingerprints")
    changed_record_events: list[str] = []
    if isinstance(previous_record_fingerprints, dict) and isinstance(
        current_record_fingerprints,
        dict,
    ):
        for result_id, current_fingerprint in current_record_fingerprints.items():
            previous_fingerprint = previous_record_fingerprints.get(result_id)
            if (
                isinstance(current_fingerprint, str)
                and isinstance(previous_fingerprint, str)
                and current_fingerprint != previous_fingerprint
            ):
                changed_record_events.append(f"{result_id}@sha256:{current_fingerprint}")
        for result_id in previous_record_fingerprints:
            if result_id not in current_record_fingerprints:
                changed_record_events.append(f"{result_id}@disappeared")

    new_patent_ids = [pid for pid in current_patents if pid not in previous_patents]
    disappeared_patent_events = [
        f"patent:{patent_id}@disappeared"
        for patent_id in sorted(previous_patents - set(current_patents))
    ]
    new_event_ids = dedupe_strings(
        [
            *[eid for eid in current_events if eid not in previous_events],
            *changed_record_events,
            *disappeared_patent_events,
        ]
    )
    return MonitorRunDelta(
        new_patent_ids=new_patent_ids,
        new_event_ids=new_event_ids,
        jurisdiction_deltas=dict(current.get("jurisdiction_deltas") or {}),
        affected_conclusions=_build_affected_conclusions(
            new_patent_ids=new_patent_ids,
            new_event_ids=new_event_ids,
            previous=previous,
            current=current,
            conclusion_dependencies=list(conclusion_dependencies or []),
        ),
    )


def build_run_summary(
    *,
    run_mode: str,
    delta: MonitorRunDelta,
    provider_names: list[str],
) -> str:
    parts = [
        f"Executed {run_mode.replace('_', ' ')} monitoring pass",
        f"against {len(provider_names)} provider layer{'s' if len(provider_names) != 1 else ''}",
    ]
    if delta.new_patent_ids:
        parts.append(
            f"and found {len(delta.new_patent_ids)} new patent candidate"
            f"{'s' if len(delta.new_patent_ids) != 1 else ''}"
        )
    elif delta.new_event_ids:
        parts.append(
            f"and found {len(delta.new_event_ids)} new event signal"
            f"{'s' if len(delta.new_event_ids) != 1 else ''}"
        )
    else:
        parts.append("with no new patent or event deltas")
    if delta.affected_conclusions:
        count = len(delta.affected_conclusions)
        parts.append(
            f"{count} prior conclusion{'s' if count != 1 else ''} now require attorney reassessment"
        )
    return " ".join(parts) + "."


def severity_for_delta(delta: MonitorRunDelta) -> str:
    if delta.affected_conclusions or delta.new_patent_ids:
        return "high"
    if delta.new_event_ids:
        return "medium"
    return "low"
