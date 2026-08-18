"""Tests for pure OCSR postprocessing plan helpers."""

from praviar_pipeline.ocsr.postprocessing_plan import (
    ABBREVIATION_MAP,
    DEFAULT_POSTPROCESSING_STEPS,
    build_postprocessing_step_map,
    default_postprocessing_steps,
)


def test_default_postprocessing_steps_match_expected_order():
    assert default_postprocessing_steps() == list(DEFAULT_POSTPROCESSING_STEPS)


def test_abbreviation_map_contains_core_protecting_groups():
    assert ABBREVIATION_MAP["Boc"] == "C(=O)OC(C)(C)C"
    assert ABBREVIATION_MAP["TMS"] == "[Si](C)(C)C"


def test_build_postprocessing_step_map_uses_live_callables():
    def fake_step(name: str):
        return lambda smiles: f"{name}:{smiles}"

    step_map = build_postprocessing_step_map(
        strip_ocsr_artifacts=fake_step("strip"),
        canonicalise=fake_step("canonicalise"),
        inchi_round_trip=fake_step("inchi"),
        remove_salts=fake_step("salts"),
        recover_salt_form=fake_step("recover_salt"),
        repair_valence=fake_step("repair"),
        normalise_aromaticity=fake_step("aromaticity"),
        recover_stereo_from_pubchem=fake_step("stereo"),
    )

    assert step_map["strip_artifacts"]("CCO") == "strip:CCO"
    assert step_map["canonicalise"]("CCO") == "canonicalise:CCO"
    assert step_map["recover_salt"]("CCO") == "recover_salt:CCO"
    assert step_map["recover_stereo"]("CCO") == "stereo:CCO"
