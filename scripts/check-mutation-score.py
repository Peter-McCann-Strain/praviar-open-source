#!/usr/bin/env python3
"""Fail CI when a Mutmut result falls below its explicit quality floor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _non_negative_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value


def evaluate_mutation_stats(
    payload: dict[str, object],
    *,
    minimum_score: float,
    minimum_mutants: int,
) -> tuple[float, list[str]]:
    """Return the killed-mutant score and any fail-closed gate violations."""
    total = _non_negative_int(payload, "total")
    killed = _non_negative_int(payload, "killed")
    survived = _non_negative_int(payload, "survived")
    timeout = _non_negative_int(payload, "timeout")
    no_tests = _non_negative_int(payload, "no_tests")
    suspicious = _non_negative_int(payload, "suspicious")
    interrupted = _non_negative_int(payload, "check_was_interrupted_by_user")
    segfault = _non_negative_int(payload, "segfault")

    if killed + survived + timeout > total:
        raise ValueError("mutation outcome counts exceed total")

    score = 100.0 * killed / total if total else 0.0
    failures: list[str] = []
    if total < minimum_mutants:
        failures.append(f"only {total} mutants ran; require at least {minimum_mutants}")
    if score < minimum_score:
        failures.append(f"mutation score {score:.2f}% is below {minimum_score:.2f}%")
    if no_tests:
        failures.append(f"{no_tests} mutants had no tests")
    if suspicious:
        failures.append(f"{suspicious} mutants were suspicious")
    if interrupted:
        failures.append("mutation run was interrupted")
    if segfault:
        failures.append(f"{segfault} mutants segfaulted")
    return score, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stats", type=Path)
    parser.add_argument("--minimum-score", type=float, required=True)
    parser.add_argument("--minimum-mutants", type=int, default=1)
    args = parser.parse_args()

    payload = json.loads(args.stats.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("mutation stats must be a JSON object")
    score, failures = evaluate_mutation_stats(
        payload,
        minimum_score=args.minimum_score,
        minimum_mutants=args.minimum_mutants,
    )
    print(f"Mutation score: {score:.2f}%")
    for failure in failures:
        print(f"ERROR: {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
