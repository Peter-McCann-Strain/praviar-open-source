"""End-to-end integration test: RECORD → REPLAY across every cached layer.

Proves that a full pipeline-shaped workload — mixing HTTP client calls
(PubChem, Lens, BigQuery, EPO, SureChEMBL, etc. via their cache-aware
wrappers) and Claude LLM calls (``complete`` / ``complete_text`` /
``complete_with_thinking`` via the LLM response cache) — can be
recorded once and replayed against the same cache without contacting
any live service.

This is the contract the manifest-v2 work was built to satisfy. If this
test fails, the SG-120 production benchmark's replay promise does not
hold.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel

from praviar_pipeline.clients.claude_response_cache import wrap_llm_call
from praviar_pipeline.response_cache import (
    CacheEntry,
    CacheMissError,
    CacheMode,
    ResponseCache,
    compute_request_key,
    get_current_cache,
    set_current_cache,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Model fixture for LLM round-trip
# ---------------------------------------------------------------------------


class _TriageVerdict(BaseModel):
    patent_id: str
    relevance: str
    score: float
    reasoning: str = ""


class _InvalidityAssessment(BaseModel):
    patent_id: str
    anticipated_by: list[str]
    overall_strength: float


# ---------------------------------------------------------------------------
# Synthetic "pipeline" — exercises every cache layer
# ---------------------------------------------------------------------------


async def _fake_pubchem_call(cache: ResponseCache | None, cid: int) -> dict:
    """Models pubchem._get through cache.wrap."""

    async def live() -> dict:
        # Simulate a real network response.
        return {"cid": cid, "synonyms": [f"compound-{cid}", f"c-{cid}"]}

    if cache is None or cache.mode == CacheMode.DISABLED:
        return await live()
    return await cache.wrap(
        source="pubchem",
        method="GET",
        url=f"/compound/cid/{cid}",
        body=None,
        call=live,
    )


async def _fake_lens_call(cache: ResponseCache | None, payload: dict) -> dict:
    async def live() -> dict:
        return {"hits": [{"patent_id": "US-1234567-B2"}]}

    if cache is None or cache.mode == CacheMode.DISABLED:
        return await live()
    return await cache.wrap(
        source="lens",
        method="POST",
        url="/patent/search",
        body=json.dumps(payload, sort_keys=True),
        call=live,
    )


async def _fake_llm_triage(compound_name: str) -> tuple[_TriageVerdict, dict]:
    """Models complete() for a triage decision."""

    async def live() -> tuple[_TriageVerdict, dict]:
        return (
            _TriageVerdict(
                patent_id="US-1234567-B2",
                relevance="relevant",
                score=0.92,
                reasoning="Claim 1 literally reads on the compound.",
            ),
            {"input_tokens": 850, "output_tokens": 120},
        )

    parsed, usage, _extras = await wrap_llm_call(
        kind="complete",
        role="triage",
        model="claude-haiku-4-5",
        system="You triage patents for FTO.",
        user=f"Compound: {compound_name}",
        response_model=_TriageVerdict,
        max_tokens=2048,
        temperature=0.0,
        effort=None,
        cache_system=False,
        live_call=live,
        unwrap=lambda r: (r[0], r[1], {}),
    )
    return parsed, usage


async def _fake_llm_invalidity(patent_id: str) -> tuple[_InvalidityAssessment, str, dict]:
    """Models complete_with_thinking() for an invalidity decision."""

    async def live() -> tuple[_InvalidityAssessment, str, dict]:
        return (
            _InvalidityAssessment(
                patent_id=patent_id,
                anticipated_by=["US-7777777", "WO-2019-XYZ"],
                overall_strength=0.75,
            ),
            "Step 1: read claim 1. Step 2: compare to US-7777777. Step 3: weigh Graham factors.",
            {"input_tokens": 4200, "output_tokens": 800},
        )

    parsed, usage, extras = await wrap_llm_call(
        kind="complete_with_thinking",
        role="invalidity",
        model="claude-sonnet-4-6",
        system="You perform invalidity analysis.",
        user=f"Patent: {patent_id}",
        response_model=_InvalidityAssessment,
        max_tokens=128000,
        temperature=0.0,
        effort=None,
        cache_system=False,
        budget_tokens=32000,
        live_call=live,
        unwrap=lambda r: (r[0], r[2], {"thinking_text": r[1]}),
    )
    return parsed, extras.get("thinking_text", ""), usage


async def _run_synthetic_pipeline(compound: str, cid: int) -> dict[str, Any]:
    """A mini-pipeline that exercises every cache layer: HTTP (pubchem +
    lens) and LLM (complete + complete_with_thinking). Returns a
    deterministic summary dict so two runs can be byte-compared."""
    cache = get_current_cache()

    pubchem = await _fake_pubchem_call(cache, cid)
    lens = await _fake_lens_call(cache, {"query": compound})
    triage, triage_usage = await _fake_llm_triage(compound)
    invalidity, thinking, invalidity_usage = await _fake_llm_invalidity(
        triage.patent_id,
    )

    return {
        "compound": compound,
        "pubchem_synonyms": pubchem.get("synonyms", []),
        "lens_hit_count": len(lens.get("hits", [])),
        "triage": triage.model_dump(mode="json"),
        "triage_usage_hit": triage_usage.get("replay_cache_hit", False),
        "invalidity": invalidity.model_dump(mode="json"),
        "invalidity_thinking_prefix": thinking[:40],
        "invalidity_usage_hit": invalidity_usage.get("replay_cache_hit", False),
    }


# ---------------------------------------------------------------------------
# Fixture: clean cache singleton between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_cache_singleton():
    set_current_cache(None)
    yield
    set_current_cache(None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_cache_baseline(tmp_path: Path) -> None:
    """Sanity check: the synthetic pipeline runs without any cache
    installed and returns a coherent result."""
    result = await _run_synthetic_pipeline(compound="aspirin", cid=2244)
    assert result["compound"] == "aspirin"
    assert result["pubchem_synonyms"] == ["compound-2244", "c-2244"]
    assert result["lens_hit_count"] == 1
    assert result["triage"]["patent_id"] == "US-1234567-B2"
    assert result["invalidity"]["overall_strength"] == 0.75
    assert result["triage_usage_hit"] is False  # no cache hit — no marker
    assert result["invalidity_usage_hit"] is False


@pytest.mark.asyncio
async def test_record_then_replay_round_trip(tmp_path: Path) -> None:
    """The end-to-end promise: record a pipeline run, then run the exact
    same pipeline against the recorded cache in REPLAY mode and get
    byte-identical output (except for the replay_cache_hit markers)."""
    # --- RECORD phase
    rec = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
    set_current_cache(rec)
    recorded = await _run_synthetic_pipeline(compound="aspirin", cid=2244)

    # Cache should have four entries: pubchem, lens, two LLM calls.
    assert len(rec) == 4
    {k.split(":", 1)[0] if ":" in k else k for k in rec}
    # (Note: sources are opaque hashes in cache; use the JSONL file to verify.)
    lines = rec.cache_path.read_text("utf-8").strip().splitlines()
    assert len(lines) == 4
    sources = {json.loads(line)["source"] for line in lines}
    assert sources == {"pubchem", "lens", "claude:triage", "claude:invalidity"}

    # --- REPLAY phase (fresh cache object reads the same dir)
    set_current_cache(None)
    rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
    set_current_cache(rep)

    replayed = await _run_synthetic_pipeline(compound="aspirin", cid=2244)

    # Non-hit-marker fields are byte-identical.
    for key in (
        "compound",
        "pubchem_synonyms",
        "lens_hit_count",
        "triage",
        "invalidity",
        "invalidity_thinking_prefix",
    ):
        assert recorded[key] == replayed[key], f"{key} diverged on replay"

    # Hit markers flip to True on the LLM paths (HTTP paths don't
    # annotate usage, they just return cached data).
    assert replayed["triage_usage_hit"] is True
    assert replayed["invalidity_usage_hit"] is True
    assert recorded["triage_usage_hit"] is False
    assert recorded["invalidity_usage_hit"] is False


@pytest.mark.asyncio
async def test_replay_missing_key_raises(tmp_path: Path) -> None:
    """If the replay asks for a key not in the recorded cache, we fail
    loudly rather than silently hitting live. Protects against drift
    between the code that made the original call and the replay."""
    # Record a partial cache (just pubchem, no LLM).
    rec = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
    set_current_cache(rec)
    await _fake_pubchem_call(rec, cid=2244)
    assert len(rec) == 1

    # Now try to replay the full pipeline — triage isn't cached, must raise.
    set_current_cache(None)
    rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
    set_current_cache(rep)

    with pytest.raises(CacheMissError):
        await _run_synthetic_pipeline(compound="aspirin", cid=2244)


@pytest.mark.asyncio
async def test_replay_then_record_hybrid(tmp_path: Path) -> None:
    """REPLAY_THEN_RECORD: existing keys return cached; new keys fall
    through to live and get persisted. Incremental re-runs can extend a
    cache without discarding it."""
    # First run records one call.
    rec = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
    set_current_cache(rec)
    await _fake_pubchem_call(rec, cid=2244)
    assert len(rec) == 1

    # Now in hybrid mode, run the full synthetic pipeline. The pubchem
    # call should hit the existing cache; the rest should record fresh.
    set_current_cache(None)
    hybrid = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
    set_current_cache(hybrid)

    result = await _run_synthetic_pipeline(compound="aspirin", cid=2244)
    assert result["pubchem_synonyms"] == ["compound-2244", "c-2244"]

    # Cache now has all 4 entries.
    assert len(hybrid) == 4
    sources = {json.loads(line)["source"] for line in hybrid.cache_path.read_text().splitlines()}
    assert sources == {"pubchem", "lens", "claude:triage", "claude:invalidity"}


@pytest.mark.asyncio
async def test_different_compound_produces_different_cache_entries(tmp_path: Path) -> None:
    """Each unique input variant keys to a distinct entry, but downstream
    calls that receive identical inputs deduplicate — that's a feature,
    not a bug: it means replay can share cached sub-computations across
    compounds that happen to hit the same patent."""
    rec = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
    set_current_cache(rec)

    await _run_synthetic_pipeline(compound="aspirin", cid=2244)
    await _run_synthetic_pipeline(compound="ibuprofen", cid=3672)

    # Expected entries:
    #   2 x pubchem (different CIDs)
    #   2 x lens (different queries)
    #   2 x triage (different compound names in the user prompt)
    #   1 x invalidity (both runs' triage returns the same patent_id in
    #                   the fake - so the invalidity input matches and
    #                   the cache dedupes correctly)
    # = 7 total. The invalidity dedup is the intended behaviour.
    assert len(rec) == 7
    # But the "unique" part of the test: at least one call did differ.
    sources = [json.loads(line)["source"] for line in rec.cache_path.read_text().splitlines()]
    assert sources.count("pubchem") == 2
    assert sources.count("lens") == 2
    assert sources.count("claude:triage") == 2
    assert sources.count("claude:invalidity") == 1


@pytest.mark.asyncio
async def test_llm_replay_usage_shows_cached_original(tmp_path: Path) -> None:
    """Replay usage dict carries the original run's token counts under
    ``cached_original`` so the manifest can audit what the original run
    spent without the replay pretending to have spent anything itself."""
    rec = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
    set_current_cache(rec)
    _triage, orig_usage = await _fake_llm_triage(compound_name="aspirin")
    assert orig_usage == {"input_tokens": 850, "output_tokens": 120}

    set_current_cache(None)
    rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
    set_current_cache(rep)

    _triage2, replay_usage = await _fake_llm_triage(compound_name="aspirin")

    assert replay_usage["input_tokens"] == 0
    assert replay_usage["output_tokens"] == 0
    assert replay_usage["replay_cache_hit"] is True
    assert replay_usage["cached_original"] == {
        "input_tokens": 850,
        "output_tokens": 120,
    }


@pytest.mark.asyncio
async def test_cache_digest_is_manifest_safe(tmp_path: Path) -> None:
    """Two runs that touched the same logical calls in different orders
    produce the same ``cache.digest()`` — so the digest is safe to pin
    in the manifest as a drift-detection signal."""
    # Run A: compound-first order.
    rec_a = ResponseCache(cache_dir=tmp_path / "a", mode=CacheMode.RECORD)
    set_current_cache(rec_a)
    await _fake_pubchem_call(rec_a, 2244)
    await _fake_lens_call(rec_a, {"query": "aspirin"})
    digest_a = rec_a.digest()

    # Run B: reverse order.
    set_current_cache(None)
    rec_b = ResponseCache(cache_dir=tmp_path / "b", mode=CacheMode.RECORD)
    set_current_cache(rec_b)
    await _fake_lens_call(rec_b, {"query": "aspirin"})
    await _fake_pubchem_call(rec_b, 2244)
    digest_b = rec_b.digest()

    assert digest_a == digest_b


@pytest.mark.asyncio
async def test_cache_digest_changes_when_input_changes(tmp_path: Path) -> None:
    """Inverse guarantee: a run that calls a different URL must produce
    a different digest — so drift is detectable."""
    rec_a = ResponseCache(cache_dir=tmp_path / "a", mode=CacheMode.RECORD)
    set_current_cache(rec_a)
    await _fake_pubchem_call(rec_a, 2244)
    digest_a = rec_a.digest()

    set_current_cache(None)
    rec_b = ResponseCache(cache_dir=tmp_path / "b", mode=CacheMode.RECORD)
    set_current_cache(rec_b)
    await _fake_pubchem_call(rec_b, 9999)  # different CID
    digest_b = rec_b.digest()

    assert digest_a != digest_b


@pytest.mark.asyncio
async def test_concurrent_pipeline_runs_are_isolated(tmp_path: Path) -> None:
    """Two concurrent pipeline runs against the same cache should not
    corrupt each other's cache entries. The cache uses a threading.Lock
    internally; this test exercises the async/concurrent path."""
    rec = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
    set_current_cache(rec)

    results = await asyncio.gather(
        _run_synthetic_pipeline(compound="aspirin", cid=2244),
        _run_synthetic_pipeline(compound="aspirin", cid=2244),  # identical
        _run_synthetic_pipeline(compound="ibuprofen", cid=3672),  # different
    )

    # All three runs return coherent results.
    assert all(r["compound"] in {"aspirin", "ibuprofen"} for r in results)

    # Cache entries under concurrency:
    #   4 for aspirin (both aspirin runs share identical keys → dedupe)
    #   + 3 more for ibuprofen (pubchem, lens, triage differ; invalidity
    #     collides with aspirin's because both fake-triage functions
    #     return the same patent_id, dedupes correctly).
    # = 7 total. Concurrent writes do not corrupt the cache: the
    # threading.Lock inside ResponseCache.wrap serialises the append.
    assert len(rec) == 7


@pytest.mark.asyncio
async def test_cache_file_disk_format_is_one_json_per_line(tmp_path: Path) -> None:
    """The cache file must be valid JSONL — each line independently
    parseable. Protects against partial writes corrupting the whole
    cache in the next load."""
    rec = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
    set_current_cache(rec)
    await _run_synthetic_pipeline(compound="aspirin", cid=2244)

    text = rec.cache_path.read_text("utf-8")
    lines = text.strip().splitlines()
    # Each line must parse as JSON independently.
    for line in lines:
        parsed = json.loads(line)
        assert set(parsed.keys()) >= {"key", "source", "method", "url", "response"}


# ---------------------------------------------------------------------------
# Regression guards
# ---------------------------------------------------------------------------


def test_cache_entry_is_serialisable() -> None:
    """CacheEntry must serialise to a plain dict compatible with the
    JSONL format the ResponseCache reads on load. A dataclass / Pydantic
    shift that breaks this would silently corrupt replay."""
    entry = CacheEntry(
        key="abc",
        source="pubchem",
        method="GET",
        url="/cid/1",
        response={"cid": 1, "synonyms": ["x"]},
        meta={"status": 200},
    )
    # Round-trip through JSON.
    blob = json.dumps(
        {
            "key": entry.key,
            "source": entry.source,
            "method": entry.method,
            "url": entry.url,
            "response": entry.response,
            "meta": entry.meta,
        }
    )
    back = json.loads(blob)
    assert back["source"] == "pubchem"
    assert back["response"] == {"cid": 1, "synonyms": ["x"]}


def test_compute_request_key_is_64_hex() -> None:
    """Key format is sha256 hex — 64 chars. A stray non-hex byte would
    corrupt file paths or grep-based tooling downstream."""
    key = compute_request_key(source="pubchem", method="GET", url="/x", body=None)
    assert len(key) == 64
    int(key, 16)  # raises if non-hex
