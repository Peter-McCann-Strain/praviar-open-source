"""Fail-closed hybrid BigQuery patent retrieval.

The configured hybrid source combines indexed lexical ``SEARCH`` candidates
with ``VECTOR_SEARCH`` candidates using Reciprocal Rank Fusion (RRF). Hybrid
mode is an explicit retrieval contract: if its embedding schema or query
execution is unavailable, the source fails and Step 2 records the gap. It never
substitutes a different retrieval algorithm.
"""

from __future__ import annotations

import asyncio
import math
import re
from typing import TYPE_CHECKING, Any

import structlog

from praviar_pipeline.clients.bigquery_helpers import build_job_config
from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

log = structlog.get_logger(__name__)

_PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DATASET_OR_TABLE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,1023}$")


def _qualified_table(project: str, dataset: str, table: str) -> str:
    """Return a validated, fully-qualified BigQuery table identifier."""
    if _PROJECT_ID_PATTERN.fullmatch(project) is None:
        raise ValueError("Hybrid BigQuery project identifier is invalid")
    if _DATASET_OR_TABLE_PATTERN.fullmatch(dataset) is None:
        raise ValueError("Hybrid BigQuery dataset identifier is invalid")
    if _DATASET_OR_TABLE_PATTERN.fullmatch(table) is None:
        raise ValueError("Hybrid BigQuery table identifier is invalid")
    return f"`{project}.{dataset}.{table}`"


def _build_hybrid_sql(
    project: str,
    dataset: str,
    table: str,
    limit: int,
    rrf_k: int,
    *,
    query_term_count: int,
    filter_jurisdictions: bool,
) -> str:
    """Return parameterized indexed-lexical+dense RRF SQL."""
    if limit < 1:
        raise ValueError("Hybrid BigQuery result limit must be positive")
    if rrf_k < 1:
        raise ValueError("Hybrid BigQuery RRF constant must be positive")
    if query_term_count < 1:
        raise ValueError("Hybrid BigQuery requires at least one query term")

    fq_table = _qualified_table(project, dataset, table)
    search_clause = " OR ".join(
        f"SEARCH(patents, @query_term_{index})" for index in range(query_term_count)
    )
    lexical_score = " + ".join(
        (f"COALESCE(CAST(SEARCH(patents, @query_term_{index}) AS INT64), 0)")
        for index in range(query_term_count)
    )
    bm25_jurisdiction_clause = (
        "\n    AND jurisdiction IN UNNEST(@jurisdictions)" if filter_jurisdictions else ""
    )
    output_jurisdiction_clause = (
        "\nWHERE p.jurisdiction IN UNNEST(@jurisdictions)" if filter_jurisdictions else ""
    )
    vector_base_table = (
        f"""(
      SELECT *
      FROM {fq_table}
      WHERE jurisdiction IN UNNEST(@jurisdictions)
    )"""
        if filter_jurisdictions
        else f"TABLE {fq_table}"
    )

    return f"""
WITH lexical_scored AS (
  SELECT patent_number,
         {lexical_score} AS lexical_score
  FROM {fq_table}
  WHERE ({search_clause}){bm25_jurisdiction_clause}
),
sparse AS (
  SELECT patent_number,
         ROW_NUMBER() OVER (
           ORDER BY lexical_score DESC, patent_number ASC
         ) AS sparse_rank
  FROM lexical_scored
  ORDER BY lexical_score DESC, patent_number ASC
  LIMIT {limit}
),
dense AS (
  SELECT base.patent_number,
         ROW_NUMBER() OVER (
           ORDER BY distance ASC, base.patent_number ASC
         ) AS dense_rank
  FROM VECTOR_SEARCH(
    {vector_base_table},
    'embedding',
    (SELECT @query_embedding AS embedding),
    top_k => {limit},
    distance_type => 'COSINE'
  )
),
fused AS (
  SELECT
    COALESCE(s.patent_number, d.patent_number)              AS patent_number,
    COALESCE(1.0 / ({rrf_k} + s.sparse_rank),  0.0) +
    COALESCE(1.0 / ({rrf_k} + d.dense_rank), 0.0)          AS rrf_score
  FROM sparse s FULL OUTER JOIN dense d USING (patent_number)
)
SELECT
  f.patent_number AS publication_number,
  f.rrf_score,
  p.title,
  p.abstract,
  p.assignee AS assignee_harmonized,
  p.filing_date,
  p.expiry_date,
  p.jurisdiction,
  p.classification AS cpc_codes
FROM fused f
JOIN {fq_table} p USING (patent_number){output_jurisdiction_clause}
ORDER BY f.rrf_score DESC, f.patent_number ASC
LIMIT {limit}
"""


def _row_value(row: Any, field: str, default: Any = None) -> Any:
    try:
        return row[field]
    except (KeyError, TypeError):
        return default


def _search_phrase(term: str) -> str:
    """Encode one configured term as a safe BigQuery SEARCH phrase."""
    escaped = term.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _row_to_canonical_bigquery_row(row: Any) -> dict[str, Any]:
    """Normalize one hybrid result to the Step 2 BigQuery row contract."""
    publication_number = str(_row_value(row, "publication_number", "") or "").strip()
    if not publication_number:
        raise ValueError("Hybrid BigQuery row is missing publication_number")

    raw_score = _row_value(row, "rrf_score", None)
    try:
        rrf_score = float(raw_score)
    except (TypeError, ValueError):
        raise ValueError("Hybrid BigQuery row has an invalid rrf_score") from None
    if not math.isfinite(rrf_score) or rrf_score < 0:
        raise ValueError("Hybrid BigQuery row has an invalid rrf_score")

    raw_assignees = _row_value(row, "assignee_harmonized", [])
    if isinstance(raw_assignees, list):
        assignees = raw_assignees
    elif raw_assignees:
        assignees = [str(raw_assignees)]
    else:
        assignees = []

    raw_cpc_codes = _row_value(row, "cpc_codes", [])
    if isinstance(raw_cpc_codes, list):
        cpc_codes = [str(code) for code in raw_cpc_codes if code]
    elif raw_cpc_codes:
        cpc_codes = [str(raw_cpc_codes)]
    else:
        cpc_codes = []

    return {
        "publication_number": publication_number,
        "title": str(_row_value(row, "title", "") or ""),
        "abstract": str(_row_value(row, "abstract", "") or ""),
        "filing_date": _row_value(row, "filing_date", None),
        "priority_date": None,
        "expiry_date": _row_value(row, "expiry_date", None),
        "assignee_harmonized": assignees,
        "inventor_harmonized": [],
        "cpc_codes": cpc_codes,
        "jurisdiction": str(_row_value(row, "jurisdiction", "") or ""),
        "rrf_score": rrf_score,
    }


def _validated_query_vector(values: Sequence[float]) -> list[float]:
    vector: list[float] = []
    for value in values:
        if isinstance(value, bool):
            raise ValueError("Hybrid query embedding contains a non-numeric value")
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            raise ValueError("Hybrid query embedding contains a non-numeric value") from None
        if not math.isfinite(numeric):
            raise ValueError("Hybrid query embedding contains a non-finite value")
        vector.append(numeric)
    if not vector:
        raise ValueError("Hybrid query embedding is empty")
    return vector


async def search_bigquery_hybrid(
    *,
    client: Any,
    settings: Any,
    query_terms: list[str],
    jurisdictions: list[str] | None,
    project: str,
    dataset: str,
    table: str,
    limit: int = 200,
    rrf_k: int = 60,
    embed_fn: Callable[[str], list[float]] | None = None,
) -> list[dict[str, Any]]:
    """Execute one hybrid query and return canonical Step 2 rows.

    Any embedding, schema, query, or row-contract failure is surfaced as
    :class:`SourceUnavailableError`; hybrid mode never retries with a different
    retrieval algorithm.
    """
    from google.cloud import bigquery as bq

    from praviar_pipeline.utils.specter2_embeddings import embed_patent_query

    cleaned_terms = list(dict.fromkeys(term.strip() for term in query_terms if term.strip()))
    if not cleaned_terms:
        return []
    cleaned_jurisdictions = list(
        dict.fromkeys(
            jurisdiction.strip().upper()
            for jurisdiction in jurisdictions or []
            if jurisdiction.strip()
        )
    )
    if embed_fn is None:
        embed_fn = embed_patent_query

    log.info(
        "hybrid_bigquery_search_start",
        dataset=dataset,
        table=table,
        query_term_count=len(cleaned_terms),
        jurisdiction_count=len(cleaned_jurisdictions),
        limit=limit,
        rrf_k=rrf_k,
    )

    try:
        embedding_text = " ; ".join(cleaned_terms)
        query_vector = _validated_query_vector(await asyncio.to_thread(embed_fn, embedding_text))
        sql = _build_hybrid_sql(
            project=project,
            dataset=dataset,
            table=table,
            limit=limit,
            rrf_k=rrf_k,
            query_term_count=len(cleaned_terms),
            filter_jurisdictions=bool(cleaned_jurisdictions),
        )
        query_parameters = [
            *[
                bq.ScalarQueryParameter(
                    f"query_term_{index}",
                    "STRING",
                    _search_phrase(term),
                )
                for index, term in enumerate(cleaned_terms)
            ],
            bq.ArrayQueryParameter("query_embedding", "FLOAT64", query_vector),
        ]
        if cleaned_jurisdictions:
            query_parameters.append(
                bq.ArrayQueryParameter(
                    "jurisdictions",
                    "STRING",
                    cleaned_jurisdictions,
                )
            )
        job_config = build_job_config(
            query_parameters=query_parameters,
            maximum_bytes_billed=settings.bigquery_max_bytes_billed,
            query_job_config_cls=bq.QueryJobConfig,
        )
        results = await asyncio.to_thread(
            client.query_and_wait,
            sql,
            job_config=job_config,
        )
        rows = [_row_to_canonical_bigquery_row(row) for row in results]
    except Exception as exc:
        log.error(
            "hybrid_bigquery_search_failed",
            error_type=safe_exception_type(exc),
        )
        raise SourceUnavailableError("bigquery", "hybrid patent search failed") from None

    log.info("hybrid_bigquery_search_complete", hits=len(rows))
    return rows
