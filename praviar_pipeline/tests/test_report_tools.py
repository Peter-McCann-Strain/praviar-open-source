"""Tests for ReportToolkit — pure logic and execute dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("praviar_pipeline.agents.tools.report_tools")

from praviar_pipeline.agents.tools.report_tools import ReportToolkit

SAMPLE_CLAIMS = """\
1. A method comprising:
   reacting compound A with compound B in a reactor;
   filtering the product.

2. The method of claim 1, wherein compound A is succinic acid.

3. The method of claim 1, wherein the reactor operates at 80-120 degrees C.

10. A composition comprising succinic acid and at least one salt.
"""


# ── _lookup_patent ─────────────────────────────────────────────────────────


class TestLookupPatent:
    def test_returns_cached_metadata(self):
        cache = {
            "US1234B2": {
                "title": "Fermentation process",
                "assignee": "BioFirm SA",
                "risk_level": "high",
            }
        }
        toolkit = ReportToolkit(patent_cache=cache)
        result = toolkit._lookup_patent("US1234B2")
        assert "US1234B2" in result
        assert "Fermentation process" in result
        assert "BioFirm SA" in result
        assert "high" in result

    def test_missing_patent_returns_fallback(self):
        toolkit = ReportToolkit()
        result = toolkit._lookup_patent("USNONE")
        assert "No data cached" in result
        assert "USNONE" in result

    def test_only_known_keys_extracted(self):
        cache = {"US5B2": {"title": "X", "secret_field": "should_not_appear"}}
        toolkit = ReportToolkit(patent_cache=cache)
        result = toolkit._lookup_patent("US5B2")
        assert "secret_field" not in result


# ── _verify_claim_text ─────────────────────────────────────────────────────


class TestVerifyClaimText:
    @pytest.mark.asyncio
    async def test_extracts_specific_claim(self):
        toolkit = ReportToolkit()
        mock_bq = AsyncMock()
        mock_bq.get_patent_claims = AsyncMock(return_value=SAMPLE_CLAIMS)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_bq)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.clients.bigquery.BigQueryClient",
            return_value=mock_ctx,
        ):
            result = await toolkit._verify_claim_text("US1B2", claim_number=2)

        assert "Claim 2" in result
        assert "succinic acid" in result

    @pytest.mark.asyncio
    async def test_returns_all_claims_when_no_number_given(self):
        toolkit = ReportToolkit()
        mock_bq = AsyncMock()
        mock_bq.get_patent_claims = AsyncMock(return_value=SAMPLE_CLAIMS)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_bq)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.clients.bigquery.BigQueryClient",
            return_value=mock_ctx,
        ):
            result = await toolkit._verify_claim_text("US1B2")

        assert "Claims for US1B2" in result
        assert "succinic acid" in result

    @pytest.mark.asyncio
    async def test_returns_fallback_when_no_claims_found(self):
        toolkit = ReportToolkit()
        mock_bq = AsyncMock()
        mock_bq.get_patent_claims = AsyncMock(return_value=None)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_bq)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.clients.bigquery.BigQueryClient",
            return_value=mock_ctx,
        ):
            result = await toolkit._verify_claim_text("US_EMPTY")

        assert "No claims text found" in result

    @pytest.mark.asyncio
    async def test_returns_graceful_message_when_claim_not_found(self):
        toolkit = ReportToolkit()
        mock_bq = AsyncMock()
        mock_bq.get_patent_claims = AsyncMock(return_value=SAMPLE_CLAIMS)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_bq)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.clients.bigquery.BigQueryClient",
            return_value=mock_ctx,
        ):
            result = await toolkit._verify_claim_text("US1B2", claim_number=999)

        assert "Could not extract claim 999" in result

    @pytest.mark.asyncio
    async def test_graceful_on_bigquery_error(self):
        toolkit = ReportToolkit()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("BQ unavailable"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.clients.bigquery.BigQueryClient",
            return_value=mock_ctx,
        ):
            result = await toolkit._verify_claim_text("US_ERR")

        assert "Failed to verify claims" in result


# ── execute dispatch ────────────────────────────────────────────────────────


class TestExecuteDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_lookup_patent(self):
        cache = {"US9B2": {"title": "Biomass process"}}
        toolkit = ReportToolkit(patent_cache=cache)
        result = await toolkit.execute("lookup_patent", {"patent_id": "US9B2"})
        assert "Biomass process" in result

    @pytest.mark.asyncio
    async def test_dispatch_verify_claim_text(self):
        toolkit = ReportToolkit()
        mock_bq = AsyncMock()
        mock_bq.get_patent_claims = AsyncMock(return_value=SAMPLE_CLAIMS)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_bq)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.clients.bigquery.BigQueryClient",
            return_value=mock_ctx,
        ):
            result = await toolkit.execute("verify_claim_text", {"patent_id": "US1B2"})
        assert "Claims for US1B2" in result

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool(self):
        toolkit = ReportToolkit()
        result = await toolkit.execute("nonexistent", {})
        assert "Unknown tool" in result


# ── tool_definitions structure ──────────────────────────────────────────────


class TestToolDefinitions:
    def test_returns_two_tools(self):
        toolkit = ReportToolkit()
        defs = toolkit.tool_definitions
        assert len(defs) == 2

    def test_all_tools_have_required_fields(self):
        toolkit = ReportToolkit()
        for tool in toolkit.tool_definitions:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    def test_tool_names_are_expected(self):
        toolkit = ReportToolkit()
        names = {t["name"] for t in toolkit.tool_definitions}
        assert names == {"verify_claim_text", "lookup_patent"}
