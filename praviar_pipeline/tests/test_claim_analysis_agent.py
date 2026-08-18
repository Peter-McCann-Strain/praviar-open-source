"""Tests for ClaimAnalysisAgent and PatentResearchToolkit."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("praviar_pipeline.agents.tools.patent_tools")


class TestPatentResearchToolkit:
    """Tests for the patent specification retrieval toolkit."""

    def test_tool_definitions_count(self):
        from praviar_pipeline.agents.tools.patent_tools import PatentResearchToolkit

        toolkit = PatentResearchToolkit()
        assert len(toolkit.tool_definitions) == 3

    def test_tool_names(self):
        from praviar_pipeline.agents.tools.patent_tools import PatentResearchToolkit

        toolkit = PatentResearchToolkit()
        names = {t["name"] for t in toolkit.tool_definitions}
        assert names == {"fetch_specification", "search_spec_definitions", "lookup_patent"}

    @pytest.mark.asyncio
    async def test_fetch_specification_caches(self):
        """Test that spec text is cached after first fetch."""
        from praviar_pipeline.agents.tools.patent_tools import PatentResearchToolkit

        mock_bq = AsyncMock()
        mock_bq.get_patent_full_text = AsyncMock(return_value="Spec text here")
        mock_bq.__aenter__ = AsyncMock(return_value=mock_bq)
        mock_bq.__aexit__ = AsyncMock(return_value=False)

        toolkit = PatentResearchToolkit()

        with patch("praviar_pipeline.clients.bigquery.BigQueryClient", return_value=mock_bq):
            result1 = await toolkit.execute("fetch_specification", {"patent_id": "US123"})
            result2 = await toolkit.execute("fetch_specification", {"patent_id": "US123"})

        assert "Spec text here" in result1
        assert result1 == result2
        # BigQuery should only be called once (cached)
        mock_bq.get_patent_full_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search_definitions_finds_patterns(self):
        """Test definitional pattern matching in specification."""
        from praviar_pipeline.agents.tools.patent_tools import PatentResearchToolkit

        spec_text = (
            "Background of the invention\n\n"
            'As used herein, the term "compound" refers to any chemical substance '
            "with a defined molecular formula.\n\n"
            "Another paragraph about something else.\n\n"
            "The compound may be selected from organic acids."
        )
        toolkit = PatentResearchToolkit()
        toolkit._spec_cache["US123"] = spec_text

        result = await toolkit.execute(
            "search_spec_definitions",
            {"patent_id": "US123", "term": "compound"},
        )
        assert "as used herein" in result.lower() or "relevant paragraph" in result.lower()

    @pytest.mark.asyncio
    async def test_search_definitions_no_spec(self):
        """Test graceful handling when no spec is cached."""
        from praviar_pipeline.agents.tools.patent_tools import PatentResearchToolkit

        mock_bq = AsyncMock()
        mock_bq.get_patent_full_text = AsyncMock(return_value="")
        mock_bq.__aenter__ = AsyncMock(return_value=mock_bq)
        mock_bq.__aexit__ = AsyncMock(return_value=False)

        toolkit = PatentResearchToolkit()

        with patch("praviar_pipeline.clients.bigquery.BigQueryClient", return_value=mock_bq):
            result = await toolkit.execute(
                "search_spec_definitions",
                {"patent_id": "US999", "term": "compound"},
            )
        assert "no specification" in result.lower() or "no" in result.lower()

    def test_lookup_patent_from_cache(self):
        """Test patent lookup returns cached metadata."""
        from praviar_pipeline.agents.tools.patent_tools import PatentResearchToolkit

        cache = {"US123": {"title": "Test Patent", "assignee": "TestCorp"}}
        toolkit = PatentResearchToolkit(patent_cache=cache)

        result = toolkit._lookup_patent("US123")
        assert "Test Patent" in result
        assert "TestCorp" in result

    def test_lookup_patent_not_in_cache(self):
        from praviar_pipeline.agents.tools.patent_tools import PatentResearchToolkit

        toolkit = PatentResearchToolkit()
        result = toolkit._lookup_patent("US999")
        assert "no cached data" in result.lower()

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        from praviar_pipeline.agents.tools.patent_tools import PatentResearchToolkit

        toolkit = PatentResearchToolkit()
        result = await toolkit.execute("nonexistent", {})
        assert "unknown tool" in result.lower()


class TestClaimAnalysisAgent:
    """Tests for the ClaimAnalysisAgent subclass."""

    def test_agent_type(self):
        from praviar_pipeline.agents.claim_analysis import ClaimAnalysisAgent

        with patch("praviar_pipeline.agents.base.get_settings") as mock:
            mock.return_value = MagicMock(
                agentic_max_agent_rounds=5,
                agentic_observation_masking=True,
                agentic_scratchpad_enabled=True,
            )
            agent = ClaimAnalysisAgent(MagicMock())
            assert agent.agent_type == "claim_analysis"

    def test_model_id_is_deep(self):
        from praviar_pipeline.agents.claim_analysis import ClaimAnalysisAgent

        with patch("praviar_pipeline.agents.base.get_settings") as mock:
            settings = MagicMock()
            settings.claude_deep_model = "claude-opus-4-6"
            mock.return_value = settings
            with patch(
                "praviar_pipeline.agents.claim_analysis.get_settings", return_value=settings
            ):
                agent = ClaimAnalysisAgent(MagicMock())
                assert agent.model_id == "claude-opus-4-6"

    def test_max_rounds(self):
        from praviar_pipeline.agents.claim_analysis import ClaimAnalysisAgent

        with patch("praviar_pipeline.agents.base.get_settings") as mock:
            mock.return_value = MagicMock(
                agentic_max_agent_rounds=5,
                agentic_observation_masking=True,
                agentic_scratchpad_enabled=True,
            )
            agent = ClaimAnalysisAgent(MagicMock())
            assert agent.max_rounds == 5

    def test_format_task_includes_sections(self):
        from praviar_pipeline.agents.claim_analysis import ClaimAnalysisAgent

        with patch("praviar_pipeline.agents.base.get_settings") as mock:
            mock.return_value = MagicMock(
                agentic_max_agent_rounds=5,
                agentic_observation_masking=True,
                agentic_scratchpad_enabled=True,
            )
            agent = ClaimAnalysisAgent(MagicMock())
            task_text = agent.format_task(
                "Analyze patent",
                {
                    "compound_context": "Succinic acid — C4H6O4",
                    "patent_context": "US7851188B2 — Fermentation method",
                    "claims_text": "1. A method of producing...",
                },
            )
            assert 'type="compound_context"' in task_text
            assert 'type="patent_context"' in task_text
            assert 'type="pre_parsed_claims"' in task_text or 'type="claims_text"' in task_text
            assert "Succinic acid" in task_text

    def test_build_toolkit_returns_patent_toolkit(self):
        from praviar_pipeline.agents.claim_analysis import ClaimAnalysisAgent
        from praviar_pipeline.agents.tools.patent_tools import PatentResearchToolkit

        with patch("praviar_pipeline.agents.base.get_settings") as mock:
            mock.return_value = MagicMock(
                agentic_max_agent_rounds=5,
                agentic_observation_masking=True,
                agentic_scratchpad_enabled=True,
            )
            agent = ClaimAnalysisAgent(MagicMock())
            toolkit = agent.build_toolkit({"patent_data": {"US123": {"title": "Test"}}})
            assert isinstance(toolkit, PatentResearchToolkit)
