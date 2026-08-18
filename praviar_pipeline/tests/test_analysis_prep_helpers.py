"""Tests for analysis prep helper utilities."""

from __future__ import annotations

from praviar_pipeline.models.patent import PatentHit
from praviar_pipeline.models.triage import Relevance, TriageResult
from praviar_pipeline.pipeline.analysis.prep_helpers import (
    build_enabled_analysis_tools,
    build_triage_map,
    filter_us_patents,
    format_amendments_summary,
    format_continuity_summary,
    format_office_actions_summary,
)


def _patent(pid: str) -> PatentHit:
    return PatentHit(
        patent_id=pid,
        title="Test",
        claims_text="",
    )


def test_build_triage_map_empty() -> None:
    assert build_triage_map(None) == {}


def test_build_triage_map_populates_keys() -> None:
    triage = TriageResult(patent_id="US1", relevance=Relevance.RELEVANT, reason="yes")
    assert build_triage_map([triage]) == {"US1": triage}


def test_build_enabled_analysis_tools() -> None:
    assert build_enabled_analysis_tools(tools_enabled=False, has_uspto_odp_api_key=False) is None
    assert build_enabled_analysis_tools(tools_enabled=True, has_uspto_odp_api_key=False) == [
        "get_current_date",
        "lookup_patent",
    ]
    assert build_enabled_analysis_tools(tools_enabled=True, has_uspto_odp_api_key=True) == [
        "get_current_date",
        "lookup_patent",
        "check_patent_status",
    ]


def test_format_office_actions_summary() -> None:
    summary = format_office_actions_summary(
        [
            {
                "documentCode": "NFOA",
                "documentDescription": "Non-Final Office Action",
                "mailDate": "2024-01-01",
            },
        ]
    )
    assert summary == "- [NFOA] Non-Final Office Action (2024-01-01)"


def test_format_continuity_summary() -> None:
    summary = format_continuity_summary(
        [
            {
                "parentApplicationNumberText": "123456",
                "claimTypeCd": "CIP",
                "filingDate": "2024-01-01",
            }
        ]
    )
    assert summary == "- Parent: 123456 (CIP, filed 2024-01-01)"


def test_format_amendments_summary() -> None:
    summary, count = format_amendments_summary(
        [
            {
                "transactionCode": "AMND",
                "transactionDescription": "Amendment filed",
                "transactionDate": "2024-01-02",
            },
            {
                "transactionCode": "X",
                "transactionDescription": "Unrelated entry",
            },
        ]
    )
    assert summary == "- [AMND] Amendment filed (2024-01-02)"
    assert count == 1


def test_filter_us_patents() -> None:
    hits = [_patent("US1"), _patent("EP1"), _patent("us2")]
    assert [hit.patent_id for hit in filter_us_patents(hits)] == ["US1", "us2"]
