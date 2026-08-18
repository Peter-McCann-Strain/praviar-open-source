"""Edge-case tests for the LLM response-cache integration helpers."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel

from praviar_pipeline.clients.claude_response_cache import (
    LLM_CACHE_ENVELOPE_SCHEMA_VERSION,
    _class_path,
    _dump_parsed,
    _load_parsed,
    _normalise_system,
    build_llm_cache_body,
    wrap_llm_call,
)
from praviar_pipeline.response_cache import (
    CacheMode,
    ResponseCache,
    set_current_cache,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _SampleTriage(BaseModel):
    """A simple public Pydantic model to round-trip through the cache."""

    relevance: str
    score: float
    reason: str = ""


@pytest.fixture(autouse=True)
def _reset_current_cache():
    set_current_cache(None)
    yield
    set_current_cache(None)


# ---------------------------------------------------------------------------
# _class_path
# ---------------------------------------------------------------------------


def test_class_path_is_stable() -> None:
    path = _class_path(_SampleTriage)
    assert path.endswith(":_SampleTriage")


# ---------------------------------------------------------------------------
# _normalise_system
# ---------------------------------------------------------------------------


def test_normalise_system_plain_string_passthrough() -> None:
    assert _normalise_system("you are a helper") == "you are a helper"


def test_normalise_system_handles_cache_control_list() -> None:
    # Anthropic content-block shape used when cache_system=True
    blocks = [
        {"type": "text", "text": "big prompt body"},
        {"type": "text", "text": "more", "cache_control": {"type": "ephemeral"}},
    ]
    normalised = _normalise_system(blocks)
    assert "big prompt body" in normalised
    assert "more" in normalised
    # Two identical semantic contents differing only in cache_control
    # produce the same normalised text → same cache key.
    blocks_no_cc = [
        {"type": "text", "text": "big prompt body"},
        {"type": "text", "text": "more"},
    ]
    assert _normalise_system(blocks) == _normalise_system(blocks_no_cc)


def test_normalise_system_handles_unexpected_types() -> None:
    assert _normalise_system(None) == "None"
    assert _normalise_system(42) == "42"


# ---------------------------------------------------------------------------
# build_llm_cache_body
# ---------------------------------------------------------------------------


def test_same_inputs_same_body() -> None:
    a = build_llm_cache_body(
        kind="complete",
        model="claude-sonnet-4-6",
        system="sys",
        user="hello",
        response_model=_SampleTriage,
        max_tokens=8192,
        temperature=0.0,
        effort=None,
        cache_system=False,
    )
    b = build_llm_cache_body(
        kind="complete",
        model="claude-sonnet-4-6",
        system="sys",
        user="hello",
        response_model=_SampleTriage,
        max_tokens=8192,
        temperature=0.0,
        effort=None,
        cache_system=False,
    )
    assert a == b


@pytest.mark.parametrize(
    "field,other",
    [
        ("kind", "complete_text"),
        ("model", "claude-haiku-4-5"),
        ("system", "different-system"),
        ("user", "different-user"),
        ("max_tokens", 4096),
        ("temperature", 1.0),
        ("effort", "high"),
        ("budget_tokens", 1024),
    ],
)
def test_different_field_different_body(field: str, other: Any) -> None:
    base_kwargs = {
        "kind": "complete",
        "model": "claude-sonnet-4-6",
        "system": "sys",
        "user": "hello",
        "response_model": _SampleTriage,
        "max_tokens": 8192,
        "temperature": 0.0,
        "effort": None,
        "cache_system": False,
        "budget_tokens": None,
    }
    a = build_llm_cache_body(**base_kwargs)
    b = build_llm_cache_body(**{**base_kwargs, field: other})
    assert a != b, f"Expected {field}={other!r} to change cache body"


def test_response_model_none_encoded_as_null() -> None:
    body = build_llm_cache_body(
        kind="complete_text",
        model="claude-sonnet-4-6",
        system="sys",
        user="hello",
        response_model=None,
        max_tokens=1024,
        temperature=0.0,
        effort=None,
        cache_system=False,
    )
    data = json.loads(body)
    assert data["response_model"] is None


def test_cache_system_does_not_affect_key_via_normalised_system() -> None:
    """cache_system=True vs False with same logical content produces
    different keys (we key on cache_system flag explicitly) — but the
    system-text normalisation is stable across the control-block
    variants."""
    body_plain = build_llm_cache_body(
        kind="complete",
        model="m",
        system="my prompt",
        user="u",
        response_model=_SampleTriage,
        max_tokens=1,
        temperature=0.0,
        effort=None,
        cache_system=False,
    )
    body_cache = build_llm_cache_body(
        kind="complete",
        model="m",
        system="my prompt",
        user="u",
        response_model=_SampleTriage,
        max_tokens=1,
        temperature=0.0,
        effort=None,
        cache_system=True,
    )
    assert body_plain != body_cache


# ---------------------------------------------------------------------------
# _dump_parsed / _load_parsed
# ---------------------------------------------------------------------------


def test_dump_load_pydantic_roundtrip() -> None:
    model = _SampleTriage(relevance="relevant", score=0.9, reason="keyword hit")
    envelope = _dump_parsed(model)
    assert envelope["kind"] == "pydantic"
    assert envelope["class_path"].endswith(":_SampleTriage")
    loaded = _load_parsed(envelope, expected_model=_SampleTriage)
    assert isinstance(loaded, _SampleTriage)
    assert loaded.relevance == "relevant"
    assert loaded.score == 0.9


def test_dump_load_plain_string() -> None:
    envelope = _dump_parsed("hello")
    assert envelope == {
        "schema_version": LLM_CACHE_ENVELOPE_SCHEMA_VERSION,
        "kind": "str",
        "data": "hello",
    }
    assert _load_parsed(envelope) == "hello"


def test_dump_load_plain_dict() -> None:
    envelope = _dump_parsed({"a": 1, "b": [2, 3]})
    assert envelope == {
        "schema_version": LLM_CACHE_ENVELOPE_SCHEMA_VERSION,
        "kind": "dict",
        "data": {"a": 1, "b": [2, 3]},
    }
    assert _load_parsed(envelope) == {"a": 1, "b": [2, 3]}


def test_dump_load_list() -> None:
    envelope = _dump_parsed([1, 2, 3])
    assert envelope == {
        "schema_version": LLM_CACHE_ENVELOPE_SCHEMA_VERSION,
        "kind": "list",
        "data": [1, 2, 3],
    }
    assert _load_parsed(envelope) == [1, 2, 3]


def test_dump_unknown_type_is_repr_and_load_fails_loudly() -> None:
    class CantSerialise:
        pass

    envelope = _dump_parsed(CantSerialise())
    assert envelope["kind"] == "repr"
    with pytest.raises(TypeError, match="non-serialisable"):
        _load_parsed(envelope)


def test_load_raises_on_unknown_kind() -> None:
    with pytest.raises(ValueError, match="Unknown"):
        _load_parsed(
            {
                "schema_version": LLM_CACHE_ENVELOPE_SCHEMA_VERSION,
                "kind": "mystery",
                "data": {},
            }
        )


def test_load_rejects_unversioned_envelope() -> None:
    with pytest.raises(ValueError, match="schema version"):
        _load_parsed({"kind": "str", "data": "unsafe"})


def test_load_never_imports_cache_controlled_class_path() -> None:
    envelope = _dump_parsed(_SampleTriage(relevance="x", score=0.1))
    envelope["class_path"] = "hostile_cache_side_effect:Payload"
    with pytest.raises(TypeError, match="does not match"):
        _load_parsed(envelope, expected_model=_SampleTriage)


@pytest.mark.parametrize("kind,data", [("dict", {}), ("str", "x"), ("list", [])])
def test_load_rejects_kind_confusion_for_expected_model(kind: str, data: Any) -> None:
    with pytest.raises(TypeError, match="kind does not match"):
        _load_parsed(
            {
                "schema_version": LLM_CACHE_ENVELOPE_SCHEMA_VERSION,
                "kind": kind,
                "data": data,
            },
            expected_model=_SampleTriage,
        )


# ---------------------------------------------------------------------------
# wrap_llm_call — RECORD / REPLAY round trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_then_replay_pydantic_roundtrip(tmp_path: Path) -> None:
    cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
    set_current_cache(cache)

    call_count = 0

    async def live() -> tuple[_SampleTriage, dict]:
        nonlocal call_count
        call_count += 1
        return (
            _SampleTriage(relevance="relevant", score=0.87, reason="aspirin hit"),
            {"input_tokens": 200, "output_tokens": 50},
        )

    def unwrap(live_result: tuple[_SampleTriage, dict]):
        parsed, usage = live_result
        return parsed, usage, {}

    kwargs = dict(
        kind="complete",
        role="triage",
        model="claude-sonnet-4-6",
        system="triage system",
        user="compound X",
        response_model=_SampleTriage,
        max_tokens=1024,
        temperature=0.0,
        effort=None,
        cache_system=False,
        live_call=live,
        unwrap=unwrap,
    )

    parsed, usage, extras = await wrap_llm_call(**kwargs)
    assert isinstance(parsed, _SampleTriage)
    assert parsed.relevance == "relevant"
    assert usage == {"input_tokens": 200, "output_tokens": 50}
    assert call_count == 1
    assert extras == {}

    # Now switch to REPLAY mode with a fresh cache reading from the same
    # directory.
    set_current_cache(None)
    replay_cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
    set_current_cache(replay_cache)

    async def should_not_be_called() -> tuple[_SampleTriage, dict]:
        raise AssertionError("live call during replay")

    parsed2, usage2, _extras2 = await wrap_llm_call(**{**kwargs, "live_call": should_not_be_called})

    assert isinstance(parsed2, _SampleTriage)
    assert parsed2.relevance == "relevant"
    assert parsed2.score == 0.87
    # Replay reports zero tokens (didn't actually spend) and preserves
    # the cached original for audit.
    assert usage2["input_tokens"] == 0
    assert usage2["output_tokens"] == 0
    assert usage2["replay_cache_hit"] is True
    assert usage2["cached_original"] == {"input_tokens": 200, "output_tokens": 50}


@pytest.mark.asyncio
async def test_record_string_result_roundtrip(tmp_path: Path) -> None:
    cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
    set_current_cache(cache)

    async def live() -> tuple[str, dict]:
        return ("42", {"input_tokens": 10, "output_tokens": 1})

    def unwrap(r: tuple[str, dict]):
        return r[0], r[1], {}

    parsed, usage, _extras = await wrap_llm_call(
        kind="complete_text",
        role="report",
        model="claude-sonnet-4-6",
        system="sys",
        user="what is 6x7?",
        response_model=None,
        max_tokens=16,
        temperature=0.0,
        effort=None,
        cache_system=False,
        live_call=live,
        unwrap=unwrap,
    )
    assert parsed == "42"
    assert usage["input_tokens"] == 10


@pytest.mark.asyncio
async def test_record_with_extras_roundtrip(tmp_path: Path) -> None:
    """complete_with_thinking returns three values — parsed, thinking text, usage.
    Verify the extras dict preserves the thinking text across a replay."""
    cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
    set_current_cache(cache)

    async def live():
        return (
            _SampleTriage(relevance="relevant", score=1.0),
            "reasoning step 1\nreasoning step 2",
            {"input_tokens": 500, "output_tokens": 100},
        )

    def unwrap(r):
        parsed, thinking_text, usage = r
        return parsed, usage, {"thinking_text": thinking_text}

    _parsed, _usage, extras = await wrap_llm_call(
        kind="complete_with_thinking",
        role="deep",
        model="claude-sonnet-4-6",
        system="sys",
        user="analyze",
        response_model=_SampleTriage,
        max_tokens=128000,
        temperature=0.0,
        effort=None,
        cache_system=False,
        budget_tokens=32000,
        live_call=live,
        unwrap=unwrap,
    )
    assert "reasoning step 1" in extras["thinking_text"]

    # Replay and confirm extras survive.
    set_current_cache(None)
    replay = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
    set_current_cache(replay)

    async def should_not_be_called():
        raise AssertionError()

    _p, _u, extras2 = await wrap_llm_call(
        kind="complete_with_thinking",
        role="deep",
        model="claude-sonnet-4-6",
        system="sys",
        user="analyze",
        response_model=_SampleTriage,
        max_tokens=128000,
        temperature=0.0,
        effort=None,
        cache_system=False,
        budget_tokens=32000,
        live_call=should_not_be_called,
        unwrap=unwrap,
    )
    assert extras2["thinking_text"] == extras["thinking_text"]


@pytest.mark.asyncio
async def test_no_cache_installed_is_pure_passthrough() -> None:
    set_current_cache(None)

    async def live():
        return _SampleTriage(relevance="n/a", score=0.0), {"input_tokens": 1, "output_tokens": 1}

    def unwrap(r):
        return r[0], r[1], {}

    parsed, usage, extras = await wrap_llm_call(
        kind="complete",
        role="triage",
        model="m",
        system="s",
        user="u",
        response_model=_SampleTriage,
        max_tokens=1,
        temperature=0.0,
        effort=None,
        cache_system=False,
        live_call=live,
        unwrap=unwrap,
    )
    # With no cache installed, unwrap() still runs and we return the same
    # unified (parsed, usage, extras) 3-tuple as the cached path. This
    # means every caller code path handles a single shape.
    assert isinstance(parsed, _SampleTriage)
    assert parsed.relevance == "n/a"
    assert usage == {"input_tokens": 1, "output_tokens": 1}
    assert extras == {}


@pytest.mark.asyncio
async def test_disabled_cache_is_passthrough(tmp_path: Path) -> None:
    cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.DISABLED)
    set_current_cache(cache)

    async def live():
        return _SampleTriage(relevance="x", score=0.1), {"input_tokens": 1, "output_tokens": 1}

    def unwrap(r):
        return r[0], r[1], {}

    result = await wrap_llm_call(
        kind="complete",
        role="triage",
        model="m",
        system="s",
        user="u",
        response_model=_SampleTriage,
        max_tokens=1,
        temperature=0.0,
        effort=None,
        cache_system=False,
        live_call=live,
        unwrap=unwrap,
    )
    parsed, usage = result[0], result[1]
    assert parsed.relevance == "x"
    assert usage == {"input_tokens": 1, "output_tokens": 1}
    # DISABLED never writes.
    assert not cache.cache_path.exists()


@pytest.mark.asyncio
async def test_different_prompt_different_cache_entries(tmp_path: Path) -> None:
    cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
    set_current_cache(cache)

    call_count = 0

    async def live():
        nonlocal call_count
        call_count += 1
        return (
            _SampleTriage(relevance="relevant", score=0.5 + 0.1 * call_count),
            {"input_tokens": 100, "output_tokens": 20},
        )

    def unwrap(r):
        return r[0], r[1], {}

    kwargs = dict(
        kind="complete",
        role="triage",
        model="claude-sonnet-4-6",
        system="triage system",
        response_model=_SampleTriage,
        max_tokens=1024,
        temperature=0.0,
        effort=None,
        cache_system=False,
        live_call=live,
        unwrap=unwrap,
    )

    await wrap_llm_call(**kwargs, user="compound A")
    await wrap_llm_call(**kwargs, user="compound B")

    assert len(cache) == 2
    assert call_count == 2


@pytest.mark.asyncio
async def test_exception_in_live_call_is_not_cached(tmp_path: Path) -> None:
    cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
    set_current_cache(cache)

    async def failing_live():
        raise RuntimeError("anthropic is on fire")

    def unwrap(r):
        return r[0], r[1], {}

    with pytest.raises(RuntimeError, match="on fire"):
        await wrap_llm_call(
            kind="complete",
            role="triage",
            model="m",
            system="s",
            user="u",
            response_model=_SampleTriage,
            max_tokens=1,
            temperature=0.0,
            effort=None,
            cache_system=False,
            live_call=failing_live,
            unwrap=unwrap,
        )
    assert len(cache) == 0
    assert cache.cache_path.exists()
    assert cache.cache_path.read_text(encoding="utf-8") == ""


@pytest.mark.asyncio
async def test_cache_key_stable_across_cache_control_variants(tmp_path: Path) -> None:
    """Two RECORD calls with logically-identical system content but
    different Anthropic cache-control wrappings should hit the same
    entry — otherwise toggling cache_system=True in the middle of a run
    would double the cache size without helping replay."""
    cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
    set_current_cache(cache)

    async def live():
        return _SampleTriage(relevance="x", score=0.0), {"input_tokens": 1, "output_tokens": 1}

    def unwrap(r):
        return r[0], r[1], {}

    # Both calls use cache_system=False but the system is delivered as
    # a content-block list in one case and a string in the other. The
    # cache body string uses _normalise_system, so both map to the same
    # key.
    base = dict(
        kind="complete",
        role="triage",
        model="m",
        user="u",
        response_model=_SampleTriage,
        max_tokens=1,
        temperature=0.0,
        effort=None,
        cache_system=False,
        live_call=live,
        unwrap=unwrap,
    )
    await wrap_llm_call(**base, system="hello")
    await wrap_llm_call(**base, system=[{"type": "text", "text": "hello"}])
    assert len(cache) == 1
