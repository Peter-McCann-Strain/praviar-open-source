"""Tests for the report manifest provenance sidecar."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from praviar_pipeline import manifest as manifest_module
from praviar_pipeline.checkpoint import CheckpointIntegrityKeyRing
from praviar_pipeline.manifest import (
    PromptHasher,
    ReportManifest,
    ToolTraceRecorder,
    build_manifest,
    compute_source_tree_provenance,
    compute_tool_trace_digest,
    get_pipeline_version,
    get_prompt_hasher,
    get_tool_trace_recorder,
    require_pipeline_version,
    sanitize_tool_arguments,
    start_provenance_context,
)
from praviar_pipeline.models.report_common import (
    SourceHealth,
    SourceHealthEntry,
    SourceStatus,
)
from praviar_pipeline.response_cache import CacheMode, ResponseCache, set_current_cache

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_global_collectors():
    """Each test starts with empty global provenance collectors."""
    get_prompt_hasher().reset()
    get_tool_trace_recorder().reset()
    yield
    get_prompt_hasher().reset()
    get_tool_trace_recorder().reset()


@pytest.fixture
def fake_settings():
    return SimpleNamespace(
        claude_triage_model="claude-haiku-test",
        claude_analysis_model="claude-sonnet-test",
        claude_deep_model="claude-opus-test",
        checkpoint_integrity_keys=CheckpointIntegrityKeyRing(
            active_key_id="test-v1",
            _keys={"test-v1": b"test-manifest-integrity-key-000001"},
        ),
    )


@pytest.fixture
def source_health() -> SourceHealth:
    return SourceHealth(
        entries=[
            SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=12),
            SourceHealthEntry(source="lens", status=SourceStatus.FAILED, patent_count=0),
            SourceHealthEntry(source="kipris", status=SourceStatus.SKIPPED, patent_count=0),
        ]
    )


# ---------------------------------------------------------------------------
# PromptHasher
# ---------------------------------------------------------------------------


def test_prompt_hasher_records_sha256(tmp_path: Path) -> None:
    fixture = tmp_path / "fake_prompt.txt"
    fixture.write_text("hello world\n", encoding="utf-8")

    hasher = PromptHasher()
    digest = hasher.record(fixture.name, fixture.read_text())

    expected = hashlib.sha256(b"hello world\n").hexdigest()
    assert digest == expected
    assert hasher.snapshot() == {fixture.name: expected}


def test_prompt_hasher_byte_change_changes_hash() -> None:
    hasher = PromptHasher()
    hasher.record("p.txt", "alpha")
    first = hasher.snapshot()["p.txt"]

    hasher.record("p.txt", "alphA")
    second = hasher.snapshot()["p.txt"]

    assert first != second


def test_load_prompt_hooks_into_global_hasher() -> None:
    """The real load_prompt() should populate the singleton hasher."""
    from praviar_pipeline.clients.claude_prompting import PROMPTS_DIR, load_prompt

    sample = next(PROMPTS_DIR.glob("*.txt"))
    text = load_prompt(sample.name)
    snapshot = get_prompt_hasher().snapshot()

    assert sample.name in snapshot
    assert snapshot[sample.name] == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_two_runs_same_files_yield_identical_hashes(tmp_path: Path) -> None:
    f = tmp_path / "p.txt"
    f.write_text("stable content")

    h1 = PromptHasher()
    h1.record(f.name, f.read_text())
    snap1 = h1.snapshot()

    h2 = PromptHasher()
    h2.record(f.name, f.read_text())
    snap2 = h2.snapshot()

    assert snap1 == snap2


# ---------------------------------------------------------------------------
# Pipeline version
# ---------------------------------------------------------------------------


def test_pipeline_version_is_sha_in_checkout() -> None:
    sha = get_pipeline_version()
    if sha == "unknown":
        pytest.skip("not a git checkout")
    assert re.fullmatch(r"[0-9a-f]{40}", sha) is not None


def test_pipeline_version_unknown_outside_git(tmp_path: Path, monkeypatch) -> None:
    """Force ``_compute_pipeline_version`` to look in a non-git directory."""

    monkeypatch.delenv("PRAVIAR_PIPELINE_VERSION", raising=False)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode=128, stdout="", stderr="not a repo")

    monkeypatch.setattr(manifest_module.subprocess, "run", fake_run)
    assert manifest_module._compute_pipeline_version() == "unknown"


def test_pipeline_version_can_come_from_build_env(monkeypatch) -> None:
    sha = "b" * 40
    monkeypatch.setenv("PRAVIAR_PIPELINE_VERSION", sha)

    assert manifest_module._compute_pipeline_version() == sha


def test_require_pipeline_version_fails_when_unpinned(monkeypatch) -> None:
    monkeypatch.setattr(manifest_module, "get_pipeline_version", lambda: "unknown")

    with pytest.raises(RuntimeError, match="PRAVIAR_PIPELINE_VERSION"):
        require_pipeline_version()


def test_source_tree_provenance_is_bound() -> None:
    state, digest = compute_source_tree_provenance()
    assert state in {"clean", "dirty", "build"}
    assert re.fullmatch(r"[0-9a-f]{64}", digest)


# ---------------------------------------------------------------------------
# Tool trace digest
# ---------------------------------------------------------------------------


def test_tool_trace_digest_empty() -> None:
    assert compute_tool_trace_digest(None) == hashlib.sha256(b"").hexdigest()
    assert compute_tool_trace_digest([]) == hashlib.sha256(b"").hexdigest()


def test_tool_trace_digest_changes_with_call_order() -> None:
    a = [
        {"name": "search", "arguments": {"q": "foo", "limit": 10}},
        {"name": "fetch", "arguments": {"id": "X"}},
    ]
    b = list(reversed(a))
    key = b"test-tool-trace-key-material-0001"
    assert compute_tool_trace_digest(a, hmac_key=key) != compute_tool_trace_digest(b, hmac_key=key)


def test_tool_trace_digest_changes_with_args() -> None:
    a = [{"name": "search", "arguments": {"q": "foo"}}]
    b = [{"name": "search", "arguments": {"q": "foo", "limit": 5}}]
    key = b"test-tool-trace-key-material-0001"
    assert compute_tool_trace_digest(a, hmac_key=key) != compute_tool_trace_digest(b, hmac_key=key)


def test_tool_trace_digest_changes_with_argument_values() -> None:
    a = [{"name": "search", "arguments": {"q": "first secret"}}]
    b = [{"name": "search", "arguments": {"q": "second secret"}}]
    key = b"test-tool-trace-key-material-0001"
    assert compute_tool_trace_digest(a, hmac_key=key) != compute_tool_trace_digest(b, hmac_key=key)


# ---------------------------------------------------------------------------
# ToolTraceRecorder
# ---------------------------------------------------------------------------


def test_sanitize_tool_arguments_binds_values_without_retaining_plaintext() -> None:
    arguments = {
        "patent_id": "US1234567B2",
        "filters": {"org_id": "org_secret", "jurisdictions": ["US", "EP"]},
        "limit": 25,
    }

    sanitized = sanitize_tool_arguments(
        arguments,
        hmac_key=b"test-tool-trace-key-material-0001",
    )
    serialized = json.dumps(sanitized)

    assert sanitized["_format"] == "hmac-sha256-bound-v1"
    assert sanitized["_type"] == "dict"
    assert re.fullmatch(r"[0-9a-f]{64}", sanitized["_hmac_sha256"])
    assert "US1234567B2" not in serialized
    assert "org_secret" not in serialized


def test_tool_trace_recorder_records_sanitized_calls() -> None:
    recorder = ToolTraceRecorder()

    recorder.record_call(
        "lookup_patent",
        {"patent_id": "US1234567B2", "filters": {"org_id": "org_secret"}},
    )

    calls = recorder.snapshot_calls()
    assert calls[0]["name"] == "lookup_patent"
    assert calls[0]["arguments"]["_format"] == "hmac-sha256-bound-v1"
    assert "US1234567B2" not in json.dumps(calls)


@pytest.mark.asyncio
async def test_concurrent_runs_have_isolated_provenance_collectors() -> None:
    both_started = asyncio.Event()
    started = 0
    lock = asyncio.Lock()

    async def run(label: str) -> tuple[dict[str, str], list[dict[str, object]]]:
        nonlocal started
        hasher, recorder = start_provenance_context()
        hasher.record(f"{label}.txt", f"prompt-{label}")
        recorder.record_call("search", {"query": f"secret-{label}"})
        async with lock:
            started += 1
            if started == 2:
                both_started.set()
        await both_started.wait()
        return hasher.snapshot(), recorder.snapshot_calls()

    first, second = await asyncio.gather(run("first"), run("second"))

    assert set(first[0]) == {"first.txt"}
    assert set(second[0]) == {"second.txt"}
    assert first[1] != second[1]


def test_tool_definition_hashes_are_deterministic() -> None:
    recorder = ToolTraceRecorder()
    first_definition = {
        "name": "lookup_patent",
        "input_schema": {
            "properties": {"patent_id": {"type": "string"}},
            "type": "object",
        },
    }
    second_definition = {
        "input_schema": {
            "type": "object",
            "properties": {"patent_id": {"type": "string"}},
        },
        "name": "lookup_patent",
    }

    first = recorder.record_tool_definitions([first_definition])["lookup_patent"]
    recorder.reset()
    second = recorder.record_tool_definitions([second_definition])["lookup_patent"]

    assert first == second
    assert re.fullmatch(r"[0-9a-f]{64}", first)


def test_tool_definition_hash_conflict_fails_closed() -> None:
    recorder = ToolTraceRecorder()
    recorder.record_tool_definitions([{"name": "search", "input_schema": {"type": "object"}}])

    with pytest.raises(RuntimeError, match="tool definition hash changed"):
        recorder.record_tool_definitions(
            [{"name": "search", "input_schema": {"type": "object", "required": ["q"]}}]
        )


@pytest.mark.asyncio
async def test_execute_tool_blocks_records_sanitized_tool_attempt() -> None:
    from praviar_pipeline.clients.claude_tool_use import execute_tool_blocks

    class Toolkit:
        async def execute(self, name: str, arguments: dict[str, object]) -> str:
            assert name == "lookup_patent"
            assert arguments["patent_id"] == "US1234567B2"
            return "ok"

    logger = SimpleNamespace(debug=lambda *args, **kwargs: None)
    block = SimpleNamespace(
        id="toolu_1",
        name="lookup_patent",
        input={"patent_id": "US1234567B2", "filters": {"org_id": "org_secret"}},
    )

    results = await execute_tool_blocks(tool_blocks=[block], toolkit=Toolkit(), logger=logger)

    assert results[0]["type"] == "tool_result"
    assert results[0]["tool_use_id"] == "toolu_1"
    assert '<untrusted_source_data type="tool_result_lookup_patent"' in results[0]["content"]
    assert "ok" in results[0]["content"]
    calls = get_tool_trace_recorder().snapshot_calls()
    assert calls[0]["name"] == "lookup_patent"
    assert calls[0]["arguments"]["_format"] == "hmac-sha256-bound-v1"
    assert "US1234567B2" not in json.dumps(calls)


# ---------------------------------------------------------------------------
# build_manifest
# ---------------------------------------------------------------------------


def test_build_manifest_populates_all_fields(fake_settings, source_health) -> None:
    hasher = get_prompt_hasher()
    hasher.record("triage_system.txt", "TRIAGE PROMPT")
    hasher.record("evaluator_system.txt", "EVAL PROMPT")
    recorder = ToolTraceRecorder()
    recorder.record_tool_definitions(
        [{"name": "search", "input_schema": {"type": "object", "required": ["q"]}}]
    )
    recorder.record_call("search", {"q": "aspirin"})

    m = build_manifest(
        compound_query="aspirin",
        source_health=source_health,
        settings=fake_settings,
        tool_trace_recorder=recorder,
    )

    assert isinstance(m, ReportManifest)
    assert m.source_tree_state in {"clean", "dirty", "build"}
    assert re.fullmatch(r"[0-9a-f]{64}", m.source_tree_digest)
    assert m.compound_query == "aspirin"
    assert m.model_versions == {
        "triage": "claude-haiku-test",
        "analysis": "claude-sonnet-test",
        "deep": "claude-opus-test",
    }
    # Live observation is explicitly not misrepresented as a replayable snapshot.
    assert m.source_snapshots == {}
    assert set(m.source_observations) == {"pubchem_sdq"}
    assert "triage_system.txt" in m.prompt_hashes
    assert "evaluator_system.txt" in m.prompt_hashes
    assert set(m.tool_definition_hashes) == {"search"}
    assert m.tool_trace_digest != hashlib.sha256(b"").hexdigest()
    assert m.tool_call_count == 1
    assert {"triage", "analysis", "deep"} <= set(m.sampling.keys())
    assert m.sampling["triage"]["temperature"] == 0.0


def test_build_manifest_accepts_explicit_tool_calls(fake_settings, source_health) -> None:
    m = build_manifest(
        compound_query="aspirin",
        source_health=source_health,
        settings=fake_settings,
        tool_calls=[{"name": "search", "arguments": {"q": "aspirin"}}],
    )

    assert m.tool_trace_digest != hashlib.sha256(b"").hexdigest()
    assert m.tool_call_count == 1


@pytest.mark.asyncio
async def test_build_manifest_authenticates_retained_response_cache(
    fake_settings,
    source_health,
    tmp_path: Path,
) -> None:
    cache = ResponseCache(
        cache_dir=tmp_path / ".replay-cache/run_1",
        mode=CacheMode.RECORD,
        manifest_reference=".replay-cache/run_1/responses.jsonl",
    )
    await cache.wrap(
        source="pubchem",
        method="GET",
        url="/compound/1",
        body=None,
        call=lambda: asyncio.sleep(0, result={"cid": 1}),
    )
    set_current_cache(cache)
    try:
        manifest = build_manifest(
            compound_query="aspirin",
            source_health=source_health,
            settings=fake_settings,
        )
    finally:
        set_current_cache(None)

    assert manifest.response_cache_reference == ".replay-cache/run_1/responses.jsonl"
    assert manifest.response_cache_digest == cache.digest()
    assert manifest.response_cache_hmac_sha256 == cache.authenticated_digest(
        key=fake_settings.checkpoint_integrity_keys.active_key()
    )
    assert manifest.response_cache_key_id == "test-v1"
    assert manifest.response_cache_entry_count == 1


def test_manifest_is_frozen(fake_settings, source_health) -> None:
    m = build_manifest(compound_query="x", source_health=source_health, settings=fake_settings)
    with pytest.raises(ValidationError):
        m.compound_query = "y"


def test_manifest_serialization_round_trip(fake_settings, source_health) -> None:
    m = build_manifest(
        compound_query="aspirin", source_health=source_health, settings=fake_settings
    )
    payload = m.model_dump_json()
    parsed = ReportManifest.model_validate(json.loads(payload))
    assert parsed == m


# ---------------------------------------------------------------------------
# FTOReport integration
# ---------------------------------------------------------------------------


def test_ftoreport_accepts_manifest(fake_settings, source_health, succinic_acid) -> None:
    from praviar_pipeline.models.analysis import RiskLevel
    from praviar_pipeline.models.report import FTOReport, RiskSummary

    m = build_manifest(
        compound_query="succinic acid",
        source_health=source_health,
        settings=fake_settings,
    )
    report = FTOReport(
        compound=succinic_acid,
        risk_summary=RiskSummary(
            overall_risk=RiskLevel.CLEAR,
            executive_summary="ok",
        ),
        manifest=m,
    )
    assert report.manifest is not None
    assert report.manifest.compound_query == "succinic acid"

    # Serialise + reload via JSON to confirm it survives the report pipeline.
    blob = report.model_dump_json()
    reloaded = FTOReport.model_validate_json(blob)
    assert reloaded.manifest == m


def test_ftoreport_manifest_default_none(succinic_acid) -> None:
    """Existing serialized reports without a manifest field still load."""
    from praviar_pipeline.models.analysis import RiskLevel
    from praviar_pipeline.models.report import FTOReport, RiskSummary

    report = FTOReport(
        compound=succinic_acid,
        risk_summary=RiskSummary(
            overall_risk=RiskLevel.CLEAR,
            executive_summary="ok",
        ),
    )
    assert report.manifest is None
