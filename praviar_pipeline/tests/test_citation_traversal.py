"""Tests for citation network traversal with mocked BigQuery client."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from praviar_pipeline.errors import SourceUnavailableError

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCitationTraversal:
    async def test_two_level_traversal(self, mock_settings):
        """2-level traversal discovers citations of citations."""
        from praviar_pipeline.pipeline.step2_search import _traverse_citation_network

        # Level 0 seeds: ["US1", "US2"]
        # Level 1: US1 cites US10, US11; US2 cites US20
        # Level 2: US10 cites US100; US11 cites US110; US20 cites US200
        citations_level1 = {
            "US1": {"examiner": ["US10", "US11"], "applicant": ["US99"]},
            "US2": {"examiner": ["US20"], "applicant": []},
        }
        citations_level2 = {
            "US10": {"examiner": ["US100"], "applicant": []},
            "US11": {"examiner": ["US110"], "applicant": []},
            "US20": {"examiner": ["US200"], "applicant": []},
        }

        mock_bq = AsyncMock()
        # First call with seeds, second call with level-1 results
        mock_bq.get_examiner_citations_batch.side_effect = [
            citations_level1,
            citations_level2,
        ]
        mock_bq.__aenter__ = AsyncMock(return_value=mock_bq)
        mock_bq.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step2_search.BigQueryClient",
            return_value=mock_bq,
        ):
            discovered = await _traverse_citation_network(
                seed_patent_ids=["US1", "US2"],
                max_depth=2,
                max_per_level=50,
            )

        # Level 1 should discover US10, US11, US20
        # Level 2 should discover US100, US110, US200
        # discovered contains normalized IDs — bare numbers get B-tier suffix.
        assert "US10B" in discovered
        assert "US11B" in discovered
        assert "US20B" in discovered
        assert "US100B" in discovered
        assert "US110B" in discovered
        assert "US200B" in discovered
        # Seeds should NOT be in discovered
        assert "US1B" not in discovered
        assert "US2B" not in discovered
        # Applicant citations should NOT be included
        assert "US99B" not in discovered

    async def test_single_level_traversal(self, mock_settings):
        """max_depth=1 discovers only direct citations."""
        from praviar_pipeline.pipeline.step2_search import _traverse_citation_network

        citations = {
            "US1": {"examiner": ["US10", "US11"], "applicant": []},
        }

        mock_bq = AsyncMock()
        mock_bq.get_examiner_citations_batch.return_value = citations
        mock_bq.__aenter__ = AsyncMock(return_value=mock_bq)
        mock_bq.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step2_search.BigQueryClient",
            return_value=mock_bq,
        ):
            discovered = await _traverse_citation_network(
                seed_patent_ids=["US1"],
                max_depth=1,
                max_per_level=50,
            )

        assert "US10B" in discovered
        assert "US11B" in discovered
        assert len(discovered) == 2

    async def test_empty_results(self, mock_settings):
        """When BigQuery returns no citations, discovered set is empty."""
        from praviar_pipeline.pipeline.step2_search import _traverse_citation_network

        mock_bq = AsyncMock()
        mock_bq.get_examiner_citations_batch.return_value = {}
        mock_bq.__aenter__ = AsyncMock(return_value=mock_bq)
        mock_bq.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step2_search.BigQueryClient",
            return_value=mock_bq,
        ):
            discovered = await _traverse_citation_network(
                seed_patent_ids=["US1", "US2"],
                max_depth=2,
                max_per_level=50,
            )

        assert discovered == set()

    async def test_empty_seed_list(self, mock_settings):
        """Empty seed list returns empty discovered set."""
        from praviar_pipeline.pipeline.step2_search import _traverse_citation_network

        mock_bq = AsyncMock()
        mock_bq.get_examiner_citations_batch.return_value = {}
        mock_bq.__aenter__ = AsyncMock(return_value=mock_bq)
        mock_bq.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step2_search.BigQueryClient",
            return_value=mock_bq,
        ):
            discovered = await _traverse_citation_network(
                seed_patent_ids=[],
                max_depth=2,
                max_per_level=50,
            )

        assert discovered == set()

    async def test_error_handling(self, mock_settings):
        """BigQuery failures invalidate citation traversal without leaking detail."""
        from praviar_pipeline.pipeline.step2_search import _traverse_citation_network

        mock_bq = AsyncMock()
        from google.api_core.exceptions import GoogleAPIError

        sentinel = "citation-bigquery-credential-sentinel"
        mock_bq.get_examiner_citations_batch.side_effect = GoogleAPIError(
            f"BigQuery request credential={sentinel}"
        )
        mock_bq.__aenter__ = AsyncMock(return_value=mock_bq)
        mock_bq.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step2_search.BigQueryClient",
            return_value=mock_bq,
        ):
            with pytest.raises(SourceUnavailableError) as exc_info:
                await _traverse_citation_network(
                    seed_patent_ids=["US1"],
                    max_depth=2,
                    max_per_level=50,
                )

        error = exc_info.value
        assert str(error) == "bigquery unavailable: citation traversal failed"
        assert sentinel not in repr(error)
        assert error.__cause__ is None
        assert error.__context__ is None

    async def test_no_duplicate_traversal(self, mock_settings):
        """Already-discovered patents are not re-traversed."""
        from praviar_pipeline.pipeline.step2_search import _traverse_citation_network

        # US1 -> US10; US10 -> US1 (cycle) and US100
        citations_level1 = {
            "US1": {"examiner": ["US10"], "applicant": []},
        }
        citations_level2 = {
            "US10": {"examiner": ["US1", "US100"], "applicant": []},
        }

        mock_bq = AsyncMock()
        mock_bq.get_examiner_citations_batch.side_effect = [
            citations_level1,
            citations_level2,
        ]
        mock_bq.__aenter__ = AsyncMock(return_value=mock_bq)
        mock_bq.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step2_search.BigQueryClient",
            return_value=mock_bq,
        ):
            discovered = await _traverse_citation_network(
                seed_patent_ids=["US1"],
                max_depth=2,
                max_per_level=50,
            )

        # US10 discovered in level 1, US100 in level 2
        # US1 should NOT re-enter discovered (it's a seed)
        assert "US10B" in discovered
        assert "US100B" in discovered
        assert "US1B" not in discovered
