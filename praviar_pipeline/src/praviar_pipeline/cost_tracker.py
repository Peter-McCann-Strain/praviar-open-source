"""Per-run LLM cost tracking — stamped into the report manifest.

Every pipeline run installs a :class:`CostTracker` via :func:`set_current_tracker`.
The Claude client records usage after every successful API call, tagged with a
role (``triage`` / ``analysis`` / ``deep`` / ``report`` / ``verification`` /
``critic`` / ``doe`` / ``invalidity`` / ``unknown``). At end-of-run, the
tracker's :meth:`CostTracker.snapshot` is stamped into the
:class:`~praviar_pipeline.manifest.ReportManifest` and logged.

Pricing is encoded in :data:`_PRICING` keyed by a model prefix match. An
unknown model prices at zero and logs ``unknown_model_pricing`` — we never
crash the pipeline over a new model ID.

Thread-safe via :class:`threading.Lock` so async gather / concurrent tool
rounds can record safely.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

import structlog

from praviar_pipeline.errors import PaidCallBudgetExceededError

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Pricing table (USD per 1M tokens) — current Anthropic public pricing
# ---------------------------------------------------------------------------

# Price order: (input, output, cache_read, cache_write) per 1M tokens.
# Keyed by model-ID prefix. First match wins; iterate deterministically by
# descending prefix length so longer prefixes beat shorter ones.
#
# All three rows verified against Anthropic's public pricing table on
# 2026-04-15: https://platform.claude.com/docs/en/docs/about-claude/pricing
# (``cache_write`` uses the 5-minute multiplier = 1.25x base input, matching
# the cache TTL ``ClaudeClient`` sets on its cache_control blocks). Opus 4.6
# was previously stamped with Opus 4.1 rates ($15 / $75 / $1.50 / $18.75) —
# actual Opus 4.6 pricing is 1/3 of that: $5 / $25 / $0.50 / $6.25.
_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_write": 3.75,
    },
    "claude-haiku-4-5": {
        "input": 1.0,
        "output": 5.0,
        "cache_read": 0.10,
        "cache_write": 1.25,
    },
    "claude-opus-4-6": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.50,
        "cache_write": 6.25,
    },
}


def _lookup_pricing(model: str) -> dict[str, float] | None:
    """Return the pricing row whose prefix matches ``model``, or ``None``."""
    # Longest-prefix-wins so ``claude-sonnet-4-6-20250929`` matches
    # ``claude-sonnet-4-6`` before any shorter-generic prefix we might add later.
    for prefix in sorted(_PRICING, key=len, reverse=True):
        if model.startswith(prefix):
            return _PRICING[prefix]
    return None


def _priced_usage_usd(*, pricing: dict[str, float], usage: dict[str, Any]) -> float:
    return (
        int(usage.get("input_tokens") or 0) * pricing["input"]
        + int(usage.get("output_tokens") or 0) * pricing["output"]
        + int(usage.get("cache_read_input_tokens") or 0) * pricing["cache_read"]
        + int(usage.get("cache_creation_input_tokens") or 0) * pricing["cache_write"]
    ) / 1_000_000.0


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class RoleCost:
    """Running totals for one pipeline role."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    estimated_usd: float = 0.0
    call_count: int = 0
    #: Map of model-id -> call count for that model under this role.
    models: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "estimated_usd": round(self.estimated_usd, 6),
            "call_count": self.call_count,
            "models": dict(self.models),
        }


@dataclass(frozen=True, slots=True)
class PaidCallReservation:
    """One worst-case budget hold around an in-flight provider request."""

    reservation_id: int
    reserved_usd: float
    model: str


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------


class CostTracker:
    """Thread-safe accumulator for Anthropic API token usage across a run."""

    def __init__(self, *, hard_budget_usd: float | None = None) -> None:
        if hard_budget_usd is not None and hard_budget_usd <= 0:
            raise ValueError("hard_budget_usd must be positive when configured")
        self._by_role: dict[str, RoleCost] = {}
        self._lock = threading.Lock()
        self._hard_budget_usd = hard_budget_usd
        self._budget_spent_usd = 0.0
        self._budget_reservations: dict[int, PaidCallReservation] = {}
        self._next_reservation_id = 1
        # Remember models we've already warned about so the log doesn't spam.
        self._unknown_warned: set[str] = set()

    # -- recording ---------------------------------------------------------

    def reserve_paid_call(
        self,
        *,
        model: str,
        max_output_tokens: int,
        estimated_input_tokens: int,
    ) -> PaidCallReservation | None:
        """Reserve the worst-case priced request before any paid network call."""
        if self._hard_budget_usd is None:
            return None
        pricing = _lookup_pricing(model)
        if pricing is None:
            raise PaidCallBudgetExceededError(
                "Paid call blocked because the configured model has no verified pricing.",
                model=model,
                hard_budget_usd=self._hard_budget_usd,
            )
        if max_output_tokens <= 0 or estimated_input_tokens < 0:
            raise ValueError("paid call token estimates must be non-negative")
        # Treat every estimated prompt token as the most expensive input-like
        # token class. This remains conservative when prompt caching is enabled.
        estimated_cost = (
            estimated_input_tokens * max(pricing["input"], pricing["cache_write"])
            + max_output_tokens * pricing["output"]
        ) / 1_000_000.0
        with self._lock:
            outstanding = sum(
                reservation.reserved_usd for reservation in self._budget_reservations.values()
            )
            projected = self._budget_spent_usd + outstanding + estimated_cost
            if projected > self._hard_budget_usd:
                raise PaidCallBudgetExceededError(
                    "Paid call blocked before dispatch because it would exceed "
                    "the configured per-run hard budget.",
                    model=model,
                    projected_usd=projected,
                    hard_budget_usd=self._hard_budget_usd,
                )
            reservation = PaidCallReservation(
                reservation_id=self._next_reservation_id,
                reserved_usd=estimated_cost,
                model=model,
            )
            self._next_reservation_id += 1
            self._budget_reservations[reservation.reservation_id] = reservation
            return reservation

    def settle_paid_call(
        self,
        reservation: PaidCallReservation | None,
        *,
        model: str,
        usage: dict[str, Any],
    ) -> None:
        """Replace an in-flight hold with the provider's actual metered usage."""
        if reservation is None:
            return
        pricing = _lookup_pricing(model)
        if pricing is None:
            actual_cost = reservation.reserved_usd
        else:
            actual_cost = _priced_usage_usd(pricing=pricing, usage=usage)
        with self._lock:
            active = self._budget_reservations.pop(reservation.reservation_id, None)
            if active is None:
                raise RuntimeError("paid call reservation is not active")
            self._budget_spent_usd += max(actual_cost, 0.0)

    def forfeit_paid_call(self, reservation: PaidCallReservation | None) -> None:
        """Conservatively charge a reservation when provider outcome is ambiguous."""
        if reservation is None:
            return
        with self._lock:
            active = self._budget_reservations.pop(reservation.reservation_id, None)
            if active is None:
                return
            self._budget_spent_usd += active.reserved_usd

    def record(self, *, role: str, model: str, usage: dict[str, Any]) -> None:
        """Record one Claude API response's token usage under ``role``.

        ``usage`` is the Anthropic SDK usage dict and must contain
        ``input_tokens`` and ``output_tokens``. ``cache_read_input_tokens`` and
        ``cache_creation_input_tokens`` are optional (absent on non-caching
        calls). Anything else in the dict is ignored.
        """
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        cache_read = int(usage.get("cache_read_input_tokens") or 0)
        cache_create = int(usage.get("cache_creation_input_tokens") or 0)

        pricing = _lookup_pricing(model)
        if pricing is None:
            # Warn once per unseen model; record zero cost but still accumulate tokens.
            if model not in self._unknown_warned:
                self._unknown_warned.add(model)
                logger.warning(
                    "unknown_model_pricing",
                    model=model,
                    action="cost_recorded_as_zero",
                )
            cost = 0.0
        else:
            cost = _priced_usage_usd(pricing=pricing, usage=usage)

        with self._lock:
            bucket = self._by_role.setdefault(role or "unknown", RoleCost())
            bucket.input_tokens += input_tokens
            bucket.output_tokens += output_tokens
            bucket.cache_read_tokens += cache_read
            bucket.cache_creation_tokens += cache_create
            bucket.estimated_usd += cost
            bucket.call_count += 1
            bucket.models[model] = bucket.models.get(model, 0) + 1

    # -- introspection -----------------------------------------------------

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """Return a plain-dict copy of the per-role aggregates."""
        with self._lock:
            return {role: cost.to_dict() for role, cost in self._by_role.items()}

    def total_usd(self) -> float:
        with self._lock:
            return round(sum(c.estimated_usd for c in self._by_role.values()), 6)

    def total_tokens(self) -> dict[str, int]:
        """Aggregate tokens across all roles — handy for end-of-run logging."""
        with self._lock:
            return {
                "input_tokens": sum(c.input_tokens for c in self._by_role.values()),
                "output_tokens": sum(c.output_tokens for c in self._by_role.values()),
                "cache_read_tokens": sum(c.cache_read_tokens for c in self._by_role.values()),
                "cache_creation_tokens": sum(
                    c.cache_creation_tokens for c in self._by_role.values()
                ),
            }

    def reset(self) -> None:
        with self._lock:
            self._by_role.clear()
            self._unknown_warned.clear()
            self._budget_spent_usd = 0.0
            self._budget_reservations.clear()
            self._next_reservation_id = 1


# ---------------------------------------------------------------------------
# Module-level singleton (same pattern as response_cache.py)
# ---------------------------------------------------------------------------

_CURRENT_TRACKER: CostTracker | None = None
_CURRENT_TRACKER_LOCK = threading.Lock()


def set_current_tracker(tracker: CostTracker | None) -> None:
    """Install (or clear) the active cost tracker for this pipeline run."""
    global _CURRENT_TRACKER
    with _CURRENT_TRACKER_LOCK:
        _CURRENT_TRACKER = tracker


def get_current_tracker() -> CostTracker | None:
    """Return the currently-installed tracker, or ``None`` if tracking is off."""
    with _CURRENT_TRACKER_LOCK:
        return _CURRENT_TRACKER


def reserve_current_paid_call(
    *,
    model: str,
    max_output_tokens: int,
    estimated_input_tokens: int,
) -> PaidCallReservation | None:
    """Reserve against the active run budget, if a tracker is installed."""
    tracker = get_current_tracker()
    if tracker is None:
        return None
    return tracker.reserve_paid_call(
        model=model,
        max_output_tokens=max_output_tokens,
        estimated_input_tokens=estimated_input_tokens,
    )


def settle_current_paid_call(
    reservation: PaidCallReservation | None,
    *,
    model: str,
    usage: dict[str, Any],
) -> None:
    tracker = get_current_tracker()
    if tracker is not None:
        tracker.settle_paid_call(reservation, model=model, usage=usage)


def forfeit_current_paid_call(reservation: PaidCallReservation | None) -> None:
    tracker = get_current_tracker()
    if tracker is not None:
        tracker.forfeit_paid_call(reservation)
