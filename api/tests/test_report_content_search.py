"""Focused tests for report content search helpers."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from conftest import bind_report_data, valid_report_data, valid_report_data_for_patents

from api.db.models import AnalysisStatus
from api.errors import APIError
from api.services.report_content_search import (
    filter_risk_ratings_impl,
    search_report_content_impl,
    search_report_for_org_impl,
)
from api.services.report_content_search_helpers import _build_snippet


def test_filter_risk_ratings_impl_redacts_attorney_only_sections():
    report = valid_report_data(
        patent_analyses=[
            {
                "patent_id": "US12345678A1",
                "title": "Novel aspirin formulation",
                "risk_summary": "High risk due to scaffold overlap.",
                "design_around_suggestions": ["Try salt form"],
            }
        ],
        action_items=["Talk to counsel"],
    )

    filtered = filter_risk_ratings_impl(report)

    assert "action_items" not in filtered
    assert "clearance_decision" not in filtered
    assert "jurisdiction_decisions" not in filtered
    assert "prosecution_dossiers" not in filtered
    assert "claim_construction_record" not in filtered
    assert "future_risk" not in filtered
    assert "commercial_exposure" not in filtered
    assert "claim_program_decisions" not in filtered
    assert "evidence_artifacts" not in filtered
    assert "evidence_adapter_results" not in filtered
    assert "collector_runs" not in filtered
    assert "evidence_collection_plan" not in filtered
    assert "coverage_gaps" not in filtered
    assert "matter_graph" not in filtered
    assert "matter_graph_summary" not in filtered
    assert "matter_store" not in filtered
    assert "authority_coverage" not in filtered
    assert "record_completeness" not in filtered
    assert "run_observability" not in filtered
    assert "matter_evidence_index" not in filtered
    assert "critic_report" not in filtered
    assert "pending_collection_directives" not in filtered["search_loop_result"]
    assert (
        "evidence_collection_directives"
        not in filtered["search_loop_result"]["iteration_logs"][0]["assessment"]
    )
    assert (
        "evidence_collection_directives" not in filtered["search_loop_result"]["final_assessment"]
    )
    assert "risk_summary" not in filtered["patent_analyses"][0]
    assert "design_around_suggestions" not in filtered["patent_analyses"][0]


def test_search_report_content_impl_limits_and_sorts_results():
    report = valid_report_data(
        patent_analyses=[
            {
                "patent_id": f"US{i:08d}A1",
                "title": f"Aspirin formulation {i}",
                "risk_summary": "Aspirin overlap.",
            }
            for i in range(25)
        ]
    )

    results = search_report_content_impl(report, "aspirin")

    assert results["total"] == 25
    assert len(results["results"]) == 20
    assert results["results"][0]["relevance"] >= results["results"][-1]["relevance"]


def test_search_report_content_impl_includes_all_supported_sections():
    report = valid_report_data(
        patent_analyses=[
            {
                "patent_id": "US12345678A1",
                "title": "Aspirin formulation",
                "risk_summary": "Aspirin overlap in the scaffold.",
            },
            "ignore me",
        ],
        risk_summary={
            "executive_summary": "Aspirin drives the overall risk assessment.",
        },
        doe_assessments=[
            {
                "patent_id": "US12345678A1",
                "reasoning": "DOE analysis mentions aspirin equivalence.",
            },
            None,
        ],
        invalidity_assessments=[
            {
                "patent_id": "US12345678A1",
                "reasoning": "Aspirin prior art remains relevant.",
            }
        ],
    )

    results = search_report_content_impl(report, "aspirin")

    assert results["total"] == 4
    assert [item["section"] for item in results["results"]] == [
        "patent_analysis",
        "executive_summary",
        "doe_assessment",
        "invalidity_assessment",
    ]


def test_build_snippet_trims_middle_matches_with_ellipses():
    snippet = _build_snippet("alpha beta gamma delta epsilon", "gamma", padding=5)

    assert snippet == "...beta gamma delt..."


@pytest.mark.asyncio
async def test_search_report_for_org_impl_raises_when_report_missing(mock_db):
    get_analysis_for_org = AsyncMock(
        return_value=SimpleNamespace(status=AnalysisStatus.COMPLETED, report_data=None)
    )

    with pytest.raises(APIError) as exc_info:
        await search_report_for_org_impl(
            mock_db,
            analysis_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            query_text="aspirin",
            get_analysis_for_org_fn=get_analysis_for_org,
        )

    assert exc_info.value.status == 404


@pytest.mark.asyncio
async def test_search_report_for_org_impl_rejects_non_completed_report_payload(mock_db):
    get_analysis_for_org = AsyncMock(
        return_value=SimpleNamespace(
            status=AnalysisStatus.RUNNING,
            report_data=valid_report_data(),
        )
    )

    with pytest.raises(APIError) as exc_info:
        await search_report_for_org_impl(
            mock_db,
            analysis_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            query_text="aspirin",
            get_analysis_for_org_fn=get_analysis_for_org,
        )

    assert exc_info.value.status == 404


@pytest.mark.asyncio
async def test_search_report_for_org_impl_rejects_unsupported_material_assertions(mock_db):
    report = valid_report_data()
    report["patent_analyses"].append(
        {
            "patent_id": "US99999999A1",
            "title": "Unsupported orphan patent",
            "risk_level": "high",
            "risk_summary": "This unsupported orphan patent should never be searchable.",
        }
    )
    get_analysis_for_org = AsyncMock(
        return_value=SimpleNamespace(status=AnalysisStatus.COMPLETED, report_data=report)
    )

    with pytest.raises(APIError) as exc_info:
        await search_report_for_org_impl(
            mock_db,
            analysis_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            query_text="orphan",
            get_analysis_for_org_fn=get_analysis_for_org,
        )

    assert exc_info.value.status == 404
    assert exc_info.value.detail == "Report not yet available"


@pytest.mark.asyncio
async def test_search_report_for_org_impl_searches_loaded_report(mock_db):
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    report = valid_report_data_for_patents(
        patent_analyses=[
            {
                "patent_id": "US12345678A1",
                "title": "Aspirin formulation",
                "risk_summary": "Aspirin overlap.",
            }
        ]
    )
    bind_report_data(report, analysis_id=analysis_id, org_id=org_id)
    analysis = SimpleNamespace(
        id=analysis_id,
        org_id=org_id,
        status=AnalysisStatus.COMPLETED,
        report_data=report,
    )
    get_analysis_for_org = AsyncMock(return_value=analysis)

    results = await search_report_for_org_impl(
        mock_db,
        analysis_id=analysis_id,
        org_id=org_id,
        query_text="aspirin",
        get_analysis_for_org_fn=get_analysis_for_org,
    )

    assert results["total"] == 1
    assert results["results"][0]["section"] == "patent_analysis"
