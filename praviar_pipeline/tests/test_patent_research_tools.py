"""Tests for PatentResearchToolkit — pure logic and execute dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("praviar_pipeline.agents.tools.patent_tools")

from praviar_pipeline.agents.tools.patent_tools import PatentResearchToolkit

# ── _lookup_patent ─────────────────────────────────────────────────────────


class TestLookupPatent:
    def test_returns_metadata_from_cache(self):
        cache = {
            "US1234567B2": {
                "title": "Method for making X",
                "assignee": "Acme Corp",
                "filing_date": "2020-01-15",
                "grant_date": "2022-06-01",
            }
        }
        toolkit = PatentResearchToolkit(patent_cache=cache)
        result = toolkit._lookup_patent("US1234567B2")
        assert "US1234567B2" in result
        assert "Method for making X" in result
        assert "Acme Corp" in result
        assert "2020-01-15" in result

    def test_truncates_long_values(self):
        cache = {"US999B2": {"title": "X" * 600}}
        toolkit = PatentResearchToolkit(patent_cache=cache)
        result = toolkit._lookup_patent("US999B2")
        # title should be truncated to 500 chars
        assert len(result) < 700

    def test_missing_patent_returns_fallback_message(self):
        toolkit = PatentResearchToolkit()
        result = toolkit._lookup_patent("US0000000A1")
        assert "No cached data" in result
        assert "US0000000A1" in result

    def test_empty_cache_returns_fallback(self):
        toolkit = PatentResearchToolkit(patent_cache={})
        result = toolkit._lookup_patent("EP1234567A1")
        # Points user to fetch_specification as next step
        assert "fetch_specification" in result

    def test_non_dict_cache_entry_still_works(self):
        # If value is not a dict, only the patent ID line should appear
        cache = {"US111": "some string value"}
        toolkit = PatentResearchToolkit(patent_cache=cache)
        result = toolkit._lookup_patent("US111")
        assert "US111" in result

    def test_ignores_empty_field_values(self):
        cache = {"US555B2": {"title": "", "assignee": "Pfizer"}}
        toolkit = PatentResearchToolkit(patent_cache=cache)
        result = toolkit._lookup_patent("US555B2")
        assert "Pfizer" in result
        # empty title should not appear as "title: "
        assert "title:" not in result


# ── _search_definitions ────────────────────────────────────────────────────


class TestSearchDefinitions:
    """Tests for the pure-regex definition search logic."""

    @pytest.mark.asyncio
    async def test_finds_as_used_herein_pattern(self):
        toolkit = PatentResearchToolkit()
        toolkit._spec_cache["US1"] = (
            "As used herein, 'reactor' means a vessel for chemical reactions."
        )
        result = await toolkit._search_definitions("US1", "reactor")
        assert "reactor" in result.lower()
        assert "Found" in result

    @pytest.mark.asyncio
    async def test_finds_the_term_means_pattern(self):
        toolkit = PatentResearchToolkit()
        toolkit._spec_cache["US2"] = (
            "The term 'catalyst' means a substance that increases reaction rate without being consumed."
        )
        result = await toolkit._search_definitions("US2", "catalyst")
        assert "Found" in result
        assert "catalyst" in result.lower()

    @pytest.mark.asyncio
    async def test_fallback_returns_paragraphs_mentioning_term(self):
        # No definitional pattern — should use fallback (any paragraph with term)
        toolkit = PatentResearchToolkit()
        toolkit._spec_cache["US3"] = (
            "The polymer is applied as a thin film.\n\n"
            "The polymer thickness ranges from 1-10 nm.\n\n"
            "The polymer exhibits high tensile strength."
        )
        result = await toolkit._search_definitions("US3", "polymer")
        assert "polymer" in result.lower()

    @pytest.mark.asyncio
    async def test_no_spec_available_returns_graceful_message(self):
        toolkit = PatentResearchToolkit()
        # No spec cached, no BigQuery — will try to fetch which will fail
        mock_bq = AsyncMock()
        mock_bq.get_patent_full_text = AsyncMock(return_value=None)
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_bq)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        with patch("praviar_pipeline.clients.bigquery.BigQueryClient", return_value=mock_ctx):
            result = await toolkit._search_definitions("USNOTFOUND", "term")
        assert "No specification available" in result

    @pytest.mark.asyncio
    async def test_term_not_found_in_spec(self):
        toolkit = PatentResearchToolkit()
        toolkit._spec_cache["US4"] = "This patent relates to chemical synthesis of compounds."
        result = await toolkit._search_definitions("US4", "robotics")
        assert "No explicit definition found" in result

    @pytest.mark.asyncio
    async def test_result_truncated_to_max_chars(self):
        toolkit = PatentResearchToolkit()
        # Inject a spec with many definition paragraphs
        long_para = "As used herein, 'widget' means " + ("x" * 700)
        spec = "\n\n".join([long_para] * 20)
        toolkit._spec_cache["US5"] = spec
        result = await toolkit._search_definitions("US5", "widget")
        assert len(result) <= 10000  # _MAX_DEFINITION_CHARS


# ── _fetch_specification ───────────────────────────────────────────────────


class TestFetchSpecification:
    @pytest.mark.asyncio
    async def test_returns_cached_spec_without_bigquery(self):
        toolkit = PatentResearchToolkit()
        toolkit._spec_cache["US10"] = "A" * 25000
        result = await toolkit._fetch_specification("US10")
        assert len(result) <= 80000  # _MAX_SPEC_CHARS; 25K cache fits fully
        # BigQuery was NOT called
        assert result == "A" * 25000  # Full cache returned (under 80K limit)

    @pytest.mark.asyncio
    async def test_fetches_from_bigquery_and_caches(self):
        toolkit = PatentResearchToolkit()
        mock_bq = AsyncMock()
        mock_bq.get_patent_full_text = AsyncMock(return_value="Spec text for US20")
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_bq)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        with patch("praviar_pipeline.clients.bigquery.BigQueryClient", return_value=mock_ctx):
            result = await toolkit._fetch_specification("US20")
        assert result == "Spec text for US20"
        assert "US20" in toolkit._spec_cache

    @pytest.mark.asyncio
    async def test_graceful_on_bigquery_error(self):
        toolkit = PatentResearchToolkit()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("Connection refused"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        with patch("praviar_pipeline.clients.bigquery.BigQueryClient", return_value=mock_ctx):
            result = await toolkit._fetch_specification("US_ERR")
        assert result == "Specification retrieval failed with a provider or validation error"
        assert "Connection refused" not in result
        assert "US_ERR" not in result


# ── execute dispatch ────────────────────────────────────────────────────────


class TestExecuteDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_to_lookup_patent(self):
        cache = {"US1B2": {"title": "Test Patent"}}
        toolkit = PatentResearchToolkit(patent_cache=cache)
        result = await toolkit.execute("lookup_patent", {"patent_id": "US1B2"})
        assert "Test Patent" in result

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool(self):
        toolkit = PatentResearchToolkit()
        result = await toolkit.execute("nonexistent_tool", {})
        assert "Unknown tool" in result

    @pytest.mark.asyncio
    async def test_dispatch_fetch_specification_uses_cache(self):
        toolkit = PatentResearchToolkit()
        toolkit._spec_cache["US999B2"] = "X" * 25000  # already cached
        result = await toolkit.execute("fetch_specification", {"patent_id": "US999B2"})
        assert len(result) <= 80_000  # _MAX_SPEC_CHARS

    @pytest.mark.asyncio
    async def test_dispatch_search_spec_definitions(self):
        toolkit = PatentResearchToolkit()
        toolkit._spec_cache["US100"] = "As used herein, 'widget' means a small device."
        result = await toolkit.execute(
            "search_spec_definitions", {"patent_id": "US100", "term": "widget"}
        )
        assert "widget" in result.lower()


# ── tool_definitions structure ──────────────────────────────────────────────


class TestToolDefinitions:
    def test_returns_three_tools(self):
        toolkit = PatentResearchToolkit()
        defs = toolkit.tool_definitions
        assert len(defs) == 3

    def test_all_tools_have_required_fields(self):
        toolkit = PatentResearchToolkit()
        for tool in toolkit.tool_definitions:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert "required" in tool["input_schema"]

    def test_tool_names_are_expected(self):
        toolkit = PatentResearchToolkit()
        names = {t["name"] for t in toolkit.tool_definitions}
        assert names == {"fetch_specification", "search_spec_definitions", "lookup_patent"}
