"""Tests that offline safety evidence identifies the exact checked-out code state."""

from __future__ import annotations

import subprocess
from pathlib import Path

from research.tools.benchmarks import offline_safety_smoke


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_working_tree_state_content_binds_tracked_and_untracked_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Offline Smoke Test")
    _git(tmp_path, "config", "user.email", "offline-smoke@example.test")
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("committed\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-q", "-m", "fixture")
    monkeypatch.setattr(offline_safety_smoke, "REPO_ROOT", tmp_path)

    clean, clean_hash = offline_safety_smoke._working_tree_state()
    assert clean is False

    tracked.write_text("modified\n", encoding="utf-8")
    tracked_dirty, tracked_hash = offline_safety_smoke._working_tree_state()
    assert tracked_dirty is True
    assert tracked_hash != clean_hash

    untracked = tmp_path / "untracked.txt"
    untracked.write_text("first\n", encoding="utf-8")
    untracked_dirty, first_untracked_hash = offline_safety_smoke._working_tree_state()
    assert untracked_dirty is True
    assert first_untracked_hash != tracked_hash

    untracked.write_text("second\n", encoding="utf-8")
    _, second_untracked_hash = offline_safety_smoke._working_tree_state()
    assert second_untracked_hash != first_untracked_hash


def test_authoritative_status_cassette_uses_concrete_adapter_path() -> None:
    cassettes = offline_safety_smoke._load_cassettes()
    case = next(
        case
        for case in cassettes["cases"]
        if case["category"] == "authoritative_status_conflict"
    )

    actual = offline_safety_smoke._decision_case(case)

    assert actual["decision"] == "unclear"
    assert actual["unresolved_contradictions"] == [
        (
            "Decision evidence for EP9999999B1 conflicts with authoritative "
            "legal status observations: active, revoked."
        )
    ]


def test_active_blocker_cassette_requires_governed_positive_controls() -> None:
    cassettes = offline_safety_smoke._load_cassettes()
    case = next(
        case
        for case in cassettes["cases"]
        if case["category"] == "active_blocker"
    )

    actual = offline_safety_smoke._decision_case(case)

    assert actual["decision"] == "blocked"
    assert actual["blocking_claim_ids"] == ["US9999999B2#claim1"]
    assert actual["claim_program_decisions"][0]["legal_status_provenance_verified"] is True
    assert actual["claim_program_decisions"][0]["accused_acts_verified"] is True
