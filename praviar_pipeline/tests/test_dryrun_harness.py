"""Tests for the zero-spend dry-run harness."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from praviar_pipeline.dryrun import (
    SHOWCASE_DRY_RUN_INPUT,
    DryRunAssertionError,
    DryRunError,
    assert_report_valid,
    attach_showcase_run_receipt,
    dry_run_provider,
    install_dry_run_harness,
    showcase_substantive_digest,
    validate_showcase_input,
)
from praviar_pipeline.response_cache import (
    CacheMode,
    get_current_cache,
    get_dry_run_provider,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Harness install/uninstall
# ---------------------------------------------------------------------------


def test_install_sets_cache_and_provider_then_restores() -> None:
    """The harness wires the cache + provider on enter and clears on exit."""
    assert get_current_cache() is None
    assert get_dry_run_provider() is None

    with install_dry_run_harness() as cache:
        assert cache.mode == CacheMode.DRY_RUN
        assert get_current_cache() is cache
        assert get_dry_run_provider() is dry_run_provider

    assert get_current_cache() is None
    assert get_dry_run_provider() is None


def test_install_restores_pubchem_methods() -> None:
    """Direct-httpx PubChem methods are restored on exit."""
    from praviar_pipeline.clients import pubchem as pubchem_mod

    original_similarity = pubchem_mod.PubChemClient.similarity_search
    original_poll = pubchem_mod.PubChemClient._poll_list_key

    with install_dry_run_harness():
        assert pubchem_mod.PubChemClient.similarity_search is not original_similarity
        assert pubchem_mod.PubChemClient._poll_list_key is not original_poll

    assert pubchem_mod.PubChemClient.similarity_search is original_similarity
    assert pubchem_mod.PubChemClient._poll_list_key is original_poll


def test_harness_is_re_installable_for_multiple_compounds() -> None:
    """Re-entering the harness cleanly re-installs the patches."""
    from praviar_pipeline.clients import pubchem as pubchem_mod

    original_similarity = pubchem_mod.PubChemClient.similarity_search

    for _ in range(3):
        with install_dry_run_harness() as cache:
            assert cache.mode == CacheMode.DRY_RUN
            assert pubchem_mod.PubChemClient.similarity_search is not original_similarity
        assert pubchem_mod.PubChemClient.similarity_search is original_similarity
        assert get_current_cache() is None


def test_nested_harness_restores_outer_provider_and_cache() -> None:
    """Nested test usage cannot clear the enclosing dry-run boundary."""
    with install_dry_run_harness() as outer_cache:
        with install_dry_run_harness() as inner_cache:
            assert inner_cache is not outer_cache
            assert get_current_cache() is inner_cache
            assert get_dry_run_provider() is dry_run_provider

        assert get_current_cache() is outer_cache
        assert get_dry_run_provider() is dry_run_provider

    assert get_current_cache() is None
    assert get_dry_run_provider() is None


def test_partial_install_failure_restores_global_state(monkeypatch) -> None:
    """Setup exceptions cannot leave fake credentials or monkey-patches active."""
    from praviar_pipeline.clients import pubchem as pubchem_mod

    original_api_key = os.environ.get("ANTHROPIC_API_KEY")
    original_similarity = pubchem_mod.PubChemClient.similarity_search

    def _fail_install(_state) -> None:
        raise RuntimeError("installation failed")

    monkeypatch.setattr(
        "praviar_pipeline.dryrun._install_analysis_patches",
        _fail_install,
    )
    with pytest.raises(RuntimeError, match="installation failed"):
        with install_dry_run_harness():
            raise AssertionError("unreachable")

    assert os.environ.get("ANTHROPIC_API_KEY") == original_api_key
    assert pubchem_mod.PubChemClient.similarity_search is original_similarity
    assert get_current_cache() is None
    assert get_dry_run_provider() is None


# ---------------------------------------------------------------------------
# 2. Cache dispatch + canned providers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_wrap_returns_canned_pubchem_response() -> None:
    """A pubchem cache.wrap() call routes to the canned provider."""
    with install_dry_run_harness() as cache:
        called = False

        async def _live() -> dict:
            nonlocal called
            called = True
            return {"should": "not be called"}

        result = await cache.wrap(
            source="pubchem",
            method="GET",
            url="/compound/cid/900000042/property/IUPACName/JSON",
            body=None,
            call=_live,
        )
        assert called is False
        assert "PropertyTable" in result


@pytest.mark.asyncio
async def test_cache_wrap_dispatches_synonyms_path() -> None:
    """The pubchem dispatcher picks the synonyms shape based on URL."""
    with install_dry_run_harness() as cache:

        async def _live() -> dict:
            raise AssertionError("live call should not happen")

        result = await cache.wrap(
            source="pubchem",
            method="GET",
            url="/compound/cid/900000042/synonyms/JSON",
            body=None,
            call=_live,
        )
        info = result["InformationList"]["Information"][0]
        assert "Synonym" in info


@pytest.mark.asyncio
async def test_cache_wrap_returns_canned_claude_complete_text_envelope() -> None:
    """A claude:<role> source produces a string envelope."""
    body = json.dumps(
        {
            "kind": "complete_text",
            "model": "claude-opus-4",
            "system": "system",
            "user": "user",
            "response_model": None,
            "max_tokens": 8192,
            "temperature": 0.0,
            "effort": None,
            "cache_system": False,
            "budget_tokens": None,
        },
        sort_keys=True,
    )
    with install_dry_run_harness() as cache:

        async def _live() -> dict:
            raise AssertionError("live call should not happen")

        envelope = await cache.wrap(
            source="claude:report",
            method="POST",
            url="messages/claude-opus-4",
            body=body,
            call=_live,
        )
        assert envelope["parsed_envelope"]["kind"] == "str"
        assert "Dry-run" in envelope["parsed_envelope"]["data"]
        assert envelope["usage"]["model"] == "dry-run"
        assert envelope["usage"]["input_tokens"] == 0
        assert envelope["usage"]["output_tokens"] == 0


@pytest.mark.asyncio
async def test_cache_wrap_builds_pydantic_envelope_for_triage() -> None:
    """A claude call requesting TriageResult yields a valid pydantic dump."""
    body = json.dumps(
        {
            "kind": "complete",
            "model": "claude-opus-4",
            "system": "system",
            "user": "user",
            "response_model": "praviar_pipeline.models.triage.TriageResult",
            "max_tokens": 8192,
            "temperature": 0.0,
            "effort": None,
            "cache_system": False,
            "budget_tokens": None,
        },
        sort_keys=True,
    )
    with install_dry_run_harness() as cache:

        async def _live() -> dict:
            raise AssertionError("live call should not happen")

        envelope = await cache.wrap(
            source="claude:triage",
            method="POST",
            url="messages/claude-opus-4",
            body=body,
            call=_live,
        )
        assert envelope["parsed_envelope"]["kind"] == "pydantic"
        data = envelope["parsed_envelope"]["data"]
        assert data["patent_id"] == "US0000000042A1"
        assert data["relevance"] == "relevant"


@pytest.mark.asyncio
async def test_cache_wrap_builds_triage_batch_for_prompt_patent_ids() -> None:
    """Dry-run triage must echo input patent IDs so Step 3 keeps the results."""
    body = json.dumps(
        {
            "kind": "complete",
            "model": "claude-opus-4",
            "system": "system",
            "user": "Patent ID: US0000000042A1\n\nPatent ID: US0000000043A1",
            "response_model": "praviar_pipeline.models.triage:TriageBatch",
            "max_tokens": 8192,
            "temperature": 0.0,
            "effort": None,
            "cache_system": False,
            "budget_tokens": None,
        },
        sort_keys=True,
    )
    with install_dry_run_harness() as cache:

        async def _live() -> dict:
            raise AssertionError("live call should not happen")

        envelope = await cache.wrap(
            source="claude:triage",
            method="POST",
            url="messages/claude-opus-4",
            body=body,
            call=_live,
        )
        data = envelope["parsed_envelope"]["data"]
        assert [row["patent_id"] for row in data["results"]] == [
            "US0000000042A1",
            "US0000000043A1",
        ]
        assert envelope["usage"]["model"] == "dry-run"


# ---------------------------------------------------------------------------
# 3. Pipeline-step smoke test (step1_resolve)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_step1_resolve_under_harness_returns_resolved_compound(mock_settings) -> None:
    """Step 1 (compound resolution) runs end-to-end under the harness.

    Validates that pubchem GET routes through the cache to canned data and
    the direct-httpx similarity_search monkey-patch returns canned results.
    """
    from praviar_pipeline.pipeline.step1_resolve import resolve_compound

    with install_dry_run_harness():
        compound = await resolve_compound(SHOWCASE_DRY_RUN_INPUT)

    assert compound.pubchem_cid == 900_000_042
    assert compound.canonical_smiles == "[*:42]~[*:43]"
    assert compound.original_input == SHOWCASE_DRY_RUN_INPUT
    assert isinstance(compound.related_compounds, list)


@pytest.mark.asyncio
async def test_step1_resolve_under_harness_rejects_non_showcase_input(mock_settings) -> None:
    """Explicit dry-run mode fails closed instead of inventing another compound."""
    from praviar_pipeline.pipeline.step1_resolve import resolve_compound

    with install_dry_run_harness():
        with pytest.raises(DryRunError, match="canonical fictional input"):
            await resolve_compound("unregistered example")


def test_patcid_provider_returns_query_shape_for_prefix() -> None:
    result = dry_run_provider(
        source="patcid",
        method="QUERY",
        url="inchikey_prefix=FICTIONALPVXAB",
        body=None,
    )
    assert result == [
        {"inchikey": "FICTIONALPVXAB-DEMOFIXTUR-N", "patent_id": "US0000000042A1"},
        {"inchikey": "FICTIONALPVXAB-DEMOFIXTUR-N", "patent_id": "US0000000043A1"},
    ]


# ---------------------------------------------------------------------------
# 4 + 5. assert_report_valid catches missing fields
# ---------------------------------------------------------------------------


def _baseline_report() -> dict:
    return {
        "compound": {"original_input": SHOWCASE_DRY_RUN_INPUT},
        "patents": [],
        "analyses": [],
        "risk_summary": {"overall_risk": "low"},
        "audit_trail": {
            "timing_data": [
                {"step_name": step_name}
                for step_name in (
                    "step1_resolve",
                    "step2_search",
                    "step3_triage",
                    "step4_analyze",
                    "step5_doe",
                    "step6_invalid",
                    "step7_verify",
                    "step8_report",
                )
            ]
        },
        "source_health": {"entries": [{"source": "pubchem", "status": "ok"}]},
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "estimated_cost_usd": 0.0,
        "manifest": {
            "pipeline_version": "0.1.0",
            "generated_at": "2026-04-15T00:00:00Z",
            "prompt_hashes": {"system": "abc"},
            "model_versions": {"analysis": "claude-opus-4"},
            "tool_definition_hashes": {"lookup_patent": "0" * 64},
            "tool_trace_digest": "0" * 64,
            "tool_call_count": 1,
            "cost_breakdown": {"total_cost_usd": 0.0},
            "total_cost_usd": 0.0,
        },
    }


def test_assert_report_valid_passes_baseline() -> None:
    assert_report_valid(_baseline_report())


def test_assert_report_valid_catches_missing_top_level_field() -> None:
    report = _baseline_report()
    del report["risk_summary"]
    with pytest.raises(DryRunAssertionError) as excinfo:
        assert_report_valid(report)
    assert "risk_summary" in excinfo.value.field_path


def test_assert_report_valid_catches_missing_pipeline_version() -> None:
    report = _baseline_report()
    report["manifest"].pop("pipeline_version")
    with pytest.raises(DryRunAssertionError) as excinfo:
        assert_report_valid(report)
    assert "pipeline_version" in excinfo.value.field_path


@pytest.mark.parametrize("bad_status", ["failed", "not_configured", "unknown"])
def test_assert_report_valid_catches_any_unavailable_source(bad_status: str) -> None:
    """A showcase receipt cannot normalize unavailable or unknown sources."""
    report = _baseline_report()
    report["source_health"]["entries"].extend(
        [
            {"source": "lens", "status": "ok"},
            {"source": "surechembl", "status": "ok"},
            {"source": "epo_ops", "status": bad_status, "error_message": "boom"},
        ]
    )
    with pytest.raises(DryRunAssertionError) as excinfo:
        assert_report_valid(report)
    assert excinfo.value.field_path.endswith(".status")


@pytest.mark.parametrize("entries", [[], None])
def test_assert_report_valid_rejects_empty_source_health(entries) -> None:
    """A run with no source execution evidence cannot receive a receipt."""
    report = _baseline_report()
    report["source_health"]["entries"] = entries
    with pytest.raises(DryRunAssertionError, match="missing or empty"):
        assert_report_valid(report)


def test_assert_report_valid_rejects_all_skipped_source_health() -> None:
    """Intentional skips cannot substitute for successful source evidence."""
    report = _baseline_report()
    report["source_health"]["entries"] = [
        {"source": "uspto_odp", "status": "skipped"},
        {"source": "epo_register", "status": "skipped"},
    ]

    with pytest.raises(DryRunAssertionError, match="no successful source execution"):
        assert_report_valid(report)


def test_assert_report_valid_catches_missing_prompt_hashes() -> None:
    report = _baseline_report()
    report["manifest"]["prompt_hashes"] = {}
    with pytest.raises(DryRunAssertionError) as excinfo:
        assert_report_valid(report)
    assert "prompt_hashes" in excinfo.value.field_path


def test_assert_report_valid_catches_missing_tool_provenance() -> None:
    report = _baseline_report()
    report["manifest"].pop("tool_trace_digest")
    with pytest.raises(DryRunAssertionError) as excinfo:
        assert_report_valid(report)
    assert "tool_trace_digest" in excinfo.value.field_path


# ---------------------------------------------------------------------------
# 6. CLI parsing for --dry-run / --output-dir
# ---------------------------------------------------------------------------


def test_parse_run_args_recognises_dry_run_flag() -> None:
    from praviar_pipeline.pipeline.runtime.cli_args import parse_run_args

    parsed = parse_run_args([SHOWCASE_DRY_RUN_INPUT, "--dry-run", "--output-dir", "/tmp/x"])
    assert parsed.dry_run is True
    assert parsed.output_dir == "/tmp/x"
    assert parsed.user_input == SHOWCASE_DRY_RUN_INPUT


def test_parse_run_args_dry_run_default_false() -> None:
    from praviar_pipeline.pipeline.runtime.cli_args import parse_run_args

    parsed = parse_run_args([SHOWCASE_DRY_RUN_INPUT])
    assert parsed.dry_run is False
    assert parsed.output_dir is None


# ---------------------------------------------------------------------------
# 7. Dry-run runner smoke — the CLI dry-run path completes without crashing.
# ---------------------------------------------------------------------------


def test_run_dry_run_emits_failure_on_pipeline_exception(tmp_path: Path, capsys) -> None:
    """If the pipeline raises, the runner returns non-zero and prints why."""
    from praviar_pipeline.pipeline.runtime.cli_args import RunCliArgs
    from praviar_pipeline.pipeline.runtime.cli_runner import _run_dry_run

    async def _broken_pipeline(*args, **kwargs):
        raise RuntimeError("SECRET-token-customer-query")

    args = RunCliArgs(
        user_input=SHOWCASE_DRY_RUN_INPUT,
        dry_run=True,
        output_dir=str(tmp_path),
    )
    rc = _run_dry_run(
        cli_args=args,
        run_pipeline_fn=_broken_pipeline,
        emit_json_report_fn=lambda *a, **kw: None,
    )
    assert rc == 2
    captured = capsys.readouterr()
    assert "DRY-RUN FAILED: pipeline raised RuntimeError" in captured.out
    assert "SECRET-token-customer-query" not in captured.out


def test_run_dry_run_emits_assertion_failure(tmp_path: Path) -> None:
    """If the pipeline returns an invalid report, the runner returns 3."""
    from praviar_pipeline.pipeline.runtime.cli_args import RunCliArgs
    from praviar_pipeline.pipeline.runtime.cli_runner import _run_dry_run

    async def _bad_report_pipeline(*args, **kwargs):
        return {"patents": []}  # missing analyses, risk_summary, manifest

    args = RunCliArgs(
        user_input=SHOWCASE_DRY_RUN_INPUT,
        dry_run=True,
        output_dir=str(tmp_path),
    )
    rc = _run_dry_run(
        cli_args=args,
        run_pipeline_fn=_bad_report_pipeline,
        emit_json_report_fn=lambda *a, **kw: None,
    )
    assert rc == 3


def test_run_dry_run_succeeds_on_valid_canned_report(tmp_path: Path) -> None:
    """A pipeline that returns a valid baseline report yields rc=0 + writes JSON."""
    from praviar_pipeline.pipeline.runtime.cli_args import RunCliArgs
    from praviar_pipeline.pipeline.runtime.cli_runner import _run_dry_run

    observed_kwargs = {}

    async def _good_pipeline(*args, **kwargs):
        observed_kwargs.update(kwargs)
        return _baseline_report()

    args = RunCliArgs(
        user_input=SHOWCASE_DRY_RUN_INPUT,
        dry_run=True,
        output_dir=str(tmp_path),
    )
    rc = _run_dry_run(
        cli_args=args,
        run_pipeline_fn=_good_pipeline,
        emit_json_report_fn=lambda *a, **kw: None,
    )
    assert rc == 0
    assert (tmp_path / "dryrun-report.json").is_file()
    saved = json.loads((tmp_path / "dryrun-report.json").read_text())
    assert saved["showcase_run"]["completed_stages"][-1] == "step8_report"
    assert saved["showcase_run"]["external_provider_calls"] == 0
    assert observed_kwargs["config_overrides"]["output_dir"] == str(tmp_path)
    assert observed_kwargs["config_overrides"]["matter_type"] == "small_molecule"
    assert observed_kwargs["config_overrides"]["target_jurisdictions"] == []


def test_run_dry_run_rejects_unknown_input_before_pipeline(tmp_path: Path, capsys) -> None:
    """Unknown inputs fail before installing providers or writing an artifact."""
    from praviar_pipeline.pipeline.runtime.cli_args import RunCliArgs
    from praviar_pipeline.pipeline.runtime.cli_runner import _run_dry_run

    called = False

    async def _pipeline(*args, **kwargs):
        nonlocal called
        called = True
        return _baseline_report()

    rc = _run_dry_run(
        cli_args=RunCliArgs(
            user_input="aspirin",
            dry_run=True,
            output_dir=str(tmp_path),
        ),
        run_pipeline_fn=_pipeline,
        emit_json_report_fn=lambda *a, **kw: None,
    )

    assert rc == 2
    assert called is False
    assert not (tmp_path / "dryrun-report.json").exists()
    assert "canonical fictional showcase" in capsys.readouterr().out


def test_run_dry_run_rejects_resume_before_pipeline_or_artifact(
    tmp_path: Path,
    capsys,
) -> None:
    """A retained production checkpoint cannot enter the canonical showcase lane."""
    from praviar_pipeline.pipeline.runtime.cli_args import RunCliArgs
    from praviar_pipeline.pipeline.runtime.cli_runner import _run_dry_run

    called = False

    async def _pipeline(*args, **kwargs):
        nonlocal called
        called = True
        return _baseline_report()

    output_dir = tmp_path / "new-output"
    rc = _run_dry_run(
        cli_args=RunCliArgs(
            user_input=SHOWCASE_DRY_RUN_INPUT,
            dry_run=True,
            output_dir=str(output_dir),
            resume_from=str(tmp_path / "production-checkpoint"),
        ),
        run_pipeline_fn=_pipeline,
        emit_json_report_fn=lambda *a, **kw: None,
    )

    assert rc == 2
    assert called is False
    assert not output_dir.exists()
    assert "cannot resume checkpoints" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# 8. Provider robustness — unknown sources fail closed
# ---------------------------------------------------------------------------


def test_provider_fails_closed_for_unknown_source() -> None:
    """A newly introduced external source needs an explicit canonical adapter."""
    with pytest.raises(DryRunError, match="no canonical provider"):
        dry_run_provider(
            source="some_brand_new_client",
            method="GET",
            url="/foo",
            body=None,
        )


@pytest.mark.parametrize(
    ("source", "url", "body"),
    [
        ("pubchem", "/new/uncanned/endpoint", None),
        ("bigquery", "new_uncanned_query", None),
        ("pubchem_sdq", "https://pubchem.invalid/sdq", "{}"),
    ],
)
def test_provider_fails_closed_for_unknown_known_source_request(
    source: str,
    url: str,
    body: str | None,
) -> None:
    """A new endpoint/query cannot inherit a vaguely compatible fallback shape."""
    with pytest.raises(DryRunError, match=r"canonical|showcase CID"):
        dry_run_provider(source=source, method="GET", url=url, body=body)


def test_showcase_input_validation_is_exact() -> None:
    validate_showcase_input(SHOWCASE_DRY_RUN_INPUT)
    with pytest.raises(DryRunError, match="canonical fictional input"):
        validate_showcase_input("Example Molecule Alpha")


def test_showcase_receipt_rejects_incomplete_or_provider_backed_run() -> None:
    report = _baseline_report()
    report["audit_trail"]["timing_data"].pop()
    with pytest.raises(DryRunAssertionError, match="step8_report"):
        attach_showcase_run_receipt(report, blocked_external_calls=0)

    with pytest.raises(DryRunAssertionError, match="uncanned HTTP"):
        attach_showcase_run_receipt(_baseline_report(), blocked_external_calls=1)

    duplicated = _baseline_report()
    duplicated["audit_trail"]["timing_data"].append({"step_name": "step8_report"})
    with pytest.raises(DryRunAssertionError, match="exactly once"):
        attach_showcase_run_receipt(duplicated, blocked_external_calls=0)

    out_of_order = _baseline_report()
    timings = out_of_order["audit_trail"]["timing_data"]
    timings[-2], timings[-1] = timings[-1], timings[-2]
    with pytest.raises(DryRunAssertionError, match="execution order"):
        attach_showcase_run_receipt(out_of_order, blocked_external_calls=0)


def test_showcase_receipt_rejects_failed_source_when_called_directly() -> None:
    """The receipt API remains fail-closed without a separate CLI validation call."""
    report = _baseline_report()
    report["source_health"]["entries"].append(
        {"source": "new_source", "status": "failed", "error_message": "boom"}
    )

    with pytest.raises(DryRunAssertionError, match="disallowed status"):
        attach_showcase_run_receipt(report, blocked_external_calls=0)


def test_showcase_receipt_requires_present_zero_nested_accounting() -> None:
    missing_total = _baseline_report()
    missing_total.pop("total_input_tokens")
    with pytest.raises(DryRunAssertionError, match="total_input_tokens"):
        attach_showcase_run_receipt(missing_total, blocked_external_calls=0)

    nested_tokens = _baseline_report()
    nested_tokens["step_token_usage"] = [{"input_tokens": 1, "output_tokens": 0}]
    with pytest.raises(DryRunAssertionError, match="step_token_usage"):
        attach_showcase_run_receipt(nested_tokens, blocked_external_calls=0)

    nested_cost = _baseline_report()
    nested_cost["manifest"]["cost_breakdown"] = {"analysis_cost_usd": 0.01}
    with pytest.raises(DryRunAssertionError, match="analysis_cost_usd"):
        attach_showcase_run_receipt(nested_cost, blocked_external_calls=0)


def test_substantive_digest_covers_source_health_and_new_business_fields() -> None:
    """Coverage regressions cannot hide behind an unchanged showcase golden."""
    baseline = _baseline_report()
    expected = showcase_substantive_digest(baseline)

    baseline["source_health"]["entries"].append(
        {"source": "new_source", "status": "failed", "error_message": "unavailable"}
    )
    assert showcase_substantive_digest(baseline) != expected

    baseline = _baseline_report()
    baseline["new_business_decision"] = {"export_ready": False}
    assert showcase_substantive_digest(baseline) != expected


@pytest.mark.asyncio
async def test_harness_blocks_and_counts_uncanned_http() -> None:
    """Direct transports cannot silently escape the zero-provider profile."""
    import httpx

    async with httpx.AsyncClient() as client:
        with install_dry_run_harness() as cache:
            with pytest.raises(DryRunError, match="blocked an uncanned"):
                await client.get("https://example.invalid/live")
            assert cache.showcase_blocked_external_calls == 1


def test_harness_blocks_sync_http_and_restores_transport() -> None:
    """A synchronous client cannot bypass the receipt's provider-call count."""
    import httpx

    original_send = httpx.Client.send
    with install_dry_run_harness() as cache:
        with httpx.Client() as client:
            with pytest.raises(DryRunError, match="blocked an uncanned"):
                client.get("https://example.invalid/live")
        assert cache.showcase_blocked_external_calls == 1

    assert httpx.Client.send is original_send


def test_harness_blocks_raw_socket_and_restores_transport() -> None:
    """The final socket boundary covers urllib, requests, SDKs, and raw TCP."""
    import socket

    original_create_connection = socket.create_connection
    with install_dry_run_harness() as cache:
        with pytest.raises(DryRunError, match="external network request"):
            socket.create_connection(("127.0.0.1", 9), timeout=0.01)
        assert cache.showcase_blocked_external_calls == 1

    assert socket.create_connection is original_create_connection


def test_harness_blocks_internet_socket_writes_and_preserves_unix_socketpairs() -> None:
    """Pre-created TCP/UDP sockets cannot write around the connection guard."""
    import socket

    # Start with an already-connected datagram descriptor. Relabelling this
    # local-only socketpair endpoint as AF_INET exercises the internet-family
    # branch without requiring network sandbox permission; an unguarded send
    # would still succeed against the local peer.
    connected_datagram, local_peer = socket.socketpair(type=socket.SOCK_DGRAM)
    internet_socket = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
        fileno=connected_datagram.detach(),
    )
    internet_socket.send(b"preflight")
    assert local_peer.recv(9) == b"preflight"
    local_left, local_right = socket.socketpair()
    original_send = socket.socket.send
    original_sendall = socket.socket.sendall
    original_sendto = socket.socket.sendto
    try:
        with install_dry_run_harness() as cache:
            with pytest.raises(DryRunError, match="external network request"):
                internet_socket.send(b"escape")
            assert cache.showcase_blocked_external_calls == 1

            with pytest.raises(DryRunError, match="external network request"):
                internet_socket.sendall(b"escape")
            assert cache.showcase_blocked_external_calls == 2

            with pytest.raises(DryRunError, match="external network request"):
                internet_socket.sendto(b"escape", ("127.0.0.1", 9))
            assert cache.showcase_blocked_external_calls == 3

            with pytest.raises(DryRunError, match="external network request"):
                socket.gethostbyname("example.invalid")
            assert cache.showcase_blocked_external_calls == 4

            # asyncio relies on AF_UNIX socketpairs for wakeups; those remain
            # available because they are process-local rather than outbound.
            local_left.sendall(b"ok")
            assert local_right.recv(2) == b"ok"
    finally:
        internet_socket.close()
        connected_datagram.close()
        local_peer.close()
        local_left.close()
        local_right.close()

    assert socket.socket.send is original_send
    assert socket.socket.sendall is original_sendall
    assert socket.socket.sendto is original_sendto


def test_harness_blocks_handshake_on_preconnected_tls_socket() -> None:
    """Native TLS handshakes cannot write around the base-socket guard."""
    import socket
    import ssl

    connected_stream, local_peer = socket.socketpair()
    internet_stream = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
        fileno=connected_stream.detach(),
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    tls_socket = context.wrap_socket(
        internet_stream,
        server_hostname="showcase.invalid",
        do_handshake_on_connect=False,
    )
    original_handshake = ssl.SSLSocket.do_handshake
    try:
        with install_dry_run_harness() as cache:
            native_tls_operations = (
                tls_socket.do_handshake,
                lambda: tls_socket.read(1),
                lambda: tls_socket.recv(1),
                tls_socket.unwrap,
            )
            for expected_count, operation in enumerate(native_tls_operations, start=1):
                with pytest.raises(DryRunError, match="external network request"):
                    operation()
                assert cache.showcase_blocked_external_calls == expected_count
    finally:
        tls_socket.close()
        connected_stream.close()
        local_peer.close()

    assert ssl.SSLSocket.do_handshake is original_handshake


def test_full_cli_is_repeatable_against_golden_digest(tmp_path: Path) -> None:
    """Two real eight-stage runs have identical substantive output."""
    digests = []
    for index in range(2):
        output_dir = tmp_path / f"run-{index}"
        hostile_env = (
            {}
            if index == 0
            else {
                "MATTER_TYPE": "biologic",
                "TARGET_JURISDICTIONS": '["EP"]',
                "TRUST_MODE": "counsel",
                "DRAWING_ANALYSIS_ENABLED": "true",
                "DETERMINISTIC_SEED": "987654",
            }
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "praviar_pipeline.cli",
                "run",
                SHOWCASE_DRY_RUN_INPUT,
                "--dry-run",
                "--format",
                "markdown",
                "--output-dir",
                str(output_dir),
            ],
            cwd=tmp_path,
            env={**os.environ, **hostile_env, "LOG_LEVEL": "CRITICAL"},
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        report = json.loads((output_dir / "dryrun-report.json").read_text())
        assert (output_dir / ".checkpoints").is_dir()
        assert report["showcase_run"]["external_provider_calls"] == 0
        assert report["showcase_run"]["completed_stages"] == [
            "step1_resolve",
            "step2_search",
            "step3_triage",
            "step4_analyze",
            "step5_doe",
            "step6_invalid",
            "step7_verify",
            "step8_report",
        ]
        assert report["total_input_tokens"] == 0
        assert report["total_output_tokens"] == 0
        assert report["estimated_cost_usd"] == 0.0
        digest = showcase_substantive_digest(report)
        assert report["showcase_run"]["substantive_sha256"] == digest
        digests.append(digest)

    assert digests == [
        "ec45ce42a085ec40f8b5d2eb4195118818aabca8e3386039c242a865f7d04556",
        "ec45ce42a085ec40f8b5d2eb4195118818aabca8e3386039c242a865f7d04556",
    ]


def test_llm_replay_zero_usage_preserves_model_key() -> None:
    """Replay/dry-run cache hits must still satisfy callers expecting usage['model']."""
    from praviar_pipeline.clients.claude_response_cache import _zero_usage

    usage = _zero_usage({"model": "dry-run", "input_tokens": 12, "output_tokens": 3})

    assert usage["model"] == "dry-run"
    assert usage["input_tokens"] == 0
    assert usage["output_tokens"] == 0
