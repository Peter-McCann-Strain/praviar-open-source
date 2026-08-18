"""Patent-metadata query implementations for the BigQuery patent client."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from praviar_pipeline.clients.bigquery_helpers import build_job_config, rows_to_dicts


async def get_patent_claims_batch_query(
    *,
    client,
    settings,
    patent_ids: list[str],
) -> dict[str, str]:
    from google.cloud.bigquery import ArrayQueryParameter, QueryJobConfig

    sql = """
        SELECT
            p.publication_number,
            claims.text AS claims_text
        FROM
            `patents-public-data.patents.publications` p,
            UNNEST(p.claims_localized) AS claims
        WHERE
            p.publication_number IN UNNEST(@patent_ids)
            AND claims.language = 'en'
    """

    job_config = build_job_config(
        query_parameters=[
            ArrayQueryParameter("patent_ids", "STRING", patent_ids),
        ],
        maximum_bytes_billed=settings.bigquery_max_bytes_billed,
        query_job_config_cls=QueryJobConfig,
    )
    rows = await asyncio.to_thread(client.query_and_wait, sql, job_config=job_config)
    result: dict[str, str] = {}
    for row in rows:
        pub_num = row.get("publication_number", "")
        if pub_num and pub_num not in result:
            result[pub_num] = row.get("claims_text", "")
    return result


async def get_examiner_citations_batch_query(
    *,
    client,
    settings,
    patent_ids: list[str],
) -> dict[str, dict[str, list[str]]]:
    from google.cloud.bigquery import ArrayQueryParameter, QueryJobConfig

    sql = """
        SELECT
            p.publication_number,
            citation.publication_number AS cited_patent,
            citation.category AS citation_category
        FROM
            `patents-public-data.patents.publications` p,
            UNNEST(p.citation) AS citation
        WHERE
            p.publication_number IN UNNEST(@patent_ids)
            AND citation.publication_number IS NOT NULL
    """

    job_config = build_job_config(
        query_parameters=[
            ArrayQueryParameter("patent_ids", "STRING", patent_ids),
        ],
        maximum_bytes_billed=settings.bigquery_max_bytes_billed,
        query_job_config_cls=QueryJobConfig,
    )
    rows = await asyncio.to_thread(client.query_and_wait, sql, job_config=job_config)

    result: dict[str, dict[str, list[str]]] = {}
    for row in rows:
        pub_num = row.get("publication_number", "")
        if pub_num not in result:
            result[pub_num] = {"examiner": [], "applicant": []}
        cited = row.get("cited_patent", "")
        category = str(row.get("citation_category", "")).lower()
        if category in {"sea", "oth"}:
            result[pub_num]["examiner"].append(cited)
        else:
            result[pub_num]["applicant"].append(cited)
    return result


async def get_patent_metadata_batch_query(
    *,
    client,
    settings,
    patent_ids: list[str],
) -> list[dict[str, Any]]:
    from google.cloud.bigquery import ArrayQueryParameter, QueryJobConfig

    sql = """
        SELECT
            p.publication_number,
            (SELECT t.text FROM UNNEST(p.title_localized) AS t
             WHERE t.language = 'en' LIMIT 1) AS title,
            (SELECT a.text FROM UNNEST(p.abstract_localized) AS a
             WHERE a.language = 'en' LIMIT 1) AS abstract,
            p.filing_date,
            p.grant_date,
            p.priority_date,
            p.assignee_harmonized,
            p.inventor_harmonized
        FROM
            `patents-public-data.patents.publications` p
        WHERE
            p.publication_number IN UNNEST(@patent_ids)
    """

    job_config = build_job_config(
        query_parameters=[
            ArrayQueryParameter("patent_ids", "STRING", patent_ids),
        ],
        maximum_bytes_billed=settings.bigquery_max_bytes_billed,
        query_job_config_cls=QueryJobConfig,
    )
    rows = await asyncio.to_thread(client.query_and_wait, sql, job_config=job_config)
    return rows_to_dicts(rows)


async def get_patent_full_text_query(
    *,
    client,
    settings,
    patent_id: str,
) -> str:
    from google.cloud.bigquery import QueryJobConfig, ScalarQueryParameter

    sql = """
        SELECT
            description.text AS description_text
        FROM
            `patents-public-data.patents.publications` p,
            UNNEST(p.description_localized) AS description
        WHERE
            p.publication_number = @patent_id
            AND description.language = 'en'
        LIMIT 1
    """

    job_config = build_job_config(
        query_parameters=[
            ScalarQueryParameter("patent_id", "STRING", patent_id),
        ],
        maximum_bytes_billed=settings.bigquery_max_bytes_billed,
        query_job_config_cls=QueryJobConfig,
    )
    rows = await asyncio.to_thread(client.query_and_wait, sql, job_config=job_config)
    for row in rows:
        return cast("str", row.get("description_text", ""))
    return ""
