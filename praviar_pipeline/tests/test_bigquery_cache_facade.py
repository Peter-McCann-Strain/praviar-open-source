from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from praviar_pipeline.clients.bigquery_cache_facade import BigQueryCacheFacade


def test_cache_facade_builds_cache_once_when_enabled() -> None:
    settings = SimpleNamespace(
        bigquery_cache_enabled=True,
        bigquery_cache_dir="/tmp/bigquery-cache",
        bigquery_cache_ttl_days=7,
    )
    cache_instance = object()

    with (
        patch("praviar_pipeline.clients.bigquery_cache_facade.get_settings", return_value=settings),
        patch(
            "praviar_pipeline.clients.bigquery_cache_facade.BigQueryCache",
            return_value=cache_instance,
        ) as cache_cls,
    ):
        facade = BigQueryCacheFacade()
        assert facade.get_cache() is cache_instance
        assert facade.get_cache() is cache_instance

    cache_cls.assert_called_once_with(
        cache_dir="/tmp/bigquery-cache",
        ttl_days=7,
    )


def test_cache_facade_returns_none_when_disabled() -> None:
    settings = SimpleNamespace(
        bigquery_cache_enabled=False,
        bigquery_cache_dir="/tmp/bigquery-cache",
        bigquery_cache_ttl_days=7,
    )

    with (
        patch("praviar_pipeline.clients.bigquery_cache_facade.get_settings", return_value=settings),
        patch("praviar_pipeline.clients.bigquery_cache_facade.BigQueryCache") as cache_cls,
    ):
        facade = BigQueryCacheFacade()
        assert facade.get_cache() is None
        assert facade.get_cache() is None

    cache_cls.assert_not_called()
