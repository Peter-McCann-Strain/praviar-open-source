"""Direct tests for extracted Step 1 resolution helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from praviar_pipeline.pipeline.resolution.biologic import (
    classify_compound,
    is_biologic_name,
    resolve_biologic,
)
from praviar_pipeline.pipeline.resolution.fingerprints import compute_fingerprints


def test_is_biologic_name_respects_small_molecule_overrides():
    assert is_biologic_name("osimertinib") is False
    assert is_biologic_name("adalimumab") is True


def test_classify_compound_peptide_window():
    assert classify_compound("peptide-x", "CC(=O)O", 7000.0) == "peptide"


def test_compute_fingerprints_returns_bitstrings_and_groups(mock_settings):
    morgan_fp, maccs_keys, functional_groups = compute_fingerprints("CCO")

    assert len(morgan_fp) == 2048
    assert len(maccs_keys) > 100
    assert "alcohol" in functional_groups


@pytest.mark.asyncio
async def test_resolve_biologic_uses_injected_purple_book_loader():
    purple_book = MagicMock()
    purple_book.lookup_biologic.return_value = {
        "product_name": "Humira",
        "proper_name": "adalimumab",
        "bla_number": "125057",
        "reference_product": "N/A",
        "biosimilar_count": 10,
    }
    load_purple_book_fn = AsyncMock(return_value=purple_book)

    compound = await resolve_biologic(
        "adalimumab",
        "name",
        load_purple_book_fn=load_purple_book_fn,
        logger=SimpleNamespace(info=lambda *args, **kwargs: None),
    )

    assert compound.name == "adalimumab"
    assert compound.compound_type == "biologic"
    assert compound.bla_number == "125057"
    assert compound.biosimilar_count == 10
    assert compound.synonyms == ["Humira"]


@pytest.mark.asyncio
async def test_resolve_biologic_rejects_non_exact_purple_book_substring_match():
    purple_book = MagicMock()
    purple_book.lookup_biologic.return_value = {
        "product_name": "Humira",
        "proper_name": "adalimumab",
        "bla_number": "125057",
        "reference_product": "N/A",
        "biosimilar_count": 10,
    }

    with pytest.raises(ValueError, match="primary, complete FDA GSRS"):
        await resolve_biologic(
            "adalimu",
            "name",
            load_purple_book_fn=AsyncMock(return_value=purple_book),
            resolve_gsrs_fn=AsyncMock(return_value=None),
            logger=SimpleNamespace(
                info=lambda *args, **kwargs: None,
                warning=lambda *args, **kwargs: None,
            ),
        )
