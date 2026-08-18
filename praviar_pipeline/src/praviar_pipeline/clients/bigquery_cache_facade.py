"""Lazy cache facade for the BigQuery client."""

from __future__ import annotations

from praviar_pipeline.clients.bigquery_cache import BigQueryCache
from praviar_pipeline.config import get_settings


class BigQueryCacheFacade:
    """Lazily create and hold the cache instance used by BigQueryClient."""

    def __init__(self) -> None:
        self._cache_instance: BigQueryCache | None = None
        self._cache_checked = False

    def get_cache(self) -> BigQueryCache | None:
        """Return the cache instance when caching is enabled."""
        if not self._cache_checked:
            self._cache_checked = True
            settings = get_settings()
            if settings.bigquery_cache_enabled:
                self._cache_instance = BigQueryCache(
                    cache_dir=settings.bigquery_cache_dir,
                    ttl_days=settings.bigquery_cache_ttl_days,
                )
        return self._cache_instance
