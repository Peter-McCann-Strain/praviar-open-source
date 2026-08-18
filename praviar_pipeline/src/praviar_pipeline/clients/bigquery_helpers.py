"""Shared helpers for the BigQuery patent client."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def build_scalar_conditions(
    values: list[str],
    *,
    limit: int,
    param_prefix: str,
    condition_builder,
    value_builder,
    scalar_query_parameter_cls,
) -> tuple[list[str], list[Any]]:
    """Build repeated scalar query conditions and their query parameters."""
    if len(values) > limit:
        logger.warning(
            "build_scalar_conditions_truncated",
            total=len(values),
            limit=limit,
        )
    conditions: list[str] = []
    query_parameters: list[Any] = []
    for index, value in enumerate(values[:limit]):
        param_name = f"{param_prefix}_{index}"
        conditions.append(condition_builder(param_name))
        query_parameters.append(
            scalar_query_parameter_cls(param_name, "STRING", value_builder(value))
        )
    return conditions, query_parameters


def build_job_config(
    *,
    query_parameters: list[Any],
    maximum_bytes_billed: int,
    query_job_config_cls,
):
    """Create a BigQuery QueryJobConfig with the shared byte limit."""
    return query_job_config_cls(
        query_parameters=query_parameters,
        maximum_bytes_billed=maximum_bytes_billed,
    )


def rows_to_dicts(rows) -> list[dict[str, Any]]:
    """Normalize BigQuery rows into plain dictionaries."""
    return [dict(row) for row in rows]


def get_cached_result(cache, cache_key: str, **cache_kwargs):
    """Return a cached payload when cache support is enabled."""
    if not cache:
        return None
    return cache.get(cache_key, **cache_kwargs)


def put_cached_result(cache, cache_key: str, results, **cache_kwargs) -> None:
    """Store a payload when cache support is enabled."""
    if cache:
        cache.put(cache_key, results, **cache_kwargs)
