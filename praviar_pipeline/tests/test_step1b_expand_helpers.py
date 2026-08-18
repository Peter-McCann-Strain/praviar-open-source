from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest

from praviar_pipeline.clients.claude import ClaudeClient
from praviar_pipeline.errors import ConfigurationError, SourceUnavailableError
from praviar_pipeline.models.search import ExpandedSearchQueries, ExpandedSearchQueryTerms
from praviar_pipeline.pipeline.step1b_expand_helpers import (
    ExpansionToolkit,
    expand_with_search_agent,
    expand_without_search,
    query_expansion_requires_grounding,
    run_query_expansion,
    validate_cpc_code,
)


def test_validate_cpc_code_matches_expected_patterns() -> None:
    assert validate_cpc_code("C12P7/46")
    assert validate_cpc_code("A61K31/00")
    assert not validate_cpc_code("INVALID")
    assert not validate_cpc_code("Z99")


async def test_expansion_toolkit_formats_search_results() -> None:
    tavily = MagicMock()
    tavily.search = AsyncMock(
        return_value=[
            {
                "title": "Result A",
                "url": "https://example.test/a",
                "content": "A" * 500,
            },
            {
                "title": "Result B",
                "url": "https://example.test/b",
                "content": "short",
            },
        ]
    )

    toolkit = ExpansionToolkit(tavily)

    assert toolkit.tool_definitions[0]["name"] == "web_search"

    formatted_text = await toolkit.execute("web_search", {"query": "succinic acid cpc"})

    assert "**Result A**" in formatted_text
    assert "**Result B**" in formatted_text
    assert "\n\n---\n\n" in formatted_text
    assert "A" * 401 not in formatted_text
    assert "Source: https://example.test/a" in formatted_text
    assert toolkit.grounding_queries == ["succinic acid cpc"]
    assert toolkit.source_urls == ["https://example.test/a", "https://example.test/b"]


async def test_expansion_toolkit_propagates_required_tavily_source_errors() -> None:
    tavily = MagicMock()
    tavily.search = AsyncMock(side_effect=SourceUnavailableError("tavily", "offline"))

    toolkit = ExpansionToolkit(tavily, required=True)

    with pytest.raises(SourceUnavailableError):
        await toolkit.execute("web_search", {"query": "succinic acid cpc"})

    assert tavily.search.await_args.kwargs["required"] is True


async def test_expand_without_search_uses_structured_completion() -> None:
    client = create_autospec(ClaudeClient, instance=True)
    expected = ExpandedSearchQueries(patent_synonyms=["amber acid"])
    client.complete.return_value = (expected, {"input_tokens": 12, "output_tokens": 4})
    settings = SimpleNamespace(claude_triage_model="test-model")

    result = await expand_without_search(
        client,
        "system prompt",
        "Compound: succinic acid",
        settings,
    )

    assert result.patent_synonyms == expected.patent_synonyms
    assert result.provenance.origin == "model_without_live_grounding"
    call_kwargs = client.complete.call_args.kwargs
    assert call_kwargs["response_model"] is ExpandedSearchQueryTerms
    assert "Generate expanded patent search queries" in call_kwargs["user"]


async def test_expand_with_search_agent_falls_back_on_invalid_json() -> None:
    client = create_autospec(ClaudeClient, instance=True)
    client.complete_text.return_value = ("not json", {"input_tokens": 20, "output_tokens": 5})
    expected = ExpandedSearchQueries(cpc_codes=["C12P7/46"])
    client.complete.return_value = (expected, {"input_tokens": 14, "output_tokens": 6})
    settings = SimpleNamespace(claude_triage_model="test-model")

    tavily = MagicMock()
    tavily.search = AsyncMock(return_value=[])

    result = await expand_with_search_agent(
        client,
        "system prompt",
        "Compound: succinic acid",
        tavily,
        settings,
    )

    assert result.cpc_codes == expected.cpc_codes
    client.complete_text.assert_called_once()
    client.complete.assert_called_once()


async def test_expand_with_search_agent_grounded_fallback_uses_prose_as_context() -> None:
    """When grounding is required but tool-loop returns prose, constrained decoding
    is called with the prose embedded as context — grounding is preserved."""
    client = create_autospec(ClaudeClient, instance=True)

    async def _grounded_complete_text(**kwargs):
        await kwargs["toolkit"].execute(
            "web_search",
            {"query": "aspirin CPC patent classification"},
        )
        return (
            "Aspirin patents relate to ...",
            {"input_tokens": 20, "output_tokens": 5},
        )

    client.complete_text.side_effect = _grounded_complete_text
    expected = ExpandedSearchQueries(cpc_codes=["A61K31/60"])
    client.complete.return_value = (expected, {"input_tokens": 30, "output_tokens": 8})
    settings = SimpleNamespace(claude_triage_model="test-model", trust_mode="counsel")

    tavily = MagicMock()
    tavily.search = AsyncMock(
        return_value=[
            {
                "title": "grounded",
                "url": "https://example.test/aspirin-cpc",
                "content": "snippet",
            }
        ]
    )

    result = await expand_with_search_agent(
        client,
        "system prompt",
        "Compound: succinic acid",
        tavily,
        settings,
    )

    assert result.cpc_codes == expected.cpc_codes
    assert result.provenance.grounded is True
    assert result.provenance.source_urls == ["https://example.test/aspirin-cpc"]
    client.complete_text.assert_called_once()
    # complete() must be called and the user prompt must embed the prose
    client.complete.assert_called_once()
    user_arg = client.complete.call_args.kwargs["user"]
    assert "Compound: succinic acid" in user_arg
    assert "Aspirin patents relate to" in user_arg
    assert (
        '<untrusted_source_data type="model_web_research_summary" encoding="xml-escaped-text">'
    ) in user_arg
    assert "</untrusted_source_data>" in user_arg
    assert "<web_research_summary>" not in user_arg


async def test_expand_with_search_agent_bounds_large_grounding_provenance() -> None:
    """Many tool results must not invalidate an otherwise valid expansion."""
    client = create_autospec(ClaudeClient, instance=True)

    async def _many_grounding_calls(**kwargs):
        for index in range(25):
            await kwargs["toolkit"].execute(
                "web_search",
                {"query": f"tavaborole patent query {index}"},
            )
        return (
            '{"patent_synonyms":["AN2690"]}',
            {"input_tokens": 20, "output_tokens": 5},
        )

    client.complete_text.side_effect = _many_grounding_calls
    settings = SimpleNamespace(claude_triage_model="test-model", trust_mode="counsel")
    tavily = MagicMock()

    async def _search(query, **_kwargs):
        index = query.rsplit(" ", 1)[-1]
        return [
            {
                "title": f"result-{index}-{result_index}",
                "url": f"https://example.test/{index}/{result_index}",
                "content": "grounded evidence",
            }
            for result_index in range(5)
        ]

    tavily.search.side_effect = _search

    result = await expand_with_search_agent(
        client,
        "system prompt",
        "Compound: tavaborole",
        tavily,
        settings,
    )

    assert result.patent_synonyms == ["AN2690"]
    assert len(result.provenance.grounding_queries) == 20
    assert len(result.provenance.source_urls) == 100
    assert client.complete_text.call_args.kwargs["max_rounds"] == 4


async def test_required_search_agent_rejects_available_but_unused_grounding_tool() -> None:
    client = create_autospec(ClaudeClient, instance=True)
    client.complete_text.return_value = (
        '{"patent_synonyms":["aspirin"]}',
        {"input_tokens": 20, "output_tokens": 5},
    )
    settings = SimpleNamespace(claude_triage_model="test-model", trust_mode="counsel")
    tavily = MagicMock()
    tavily.search = AsyncMock(return_value=[])

    with pytest.raises(SourceUnavailableError, match="no live grounding evidence"):
        await expand_with_search_agent(
            client,
            "system prompt",
            "Compound: aspirin",
            tavily,
            settings,
        )


async def test_run_query_expansion_requires_tavily_for_counsel_grade_grounding() -> None:
    client = create_autospec(ClaudeClient, instance=True)
    tavily = MagicMock()
    tavily.available = False
    settings = SimpleNamespace(claude_triage_model="test-model", trust_mode="counsel")

    with pytest.raises(ConfigurationError) as excinfo:
        await run_query_expansion(
            client,
            "system prompt",
            "Compound: succinic acid",
            tavily,
            settings,
        )

    assert excinfo.value.source == "tavily"


def test_query_expansion_grounding_requirement_policy() -> None:
    assert query_expansion_requires_grounding(SimpleNamespace(trust_mode="counsel"))
    assert query_expansion_requires_grounding(
        SimpleNamespace(required_record_components=["claims_text"])
    )
    assert not query_expansion_requires_grounding(SimpleNamespace(trust_mode="explorer"))
