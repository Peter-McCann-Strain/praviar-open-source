"""Tests for per-run LLM cost tracking."""

from __future__ import annotations

import asyncio
import json
from typing import ClassVar

import pytest

from praviar_pipeline import cost_tracker as cost_tracker_module
from praviar_pipeline.cost_tracker import (
    CostTracker,
    get_current_tracker,
    set_current_tracker,
)
from praviar_pipeline.errors import PaidCallBudgetExceededError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Every test starts and ends with no installed tracker."""
    set_current_tracker(None)
    yield
    set_current_tracker(None)


# ---------------------------------------------------------------------------
# Pricing + record()
# ---------------------------------------------------------------------------


def test_record_sonnet_prices_match_public_table() -> None:
    tracker = CostTracker()
    tracker.record(
        role="analysis",
        model="claude-sonnet-4-6-20250929",
        usage={
            "input_tokens": 1_000_000,
            "output_tokens": 1_000_000,
            "cache_read_input_tokens": 1_000_000,
            "cache_creation_input_tokens": 1_000_000,
        },
    )
    snapshot = tracker.snapshot()
    row = snapshot["analysis"]
    # 3 + 15 + 0.30 + 3.75 = 22.05
    assert row["estimated_usd"] == pytest.approx(22.05, abs=1e-6)
    assert row["input_tokens"] == 1_000_000
    assert row["output_tokens"] == 1_000_000
    assert row["cache_read_tokens"] == 1_000_000
    assert row["cache_creation_tokens"] == 1_000_000
    assert row["call_count"] == 1
    assert row["models"] == {"claude-sonnet-4-6-20250929": 1}


def test_record_haiku_prices() -> None:
    tracker = CostTracker()
    tracker.record(
        role="triage",
        model="claude-haiku-4-5",
        usage={"input_tokens": 2_000_000, "output_tokens": 500_000},
    )
    # 2 * 1.0 + 0.5 * 5.0 = 4.5
    assert tracker.total_usd() == pytest.approx(4.5, abs=1e-6)


def test_record_opus_prices() -> None:
    tracker = CostTracker()
    tracker.record(
        role="deep",
        model="claude-opus-4-6",
        usage={"input_tokens": 100_000, "output_tokens": 100_000},
    )
    # Opus 4.6: $5/M input, $25/M output — verified 2026-04-15 against
    # Anthropic's pricing page. 0.1 * 5 + 0.1 * 25 = 3.0
    assert tracker.total_usd() == pytest.approx(3.0, abs=1e-6)


def test_record_accumulates_per_role() -> None:
    tracker = CostTracker()
    for _ in range(3):
        tracker.record(
            role="analysis",
            model="claude-sonnet-4-6",
            usage={"input_tokens": 1000, "output_tokens": 500},
        )
    row = tracker.snapshot()["analysis"]
    assert row["call_count"] == 3
    assert row["input_tokens"] == 3000
    assert row["output_tokens"] == 1500
    # 3 * (1000 * 3 + 500 * 15) / 1M = 3 * 0.0105 = 0.0315
    assert row["estimated_usd"] == pytest.approx(0.0315, abs=1e-6)


def test_record_unknown_model_logs_warning_and_records_zero(caplog) -> None:
    tracker = CostTracker()
    tracker.record(
        role="analysis",
        model="some-unreleased-model-id",
        usage={"input_tokens": 1_000_000, "output_tokens": 1_000_000},
    )
    # Does not crash; cost is zero; tokens still accumulate.
    row = tracker.snapshot()["analysis"]
    assert row["estimated_usd"] == 0.0
    assert row["input_tokens"] == 1_000_000
    assert row["output_tokens"] == 1_000_000
    # Warn only once for the same model on repeat calls.
    tracker.record(
        role="analysis",
        model="some-unreleased-model-id",
        usage={"input_tokens": 10, "output_tokens": 10},
    )
    assert len(tracker._unknown_warned) == 1


def test_opus_4_6_dated_snapshot_matches_prefix() -> None:
    """A dated Opus 4.6 snapshot (``claude-opus-4-6-20260101``) prices at the
    Opus 4.6 rate — prefix match finds the pricing row regardless of the
    date suffix Anthropic ships on the model ID."""
    tracker = CostTracker()
    tracker.record(
        role="deep",
        model="claude-opus-4-6-20260101",
        usage={"input_tokens": 1_000_000, "output_tokens": 1_000_000},
    )
    # 1M * 5 + 1M * 25 = 30 USD at Opus 4.6 rates.
    assert tracker.total_usd() == pytest.approx(30.0, abs=1e-6)


def test_opus_4_5_does_not_match_opus_4_6_prefix() -> None:
    """Model ID ``claude-opus-4-5-something`` must NOT match the
    ``claude-opus-4-6`` pricing row — different generations have different
    prices and a mismatched prefix would silently mis-bill. The call is
    recorded at zero cost with an ``unknown_model_pricing`` warning."""
    tracker = CostTracker()
    tracker.record(
        role="deep",
        model="claude-opus-4-5-something",
        usage={"input_tokens": 1_000_000, "output_tokens": 1_000_000},
    )
    row = tracker.snapshot()["deep"]
    # Tokens still accumulate even though we can't price them.
    assert row["input_tokens"] == 1_000_000
    assert row["output_tokens"] == 1_000_000
    # Cost is zero because no pricing row matched.
    assert row["estimated_usd"] == 0.0
    # And the tracker remembered the unseen model (warn-once behaviour).
    assert "claude-opus-4-5-something" in tracker._unknown_warned


def test_longest_prefix_wins_for_opus_4_6_variants() -> None:
    """Longest-prefix-wins guarantee: ``claude-opus-4-6-v2`` binds to the
    ``claude-opus-4-6`` row specifically. If we ever add a shorter
    ``claude-opus`` catch-all, this test pins the ordering so that
    version-specific prefixes still take precedence."""
    tracker = CostTracker()
    tracker.record(
        role="deep",
        model="claude-opus-4-6-v2",
        usage={"input_tokens": 100_000, "output_tokens": 0},
    )
    # Must price at Opus 4.6's $5/M input — 100k * $5 / 1M = $0.50.
    assert tracker.total_usd() == pytest.approx(0.5, abs=1e-6)


def test_record_handles_missing_cache_fields() -> None:
    tracker = CostTracker()
    tracker.record(
        role="triage",
        model="claude-haiku-4-5",
        usage={"input_tokens": 100, "output_tokens": 50},
    )
    row = tracker.snapshot()["triage"]
    assert row["cache_read_tokens"] == 0
    assert row["cache_creation_tokens"] == 0


def test_record_handles_none_cache_fields() -> None:
    tracker = CostTracker()
    tracker.record(
        role="triage",
        model="claude-haiku-4-5",
        usage={
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_input_tokens": None,
            "cache_creation_input_tokens": None,
        },
    )
    row = tracker.snapshot()["triage"]
    assert row["cache_read_tokens"] == 0
    assert row["cache_creation_tokens"] == 0


def test_hard_budget_reserves_concurrent_worst_case_cost_before_calls() -> None:
    tracker = CostTracker(hard_budget_usd=0.20)

    first = tracker.reserve_paid_call(
        model="claude-sonnet-4-6",
        max_output_tokens=10_000,
        estimated_input_tokens=1_000,
    )

    assert first is not None
    with pytest.raises(PaidCallBudgetExceededError, match="before dispatch"):
        tracker.reserve_paid_call(
            model="claude-sonnet-4-6",
            max_output_tokens=10_000,
            estimated_input_tokens=1_000,
        )


def test_hard_budget_settles_actual_usage_and_releases_unused_hold() -> None:
    tracker = CostTracker(hard_budget_usd=0.20)
    first = tracker.reserve_paid_call(
        model="claude-sonnet-4-6",
        max_output_tokens=10_000,
        estimated_input_tokens=1_000,
    )
    tracker.settle_paid_call(
        first,
        model="claude-sonnet-4-6",
        usage={"input_tokens": 100, "output_tokens": 100},
    )

    second = tracker.reserve_paid_call(
        model="claude-sonnet-4-6",
        max_output_tokens=10_000,
        estimated_input_tokens=1_000,
    )

    assert second is not None


def test_hard_budget_rejects_unknown_pricing_before_provider_call() -> None:
    tracker = CostTracker(hard_budget_usd=15.0)

    with pytest.raises(PaidCallBudgetExceededError, match="no verified pricing"):
        tracker.reserve_paid_call(
            model="claude-unpriced-future-model",
            max_output_tokens=1_000,
            estimated_input_tokens=1_000,
        )


# ---------------------------------------------------------------------------
# snapshot() / total_usd() / reset()
# ---------------------------------------------------------------------------


def test_snapshot_aggregates_per_role() -> None:
    tracker = CostTracker()
    tracker.record(
        role="triage",
        model="claude-haiku-4-5",
        usage={"input_tokens": 100, "output_tokens": 100},
    )
    tracker.record(
        role="analysis",
        model="claude-sonnet-4-6",
        usage={"input_tokens": 100, "output_tokens": 100},
    )
    tracker.record(
        role="deep",
        model="claude-opus-4-6",
        usage={"input_tokens": 100, "output_tokens": 100},
    )
    snap = tracker.snapshot()
    assert set(snap.keys()) == {"triage", "analysis", "deep"}
    assert all(v["call_count"] == 1 for v in snap.values())


def test_total_usd_sums_across_roles() -> None:
    tracker = CostTracker()
    tracker.record(
        role="triage",
        model="claude-haiku-4-5",
        usage={"input_tokens": 1_000_000, "output_tokens": 0},
    )
    tracker.record(
        role="analysis",
        model="claude-sonnet-4-6",
        usage={"input_tokens": 1_000_000, "output_tokens": 0},
    )
    # Haiku input 1.0 + Sonnet input 3.0 = 4.0
    assert tracker.total_usd() == pytest.approx(4.0, abs=1e-6)


def test_total_tokens_sums_across_roles() -> None:
    tracker = CostTracker()
    tracker.record(
        role="triage",
        model="claude-haiku-4-5",
        usage={
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_input_tokens": 10,
            "cache_creation_input_tokens": 5,
        },
    )
    tracker.record(
        role="analysis",
        model="claude-sonnet-4-6",
        usage={"input_tokens": 200, "output_tokens": 100},
    )
    totals = tracker.total_tokens()
    assert totals == {
        "input_tokens": 300,
        "output_tokens": 150,
        "cache_read_tokens": 10,
        "cache_creation_tokens": 5,
    }


def test_reset_clears_state() -> None:
    tracker = CostTracker()
    tracker.record(
        role="triage",
        model="claude-haiku-4-5",
        usage={"input_tokens": 100, "output_tokens": 50},
    )
    tracker.record(
        role="analysis",
        model="unknown-model-x",
        usage={"input_tokens": 1, "output_tokens": 1},
    )
    assert tracker.snapshot()
    tracker.reset()
    assert tracker.snapshot() == {}
    assert tracker.total_usd() == 0.0
    # Unknown-model warning tracking is also reset so it re-warns.
    assert tracker._unknown_warned == set()


# ---------------------------------------------------------------------------
# Thread / async safety
# ---------------------------------------------------------------------------


def test_concurrent_record_produces_correct_totals() -> None:
    tracker = CostTracker()
    n_calls = 100

    async def _do_record(i: int) -> None:
        tracker.record(
            role="analysis" if i % 2 == 0 else "triage",
            model="claude-sonnet-4-6" if i % 2 == 0 else "claude-haiku-4-5",
            usage={"input_tokens": 10, "output_tokens": 5},
        )

    async def _main() -> None:
        await asyncio.gather(*[_do_record(i) for i in range(n_calls)])

    asyncio.run(_main())

    snap = tracker.snapshot()
    # 50 analysis calls, 50 triage calls.
    assert snap["analysis"]["call_count"] == 50
    assert snap["triage"]["call_count"] == 50
    assert snap["analysis"]["input_tokens"] == 500
    assert snap["triage"]["input_tokens"] == 500


# ---------------------------------------------------------------------------
# Singleton install / clear
# ---------------------------------------------------------------------------


def test_singleton_install_and_clear() -> None:
    assert get_current_tracker() is None
    tracker = CostTracker()
    set_current_tracker(tracker)
    assert get_current_tracker() is tracker
    set_current_tracker(None)
    assert get_current_tracker() is None


def test_singleton_is_module_level() -> None:
    """The module exposes the same lock object — one process-wide singleton."""
    assert cost_tracker_module._CURRENT_TRACKER_LOCK is not None


# ---------------------------------------------------------------------------
# Manifest integration
# ---------------------------------------------------------------------------


def test_manifest_serializes_cost_breakdown() -> None:
    """A manifest with populated cost_breakdown round-trips through JSON."""
    from types import SimpleNamespace

    from praviar_pipeline.manifest import ReportManifest, build_manifest

    tracker = CostTracker()
    tracker.record(
        role="analysis",
        model="claude-sonnet-4-6",
        usage={
            "input_tokens": 1234,
            "output_tokens": 567,
            "cache_read_input_tokens": 100,
            "cache_creation_input_tokens": 50,
        },
    )
    tracker.record(
        role="triage",
        model="claude-haiku-4-5",
        usage={"input_tokens": 999, "output_tokens": 100},
    )
    set_current_tracker(tracker)

    fake_settings = SimpleNamespace(
        claude_triage_model="claude-haiku-4-5",
        claude_analysis_model="claude-sonnet-4-6",
        claude_deep_model="claude-opus-4-6",
    )
    manifest = build_manifest(
        compound_query="aspirin",
        source_health=None,
        settings=fake_settings,
    )
    assert "analysis" in manifest.cost_breakdown
    assert "triage" in manifest.cost_breakdown
    assert manifest.cost_breakdown["analysis"]["input_tokens"] == 1234
    assert manifest.cost_breakdown["analysis"]["call_count"] == 1
    assert manifest.total_cost_usd > 0
    # Round-trip.
    blob = manifest.model_dump_json()
    reparsed = ReportManifest.model_validate(json.loads(blob))
    assert reparsed == manifest


def test_manifest_without_tracker_has_empty_cost_breakdown() -> None:
    """build_manifest works when no tracker is installed — backward compat."""
    from types import SimpleNamespace

    from praviar_pipeline.manifest import build_manifest

    fake_settings = SimpleNamespace(
        claude_triage_model="h",
        claude_analysis_model="s",
        claude_deep_model="o",
    )
    manifest = build_manifest(
        compound_query="x",
        source_health=None,
        settings=fake_settings,
    )
    assert manifest.cost_breakdown == {}
    assert manifest.total_cost_usd == 0.0


def test_manifest_default_cost_breakdown_for_legacy_payloads() -> None:
    """A legacy manifest JSON without cost fields still deserialises."""
    from praviar_pipeline.manifest import ReportManifest

    # Hand-build a v1 payload that predates cost_breakdown.
    payload = {
        "pipeline_version": "unknown",
        "generated_at": "2026-04-15T00:00:00+00:00",
        "compound_query": "aspirin",
        "prompt_hashes": {},
        "model_versions": {},
        "sampling": {},
        "source_snapshots": {},
        "tool_trace_digest": "0" * 64,
    }
    manifest = ReportManifest.model_validate(payload)
    assert manifest.cost_breakdown == {}
    assert manifest.total_cost_usd == 0.0


# ---------------------------------------------------------------------------
# Tool-loop -> tracker plumbing
#
# Closes the gap where ``agents/base_runtime.py`` calls ``_tool_use_loop``
# directly and would otherwise leave its tokens unattributed in the manifest.
# ---------------------------------------------------------------------------


def _fake_text_response(*, input_tokens: int, output_tokens: int):
    """Build a minimal Anthropic-shaped response that ends the tool loop."""
    from types import SimpleNamespace

    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text="done")],
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
        stop_reason="end_turn",
    )


def _fake_tool_use_response(*, input_tokens: int, output_tokens: int, tool_id: str):
    """Build an Anthropic-shaped response that requests one tool call."""
    from types import SimpleNamespace

    tool_block = SimpleNamespace(
        type="tool_use",
        id=tool_id,
        name="noop",
        input={"x": 1},
    )
    return SimpleNamespace(
        content=[tool_block],
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
        stop_reason="tool_use",
    )


def _build_fake_client(responses):
    """Build a fake Anthropic client whose stream yields ``responses`` in order."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    queue = list(responses)

    class FakeStream:
        def __init__(self, response):
            self._response = response

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get_final_message(self):
            return self._response

    def _stream(**_kwargs):
        return FakeStream(queue.pop(0))

    return SimpleNamespace(messages=SimpleNamespace(stream=MagicMock(side_effect=_stream)))


class _NoopToolkit:
    tool_definitions: ClassVar[list[dict[str, object]]] = [
        {"name": "noop", "description": "noop", "input_schema": {}}
    ]

    async def execute(self, tool_name: str, tool_input: dict) -> str:
        return "ok"


@pytest.mark.asyncio
async def test_tool_use_loop_records_cost_under_role_when_set() -> None:
    """Happy path: a tool-loop run with ``role="agent"`` accumulates tokens
    on the tracker under ``"agent"`` (closes the
    ``agents/base_runtime.py:200`` direct-call gap)."""
    from praviar_pipeline.clients.claude_runtime_tool_loop import tool_use_loop_impl

    tracker = CostTracker()
    set_current_tracker(tracker)

    client = _build_fake_client([_fake_text_response(input_tokens=120, output_tokens=80)])

    response, total_in, total_out, _ = await tool_use_loop_impl(
        client=client,
        max_rounds=3,
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        toolkit=_NoopToolkit(),
        logger=cost_tracker_module.logger,
        role="agent",
    )

    assert total_in == 120
    assert total_out == 80
    snap = tracker.snapshot()
    assert "agent" in snap
    assert snap["agent"]["input_tokens"] == 120
    assert snap["agent"]["output_tokens"] == 80
    assert snap["agent"]["call_count"] == 1
    # Sonnet 4-6 input $3/M + output $15/M -> 120*3 + 80*15 = 360 + 1200 = 1560 micro-USD.
    assert snap["agent"]["estimated_usd"] == pytest.approx(0.00156, abs=1e-9)
    assert response is not None


@pytest.mark.asyncio
async def test_tool_use_loop_records_cost_under_supplied_role() -> None:
    """Role propagation: ``role="critic"`` lands under ``"critic"``, not ``"agent"``."""
    from praviar_pipeline.clients.claude_runtime_tool_loop import tool_use_loop_impl

    tracker = CostTracker()
    set_current_tracker(tracker)

    client = _build_fake_client([_fake_text_response(input_tokens=10, output_tokens=20)])

    await tool_use_loop_impl(
        client=client,
        max_rounds=1,
        model="claude-sonnet-4-6",
        max_tokens=128,
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        toolkit=_NoopToolkit(),
        logger=cost_tracker_module.logger,
        role="critic",
    )

    snap = tracker.snapshot()
    assert "critic" in snap
    assert "agent" not in snap
    assert snap["critic"]["input_tokens"] == 10
    assert snap["critic"]["output_tokens"] == 20


@pytest.mark.asyncio
async def test_tool_use_loop_runs_when_no_tracker_installed() -> None:
    """Defensive: with no tracker installed the loop still runs and returns."""
    from praviar_pipeline.clients.claude_runtime_tool_loop import tool_use_loop_impl

    assert get_current_tracker() is None  # baseline

    client = _build_fake_client([_fake_text_response(input_tokens=5, output_tokens=7)])

    response, total_in, total_out, _ = await tool_use_loop_impl(
        client=client,
        max_rounds=1,
        model="claude-sonnet-4-6",
        max_tokens=64,
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        toolkit=_NoopToolkit(),
        logger=cost_tracker_module.logger,
        role="agent",
    )
    assert response is not None
    assert (total_in, total_out) == (5, 7)


@pytest.mark.asyncio
async def test_tool_use_loop_records_summed_totals_across_multiple_rounds() -> None:
    """Multi-round: 3 rounds (2 tool-use + 1 final) record ONE summed entry,
    not one entry per round — matches how ``log_and_build_usage`` reports."""
    from praviar_pipeline.clients.claude_runtime_tool_loop import tool_use_loop_impl

    tracker = CostTracker()
    set_current_tracker(tracker)

    client = _build_fake_client(
        [
            _fake_tool_use_response(input_tokens=100, output_tokens=10, tool_id="t1"),
            _fake_tool_use_response(input_tokens=200, output_tokens=20, tool_id="t2"),
            _fake_text_response(input_tokens=300, output_tokens=30),
        ]
    )

    _resp, total_in, total_out, _ = await tool_use_loop_impl(
        client=client,
        max_rounds=5,
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        toolkit=_NoopToolkit(),
        logger=cost_tracker_module.logger,
        role="agent",
    )
    assert total_in == 600
    assert total_out == 60

    snap = tracker.snapshot()
    assert snap["agent"]["call_count"] == 1  # one record entry, not three
    assert snap["agent"]["input_tokens"] == 600
    assert snap["agent"]["output_tokens"] == 60


@pytest.mark.asyncio
async def test_tool_use_loop_skips_tracker_when_role_unset_avoiding_double_count() -> None:
    """No-double-count: when the outer caller (``complete_text_impl`` /
    ``complete_with_thinking_impl``) drives the loop, it leaves ``role`` unset
    and reports usage itself via ``log_and_build_usage``. The loop must NOT
    also record, otherwise tokens are billed twice. This test simulates that
    pattern: one explicit ``log_and_build_usage`` call after a ``role=None``
    tool loop with the same totals should yield exactly one record entry."""
    from praviar_pipeline.clients.claude_runtime_results import log_and_build_usage
    from praviar_pipeline.clients.claude_runtime_tool_loop import tool_use_loop_impl

    tracker = CostTracker()
    set_current_tracker(tracker)

    client = _build_fake_client([_fake_text_response(input_tokens=50, output_tokens=30)])

    response, total_in, total_out, _ = await tool_use_loop_impl(
        client=client,
        max_rounds=1,
        model="claude-sonnet-4-6",
        max_tokens=128,
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        toolkit=_NoopToolkit(),
        logger=cost_tracker_module.logger,
        # role left unset -> no internal record (mirrors the wrapper-driven path)
    )
    log_and_build_usage(
        purpose="complete_text",
        response=response,
        model="claude-sonnet-4-6",
        total_input=total_in,
        total_output=total_out,
        duration_s=0.0,
        log_fn=lambda **_: None,
        role="analysis",
    )

    snap = tracker.snapshot()
    # Exactly one entry, only from the outer log_and_build_usage call.
    assert "agent" not in snap
    assert snap["analysis"]["call_count"] == 1
    assert snap["analysis"]["input_tokens"] == 50
    assert snap["analysis"]["output_tokens"] == 30
