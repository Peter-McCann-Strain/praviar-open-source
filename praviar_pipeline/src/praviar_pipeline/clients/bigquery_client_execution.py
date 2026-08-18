"""Execution helpers for the BigQuery client facade."""

from __future__ import annotations


async def run_bigquery_search_operation(
    *,
    ensure_client_fn,
    settings_fn,
    cache_facade,
    impl_fn,
    search_fn,
    **kwargs,
):
    return await impl_fn(
        ensure_client_fn=ensure_client_fn,
        settings_fn=settings_fn,
        cache_facade=cache_facade,
        search_fn=search_fn,
        **kwargs,
    )


async def run_bigquery_query_operation(
    *,
    ensure_client_fn,
    settings_fn,
    impl_fn,
    query_fn,
    **kwargs,
):
    return await impl_fn(
        ensure_client_fn=ensure_client_fn,
        settings_fn=settings_fn,
        query_fn=query_fn,
        **kwargs,
    )
