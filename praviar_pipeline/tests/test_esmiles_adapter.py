"""Unit tests for the E-SMILES ↔ RDKit / CXSMILES adapter.

These tests run entirely in the main praviar_pipeline venv — they exercise
pure-Python string parsing + RDKit round-tripping and have no
dependency on the molparser worker venv. They cover the mapping
documented in ``praviar_pipeline/venvs/molparser/README.md``:

    <a>Xx</a>   → inline label (best-effort)
    <r>R1</r>   → [*:1] + CXSMILES annotation "R1"
    <c>x</c>    → [*:n] + CXSMILES annotation "x"
    <dum>       → stripped
"""

from __future__ import annotations

import pytest

from praviar_pipeline.ocsr.esmiles_adapter import (
    ESmilesConversionError,
    esmiles_to_cxsmiles,
    esmiles_to_rdkit,
    parse_esmiles,
)

# ---------------------------------------------------------------------------
# Degenerate input
# ---------------------------------------------------------------------------


def test_parse_empty_string_returns_empty_result() -> None:
    result = parse_esmiles("")
    assert result == {
        "core_smiles": "",
        "markush_tags": {},
        "is_markush": False,
        "raw_esmiles": "",
    }


def test_parse_none_returns_empty_result() -> None:
    result = parse_esmiles(None)  # type: ignore[arg-type]
    assert result["core_smiles"] == ""
    assert result["is_markush"] is False


def test_parse_whitespace_only_returns_empty_result() -> None:
    result = parse_esmiles("   \n\t  ")
    assert result["core_smiles"] == ""
    assert result["is_markush"] is False


def test_esmiles_to_rdkit_empty_returns_empty() -> None:
    assert esmiles_to_rdkit("") == ""
    assert esmiles_to_rdkit("   ") == ""


def test_esmiles_to_cxsmiles_empty_returns_empty() -> None:
    assert esmiles_to_cxsmiles("") == ""


def test_esmiles_to_rdkit_nonsense_fails_closed() -> None:
    # String that looks like a SMILES but is not parseable.
    with pytest.raises(ESmilesConversionError):
        esmiles_to_rdkit("not-a-smiles[[[")


# ---------------------------------------------------------------------------
# Plain SMILES (no Markush)
# ---------------------------------------------------------------------------


def test_plain_smiles_round_trips_through_rdkit() -> None:
    # Ethanol — canonical form should match RDKit's canonicalisation.
    result = parse_esmiles("CCO")
    assert result["core_smiles"] == "CCO"
    assert result["is_markush"] is False
    assert result["markush_tags"] == {}

    canonical = esmiles_to_rdkit("CCO")
    # RDKit canonicalises "CCO" as "CCO"
    assert canonical == "CCO"


def test_plain_smiles_cxsmiles_is_canonical_smiles() -> None:
    # Non-Markush CXSMILES is just canonical SMILES (no annotation).
    assert esmiles_to_cxsmiles("c1ccccc1") == "c1ccccc1"


def test_parse_tolerates_leading_trailing_whitespace() -> None:
    result = parse_esmiles("  CCO  \n")
    assert result["core_smiles"] == "CCO"
    assert result["raw_esmiles"] == "CCO"


# ---------------------------------------------------------------------------
# Markush <r> tags
# ---------------------------------------------------------------------------


def test_markush_r1_produces_placeholder_and_tag_map() -> None:
    # Phenyl with an R1 substituent: c1ccc(<r>R1</r>)cc1
    result = parse_esmiles("c1ccc(<r>R1</r>)cc1")
    assert result["is_markush"] is True
    assert result["core_smiles"] == "c1ccc([*:1])cc1"
    assert result["markush_tags"] == {"r1": "R1"}


def test_markush_esmiles_to_rdkit_returns_empty_string() -> None:
    # Markush structures cannot be canonicalised losslessly → "".
    assert esmiles_to_rdkit("c1ccc(<r>R1</r>)cc1") == ""


def test_markush_cxsmiles_contains_annotation_block() -> None:
    cxsmiles = esmiles_to_cxsmiles("c1ccc(<r>R1</r>)cc1")
    # Accept either the RDKit-canonical order or the parse-order core
    # as long as the CXSMILES annotation block is present with R1.
    assert "|$" in cxsmiles
    assert "R1" in cxsmiles
    assert cxsmiles.endswith("$|")


def test_repeated_rgroup_label_reuses_same_index() -> None:
    # Two ``<r>R1</r>`` tags should both map to [*:1].
    result = parse_esmiles("<r>R1</r>CC<r>R1</r>")
    assert result["is_markush"] is True
    assert result["core_smiles"].count("[*:1]") == 2
    assert "[*:2]" not in result["core_smiles"]


def test_distinct_rgroup_labels_get_distinct_indices() -> None:
    result = parse_esmiles("<r>R1</r>CC<r>R2</r>")
    assert result["is_markush"] is True
    assert "[*:1]" in result["core_smiles"]
    assert "[*:2]" in result["core_smiles"]


# ---------------------------------------------------------------------------
# <c> connection-point tags
# ---------------------------------------------------------------------------


def test_c_tag_is_markush_and_generates_placeholder() -> None:
    result = parse_esmiles("CC<c>endpoint</c>")
    assert result["is_markush"] is True
    assert "[*:1]" in result["core_smiles"]
    assert result["markush_tags"] == {"c1": "endpoint"}


# ---------------------------------------------------------------------------
# <dum> tokens
# ---------------------------------------------------------------------------


def test_dum_token_is_stripped_without_marking_markush() -> None:
    result = parse_esmiles("CC<dum>O")
    assert result["is_markush"] is False
    assert result["core_smiles"] == "CCO"


def test_dum_self_closing_token_is_stripped() -> None:
    result = parse_esmiles("CC<dum/>O")
    assert result["is_markush"] is False
    assert result["core_smiles"] == "CCO"


def test_dum_only_round_trips_to_rdkit_canonical() -> None:
    # After stripping <dum>, "CCO" should canonicalise cleanly.
    assert esmiles_to_rdkit("CC<dum>O") == "CCO"


# ---------------------------------------------------------------------------
# <a> atom-label tags
# ---------------------------------------------------------------------------


def test_a_tag_alone_is_not_markush() -> None:
    # <a> is an inline atom label, not a variable substituent.
    result = parse_esmiles("C<a>Xx</a>C")
    # markush_tags records the label, but is_markush stays False.
    assert result["is_markush"] is False
    assert "a1" in result["markush_tags"]


# ---------------------------------------------------------------------------
# Stray / malformed input
# ---------------------------------------------------------------------------


def test_stray_tag_is_stripped_not_raised() -> None:
    # Unknown tag → stripped defensively.
    result = parse_esmiles("CC<unknown>O")
    # The stray opener is dropped.
    assert "<" not in result["core_smiles"]


def test_unbalanced_tag_does_not_raise() -> None:
    # ``<r>R1`` without closer is malformed — must not crash.
    result = parse_esmiles("CC<r>R1")
    # Returns a defensive core (the <r> is stripped by the stray tag
    # fallback since it never matched the paired pattern).
    assert isinstance(result["core_smiles"], str)
    assert result["is_markush"] is False  # no paired <r> ever matched


def test_raw_esmiles_preserved_in_result() -> None:
    raw = "c1ccc(<r>R1</r>)cc1"
    result = parse_esmiles(raw)
    assert result["raw_esmiles"] == raw


# ---------------------------------------------------------------------------
# Integration: a realistic MolParser-style Markush output
# ---------------------------------------------------------------------------


def test_realistic_markush_full_pipeline() -> None:
    # Benzene with two distinct R-groups at para positions — a very
    # common patent-drawing motif.
    raw = "<r>R1</r>c1ccc(<r>R2</r>)cc1"
    parsed = parse_esmiles(raw)

    assert parsed["is_markush"] is True
    assert parsed["core_smiles"] == "[*:1]c1ccc([*:2])cc1"
    assert parsed["markush_tags"] == {"r1": "R1", "r2": "R2"}

    # RDKit conversion returns "" (Markush not canonicalisable).
    assert esmiles_to_rdkit(raw) == ""

    # CXSMILES populated with both labels.
    cxsmiles = esmiles_to_cxsmiles(raw)
    assert "R1" in cxsmiles
    assert "R2" in cxsmiles


@pytest.mark.parametrize(
    "raw,expect_markush",
    [
        ("CCO", False),
        ("<dum>", False),
        ("<r>R1</r>", True),
        ("<c>endpoint</c>", True),
        ("<a>Xx</a>", False),
        ("", False),
    ],
)
def test_is_markush_flag(raw: str, expect_markush: bool) -> None:
    assert parse_esmiles(raw)["is_markush"] is expect_markush
