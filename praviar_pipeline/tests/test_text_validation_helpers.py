"""Tests for pure text-validation helpers."""

from praviar_pipeline.ocsr.text_validation_helpers import (
    extract_abbreviation_labels,
    extract_cas_numbers,
    extract_chemical_names,
    extract_molecular_formulas,
    smiles_to_formula,
    smiles_to_inchi_key,
    tanimoto,
)


class TestTextValidationHelpers:
    def test_extracts_formula(self):
        formulas = extract_molecular_formulas("The compound has formula C12H22O11.")
        assert "C12H22O11" in formulas

    def test_extracts_cas(self):
        cas_numbers = extract_cas_numbers("Aspirin (CAS 50-78-2) was used.")
        assert "50-78-2" in cas_numbers

    def test_extracts_name(self):
        names = extract_chemical_names("Treatment with Imatinib showed improvement.")
        assert any("imatinib" in n.lower() for n in names)

    def test_smiles_to_formula(self):
        assert smiles_to_formula("CCO") == "C2H6O"

    def test_smiles_to_inchi_key(self):
        assert smiles_to_inchi_key("CCO").startswith("LFQSCWFLJHTTHZ")

    def test_tanimoto(self):
        assert tanimoto("CCO", "CCO") == 1.0


class TestExtractAbbreviationLabels:
    def test_extracts_known_labels(self) -> None:
        text = "compound (Boc-protected) or with Ts substituent and Ms group"
        labels = extract_abbreviation_labels(text)
        assert "Boc" in labels
        assert "Ts" in labels
        assert "Ms" in labels

    def test_filters_non_superatom_words(self) -> None:
        text = "compound (Boc-protected) or with Ts substituent and Ms group"
        labels = extract_abbreviation_labels(text)
        # English words should not survive the dictionary filter.
        for noise in (
            "compound",
            "protected",
            "substituent",
            "group",
            "with",
            "and",
            "or",
        ):
            assert noise not in labels

    def test_case_sensitive_matching(self) -> None:
        # ``Boc`` is in the dict; ``boc`` is not, and lowercase must NOT match.
        labels = extract_abbreviation_labels("the boc group is protected")
        assert "Boc" not in labels
        assert "boc" not in labels

    def test_empty_text_returns_empty(self) -> None:
        assert extract_abbreviation_labels("") == []

    def test_no_known_labels_returns_empty(self) -> None:
        assert extract_abbreviation_labels("nothing relevant here at all") == []

    def test_returns_unique_labels(self) -> None:
        # Repeat ``Boc`` three times — output should de-duplicate.
        labels = extract_abbreviation_labels("Boc and Boc and Boc again")
        assert labels.count("Boc") == 1

    def test_filters_short_and_long_tokens(self) -> None:
        # Tokens shorter than 2 chars or longer than 10 chars are filtered as
        # noise. ``Me`` (len 2) is in the dict and must survive; a 12-char
        # made-up token must not appear regardless of dict membership.
        labels = extract_abbreviation_labels("methyl Me group abcdefghijkl xyz")
        assert "Me" in labels
        assert "abcdefghijkl" not in labels
