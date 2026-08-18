"""Tests for Step 2.5: Patent family expansion and broadest-claims selection."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from praviar_pipeline.models.patent import (
    PatentFamily,
    PatentFamilyMember,
    PatentHit,
    PatentSource,
)
from praviar_pipeline.pipeline.step2c_families import (
    _estimate_claim_breadth,
    expand_and_select_families,
)


class TestEstimateClaimBreadth:
    def test_empty_claims(self):
        assert _estimate_claim_breadth("") == 0.0

    def test_broad_claim_short(self):
        claim = "1. A method comprising mixing a compound with a solvent."
        score = _estimate_claim_breadth(claim)
        assert score > 0

    def test_comprising_broader_than_consisting(self):
        broad = "1. A composition comprising component A and component B."
        narrow = "1. A composition consisting of component A and component B."
        assert _estimate_claim_breadth(broad) > _estimate_claim_breadth(narrow)

    def test_functional_language_adds_score(self):
        functional = "1. A device capable of processing data, adapted to receive input."
        plain = "1. A device that processes data and receives input."
        assert _estimate_claim_breadth(functional) >= _estimate_claim_breadth(plain)


class TestExpandAndSelectFamilies:
    def _make_hit(
        self, patent_id: str, family_id: str | None = None, claims: str = ""
    ) -> PatentHit:
        family = None
        if family_id:
            family = PatentFamily(
                family_id=family_id,
                members=[
                    PatentFamilyMember(
                        doc_number=patent_id,
                        country="US",
                        kind="B2",
                    )
                ],
            )
        return PatentHit(
            patent_id=patent_id,
            title=f"Patent {patent_id}",
            sources=[PatentSource.BIGQUERY],
            confidence_score=0.5,
            claims_text=claims,
            family=family,
        )

    @pytest.mark.asyncio
    async def test_no_families_passthrough(self):
        """Patents without family info pass through unchanged."""
        hits = [self._make_hit("US1"), self._make_hit("US2")]
        result = await expand_and_select_families(hits)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_input(self):
        result = await expand_and_select_families([])
        assert result == []

    @pytest.mark.asyncio
    async def test_single_family_member_kept(self):
        """Family with only one member is kept as-is."""
        hits = [self._make_hit("US1", "FAM1", "1. A method comprising...")]
        result = await expand_and_select_families(hits)
        assert len(result) == 1
        assert result[0].patent_id == "US1"

    @pytest.mark.asyncio
    async def test_family_deduplication(self):
        """Multiple family members -> only broadest kept."""
        hits = [
            self._make_hit("US1", "FAM1", "1. A composition comprising A."),
            self._make_hit("US2", "FAM1", "1. A composition consisting of A; B; C; D; E."),
            self._make_hit("US3"),  # No family
        ]
        result = await expand_and_select_families(hits)
        # Should have 2: broadest from FAM1 + US3
        assert len(result) == 2
        family_member = next(h for h in result if h.family is not None)
        # US1 should win (broader -- "comprising" + shorter)
        assert family_member.patent_id == "US1"
        assert family_member.family_broadest is True

    @pytest.mark.asyncio
    async def test_claims_enrichment_on_missing(self):
        """Patents missing claims get enriched from BigQuery."""
        hits = [
            self._make_hit("US1", "FAM1", ""),  # Missing claims
            self._make_hit("US2", "FAM1", "1. A method comprising step A."),
        ]

        mock_bq = AsyncMock()
        mock_bq.get_patent_claims_batch = AsyncMock(
            return_value={
                "US1": "1. A broad composition comprising X.",
            }
        )
        mock_bq.__aenter__ = AsyncMock(return_value=mock_bq)
        mock_bq.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.pipeline.step2c_families.BigQueryClient", return_value=mock_bq
        ):
            result = await expand_and_select_families(hits)

        assert len(result) == 1
        mock_bq.get_patent_claims_batch.assert_awaited_once()
