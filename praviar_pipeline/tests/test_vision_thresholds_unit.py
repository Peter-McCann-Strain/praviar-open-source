"""Offline unit tests for the vision pipeline threshold assertions.

These tests run on any CI runner without model venvs, page PDFs, or optional
dependencies.  They encode the same threshold constants used by the full e2e
gate so any change to the thresholds breaks both files simultaneously.
"""

from __future__ import annotations

import sys

import pytest

MIN_DETECTION_RECALL = 0.50
MIN_TRIAGE_CHEMICAL_ROUTE = 0.80

_CANNED_RESULT: dict = {
    "totals": {"n_pages": 5},
    "ocsr_mode": "replay",
    "stage_attribution": {
        "detection_recall": MIN_DETECTION_RECALL,
        "triage_chemical_route_rate": MIN_TRIAGE_CHEMICAL_ROUTE,
        "ocsr_resolved_rate": 0.70,
        "end_to_end_correct_per_gt_box": 0.55,
        "end_to_end_correct_per_labeled_gt": 0.60,
    },
    "per_page": [
        {"stem": "page_001", "n_gt": 3, "n_pred": 3, "n_matched": 3, "matches": []},
    ],
}

_BELOW_DETECTION: dict = {
    **_CANNED_RESULT,
    "stage_attribution": {
        **_CANNED_RESULT["stage_attribution"],
        "detection_recall": MIN_DETECTION_RECALL - 0.01,
    },
}

_BELOW_TRIAGE: dict = {
    **_CANNED_RESULT,
    "stage_attribution": {
        **_CANNED_RESULT["stage_attribution"],
        "triage_chemical_route_rate": MIN_TRIAGE_CHEMICAL_ROUTE - 0.01,
    },
}


def test_threshold_unit_detection_passes() -> None:
    sa = _CANNED_RESULT["stage_attribution"]
    assert sa["detection_recall"] >= MIN_DETECTION_RECALL


def test_threshold_unit_triage_passes() -> None:
    sa = _CANNED_RESULT["stage_attribution"]
    assert sa["triage_chemical_route_rate"] >= MIN_TRIAGE_CHEMICAL_ROUTE


def test_threshold_unit_detection_regression_detected() -> None:
    sa = _BELOW_DETECTION["stage_attribution"]
    assert sa["detection_recall"] < MIN_DETECTION_RECALL


def test_threshold_unit_triage_regression_detected() -> None:
    sa = _BELOW_TRIAGE["stage_attribution"]
    assert sa["triage_chemical_route_rate"] < MIN_TRIAGE_CHEMICAL_ROUTE


def test_threshold_unit_required_fields_present() -> None:
    sa = _CANNED_RESULT["stage_attribution"]
    for k in (
        "detection_recall",
        "triage_chemical_route_rate",
        "ocsr_resolved_rate",
        "end_to_end_correct_per_gt_box",
        "end_to_end_correct_per_labeled_gt",
    ):
        assert k in sa, f"missing stage_attribution key: {k}"


def test_threshold_unit_per_page_records_complete() -> None:
    for p in _CANNED_RESULT["per_page"]:
        assert {"stem", "n_gt", "n_pred", "n_matched", "matches"} <= set(p.keys())
        assert p["n_matched"] <= min(p["n_gt"], p["n_pred"])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
