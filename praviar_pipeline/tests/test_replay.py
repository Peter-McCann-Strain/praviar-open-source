"""Tests for the manifest replay module and CLI."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from praviar_pipeline.cli_replay import _resolve_response_cache_dir, build_parser
from praviar_pipeline.cli_replay import main as cli_replay_main
from praviar_pipeline.manifest import ReportManifest, compute_source_tree_provenance
from praviar_pipeline.replay import (
    PreconditionResult,
    ReportDiff,
    apply_pinned_config,
    diff_reports,
    load_manifest,
    verify_preconditions,
)

if TYPE_CHECKING:
    from pathlib import Path


def _make_manifest(
    *,
    pipeline_version: str = "a" * 40,
    compound_query: str = "aspirin",
    prompt_hashes: dict[str, str] | None = None,
    model_versions: dict[str, str] | None = None,
    tool_definition_hashes: dict[str, str] | None = None,
) -> ReportManifest:
    source_tree_state, source_tree_digest = compute_source_tree_provenance()
    return ReportManifest(
        pipeline_version=pipeline_version,
        source_tree_state=source_tree_state,
        source_tree_digest=source_tree_digest,
        generated_at=datetime.now(UTC),
        compound_query=compound_query,
        prompt_hashes=prompt_hashes or {},
        model_versions=model_versions
        or {
            "triage": "claude-sonnet-4-6-20260301",
            "analysis": "claude-opus-4-6-20260301",
            "deep": "claude-opus-4-6-20260301",
        },
        sampling={"analysis": {"temperature": 0.0, "top_p": 1.0}},
        source_snapshots={"pubchem": "2026-04-15T10:00:00+00:00"},
        source_observations={},
        tool_definition_hashes=tool_definition_hashes or {},
        tool_trace_digest=hashlib.sha256(b"").hexdigest(),
    )


# ---------------------------------------------------------------------------
# load_manifest
# ---------------------------------------------------------------------------


def test_load_manifest_roundtrip(tmp_path: Path) -> None:
    manifest = _make_manifest()
    path = tmp_path / "m.json"
    path.write_text(manifest.model_dump_json())
    loaded = load_manifest(path)
    assert loaded.pipeline_version == manifest.pipeline_version
    assert loaded.compound_query == "aspirin"
    assert loaded.model_versions["analysis"] == "claude-opus-4-6-20260301"


def test_load_manifest_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_manifest(tmp_path / "nope.json")


def test_load_manifest_invalid_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_manifest(bad)


def test_load_manifest_schema_mismatch(tmp_path: Path) -> None:
    bad = tmp_path / "wrong_shape.json"
    bad.write_text(json.dumps({"unexpected": "payload"}))
    with pytest.raises(ValueError, match="does not match the expected schema"):
        load_manifest(bad)


# ---------------------------------------------------------------------------
# verify_preconditions
# ---------------------------------------------------------------------------


def _prompts_dir(tmp_path: Path, files: dict[str, str]) -> Path:
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    for name, content in files.items():
        (prompts / name).write_text(content)
    return prompts


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_verify_preconditions_all_match(tmp_path: Path, monkeypatch) -> None:
    # Match current git SHA so version comparison passes.
    from praviar_pipeline import replay as replay_mod

    monkeypatch.setattr(replay_mod, "get_pipeline_version", lambda: "a" * 40)

    prompts = _prompts_dir(tmp_path, {"triage.txt": "triage body"})
    manifest = _make_manifest(prompt_hashes={"triage.txt": _sha("triage body")})

    result = verify_preconditions(manifest, prompts_dir=prompts)
    assert result.ok is True
    assert result.version_matches
    assert result.prompt_drift == {}
    assert result.missing_prompts == []
    assert result.tool_definition_drift == {}
    assert result.missing_tool_definitions == []


def test_verify_preconditions_detects_version_drift(tmp_path: Path, monkeypatch) -> None:
    from praviar_pipeline import replay as replay_mod

    monkeypatch.setattr(replay_mod, "get_pipeline_version", lambda: "b" * 40)

    prompts = _prompts_dir(tmp_path, {"triage.txt": "triage body"})
    manifest = _make_manifest(prompt_hashes={"triage.txt": _sha("triage body")})

    result = verify_preconditions(manifest, prompts_dir=prompts)
    assert result.ok is False
    assert result.version_matches is False
    assert result.version_diff == ("a" * 40, "b" * 40)


def test_verify_preconditions_detects_prompt_drift(tmp_path: Path, monkeypatch) -> None:
    from praviar_pipeline import replay as replay_mod

    monkeypatch.setattr(replay_mod, "get_pipeline_version", lambda: "a" * 40)

    # Prompt contents changed since manifest was recorded.
    prompts = _prompts_dir(tmp_path, {"triage.txt": "triage body CHANGED"})
    manifest = _make_manifest(prompt_hashes={"triage.txt": _sha("triage body")})

    result = verify_preconditions(manifest, prompts_dir=prompts)
    assert result.ok is False
    assert "triage.txt" in result.prompt_drift


def test_verify_preconditions_detects_missing_prompt(tmp_path: Path, monkeypatch) -> None:
    from praviar_pipeline import replay as replay_mod

    monkeypatch.setattr(replay_mod, "get_pipeline_version", lambda: "a" * 40)

    prompts = _prompts_dir(tmp_path, {})  # empty dir
    manifest = _make_manifest(prompt_hashes={"triage.txt": _sha("triage body")})

    result = verify_preconditions(manifest, prompts_dir=prompts)
    assert result.ok is False
    assert "triage.txt" in result.missing_prompts


def test_verify_preconditions_detects_tool_definition_drift(tmp_path: Path, monkeypatch) -> None:
    from praviar_pipeline import replay as replay_mod

    monkeypatch.setattr(replay_mod, "get_pipeline_version", lambda: "a" * 40)

    prompts = _prompts_dir(tmp_path, {"triage.txt": "triage body"})
    manifest = _make_manifest(
        prompt_hashes={"triage.txt": _sha("triage body")},
        tool_definition_hashes={"lookup_patent": "f" * 64},
    )

    result = verify_preconditions(manifest, prompts_dir=prompts)
    assert result.ok is False
    assert "lookup_patent" in result.tool_definition_drift


def test_verify_preconditions_detects_missing_tool_definition(tmp_path: Path, monkeypatch) -> None:
    from praviar_pipeline import replay as replay_mod

    monkeypatch.setattr(replay_mod, "get_pipeline_version", lambda: "a" * 40)

    prompts = _prompts_dir(tmp_path, {"triage.txt": "triage body"})
    manifest = _make_manifest(
        prompt_hashes={"triage.txt": _sha("triage body")},
        tool_definition_hashes={"retired_tool": "f" * 64},
    )

    result = verify_preconditions(manifest, prompts_dir=prompts)
    assert result.ok is False
    assert result.missing_tool_definitions == ["retired_tool"]


def test_verify_preconditions_allow_drift_overrides_ok_flag(tmp_path: Path, monkeypatch) -> None:
    from praviar_pipeline import replay as replay_mod

    monkeypatch.setattr(replay_mod, "get_pipeline_version", lambda: "b" * 40)

    prompts = _prompts_dir(tmp_path, {"triage.txt": "triage body"})
    manifest = _make_manifest(prompt_hashes={"triage.txt": _sha("triage body")})

    result = verify_preconditions(manifest, prompts_dir=prompts, allow_drift=True)
    # Still reports the drift in fields, but ok=True so callers can proceed.
    assert result.ok is True
    assert result.version_matches is False


# ---------------------------------------------------------------------------
# apply_pinned_config
# ---------------------------------------------------------------------------


class _FakeSettings:
    """Minimal Pydantic-like settings object for the apply_pinned_config test."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def model_copy(self, *, update: dict) -> _FakeSettings:
        merged = {**self.__dict__, **update}
        return _FakeSettings(**merged)


def test_apply_pinned_config_overrides_model_ids() -> None:
    manifest = _make_manifest(
        model_versions={
            "triage": "claude-sonnet-X",
            "analysis": "claude-opus-Y",
            "deep": "claude-opus-Z",
        }
    )
    original = _FakeSettings(
        claude_triage_model="default-triage",
        claude_analysis_model="default-analysis",
        claude_deep_model="default-deep",
        other_field="unchanged",
    )
    pinned = apply_pinned_config(manifest, original)
    assert pinned.claude_triage_model == "claude-sonnet-X"
    assert pinned.claude_analysis_model == "claude-opus-Y"
    assert pinned.claude_deep_model == "claude-opus-Z"
    # Unrelated fields are preserved.
    assert pinned.other_field == "unchanged"
    # Original is unchanged (copy semantics).
    assert original.claude_triage_model == "default-triage"


def test_apply_pinned_config_empty_manifest_is_noop() -> None:
    # All empty strings => no model_id overrides => return original unchanged.
    manifest = _make_manifest(model_versions={"triage": "", "analysis": "", "deep": ""})
    original = _FakeSettings(claude_triage_model="default-triage")
    pinned = apply_pinned_config(manifest, original)
    # Same object returned when no overrides to apply.
    assert pinned is original


# ---------------------------------------------------------------------------
# diff_reports
# ---------------------------------------------------------------------------


def test_diff_identical_reports() -> None:
    payload = {
        "risk_summary": {"overall_risk": "MEDIUM"},
        "patents": [{"patent_id": "US1"}, {"patent_id": "US2"}],
    }
    diff = diff_reports(payload, payload)
    assert diff.identical is True
    assert diff.risk_verdict_matches is True
    assert diff.patent_count_delta == 0


def test_diff_risk_verdict_change() -> None:
    original = {
        "risk_summary": {"overall_risk": "HIGH"},
        "patents": [{"patent_id": "US1"}],
    }
    replayed = {
        "risk_summary": {"overall_risk": "MEDIUM"},
        "patents": [{"patent_id": "US1"}],
    }
    diff = diff_reports(original, replayed)
    assert diff.risk_verdict_matches is False
    assert any("Governed verdict changed" in m for m in diff.messages)
    assert diff.identical is False


def test_diff_patent_set_change() -> None:
    original = {
        "risk_summary": {"overall_risk": "LOW"},
        "patents": [{"patent_id": "US1"}, {"patent_id": "US2"}],
    }
    replayed = {
        "risk_summary": {"overall_risk": "LOW"},
        "patents": [{"patent_id": "US2"}, {"patent_id": "US3"}],
    }
    diff = diff_reports(original, replayed)
    assert diff.identical is False
    assert diff.unique_to_original == ["US1"]
    assert diff.unique_to_replay == ["US3"]
    assert diff.patent_count_delta == 0


def test_diff_uses_canonical_patent_analyses() -> None:
    original = {
        "clearance_decision": {"decision": "clear"},
        "risk_summary": {"overall_risk": "CLEAR"},
        "patent_analyses": [{"patent_id": "US-ORIGINAL"}],
    }
    replayed = {
        "clearance_decision": {"decision": "clear"},
        "risk_summary": {"overall_risk": "CLEAR"},
        "patent_analyses": [{"patent_id": "US-REPLAY"}],
    }

    diff = diff_reports(original, replayed)

    assert diff.identical is False
    assert diff.unique_to_original == ["US-ORIGINAL"]
    assert diff.unique_to_replay == ["US-REPLAY"]


def test_diff_prefers_governed_clearance_decision_over_legacy_risk() -> None:
    original = {
        "clearance_decision": {"decision": "clear"},
        "risk_summary": {"overall_risk": "LOW"},
        "patent_analyses": [{"patent_id": "US1"}],
    }
    replayed = {
        "clearance_decision": {"decision": "blocked"},
        "risk_summary": {"overall_risk": "LOW"},
        "patent_analyses": [{"patent_id": "US1"}],
    }

    diff = diff_reports(original, replayed)

    assert diff.identical is False
    assert diff.risk_verdict_matches is False
    assert any("clearance_decision.decision" in message for message in diff.messages)


def test_diff_detects_loss_of_governed_decision() -> None:
    original = {
        "clearance_decision": {"decision": "clear"},
        "risk_summary": {"overall_risk": "CLEAR"},
    }
    replayed = {"risk_summary": {"overall_risk": "CLEAR"}}

    assert diff_reports(original, replayed).identical is False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_parser_accepts_manifest_path(tmp_path: Path) -> None:
    parser = build_parser()
    args = parser.parse_args([str(tmp_path / "m.json")])
    assert args.manifest_path == tmp_path / "m.json"
    assert args.allow_drift is False
    assert args.run is False


def test_cli_parser_allows_flags(tmp_path: Path) -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            str(tmp_path / "m.json"),
            "--allow-drift",
            "--run",
            "--original",
            str(tmp_path / "orig.json"),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert args.allow_drift is True
    assert args.run is True
    assert args.original == tmp_path / "orig.json"
    assert args.output_dir == tmp_path / "out"


def test_exact_replay_resolves_retained_cache_beside_manifest(tmp_path: Path) -> None:
    cache_path = tmp_path / ".replay-cache/run_1/responses.jsonl"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text("")
    manifest = _make_manifest().model_copy(
        update={
            "response_cache_reference": ".replay-cache/run_1/responses.jsonl",
            "response_cache_digest": "a" * 64,
            "response_cache_hmac_sha256": "b" * 64,
            "response_cache_key_id": "test-v1",
        }
    )

    assert (
        _resolve_response_cache_dir(
            manifest,
            manifest_path=tmp_path / "report.manifest.json",
        )
        == cache_path.parent.resolve()
    )


def test_exact_replay_rejects_missing_or_escaping_cache_reference(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="exact response-cache"):
        _resolve_response_cache_dir(
            _make_manifest(),
            manifest_path=tmp_path / "report.manifest.json",
        )

    outside = tmp_path.parent / "responses.jsonl"
    outside.write_text("")
    manifest = _make_manifest().model_copy(
        update={
            "response_cache_reference": "../responses.jsonl",
            "response_cache_digest": "a" * 64,
            "response_cache_hmac_sha256": "b" * 64,
            "response_cache_key_id": "test-v1",
        }
    )
    with pytest.raises(RuntimeError, match="escapes"):
        _resolve_response_cache_dir(
            manifest,
            manifest_path=tmp_path / "report.manifest.json",
        )


def test_cli_missing_manifest_returns_manifest_error(tmp_path: Path, capsys) -> None:
    from praviar_pipeline.cli_replay import EXIT_MANIFEST_ERROR

    secret_path = tmp_path / "SECRET-token-customer-query.json"
    rc = cli_replay_main([str(secret_path)])
    assert rc == EXIT_MANIFEST_ERROR
    captured = capsys.readouterr()
    assert "replay manifest unavailable (FileNotFoundError)" in captured.err
    assert str(tmp_path) not in captured.err
    assert secret_path.name not in captured.err


def test_cli_verification_only_success(tmp_path: Path, monkeypatch, capsys) -> None:
    from praviar_pipeline import replay as replay_mod
    from praviar_pipeline.cli_replay import EXIT_OK

    monkeypatch.setattr(replay_mod, "get_pipeline_version", lambda: "a" * 40)
    # Point the replay module at a writable prompts dir for the duration of the test.
    prompts = _prompts_dir(tmp_path, {"triage.txt": "body"})
    manifest = _make_manifest(prompt_hashes={"triage.txt": _sha("body")})
    path = tmp_path / "m.json"
    path.write_text(manifest.model_dump_json())

    # Monkeypatch the default prompts dir resolution by overriding verify_preconditions
    # to use the test directory.
    import praviar_pipeline.cli_replay as cli_replay_mod

    original_verify = cli_replay_mod.verify_preconditions

    def _verify_with_test_prompts(m, **kwargs):
        kwargs.setdefault("prompts_dir", prompts)
        return original_verify(m, **kwargs)

    monkeypatch.setattr(cli_replay_mod, "verify_preconditions", _verify_with_test_prompts)

    rc = cli_replay_main([str(path)])
    assert rc == EXIT_OK
    captured = capsys.readouterr()
    assert "pipeline_version: MATCH" in captured.out
    assert "prompt_hashes: ALL MATCH" in captured.out
    assert "Verification-only mode" in captured.out


def test_cli_drift_exits_non_zero_without_allow_drift(tmp_path: Path, monkeypatch, capsys) -> None:
    from praviar_pipeline import replay as replay_mod
    from praviar_pipeline.cli_replay import EXIT_DRIFT

    monkeypatch.setattr(replay_mod, "get_pipeline_version", lambda: "b" * 40)
    prompts = _prompts_dir(tmp_path, {"triage.txt": "body"})
    manifest = _make_manifest(prompt_hashes={"triage.txt": _sha("body")})
    path = tmp_path / "m.json"
    path.write_text(manifest.model_dump_json())

    import praviar_pipeline.cli_replay as cli_replay_mod

    original_verify = cli_replay_mod.verify_preconditions

    def _verify_with_test_prompts(m, **kwargs):
        kwargs.setdefault("prompts_dir", prompts)
        return original_verify(m, **kwargs)

    monkeypatch.setattr(cli_replay_mod, "verify_preconditions", _verify_with_test_prompts)

    rc = cli_replay_main([str(path)])
    assert rc == EXIT_DRIFT
    captured = capsys.readouterr()
    assert "DRIFT detected" in captured.err


# ---------------------------------------------------------------------------
# Dataclass sanity
# ---------------------------------------------------------------------------


def test_precondition_result_defaults() -> None:
    r = PreconditionResult(ok=True, version_matches=True, version_diff=None)
    assert r.missing_prompts == []
    assert r.prompt_drift == {}
    assert r.messages == []


def test_report_diff_defaults() -> None:
    d = ReportDiff(identical=True, risk_verdict_matches=True, patent_count_delta=0)
    assert d.unique_to_original == []
    assert d.unique_to_replay == []
