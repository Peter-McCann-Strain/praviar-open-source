"""Tests for /api/v1/patents endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import bind_report_data, valid_report_data_for_patents

from api.errors import APIError
from api.services.patents import get_patent_detail_for_org, list_patents_for_org

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_PATENT = {
    "patent_id": "US-10000001-B2",
    "title": "Novel Compound Composition",
    "assignee": "Pharma Corp",
    "risk_level": "high",
    "expiry_date": "2035-06-15",
}

SAMPLE_DOE = {
    "patent_id": "US-10000001-B2",
    "claim_number": 1,
    "element_number": 1,
    "element_text": "A composition comprising compound X",
    "overall_equivalent": False,
    "confidence": 0.6,
    "confidence_band": "MODERATE",
    "reasoning": "Some elements are functionally equivalent",
}

SAMPLE_INVALIDITY = {
    "patent_id": "US-10000001-B2",
    "claim_numbers": [1, 3],
    "overall_invalidity_strength": "moderate",
    "confidence": 0.7,
    "confidence_band": "MODERATE",
    "reasoning": "Prior art found for key claims",
}

COUNSEL_ONLY_MARKERS = {
    "Counsel-only claim match",
    "Counsel-only claim reasoning",
    "Counsel-only internal thinking",
    "Counsel-only DoE reasoning",
    "Counsel-only FWR conclusion",
    "Counsel-only invalidity reasoning",
    "Counsel-only invalidity strength",
    "Counsel-only claim chart conclusion",
    "Counsel-only relevance conclusion",
}
RESTRICTED_FORBIDDEN_KEYS = {
    "risk_level",
    "risk_summary",
    "design_around_suggestions",
    "reasoning",
    "thinking_text",
    "overall_status",
    "confidence",
    "confidence_band",
    "evidence",
    "orange_book_info",
    "model_used",
    "input_tokens",
    "output_tokens",
    "estoppel",
    "fwr",
    "overall_equivalent",
    "overall_invalidity_strength",
    "relevance",
    "anticipation_score",
    "obviousness_score",
    "written_description_issues",
    "claim_charts",
    "graham_factors",
    "enablement_screening",
    "screening_disclaimer",
    "outcome_summary",
    "all_elements_disclosed",
    "chart_summary",
    "disclosed",
    "notes",
}


def _assert_counsel_only_markers_absent(payload: object) -> None:
    serialized = str(payload)
    for marker in COUNSEL_ONLY_MARKERS:
        assert marker not in serialized


def _assert_restricted_keys_absent(payload: object) -> None:
    if isinstance(payload, dict):
        assert RESTRICTED_FORBIDDEN_KEYS.isdisjoint(payload)
        for value in payload.values():
            _assert_restricted_keys_absent(value)
    elif isinstance(payload, list):
        for value in payload:
            _assert_restricted_keys_absent(value)


def _make_patent_row(patent=None, analysis_id=None, total_count=1, report_data=None):
    """Create a mapping-like dict for a patent row (mirrors the SQL CTE output)."""
    p = patent or SAMPLE_PATENT
    resolved_analysis_id = str(analysis_id or uuid.uuid4())
    resolved_report = report_data or valid_report_data_for_patents([p])
    bind_report_data(resolved_report, analysis_id=resolved_analysis_id)
    return {
        "patent_id": p["patent_id"],
        "title": p.get("title", ""),
        "assignee": p.get("assignee", ""),
        "risk_level": p.get("risk_level", ""),
        "expiry_date": p.get("expiry_date"),
        "analysis_id": resolved_analysis_id,
        "compound_name": p.get("compound_name", "Test Compound"),
        "cpc_codes": p.get("cpc_codes", []),
        "report_data": resolved_report,
        "total_count": total_count,
    }


def _mock_mappings_result(rows):
    """Return a mock result that supports .mappings().all()."""
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    return result


def _mock_mappings_first(row):
    """Return a mock result that supports .mappings().first()."""
    resolved_row = row
    if resolved_row is not None and "report_data" not in resolved_row:
        analysis_id = str(resolved_row["analysis_id"])
        report_data = valid_report_data_for_patents([resolved_row["patent_analysis"]])
        resolved_row = {
            **resolved_row,
            "report_data": bind_report_data(report_data, analysis_id=analysis_id),
        }
    result = MagicMock()
    result.mappings.return_value.first.return_value = resolved_row
    result.mappings.return_value.all.return_value = [resolved_row] if resolved_row else []
    return result


def _assert_report_provenance_predicates(sql: str) -> None:
    assert "WITH structurally_valid_reports AS MATERIALIZED" in sql
    assert "eligible_analyses AS MATERIALIZED" in sql
    assert "FROM analyses a" in sql
    assert "FROM structurally_valid_reports a" in sql
    assert "FROM eligible_analyses a" in sql
    assert "FROM analyses a,\n" not in sql
    assert "a.status = 'completed'" in sql
    assert "a.report_data IS NOT NULL" in sql
    assert "jsonb_typeof(a.report_data) = 'object'" in sql
    assert "a.report_data <> '{}'::jsonb" in sql
    assert "jsonb_typeof(a.report_data->'patent_analyses') = 'array'" in sql
    assert "a.report_data->'verification'" in sql
    assert "verification_check" in sql
    assert "all_citations_valid" in sql
    assert "all_claims_grounded" in sql
    assert "risk_levels_justified" in sql
    assert "verification_summary" in sql
    assert "overall_assessment" in sql
    assert "factual_accuracy_rate" in sql
    assert "claims_incorrect" in sql
    assert "claims_unverifiable" in sql
    assert "corrections_needed" in sql
    assert "total_claims_checked" in sql
    assert "a.report_data->'claim_source_span_map'" in sql
    assert "a.report_data->'claim_source_span_map'->'entries'" in sql
    assert "a.report_data->'claim_source_span_map'->'spans'" in sql
    assert "jsonb_array_length(a.report_data->'patent_analyses') = 0" in sql
    assert (
        "jsonb_array_length(\n"
        "                          a.report_data->'claim_source_span_map'->'entries'\n"
        "                      ) > 0" in sql
    )
    assert (
        "AND a.report_data->'claim_source_span_map'->'spans'\n"
        "                          <> '{}'::jsonb" in sql
    )
    assert "unsupported_customer_visible_claim_count" in sql
    assert "needs_review_count" in sql
    assert "review_required" in sql
    assert (
        "jsonb_typeof(\n"
        "                             claim_support.value->'customer_visible'\n"
        "                         ) <> 'boolean'" in sql
    )
    assert (
        "jsonb_typeof(\n"
        "                             claim_support.value->'review_required'\n"
        "                         ) <> 'boolean'" in sql
    )
    assert "support_status' = 'needs_review'" in sql
    assert (
        "jsonb_array_elements(\n"
        "                                     claim_support.value->'source_span_ids'\n"
        "                                 ) AS raw_source_span_id(value)" in sql
    )
    assert "jsonb_typeof(raw_source_span_id.value) <> 'string'" in sql
    assert "jsonb_array_elements_text" in sql
    assert "source_span_ids" in sql
    assert "CROSS JOIN LATERAL" in sql
    assert "source_span.value->>'span_id' = source_span_id.value" in sql
    assert "evidence_source_span" in sql
    assert "source_type" in sql
    assert "verified_claim_text" in sql
    assert "element_evidence" not in sql
    assert "specification_citation" in sql
    assert "COALESCE(source_span.value->>'excerpt', '')" in sql
    assert "source_span.value->>'patent_id'" in sql
    assert "claim_support.value->>'patent_id'" in sql
    assert "source_span.value->'claim_number'" in sql
    assert "claim_support.value->'claim_number'" in sql
    assert "source_span.value->'element_number'" in sql
    assert "claim_support.value->'element_number'" in sql
    assert "REPORT_PATENT_ANALYSIS_SUPPORT_SQL_PREDICATE" not in sql
    assert "patent_support.value->>'patent_id' = pa.value->>'patent_id'" in sql
    assert "patent_source_span.value->>'patent_id'" in sql
    assert "patent_source_span.value->>'source_type' IN" in sql


# ---------------------------------------------------------------------------
# GET /api/v1/patents
# ---------------------------------------------------------------------------


class TestListPatents:
    @pytest.mark.asyncio
    async def test_list_returns_patents(self, scientist_client):
        c, db = scientist_client
        rows = [_make_patent_row()]
        db.execute = AsyncMock(return_value=_mock_mappings_result(rows))

        resp = await c.get("/api/v1/patents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == "US-10000001-B2"
        assert data["items"][0]["patent_number"] == "US-10000001-B2"
        assert "risk_level" not in data["items"][0]
        sql = str(db.execute.await_args.args[0])
        assert "ORDER BY patent_id ASC" in sql

    @pytest.mark.asyncio
    async def test_list_empty_when_no_reports(self, scientist_client):
        c, db = scientist_client
        db.execute = AsyncMock(return_value=_mock_mappings_result([]))

        resp = await c.get("/api/v1/patents")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["items"] == []

    @pytest.mark.asyncio
    async def test_list_multiple_patents(self, scientist_client):
        c, db = scientist_client
        rows = [
            _make_patent_row(SAMPLE_PATENT, total_count=2),
            _make_patent_row(
                {
                    "patent_id": "US-20000002-A1",
                    "title": "Another Patent",
                    "assignee": "Other Corp",
                    "risk_level": "low",
                    "expiry_date": "2040-01-01",
                },
                total_count=2,
            ),
        ]
        db.execute = AsyncMock(return_value=_mock_mappings_result(rows))

        resp = await c.get("/api/v1/patents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_rejects_sql_candidate_that_fails_shared_publishability(self):
        """SQL prefiltering is followed by the shared serving-time gate."""
        db = AsyncMock()
        invalid_report = valid_report_data_for_patents([SAMPLE_PATENT])
        invalid_report["clearance_decision"]["decision"] = "clear"
        invalid_report["clearance_decision"]["decision_audit"]["decisive_references"] = []
        valid_report = valid_report_data_for_patents([SAMPLE_PATENT])
        db.execute.return_value = _mock_mappings_result(
            [
                _make_patent_row(
                    SAMPLE_PATENT,
                    analysis_id=uuid.uuid4(),
                    report_data=invalid_report,
                    total_count=2,
                ),
                _make_patent_row(
                    SAMPLE_PATENT,
                    analysis_id=uuid.uuid4(),
                    report_data=valid_report,
                    total_count=2,
                ),
            ]
        )

        with pytest.raises(APIError) as exc_info:
            await list_patents_for_org(
                db,
                org_id=uuid.uuid4(),
                risk_ratings_restricted=False,
                risk_filter=None,
                search=None,
                page=1,
                per_page=20,
            )

        assert exc_info.value.status == 409
        assert "failed publishability checks" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_list_rejects_revoked_clear_report_with_exact_owner_context(self):
        db = AsyncMock()
        org_id = uuid.uuid4()
        analysis_id = uuid.uuid4()
        report = valid_report_data_for_patents([SAMPLE_PATENT])
        db.execute.return_value = _mock_mappings_result(
            [
                _make_patent_row(
                    SAMPLE_PATENT,
                    analysis_id=analysis_id,
                    report_data=report,
                )
            ]
        )

        with (
            patch(
                "api.services.patents.validate_report_publishability",
                side_effect=ValueError("certification_release_receipt_revoked"),
            ) as validate,
            pytest.raises(APIError) as exc_info,
        ):
            await list_patents_for_org(
                db,
                org_id=org_id,
                risk_ratings_restricted=False,
                risk_filter=None,
                search=None,
                page=1,
                per_page=20,
            )

        assert exc_info.value.status == 409
        validate.assert_called_once_with(
            report,
            analysis_id=str(analysis_id),
            org_id=str(org_id),
        )

    @pytest.mark.asyncio
    async def test_list_with_risk_filter(self, attorney_client):
        c, db = attorney_client
        rows = [_make_patent_row()]
        db.execute = AsyncMock(return_value=_mock_mappings_result(rows))

        resp = await c.get("/api/v1/patents?risk_filter=high")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["risk_level"] == "high"

    @pytest.mark.asyncio
    async def test_list_rejects_risk_filter_for_risk_restricted_scientist(
        self,
        scientist_client,
    ):
        c, db = scientist_client

        resp = await c.get("/api/v1/patents?risk_filter=high")

        assert resp.status_code == 403
        assert resp.json()["type"] == ("https://problems.praviar.invalid/risk-ratings-restricted")
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sort_by", ["risk-asc", "risk-desc"])
    async def test_list_rejects_risk_sort_for_risk_restricted_scientist(
        self,
        scientist_client,
        sort_by,
    ):
        c, db = scientist_client

        resp = await c.get(f"/api/v1/patents?sort_by={sort_by}")

        assert resp.status_code == 403
        assert resp.json()["type"] == ("https://problems.praviar.invalid/risk-ratings-restricted")
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_service_rejects_restricted_risk_query_before_database_access(self):
        db = AsyncMock()

        with pytest.raises(APIError) as exc_info:
            await list_patents_for_org(
                db,
                org_id=uuid.uuid4(),
                risk_ratings_restricted=True,
                risk_filter="high",
                search=None,
                sort_by="id-asc",
                page=1,
                per_page=20,
            )

        assert exc_info.value.status == 403
        assert exc_info.value.type_uri == (
            "https://problems.praviar.invalid/risk-ratings-restricted"
        )
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_allows_id_sort_for_risk_restricted_scientist(
        self,
        scientist_client,
    ):
        c, db = scientist_client
        rows = [_make_patent_row()]
        db.execute = AsyncMock(return_value=_mock_mappings_result(rows))

        resp = await c.get("/api/v1/patents?sort_by=id-desc")

        assert resp.status_code == 200
        assert "risk_level" not in resp.json()["items"][0]
        assert "ORDER BY patent_id DESC" in str(db.execute.await_args.args[0])

    @pytest.mark.asyncio
    async def test_list_pagination(self, scientist_client):
        c, db = scientist_client
        # SQL applies OFFSET/LIMIT — only per_page=2 rows are returned.
        # COUNT(*) OVER () sets total_count=5 across all pages.
        rows = [
            _make_patent_row(
                {**SAMPLE_PATENT, "patent_id": f"US-1000000{index}-B2"},
                total_count=5,
            )
            for index in range(2)
        ]
        db.execute = AsyncMock(return_value=_mock_mappings_result(rows))

        resp = await c.get("/api/v1/patents?page=1&per_page=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_passes_library_wide_sort_before_pagination(self, attorney_client):
        c, db = attorney_client
        db.execute = AsyncMock(return_value=_mock_mappings_result([]))

        resp = await c.get("/api/v1/patents?sort_by=risk-asc&page=2&per_page=5")

        assert resp.status_code == 200
        sql = str(db.execute.await_args.args[0])
        params = db.execute.await_args.args[1]
        assert "ORDER BY \n            CASE lower(risk_level)" in sql
        assert "ASC NULLS LAST, patent_id ASC" in sql
        assert "OFFSET :offset LIMIT :per_page" in sql
        assert sql.index("ASC NULLS LAST, patent_id ASC") < sql.index(
            "OFFSET :offset LIMIT :per_page"
        )
        assert "ORDER BY patent_id, analysis_completed_at DESC, analysis_id DESC" in sql
        assert params["offset"] == 5
        assert params["per_page"] == 5

    @pytest.mark.asyncio
    async def test_list_rejects_unknown_sort(self, scientist_client):
        c, db = scientist_client
        db.execute = AsyncMock()

        resp = await c.get("/api/v1/patents?sort_by=page-local-risk")

        assert resp.status_code == 422
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_forbidden_for_client(self, client_role_client):
        c, _db = client_role_client
        resp = await c.get("/api/v1/patents")
        assert resp.status_code == 403
        assert "Insufficient permissions" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_query_filters_to_completed_reports_with_source_span_provenance(self):
        db = AsyncMock()
        db.execute.return_value = _mock_mappings_result([])

        await list_patents_for_org(
            db,
            org_id=uuid.uuid4(),
            risk_ratings_restricted=False,
            risk_filter=None,
            search=None,
            page=1,
            per_page=20,
        )

        sql = str(db.execute.await_args.args[0])
        _assert_report_provenance_predicates(sql)
        assert "ORDER BY patent_id, analysis_completed_at DESC, analysis_id DESC" in sql

    @pytest.mark.asyncio
    async def test_list_search_treats_like_metacharacters_literally(self):
        db = AsyncMock()
        db.execute.return_value = _mock_mappings_result([])

        await list_patents_for_org(
            db,
            org_id=uuid.uuid4(),
            risk_ratings_restricted=False,
            risk_filter=None,
            search="US_100%\\family",
            page=1,
            per_page=20,
        )

        sql = str(db.execute.await_args.args[0])
        params = db.execute.await_args.args[1]
        assert params["search_query"] == r"%US\_100\%\\family%"
        assert sql.count("ILIKE :search_query ESCAPE '\\'") == 4


# ---------------------------------------------------------------------------
# GET /api/v1/patents/{patent_id}
# ---------------------------------------------------------------------------


class TestGetPatent:
    @pytest.mark.asyncio
    async def test_get_patent_found(self, scientist_client):
        c, db = scientist_client
        analysis_id = str(uuid.uuid4())

        combined = _mock_mappings_first(
            {
                "patent_analysis": {
                    **SAMPLE_PATENT,
                    "risk_summary": "Counsel-only infringement assessment",
                    "design_around_suggestions": [
                        {
                            "element_avoided": 1,
                            "suggestion": "Counsel-only design-around",
                            "feasibility": "moderate",
                        }
                    ],
                    "claims_analyzed": [
                        {
                            "claim_number": 1,
                            "claim_type": "independent",
                            "depends_on": None,
                            "preamble": "A composition",
                            "transitional_phrase": "comprising",
                            "reasoning": "Counsel-only claim reasoning",
                            "overall_status": "met",
                            "overall_confidence": 0.99,
                            "elements": [
                                {
                                    "element_number": 1,
                                    "element_text": "compound X",
                                    "status": "met",
                                    "reasoning": "Counsel-only claim match",
                                    "confidence": 0.98,
                                    "evidence": "Product evidence proves the limitation",
                                }
                            ],
                        }
                    ],
                    "orange_book_info": {
                        "blocking_listing": True,
                        "conclusion": "Counsel-only Orange Book conclusion",
                    },
                    "model_used": "internal-counsel-model",
                    "thinking_text": "Counsel-only internal thinking",
                    "input_tokens": 100,
                    "output_tokens": 50,
                },
                "doe_assessment": {
                    **SAMPLE_DOE,
                    "overall_equivalent": True,
                    "reasoning": "Counsel-only DoE reasoning",
                    "estoppel": {
                        "estoppel_applies": True,
                        "surrendered_scope": "Counsel-only estoppel conclusion",
                    },
                    "fwr": {
                        "same_function": True,
                        "same_way": True,
                        "same_result": True,
                        "equivalent": True,
                        "function_reasoning": "Counsel-only FWR conclusion",
                        "way_reasoning": "Counsel-only way conclusion",
                        "result_reasoning": "Counsel-only result conclusion",
                    },
                },
                "invalidity_assessment": {
                    **SAMPLE_INVALIDITY,
                    "overall_invalidity_strength": "Counsel-only invalidity strength",
                    "reasoning": "Counsel-only invalidity reasoning",
                    "written_description_issues": ["Counsel-only written-description issue"],
                    "claim_charts": [
                        {
                            "chart_summary": "Counsel-only claim chart conclusion",
                            "all_elements_disclosed": True,
                        }
                    ],
                    "graham_factors": {
                        "overall_obviousness_assessment": ("Counsel-only obviousness conclusion")
                    },
                    "enablement_screening": {
                        "reasoning": "Counsel-only enablement conclusion",
                    },
                    "ptab": {
                        "has_been_challenged": True,
                        "all_claims_cancelled": [],
                        "proceedings": [
                            {
                                "proceeding_number": "IPR2025-00001",
                                "type": "IPR",
                                "status": "Instituted",
                                "filing_date": "2025-01-02",
                                "decision_date": None,
                                "claims_challenged": [1],
                                "claims_cancelled": [],
                                "claims_survived": [],
                                "outcome_summary": "Counsel-only PTAB outcome analysis",
                            }
                        ],
                    },
                    "prior_art": [
                        {
                            "reference_id": "WO2020000001A1",
                            "title": "Earlier composition",
                            "publication_date": "2020-01-01",
                            "relevance": "Counsel-only relevance conclusion",
                            "anticipation_score": 0.91,
                            "obviousness_score": 0.82,
                            "reference_type": "patent",
                            "authors": ["Example Inventor"],
                            "journal": "",
                            "doi": "",
                            "url": "https://example.test/prior-art",
                            "abstract": "Neutral source abstract",
                            "source_database": "lens",
                        }
                    ],
                },
                "analysis_id": analysis_id,
            }
        )
        db.execute = AsyncMock(return_value=combined)

        resp = await c.get("/api/v1/patents/US-10000001-B2")
        assert resp.status_code == 200
        data = resp.json()
        assert set(data["patent_analysis"]) == {
            "patent_id",
            "title",
            "assignee",
            "expiry_date",
            "claims_analyzed",
        }
        restricted_claim = data["patent_analysis"]["claims_analyzed"][0]
        assert set(restricted_claim) == {
            "claim_number",
            "claim_type",
            "depends_on",
            "preamble",
            "transitional_phrase",
            "elements",
        }
        assert restricted_claim["elements"] == [{"element_number": 1, "element_text": "compound X"}]
        assert data["doe_assessment"] == {
            "patent_id": "US-10000001-B2",
            "claim_number": 1,
            "element_number": 1,
            "element_text": "A composition comprising compound X",
        }
        assert set(data["invalidity_assessment"]) == {
            "patent_id",
            "claim_numbers",
            "ptab",
            "prior_art",
        }
        assert "outcome_summary" not in data["invalidity_assessment"]["ptab"]["proceedings"][0]
        assert set(data["invalidity_assessment"]["prior_art"][0]) == {
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
        }
        _assert_restricted_keys_absent(data)
        _assert_counsel_only_markers_absent(data)
        assert data["analysis_id"] == analysis_id

    @pytest.mark.asyncio
    async def test_get_patent_not_found(self, scientist_client):
        c, db = scientist_client
        db.execute = AsyncMock(return_value=_mock_mappings_first(None))

        resp = await c.get("/api/v1/patents/US-99999999-B2")
        assert resp.status_code == 404
        assert "Patent not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_patent_no_doe_or_invalidity(self, scientist_client):
        c, db = scientist_client
        analysis_id = str(uuid.uuid4())

        combined = _mock_mappings_first(
            {
                "patent_analysis": {
                    **SAMPLE_PATENT,
                    "risk_summary": "Authorized counsel assessment",
                    "design_around_suggestions": [
                        {
                            "element_avoided": 1,
                            "suggestion": "Authorized design-around",
                            "feasibility": "moderate",
                        }
                    ],
                },
                "doe_assessment": None,
                "invalidity_assessment": None,
                "analysis_id": analysis_id,
            }
        )
        db.execute = AsyncMock(return_value=combined)

        resp = await c.get("/api/v1/patents/US-10000001-B2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["doe_assessment"] is None
        assert data["invalidity_assessment"] is None

    @pytest.mark.asyncio
    async def test_detail_rejects_sql_candidate_that_fails_shared_publishability(self):
        db = AsyncMock()
        invalid_report = valid_report_data_for_patents([SAMPLE_PATENT])
        invalid_report["clearance_decision"]["decision"] = "clear"
        invalid_report["clearance_decision"]["decision_audit"]["decisive_references"] = []
        valid_report = valid_report_data_for_patents([SAMPLE_PATENT])
        result = MagicMock()
        result.mappings.return_value.all.return_value = [
            {
                "patent_analysis": SAMPLE_PATENT,
                "doe_assessment": None,
                "invalidity_assessment": None,
                "analysis_id": str(uuid.uuid4()),
                "report_data": invalid_report,
            },
            {
                "patent_analysis": SAMPLE_PATENT,
                "doe_assessment": SAMPLE_DOE,
                "invalidity_assessment": SAMPLE_INVALIDITY,
                "analysis_id": str(uuid.uuid4()),
                "report_data": valid_report,
            },
        ]
        db.execute.return_value = result

        with pytest.raises(APIError) as exc_info:
            await get_patent_detail_for_org(
                db,
                patent_id=SAMPLE_PATENT["patent_id"],
                org_id=uuid.uuid4(),
                risk_ratings_restricted=False,
            )

        assert exc_info.value.status == 409
        assert "failed publishability checks" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_patent_forbidden_for_client(self, client_role_client):
        c, _db = client_role_client
        resp = await c.get("/api/v1/patents/US-10000001-B2")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_get_patent_allowed_for_admin(self, admin_client):
        c, db = admin_client
        analysis_id = str(uuid.uuid4())

        combined = _mock_mappings_first(
            {
                "patent_analysis": {
                    **SAMPLE_PATENT,
                    "risk_summary": "Authorized counsel assessment",
                    "design_around_suggestions": [
                        {
                            "element_avoided": 1,
                            "suggestion": "Authorized design-around",
                            "feasibility": "moderate",
                        }
                    ],
                    "claims_analyzed": [
                        {
                            "claim_number": 1,
                            "elements": [
                                {
                                    "element_number": 1,
                                    "element_text": "compound X",
                                    "status": "met",
                                    "reasoning": "Counsel-only claim match",
                                }
                            ],
                            "reasoning": "Counsel-only claim reasoning",
                            "overall_status": "met",
                        }
                    ],
                    "thinking_text": "Counsel-only internal thinking",
                },
                "doe_assessment": {
                    **SAMPLE_DOE,
                    "overall_equivalent": True,
                    "reasoning": "Counsel-only DoE reasoning",
                },
                "invalidity_assessment": {
                    **SAMPLE_INVALIDITY,
                    "overall_invalidity_strength": "strong",
                    "reasoning": "Counsel-only invalidity reasoning",
                },
                "analysis_id": analysis_id,
            }
        )
        db.execute = AsyncMock(return_value=combined)

        resp = await c.get("/api/v1/patents/US-10000001-B2")
        assert resp.status_code == 200
        assert resp.json()["patent_analysis"]["risk_level"] == "high"
        assert resp.json()["patent_analysis"]["risk_summary"] == "Authorized counsel assessment"
        assert resp.json()["patent_analysis"]["design_around_suggestions"] == [
            {
                "element_avoided": 1,
                "suggestion": "Authorized design-around",
                "feasibility": "moderate",
            }
        ]
        assert (
            resp.json()["patent_analysis"]["claims_analyzed"][0]["elements"][0]["status"] == "met"
        )
        assert resp.json()["patent_analysis"]["thinking_text"] == "Counsel-only internal thinking"
        assert resp.json()["doe_assessment"]["overall_equivalent"] is True
        assert resp.json()["invalidity_assessment"]["overall_invalidity_strength"] == "strong"

    @pytest.mark.asyncio
    async def test_get_patent_allowed_for_attorney(self, attorney_client):
        c, db = attorney_client
        analysis_id = str(uuid.uuid4())
        db.execute = AsyncMock(
            return_value=_mock_mappings_first(
                {
                    "patent_analysis": {
                        **SAMPLE_PATENT,
                        "claims_analyzed": [
                            {
                                "claim_number": 1,
                                "elements": [
                                    {
                                        "element_number": 1,
                                        "element_text": "compound X",
                                        "status": "met",
                                        "reasoning": "Authorized claim reasoning",
                                    }
                                ],
                                "overall_status": "met",
                                "reasoning": "Authorized overall claim reasoning",
                            }
                        ],
                        "thinking_text": "Authorized internal analysis",
                    },
                    "doe_assessment": {
                        **SAMPLE_DOE,
                        "overall_equivalent": True,
                        "reasoning": "Authorized DoE reasoning",
                    },
                    "invalidity_assessment": {
                        **SAMPLE_INVALIDITY,
                        "overall_invalidity_strength": "strong",
                        "reasoning": "Authorized invalidity reasoning",
                    },
                    "analysis_id": analysis_id,
                }
            )
        )

        resp = await c.get("/api/v1/patents/US-10000001-B2")

        assert resp.status_code == 200
        data = resp.json()
        assert data["patent_analysis"]["claims_analyzed"][0]["overall_status"] == "met"
        assert (
            data["patent_analysis"]["claims_analyzed"][0]["elements"][0]["reasoning"]
            == "Authorized claim reasoning"
        )
        assert data["patent_analysis"]["thinking_text"] == "Authorized internal analysis"
        assert data["doe_assessment"]["overall_equivalent"] is True
        assert data["doe_assessment"]["reasoning"] == "Authorized DoE reasoning"
        assert data["invalidity_assessment"]["overall_invalidity_strength"] == "strong"
        assert data["invalidity_assessment"]["reasoning"] == "Authorized invalidity reasoning"

    @pytest.mark.asyncio
    async def test_detail_query_filters_to_completed_reports_with_source_span_provenance(self):
        db = AsyncMock()
        db.execute.return_value = _mock_mappings_first(None)

        with pytest.raises(APIError):
            await get_patent_detail_for_org(
                db,
                patent_id="US-10000001-B2",
                org_id=uuid.uuid4(),
                risk_ratings_restricted=False,
            )

        sql = str(db.execute.await_args.args[0])
        _assert_report_provenance_predicates(sql)
        assert "ORDER BY a.completed_at DESC, a.id DESC" in sql
