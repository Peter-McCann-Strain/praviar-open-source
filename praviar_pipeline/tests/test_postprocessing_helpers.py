"""Tests for pure OCSR postprocessing helpers."""

from praviar_pipeline.ocsr import postprocessing
from praviar_pipeline.ocsr.postprocessing_helpers import (
    clean_fragments,
    fragment_records,
    has_suspicious_counterions,
    is_trivial_fragment,
    largest_fragment_smiles,
    split_fragments,
)


def test_split_fragments_trims_and_discards_empty_parts():
    assert split_fragments(" CCO . . CCC ") == ["CCO", "CCC"]


def test_is_trivial_fragment_identifies_artifacts():
    assert is_trivial_fragment("*")
    assert is_trivial_fragment("[HH]")
    assert is_trivial_fragment("(*.)")
    assert not is_trivial_fragment("CCO")


def test_clean_fragments_filters_artifacts_and_canonicalises():
    assert clean_fragments("CCO.*.[HH].C") == ["CCO", "C"]


def test_fragment_records_and_suspicious_counterions():
    records = fragment_records("CCO.[HH]")
    assert len(records) == 2
    assert has_suspicious_counterions(records)


def test_largest_fragment_smiles_prefers_heaviest_fragment():
    assert largest_fragment_smiles("CC.CCCCC") == "CCCCC"


def test_postprocess_keeps_module_level_patch_points(monkeypatch):
    calls: list[str] = []

    def fake_strip(smiles: str) -> str:
        calls.append(smiles)
        return f"{smiles}X"

    monkeypatch.setattr(postprocessing, "strip_ocsr_artifacts", fake_strip)

    processed, applied = postprocessing.postprocess("CCO", steps=["strip_artifacts"])

    assert processed == "CCOX"
    assert applied == ["strip_artifacts"]
    assert calls == ["CCO"]


def test_postprocessing_facades_preserve_safe_fallbacks():
    assert postprocessing.to_inchi_key("not-a-smiles") == ""
    assert postprocessing.recover_stereo_from_pubchem("not-a-smiles") == "not-a-smiles"
    assert postprocessing.recover_salt_form("CCO") == "CCO"
