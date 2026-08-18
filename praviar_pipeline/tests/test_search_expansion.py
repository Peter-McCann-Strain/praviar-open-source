"""Tests for patent search expansion (Step 1.5) and expanded search sources.

Covers:
1. ExpandedSearchQueries model construction, defaults, extra field handling
2. expand_search_queries pipeline step (success + failure)
3. BigQuery CPC search (search_by_cpc_and_keywords)
4. BigQuery assignee search (search_by_assignee)
5. EPO search (search_published_data)
6. _bq_row_to_patent_hit helper
7. PatentSource enum new values
8. search_patents integration with expanded_queries
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest

from praviar_pipeline.clients.claude import ClaudeClient
from praviar_pipeline.config import clear_settings_cache
from praviar_pipeline.errors import ConfigurationError, SourceUnavailableError
from praviar_pipeline.models.patent import PatentSource
from praviar_pipeline.models.search import ExpandedSearchQueries, ExpandedSearchQueryTerms


@pytest.fixture(autouse=True)
def _allow_bigquery_in_tests():
    """Suppress the NO_PAID_API guard for BigQueryClient so tests can inject mock clients."""
    with patch("praviar_pipeline.clients.bigquery.assert_paid_api_allowed"):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sdq_patent(pub_num: str, title: str = "", **kwargs) -> dict:
    """Helper to create a minimal SDQ result dict."""
    pat = {"publicationnumber": pub_num, "title": title}
    pat.update(kwargs)
    return pat


def _make_bq_row(pub_num: str, title: str = "BQ Patent", **kwargs) -> dict:
    """Helper to create a BigQuery result row."""
    row = {
        "publication_number": pub_num,
        "title": title,
        "abstract": f"Abstract of {pub_num}",
        "claims_text": f"Claims of {pub_num}",
        "filing_date": None,
        "grant_date": None,
        "priority_date": None,
        "assignee_harmonized": [],
        "inventor_harmonized": [],
        "cpc_codes": [],
    }
    row.update(kwargs)
    return row


def _make_expanded_queries(**kwargs) -> ExpandedSearchQueries:
    """Helper to create ExpandedSearchQueries with common defaults."""
    defaults = {
        "patent_synonyms": ["amber acid", "C4 dicarboxylic acid"],
        "cpc_codes": ["C12P7/46", "C07C55/10"],
        "key_assignees": ["BioAmber Inc.", "Myriant Technologies"],
        "process_keywords": ["fermentation", "biosynthesis"],
        "compound_class_terms": ["dicarboxylic acid"],
    }
    defaults.update(kwargs)
    return ExpandedSearchQueries(**defaults)


def _make_claude_client_mock() -> MagicMock:
    """Create a ClaudeClient test double with sync and async methods typed correctly.

    Returns ``MagicMock`` (not ``ClaudeClient``) so that pyright lets tests
    poke at ``.return_value``/``.side_effect``/``.assert_called_once`` on the
    auto-specced method attributes. The mock still respects the ClaudeClient
    spec at runtime via ``create_autospec``.
    """
    mock_client = create_autospec(ClaudeClient, instance=True)
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False
    return mock_client


# ============================================================================
# 1. ExpandedSearchQueries model
# ============================================================================


class TestExpandedSearchQueriesModel:
    def test_construction_with_all_fields(self):
        """Model should accept all fields."""
        eq = ExpandedSearchQueries(
            patent_synonyms=["amber acid"],
            cpc_codes=["C12P7/46"],
            key_assignees=["BioAmber Inc."],
            process_keywords=["fermentation"],
            compound_class_terms=["dicarboxylic acid"],
        )
        assert eq.patent_synonyms == ["amber acid"]
        assert eq.cpc_codes == ["C12P7/46"]
        assert eq.key_assignees == ["BioAmber Inc."]
        assert eq.process_keywords == ["fermentation"]
        assert eq.compound_class_terms == ["dicarboxylic acid"]

    def test_defaults_are_empty_lists(self):
        """All fields should default to empty lists."""
        eq = ExpandedSearchQueries()
        assert eq.patent_synonyms == []
        assert eq.cpc_codes == []
        assert eq.key_assignees == []
        assert eq.process_keywords == []
        assert eq.compound_class_terms == []

    def test_extra_fields_ignored(self):
        """Extra fields should be silently ignored (extra='ignore')."""
        # Use ``model_validate`` instead of kwargs so static type-checkers
        # (pyright) don't flag the deliberately-unknown keys.
        eq = ExpandedSearchQueries.model_validate(
            {
                "patent_synonyms": ["amber acid"],
                "unknown_field": "should be ignored",
                "another_extra": 42,
            }
        )
        assert eq.patent_synonyms == ["amber acid"]
        assert not hasattr(eq, "unknown_field")
        assert not hasattr(eq, "another_extra")

    def test_partial_construction(self):
        """Should allow constructing with only some fields."""
        eq = ExpandedSearchQueries(cpc_codes=["C12P7/46"])
        assert eq.cpc_codes == ["C12P7/46"]
        assert eq.patent_synonyms == []
        assert eq.key_assignees == []

    def test_serialization_round_trip(self):
        """Model should serialize and deserialize cleanly."""
        eq = _make_expanded_queries()
        data = eq.model_dump()
        eq2 = ExpandedSearchQueries(**data)
        assert eq == eq2

    def test_model_config_extra_ignore(self):
        """ConfigDict should have extra='ignore'."""
        assert ExpandedSearchQueries.model_config.get("extra") == "ignore"


# ============================================================================
# 2. expand_search_queries pipeline step
# ============================================================================


def _mock_tavily_unavailable():
    """Create a mock TavilyClient that reports available=False."""
    mock_tavily = MagicMock()
    mock_tavily.available = False
    mock_tavily.close = AsyncMock()
    return mock_tavily


class TestExpandSearchQueries:
    async def test_success_returns_expanded_queries(self, succinic_acid, mock_settings):
        """Successful LLM call should return populated ExpandedSearchQueries."""
        from praviar_pipeline.pipeline.step1b_expand import expand_search_queries

        expected = _make_expanded_queries()
        usage = {"input_tokens": 500, "output_tokens": 200}

        mock_client = _make_claude_client_mock()
        mock_client.load_prompt.return_value = "system prompt"
        mock_client.complete.return_value = (expected, usage)

        with (
            patch(
                "praviar_pipeline.pipeline.step1b_expand.ClaudeClient",
                return_value=mock_client,
            ),
            patch(
                "praviar_pipeline.pipeline.step1b_expand.TavilyClient",
                return_value=_mock_tavily_unavailable(),
            ),
        ):
            result = await expand_search_queries(succinic_acid)

        assert result.patent_synonyms == expected.patent_synonyms
        assert result.cpc_codes == expected.cpc_codes
        assert result.provenance.origin == "model_without_live_grounding"
        assert result.cpc_codes == ["C12P7/46", "C07C55/10"]
        assert result.key_assignees == ["BioAmber Inc.", "Myriant Technologies"]

        # Verify complete() was called with correct kwargs
        mock_client.complete.assert_called_once()
        call_kwargs = mock_client.complete.call_args.kwargs
        assert call_kwargs["response_model"] is ExpandedSearchQueryTerms
        assert call_kwargs["max_tokens"] == 2048
        # Pinned to 0.0 for reproducibility (WS-2 foundation work).
        assert call_kwargs["temperature"] == 0.0

    async def test_failure_returns_empty_queries(self, succinic_acid, mock_settings):
        """LLM failure should return empty ExpandedSearchQueries, not raise."""
        from praviar_pipeline.pipeline.step1b_expand import expand_search_queries

        mock_client = _make_claude_client_mock()
        mock_client.load_prompt.return_value = "system prompt"
        mock_client.complete.side_effect = ConnectionError("API error")

        with (
            patch(
                "praviar_pipeline.pipeline.step1b_expand.ClaudeClient",
                return_value=mock_client,
            ),
            patch(
                "praviar_pipeline.pipeline.step1b_expand.TavilyClient",
                return_value=_mock_tavily_unavailable(),
            ),
        ):
            result = await expand_search_queries(succinic_acid)

        assert result == ExpandedSearchQueries()
        assert result.patent_synonyms == []
        assert result.cpc_codes == []

    async def test_failure_raises_when_grounding_required(self, succinic_acid, mock_settings):
        """Required grounded query expansion must fail closed instead of returning empty input."""
        from praviar_pipeline.pipeline.step1b_expand import expand_search_queries

        mock_client = _make_claude_client_mock()
        mock_client.load_prompt.return_value = "system prompt"
        mock_client.complete_text.side_effect = ConnectionError("API error")

        mock_tavily = MagicMock()
        mock_tavily.available = True
        mock_tavily.close = AsyncMock()

        with (
            patch(
                "praviar_pipeline.pipeline.step1b_expand.get_settings",
                return_value=SimpleNamespace(
                    claude_triage_model="test-model",
                    trust_mode="counsel",
                    required_record_components=[],
                ),
            ),
            patch(
                "praviar_pipeline.pipeline.step1b_expand.ClaudeClient",
                return_value=mock_client,
            ),
            patch(
                "praviar_pipeline.pipeline.step1b_expand.TavilyClient",
                return_value=mock_tavily,
            ),
        ):
            with pytest.raises(SourceUnavailableError) as excinfo:
                await expand_search_queries(succinic_acid)

        assert excinfo.value.source == "query_expansion"

    async def test_required_grounding_error_is_sanitized_without_exception_context(
        self,
        succinic_acid,
    ):
        from praviar_pipeline.pipeline.step1b_expand import expand_search_queries

        sentinel = "grounding-request-api-key-sentinel"
        provider_error = SourceUnavailableError(
            "tavily",
            f"https://provider.test/search?api_key={sentinel}",
        )
        mock_client = _make_claude_client_mock()
        mock_client.load_prompt.return_value = "system prompt"
        mock_tavily = MagicMock(available=True)
        mock_tavily.close = AsyncMock()
        recording_logger = MagicMock()

        with (
            patch(
                "praviar_pipeline.pipeline.step1b_expand.get_settings",
                return_value=SimpleNamespace(
                    claude_triage_model="test-model",
                    trust_mode="counsel",
                    required_record_components=[],
                ),
            ),
            patch(
                "praviar_pipeline.pipeline.step1b_expand.ClaudeClient",
                return_value=mock_client,
            ),
            patch(
                "praviar_pipeline.pipeline.step1b_expand.TavilyClient",
                return_value=mock_tavily,
            ),
            patch(
                "praviar_pipeline.pipeline.step1b_expand.run_query_expansion",
                new=AsyncMock(side_effect=provider_error),
            ),
            patch(
                "praviar_pipeline.pipeline.step1b_expand.logger",
                recording_logger,
            ),
            pytest.raises(SourceUnavailableError) as exc_info,
        ):
            await expand_search_queries(succinic_acid)

        error = exc_info.value
        assert str(error) == ("query_expansion unavailable: grounded query expansion failed")
        assert sentinel not in repr(error)
        assert error.__cause__ is None
        assert error.__context__ is None
        for call in recording_logger.method_calls:
            assert sentinel not in repr((call.args, call.kwargs))

    async def test_optional_grounding_source_error_may_return_empty_expansion(
        self,
        succinic_acid,
        mock_settings,
    ):
        from praviar_pipeline.pipeline.step1b_expand import expand_search_queries

        mock_client = _make_claude_client_mock()
        mock_client.load_prompt.return_value = "system prompt"
        mock_tavily = MagicMock(available=True)
        mock_tavily.close = AsyncMock()

        with (
            patch(
                "praviar_pipeline.pipeline.step1b_expand.ClaudeClient",
                return_value=mock_client,
            ),
            patch(
                "praviar_pipeline.pipeline.step1b_expand.TavilyClient",
                return_value=mock_tavily,
            ),
            patch(
                "praviar_pipeline.pipeline.step1b_expand.run_query_expansion",
                new=AsyncMock(side_effect=SourceUnavailableError("tavily", "offline")),
            ),
        ):
            result = await expand_search_queries(succinic_acid)

        assert result == ExpandedSearchQueries()

    async def test_prompt_contains_compound_info(self, succinic_acid, mock_settings):
        """The user prompt should include compound name, SMILES, and synonyms."""
        from praviar_pipeline.pipeline.step1b_expand import expand_search_queries

        expected = ExpandedSearchQueries()
        usage = {"input_tokens": 100, "output_tokens": 50}

        mock_client = _make_claude_client_mock()
        mock_client.load_prompt.return_value = "system prompt"
        mock_client.complete.return_value = (expected, usage)

        with (
            patch(
                "praviar_pipeline.pipeline.step1b_expand.ClaudeClient",
                return_value=mock_client,
            ),
            patch(
                "praviar_pipeline.pipeline.step1b_expand.TavilyClient",
                return_value=_mock_tavily_unavailable(),
            ),
        ):
            await expand_search_queries(succinic_acid)

        call_kwargs = mock_client.complete.call_args.kwargs
        user_prompt = call_kwargs["user"]
        assert "succinic acid" in user_prompt
        assert succinic_acid.canonical_smiles in user_prompt
        assert succinic_acid.molecular_formula in user_prompt

    async def test_loads_query_expansion_prompt(self, succinic_acid, mock_settings):
        """Should load the query_expansion_system.txt prompt template."""
        from praviar_pipeline.pipeline.step1b_expand import expand_search_queries

        expected = ExpandedSearchQueries()
        usage = {"input_tokens": 100, "output_tokens": 50}

        mock_client = _make_claude_client_mock()
        mock_client.load_prompt.return_value = "system prompt text"
        mock_client.complete.return_value = (expected, usage)

        with (
            patch(
                "praviar_pipeline.pipeline.step1b_expand.ClaudeClient",
                return_value=mock_client,
            ),
            patch(
                "praviar_pipeline.pipeline.step1b_expand.TavilyClient",
                return_value=_mock_tavily_unavailable(),
            ),
        ):
            await expand_search_queries(succinic_acid)

        mock_client.load_prompt.assert_called_once_with("query_expansion_system.txt")

    async def test_uses_triage_model(self, succinic_acid, mock_settings):
        """Should use the triage (Haiku) model for cost efficiency."""
        from praviar_pipeline.config import get_settings
        from praviar_pipeline.pipeline.step1b_expand import expand_search_queries

        settings = get_settings()
        expected = ExpandedSearchQueries()
        usage = {"input_tokens": 100, "output_tokens": 50}

        mock_client = _make_claude_client_mock()
        mock_client.load_prompt.return_value = "system prompt"
        mock_client.complete.return_value = (expected, usage)

        with (
            patch(
                "praviar_pipeline.pipeline.step1b_expand.ClaudeClient",
                return_value=mock_client,
            ),
            patch(
                "praviar_pipeline.pipeline.step1b_expand.TavilyClient",
                return_value=_mock_tavily_unavailable(),
            ),
        ):
            await expand_search_queries(succinic_acid)

        call_kwargs = mock_client.complete.call_args.kwargs
        assert call_kwargs["model"] == settings.claude_triage_model

    async def test_search_agent_path_when_tavily_available(self, succinic_acid, mock_settings):
        """When Tavily is available, should use complete_text with toolkit."""
        from praviar_pipeline.pipeline.step1b_expand import expand_search_queries

        json_output = (
            '{"patent_synonyms": ["amber acid"], "cpc_codes": ["C12P7/46"],'
            ' "key_assignees": ["BIOAMBER INC"], "process_keywords": ["fermentation"],'
            ' "compound_class_terms": ["dicarboxylic acid"]}'
        )
        usage = {"input_tokens": 800, "output_tokens": 300}

        mock_client = _make_claude_client_mock()
        mock_client.load_prompt.return_value = "system prompt"
        mock_client.complete_text.return_value = (json_output, usage)

        mock_tavily = MagicMock()
        mock_tavily.available = True
        mock_tavily.close = AsyncMock()

        with (
            patch(
                "praviar_pipeline.pipeline.step1b_expand.ClaudeClient",
                return_value=mock_client,
            ),
            patch(
                "praviar_pipeline.pipeline.step1b_expand.TavilyClient",
                return_value=mock_tavily,
            ),
        ):
            result = await expand_search_queries(succinic_acid)

        # Should use complete_text (not complete) when Tavily is available
        mock_client.complete_text.assert_called_once()
        mock_client.complete.assert_not_called()

        assert result.cpc_codes == ["C12P7/46"]
        assert result.key_assignees == ["BIOAMBER INC"]
        assert result.process_keywords == ["fermentation"]

    async def test_cpc_validation_strips_invalid_codes(self, succinic_acid, mock_settings):
        """CPC codes that don't match the valid format should be stripped."""
        from praviar_pipeline.pipeline.step1b_expand import expand_search_queries

        bad_expansion = ExpandedSearchQueries(
            cpc_codes=["C12P7/46", "INVALID", "C07C55/10", "not-a-code", "Z99"],
        )
        usage = {"input_tokens": 100, "output_tokens": 50}

        mock_client = _make_claude_client_mock()
        mock_client.load_prompt.return_value = "system prompt"
        mock_client.complete.return_value = (bad_expansion, usage)

        with (
            patch(
                "praviar_pipeline.pipeline.step1b_expand.ClaudeClient",
                return_value=mock_client,
            ),
            patch(
                "praviar_pipeline.pipeline.step1b_expand.TavilyClient",
                return_value=_mock_tavily_unavailable(),
            ),
        ):
            result = await expand_search_queries(succinic_acid)

        # Only valid CPC codes should survive
        assert "C12P7/46" in result.cpc_codes
        assert "C07C55/10" in result.cpc_codes
        assert "INVALID" not in result.cpc_codes
        assert "not-a-code" not in result.cpc_codes
        assert len(result.cpc_codes) == 2


# ============================================================================
# 3. BigQuery CPC search
# ============================================================================


class TestBigQueryCPCSearch:
    async def test_search_by_cpc_and_keywords_returns_rows(self, mock_settings):
        """CPC+keywords search should return matching rows."""
        from praviar_pipeline.clients.bigquery import BigQueryClient

        mock_bq = MagicMock()
        mock_bq.query_and_wait.return_value = [
            _make_bq_row("US1111111B2", title="Fermentation process"),
            _make_bq_row("US2222222B1", title="Biosynthesis method"),
        ]

        with patch(
            "praviar_pipeline.clients.bigquery._get_bq_client",
            return_value=mock_bq,
        ):
            client = BigQueryClient()
            results = await client.search_by_cpc_and_keywords(
                cpc_codes=["C12P7/46"],
                keywords=["fermentation"],
            )

        assert len(results) == 2
        assert results[0]["publication_number"] == "US1111111B2"

    async def test_search_by_cpc_empty_codes_returns_empty(self, mock_settings):
        """Empty CPC codes should return empty list immediately."""
        from praviar_pipeline.clients.bigquery import BigQueryClient

        mock_bq = MagicMock()

        with patch(
            "praviar_pipeline.clients.bigquery._get_bq_client",
            return_value=mock_bq,
        ):
            client = BigQueryClient()
            results = await client.search_by_cpc_and_keywords(
                cpc_codes=[],
                keywords=["fermentation"],
            )

        assert results == []
        # Should not have called query_and_wait
        mock_bq.query_and_wait.assert_not_called()

    async def test_search_by_cpc_without_keywords(self, mock_settings):
        """CPC search without keywords should still work (broader results)."""
        from praviar_pipeline.clients.bigquery import BigQueryClient

        mock_bq = MagicMock()
        mock_bq.query_and_wait.return_value = [
            _make_bq_row("US3333333B2"),
        ]

        with patch(
            "praviar_pipeline.clients.bigquery._get_bq_client",
            return_value=mock_bq,
        ):
            client = BigQueryClient()
            results = await client.search_by_cpc_and_keywords(
                cpc_codes=["C12P7/46"],
                keywords=[],
            )

        assert len(results) == 1

    async def test_search_by_cpc_limits_to_10_codes(self, mock_settings):
        """Should cap CPC codes at 10 to avoid SQL bloat."""
        from praviar_pipeline.clients.bigquery import BigQueryClient

        mock_bq = MagicMock()
        mock_bq.query_and_wait.return_value = []

        with patch(
            "praviar_pipeline.clients.bigquery._get_bq_client",
            return_value=mock_bq,
        ):
            client = BigQueryClient()
            cpc_codes = [f"C12P{i}/00" for i in range(20)]
            await client.search_by_cpc_and_keywords(
                cpc_codes=cpc_codes,
                keywords=["test"],
            )

        # Verify query was called (just ensure no crash with 20 codes)
        mock_bq.query_and_wait.assert_called_once()


# ============================================================================
# 4. BigQuery assignee search
# ============================================================================


class TestBigQueryAssigneeSearch:
    async def test_search_by_assignee_returns_rows(self, mock_settings):
        """Assignee search should return matching rows."""
        from praviar_pipeline.clients.bigquery import BigQueryClient

        mock_bq = MagicMock()
        mock_bq.query_and_wait.return_value = [
            _make_bq_row(
                "US4444444B2",
                title="BioAmber patent",
                assignee_harmonized=[{"name": "BioAmber Inc."}],
            ),
        ]

        with patch(
            "praviar_pipeline.clients.bigquery._get_bq_client",
            return_value=mock_bq,
        ):
            client = BigQueryClient()
            results = await client.search_by_assignee(
                assignees=["BioAmber Inc."],
            )

        assert len(results) == 1
        assert results[0]["publication_number"] == "US4444444B2"

    async def test_search_by_assignee_empty_list_returns_empty(self, mock_settings):
        """Empty assignees list should return empty immediately."""
        from praviar_pipeline.clients.bigquery import BigQueryClient

        mock_bq = MagicMock()

        with patch(
            "praviar_pipeline.clients.bigquery._get_bq_client",
            return_value=mock_bq,
        ):
            client = BigQueryClient()
            results = await client.search_by_assignee(assignees=[])

        assert results == []
        mock_bq.query_and_wait.assert_not_called()

    async def test_search_by_assignee_with_cpc_filter(self, mock_settings):
        """Assignee search with CPC filter should narrow results."""
        from praviar_pipeline.clients.bigquery import BigQueryClient

        mock_bq = MagicMock()
        mock_bq.query_and_wait.return_value = [
            _make_bq_row("US5555555B1", title="Filtered result"),
        ]

        with patch(
            "praviar_pipeline.clients.bigquery._get_bq_client",
            return_value=mock_bq,
        ):
            client = BigQueryClient()
            results = await client.search_by_assignee(
                assignees=["Myriant Technologies"],
                cpc_codes=["C12P7/46"],
            )

        assert len(results) == 1
        mock_bq.query_and_wait.assert_called_once()

    async def test_search_by_assignee_without_cpc_filter(self, mock_settings):
        """Assignee search without CPC codes should still work."""
        from praviar_pipeline.clients.bigquery import BigQueryClient

        mock_bq = MagicMock()
        mock_bq.query_and_wait.return_value = []

        with patch(
            "praviar_pipeline.clients.bigquery._get_bq_client",
            return_value=mock_bq,
        ):
            client = BigQueryClient()
            results = await client.search_by_assignee(
                assignees=["Test Corp"],
                cpc_codes=None,
            )

        assert results == []
        mock_bq.query_and_wait.assert_called_once()

    async def test_search_by_assignee_limits_to_10(self, mock_settings):
        """Should cap assignees at 10 to avoid SQL bloat."""
        from praviar_pipeline.clients.bigquery import BigQueryClient

        mock_bq = MagicMock()
        mock_bq.query_and_wait.return_value = []

        with patch(
            "praviar_pipeline.clients.bigquery._get_bq_client",
            return_value=mock_bq,
        ):
            client = BigQueryClient()
            assignees = [f"Company {i}" for i in range(20)]
            await client.search_by_assignee(assignees=assignees)

        mock_bq.query_and_wait.assert_called_once()


# ============================================================================
# 5. EPO search (search_published_data)
# ============================================================================


class TestEPOSearchPublishedData:
    async def test_search_published_data_returns_results(self, mock_settings):
        """EPO search should parse OPS response and return publication numbers."""
        from praviar_pipeline.clients.epo_ops import EPOOPSClient

        ops_response_json = {
            "ops:world-patent-data": {
                "ops:biblio-search": {
                    "ops:search-result": {
                        "ops:publication-reference": [
                            {
                                "document-id": [
                                    {
                                        "@document-id-type": "docdb",
                                        "country": {"$": "EP"},
                                        "doc-number": {"$": "1234567"},
                                        "kind": {"$": "A1"},
                                    },
                                    {
                                        "@document-id-type": "epodoc",
                                        "doc-number": {"$": "EP1234567"},
                                    },
                                ],
                            },
                        ],
                    },
                },
            },
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = ops_response_json
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response

        with patch(
            "praviar_pipeline.clients.epo_ops.EPOOPSClient._ensure_token",
            new_callable=AsyncMock,
            return_value="test-token",
        ):
            client = EPOOPSClient(client=mock_http)
            results = await client.search_published_data(
                cpc_codes=["C12P7/46"],
                claim_keywords=["succinic acid"],
            )

        assert len(results) == 1
        assert results[0]["publication_number"] == "EP1234567A1"
        assert results[0]["country"] == "EP"
        assert results[0]["doc_number"] == "1234567"

    async def test_search_published_data_no_credentials(self, mock_settings):
        """Without OPS credentials, should return empty list."""
        from praviar_pipeline.clients.epo_ops import EPOOPSClient

        mock_http = AsyncMock()
        client = EPOOPSClient(client=mock_http)
        # Clear credentials
        client._consumer_key = ""
        client._consumer_secret = ""

        results = await client.search_published_data(
            cpc_codes=["C12P7/46"],
        )

        assert results == []
        mock_http.get.assert_not_called()

    async def test_search_published_data_no_parts(self, mock_settings):
        """No CPC, keywords, or applicants should return empty list."""
        from praviar_pipeline.clients.epo_ops import EPOOPSClient

        mock_http = AsyncMock()
        client = EPOOPSClient(client=mock_http)

        results = await client.search_published_data()
        assert results == []

    async def test_search_published_data_404_returns_empty(self, mock_settings):
        """404 from EPO means no matching patents — should return empty."""
        from praviar_pipeline.clients.epo_ops import EPOOPSClient

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response

        with patch(
            "praviar_pipeline.clients.epo_ops.EPOOPSClient._ensure_token",
            new_callable=AsyncMock,
            return_value="test-token",
        ):
            client = EPOOPSClient(client=mock_http)
            results = await client.search_published_data(
                cpc_codes=["C12P7/46"],
            )

        assert results == []

    async def test_search_published_data_400_returns_empty(self, mock_settings):
        """Bad query (400) should return empty, not raise."""
        from praviar_pipeline.clients.epo_ops import EPOOPSClient

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad CQL query"

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response

        with patch(
            "praviar_pipeline.clients.epo_ops.EPOOPSClient._ensure_token",
            new_callable=AsyncMock,
            return_value="test-token",
        ):
            client = EPOOPSClient(client=mock_http)
            results = await client.search_published_data(
                cpc_codes=["INVALID"],
            )

        assert results == []

    async def test_search_published_data_single_result_dict(self, mock_settings):
        """Single result should be wrapped in list (OPS returns dict for one)."""
        from praviar_pipeline.clients.epo_ops import EPOOPSClient

        ops_response = {
            "ops:world-patent-data": {
                "ops:biblio-search": {
                    "ops:search-result": {
                        "ops:publication-reference": {
                            "document-id": {
                                "@document-id-type": "docdb",
                                "country": {"$": "US"},
                                "doc-number": {"$": "9999999"},
                                "kind": {"$": "B2"},
                            },
                        },
                    },
                },
            },
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = ops_response
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response

        with patch(
            "praviar_pipeline.clients.epo_ops.EPOOPSClient._ensure_token",
            new_callable=AsyncMock,
            return_value="test-token",
        ):
            client = EPOOPSClient(client=mock_http)
            results = await client.search_published_data(
                applicants=["BioAmber"],
            )

        assert len(results) == 1
        assert results[0]["publication_number"] == "US9999999B2"

    async def test_search_published_data_builds_cql_query(self, mock_settings):
        """CQL query should combine CPC, claim keywords, and applicants."""
        from praviar_pipeline.clients.epo_ops import EPOOPSClient

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response

        with patch(
            "praviar_pipeline.clients.epo_ops.EPOOPSClient._ensure_token",
            new_callable=AsyncMock,
            return_value="test-token",
        ):
            client = EPOOPSClient(client=mock_http)
            await client.search_published_data(
                cpc_codes=["C12P7/46"],
                claim_keywords=["succinic acid"],
                applicants=["BioAmber"],
            )

        # Verify the CQL query in the params
        call_kwargs = mock_http.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
        cql = params.get("q", "")
        assert 'cpc="C12P7/46"' in cql
        assert 'cl="succinic acid"' in cql
        assert 'pa="BioAmber"' in cql


# ============================================================================
# 6. _bq_row_to_patent_hit helper
# ============================================================================


class TestBqRowToPatentHit:
    def test_basic_conversion(self, mock_settings):
        """Should convert a BQ row to a PatentHit with correct fields."""
        from praviar_pipeline.pipeline.step2_search import _bq_row_to_patent_hit

        row = _make_bq_row(
            "US1234567B2",
            title="Test Patent",
            assignee_harmonized=[{"name": "TestCorp"}],
            cpc_codes="C12P7/46",
        )
        hit = _bq_row_to_patent_hit(row, PatentSource.CPC_SEARCH, {})

        assert hit.patent_id == "US1234567B2"
        assert hit.title == "Test Patent"
        assert hit.abstract == "Abstract of US1234567B2"
        assert hit.claims_text == "Claims of US1234567B2"
        assert PatentSource.CPC_SEARCH in hit.sources
        assert hit.assignees == ["TestCorp"]
        assert hit.cpc_codes == ["C12P7/46"]

    def test_source_map_merges_sources(self, mock_settings):
        """Existing source_map entries should be merged into the PatentHit."""
        from praviar_pipeline.pipeline.step2_search import _bq_row_to_patent_hit
        from praviar_pipeline.utils.patent_ids import normalize_patent_id

        row = _make_bq_row("US1234567B2")
        norm_id = normalize_patent_id("US1234567B2")
        source_map = {
            norm_id: {PatentSource.PUBCHEM, PatentSource.SURECHEMBL},
        }

        hit = _bq_row_to_patent_hit(row, PatentSource.CPC_SEARCH, source_map)

        assert PatentSource.CPC_SEARCH in hit.sources
        assert PatentSource.PUBCHEM in hit.sources
        assert PatentSource.SURECHEMBL in hit.sources
        # 3 sources -> confidence ~0.85
        assert hit.confidence_score >= 0.8

    @pytest.mark.parametrize(
        ("raw_value", "expected"),
        [
            pytest.param(
                [{"name": "Company A"}, {"name": "Company B"}],
                ["Company A", "Company B"],
                id="list_of_dicts",
            ),
            pytest.param(
                ["Company A", "Company B"],
                ["Company A", "Company B"],
                id="list_of_strings",
            ),
            pytest.param("not a list", [], id="non_list_falls_back_to_empty"),
        ],
    )
    def test_assignee_harmonized_normalization(self, mock_settings, raw_value, expected):
        """``assignee_harmonized`` accepts list-of-dicts, list-of-strings, and
        gracefully degrades to ``[]`` for non-list input.

        Collapses three single-input variants into one parameterized test.
        """
        from praviar_pipeline.pipeline.step2_search import _bq_row_to_patent_hit

        row = _make_bq_row("US5555555B2", assignee_harmonized=raw_value)
        hit = _bq_row_to_patent_hit(row, PatentSource.BIGQUERY, {})
        assert hit.assignees == expected

    @pytest.mark.parametrize(
        ("raw_value", "expected"),
        [
            pytest.param("C12P7/46", ["C12P7/46"], id="single_string_is_wrapped"),
            pytest.param(
                ["C12P7/46", "C07C55/10"],
                ["C12P7/46", "C07C55/10"],
                id="list_passed_through",
            ),
            pytest.param(42, [], id="non_standard_type_becomes_empty"),
        ],
    )
    def test_cpc_codes_normalization(self, mock_settings, raw_value, expected):
        """CPC codes accept str, list, and gracefully degrade for other types.

        Collapses three single-input variants into one parameterized test.
        """
        from praviar_pipeline.pipeline.step2_search import _bq_row_to_patent_hit

        row = _make_bq_row("US5555555B2", cpc_codes=raw_value)
        hit = _bq_row_to_patent_hit(row, PatentSource.BIGQUERY, {})
        assert hit.cpc_codes == expected

    def test_missing_fields_use_defaults(self, mock_settings):
        """Missing optional fields should use safe defaults."""
        from praviar_pipeline.pipeline.step2_search import _bq_row_to_patent_hit

        row = {"publication_number": "US6666666B1"}
        hit = _bq_row_to_patent_hit(row, PatentSource.ASSIGNEE_SEARCH, {})
        assert hit.patent_id == "US6666666B1"
        assert hit.title == ""
        assert hit.abstract == ""
        assert hit.assignees == []
        assert hit.cpc_codes == []


# ============================================================================
# 7. PatentSource enum — new values
# ============================================================================


_NEW_PATENT_SOURCES: tuple[tuple[str, str], ...] = (
    ("CPC_SEARCH", "cpc_search"),
    ("ASSIGNEE_SEARCH", "assignee_search"),
    ("EPO_SEARCH", "epo_search"),
)


class TestPatentSourceEnum:
    @pytest.mark.parametrize(("member_name", "value"), _NEW_PATENT_SOURCES)
    def test_new_source_value_and_str_compat(self, member_name, value):
        """Each new ``PatentSource`` member exists with the expected string
        value, is StrEnum-compatible, and is accessible via ``PatentSource``
        members.

        Collapses three ``test_*_search_exists`` tests + ``test_new_sources_are_str_enum``
        + ``test_new_sources_in_members`` into one parameterized test.
        """
        member = PatentSource[member_name]
        assert member == value
        assert isinstance(member, str)
        assert member_name in {m.name for m in PatentSource}

    def test_patent_hit_accepts_new_sources(self):
        """PatentHit should accept new source types."""
        from praviar_pipeline.models.patent import PatentHit

        hit = PatentHit(
            patent_id="US1234567B2",
            title="Test",
            sources=[PatentSource.CPC_SEARCH, PatentSource.EPO_SEARCH],
            confidence_score=0.5,
        )
        assert PatentSource.CPC_SEARCH in hit.sources
        assert PatentSource.EPO_SEARCH in hit.sources


# ============================================================================
# 8. search_patents with expanded_queries — integration
# ============================================================================


def _patch_base_sources(**overrides):
    """Return a list of patch context managers for the 5 base search sources + enrichment."""
    defaults = {
        "_search_pubchem_sdq": [],
        "_search_surechembl": [],
        "_search_bigquery": [],
        "_search_bigquery_annotations": [],
        "_search_patcid": [],
        "_search_pubchem_similar": [],
        "_search_pubchem_genus": [],
        "_search_kipris": [],
        "_search_patentscope": [],
        "_search_bigquery_translated": [],
        "_search_patentsview": [],
        "_enrich_legal_status": 0,
        "_expand_families": 0,
        "_enrich_patent_term": 0,
        "_enrich_application_data": 0,
        "_enrich_epo_register": 0,
        "_enrich_ptab_proceedings": 0,
        "_enrich_orange_book": 0,
        "_expand_continuations": 0,
    }
    defaults.update(overrides)

    patches = []
    for fn_name, return_value in defaults.items():
        patches.append(
            patch(
                f"praviar_pipeline.pipeline.step2_search.{fn_name}",
                new_callable=AsyncMock,
                return_value=return_value,
            )
        )
    return patches


class TestSearchPatentsWithExpansion:
    async def test_hybrid_source_uses_canonical_scope_and_assembles_nonempty_rows(
        self,
        succinic_acid,
        mock_settings,
    ):
        from praviar_pipeline.config import get_settings
        from praviar_pipeline.pipeline.step2_search import search_patents

        settings = get_settings().model_copy(
            update={
                "hybrid_retrieval_enabled": True,
                "search_enable_bigquery": True,
                "bigquery_project_id": "project-1",
                "bigquery_dataset": "patents",
                "bigquery_table": "hybrid_index",
            }
        )
        hybrid_rows = [
            _make_bq_row(
                "US-HYBRID-001B2",
                title="Hybrid patent",
                expiry_date="2031-04-05",
                rrf_score=0.03,
            )
        ]
        hybrid_client = AsyncMock()
        hybrid_client.__aenter__.return_value = hybrid_client
        hybrid_client.__aexit__.return_value = False
        hybrid_client.search_patents_hybrid.return_value = hybrid_rows

        patches = [
            *_patch_base_sources(),
            patch(
                "praviar_pipeline.pipeline.step2_search.get_settings",
                return_value=settings,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search.BigQueryClient",
                return_value=hybrid_client,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search.rank_patents",
                return_value=[],
            ),
        ]
        for patcher in patches:
            patcher.__enter__()

        try:
            hits, health, _funnel = await search_patents(succinic_acid)
        finally:
            for patcher in reversed(patches):
                patcher.__exit__(None, None, None)

        assert [hit.patent_id for hit in hits] == ["US-HYBRID-001B2"]
        assert hits[0].expiry_date == date(2031, 4, 5)
        hybrid_client.search_patents_hybrid.assert_awaited_once_with(
            [
                "succinic acid",
                "butanedioic acid",
                "amber acid",
                "110-15-6",
            ],
            jurisdictions=settings.search_allowed_jurisdictions,
            project="project-1",
            dataset="patents",
            table="hybrid_index",
            max_results=settings.search_bigquery_max_results,
        )
        bigquery_health = next(entry for entry in health.entries if entry.source == "bigquery")
        assert bigquery_health.status.value == "ok"
        assert bigquery_health.patent_count == 1

    async def test_hybrid_failure_is_recorded_failed_never_ok(
        self,
        succinic_acid,
        mock_settings,
    ):
        from praviar_pipeline.config import get_settings
        from praviar_pipeline.pipeline.step2_search import search_patents

        settings = get_settings().model_copy(
            update={
                "hybrid_retrieval_enabled": True,
                "search_enable_bigquery": True,
                "bigquery_project_id": "project-1",
                "bigquery_dataset": "patents",
                "bigquery_table": "hybrid_index",
            }
        )
        hybrid_client = AsyncMock()
        hybrid_client.__aenter__.return_value = hybrid_client
        hybrid_client.__aexit__.return_value = False
        hybrid_client.search_patents_hybrid.side_effect = SourceUnavailableError(
            "bigquery",
            "hybrid patent search failed",
        )

        patches = [
            *_patch_base_sources(),
            patch(
                "praviar_pipeline.pipeline.step2_search.get_settings",
                return_value=settings,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search.BigQueryClient",
                return_value=hybrid_client,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search.rank_patents",
                return_value=[],
            ),
        ]
        for patcher in patches:
            patcher.__enter__()

        try:
            _hits, health, _funnel = await search_patents(succinic_acid)
        finally:
            for patcher in reversed(patches):
                patcher.__exit__(None, None, None)

        bigquery_entries = [entry for entry in health.entries if entry.source == "bigquery"]
        assert len(bigquery_entries) == 1
        assert bigquery_entries[0].status.value == "failed"
        assert "source search failed" in bigquery_entries[0].error_message

    async def test_expanded_sources_fired_when_queries_present(
        self,
        succinic_acid,
        mock_settings,
    ):
        """When expanded_queries has CPC/assignees, expanded sources should fire."""
        from praviar_pipeline.pipeline.step2_search import search_patents

        expanded = _make_expanded_queries()

        cpc_rows = [_make_bq_row("US-CPC-001B2", title="CPC patent")]
        assignee_rows = [_make_bq_row("US-ASN-001B2", title="Assignee patent")]
        epo_rows = [{"publication_number": "EP-EPO-001A1", "country": "EP"}]

        base_patches = _patch_base_sources()
        expanded_patches = [
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_cpc",
                new_callable=AsyncMock,
                return_value=cpc_rows,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_assignee",
                new_callable=AsyncMock,
                return_value=assignee_rows,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_epo_claims",
                new_callable=AsyncMock,
                return_value=epo_rows,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search.rank_patents",
                return_value=[],
            ),
        ]

        all_patches = base_patches + expanded_patches
        # Enter all patches
        entered = []
        for p in all_patches:
            entered.append(p.__enter__())

        try:
            hits, health, _funnel = await search_patents(
                succinic_acid,
                expanded_queries=expanded,
            )

            # All three expanded sources should contribute hits
            patent_ids = {h.patent_id for h in hits}
            assert "US-CPC-001B2" in patent_ids
            assert "US-ASN-001B2" in patent_ids
            assert "EP-EPO-001A1" in patent_ids

            # Health should track all sources as OK
            source_names = {e.source for e in health.entries}
            assert "cpc_search" in source_names
            assert "assignee_search" in source_names
            assert "epo_search" in source_names
        finally:
            for p in all_patches:
                p.__exit__(None, None, None)

    async def test_expanded_sources_not_fired_without_expansion(
        self,
        succinic_acid,
        mock_settings,
    ):
        """Without expanded_queries, expanded sources should NOT fire."""
        from praviar_pipeline.pipeline.step2_search import search_patents

        mock_cpc = AsyncMock(return_value=[])
        mock_assignee = AsyncMock(return_value=[])
        mock_epo = AsyncMock(return_value=[])

        base_patches = _patch_base_sources()
        expanded_patches = [
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_cpc",
                mock_cpc,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_assignee",
                mock_assignee,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_epo_claims",
                mock_epo,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search.rank_patents",
                return_value=[],
            ),
        ]

        all_patches = base_patches + expanded_patches
        entered = []
        for p in all_patches:
            entered.append(p.__enter__())

        try:
            # Pass None for expanded_queries (default)
            await search_patents(succinic_acid, expanded_queries=None)

            # Expanded sources should NOT have been called
            mock_cpc.assert_not_called()
            mock_assignee.assert_not_called()
            mock_epo.assert_not_called()
        finally:
            for p in all_patches:
                p.__exit__(None, None, None)

    async def test_expanded_sources_not_fired_with_empty_expansion(
        self,
        succinic_acid,
        mock_settings,
    ):
        """Empty ExpandedSearchQueries should NOT trigger expanded sources."""
        from praviar_pipeline.pipeline.step2_search import search_patents

        empty_expansion = ExpandedSearchQueries()

        mock_cpc = AsyncMock(return_value=[])
        mock_assignee = AsyncMock(return_value=[])
        mock_epo = AsyncMock(return_value=[])

        base_patches = _patch_base_sources()
        expanded_patches = [
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_cpc",
                mock_cpc,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_assignee",
                mock_assignee,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_epo_claims",
                mock_epo,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search.rank_patents",
                return_value=[],
            ),
        ]

        all_patches = base_patches + expanded_patches
        entered = []
        for p in all_patches:
            entered.append(p.__enter__())

        try:
            await search_patents(succinic_acid, expanded_queries=empty_expansion)

            mock_cpc.assert_not_called()
            mock_assignee.assert_not_called()
            mock_epo.assert_not_called()
        finally:
            for p in all_patches:
                p.__exit__(None, None, None)

    async def test_cpc_search_results_merged_into_source_map(
        self,
        succinic_acid,
        mock_settings,
    ):
        """CPC search results should add CPC_SEARCH to the source map."""
        from praviar_pipeline.pipeline.step2_search import search_patents

        expanded = _make_expanded_queries()

        # Same patent found by both SDQ and CPC search
        sdq_results = [_make_sdq_patent("US7777777B2", "Shared patent")]
        cpc_rows = [_make_bq_row("US7777777B2", title="Shared patent via CPC")]

        base_patches = _patch_base_sources(
            _search_pubchem_sdq=sdq_results,
        )
        expanded_patches = [
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_cpc",
                new_callable=AsyncMock,
                return_value=cpc_rows,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_assignee",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_epo_claims",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search.rank_patents",
                return_value=sdq_results,
            ),
        ]

        all_patches = base_patches + expanded_patches
        entered = []
        for p in all_patches:
            entered.append(p.__enter__())

        try:
            hits, _health, _funnel = await search_patents(
                succinic_acid,
                expanded_queries=expanded,
            )

            # The shared patent should have CPC_SEARCH in its sources
            shared = [h for h in hits if h.patent_id == "US7777777B2"]
            assert len(shared) == 1
            assert PatentSource.CPC_SEARCH in shared[0].sources
        finally:
            for p in all_patches:
                p.__exit__(None, None, None)

    async def test_deduplication_across_expanded_sources(
        self,
        succinic_acid,
        mock_settings,
    ):
        """Same patent from multiple expanded sources should not duplicate hits."""
        from praviar_pipeline.pipeline.step2_search import search_patents

        expanded = _make_expanded_queries()

        # Same patent from CPC and assignee search
        cpc_rows = [_make_bq_row("US8888888B2", title="Multi-source patent")]
        assignee_rows = [_make_bq_row("US8888888B2", title="Multi-source patent")]

        base_patches = _patch_base_sources()
        expanded_patches = [
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_cpc",
                new_callable=AsyncMock,
                return_value=cpc_rows,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_assignee",
                new_callable=AsyncMock,
                return_value=assignee_rows,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_epo_claims",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search.rank_patents",
                return_value=[],
            ),
        ]

        all_patches = base_patches + expanded_patches
        entered = []
        for p in all_patches:
            entered.append(p.__enter__())

        try:
            hits, _health, _funnel = await search_patents(
                succinic_acid,
                expanded_queries=expanded,
            )

            # Should appear only once in results
            matching = [h for h in hits if h.patent_id == "US8888888B2"]
            assert len(matching) == 1

            # But should have both sources registered
            assert PatentSource.CPC_SEARCH in matching[0].sources
            assert PatentSource.ASSIGNEE_SEARCH in matching[0].sources
        finally:
            for p in all_patches:
                p.__exit__(None, None, None)

    async def test_epo_search_creates_minimal_hit(
        self,
        succinic_acid,
        mock_settings,
    ):
        """EPO search returns minimal metadata — PatentHit should still be valid."""
        from praviar_pipeline.pipeline.step2_search import search_patents

        expanded = _make_expanded_queries()
        epo_rows = [
            {
                "publication_number": "EP9876543A1",
                "country": "EP",
                "doc_number": "9876543",
                "kind": "A1",
            },
        ]

        base_patches = _patch_base_sources()
        expanded_patches = [
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_cpc",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_assignee",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_epo_claims",
                new_callable=AsyncMock,
                return_value=epo_rows,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search.rank_patents",
                return_value=[],
            ),
        ]

        all_patches = base_patches + expanded_patches
        entered = []
        for p in all_patches:
            entered.append(p.__enter__())

        try:
            hits, _health, _funnel = await search_patents(
                succinic_acid,
                expanded_queries=expanded,
            )

            epo_hits = [h for h in hits if h.patent_id == "EP9876543A1"]
            assert len(epo_hits) == 1
            assert epo_hits[0].sources == [PatentSource.EPO_SEARCH]
            assert epo_hits[0].title == ""  # EPO search returns minimal data
            assert epo_hits[0].abstract == ""
        finally:
            for p in all_patches:
                p.__exit__(None, None, None)

    async def test_expanded_source_failure_tracked_in_health(
        self,
        succinic_acid,
        mock_settings,
    ):
        """If an expanded source fails, it should appear in source health as failed."""
        from praviar_pipeline.pipeline.step2_search import search_patents

        expanded = _make_expanded_queries()

        base_patches = _patch_base_sources()
        expanded_patches = [
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_cpc",
                new_callable=AsyncMock,
                side_effect=RuntimeError("BigQuery CPC query failed"),
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_assignee",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_epo_claims",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search.rank_patents",
                return_value=[],
            ),
        ]

        all_patches = base_patches + expanded_patches
        entered = []
        for p in all_patches:
            entered.append(p.__enter__())

        try:
            _hits, health, _funnel = await search_patents(
                succinic_acid,
                expanded_queries=expanded,
            )

            # CPC search should be tracked as failed
            failed = {e.source for e in health.entries if e.status.value == "failed"}
            assert "cpc_search" in failed

            # Other sources should be OK
            ok = {e.source for e in health.entries if e.status.value == "ok"}
            assert "assignee_search" in ok
            assert "epo_search" in ok
        finally:
            for p in all_patches:
                p.__exit__(None, None, None)

    async def test_confidence_increases_with_expanded_sources(
        self,
        succinic_acid,
        mock_settings,
    ):
        """Patent found by multiple expanded sources should have higher confidence."""
        from praviar_pipeline.pipeline.step2_search import search_patents

        expanded = _make_expanded_queries()

        # Patent found by all three expanded sources
        cpc_rows = [_make_bq_row("US1010101B2")]
        assignee_rows = [_make_bq_row("US1010101B2")]
        epo_rows = [{"publication_number": "US1010101B2"}]

        base_patches = _patch_base_sources()
        expanded_patches = [
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_cpc",
                new_callable=AsyncMock,
                return_value=cpc_rows,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_bigquery_assignee",
                new_callable=AsyncMock,
                return_value=assignee_rows,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search._search_epo_claims",
                new_callable=AsyncMock,
                return_value=epo_rows,
            ),
            patch(
                "praviar_pipeline.pipeline.step2_search.rank_patents",
                return_value=[],
            ),
        ]

        all_patches = base_patches + expanded_patches
        entered = []
        for p in all_patches:
            entered.append(p.__enter__())

        try:
            hits, _health, _funnel = await search_patents(
                succinic_acid,
                expanded_queries=expanded,
            )

            matching = [h for h in hits if h.patent_id == "US1010101B2"]
            assert len(matching) == 1
            # 3 sources -> confidence 0.85
            assert matching[0].confidence_score >= 0.8
        finally:
            for p in all_patches:
                p.__exit__(None, None, None)


# ============================================================================
# 9. Step 2 internal expanded search wrappers
# ============================================================================


class TestSearchBigqueryCPC:
    async def test_returns_empty_without_cpc_codes(self, succinic_acid, mock_settings):
        """_search_bigquery_cpc should return [] when expanded has no CPC codes."""
        from praviar_pipeline.pipeline.step2_search import _search_bigquery_cpc

        expanded = ExpandedSearchQueries()  # no cpc_codes
        result = await _search_bigquery_cpc(succinic_acid, expanded)
        assert result == []

    async def test_calls_bigquery_client(self, succinic_acid, mock_settings):
        """Should call BigQueryClient.search_by_cpc_and_keywords."""
        from praviar_pipeline.pipeline.step2_search import _search_bigquery_cpc

        expanded = _make_expanded_queries()
        expected = [_make_bq_row("US1111111B2")]

        mock_client = AsyncMock()
        mock_client.search_by_cpc_and_keywords.return_value = expected
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step2_search.BigQueryClient",
            return_value=mock_client,
        ):
            result = await _search_bigquery_cpc(succinic_acid, expanded)

        assert result == expected
        mock_client.search_by_cpc_and_keywords.assert_called_once()

        # Keywords should include compound name + process keywords + synonyms
        call_kwargs = mock_client.search_by_cpc_and_keywords.call_args.kwargs
        keywords = call_kwargs["keywords"]
        assert succinic_acid.name in keywords
        assert "fermentation" in keywords


class TestSearchBigqueryAssignee:
    async def test_returns_empty_without_assignees(self, succinic_acid, mock_settings):
        """_search_bigquery_assignee should return [] when expanded has no assignees."""
        from praviar_pipeline.pipeline.step2_search import _search_bigquery_assignee

        expanded = ExpandedSearchQueries()  # no key_assignees
        result = await _search_bigquery_assignee(succinic_acid, expanded)
        assert result == []

    async def test_calls_bigquery_client(self, succinic_acid, mock_settings):
        """Should call BigQueryClient.search_by_assignee."""
        from praviar_pipeline.pipeline.step2_search import _search_bigquery_assignee

        expanded = _make_expanded_queries()
        expected = [_make_bq_row("US2222222B2")]

        mock_client = AsyncMock()
        mock_client.search_by_assignee.return_value = expected
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step2_search.BigQueryClient",
            return_value=mock_client,
        ):
            result = await _search_bigquery_assignee(succinic_acid, expanded)

        assert result == expected
        call_kwargs = mock_client.search_by_assignee.call_args.kwargs
        assert call_kwargs["assignees"] == expanded.key_assignees


class TestSearchEPOClaims:
    async def test_missing_ops_credentials_fails_closed(self, succinic_acid, mock_settings):
        """_search_epo_claims should fail as not configured without OPS credentials."""
        from praviar_pipeline.pipeline.step2_search import _search_epo_claims

        expanded = _make_expanded_queries()

        with patch.dict("os.environ", {"OPS_CONSUMER_KEY": "", "OPS_CONSUMER_SECRET": ""}):
            clear_settings_cache()
            try:
                with pytest.raises(ConfigurationError, match="EPO OPS credentials"):
                    await _search_epo_claims(succinic_acid, expanded)
            finally:
                clear_settings_cache()

    async def test_calls_epo_client(self, succinic_acid, mock_settings):
        """Should call EPOOPSClient.search_published_data."""
        from praviar_pipeline.pipeline.step2_search import _search_epo_claims

        expanded = _make_expanded_queries()
        expected = [{"publication_number": "EP1234567A1"}]

        mock_client = AsyncMock()
        mock_client.search_published_data.return_value = expected
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step2_search.EPOOPSClient",
            return_value=mock_client,
        ):
            result = await _search_epo_claims(succinic_acid, expanded)

        assert result == expected
        call_kwargs = mock_client.search_published_data.call_args.kwargs
        assert succinic_acid.name in call_kwargs["claim_keywords"]
        assert call_kwargs["max_results"] == 100


# ============================================================================
# 10. BigQuery get_patent_metadata_batch
# ============================================================================


class TestGetPatentMetadataBatch:
    async def test_returns_metadata_for_patent_ids(self, mock_settings):
        """Should return metadata rows for given patent IDs."""
        from praviar_pipeline.clients.bigquery import BigQueryClient

        expected_rows = [
            _make_bq_row("US1111111B2", title="Patent 1"),
            _make_bq_row("US2222222B1", title="Patent 2"),
        ]

        mock_bq = MagicMock()
        mock_bq.query_and_wait.return_value = expected_rows

        with (
            patch("praviar_pipeline.clients.bigquery.assert_paid_api_allowed"),
            patch(
                "praviar_pipeline.clients.bigquery._get_bq_client",
                return_value=mock_bq,
            ),
        ):
            client = BigQueryClient()
            results = await client.get_patent_metadata_batch(
                ["US1111111B2", "US2222222B1"],
            )

        assert len(results) == 2
        assert results[0]["title"] == "Patent 1"

    async def test_empty_list_returns_empty(self, mock_settings):
        """Empty patent_ids list should return empty immediately."""
        from praviar_pipeline.clients.bigquery import BigQueryClient

        mock_bq = MagicMock()

        with patch(
            "praviar_pipeline.clients.bigquery._get_bq_client",
            return_value=mock_bq,
        ):
            client = BigQueryClient()
            results = await client.get_patent_metadata_batch([])

        assert results == []
        mock_bq.query_and_wait.assert_not_called()
