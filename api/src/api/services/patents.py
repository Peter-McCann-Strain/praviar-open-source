"""Business logic for patent browser endpoints."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.errors import APIError, problem_type_uri
from api.services.report_access import validate_report_publishability

logger = structlog.get_logger()

PATENT_RISK_SORT_EXPRESSION = """
            CASE lower(risk_level)
                WHEN 'high' THEN 3
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 1
                WHEN 'clear' THEN 0
                ELSE NULL
            END
"""

PATENT_LIBRARY_ORDER_BY: dict[str, str] = {
    "id-asc": "patent_id ASC",
    "id-desc": "patent_id DESC",
    "risk-desc": f"{PATENT_RISK_SORT_EXPRESSION} DESC NULLS LAST, patent_id ASC",
    "risk-asc": f"{PATENT_RISK_SORT_EXPRESSION} ASC NULLS LAST, patent_id ASC",
}
PATENT_RISK_SORTS = frozenset({"risk-desc", "risk-asc"})
PATENT_RISK_RESTRICTED_ERROR_TYPE = problem_type_uri("risk-ratings-restricted")
LIKE_ESCAPE_CHARACTER = "\\"

REPORT_STRUCTURAL_SQL_PREDICATE = """
              AND a.status = 'completed'
              AND a.report_data IS NOT NULL
              AND jsonb_typeof(a.report_data) = 'object'
              AND a.report_data <> '{}'::jsonb
              AND jsonb_typeof(a.report_data->'patent_analyses') = 'array'
              AND jsonb_typeof(a.report_data->'verification') = 'object'
              AND jsonb_typeof(a.report_data->'verification'->'checks') = 'array'
              AND jsonb_array_length(a.report_data->'verification'->'checks') > 0
              AND NOT EXISTS (
                  SELECT 1
                  FROM jsonb_array_elements(
                      a.report_data->'verification'->'checks'
                  ) AS verification_check(value)
                  WHERE COALESCE(
                      verification_check.value->'passed',
                      'false'::jsonb
                  ) <> 'true'::jsonb
              )
              AND COALESCE(
                  a.report_data->'verification'->'all_citations_valid',
                  'false'::jsonb
              ) = 'true'::jsonb
              AND COALESCE(
                  a.report_data->'verification'->'all_claims_grounded',
                  'false'::jsonb
              ) = 'true'::jsonb
              AND COALESCE(
                  a.report_data->'verification'->'all_entities_valid',
                  'false'::jsonb
              ) = 'true'::jsonb
              AND COALESCE(
                  a.report_data->'verification'->'dates_consistent',
                  'false'::jsonb
              ) = 'true'::jsonb
              AND COALESCE(
                  a.report_data->'verification'->'risk_levels_justified',
                  'false'::jsonb
              ) = 'true'::jsonb
              AND CASE
                  WHEN a.report_data->'verification' ? 'issues'
                  THEN jsonb_typeof(a.report_data->'verification'->'issues') = 'array'
                       AND jsonb_array_length(
                           a.report_data->'verification'->'issues'
                       ) = 0
                  ELSE TRUE
              END
              AND jsonb_typeof(a.report_data->'verification_summary') = 'object'
              AND (
                  a.report_data->'verification_summary'->>'overall_assessment'
              ) IN ('PASS', 'PASS_WITH_CORRECTIONS')
              AND CASE
                  WHEN jsonb_typeof(
                      a.report_data->'verification_summary'->'factual_accuracy_rate'
                  ) = 'number'
                  THEN (
                      a.report_data->'verification_summary'->>'factual_accuracy_rate'
                  )::numeric >= 0.95
                  ELSE FALSE
              END
              AND COALESCE(
                  a.report_data->'verification_summary'->>'claims_incorrect',
                  ''
              ) = '0'
              AND COALESCE(
                  a.report_data->'verification_summary'->>'claims_unverifiable',
                  ''
              ) = '0'
              AND CASE
                  WHEN a.report_data->'verification_summary' ? 'corrections_needed'
                  THEN jsonb_typeof(
                      a.report_data->'verification_summary'->'corrections_needed'
                  ) = 'array'
                  AND jsonb_array_length(
                      a.report_data->'verification_summary'->'corrections_needed'
                  ) = 0
                  ELSE TRUE
              END
              AND (
                  jsonb_array_length(a.report_data->'patent_analyses') = 0
                  OR COALESCE(
                      a.report_data->'verification_summary'->>'total_claims_checked',
                      ''
                  ) <> '0'
              )
              AND jsonb_typeof(a.report_data->'claim_source_span_map') = 'object'
              AND jsonb_typeof(a.report_data->'claim_source_span_map'->'entries') = 'array'
              AND jsonb_typeof(a.report_data->'claim_source_span_map'->'spans') = 'object'
              AND (
                  jsonb_array_length(a.report_data->'patent_analyses') = 0
                  OR (
                      jsonb_array_length(
                          a.report_data->'claim_source_span_map'->'entries'
                      ) > 0
                      AND a.report_data->'claim_source_span_map'->'spans'
                          <> '{}'::jsonb
                  )
              )
              AND (
                  a.report_data->'claim_source_span_map'
                      ->>'unsupported_customer_visible_claim_count'
              ) = '0'
              AND (
                  a.report_data->'claim_source_span_map'->>'needs_review_count'
              ) = '0'
"""

REPORT_ENTRY_SUPPORT_SQL_PREDICATE = """
              AND NOT EXISTS (
                  SELECT 1
                  FROM jsonb_array_elements(
                      a.report_data->'claim_source_span_map'->'entries'
                  ) AS claim_support(value)
                  WHERE COALESCE(claim_support.value->>'support_status', '') NOT IN (
                      'supported',
                      'unsupported',
                      'needs_review'
                  )
                     OR (
                         claim_support.value ? 'customer_visible'
                         AND jsonb_typeof(
                             claim_support.value->'customer_visible'
                         ) <> 'boolean'
                     )
                     OR (
                         claim_support.value ? 'review_required'
                         AND jsonb_typeof(
                             claim_support.value->'review_required'
                         ) <> 'boolean'
                     )
                     OR (
                         COALESCE(
                             claim_support.value->'customer_visible',
                             'true'::jsonb
                         ) <> 'false'::jsonb
                         AND claim_support.value->>'support_status' = 'unsupported'
                     )
                     OR (
                         COALESCE(
                             claim_support.value->'customer_visible',
                             'true'::jsonb
                         ) <> 'false'::jsonb
                         AND (
                             claim_support.value->>'support_status' = 'needs_review'
                             OR COALESCE(
                                 claim_support.value->'review_required',
                                 'false'::jsonb
                             ) = 'true'::jsonb
                         )
                     )
                     OR (
                         COALESCE(
                             claim_support.value->'customer_visible',
                             'true'::jsonb
                         ) <> 'false'::jsonb
                         AND claim_support.value->>'support_status' = 'supported'
                         AND CASE
                             WHEN jsonb_typeof(
                                 claim_support.value->'source_span_ids'
                             ) = 'array'
                             THEN jsonb_array_length(
                                 claim_support.value->'source_span_ids'
                             ) = 0
                             OR EXISTS (
                                 SELECT 1
                                 FROM jsonb_array_elements(
                                     claim_support.value->'source_span_ids'
                                 ) AS raw_source_span_id(value)
                                 WHERE jsonb_typeof(raw_source_span_id.value) <> 'string'
                             )
                             OR EXISTS (
                                 SELECT 1
                                 FROM jsonb_array_elements_text(
                                     claim_support.value->'source_span_ids'
                                 ) AS source_span_id(value)
                                 CROSS JOIN LATERAL (
                                     SELECT
                                         a.report_data->'claim_source_span_map'->'spans'
                                             ->source_span_id.value AS value
                                 ) AS source_span
                                 WHERE NOT (
                                     a.report_data->'claim_source_span_map'->'spans'
                                         ? source_span_id.value
                                     AND jsonb_typeof(source_span.value) = 'object'
                                     AND source_span.value->>'span_id' = source_span_id.value
                                     AND btrim(
                                         COALESCE(source_span.value->>'excerpt', '')
                                     ) <> ''
                                     AND (
                                         COALESCE(
                                             claim_support.value->>'patent_id',
                                             ''
                                         ) = ''
                                         OR source_span.value->>'patent_id'
                                             = claim_support.value->>'patent_id'
                                     )
                                     AND (
                                         NOT (claim_support.value ? 'claim_number')
                                         OR claim_support.value->'claim_number' = 'null'::jsonb
                                         OR source_span.value->'claim_number'
                                             = claim_support.value->'claim_number'
                                     )
                                     AND (
                                         NOT (claim_support.value ? 'element_number')
                                         OR claim_support.value->'element_number' = 'null'::jsonb
                                         OR source_span.value->'element_number'
                                             = claim_support.value->'element_number'
                                     )
                                 )
                             )
                             OR NOT EXISTS (
                                 SELECT 1
                                 FROM jsonb_array_elements_text(
                                     claim_support.value->'source_span_ids'
                                 ) AS evidence_source_span_id(value)
                                 CROSS JOIN LATERAL (
                                     SELECT
                                         a.report_data->'claim_source_span_map'->'spans'
                                             ->evidence_source_span_id.value AS value
                                 ) AS evidence_source_span
                                 WHERE
                                    a.report_data->'claim_source_span_map'->'spans'
                                        ? evidence_source_span_id.value
                                    AND jsonb_typeof(evidence_source_span.value) = 'object'
                                    AND evidence_source_span.value->>'source_type' IN (
                                        'verified_claim_text',
                                        'specification_citation'
                                    )
                             )
                             ELSE TRUE
                         END
                     )
              )
"""

REPORT_PATENT_ANALYSIS_SUPPORT_SQL_PREDICATE = """
                  AND EXISTS (
                      SELECT 1
                      FROM jsonb_array_elements(
                          a.report_data->'claim_source_span_map'->'entries'
                      ) AS patent_support(value)
                      WHERE patent_support.value->>'patent_id' = pa.value->>'patent_id'
                        AND COALESCE(
                            patent_support.value->>'support_status',
                            ''
                        ) = 'supported'
                        AND COALESCE(
                            patent_support.value->'customer_visible',
                            'true'::jsonb
                        ) <> 'false'::jsonb
                        AND jsonb_typeof(
                            patent_support.value->'source_span_ids'
                        ) = 'array'
                        AND EXISTS (
                            SELECT 1
                            FROM jsonb_array_elements_text(
                                patent_support.value->'source_span_ids'
                            ) AS patent_source_span_id(value)
                            CROSS JOIN LATERAL (
                                SELECT
                                    a.report_data->'claim_source_span_map'->'spans'
                                        ->patent_source_span_id.value AS value
                            ) AS patent_source_span
                            WHERE
                                a.report_data->'claim_source_span_map'->'spans'
                                    ? patent_source_span_id.value
                                AND jsonb_typeof(patent_source_span.value) = 'object'
                                AND patent_source_span.value->>'patent_id'
                                    = pa.value->>'patent_id'
                                AND btrim(
                                    COALESCE(patent_source_span.value->>'excerpt', '')
                                ) <> ''
                                AND patent_source_span.value->>'source_type' IN (
                                    'verified_claim_text',
                                    'specification_citation'
                                )
                        )
                  )
"""


def parse_cpc_codes(raw_cpc: object) -> list[str]:
    """Normalize CPC codes from JSONB-backed query output."""
    if isinstance(raw_cpc, list):
        return raw_cpc
    if isinstance(raw_cpc, str):
        try:
            parsed = json.loads(raw_cpc)
        except (ValueError, TypeError):
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def escape_like_pattern(value: str) -> str:
    """Escape SQL LIKE metacharacters so patent searches remain literal."""
    return (
        value.replace(LIKE_ESCAPE_CHARACTER, LIKE_ESCAPE_CHARACTER * 2)
        .replace("%", f"{LIKE_ESCAPE_CHARACTER}%")
        .replace("_", f"{LIKE_ESCAPE_CHARACTER}_")
    )


def _project_present_fields(
    source: Mapping[str, object],
    allowed_fields: tuple[str, ...],
) -> dict[str, object]:
    """Copy only a reviewed allowlist into a restricted response projection."""
    return {field: source[field] for field in allowed_fields if field in source}


def _project_restricted_claims(value: object) -> list[dict[str, object]]:
    """Preserve claim source language while removing claim-matching decisions."""
    if not isinstance(value, list):
        return []

    projected_claims: list[dict[str, object]] = []
    for raw_claim in value:
        if not isinstance(raw_claim, Mapping):
            continue
        claim = _project_present_fields(
            raw_claim,
            (
                "claim_number",
                "claim_type",
                "depends_on",
                "preamble",
                "transitional_phrase",
            ),
        )
        raw_elements = raw_claim.get("elements")
        elements: list[dict[str, object]] = []
        if isinstance(raw_elements, list):
            for raw_element in raw_elements:
                if isinstance(raw_element, Mapping):
                    elements.append(
                        _project_present_fields(
                            raw_element,
                            ("element_number", "element_text"),
                        )
                    )
        claim["elements"] = elements
        projected_claims.append(claim)
    return projected_claims


def _project_restricted_patent_analysis(value: object) -> dict[str, object]:
    """Project patent identity and source claim text without FTO conclusions."""
    if not isinstance(value, Mapping):
        return {}
    projected = _project_present_fields(
        value,
        ("patent_id", "title", "assignee", "expiry_date"),
    )
    projected["claims_analyzed"] = _project_restricted_claims(value.get("claims_analyzed"))
    return projected


def _project_restricted_doe(value: object) -> dict[str, object] | None:
    """Project only the claim-element identity targeted by a DoE assessment."""
    if not isinstance(value, Mapping):
        return None
    return _project_present_fields(
        value,
        ("patent_id", "claim_number", "element_number", "element_text"),
    )


def _project_restricted_ptab(value: object) -> dict[str, object]:
    """Project public PTAB docket facts without evaluative summaries."""
    if not isinstance(value, Mapping):
        return {}
    projected = _project_present_fields(
        value,
        ("has_been_challenged", "all_claims_cancelled"),
    )
    proceedings: list[dict[str, object]] = []
    raw_proceedings = value.get("proceedings")
    if isinstance(raw_proceedings, list):
        for raw_proceeding in raw_proceedings:
            if isinstance(raw_proceeding, Mapping):
                proceedings.append(
                    _project_present_fields(
                        raw_proceeding,
                        (
                            "proceeding_number",
                            "type",
                            "status",
                            "filing_date",
                            "decision_date",
                            "claims_challenged",
                            "claims_cancelled",
                            "claims_survived",
                        ),
                    )
                )
    projected["proceedings"] = proceedings
    return projected


def _project_restricted_prior_art(value: object) -> list[dict[str, object]]:
    """Project bibliographic source metadata without invalidity scoring."""
    if not isinstance(value, list):
        return []
    projected: list[dict[str, object]] = []
    for raw_reference in value:
        if isinstance(raw_reference, Mapping):
            projected.append(
                _project_present_fields(
                    raw_reference,
                    (
                        "reference_id",
                        "title",
                        "publication_date",
                        "reference_type",
                        "authors",
                        "journal",
                        "doi",
                        "url",
                        "abstract",
                        "source_database",
                    ),
                )
            )
    return projected


def _project_restricted_invalidity(value: object) -> dict[str, object] | None:
    """Project source inventories without an invalidity conclusion."""
    if not isinstance(value, Mapping):
        return None
    projected = _project_present_fields(value, ("patent_id", "claim_numbers"))
    projected["ptab"] = _project_restricted_ptab(value.get("ptab"))
    projected["prior_art"] = _project_restricted_prior_art(value.get("prior_art"))
    return projected


def _is_publishable_report_payload(
    report_data: object,
    *,
    analysis_id: object,
    org_id: object,
) -> bool:
    if not isinstance(report_data, Mapping):
        return False
    try:
        validate_report_publishability(
            report_data,
            analysis_id=str(analysis_id),
            org_id=str(org_id),
        )
    except ValueError:
        return False
    return True


async def list_patents_for_org(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    risk_ratings_restricted: bool,
    page: int,
    per_page: int,
    risk_filter: str | None = None,
    search: str | None = None,
    sort_by: str = "risk-desc",
) -> dict:
    """Browse patents across analyses using SQL-level JSONB extraction."""
    if risk_ratings_restricted and (risk_filter is not None or sort_by in PATENT_RISK_SORTS):
        raise APIError(
            403,
            "Forbidden",
            "Risk filters and risk sorting are restricted to attorney-role users",
            type_uri=PATENT_RISK_RESTRICTED_ERROR_TYPE,
        )

    order_by = PATENT_LIBRARY_ORDER_BY.get(sort_by)
    if order_by is None:
        raise APIError(400, "Bad Request", "Unsupported patent library sort")
    offset = (page - 1) * per_page
    params: dict = {"org_id": str(org_id), "offset": offset, "per_page": per_page}

    risk_where = ""
    if risk_filter is not None:
        params["risk_filter"] = risk_filter
        risk_where = "\n              AND pa.value->>'risk_level' = :risk_filter"

    search_where = ""
    if search:
        params["search_query"] = f"%{escape_like_pattern(search)}%"
        search_where = """
              AND (
                  pa.value->>'patent_id' ILIKE :search_query ESCAPE '\\'
                  OR pa.value->>'title' ILIKE :search_query ESCAPE '\\'
                  OR pa.value->>'assignee' ILIKE :search_query ESCAPE '\\'
                  OR a.compound_name ILIKE :search_query ESCAPE '\\'
              )"""

    # DISTINCT ON deduplicates to the most-recent analysis per patent.
    # Wrapping in a subquery lets COUNT(*) OVER () compute the accurate total
    # across all distinct patents before OFFSET/LIMIT slices the page.
    # report_data is not selected here (used only in CTE WHERE predicates above).
    query = text(  # nosemgrep
        f"""
        WITH structurally_valid_reports AS MATERIALIZED (
            SELECT a.id, a.report_data, a.compound_name, a.completed_at
            FROM analyses a
            WHERE a.org_id = :org_id
{REPORT_STRUCTURAL_SQL_PREDICATE}
        ),
        eligible_analyses AS MATERIALIZED (
            SELECT a.id, a.report_data, a.compound_name, a.completed_at
            FROM structurally_valid_reports a
            WHERE TRUE
{REPORT_ENTRY_SUPPORT_SQL_PREDICATE}
        ),
        candidate_patents AS (
            SELECT
                pa.value->>'patent_id' AS patent_id,
                pa.value->>'title' AS title,
                pa.value->>'assignee' AS assignee,
                pa.value->>'risk_level' AS risk_level,
                pa.value->>'expiry_date' AS expiry_date,
                a.id::text AS analysis_id,
                a.compound_name AS compound_name,
                COALESCE(pa.value->'cpc_codes', '[]'::jsonb) AS cpc_codes,
                a.report_data AS report_data,
                a.completed_at AS analysis_completed_at
            FROM eligible_analyses a,
                 jsonb_array_elements(a.report_data->'patent_analyses') AS pa(value)
            WHERE pa.value->>'patent_id' IS NOT NULL
              AND btrim(pa.value->>'patent_id') <> ''
{REPORT_PATENT_ANALYSIS_SUPPORT_SQL_PREDICATE}{risk_where}{search_where}
        )
        SELECT *, COUNT(*) OVER () AS total_count
        FROM (
            SELECT DISTINCT ON (patent_id)
                patent_id, title, assignee, risk_level, expiry_date,
                analysis_id, compound_name, cpc_codes, report_data
            FROM candidate_patents
            ORDER BY patent_id, analysis_completed_at DESC, analysis_id DESC
        ) AS deduped
        ORDER BY {order_by}
        OFFSET :offset LIMIT :per_page
        """
    )

    rows = (await db.execute(query, params)).mappings().all()
    total = int(rows[0]["total_count"]) if rows else 0

    items = []
    for row in rows:
        patent_id = row["patent_id"]
        report_data = row.get("report_data") if isinstance(row, Mapping) else None
        if not _is_publishable_report_payload(
            report_data,
            analysis_id=row["analysis_id"],
            org_id=org_id,
        ):
            logger.warning(
                "patent_report_failed_publishability",
                patent_id=patent_id,
                analysis_id=row["analysis_id"],
            )
            raise APIError(
                409,
                "Conflict",
                "Patent library report failed publishability checks",
            )
        title = row["title"]
        risk_level = row["risk_level"]
        if not title or not risk_level:
            logger.warning(
                "patent_missing_data",
                patent_id=patent_id,
                missing_title=not title,
                missing_risk_level=not risk_level,
            )
        item = {
            "id": patent_id,
            "patent_number": patent_id,
            "title": title or "",
            "assignee": row["assignee"] or "",
            "cpc_codes": parse_cpc_codes(row["cpc_codes"]),
            "expiry_date": row["expiry_date"],
            "analysis_id": row["analysis_id"],
            "compound_name": row["compound_name"] or "",
        }
        if not risk_ratings_restricted:
            item["risk_level"] = risk_level or ""
        items.append(item)

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


async def get_patent_detail_for_org(
    db: AsyncSession,
    *,
    patent_id: str,
    org_id: uuid.UUID,
    risk_ratings_restricted: bool,
) -> dict:
    """Return the deepest available patent-specific data across analyses."""
    combined_query = text(  # nosemgrep
        f"""
        WITH structurally_valid_reports AS MATERIALIZED (
            SELECT a.id, a.report_data, a.completed_at
            FROM analyses a
            WHERE a.org_id = :org_id
{REPORT_STRUCTURAL_SQL_PREDICATE}
        ),
        eligible_analyses AS MATERIALIZED (
            SELECT a.id, a.report_data, a.completed_at
            FROM structurally_valid_reports a
            WHERE TRUE
{REPORT_ENTRY_SUPPORT_SQL_PREDICATE}
        ),
        target_analyses AS (
            SELECT a.id, a.report_data
            FROM eligible_analyses a,
                 jsonb_array_elements(
                     a.report_data->'patent_analyses'
                 ) AS pa(value)
            WHERE pa.value->>'patent_id' = :patent_id
{REPORT_PATENT_ANALYSIS_SUPPORT_SQL_PREDICATE}
            ORDER BY a.completed_at DESC, a.id DESC
        )
        SELECT
            ta.id::text AS analysis_id,
            ta.report_data AS report_data,
            (SELECT pa.value
             FROM jsonb_array_elements(
                 ta.report_data->'patent_analyses'
             ) AS pa(value)
             WHERE pa.value->>'patent_id' = :patent_id
             LIMIT 1) AS patent_analysis,
            (SELECT d.value
             FROM jsonb_array_elements(
                 ta.report_data->'doe_assessments'
             ) AS d(value)
             WHERE d.value->>'patent_id' = :patent_id
             LIMIT 1) AS doe_assessment,
            (SELECT i.value
             FROM jsonb_array_elements(
                 ta.report_data->'invalidity_assessments'
             ) AS i(value)
             WHERE i.value->>'patent_id' = :patent_id
             LIMIT 1) AS invalidity_assessment
        FROM target_analyses ta
        """
    )
    rows = (
        (
            await db.execute(
                combined_query,
                {"org_id": str(org_id), "patent_id": patent_id},
            )
        )
        .mappings()
        .all()
    )
    for row in rows:
        report_data = row.get("report_data") if isinstance(row, Mapping) else None
        if not _is_publishable_report_payload(
            report_data,
            analysis_id=row["analysis_id"],
            org_id=org_id,
        ):
            logger.warning(
                "patent_detail_report_failed_publishability",
                patent_id=patent_id,
                analysis_id=row["analysis_id"],
            )
            raise APIError(
                409,
                "Conflict",
                "Patent detail report failed publishability checks",
            )
        patent_analysis = dict(row["patent_analysis"])
        if risk_ratings_restricted:
            return {
                "patent_analysis": _project_restricted_patent_analysis(
                    patent_analysis,
                ),
                "doe_assessment": _project_restricted_doe(row["doe_assessment"]),
                "invalidity_assessment": _project_restricted_invalidity(
                    row["invalidity_assessment"],
                ),
                "analysis_id": row["analysis_id"],
            }
        return {
            "patent_analysis": patent_analysis,
            "doe_assessment": row["doe_assessment"],
            "invalidity_assessment": row["invalidity_assessment"],
            "analysis_id": row["analysis_id"],
        }

    raise APIError(404, "Not Found", "Patent not found")
