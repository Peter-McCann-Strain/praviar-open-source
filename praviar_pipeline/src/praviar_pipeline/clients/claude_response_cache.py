"""LLM response caching for the Claude client.

Extends :mod:`praviar_pipeline.response_cache` to cover Claude completions.
Combined with per-client HTTP caches (PubChem / Lens / EPO / BigQuery),
an entire pipeline run can be replayed from disk without spending a
single dollar at Anthropic or any external service.

Design notes
============

* **What we cache**: the final parsed result the caller would receive,
  plus the usage dict, plus any additional tuple members ("extras").
  We do NOT cache Anthropic's raw stream events — too low-level, too
  coupled to SDK versions.

* **What we key on**: model ID, system prompt (normalised so
  ``cache_system`` content-blocks hash to the same key as the plain
  string form), user prompt, response model class path, max_tokens,
  temperature, effort, cache_system flag, and budget_tokens.

* **What we don't cache**: side-effects (logging, cost-tracker writes).
  On a replay hit we emit zero tokens and mark the usage dict
  ``replay_cache_hit=True`` — a replay should report $0 spent.

* **Safety**: never pickle or dynamically import cache-controlled classes.
  Pydantic ``model_dump(mode="json")`` envelopes carry a schema version and
  must exactly match the response model already authorized by the live call.

API shape
=========

``wrap_llm_call`` always returns ``(parsed, usage, extras)`` —
regardless of whether the cache hit, missed, or was absent. Callers
decompose that tuple into whatever shape their completion method
normally returns (e.g. ``complete`` is ``(parsed, usage)``;
``complete_with_thinking`` is ``(parsed, thinking_text, usage)`` —
the thinking_text lives in ``extras``).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

from praviar_pipeline.response_cache import CacheMode, get_current_cache

if TYPE_CHECKING:
    from pydantic import BaseModel

logger = structlog.get_logger()
LLM_CACHE_ENVELOPE_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Cache key construction
# ---------------------------------------------------------------------------


def _class_path(cls: type) -> str:
    """Return ``"module:ClassName"`` for cache-key and equality checks."""
    return f"{cls.__module__}:{cls.__name__}"


def _normalise_system(system: Any) -> str:
    """Flatten the Anthropic system-content shape (plain string or content-
    block list with ``cache_control`` sidecars) into a deterministic
    string. Two calls with identical content but different
    ``cache_control`` wrapping hash to the same key — otherwise toggling
    the ephemeral-cache flag mid-run would bloat the cache without
    improving replay."""
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        parts: list[str] = []
        for block in system:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(system)


def build_llm_cache_body(
    *,
    kind: str,
    model: str,
    system: Any,
    user: str,
    response_model: type | None,
    max_tokens: int,
    temperature: float,
    effort: str | None,
    cache_system: bool,
    budget_tokens: int | None = None,
) -> str:
    """Build the deterministic request-body string used as the cache key.

    ``kind`` is one of ``"complete"`` / ``"complete_text"`` /
    ``"complete_with_thinking"`` so the three completion families never
    collide on an otherwise-identical payload.
    """
    payload = {
        "kind": kind,
        "model": model,
        "system": _normalise_system(system),
        "user": user,
        "response_model": _class_path(response_model) if response_model else None,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "effort": effort,
        "cache_system": cache_system,
        "budget_tokens": budget_tokens,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def _dump_parsed(value: Any) -> dict[str, Any]:
    """Serialise a parsed LLM response into a JSON-safe envelope."""
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return {
            "schema_version": LLM_CACHE_ENVELOPE_SCHEMA_VERSION,
            "kind": "pydantic",
            "class_path": _class_path(type(value)),
            "data": dump(mode="json"),
        }
    if isinstance(value, str):
        return {
            "schema_version": LLM_CACHE_ENVELOPE_SCHEMA_VERSION,
            "kind": "str",
            "data": value,
        }
    if isinstance(value, dict):
        return {
            "schema_version": LLM_CACHE_ENVELOPE_SCHEMA_VERSION,
            "kind": "dict",
            "data": value,
        }
    if isinstance(value, (list, tuple)):
        return {
            "schema_version": LLM_CACHE_ENVELOPE_SCHEMA_VERSION,
            "kind": "list",
            "data": list(value),
        }
    return {
        "schema_version": LLM_CACHE_ENVELOPE_SCHEMA_VERSION,
        "kind": "repr",
        "data": repr(value),
    }


def _load_parsed(
    envelope: dict[str, Any],
    *,
    expected_model: type[BaseModel] | None = None,
) -> Any:
    """Load a cache envelope using only the caller-authorized response model."""
    if envelope.get("schema_version") != LLM_CACHE_ENVELOPE_SCHEMA_VERSION:
        raise ValueError("Unsupported cached LLM envelope schema version")
    kind = envelope.get("kind")
    data = envelope.get("data")
    if expected_model is not None and kind != "pydantic":
        raise TypeError("Cached response kind does not match the authorized response model")
    if kind == "pydantic":
        if expected_model is None:
            raise TypeError("Cached Pydantic response has no authorized response model")
        expected_path = _class_path(expected_model)
        if envelope.get("class_path") != expected_path:
            raise TypeError("Cached Pydantic response model does not match the authorized model")
        return expected_model.model_validate(data)
    if kind == "str":
        return data
    if kind == "dict":
        return data
    if kind == "list":
        return data
    if kind == "repr":
        raise TypeError(
            "Cached LLM response used a non-serialisable type "
            f"(repr={data!r}). Replay cannot reconstruct it."
        )
    raise ValueError(f"Unknown cached LLM envelope kind: {kind!r}")


# ---------------------------------------------------------------------------
# Replay-hit marker on usage dict
# ---------------------------------------------------------------------------


def _zero_usage(original_usage: dict[str, Any] | None) -> dict[str, Any]:
    """Usage dict reporting zero tokens; original usage kept under
    ``cached_original`` for audit."""
    out: dict[str, Any] = {
        "model": (original_usage or {}).get("model", "replay"),
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "replay_cache_hit": True,
    }
    if original_usage:
        out["cached_original"] = dict(original_usage)
    return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def wrap_llm_call(
    *,
    kind: str,
    role: str,
    model: str,
    system: Any,
    user: str,
    response_model: type | None,
    max_tokens: int,
    temperature: float,
    effort: str | None,
    cache_system: bool,
    live_call,
    unwrap,
    budget_tokens: int | None = None,
):
    """Run ``live_call`` through the active response cache.

    Parameters
    ----------
    live_call : async callable
        Performs the real LLM call. Returns the caller's usual tuple
        (e.g. ``(parsed, usage)`` for ``complete``).
    unwrap : callable
        Takes whatever ``live_call`` returned and maps it to
        ``(parsed, usage, extras)`` where ``parsed`` is the value to
        cache, ``usage`` is the usage dict, and ``extras`` is a dict of
        any additional tuple members (e.g. ``{"thinking_text": ...}``).

    Returns
    -------
    tuple[Any, dict, dict]
        Always returns ``(parsed, usage, extras)`` — even in passthrough
        (no cache installed). Callers rebuild their original tuple from
        this three-tuple.
    """
    cache = get_current_cache()
    if cache is None or cache.mode == CacheMode.DISABLED:
        live_result = await live_call()
        parsed, usage, extras = unwrap(live_result)
        return parsed, dict(usage) if usage else {}, dict(extras) if extras else {}

    cache_body = build_llm_cache_body(
        kind=kind,
        model=model,
        system=system,
        user=user,
        response_model=response_model,
        max_tokens=max_tokens,
        temperature=temperature,
        effort=effort,
        cache_system=cache_system,
        budget_tokens=budget_tokens,
    )

    before_entries = len(cache)

    async def _do_live_then_wrap() -> dict[str, Any]:
        live_result = await live_call()
        parsed, usage, extras = unwrap(live_result)
        return {
            "parsed_envelope": _dump_parsed(parsed),
            "usage": dict(usage) if usage else {},
            "extras": dict(extras) if extras else {},
        }

    cached = await cache.wrap(
        source=f"claude:{role}",
        method="POST",
        url=f"messages/{model}",
        body=cache_body,
        call=_do_live_then_wrap,
    )

    was_replay_hit = len(cache) == before_entries
    parsed = _load_parsed(cached["parsed_envelope"], expected_model=response_model)
    original_usage = cached.get("usage") or {}
    extras = cached.get("extras") or {}

    if was_replay_hit:
        logger.debug(
            "llm_cache_hit",
            model=model,
            cached_input=original_usage.get("input_tokens", 0),
            cached_output=original_usage.get("output_tokens", 0),
        )
        usage = _zero_usage(original_usage)
    else:
        usage = original_usage

    return parsed, usage, extras
