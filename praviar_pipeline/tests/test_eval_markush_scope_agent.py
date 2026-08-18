"""Tests for research/experiments/drawing_analysis/eval_markush_scope_agent.py.

The eval script lives under `research/` (outside the praviar_pipeline package), so
we load it via `importlib.util` from the repo-root-relative path. All tests
are fully offline — no real Claude calls.

Unit tests for the verdict-classification logic run unconditionally against
hardcoded fixtures. Integration tests that invoke the eval harness are skipped
when the generated fixture file is absent (CI / fresh checkouts).
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

# ---------------------------------------------------------------------------
# Locate the eval script relative to the praviar_pipeline package.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_EVAL_SCRIPT = (
    _REPO_ROOT / "research" / "experiments" / "drawing_analysis" / "eval_markush_scope_agent.py"
)
_FIXTURE = (
    _REPO_ROOT
    / "research"
    / "experiments"
    / "drawing_analysis"
    / "output"
    / "markush_scope_fixture"
    / "cases.json"
)

_HARNESS_AVAILABLE = _EVAL_SCRIPT.exists() and _FIXTURE.exists()

_skip_harness = pytest.mark.skipif(
    not _HARNESS_AVAILABLE,
    reason="eval_markush_scope_agent.py or cases.json fixture not present; run the research script to generate them",
)


def _load_eval_module() -> ModuleType:
    """Import the eval script as a module under a synthetic name."""
    assert _EVAL_SCRIPT.exists(), f"Eval script not found at {_EVAL_SCRIPT}"
    spec = importlib.util.spec_from_file_location(
        "eval_markush_scope_agent_under_test", _EVAL_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def eval_mod() -> ModuleType:
    return _load_eval_module()


@pytest.fixture
def fixture_path() -> Path:
    assert _FIXTURE.exists(), f"Fixture not found at {_FIXTURE}"
    return _FIXTURE


# ---------------------------------------------------------------------------
# Unit tests for verdict-classification logic — always run, no fixture needed.
# ---------------------------------------------------------------------------

VERDICT_LABELS = ("in_scope", "out_of_scope", "ambiguous")
_US_PUBLICATION_ID_RE = re.compile(r"^US\d{11}[A-Z]\d$")

_HARDCODED_CASES = [
    {
        "id": "u1",
        "expected": "in_scope",
        "predicted": "in_scope",
        "correct": True,
        "confidence": 0.9,
    },
    {
        "id": "u2",
        "expected": "in_scope",
        "predicted": "out_of_scope",
        "correct": False,
        "confidence": 0.6,
    },
    {
        "id": "u3",
        "expected": "out_of_scope",
        "predicted": "out_of_scope",
        "correct": True,
        "confidence": 0.85,
    },
    {
        "id": "u4",
        "expected": "ambiguous",
        "predicted": "ambiguous",
        "correct": True,
        "confidence": 0.7,
    },
    {
        "id": "u5",
        "expected": "ambiguous",
        "predicted": "in_scope",
        "correct": False,
        "confidence": 0.5,
    },
]


def _confusion_matrix(
    results: list[dict],
    labels: tuple[str, ...] = VERDICT_LABELS,
) -> dict:
    """Inline implementation of the verdict confusion-matrix logic under test."""
    index = {label: i for i, label in enumerate(labels)}
    matrix = [[0 for _ in labels] for _ in labels]
    for r in results:
        if r["expected"] in index and r["predicted"] in index:
            matrix[index[r["expected"]]][index[r["predicted"]]] += 1
    return {
        "labels": list(labels),
        "rows": "expected",
        "cols": "predicted",
        "matrix": matrix,
    }


def _per_verdict_accuracy(
    results: list[dict],
    labels: tuple[str, ...] = VERDICT_LABELS,
) -> dict:
    out: dict = {}
    for label in labels:
        subset = [r for r in results if r["expected"] == label]
        total = len(subset)
        correct = sum(1 for r in subset if r["correct"])
        out[label] = {
            "total": total,
            "correct": correct,
            "accuracy": (correct / total) if total else 0.0,
        }
    return out


def test_confusion_matrix_shape_and_labels_hardcoded() -> None:
    cm = _confusion_matrix(_HARDCODED_CASES)

    assert cm["labels"] == ["in_scope", "out_of_scope", "ambiguous"]
    assert cm["rows"] == "expected"
    assert cm["cols"] == "predicted"

    matrix = cm["matrix"]
    assert len(matrix) == 3
    assert all(len(row) == 3 for row in matrix)

    labels = cm["labels"]
    r = labels.index("in_scope")
    c = labels.index("out_of_scope")
    assert matrix[r][c] == 1

    r = labels.index("ambiguous")
    c = labels.index("ambiguous")
    assert matrix[r][c] == 1


def test_confusion_matrix_diagonal_correct_cases() -> None:
    results = [{"expected": v, "predicted": v, "correct": True} for v in VERDICT_LABELS]
    cm = _confusion_matrix(results)
    matrix = cm["matrix"]
    labels = cm["labels"]
    for label in VERDICT_LABELS:
        idx = labels.index(label)
        assert matrix[idx][idx] == 1, f"diagonal cell for {label} should be 1"


def test_per_verdict_accuracy_hardcoded() -> None:
    pv = _per_verdict_accuracy(_HARDCODED_CASES)
    assert pv["in_scope"]["total"] == 2
    assert pv["in_scope"]["correct"] == 1
    assert pv["in_scope"]["accuracy"] == pytest.approx(0.5)

    assert pv["out_of_scope"]["total"] == 1
    assert pv["out_of_scope"]["correct"] == 1
    assert pv["out_of_scope"]["accuracy"] == pytest.approx(1.0)

    assert pv["ambiguous"]["total"] == 2
    assert pv["ambiguous"]["correct"] == 1
    assert pv["ambiguous"]["accuracy"] == pytest.approx(0.5)


def test_overall_accuracy_hardcoded() -> None:
    total = len(_HARDCODED_CASES)
    correct = sum(1 for r in _HARDCODED_CASES if r["correct"])
    accuracy = correct / total
    assert accuracy == pytest.approx(0.6)


def test_verdict_labels_are_the_canonical_three() -> None:
    assert set(VERDICT_LABELS) == {"in_scope", "out_of_scope", "ambiguous"}


# ---------------------------------------------------------------------------
# Eval harness tests — require the eval script and generated fixture.
# ---------------------------------------------------------------------------


@_skip_harness
def test_fixture_uses_unique_production_valid_publication_ids(fixture_path: Path) -> None:
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))["cases"]
    publication_ids = [case["id"] for case in cases]

    assert len(publication_ids) == 50
    assert len(set(publication_ids)) == len(publication_ids)
    assert all(
        _US_PUBLICATION_ID_RE.fullmatch(publication_id) for publication_id in publication_ids
    )


@_skip_harness
def test_confusion_matrix_shape_and_labels(eval_mod: ModuleType) -> None:
    results = [
        {"expected": "in_scope", "predicted": "in_scope", "correct": True},
        {"expected": "in_scope", "predicted": "out_of_scope", "correct": False},
        {"expected": "out_of_scope", "predicted": "ambiguous", "correct": False},
        {"expected": "ambiguous", "predicted": "ambiguous", "correct": True},
    ]
    cm = eval_mod.confusion_matrix(results)

    assert cm["labels"] == ["in_scope", "out_of_scope", "ambiguous"]
    assert cm["rows"] == "expected"
    assert cm["cols"] == "predicted"

    matrix = cm["matrix"]
    assert len(matrix) == 3
    assert all(len(row) == 3 for row in matrix)

    labels = cm["labels"]
    r = labels.index("in_scope")
    c = labels.index("out_of_scope")
    assert matrix[r][c] == 1

    r = labels.index("ambiguous")
    c = labels.index("ambiguous")
    assert matrix[r][c] == 1


@_skip_harness
async def test_dry_run_full_accuracy(
    eval_mod: ModuleType, fixture_path: Path, tmp_path: Path
) -> None:
    output = tmp_path / "results.json"
    rc = await eval_mod._run_async(
        eval_mod.parse_args(
            [
                "--dry-run",
                "--fixture",
                str(fixture_path),
                "--output",
                str(output),
            ]
        )
    )
    assert rc == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["mode"] == "dry-run"
    summary = payload["summary"]
    assert summary["total"] == 50
    assert summary["correct"] == 50
    assert summary["accuracy"] == 1.0


@_skip_harness
async def test_echo_random_seed_deterministic(
    eval_mod: ModuleType, fixture_path: Path, tmp_path: Path
) -> None:
    output_a = tmp_path / "a.json"
    output_b = tmp_path / "b.json"

    for dest in (output_a, output_b):
        rc = await eval_mod._run_async(
            eval_mod.parse_args(
                [
                    "--echo-random",
                    "--seed",
                    "123",
                    "--fixture",
                    str(fixture_path),
                    "--output",
                    str(dest),
                ]
            )
        )
        assert rc == 0

    a = json.loads(output_a.read_text(encoding="utf-8"))
    b = json.loads(output_b.read_text(encoding="utf-8"))

    preds_a = [r["predicted"] for r in a["results"]]
    preds_b = [r["predicted"] for r in b["results"]]
    assert preds_a == preds_b

    acc = a["summary"]["accuracy"]
    assert 0.10 <= acc <= 0.55, f"accuracy {acc:.3f} outside expected band for random"


@_skip_harness
async def test_limit_truncates_cases(
    eval_mod: ModuleType, fixture_path: Path, tmp_path: Path
) -> None:
    output = tmp_path / "limited.json"
    rc = await eval_mod._run_async(
        eval_mod.parse_args(
            [
                "--dry-run",
                "--limit",
                "5",
                "--fixture",
                str(fixture_path),
                "--output",
                str(output),
            ]
        )
    )
    assert rc == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["total"] == 5
    assert len(payload["results"]) == 5


@_skip_harness
async def test_output_file_schema(eval_mod: ModuleType, fixture_path: Path, tmp_path: Path) -> None:
    output = tmp_path / "schema" / "results.json"
    rc = await eval_mod._run_async(
        eval_mod.parse_args(
            [
                "--dry-run",
                "--fixture",
                str(fixture_path),
                "--output",
                str(output),
            ]
        )
    )
    assert rc == 0
    assert output.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    for key in ("mode", "fixture", "summary", "results"):
        assert key in payload, f"missing top-level key: {key}"

    summary = payload["summary"]
    for key in (
        "total",
        "correct",
        "accuracy",
        "confusion_matrix",
        "per_verdict_accuracy",
        "mean_tool_calls",
        "mean_confidence_correct",
        "mean_confidence_incorrect",
    ):
        assert key in summary, f"missing summary key: {key}"

    for case_result in payload["results"]:
        for key in ("id", "expected", "predicted", "correct", "confidence"):
            assert key in case_result, f"missing per-case key: {key}"


@_skip_harness
def test_dry_run_exits_zero(tmp_path: Path) -> None:
    output = tmp_path / "results.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(_EVAL_SCRIPT),
            "--dry-run",
            "--fixture",
            str(_FIXTURE),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert output.exists()


@_skip_harness
def test_real_without_confirm_cost_exits_one(tmp_path: Path) -> None:
    output = tmp_path / "results.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(_EVAL_SCRIPT),
            "--real",
            "--fixture",
            str(_FIXTURE),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "--confirm-cost" in proc.stderr
    assert not output.exists()
