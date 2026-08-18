from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.errors import APIError
from api.services.chat_budget import (
    _RESERVE_SCRIPT,
    ChatBudgetReservation,
    actual_chat_cost_microusd,
    estimate_chat_reservation_microusd,
    reconcile_chat_budget,
    reserve_chat_budget,
)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        chat_max_tokens=1000,
        chat_org_monthly_budget_usd=25.0,
        chat_user_daily_budget_usd=5.0,
        chat_input_cost_per_million_usd=3.0,
        chat_cache_creation_input_cost_per_million_usd=6.0,
        chat_cache_read_input_cost_per_million_usd=0.3,
        chat_output_cost_per_million_usd=15.0,
    )


def _prepared() -> SimpleNamespace:
    return SimpleNamespace(
        system_prompt="Use only cited report evidence.",
        messages=[{"role": "user", "content": "Summarize the blockers."}],
    )


def _scope() -> SimpleNamespace:
    return SimpleNamespace(org_id=uuid.uuid4(), user_id=uuid.uuid4())


def test_chat_budget_estimate_reserves_input_and_maximum_output() -> None:
    amount = estimate_chat_reservation_microusd(_prepared(), _settings())

    assert amount > 15_000


def test_actual_chat_cost_rejects_untrusted_usage_values() -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        actual_chat_cost_microusd(
            {
                "input_tokens": "100",
                "output_tokens": 5,
            },
            _settings(),
        )


def test_actual_chat_cost_handles_valid_zero_usage_conservatively() -> None:
    assert actual_chat_cost_microusd({}, _settings()) == 1


def test_actual_chat_cost_uses_distinct_prompt_cache_rates() -> None:
    assert (
        actual_chat_cost_microusd(
            {
                "input_tokens": 100,
                "cache_creation_input_tokens": 200,
                "cache_read_input_tokens": 300,
                "output_tokens": 10,
            },
            _settings(),
        )
        == 1740
    )


@pytest.mark.asyncio
async def test_chat_budget_reserves_org_and_user_limits_atomically() -> None:
    redis = AsyncMock()
    redis.eval.return_value = [1, 1000, 1000]
    scope = _scope()

    reservation = await reserve_chat_budget(
        prepared=_prepared(),
        scope=scope,
        settings=_settings(),
        now=datetime(2026, 7, 31, 12, 0, tzinfo=UTC),
        redis_factory=AsyncMock(return_value=redis),
    )

    assert reservation.amount_microusd > 0
    assert reservation.org_key == f"chat-budget:v1:org:{scope.org_id}:2026-07"
    assert reservation.user_key == f"chat-budget:v1:user:{scope.org_id}:{scope.user_id}:2026-07-31"
    assert reservation.reservation_key.startswith(
        f"chat-budget:v1:reservation:{scope.org_id}:{scope.user_id}:"
    )
    redis.eval.assert_awaited_once()
    assert redis.eval.await_args.args[1] == 3


@pytest.mark.asyncio
async def test_chat_budget_rejects_exhausted_limit_before_provider_call() -> None:
    redis = AsyncMock()
    redis.eval.return_value = [0, 25_000_000, 1_000_000]

    with pytest.raises(APIError) as exc_info:
        await reserve_chat_budget(
            prepared=_prepared(),
            scope=_scope(),
            settings=_settings(),
            redis_factory=AsyncMock(return_value=redis),
        )

    assert exc_info.value.status == 429
    assert exc_info.value.retry_after_seconds is not None


@pytest.mark.asyncio
async def test_chat_budget_fails_closed_when_ledger_is_unavailable() -> None:
    with pytest.raises(APIError) as exc_info:
        await reserve_chat_budget(
            prepared=_prepared(),
            scope=_scope(),
            settings=_settings(),
            redis_factory=AsyncMock(side_effect=RuntimeError("redis unavailable")),
        )

    assert exc_info.value.status == 503
    assert "refusing a paid provider call" in exc_info.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize("ledger_result", [[-2, 0, 0], [-1, 0, 0], [], "invalid"])
async def test_chat_budget_integrity_failures_are_not_reported_as_spend_exhaustion(
    ledger_result: object,
) -> None:
    redis = AsyncMock()
    redis.eval.return_value = ledger_result

    with pytest.raises(APIError) as exc_info:
        await reserve_chat_budget(
            prepared=_prepared(),
            scope=_scope(),
            settings=_settings(),
            redis_factory=AsyncMock(return_value=redis),
        )

    assert exc_info.value.status == 503
    assert exc_info.value.retry_after_seconds is None
    assert "durable reservation" in exc_info.value.detail


def test_chat_budget_script_marks_first_and_compensates_partial_writes() -> None:
    assert _RESERVE_SCRIPT.index("redis.pcall('SET', KEYS[3]") < _RESERVE_SCRIPT.index(
        "redis.pcall('INCRBY', KEYS[1]"
    )
    assert "redis.pcall('DECRBY', KEYS[1], amount)" in _RESERVE_SCRIPT
    assert "redis.pcall('DECRBY', KEYS[2], amount)" in _RESERVE_SCRIPT
    assert "return {-2, org_used, user_used}" in _RESERVE_SCRIPT


@pytest.mark.asyncio
async def test_chat_budget_refunds_only_unused_reservation() -> None:
    redis = AsyncMock()
    redis.eval.return_value = [1, 1000, 1000]
    redis_factory = AsyncMock(return_value=redis)
    reservation = await reserve_chat_budget(
        prepared=_prepared(),
        scope=_scope(),
        settings=_settings(),
        redis_factory=redis_factory,
    )
    redis.eval.reset_mock()
    redis.eval.return_value = 1

    await reconcile_chat_budget(
        reservation=reservation,
        usage={
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
        settings=_settings(),
        redis_factory=redis_factory,
    )

    redis.eval.assert_awaited_once()
    refund = int(redis.eval.await_args.args[-1])
    assert 0 < refund < reservation.amount_microusd


@pytest.mark.asyncio
async def test_chat_budget_reconciliation_is_one_shot_and_replay_safe() -> None:
    redis = AsyncMock()
    redis.eval.side_effect = ([1, 1000, 1000], 1, 0)
    redis_factory = AsyncMock(return_value=redis)
    reservation = await reserve_chat_budget(
        prepared=_prepared(),
        scope=_scope(),
        settings=_settings(),
        redis_factory=redis_factory,
    )
    usage = {
        "input_tokens": 10,
        "output_tokens": 5,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }

    await reconcile_chat_budget(
        reservation=reservation,
        usage=usage,
        settings=_settings(),
        redis_factory=redis_factory,
    )
    await reconcile_chat_budget(
        reservation=reservation,
        usage=usage,
        settings=_settings(),
        redis_factory=redis_factory,
    )

    first_reconcile = redis.eval.await_args_list[1].args
    replay = redis.eval.await_args_list[2].args
    assert first_reconcile == replay
    assert first_reconcile[1] == 3
    assert reservation.reservation_key in first_reconcile


@pytest.mark.asyncio
async def test_chat_budget_reconciliation_rejects_reservation_amount_mismatch() -> None:
    redis = AsyncMock()
    redis.eval.return_value = -1
    reservation = ChatBudgetReservation(
        amount_microusd=10_000,
        org_key="org",
        user_key="user",
        reservation_key="reservation",
    )

    with pytest.raises(RuntimeError, match="did not match"):
        await reconcile_chat_budget(
            reservation=reservation,
            usage={"input_tokens": 1},
            settings=_settings(),
            redis_factory=AsyncMock(return_value=redis),
        )
