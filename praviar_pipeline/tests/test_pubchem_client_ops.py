"""Tests for PubChem client operations helpers."""

from __future__ import annotations

from praviar_pipeline.clients.pubchem_client_ops import build_property_path


def test_build_property_path_encodes_names() -> None:
    path = build_property_path("name", "succinic acid")
    assert path == (
        "/compound/name/succinic%20acid/"
        "property/IUPACName,MolecularFormula,MolecularWeight,CanonicalSMILES,InChI,InChIKey/JSON"
    )


def test_build_property_path_preserves_non_name_values() -> None:
    path = build_property_path("inchikey", "KDYFGRWQOYBRFD-UHFFFAOYSA-N")
    assert path == (
        "/compound/inchikey/KDYFGRWQOYBRFD-UHFFFAOYSA-N/"
        "property/IUPACName,MolecularFormula,MolecularWeight,CanonicalSMILES,InChI,InChIKey/JSON"
    )
