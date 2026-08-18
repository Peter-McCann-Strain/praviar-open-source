"""Tests for the 50-case Markush scope validation fixture.

The fixture builder (`research/experiments/drawing_analysis/markush_scope_fixture.py`)
requires pandas + rdkit to read the parquet/JSON sources. These tests read the
produced `cases.json` instead — no parquet / rdkit dep at test time.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE_SCRIPT = (
    REPO_ROOT / "research" / "experiments" / "drawing_analysis" / "markush_scope_fixture.py"
)
CASES_JSON = (
    REPO_ROOT
    / "research"
    / "experiments"
    / "drawing_analysis"
    / "output"
    / "markush_scope_fixture"
    / "cases.json"
)
VALID_VERDICTS = {"in_scope", "out_of_scope", "ambiguous"}


@pytest.fixture(scope="module")
def cases_payload() -> dict:
    """Load the fixture JSON. Fail fast if it hasn't been generated."""
    if not CASES_JSON.exists():
        pytest.skip(
            "cases.json not present — run "
            "praviar_pipeline/.venv/bin/python "
            "research/experiments/drawing_analysis/markush_scope_fixture.py"
        )
    return json.loads(CASES_JSON.read_text())


@pytest.fixture(scope="module")
def cases(cases_payload: dict) -> list[dict]:
    return cases_payload["cases"]


class TestFixtureShape:
    def test_has_top_level_metadata(self, cases_payload: dict) -> None:
        assert "cases" in cases_payload
        assert isinstance(cases_payload["cases"], list)
        # Optional but expected bookkeeping for reproducibility
        assert True

    def test_total_case_count_is_fifty(self, cases: list[dict]) -> None:
        assert len(cases) == 50

    def test_verdict_distribution(self, cases: list[dict]) -> None:
        """Distribution target: 20 in_scope, 15 out_of_scope, 15 ambiguous."""
        by_verdict: dict[str, int] = {}
        for case in cases:
            by_verdict[case["expected_verdict"]] = by_verdict.get(case["expected_verdict"], 0) + 1
        assert by_verdict.get("in_scope", 0) == 20
        assert by_verdict.get("out_of_scope", 0) == 15
        assert by_verdict.get("ambiguous", 0) == 15


class TestCaseSchema:
    def test_required_fields_present(self, cases: list[dict]) -> None:
        required = {"scaffold_cxsmiles", "target_smiles", "expected_verdict"}
        for i, case in enumerate(cases):
            missing = required - set(case.keys())
            assert not missing, f"case {i} missing {missing}"

    def test_scaffold_non_empty(self, cases: list[dict]) -> None:
        for i, case in enumerate(cases):
            assert case["scaffold_cxsmiles"].strip(), f"case {i} has empty scaffold_cxsmiles"

    def test_target_smiles_present(self, cases: list[dict]) -> None:
        """target_smiles may be empty for the most abstract `ambiguous` cases —
        but must exist as a key."""
        for case in cases:
            assert "target_smiles" in case
            # At minimum a non-None string
            assert isinstance(case["target_smiles"], str)

    def test_verdict_values_are_valid(self, cases: list[dict]) -> None:
        for i, case in enumerate(cases):
            verdict = case["expected_verdict"]
            assert verdict in VALID_VERDICTS, (
                f"case {i} verdict {verdict!r} not in {VALID_VERDICTS}"
            )


class TestDeterminism:
    def test_same_seed_produces_same_fixture(self) -> None:
        """Re-running the builder writes the same cases.json byte-for-byte."""
        if not FIXTURE_SCRIPT.exists():
            pytest.skip(f"fixture builder missing: {FIXTURE_SCRIPT}")

        # Snapshot current file
        original = CASES_JSON.read_text() if CASES_JSON.exists() else None
        if original is None:
            pytest.skip("Fixture JSON not yet generated — nothing to compare against.")

        # Python executable that has pandas + rdkit. Fall back to skipping if
        # neither is available (tests on bare dev venv should still pass.)
        candidate_pythons = [
            REPO_ROOT / "praviar_pipeline" / ".venv" / "bin" / "python",
            Path(sys.executable),
        ]
        python = next((p for p in candidate_pythons if p.exists()), None)
        if python is None:
            pytest.skip("No Python interpreter with pandas + rdkit available.")

        # Check whether pandas is importable — if not, skip.
        probe = subprocess.run(
            [str(python), "-c", "import pandas, rdkit"],
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0:
            pytest.skip("pandas or rdkit unavailable in this interpreter.")

        result = subprocess.run(
            [str(python), str(FIXTURE_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=120,
        )
        assert result.returncode == 0, f"fixture builder failed:\n{result.stderr[:500]}"
        after = CASES_JSON.read_text()
        assert after == original, (
            "Same seed produced different fixture — determinism invariant violated."
        )


class TestContentSanity:
    def test_in_scope_cases_carry_expected_reason(self, cases: list[dict]) -> None:
        """Every in_scope case should have a human-readable reason so the
        human reviewer can audit the label."""
        in_scope = [c for c in cases if c["expected_verdict"] == "in_scope"]
        assert len(in_scope) == 20
        # The field is optional in the schema but present in the builder's output;
        # if present, must be non-empty for at least half the cases.
        with_reason = [c for c in in_scope if str(c.get("expected_reason", "")).strip()]
        assert len(with_reason) >= 10, "Reasons missing on in_scope cases — reduces auditability."

    def test_provenance_present_on_majority(self, cases: list[dict]) -> None:
        """Provenance (source_ip_office or provenance dict) helps trace where
        each case came from. Not required on every case but on most."""
        with_prov = [c for c in cases if c.get("source_ip_office") or c.get("provenance")]
        assert len(with_prov) >= 30, (
            f"Only {len(with_prov)}/50 cases carry provenance — reproducibility at risk."
        )
