"""Wiring tests: BigQueryClient ↔ ResponseCache.

The BigQuery client has two layers of caching:

* ``BigQueryCacheFacade`` — file-backed result cache used to avoid
  re-paying for scans when the same SQL repeats across runs.
* ``ResponseCache`` — the pipeline-scoped cache under test, which
  captures the logical call signature (function name + kwargs) so
  replays are byte-identical regardless of BigQuery availability.

The two are independent. These tests wrap at the
``_run_search`` / ``_run_query`` boundary, so the response cache sees
each logical call once and returns its result on replay without
touching BigQuery at all.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from praviar_pipeline.clients.bigquery import BigQueryClient
from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.response_cache import (
    CacheMissError,
    CacheMode,
    ResponseCache,
    compute_request_key,
    set_current_cache,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _clear_cache_singleton():
    set_current_cache(None)
    yield
    set_current_cache(None)


@pytest.fixture
def bq_client(mock_settings) -> BigQueryClient:
    """BigQueryClient with its underlying BigQuery SDK stubbed out.

    We don't want to actually connect to Google. The tests patch the
    module-level helpers that run the operation so the response cache
    layer is the only thing exercised.
    """
    client = BigQueryClient()
    # Avoid creating a real google-bigquery client.
    client._ensure_client = lambda: object()  # type: ignore[assignment]
    return client


# ---------------------------------------------------------------------------
# RECORD
# ---------------------------------------------------------------------------


class TestRecord:
    async def test_record_captures_first_observation_only(
        self, bq_client: BigQueryClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        call_count = 0

        async def fake_op(**kwargs):
            nonlocal call_count
            call_count += 1
            return [{"patent_id": "US1234567B2"}]

        with patch(
            "praviar_pipeline.clients.bigquery.run_bigquery_search_operation",
            side_effect=fake_op,
        ):
            first = await bq_client._run_search(
                impl_fn=None, search_fn=lambda: None, synonyms=["aspirin"]
            )
            second = await bq_client._run_search(
                impl_fn=None, search_fn=lambda: None, synonyms=["aspirin"]
            )

        assert first == second == [{"patent_id": "US1234567B2"}]
        assert call_count == 2  # RECORD always calls through
        lines = cache.cache_path.read_text("utf-8").strip().splitlines()
        assert len(lines) == 1
        assert '"source": "bigquery"' in lines[0]

    async def test_replay_then_record_serves_second_call_from_cache(
        self, bq_client: BigQueryClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        call_count = 0

        async def fake_op(**kwargs):
            nonlocal call_count
            call_count += 1
            return {"US9999": "claims text"}

        with patch(
            "praviar_pipeline.clients.bigquery.run_bigquery_query_operation",
            side_effect=fake_op,
        ):
            await bq_client._run_query(impl_fn=None, query_fn=lambda: None, patent_ids=["US9999"])
            await bq_client._run_query(impl_fn=None, query_fn=lambda: None, patent_ids=["US9999"])

        assert call_count == 1

    async def test_different_kwargs_produce_different_keys(
        self, bq_client: BigQueryClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY_THEN_RECORD)
        set_current_cache(cache)

        call_count = 0

        async def fake_op(**kwargs):
            nonlocal call_count
            call_count += 1
            return []

        search_fn = lambda: None  # noqa: E731
        search_fn.__name__ = "search_patents_by_compound_cached"  # type: ignore[attr-defined]

        with patch(
            "praviar_pipeline.clients.bigquery.run_bigquery_search_operation",
            side_effect=fake_op,
        ):
            await bq_client._run_search(impl_fn=None, search_fn=search_fn, synonyms=["aspirin"])
            await bq_client._run_search(
                impl_fn=None, search_fn=search_fn, synonyms=["aspirin"]
            )  # hit
            await bq_client._run_search(
                impl_fn=None, search_fn=search_fn, synonyms=["ibuprofen"]
            )  # distinct

        assert call_count == 2
        assert len(cache) == 2


# ---------------------------------------------------------------------------
# REPLAY
# ---------------------------------------------------------------------------


class TestReplay:
    async def test_replay_hit_skips_bigquery(
        self, bq_client: BigQueryClient, tmp_path: Path
    ) -> None:
        # Record
        rec = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(rec)
        payload = [{"patent_id": "US1234567B2"}]

        async def fake_op(**kwargs):
            return payload

        search_fn = lambda: None  # noqa: E731
        search_fn.__name__ = "search_patents_by_compound_cached"  # type: ignore[attr-defined]

        with patch(
            "praviar_pipeline.clients.bigquery.run_bigquery_search_operation",
            side_effect=fake_op,
        ):
            await bq_client._run_search(impl_fn=None, search_fn=search_fn, synonyms=["aspirin"])

        # Replay
        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)

        async def explode(**kwargs):
            raise AssertionError("live call in replay mode")

        with patch(
            "praviar_pipeline.clients.bigquery.run_bigquery_search_operation",
            side_effect=explode,
        ):
            result = await bq_client._run_search(
                impl_fn=None, search_fn=search_fn, synonyms=["aspirin"]
            )
        assert result == payload

    async def test_replay_miss_raises_cache_miss_error(
        self, bq_client: BigQueryClient, tmp_path: Path
    ) -> None:
        rep = ResponseCache(cache_dir=tmp_path, mode=CacheMode.REPLAY)
        set_current_cache(rep)

        async def explode(**kwargs):
            raise AssertionError("live call in replay mode")

        search_fn = lambda: None  # noqa: E731
        search_fn.__name__ = "search_patents_by_compound_cached"  # type: ignore[attr-defined]

        with (
            patch(
                "praviar_pipeline.clients.bigquery.run_bigquery_search_operation",
                side_effect=explode,
            ),
            pytest.raises(CacheMissError) as excinfo,
        ):
            await bq_client._run_search(impl_fn=None, search_fn=search_fn, synonyms=["missing"])

        expected_body = json.dumps({"synonyms": ["missing"]}, sort_keys=True, default=str)
        expected_key = compute_request_key(
            source="bigquery",
            method="POST",
            url="search_patents_by_compound_cached",
            body=expected_body,
        )
        assert excinfo.value.key == expected_key


# ---------------------------------------------------------------------------
# DISABLED / no cache installed
# ---------------------------------------------------------------------------


class TestPassthrough:
    async def test_disabled_mode_is_pure_passthrough(
        self, bq_client: BigQueryClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.DISABLED)
        set_current_cache(cache)

        call_count = 0

        async def fake_op(**kwargs):
            nonlocal call_count
            call_count += 1
            return []

        with patch(
            "praviar_pipeline.clients.bigquery.run_bigquery_search_operation",
            side_effect=fake_op,
        ):
            await bq_client._run_search(impl_fn=None, search_fn=lambda: None, synonyms=["x"])
            await bq_client._run_search(impl_fn=None, search_fn=lambda: None, synonyms=["x"])
        assert call_count == 2
        assert len(cache) == 0
        assert not cache.cache_path.exists()

    async def test_no_cache_installed_passthrough(self, bq_client: BigQueryClient) -> None:
        call_count = 0

        async def fake_op(**kwargs):
            nonlocal call_count
            call_count += 1
            return []

        with patch(
            "praviar_pipeline.clients.bigquery.run_bigquery_search_operation",
            side_effect=fake_op,
        ):
            await bq_client._run_search(impl_fn=None, search_fn=lambda: None, synonyms=["x"])
            await bq_client._run_search(impl_fn=None, search_fn=lambda: None, synonyms=["x"])
        assert call_count == 2


# ---------------------------------------------------------------------------
# Error propagation + retry semantics + key isolation
# ---------------------------------------------------------------------------


class TestErrorsAndRetries:
    async def test_exception_is_not_recorded(
        self, bq_client: BigQueryClient, tmp_path: Path
    ) -> None:
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        async def fake_op(**kwargs):
            raise SourceUnavailableError("bigquery", "boom")

        with (
            patch(
                "praviar_pipeline.clients.bigquery.run_bigquery_search_operation",
                side_effect=fake_op,
            ),
            pytest.raises(SourceUnavailableError),
        ):
            await bq_client._run_search(impl_fn=None, search_fn=lambda: None, synonyms=["boom"])

        assert len(cache) == 0
        assert not cache.cache_path.exists() or cache.cache_path.read_text("utf-8") == ""

    async def test_retry_on_search_patents_by_compound_records_one_entry_on_success(
        self, bq_client: BigQueryClient, tmp_path: Path
    ) -> None:
        """search_patents_by_compound has its own @retry(3) decorator around
        _run_search; on eventual success the cache sees exactly one recorded
        entry — retries are below the cache boundary.
        """
        cache = ResponseCache(cache_dir=tmp_path, mode=CacheMode.RECORD)
        set_current_cache(cache)

        attempt = 0

        async def fake_op(**kwargs):
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                raise SourceUnavailableError("bigquery", "transient")
            return [{"patent_id": "US1234567B2"}]

        with (
            patch(
                "praviar_pipeline.clients.bigquery.wait_exponential_jitter",
                return_value=lambda *_a, **_kw: 0,
            ),
            patch(
                "praviar_pipeline.clients.bigquery.run_bigquery_search_operation",
                side_effect=fake_op,
            ),
        ):
            result = await bq_client.search_patents_by_compound(synonyms=["x"])

        assert attempt == 3
        assert result == [{"patent_id": "US1234567B2"}]
        # Two failed attempts produced no recorded entry; one successful
        # attempt recorded exactly one entry.
        assert len(cache) == 1

    async def test_different_source_does_not_collide_with_bigquery_key(self) -> None:
        body = json.dumps({"synonyms": ["x"]}, sort_keys=True, default=str)
        bq_key = compute_request_key(
            source="bigquery",
            method="POST",
            url="search_patents_by_compound_cached",
            body=body,
        )
        lens_key = compute_request_key(
            source="lens",
            method="POST",
            url="search_patents_by_compound_cached",
            body=body,
        )
        assert bq_key != lens_key
