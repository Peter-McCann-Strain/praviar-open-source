"""Tests for Fix 7: EPO OPS auth error handling in Step 2 enrichment.

Tests that source failures in legal-status/family enrichment stop incomplete
coverage from being represented as a successful zero-result enrichment.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from praviar_pipeline.errors import AuthenticationError, SourceUnavailableError
from praviar_pipeline.models.patent import PatentHit, PatentSource
from praviar_pipeline.pipeline.step2_search import _enrich_legal_status, _expand_families


@pytest.fixture
def sample_hits() -> list[PatentHit]:
    """Multiple patent hits for enrichment testing."""
    return [
        PatentHit(
            patent_id="US7851188B2",
            title="Patent 1",
            sources=[PatentSource.PUBCHEM],
            confidence_score=0.9,
        ),
        PatentHit(
            patent_id="US6265190B1",
            title="Patent 2",
            sources=[PatentSource.PUBCHEM],
            confidence_score=0.8,
        ),
        PatentHit(
            patent_id="US9999999B2",
            title="Patent 3",
            sources=[PatentSource.PUBCHEM],
            confidence_score=0.7,
        ),
    ]


class TestLegalStatusAuthError:
    """AuthenticationError should break out of enrichment loop."""

    async def test_auth_error_breaks_loop(self, sample_hits, mock_settings):
        """On auth failure, stop and fail the legal-status coverage."""
        mock_epo = AsyncMock()
        mock_epo.get_legal_status.side_effect = AuthenticationError(
            "EPO OPS access token rejected",
            source="epo_ops",
        )
        mock_epo.close = AsyncMock()
        mock_epo.__aenter__ = AsyncMock(return_value=mock_epo)
        mock_epo.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.search.enrichment.EPOOPSClient",
            return_value=mock_epo,
        ):
            with pytest.raises(AuthenticationError):
                await _enrich_legal_status(sample_hits, max_patents=3)
        # Should have called get_legal_status only ONCE (break after first auth error)
        assert mock_epo.get_legal_status.call_count == 1

    async def test_non_auth_error_continues(self, sample_hits, mock_settings):
        """Any per-patent source error makes aggregate coverage incomplete."""
        mock_epo = AsyncMock()
        # First call fails with HTTP error, second succeeds
        mock_epo.get_legal_status.side_effect = [
            httpx.HTTPStatusError(
                "404",
                request=httpx.Request("GET", "http://test"),
                response=httpx.Response(404),
            ),
            [],  # Second call returns empty
            [],  # Third call returns empty
        ]
        mock_epo.close = AsyncMock()
        mock_epo.__aenter__ = AsyncMock(return_value=mock_epo)
        mock_epo.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.search.enrichment.EPOOPSClient",
            return_value=mock_epo,
        ):
            with pytest.raises(SourceUnavailableError):
                await _enrich_legal_status(sample_hits, max_patents=3)

        # Should have tried all 3 patents (not stopped at first error)
        assert mock_epo.get_legal_status.call_count == 3


class TestFamilyExpansionAuthError:
    """AuthenticationError should break out of family expansion loop."""

    async def test_auth_error_breaks_loop(self, sample_hits, mock_settings):
        mock_epo = AsyncMock()
        mock_epo.get_family.side_effect = AuthenticationError(
            "EPO OPS access token rejected",
            source="epo_ops",
        )
        mock_epo.close = AsyncMock()
        mock_epo.__aenter__ = AsyncMock(return_value=mock_epo)
        mock_epo.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step2_search.EPOOPSClient",
            return_value=mock_epo,
        ):
            with pytest.raises(AuthenticationError):
                await _expand_families(sample_hits, max_patents=3)
        assert mock_epo.get_family.call_count == 1
