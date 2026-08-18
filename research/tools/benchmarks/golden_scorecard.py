"""Golden legal ground-truth scorecards for reconciled compound reports."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

try:
    from research.tools.benchmarks.scoring_core import normalize_patent_id
except ImportError:  # pragma: no cover - direct script path import
    from scoring_core import normalize_patent_id  # type: ignore[no-redef]


def _patent_id(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("patent_id") or value.get("number") or value.get("patent_number") or ""
    return ""


def _normalize_ids(values: Iterable[Any]) -> set[str]:
    return {normalize_patent_id(pid) for value in values if (pid := _patent_id(value))}


def _report_patent_ids(report: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for key in ("patents", "patent_details", "patent_analyses", "analyses"):
        records = report.get(key, [])
        if isinstance(records, dict):
            records = list(records.values())
        if not isinstance(records, list):
            continue
        ids.update(_normalize_ids(records))
    return ids


def _family_ids(patent: dict[str, Any]) -> set[str]:
    ids = _normalize_ids([patent])
    for key in ("us_family_members", "family_members", "equivalents"):
        members = patent.get(key, [])
        if isinstance(members, list):
            ids.update(_normalize_ids(members))
    return ids


def _expected_high_active_blockers(ground_truth: dict[str, Any]) -> list[dict[str, Any]]:
    blockers = ground_truth.get("known_blocking_patents", [])
    expected: list[dict[str, Any]] = []
    for patent in blockers:
        if not isinstance(patent, dict):
            continue
        risk = str(patent.get("expected_risk_level", "")).lower()
        status = str(patent.get("blocking_status", patent.get("status", ""))).lower()
        if risk == "high" or status in {"currently_blocking", "active"}:
            expected.append(patent)
    return expected


def score_golden_report(report: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    """Score a generated report against one reconciled legal ground-truth file."""
    discovered_ids = _report_patent_ids(report)
    blockers = [
        patent
        for patent in ground_truth.get("known_blocking_patents", [])
        if isinstance(patent, dict) and _patent_id(patent)
    ]
    non_blockers = [
        patent
        for patent in ground_truth.get("known_non_blocking_patents", [])
        if isinstance(patent, dict) and _patent_id(patent)
    ]
    high_active = _expected_high_active_blockers(ground_truth)

    family_hits = [
        patent
        for patent in blockers
        if discovered_ids.intersection(_family_ids(patent))
    ]
    high_active_hits = [
        patent
        for patent in high_active
        if discovered_ids.intersection(_family_ids(patent))
    ]
    non_blocker_hits = [
        patent
        for patent in non_blockers
        if discovered_ids.intersection(_family_ids(patent))
    ]

    source_health = report.get("source_health", {})
    entries = source_health.get("entries", []) if isinstance(source_health, dict) else []
    citation_backed = 0
    assertion_count = 0
    for analysis in report.get("patent_analyses", []) or []:
        if not isinstance(analysis, dict):
            continue
        assertion_count += 1
        if analysis.get("citations") or analysis.get("evidence") or analysis.get("claims_analyzed"):
            citation_backed += 1

    return {
        "compound": ground_truth.get("compound", {}).get("name", ""),
        "compound_identity_correct": _compound_identity_correct(report, ground_truth),
        "blocking_family_recall": _ratio(len(family_hits), len(blockers)),
        "high_active_blocker_recall": _ratio(len(high_active_hits), len(high_active)),
        "non_blocking_discrimination": 1.0 - _ratio(len(non_blocker_hits), len(non_blockers)),
        "citation_fidelity": _ratio(citation_backed, assertion_count),
        "source_coverage": {
            "ok": [entry.get("source") for entry in entries if entry.get("status") == "ok"],
            "incomplete": [
                entry.get("source")
                for entry in entries
                if entry.get("status") in {"failed", "not_configured"}
            ],
        },
        "missed_blocking_patents": [
            _patent_id(patent)
            for patent in blockers
            if not discovered_ids.intersection(_family_ids(patent))
        ],
        "missed_high_active_blockers": [
            _patent_id(patent)
            for patent in high_active
            if not discovered_ids.intersection(_family_ids(patent))
        ],
    }


def _compound_identity_correct(report: dict[str, Any], ground_truth: dict[str, Any]) -> bool:
    expected = ground_truth.get("compound", {})
    actual = report.get("compound", {})
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        return False
    expected_cid = expected.get("pubchem_cid")
    actual_cid = actual.get("pubchem_cid") or actual.get("cid")
    if expected_cid and actual_cid:
        return str(expected_cid) == str(actual_cid)
    expected_name = str(expected.get("name", "")).strip().lower()
    actual_name = str(actual.get("name", "")).strip().lower()
    return bool(expected_name and expected_name == actual_name)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0
    return numerator / denominator


__all__ = ["score_golden_report"]
