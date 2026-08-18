"""Tests for stereo_validation — Phase C stereo check."""

from __future__ import annotations

from praviar_pipeline.ocsr.stereo_validation import (
    claim_mentions_stereo,
    count_stereocenters,
    validate_stereo,
)


class TestCountStereocenters:
    def test_empty_smiles(self):
        assert count_stereocenters("") == (0, 0)

    def test_invalid_smiles(self):
        assert count_stereocenters("NOT_A_SMILES") == (0, 0)

    def test_no_stereo(self):
        assert count_stereocenters("CCO") == (0, 0)

    def test_single_cip_center(self):
        # (S)-alanine
        cip, ez = count_stereocenters("C[C@H](N)C(=O)O")
        assert cip == 1
        assert ez == 0

    def test_two_cip_centers(self):
        # (2R,3S)-2,3-butanediol
        cip, ez = count_stereocenters("C[C@H](O)[C@@H](O)C")
        assert cip == 2
        assert ez == 0

    def test_ez_double_bond(self):
        # (E)-2-butene
        cip, ez = count_stereocenters("C/C=C/C")
        assert cip == 0
        assert ez == 1


class TestClaimMentionsStereo:
    def test_empty(self):
        assert not claim_mentions_stereo("")

    def test_no_stereo_mention(self):
        assert not claim_mentions_stereo("A compound of formula I comprising an aromatic ring.")

    def test_r_descriptor(self):
        assert claim_mentions_stereo("The (R)-enantiomer of compound X")

    def test_s_descriptor(self):
        assert claim_mentions_stereo("(S)- configuration at the alpha carbon")

    def test_enantiomer_word(self):
        assert claim_mentions_stereo("the S-enantiomer exhibits higher potency")

    def test_racemate(self):
        assert claim_mentions_stereo("a racemate of the disclosed compound")

    def test_chiral(self):
        assert claim_mentions_stereo("the chiral center at position 2")

    def test_plus_minus(self):
        assert claim_mentions_stereo("(+)- form of the compound")
        assert claim_mentions_stereo("(\u2212)-menthol")
        assert claim_mentions_stereo("(-)-stereoisomer")

    def test_stereospecific(self):
        assert claim_mentions_stereo("stereospecific synthesis of compound X")
        assert claim_mentions_stereo("stereo-specific methodology")

    def test_case_insensitive(self):
        assert claim_mentions_stereo("RACEMATE")
        assert claim_mentions_stereo("Chiral")

    def test_no_false_positive_on_spirocyclic(self):
        """'spirocyclic' contains 'cyclic' but not 'chiral'."""
        assert not claim_mentions_stereo("a spirocyclic ring system")


class TestValidateStereo:
    def test_no_ocsr_returns_empty_flag(self):
        v = validate_stereo("", target_smiles="C[C@H](N)C(=O)O")
        assert v.flag == ""
        assert v.ocsr_cip_count == 0

    def test_ok_when_stereo_preserved(self):
        v = validate_stereo(
            ocsr_smiles="C[C@H](N)C(=O)O",
            target_smiles="C[C@H](N)C(=O)O",
            claim_text="the (S)-alanine compound",
        )
        assert v.flag == "ok"
        assert v.ocsr_cip_count == 1
        assert v.target_cip_count == 1
        assert v.claim_mentions_stereo

    def test_claim_demands_stereo_but_ocsr_blind(self):
        v = validate_stereo(
            ocsr_smiles="CC(N)C(=O)O",  # stereo stripped
            target_smiles="C[C@H](N)C(=O)O",
            claim_text="the (R)-enantiomer is claimed",
        )
        assert v.flag == "claim_demands_stereo_but_ocsr_blind"
        assert v.ocsr_cip_count == 0
        assert v.target_cip_count == 1

    def test_target_mismatch_without_claim_context(self):
        v = validate_stereo(
            ocsr_smiles="CC(N)C(=O)O",
            target_smiles="C[C@H](N)C(=O)O",
            claim_text="",
        )
        assert v.flag == "target_mismatch"

    def test_stereo_blind_without_target_or_claim(self):
        v = validate_stereo(ocsr_smiles="CC(N)C(=O)O")
        assert v.flag == "stereo_blind"

    def test_ok_when_no_target_but_ocsr_has_stereo(self):
        v = validate_stereo(ocsr_smiles="C[C@H](N)C(=O)O")
        assert v.flag == "ok"

    def test_ez_counted_alongside_cip(self):
        v = validate_stereo(ocsr_smiles="C/C=C/[C@H](O)C")
        assert v.ocsr_cip_count == 1
        assert v.ocsr_ez_count == 1
        assert v.flag == "ok"

    def test_claim_mentions_stereo_flag_independent_of_flag(self):
        """claim_mentions_stereo must be surfaced even when flag='ok'."""
        v = validate_stereo(
            ocsr_smiles="C[C@H](N)C(=O)O",
            target_smiles="C[C@H](N)C(=O)O",
            claim_text="chiral purity of at least 99% ee",
        )
        assert v.claim_mentions_stereo
        assert v.flag == "ok"
