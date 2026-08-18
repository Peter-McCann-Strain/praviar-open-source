from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from praviar_pipeline.models.patent import LegalStatus, PatentTermInfo
from praviar_pipeline.tools import FTOToolkit
from praviar_pipeline.tools_cache import build_known_patent_cache


@pytest.mark.asyncio
async def test_execute_current_date_returns_utc() -> None:
    toolkit = FTOToolkit()

    result = await toolkit.execute("get_current_date", {})

    assert "UTC" in result


@pytest.mark.asyncio
async def test_lookup_patent_uses_cache(mock_settings) -> None:
    toolkit = FTOToolkit(
        known_patents={
            "US123": {
                "title": "Example Title",
                "abstract": "Abstract text",
                "filing_date": "2020-01-01",
                "assignee": "Acme",
            }
        }
    )

    result = await toolkit.execute("lookup_patent", {"patent_id": "US123"})

    assert "Patent: US123" in result
    assert "Title: Example Title" in result
    assert "Assignee: Acme" in result


@pytest.mark.asyncio
async def test_check_patent_status_falls_back_to_cache() -> None:
    toolkit = FTOToolkit(
        known_patents={
            "US555": {
                "filing_date": "2018-01-01",
                "assignee": "Fallback Corp",
                "legal_status": "active",
                "expiry_date": "2038-01-01",
                "legal_events": [{"date": "2024-01-01", "description": "Maintenance fee paid"}],
            }
        }
    )

    with patch(
        "praviar_pipeline.clients.uspto_odp.USPTOODPClient",
        side_effect=RuntimeError("ODP unavailable"),
    ):
        result = await toolkit.execute("check_patent_status", {"patent_id": "US555"})

    assert "Patent: US555 (from cached pipeline data)" in result
    assert "Expected Expiry: 2038-01-01" in result
    assert "Fallback Corp" in result


def test_tool_definition_filtering() -> None:
    toolkit = FTOToolkit(enabled_tools=["get_current_date", "lookup_patent"])

    assert [tool["name"] for tool in toolkit.tool_definitions] == [
        "get_current_date",
        "lookup_patent",
    ]


def test_build_known_patent_cache_uses_adjusted_expiry(mock_settings) -> None:
    patent = SimpleNamespace(
        patent_id="US777",
        title="Adjusted Expiry Patent",
        abstract="Summary",
        filing_date=date(2010, 1, 1),
        assignees=["Acme"],
        claims_text="claim text",
        legal_status=LegalStatus.ACTIVE,
        legal_events=[],
        patent_term_info=PatentTermInfo(
            patent_id="US777",
            adjusted_expiry=date(2031, 1, 1),
        ),
    )

    cache = build_known_patent_cache([patent], claims_truncation=50)

    assert cache["US777"]["expiry_date"] == "2031-01-01"


@pytest.mark.asyncio
async def test_execute_unknown_tool_returns_error() -> None:
    toolkit = FTOToolkit()

    result = await toolkit.execute("unknown_tool", {})

    assert "Unknown tool" in result
