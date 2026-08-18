"""Atomic monetary reservations for paid report-chat calls."""

from __future__ import annotations

import json
import math
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol, cast

import structlog

from api.cache import get_chat_budget_redis
from api.errors import APIError

if TYPE_CHECKING:
    from api.services.chat_history import ChatConversationScope, PreparedChatRequest

logger = structlog.get_logger()
_MICRO_USD_PER_USD = 1_000_000

_RESERVE_SCRIPT = """
local function command_failed(result)
  return type(result) == 'table' and result.err ~= nil
end

local function compensate(org_incremented, user_incremented, amount)
  if user_incremented then redis.pcall('DECRBY', KEYS[2], amount) end
  if org_incremented then redis.pcall('DECRBY', KEYS[1], amount) end
  redis.pcall('DEL', KEYS[3])
end

local org_used = tonumber(redis.call('GET', KEYS[1]) or '0')
local user_used = tonumber(redis.call('GET', KEYS[2]) or '0')
local amount = tonumber(ARGV[1])
if redis.call('EXISTS', KEYS[3]) == 1 then
  return {-1, org_used, user_used}
end
if org_used + amount > tonumber(ARGV[2]) then
  return {0, org_used, user_used}
end
if user_used + amount > tonumber(ARGV[3]) then
  return {0, org_used, user_used}
end

-- Establish the durable reconciliation marker before charging either counter.
-- redis.pcall prevents a later Redis write error from aborting the script after
-- an earlier mutation; every failure path explicitly compensates prior writes.
local marker_result = redis.pcall('SET', KEYS[3], amount, 'EX', ARGV[6], 'NX')
if command_failed(marker_result) then
  return {-2, org_used, user_used}
end
if not marker_result then
  return {-1, org_used, user_used}
end

local org_new = redis.pcall('INCRBY', KEYS[1], amount)
if command_failed(org_new) then
  compensate(false, false, amount)
  return {-2, org_used, user_used}
end
local user_new = redis.pcall('INCRBY', KEYS[2], amount)
if command_failed(user_new) then
  compensate(true, false, amount)
  return {-2, org_used, user_used}
end

local org_ttl = redis.pcall('TTL', KEYS[1])
if command_failed(org_ttl) then
  compensate(true, true, amount)
  return {-2, org_used, user_used}
end
if org_ttl < 0 then
  local org_expire = redis.pcall('EXPIRE', KEYS[1], ARGV[4])
  if command_failed(org_expire) or org_expire ~= 1 then
    compensate(true, true, amount)
    return {-2, org_used, user_used}
  end
end
local user_ttl = redis.pcall('TTL', KEYS[2])
if command_failed(user_ttl) then
  compensate(true, true, amount)
  return {-2, org_used, user_used}
end
if user_ttl < 0 then
  local user_expire = redis.pcall('EXPIRE', KEYS[2], ARGV[5])
  if command_failed(user_expire) or user_expire ~= 1 then
    compensate(true, true, amount)
    return {-2, org_used, user_used}
  end
end
return {1, org_new, user_new}
"""

_REFUND_SCRIPT = """
local reserved = tonumber(redis.call('GET', KEYS[3]) or '-1')
if reserved < 0 then
  return 0
end
if reserved ~= tonumber(ARGV[1]) then
  return -1
end
redis.call('DEL', KEYS[3])
local amount = tonumber(ARGV[2])
for index = 1, 2 do
  if redis.call('EXISTS', KEYS[index]) == 1 then
    local used = tonumber(redis.call('GET', KEYS[index]) or '0')
    redis.call('SET', KEYS[index], math.max(0, used - amount), 'KEEPTTL')
  end
end
return 1
"""


class ChatBudgetSettings(Protocol):
    chat_cache_creation_input_cost_per_million_usd: float
    chat_cache_read_input_cost_per_million_usd: float
    chat_input_cost_per_million_usd: float
    chat_max_tokens: int
    chat_org_monthly_budget_usd: float
    chat_output_cost_per_million_usd: float
    chat_user_daily_budget_usd: float


class ChatBudgetLedger(Protocol):
    async def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: str,
    ) -> Any: ...


ChatBudgetRedisFactory = Callable[[], Awaitable[ChatBudgetLedger]]


@dataclass(frozen=True, slots=True)
class ChatBudgetReservation:
    amount_microusd: int
    org_key: str
    reservation_key: str
    user_key: str


def _usd_to_microusd(value: float) -> int:
    if not math.isfinite(value) or value <= 0:
        raise ValueError("chat budget and pricing values must be finite and positive")
    return math.ceil(value * _MICRO_USD_PER_USD)


def _period_keys(scope: ChatConversationScope, now: datetime) -> tuple[str, str]:
    return (
        f"chat-budget:v1:org:{scope.org_id}:{now:%Y-%m}",
        f"chat-budget:v1:user:{scope.org_id}:{scope.user_id}:{now:%Y-%m-%d}",
    )


def _period_ttls(now: datetime) -> tuple[int, int]:
    tomorrow = datetime.combine(
        now.date() + timedelta(days=1),
        datetime.min.time(),
        tzinfo=UTC,
    )
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1, tzinfo=UTC)
    else:
        next_month = datetime(now.year, now.month + 1, 1, tzinfo=UTC)
    return (
        max(1, math.ceil((next_month - now).total_seconds())),
        max(1, math.ceil((tomorrow - now).total_seconds())),
    )


def estimate_chat_reservation_microusd(
    prepared: PreparedChatRequest,
    settings: ChatBudgetSettings,
) -> int:
    """Reserve a conservative upper bound before contacting the provider."""

    serialized = json.dumps(
        {
            "system": prepared.system_prompt,
            "messages": prepared.messages,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    # A tokenizer cannot emit more input tokens than this conservative UTF-8
    # byte count for the supported text payload. Output reserves the configured
    # provider maximum.
    estimated_input_tokens = len(serialized)
    input_price = float(getattr(settings, "chat_input_cost_per_million_usd", 3.0))
    cache_creation_price = float(
        getattr(settings, "chat_cache_creation_input_cost_per_million_usd", 6.0)
    )
    output_price = float(getattr(settings, "chat_output_cost_per_million_usd", 15.0))
    # The first request can write the complete one-hour prompt cache, so reserve
    # every estimated input token at the more expensive applicable input rate.
    input_cost = estimated_input_tokens * max(input_price, cache_creation_price) / 1_000_000
    output_cost = settings.chat_max_tokens * output_price / 1_000_000
    return max(1, _usd_to_microusd(input_cost + output_cost))


def actual_chat_cost_microusd(
    usage: dict[str, Any],
    settings: ChatBudgetSettings,
) -> int:
    """Compute a conservative actual charge from provider usage metadata."""

    def tokens(name: str) -> int:
        value = usage.get(name, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"chat usage {name} must be a non-negative integer")
        return value

    input_tokens = tokens("input_tokens")
    cache_creation_input_tokens = tokens("cache_creation_input_tokens")
    cache_read_input_tokens = tokens("cache_read_input_tokens")
    output_tokens = tokens("output_tokens")
    input_price = float(getattr(settings, "chat_input_cost_per_million_usd", 3.0))
    cache_creation_price = float(
        getattr(settings, "chat_cache_creation_input_cost_per_million_usd", 6.0)
    )
    cache_read_price = float(getattr(settings, "chat_cache_read_input_cost_per_million_usd", 0.3))
    output_price = float(getattr(settings, "chat_output_cost_per_million_usd", 15.0))
    cost = (
        input_tokens * input_price
        + cache_creation_input_tokens * cache_creation_price
        + cache_read_input_tokens * cache_read_price
        + output_tokens * output_price
    ) / 1_000_000
    if cost == 0:
        return 1
    return _usd_to_microusd(cost)


async def reserve_chat_budget(
    *,
    prepared: PreparedChatRequest,
    scope: ChatConversationScope,
    settings: ChatBudgetSettings,
    now: datetime | None = None,
    redis_factory: ChatBudgetRedisFactory | None = None,
) -> ChatBudgetReservation:
    """Atomically reserve both the organization-month and user-day budgets."""

    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        raise ValueError("chat budget reservation time must be timezone-aware")
    amount = estimate_chat_reservation_microusd(prepared, settings)
    org_limit = _usd_to_microusd(float(getattr(settings, "chat_org_monthly_budget_usd", 25.0)))
    user_limit = _usd_to_microusd(float(getattr(settings, "chat_user_daily_budget_usd", 5.0)))
    org_key, user_key = _period_keys(scope, current_time)
    org_ttl, user_ttl = _period_ttls(current_time)
    reservation_key = f"chat-budget:v1:reservation:{scope.org_id}:{scope.user_id}:{uuid.uuid4()}"
    reservation_ttl = max(86_400, user_ttl)
    try:
        resolved_redis_factory = redis_factory or cast(
            ChatBudgetRedisFactory,
            get_chat_budget_redis,
        )
        redis = await resolved_redis_factory()
        result = await redis.eval(
            _RESERVE_SCRIPT,
            3,
            org_key,
            user_key,
            reservation_key,
            str(amount),
            str(org_limit),
            str(user_limit),
            str(org_ttl),
            str(user_ttl),
            str(reservation_ttl),
        )
    except Exception as exc:
        logger.error(
            "chat_budget_reservation_backend_failed",
            org_id=str(scope.org_id),
            user_id=str(scope.user_id),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        raise APIError(
            503,
            "Service Unavailable",
            "Chat budget controls are unavailable; refusing a paid provider call.",
        ) from exc

    try:
        status = int(result[0]) if isinstance(result, list | tuple) and result else -2
    except (TypeError, ValueError, OverflowError):
        status = -2
    if status == 0:
        logger.warning(
            "chat_budget_exhausted",
            org_id=str(scope.org_id),
            user_id=str(scope.user_id),
        )
        raise APIError(
            429,
            "Too Many Requests",
            "The governed chat spend limit has been reached for this billing period.",
            retry_after_seconds=user_ttl,
        )
    if status != 1:
        logger.error(
            "chat_budget_reservation_integrity_failed",
            org_id=str(scope.org_id),
            user_id=str(scope.user_id),
            ledger_status=status,
        )
        raise APIError(
            503,
            "Service Unavailable",
            "Chat budget controls could not establish a durable reservation; "
            "refusing a paid provider call.",
        )
    return ChatBudgetReservation(
        amount_microusd=amount,
        org_key=org_key,
        reservation_key=reservation_key,
        user_key=user_key,
    )


async def reconcile_chat_budget(
    *,
    reservation: ChatBudgetReservation,
    usage: dict[str, Any],
    settings: ChatBudgetSettings,
    redis_factory: ChatBudgetRedisFactory | None = None,
) -> None:
    """Refund only the unused conservative reservation after complete usage."""

    actual = actual_chat_cost_microusd(usage, settings)
    refund = max(0, reservation.amount_microusd - actual)
    resolved_redis_factory = redis_factory or cast(
        ChatBudgetRedisFactory,
        get_chat_budget_redis,
    )
    redis = await resolved_redis_factory()
    result = await redis.eval(
        _REFUND_SCRIPT,
        3,
        reservation.org_key,
        reservation.user_key,
        reservation.reservation_key,
        str(reservation.amount_microusd),
        str(refund),
    )
    if int(result) < 0:
        raise RuntimeError("chat budget reservation amount did not match the ledger")
    if int(result) == 0:
        logger.info(
            "chat_budget_reconciliation_already_applied",
            reservation_key=reservation.reservation_key,
        )
