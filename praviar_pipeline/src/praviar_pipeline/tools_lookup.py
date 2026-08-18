"""Lookup-oriented handlers for the Claude-facing FTO tools."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import structlog

from praviar_pipeline.config import get_settings
from praviar_pipeline.tools_cache import format_cached_patent_lookup

logger = structlog.get_logger()


async def handle_get_current_date(_input: dict) -> str:
    """Return current UTC date/time."""
    now = datetime.now(tz=UTC)
    return (
        f"Current date: {now.strftime('%B %d, %Y')} ({now.strftime('%Y-%m-%d')}) UTC. "
        f"Current time: {now.strftime('%H:%M:%S')} UTC. "
        f"Year: {now.year}. "
        "Patents published up to and including this date are real and exist "
        "in public patent databases."
    )


async def handle_lookup_patent(
    input_data: dict,
    cache: dict[str, dict],
) -> str:
    """Look up patent metadata. Checks cache first, then BigQuery."""
    patent_id = input_data.get("patent_id", "").strip()
    if not patent_id:
        return "Error: patent_id is required."

    if patent_id in cache:
        settings = get_settings()
        return format_cached_patent_lookup(
            patent_id,
            cached=cache[patent_id],
            abstract_truncation=settings.tool_abstract_truncation,
            claims_truncation=settings.tool_claims_truncation,
        )

    try:
        from praviar_pipeline.clients.bigquery import BigQueryClient

        async with BigQueryClient() as bigquery_client:
            metadata = await _bigquery_patent_lookup(bigquery_client, patent_id)
            if metadata:
                cache[patent_id] = metadata
                return await handle_lookup_patent(input_data, cache)
    except Exception:
        logger.warning(
            "tool_lookup_patent_bigquery_failed",
        )

    return (
        f"Patent {patent_id} not found in available databases. "
        "This does not mean the patent doesn't exist — it may not be "
        "indexed in Google Patents BigQuery."
    )


async def _bigquery_patent_lookup(
    bigquery_client: Any,
    patent_id: str,
) -> dict | None:
    """Fetch patent metadata from BigQuery by publication number."""
    from google.cloud import bigquery as bq_lib

    settings = get_settings()
    client = bigquery_client.get_client()

    sql = """
        SELECT
            p.publication_number,
            title.text AS title,
            abstract.text AS abstract,
            p.filing_date,
            p.grant_date,
            p.priority_date,
            p.assignee_harmonized
        FROM
            `patents-public-data.patents.publications` p,
            UNNEST(p.title_localized) AS title,
            UNNEST(p.abstract_localized) AS abstract
        WHERE
            p.publication_number = @patent_id
            AND title.language = 'en'
            AND abstract.language = 'en'
        LIMIT 1
    """

    job_config = bq_lib.QueryJobConfig(
        query_parameters=[
            bq_lib.ScalarQueryParameter("patent_id", "STRING", patent_id),
        ],
        maximum_bytes_billed=settings.bigquery_max_bytes_billed,
    )

    rows = await asyncio.to_thread(
        client.query_and_wait,
        sql,
        job_config=job_config,
    )
    for row in rows:
        row_dict = dict(row)
        assignees = row_dict.get("assignee_harmonized", [])
        assignee = ""
        if assignees and isinstance(assignees, list):
            first = assignees[0]
            assignee = first.get("name", "") if isinstance(first, dict) else str(first)
        if not assignee:
            logger.warning(
                "patent_missing_assignee",
            )

        return {
            "title": row_dict.get("title", ""),
            "abstract": row_dict.get("abstract", ""),
            "filing_date": str(row_dict.get("filing_date", "")),
            "grant_date": str(row_dict.get("grant_date", "")),
            "priority_date": str(row_dict.get("priority_date", "")),
            "assignee": assignee,
        }
    return None
