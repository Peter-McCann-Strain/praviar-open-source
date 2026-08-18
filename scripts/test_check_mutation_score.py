from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).with_name("check-mutation-score.py")
SPEC = importlib.util.spec_from_file_location("check_mutation_score", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _stats(**overrides: int) -> dict[str, object]:
    payload: dict[str, object] = {
        "killed": 80,
        "survived": 18,
        "total": 100,
        "no_tests": 0,
        "suspicious": 0,
        "timeout": 2,
        "check_was_interrupted_by_user": 0,
        "segfault": 0,
    }
    payload.update(overrides)
    return payload


def test_accepts_score_at_floor_and_counts_timeouts_as_not_killed() -> None:
    score, failures = MODULE.evaluate_mutation_stats(
        _stats(), minimum_score=80.0, minimum_mutants=100
    )
    assert score == 80.0
    assert failures == []


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"killed": 74, "survived": 24}, "below"),
        ({"total": 99, "killed": 80, "survived": 17}, "at least"),
        ({"no_tests": 1}, "no tests"),
        ({"suspicious": 1}, "suspicious"),
        ({"check_was_interrupted_by_user": 1}, "interrupted"),
        ({"segfault": 1}, "segfaulted"),
    ],
)
def test_rejects_incomplete_or_below_floor_runs(
    overrides: dict[str, int], expected: str
) -> None:
    _, failures = MODULE.evaluate_mutation_stats(
        _stats(**overrides), minimum_score=75.0, minimum_mutants=100
    )
    assert any(expected in failure for failure in failures)


def test_rejects_malformed_or_inconsistent_counts() -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        MODULE.evaluate_mutation_stats(
            _stats(killed=-1), minimum_score=75.0, minimum_mutants=100
        )
    with pytest.raises(ValueError, match="exceed total"):
        MODULE.evaluate_mutation_stats(
            _stats(killed=90, survived=20), minimum_score=75.0, minimum_mutants=100
        )
