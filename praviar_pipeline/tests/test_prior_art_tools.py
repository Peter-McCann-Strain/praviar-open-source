"""Tests for PriorArtToolkit and checkpoint utilities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("praviar_pipeline.agents.tools.prior_art_tools")

from praviar_pipeline.agents.tools.prior_art_tools import PriorArtToolkit

from praviar_pipeline.models.hitl import CheckpointType, HITLConfig
from praviar_pipeline.pipeline.checkpoints import (
    _is_blocking,
    _serialize_context,
    await_checkpoint,
)

# ── PriorArtToolkit.tool_definitions ─────────────────────────────────────────


class TestToolDefinitions:
    def test_returns_three_tools(self):
        assert len(PriorArtToolkit().tool_definitions) == 3

    def test_tool_names(self):
        names = {t["name"] for t in PriorArtToolkit().tool_definitions}
        assert names == {
            "search_patent_prior_art",
            "search_scholarly",
            "fetch_examiner_citations",
        }

    def test_search_patent_prior_art_requires_cpc_and_date(self):
        schema = next(
            t for t in PriorArtToolkit().tool_definitions if t["name"] == "search_patent_prior_art"
        )
        assert "cpc_codes" in schema["input_schema"]["required"]
        assert "before_date" in schema["input_schema"]["required"]

    def test_search_scholarly_requires_query(self):
        schema = next(
            t for t in PriorArtToolkit().tool_definitions if t["name"] == "search_scholarly"
        )
        assert schema["input_schema"]["required"] == ["query"]


# ── execute dispatch ──────────────────────────────────────────────────────────


class TestExecuteDispatch:
    @pytest.mark.asyncio
    async def test_dispatches_search_patent_prior_art(self):
        toolkit = PriorArtToolkit()
        toolkit._search_patent_prior_art = AsyncMock(return_value="patent results")
        result = await toolkit.execute(
            "search_patent_prior_art",
            {"cpc_codes": ["C07C"], "before_date": "2018-01-01", "keywords": ["acid"]},
        )
        toolkit._search_patent_prior_art.assert_called_once_with(["C07C"], "2018-01-01", ["acid"])
        assert result == "patent results"

    @pytest.mark.asyncio
    async def test_dispatches_search_scholarly(self):
        toolkit = PriorArtToolkit()
        toolkit._search_scholarly = AsyncMock(return_value="papers")
        result = await toolkit.execute(
            "search_scholarly", {"query": "succinic acid synthesis", "before_year": 2015}
        )
        toolkit._search_scholarly.assert_called_once_with("succinic acid synthesis", 2015)
        assert result == "papers"

    @pytest.mark.asyncio
    async def test_dispatches_fetch_examiner_citations(self):
        toolkit = PriorArtToolkit()
        toolkit._fetch_examiner_citations = AsyncMock(return_value="citations")
        result = await toolkit.execute("fetch_examiner_citations", {"patent_id": "US999"})
        toolkit._fetch_examiner_citations.assert_called_once_with("US999")
        assert result == "citations"

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error_string(self):
        toolkit = PriorArtToolkit()
        result = await toolkit.execute("nope", {})
        assert "Unknown tool" in result
        assert "nope" in result

    @pytest.mark.asyncio
    async def test_scholarly_defaults_before_year_to_none(self):
        toolkit = PriorArtToolkit()
        toolkit._search_scholarly = AsyncMock(return_value="ok")
        await toolkit.execute("search_scholarly", {"query": "aspirin"})
        toolkit._search_scholarly.assert_called_once_with("aspirin", None)


# ── _search_patent_prior_art ──────────────────────────────────────────────────


class TestSearchPatentPriorArt:
    @pytest.mark.asyncio
    async def test_formats_results(self):
        mock_results = [
            {
                "publication_number": "US8765432B2",
                "title": "Method for biofermentation",
                "filing_date": "2010-05-20",
            },
            {
                "publication_number": "EP3456789A1",
                "title": "Succinic acid production",
                "filing_date": "2012-09-01",
            },
        ]
        mock_client = AsyncMock()
        mock_client.search_by_cpc_and_keywords = AsyncMock(return_value=mock_results)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("praviar_pipeline.clients.bigquery.BigQueryClient", return_value=mock_ctx):
            toolkit = PriorArtToolkit()
            result = await toolkit._search_patent_prior_art(
                ["C12P7/44"], "2015-01-01", ["fermentation"]
            )

        assert "2 potential prior art references" in result
        assert "US8765432B2" in result
        assert "biofermentation" in result

    @pytest.mark.asyncio
    async def test_limits_output_to_10(self):
        mock_results = [
            {"publication_number": f"US{i}B2", "title": f"Patent {i}", "filing_date": "2010-01-01"}
            for i in range(15)
        ]
        mock_client = AsyncMock()
        mock_client.search_by_cpc_and_keywords = AsyncMock(return_value=mock_results)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("praviar_pipeline.clients.bigquery.BigQueryClient", return_value=mock_ctx):
            toolkit = PriorArtToolkit()
            result = await toolkit._search_patent_prior_art(["C07C"], "2015-01-01", [])

        lines = [line for line in result.split("\n") if line.strip().startswith("-")]
        assert len(lines) == 10

    @pytest.mark.asyncio
    async def test_empty_results_returns_no_found_message(self):
        mock_client = AsyncMock()
        mock_client.search_by_cpc_and_keywords = AsyncMock(return_value=[])
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("praviar_pipeline.clients.bigquery.BigQueryClient", return_value=mock_ctx):
            toolkit = PriorArtToolkit()
            result = await toolkit._search_patent_prior_art(["C07C"], "2015-01-01", [])

        assert "No prior art patents found" in result

    @pytest.mark.asyncio
    async def test_exception_returns_error_string(self):
        with patch(
            "praviar_pipeline.clients.bigquery.BigQueryClient",
            side_effect=RuntimeError("bq down"),
        ):
            toolkit = PriorArtToolkit()
            result = await toolkit._search_patent_prior_art(["C07C"], "2010-01-01", [])

        assert "Prior art search failed" in result
        assert "bq down" in result


# ── _search_scholarly ────────────────────────────────────────────────────────


class TestSearchScholarly:
    @pytest.mark.asyncio
    async def test_formats_results(self):
        mock_papers = [
            {"title": "Succinic acid biosynthesis review", "year": 2010, "doi": "10.1234/x"},
            {"title": "Organic acid fermentation", "year": 2008, "doi": "10.5678/y"},
        ]
        mock_client = AsyncMock()
        mock_client.search = AsyncMock(return_value=mock_papers)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.clients.semantic_scholar.SemanticScholarClient",
            return_value=mock_ctx,
        ):
            toolkit = PriorArtToolkit()
            result = await toolkit._search_scholarly("succinic acid biosynthesis", None)

        assert "2 scholarly references" in result
        assert "Succinic acid biosynthesis review" in result
        assert "10.1234/x" in result

    @pytest.mark.asyncio
    async def test_empty_results_returns_no_found_message(self):
        mock_client = AsyncMock()
        mock_client.search = AsyncMock(return_value=[])
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.clients.semantic_scholar.SemanticScholarClient",
            return_value=mock_ctx,
        ):
            toolkit = PriorArtToolkit()
            result = await toolkit._search_scholarly("very obscure query", None)

        assert "No scholarly references found" in result

    @pytest.mark.asyncio
    async def test_exception_returns_error_string(self):
        with patch(
            "praviar_pipeline.clients.semantic_scholar.SemanticScholarClient",
            side_effect=ImportError("not installed"),
        ):
            toolkit = PriorArtToolkit()
            result = await toolkit._search_scholarly("query", 2010)

        assert "Scholarly search failed" in result


# ── _fetch_examiner_citations ────────────────────────────────────────────────


class TestFetchExaminerCitations:
    @pytest.mark.asyncio
    async def test_formats_examiner_and_applicant_refs(self):
        mock_client = AsyncMock()
        mock_client.get_examiner_citations = AsyncMock(
            return_value={
                "examiner": ["US1234567", "EP9876543"],
                "applicant": ["WO2010001234"],
            }
        )
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("praviar_pipeline.clients.bigquery.BigQueryClient", return_value=mock_ctx):
            toolkit = PriorArtToolkit()
            result = await toolkit._fetch_examiner_citations("US999B2")

        assert "US999B2" in result
        assert "Examiner-cited (2)" in result
        assert "Applicant-cited (1)" in result
        assert "US1234567" in result

    @pytest.mark.asyncio
    async def test_no_citations_returns_not_found(self):
        mock_client = AsyncMock()
        mock_client.get_examiner_citations = AsyncMock(
            return_value={"examiner": [], "applicant": []}
        )
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("praviar_pipeline.clients.bigquery.BigQueryClient", return_value=mock_ctx):
            toolkit = PriorArtToolkit()
            result = await toolkit._fetch_examiner_citations("US000")

        assert "No citation data found" in result

    @pytest.mark.asyncio
    async def test_exception_returns_error_string(self):
        with patch(
            "praviar_pipeline.clients.bigquery.BigQueryClient",
            side_effect=RuntimeError("bq timeout"),
        ):
            toolkit = PriorArtToolkit()
            result = await toolkit._fetch_examiner_citations("US555")

        assert "Citation fetch failed" in result


# ── checkpoints._is_blocking ─────────────────────────────────────────────────


class TestIsBlocking:
    def test_analysis_review_is_blocking(self):
        assert _is_blocking(CheckpointType.ANALYSIS_REVIEW) is True

    def test_report_review_is_blocking(self):
        assert _is_blocking(CheckpointType.REPORT_REVIEW) is True

    def test_search_review_is_not_blocking(self):
        assert _is_blocking(CheckpointType.SEARCH_REVIEW) is False

    def test_triage_review_is_not_blocking(self):
        assert _is_blocking(CheckpointType.TRIAGE_REVIEW) is False


# ── checkpoints._serialize_context ───────────────────────────────────────────


class TestSerializeContext:
    def test_passes_through_short_values(self):
        ctx = {"key": "short value", "num": 42}
        result = _serialize_context(ctx)
        assert result["key"] == "short value"
        assert result["num"] == 42

    def test_truncates_long_list(self):
        ctx = {"patents": list(range(50))}
        result = _serialize_context(ctx)
        assert len(result["patents"]) == 20
        assert result["patents_total"] == 50

    def test_short_list_not_truncated(self):
        ctx = {"items": [1, 2, 3]}
        result = _serialize_context(ctx)
        assert result["items"] == [1, 2, 3]
        assert "items_total" not in result

    def test_truncates_long_string(self):
        long_str = "x" * 6000
        ctx = {"text": long_str}
        result = _serialize_context(ctx)
        assert len(result["text"]) < 6000
        assert result["text"].endswith("... [truncated]")

    def test_short_string_not_truncated(self):
        ctx = {"text": "hello world"}
        result = _serialize_context(ctx)
        assert result["text"] == "hello world"

    def test_empty_context(self):
        assert _serialize_context({}) == {}


# ── await_checkpoint ──────────────────────────────────────────────────────────


class TestAwaitCheckpoint:
    @pytest.mark.asyncio
    async def test_returns_none_when_hitl_disabled(self):
        config = HITLConfig(enabled=False)
        result = await await_checkpoint(CheckpointType.TRIAGE_REVIEW, {}, None, config)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_checkpoint_not_in_config(self):
        config = HITLConfig(enabled=True, checkpoints=[CheckpointType.ANALYSIS_REVIEW])
        result = await await_checkpoint(CheckpointType.TRIAGE_REVIEW, {}, None, config)
        assert result is None

    @pytest.mark.asyncio
    async def test_non_blocking_returns_none(self):
        config = HITLConfig(enabled=True, checkpoints=[CheckpointType.TRIAGE_REVIEW])
        callback_calls = []

        def on_progress(step, name, event, payload):
            callback_calls.append((step, name, event, payload))

        result = await await_checkpoint(
            CheckpointType.TRIAGE_REVIEW, {"data": "x"}, on_progress, config
        )
        assert result is None
        assert len(callback_calls) == 1
        assert callback_calls[0][2] == "checkpoint"

    @pytest.mark.asyncio
    async def test_blocking_returns_review_required_decision(self):
        config = HITLConfig(enabled=True, checkpoints=[CheckpointType.ANALYSIS_REVIEW])
        result = await await_checkpoint(CheckpointType.ANALYSIS_REVIEW, {}, None, config)
        assert result is not None
        assert result.action == "review_required"
        assert "persisted human decision" in result.notes

    @pytest.mark.asyncio
    async def test_callback_receives_context(self):
        config = HITLConfig(enabled=True, checkpoints=[CheckpointType.TRIAGE_REVIEW])
        received = []

        def on_progress(step, name, event, payload):
            received.append(payload)

        await await_checkpoint(
            CheckpointType.TRIAGE_REVIEW,
            {"patents": ["US123"]},
            on_progress,
            config,
        )
        assert len(received) == 1
        assert received[0]["checkpoint_type"] == CheckpointType.TRIAGE_REVIEW.value
