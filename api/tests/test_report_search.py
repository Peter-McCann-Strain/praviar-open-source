"""Tests for POST /api/v1/reports/{analysis_id}/search endpoint."""

from __future__ import annotations

import re
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from conftest import (
    _build_app,
    make_analysis_mock,
    make_mock_db,
    make_user,
    valid_report_data_for_patents,
)
from httpx import ASGITransport

from api.db.models import AnalysisStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _report_with_searchable_content(**overrides) -> dict:
    """Return a report dict with content that can be searched."""
    patent_analyses = overrides.pop(
        "patent_analyses",
        [
            {
                "patent_id": "US12345678A1",
                "title": "Novel aspirin formulation with enhanced bioavailability",
                "risk_summary": (
                    "Clearance review found structural similarity and overlapping claims."
                ),
            },
            {
                "patent_id": "EP9876543B1",
                "title": "Improved ibuprofen synthesis method",
                "risk_summary": "Low risk. Claims focus on manufacturing process only.",
            },
        ],
    )
    defaults = {
        "risk_summary": {
            "overall_risk": "medium",
            "blocking_patents_count": 1,
            "total_patents_analyzed": 2,
            "key_risks": ["Aspirin formulation patent overlap"],
            "executive_summary": "The compound shows moderate risk due to aspirin patent coverage.",
        },
        "doe_assessments": [
            {
                "patent_id": "US12345678A1",
                "reasoning": (
                    "Doctrine of equivalents analysis shows potential infringement "
                    "under function-way-result test."
                ),
            },
        ],
        "invalidity_assessments": [
            {
                "patent_id": "US12345678A1",
                "reasoning": "Prior art from 1995 publication may invalidate claims 1-3.",
            },
        ],
    }
    defaults.update(overrides)
    return valid_report_data_for_patents(patent_analyses=patent_analyses, **defaults)


def _assert_analysis_lookup_was_org_scoped(db) -> None:
    """Route-level canary: analysis lookup must include id and org predicates."""
    statements = [str(call.args[0]).lower() for call in db.execute.await_args_list if call.args]
    assert any(
        "analyses.id" in statement and "analyses.org_id" in statement for statement in statements
    )


def _result_with_analysis(analysis) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = analysis
    return result


def _statement_binds_column_to_value(
    statement,
    *,
    column_sql: str,
    expected: uuid.UUID,
) -> bool:
    compiled = statement.compile()
    sql = str(compiled).lower()
    param_names = re.findall(
        rf"{re.escape(column_sql.lower())}\s*=\s*:([a-zA-Z_][a-zA-Z0-9_]*)",
        sql,
    )
    return any(str(compiled.params.get(param_name)) == str(expected) for param_name in param_names)


def _is_analysis_lookup_for_user_org(
    statement,
    *,
    analysis_id: uuid.UUID,
    user_org_id: uuid.UUID,
) -> bool:
    sql = str(statement).lower()
    return (
        "analyses.id =" in sql
        and "analyses.org_id =" in sql
        and _statement_binds_column_to_value(
            statement,
            column_sql="analyses.id",
            expected=analysis_id,
        )
        and _statement_binds_column_to_value(
            statement,
            column_sql="analyses.org_id",
            expected=user_org_id,
        )
    )


def _install_cross_org_report_tripwire(
    db,
    *,
    analysis_id: uuid.UUID,
    user_org_id: uuid.UUID,
    victim_analysis,
) -> dict[str, bool]:
    """Return victim row unless the query is scoped to the requesting org."""
    state = {"saw_secure_lookup": False}

    async def _execute(statement, *_args, **_kwargs):
        if _is_analysis_lookup_for_user_org(
            statement,
            analysis_id=analysis_id,
            user_org_id=user_org_id,
        ):
            state["saw_secure_lookup"] = True
            return _result_with_analysis(None)
        return _result_with_analysis(victim_analysis)

    db.execute = AsyncMock(side_effect=_execute)
    return state


async def _post_report_search_with_user(user, db, analysis_id: uuid.UUID, query: str):
    app = _build_app(user, db)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.post(
            f"/api/v1/reports/{analysis_id}/search",
            json={"query": query},
        )


# ---------------------------------------------------------------------------
# POST /api/v1/reports/{id}/search — keyword search
# ---------------------------------------------------------------------------


class TestSearchReportKeywords:
    """POST /api/v1/reports/{analysis_id}/search"""

    @pytest.mark.asyncio
    async def test_search_report_keywords(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(
            id=analysis_id,
            report_data=_report_with_searchable_content(),
        )
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        with patch(
            "api.routes.reports.get_settings",
            return_value=SimpleNamespace(require_attorney_role_for_risk_ratings=False),
        ):
            resp = await c.post(
                f"/api/v1/reports/{analysis_id}/search",
                json={"query": "aspirin"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "aspirin"
        assert data["total"] > 0
        assert len(data["results"]) > 0

    @pytest.mark.asyncio
    async def test_search_report_empty_query(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()

        resp = await c.post(
            f"/api/v1/reports/{analysis_id}/search",
            json={"query": ""},
        )
        assert resp.status_code == 422  # Pydantic validation (min_length=2)

    @pytest.mark.asyncio
    async def test_search_report_short_query(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()

        resp = await c.post(
            f"/api/v1/reports/{analysis_id}/search",
            json={"query": "a"},
        )
        assert resp.status_code == 422  # Pydantic validation (min_length=2)

    @pytest.mark.asyncio
    async def test_search_report_not_found(self, scientist_client):
        c, db = scientist_client
        db.execute.return_value.scalar_one_or_none.return_value = None

        resp = await c.post(
            f"/api/v1/reports/{uuid.uuid4()}/search",
            json={"query": "aspirin"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_search_report_cross_org_returns_404_without_payload(self):
        analysis_id = uuid.uuid4()
        user_org_id = uuid.uuid4()
        victim_analysis = make_analysis_mock(
            id=analysis_id,
            org_id=uuid.uuid4(),
            report_data=_report_with_searchable_content(
                patent_analyses=[
                    {
                        "patent_id": "US91000010A1",
                        "title": "cross-tenant-private-compound formulation",
                        "risk_summary": "Victim-only report content.",
                    }
                ]
            ),
        )
        db = make_mock_db()
        lookup_state = _install_cross_org_report_tripwire(
            db,
            analysis_id=analysis_id,
            user_org_id=user_org_id,
            victim_analysis=victim_analysis,
        )
        user = make_user(org_id=user_org_id)

        with (
            patch(
                "api.routes.reports.get_settings",
                return_value=SimpleNamespace(require_attorney_role_for_risk_ratings=False),
            ),
            patch(
                "api.services.report_content_search.search_report_content_impl"
            ) as search_content,
        ):
            resp = await _post_report_search_with_user(
                user,
                db,
                analysis_id,
                "cross-tenant-private-compound",
            )

        assert resp.status_code == 404
        body = resp.json()
        assert body["detail"] == "Analysis not found"
        assert "cross-tenant-private-compound" not in resp.text
        search_content.assert_not_called()
        assert lookup_state["saw_secure_lookup"] is True
        _assert_analysis_lookup_was_org_scoped(db)

    @pytest.mark.asyncio
    async def test_search_report_redacted_cross_org_denies_before_searching_payload(
        self,
    ):
        analysis_id = uuid.uuid4()
        user_org_id = uuid.uuid4()
        victim_analysis = make_analysis_mock(
            id=analysis_id,
            org_id=uuid.uuid4(),
            report_data=_report_with_searchable_content(
                risk_summary={
                    "overall_risk": "high",
                    "blocking_patents_count": 1,
                    "total_patents_analyzed": 1,
                    "key_risks": ["cross-tenant-risk-language"],
                    "executive_summary": "cross-tenant-risk-language",
                },
            ),
        )
        db = make_mock_db()
        lookup_state = _install_cross_org_report_tripwire(
            db,
            analysis_id=analysis_id,
            user_org_id=user_org_id,
            victim_analysis=victim_analysis,
        )
        user = make_user(org_id=user_org_id)

        with (
            patch(
                "api.routes.reports.get_settings",
                return_value=SimpleNamespace(require_attorney_role_for_risk_ratings=True),
            ),
            patch("api.routes.reports._search_report_content") as search_content,
            patch("api.routes.reports._search_report_for_org") as search_report_for_org,
        ):
            resp = await _post_report_search_with_user(
                user,
                db,
                analysis_id,
                "cross-tenant-risk-language",
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Analysis not found"
        assert "cross-tenant-risk-language" not in resp.text
        search_content.assert_not_called()
        search_report_for_org.assert_not_called()
        assert lookup_state["saw_secure_lookup"] is True
        _assert_analysis_lookup_was_org_scoped(db)

    @pytest.mark.asyncio
    async def test_search_report_no_report_data(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(id=analysis_id, report_data=None)
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.post(
            f"/api/v1/reports/{analysis_id}/search",
            json={"query": "aspirin"},
        )
        assert resp.status_code == 404
        assert "Report not yet available" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_search_report_rejects_redacted_non_completed_report_payload(
        self,
        scientist_client,
    ):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(
            id=analysis_id,
            status=AnalysisStatus.RUNNING,
            report_data=_report_with_searchable_content(),
        )
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        with (
            patch(
                "api.routes.reports.get_settings",
                return_value=SimpleNamespace(require_attorney_role_for_risk_ratings=True),
            ),
            patch("api.routes.reports._search_report_content") as search_content,
        ):
            resp = await c.post(
                f"/api/v1/reports/{analysis_id}/search",
                json={"query": "aspirin"},
            )

        assert resp.status_code == 404
        assert "Report not yet available" in resp.json()["detail"]
        search_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_report_uses_redacted_report_for_non_attorney_when_required(
        self,
        scientist_client,
    ):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(
            id=analysis_id,
            report_data=_report_with_searchable_content(
                patent_analyses=[
                    {
                        "patent_id": "US12345678A1",
                        "title": "Aspirin formulation",
                        "risk_summary": "Restricted structural similarity risk language.",
                    }
                ],
                risk_summary={
                    "overall_risk": "high",
                    "blocking_patents_count": 1,
                    "total_patents_analyzed": 1,
                    "key_risks": ["Restricted structural similarity risk language."],
                    "executive_summary": "Restricted structural similarity risk language.",
                },
            ),
        )
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        with patch(
            "api.routes.reports.get_settings",
            return_value=SimpleNamespace(require_attorney_role_for_risk_ratings=True),
        ):
            resp = await c.post(
                f"/api/v1/reports/{analysis_id}/search",
                json={"query": "structural similarity"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["results"] == []


class TestSearchReturnsSnippets:
    """Verify that search results include context snippets."""

    @pytest.mark.asyncio
    async def test_search_returns_snippets(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(
            id=analysis_id,
            report_data=_report_with_searchable_content(),
        )
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.post(
            f"/api/v1/reports/{analysis_id}/search",
            json={"query": "aspirin"},
        )

        assert resp.status_code == 200
        data = resp.json()
        for result in data["results"]:
            assert "snippet" in result
            assert len(result["snippet"]) > 0
            assert "relevance" in result
            assert "section" in result

    @pytest.mark.asyncio
    async def test_search_results_sorted_by_relevance(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(
            id=analysis_id,
            report_data=_report_with_searchable_content(),
        )
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.post(
            f"/api/v1/reports/{analysis_id}/search",
            json={"query": "aspirin"},
        )

        assert resp.status_code == 200
        data = resp.json()
        relevances = [r["relevance"] for r in data["results"]]
        assert relevances == sorted(relevances, reverse=True)


class TestSearchMultipleSections:
    """Search should cover patent analyses, executive summary, DOE, and invalidity."""

    @pytest.mark.asyncio
    async def test_search_multiple_sections(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(
            id=analysis_id,
            report_data=_report_with_searchable_content(),
        )
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        # "clearance" appears in patent-analysis risk prose and the governed summary.
        with patch(
            "api.routes.reports.get_settings",
            return_value=SimpleNamespace(require_attorney_role_for_risk_ratings=False),
        ):
            resp = await c.post(
                f"/api/v1/reports/{analysis_id}/search",
                json={"query": "clearance"},
            )

        assert resp.status_code == 200
        data = resp.json()
        sections_found = {r["section"] for r in data["results"]}
        # At minimum, should find in patent_analysis and executive_summary
        assert "patent_analysis" in sections_found
        assert "executive_summary" in sections_found

    @pytest.mark.asyncio
    async def test_search_doe_section(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(
            id=analysis_id,
            report_data=_report_with_searchable_content(),
        )
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.post(
            f"/api/v1/reports/{analysis_id}/search",
            json={"query": "equivalents"},
        )

        assert resp.status_code == 200
        data = resp.json()
        sections_found = {r["section"] for r in data["results"]}
        assert "doe_assessment" in sections_found

    @pytest.mark.asyncio
    async def test_search_invalidity_section(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(
            id=analysis_id,
            report_data=_report_with_searchable_content(),
        )
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.post(
            f"/api/v1/reports/{analysis_id}/search",
            json={"query": "prior art"},
        )

        assert resp.status_code == 200
        data = resp.json()
        sections_found = {r["section"] for r in data["results"]}
        assert "invalidity_assessment" in sections_found

    @pytest.mark.asyncio
    async def test_search_no_results(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(
            id=analysis_id,
            report_data=_report_with_searchable_content(),
        )
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.post(
            f"/api/v1/reports/{analysis_id}/search",
            json={"query": "zzzznonexistentzzz"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["results"] == []

    @pytest.mark.asyncio
    async def test_search_interpreted_query(self, scientist_client):
        c, db = scientist_client
        analysis_id = uuid.uuid4()
        analysis = make_analysis_mock(
            id=analysis_id,
            report_data=_report_with_searchable_content(),
        )
        db.execute.return_value.scalar_one_or_none.return_value = analysis

        resp = await c.post(
            f"/api/v1/reports/{analysis_id}/search",
            json={"query": "aspirin"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "interpreted_query" in data
        assert "aspirin" in data["interpreted_query"]
