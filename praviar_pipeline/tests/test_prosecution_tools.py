"""Tests for ProsecutionToolkit — dispatch, formatting, and error handling."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("praviar_pipeline.agents.tools.prosecution_tools")

from praviar_pipeline.agents.tools.prosecution_tools import ProsecutionToolkit

# ── tool_definitions ────────────────────────────────────────────────────────


class TestToolDefinitions:
    def test_returns_six_tools(self):
        toolkit = ProsecutionToolkit()
        assert len(toolkit.tool_definitions) == 6

    def test_tool_names(self):
        names = {t["name"] for t in ProsecutionToolkit().tool_definitions}
        assert names == {
            "fetch_file_wrapper",
            "fetch_prosecution_summary",
            "fetch_assignment_chain",
            "fetch_transaction_log",
            "fetch_patent_term_detail",
            "get_patent_claims",
        }

    def test_all_tools_have_required_fields(self):
        for tool in ProsecutionToolkit().tool_definitions:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool


# ── execute dispatch ─────────────────────────────────────────────────────────


class TestExecuteDispatch:
    @pytest.mark.asyncio
    async def test_dispatches_fetch_file_wrapper(self):
        toolkit = ProsecutionToolkit()
        toolkit._fetch_file_wrapper = AsyncMock(return_value="wrapper result")
        result = await toolkit.execute("fetch_file_wrapper", {"patent_id": "US123"})
        toolkit._fetch_file_wrapper.assert_called_once_with("US123")
        assert result == "wrapper result"

    @pytest.mark.asyncio
    async def test_dispatches_fetch_prosecution_summary(self):
        toolkit = ProsecutionToolkit()
        toolkit._fetch_prosecution_summary = AsyncMock(return_value="summary")
        result = await toolkit.execute("fetch_prosecution_summary", {"patent_id": "US123"})
        toolkit._fetch_prosecution_summary.assert_called_once_with("US123")
        assert result == "summary"

    @pytest.mark.asyncio
    async def test_dispatches_fetch_assignment_chain(self):
        toolkit = ProsecutionToolkit()
        toolkit._fetch_assignment_chain = AsyncMock(return_value="chain")
        result = await toolkit.execute("fetch_assignment_chain", {"patent_id": "US123"})
        toolkit._fetch_assignment_chain.assert_called_once_with("US123")
        assert result == "chain"

    @pytest.mark.asyncio
    async def test_dispatches_get_patent_claims(self):
        toolkit = ProsecutionToolkit()
        toolkit._get_claims = AsyncMock(return_value="claims text")
        result = await toolkit.execute("get_patent_claims", {"patent_id": "US999"})
        toolkit._get_claims.assert_called_once_with("US999")
        assert result == "claims text"

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error_string(self):
        toolkit = ProsecutionToolkit()
        result = await toolkit.execute("does_not_exist", {})
        assert "Unknown tool" in result
        assert "does_not_exist" in result


# ── _fetch_file_wrapper ──────────────────────────────────────────────────────


class TestFetchFileWrapper:
    @pytest.mark.asyncio
    async def test_returns_formatted_document_list(self):
        mock_docs = [
            {
                "documentCode": "OA",
                "documentDescription": "Office Action",
                "documentDate": "2021-03-01",
            },
            {
                "documentCode": "RES",
                "documentDescription": "Response",
                "documentDate": "2021-06-01",
            },
        ]
        mock_client = AsyncMock()
        mock_client.get_file_wrapper_documents = AsyncMock(return_value=mock_docs)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("praviar_pipeline.clients.uspto_odp.USPTOODPClient", return_value=mock_ctx):
            toolkit = ProsecutionToolkit()
            result = await toolkit._fetch_file_wrapper("US123")

        assert "US123" in result
        assert "2 documents" in result
        assert "Office Action" in result
        assert "Response" in result

    @pytest.mark.asyncio
    async def test_empty_docs_returns_not_found_message(self):
        mock_client = AsyncMock()
        mock_client.get_file_wrapper_documents = AsyncMock(return_value=[])
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("praviar_pipeline.clients.uspto_odp.USPTOODPClient", return_value=mock_ctx):
            toolkit = ProsecutionToolkit()
            result = await toolkit._fetch_file_wrapper("US456")

        assert "No prosecution documents found" in result
        assert "US456" in result

    @pytest.mark.asyncio
    async def test_limits_output_to_40_docs(self):
        mock_docs = [
            {"documentCode": "OA", "documentDescription": f"Doc {i}", "documentDate": "2021-01-01"}
            for i in range(50)
        ]
        mock_client = AsyncMock()
        mock_client.get_file_wrapper_documents = AsyncMock(return_value=mock_docs)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("praviar_pipeline.clients.uspto_odp.USPTOODPClient", return_value=mock_ctx):
            toolkit = ProsecutionToolkit()
            result = await toolkit._fetch_file_wrapper("US789")

        # Header says 50 total, but only 40 listed
        assert "50 documents" in result
        lines = [line for line in result.split("\n") if line.startswith("  - ")]
        assert len(lines) == 40

    @pytest.mark.asyncio
    async def test_exception_returns_error_string(self):
        with patch(
            "praviar_pipeline.clients.uspto_odp.USPTOODPClient",
            side_effect=RuntimeError("network error"),
        ):
            toolkit = ProsecutionToolkit()
            result = await toolkit._fetch_file_wrapper("US000")

        assert "Unable to fetch file wrapper" in result
        assert "US000" in result
        assert "network error" in result


# ── _get_claims ──────────────────────────────────────────────────────────────


class TestGetClaims:
    @pytest.mark.asyncio
    async def test_returns_truncated_claims(self):
        mock_client = AsyncMock()
        mock_client.get_patent_claims = AsyncMock(return_value="B" * 15000)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("praviar_pipeline.clients.bigquery.BigQueryClient", return_value=mock_ctx):
            toolkit = ProsecutionToolkit()
            result = await toolkit._get_claims("US123")

        assert len(result) == 10000

    @pytest.mark.asyncio
    async def test_no_claims_returns_not_found(self):
        mock_client = AsyncMock()
        mock_client.get_patent_claims = AsyncMock(return_value=None)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("praviar_pipeline.clients.bigquery.BigQueryClient", return_value=mock_ctx):
            toolkit = ProsecutionToolkit()
            result = await toolkit._get_claims("US000")

        assert "No claims found" in result
        assert "US000" in result

    @pytest.mark.asyncio
    async def test_exception_returns_error_string(self):
        with patch(
            "praviar_pipeline.clients.bigquery.BigQueryClient",
            side_effect=RuntimeError("bq unavailable"),
        ):
            toolkit = ProsecutionToolkit()
            result = await toolkit._get_claims("US555")

        assert "Unable to fetch claims" in result
        assert "US555" in result
