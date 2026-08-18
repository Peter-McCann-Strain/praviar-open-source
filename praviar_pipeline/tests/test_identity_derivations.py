"""Adversarial tests for bounded identity chemistry derivations."""

from __future__ import annotations

from praviar_pipeline.pipeline.resolution.identity_derivations import (
    derive_prodrug_candidates,
    enumerate_tautomer_candidates,
)


def test_tautomer_enumeration_is_deterministic_bounded_and_property_checked() -> None:
    smiles = "CC(=O)C=C(O)C"

    first = enumerate_tautomer_candidates(
        smiles,
        max_tautomers=32,
        max_transforms=64,
        max_search_candidates=3,
    )
    second = enumerate_tautomer_candidates(
        smiles,
        max_tautomers=32,
        max_transforms=64,
        max_search_candidates=3,
    )

    assert first.model_dump() == second.model_dump()
    assert first.status == "completed"
    assert first.enumerated_count == 5
    assert first.search_expansion_allowed is True
    assert 1 <= len(first.candidates) <= 3
    assert all(candidate.search_eligible for candidate in first.candidates)
    assert all(candidate.integrity.passed for candidate in first.candidates)
    assert all(
        "molecular_formula_matches_source" in candidate.integrity.checks
        for candidate in first.candidates
    )


def test_tautomer_bound_hit_fails_closed_for_search_expansion() -> None:
    result = enumerate_tautomer_candidates(
        "CC(=O)C=C(O)C",
        max_tautomers=2,
        max_transforms=64,
        max_search_candidates=8,
    )

    assert result.status == "max_tautomers_reached"
    assert result.search_expansion_allowed is False
    assert all(not candidate.search_eligible for candidate in result.candidates)
    assert all(
        candidate.exclusion_reason == "enumeration_status_max_tautomers_reached"
        for candidate in result.candidates
    )


def test_aspirin_generates_only_dominant_salicylic_parent_hypothesis() -> None:
    result = derive_prodrug_candidates("CC(=O)Oc1ccccc1C(=O)O")

    assert result.detected_motifs == ["ester_prodrug_candidate"]
    assert result.unsupported_motifs == []
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.rule_id == "ester_hydrolysis_alcohol_parent"
    assert candidate.canonical_smiles == "O=C(O)c1ccccc1O"
    assert candidate.hypothesis is True
    assert candidate.search_eligible is True
    assert candidate.integrity.passed is True
    assert candidate.integrity.retained_heavy_atom_fraction > 0.75


def test_simple_phosphate_and_dominant_n_carbamate_are_supported_hypotheses() -> None:
    phosphate = derive_prodrug_candidates("O=P(O)(O)Oc1ccc(CCN)cc1")
    carbamate = derive_prodrug_candidates("CCOC(=O)NCCCCCCCC")

    assert [candidate.rule_id for candidate in phosphate.candidates] == [
        "phosphate_monoester_dephosphorylation"
    ]
    assert phosphate.candidates[0].canonical_smiles == "NCCc1ccc(O)cc1"
    assert [candidate.rule_id for candidate in carbamate.candidates] == ["n_carbamate_deprotection"]
    assert carbamate.candidates[0].canonical_smiles == "CCCCCCCCN"


def test_complex_phosphorus_promoieties_are_explicitly_unsupported() -> None:
    result = derive_prodrug_candidates("COP(=O)(NC(C)C)Oc1ccccc1")

    assert result.candidates == []
    assert any("phosphoramidate" in motif for motif in result.unsupported_motifs)
    assert "multiester_phosphate_activation_unsupported" in result.unsupported_motifs
