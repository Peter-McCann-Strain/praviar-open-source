"""File-based cache for BigQuery search results.

Caches query results as JSON files keyed by a SHA-256 hash of the
query method name and its parameters. This avoids redundant BigQuery
scans when the same compound is analyzed multiple times (e.g., during
benchmarks or re-runs).
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, cast

import structlog

from praviar_pipeline.utils.private_artifacts import (
    atomic_write_text,
    ensure_private_directory,
    private_file_for_read,
)
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

logger = structlog.get_logger()


class BigQueryCache:
    """Simple file-based JSON cache with TTL expiration."""

    def __init__(self, cache_dir: str | Path, ttl_days: int = 7) -> None:
        self._dir = Path(cache_dir).expanduser()
        self._ttl_seconds = ttl_days * 86400
        ensure_private_directory(self._dir)

    def get(self, method: str, **params: Any) -> list[dict] | None:
        key = self._cache_key(method, **params)
        path = self._dir / f"{key}.json"
        if not path.exists():
            return None

        try:
            data = json.loads(private_file_for_read(path).read_text())
            if time.time() - data.get("ts", 0) > self._ttl_seconds:
                path.unlink(missing_ok=True)
                logger.debug("bigquery_cache_expired", method=method)
                return None
            logger.debug("bigquery_cache_hit", method=method)
            return cast("list[dict]", data["results"])
        except (json.JSONDecodeError, KeyError, OSError):
            path.unlink(missing_ok=True)
            return None

    def put(self, method: str, results: list[dict], **params: Any) -> None:
        key = self._cache_key(method, **params)
        path = self._dir / f"{key}.json"
        try:
            atomic_write_text(
                path,
                json.dumps(
                    {"ts": time.time(), "method": method, "results": results},
                    default=str,
                ),
            )
            logger.debug("bigquery_cache_stored", method=method, count=len(results))
        except OSError as exc:
            logger.warning(
                "bigquery_cache_write_failed",
                error_type=safe_exception_type(exc),
            )

    def clear(self) -> int:
        count = 0
        for f in self._dir.glob("*.json"):
            private_file_for_read(f).unlink(missing_ok=True)
            count += 1
        return count

    def _cache_key(self, method: str, **params: Any) -> str:
        canonical = json.dumps({"method": method, **params}, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()
