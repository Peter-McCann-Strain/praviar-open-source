from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from praviar_pipeline.pipeline.resolution import pubchem_resolution


@pytest.mark.asyncio
async def test_resolve_pubchem_props_routes_inchi_through_inchikey(monkeypatch) -> None:
    pubchem = AsyncMock()
    expected = {"CID": 123}

    monkeypatch.setattr(
        pubchem_resolution,
        "_resolve_inchi_props",
        AsyncMock(return_value=expected),
    )

    props = await pubchem_resolution.resolve_pubchem_props(
        pubchem,
        user_input="InChI=1S/example",
        input_type="inchi",
        logger=MagicMock(),
    )

    assert props == expected


def test_build_related_compounds_skips_missing_and_self_rows() -> None:
    settings = SimpleNamespace(
        resolve_max_related_compounds=5,
        resolve_similarity_threshold=0.7,
        resolve_tanimoto_step=0.05,
    )
    logger = MagicMock()

    related = pubchem_resolution.build_related_compounds(
        sim_results=[
            {"IUPACName": "missing cid"},
            {"CID": 1110, "IUPACName": "self"},
            {"CID": 2220, "IUPACName": "other", "CanonicalSMILES": "CCO"},
        ],
        cid=1110,
        settings=settings,
        logger=logger,
    )

    assert [compound.cid for compound in related] == [2220]
    logger.warning.assert_called_once()
