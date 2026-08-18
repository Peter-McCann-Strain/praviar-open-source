"""Adversarial tests for claim-analysis matter-context receipts."""

from __future__ import annotations

from praviar_pipeline.models.compound import ResolvedCompound
from praviar_pipeline.pipeline.analysis.context_binding import (
    analysis_context_payload,
    analysis_context_sha256,
)


def _compound(name: str, smiles: str, inchi_key: str) -> ResolvedCompound:
    return ResolvedCompound(
        name=name,
        canonical_smiles=smiles,
        inchi_key=inchi_key,
        original_input=name,
        input_type="name",
    )


def _context_kwargs(compound: ResolvedCompound) -> dict[str, object]:
    return {
        "patent_id": "us1234567b2",
        "compound_identity": compound,
        "product_context": {
            "commercialTerritories": ["US"],
            "manufacturingRoute": "direct synthesis",
        },
        "intended_actions": ["sale", "manufacture"],
        "target_jurisdictions": ["US"],
        "development_stage": "commercial",
    }


def test_context_receipt_binds_the_resolved_compound_identity() -> None:
    aspirin = _compound(
        "aspirin",
        "CC(=O)Oc1ccccc1C(=O)O",
        "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
    )
    ibuprofen = _compound(
        "ibuprofen",
        "CC(C)Cc1ccc(cc1)[C@@H](C)C(=O)O",
        "HEFNNWSXXWATRW-UHFFFAOYSA-N",
    )

    assert analysis_context_sha256(**_context_kwargs(aspirin)) != (
        analysis_context_sha256(**_context_kwargs(ibuprofen))
    )


def test_context_receipt_is_stable_for_equivalent_mapping_order() -> None:
    compound = _compound(
        "aspirin",
        "CC(=O)Oc1ccccc1C(=O)O",
        "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
    )
    first = _context_kwargs(compound)
    second = dict(first)
    second["product_context"] = {
        "manufacturingRoute": "direct synthesis",
        "commercialTerritories": ["US"],
    }
    second["intended_actions"] = ["manufacture", "sale"]

    assert analysis_context_sha256(**first) == analysis_context_sha256(**second)
    assert analysis_context_payload(**first)["schema_version"] == ("claim-analysis-context-v2")


def test_context_receipt_excludes_discovery_metadata_but_binds_identity_fields() -> None:
    base = {
        "name": "aspirin",
        "compound_type": "small_molecule",
        "canonical_smiles": "CC(=O)Oc1ccccc1C(=O)O",
        "inchi_key": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
        "related_compounds": [{"name": "salicylic acid"}],
        "morgan_fp": "large-derived-search-fingerprint",
    }
    changed_discovery = {
        **base,
        "related_compounds": [{"name": "ibuprofen"}],
        "morgan_fp": "different-derived-search-fingerprint",
    }
    changed_identity = {
        **base,
        "canonical_smiles": "CC(C)Cc1ccc(cc1)[C@@H](C)C(=O)O",
    }

    assert analysis_context_sha256(**_context_kwargs(base)) == (
        analysis_context_sha256(**_context_kwargs(changed_discovery))
    )
    assert analysis_context_sha256(**_context_kwargs(base)) != (
        analysis_context_sha256(**_context_kwargs(changed_identity))
    )
