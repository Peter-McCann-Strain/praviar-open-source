"""Tests for praviar_pipeline.utils.formatting — LLM prompt formatting utilities."""

from unittest.mock import MagicMock

from praviar_pipeline.utils.formatting import (
    _truncate_at_word_boundary,
    format_compound_context,
    format_patent_context,
)


def _make_compound(**overrides):
    """Create a mock ResolvedCompound with sensible defaults."""
    defaults = {
        "name": "Aspirin",
        "canonical_smiles": "CC(=O)Oc1ccccc1C(=O)O",
        "molecular_formula": "C9H8O4",
        "inchi_key": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
        "inchi": "InChI=1S/C9H8O4/...",
        "molecular_weight": 180.16,
        "cas_numbers": ["50-78-2"],
        "functional_groups": ["carboxylic acid", "ester"],
        "synonyms": ["acetylsalicylic acid", "2-acetoxybenzoic acid"],
    }
    defaults.update(overrides)
    compound = MagicMock()
    for k, v in defaults.items():
        setattr(compound, k, v)
    return compound


def _make_patent(**overrides):
    """Create a mock PatentHit with sensible defaults."""
    defaults = {
        "patent_id": "US7851188B2",
        "title": "Method for producing biosynthetic compounds",
        "abstract": "A method for producing compounds via fermentation.",
        "claims_text": "1. A method comprising fermenting a microorganism.",
        "assignees": ["Acme Corp", "Bio Inc", "Chem Ltd", "Delta Co"],
        "filing_date": None,
        "expiry_date": None,
        "legal_status": None,
    }
    defaults.update(overrides)
    patent = MagicMock()
    for k, v in defaults.items():
        setattr(patent, k, v)
    return patent


class TestTruncateAtWordBoundary:
    """Tests for _truncate_at_word_boundary()."""

    def test_short_text_unchanged(self):
        assert _truncate_at_word_boundary("hello world", 50) == "hello world"

    def test_exact_length_unchanged(self):
        text = "hello"
        assert _truncate_at_word_boundary(text, 5) == "hello"

    def test_truncates_at_word_boundary(self):
        result = _truncate_at_word_boundary("the quick brown fox jumps", 15)
        # Should truncate at a space before 15 chars
        assert result.endswith("\u2026")
        assert len(result) <= 16  # 15 + ellipsis char

    def test_ellipsis_appended(self):
        result = _truncate_at_word_boundary("a long text here", 10)
        assert result.endswith("\u2026")

    def test_no_word_boundary_uses_full_length(self):
        # Single long word — no space to break at beyond 50% threshold
        result = _truncate_at_word_boundary("supercalifragilisticexpialidocious", 10)
        assert result.endswith("\u2026")

    def test_empty_string(self):
        assert _truncate_at_word_boundary("", 10) == ""


class TestFormatCompoundContext:
    """Tests for format_compound_context()."""

    def test_basic_fields(self):
        compound = _make_compound()
        result = format_compound_context(compound)
        assert "Target Compound: Aspirin" in result
        assert "SMILES: CC(=O)Oc1ccccc1C(=O)O" in result
        assert "Molecular Formula: C9H8O4" in result

    def test_includes_inchikey(self):
        compound = _make_compound()
        result = format_compound_context(compound)
        assert "InChIKey: BSYNRYMUTXBXSQ-UHFFFAOYSA-N" in result

    def test_inchi_excluded_by_default(self):
        compound = _make_compound()
        result = format_compound_context(compound)
        assert "InChI:" not in result

    def test_inchi_included_when_requested(self):
        compound = _make_compound()
        result = format_compound_context(compound, include_inchi=True)
        assert "InChI: InChI=1S/C9H8O4/..." in result

    def test_weight_excluded_by_default(self):
        compound = _make_compound()
        result = format_compound_context(compound)
        assert "Molecular Weight:" not in result

    def test_weight_included_when_requested(self):
        compound = _make_compound()
        result = format_compound_context(compound, include_weight=True)
        assert "Molecular Weight: 180.16" in result

    def test_cas_numbers_included(self):
        compound = _make_compound()
        result = format_compound_context(compound)
        assert "CAS Numbers: 50-78-2" in result

    def test_functional_groups_included(self):
        compound = _make_compound()
        result = format_compound_context(compound)
        assert "Functional Groups: carboxylic acid, ester" in result

    def test_synonyms_capped(self):
        compound = _make_compound(synonyms=[f"syn{i}" for i in range(20)])
        result = format_compound_context(compound, max_synonyms=3)
        assert "syn0, syn1, syn2" in result
        assert "syn3" not in result

    def test_empty_cas_omitted(self):
        compound = _make_compound(cas_numbers=[])
        result = format_compound_context(compound)
        assert "CAS Numbers:" not in result

    def test_empty_synonyms_omitted(self):
        compound = _make_compound(synonyms=[])
        result = format_compound_context(compound)
        assert "Key Synonyms:" not in result

    def test_empty_inchikey_omitted(self):
        compound = _make_compound(inchi_key="")
        result = format_compound_context(compound)
        assert "InChIKey:" not in result


class TestFormatPatentContext:
    """Tests for format_patent_context()."""

    def test_basic_fields(self):
        patent = _make_patent()
        result = format_patent_context(patent)
        assert "Patent ID: US7851188B2" in result
        assert "Title: Method for producing biosynthetic compounds" in result

    def test_assignees_capped_at_3(self):
        patent = _make_patent()
        result = format_patent_context(patent)
        assert "Acme Corp" in result
        assert "Bio Inc" in result
        assert "Chem Ltd" in result
        assert "Delta Co" not in result

    def test_abstract_included(self):
        patent = _make_patent()
        result = format_patent_context(patent)
        assert "Abstract:" in result
        assert "fermentation" in result

    def test_abstract_truncation(self):
        patent = _make_patent(abstract="A " * 100)
        result = format_patent_context(patent, max_abstract=20)
        assert "\u2026" in result  # Ellipsis present

    def test_claims_full_label(self):
        patent = _make_patent()
        result = format_patent_context(patent, max_claims=0)
        assert "FULL CLAIM TEXT:" in result

    def test_claims_truncated_label(self):
        patent = _make_patent()
        result = format_patent_context(patent, max_claims=20)
        assert "Claims (first 20 chars)" in result

    def test_no_claims_shows_note(self):
        patent = _make_patent(claims_text="")
        result = format_patent_context(patent)
        assert "Full claim text not available" in result

    def test_dates_excluded_by_default(self):
        from datetime import date

        patent = _make_patent(filing_date=date(2020, 1, 1))
        result = format_patent_context(patent)
        assert "Filing Date:" not in result

    def test_dates_included_when_requested(self):
        from datetime import date

        patent = _make_patent(
            filing_date=date(2020, 1, 1),
            expiry_date=date(2040, 1, 1),
        )
        result = format_patent_context(patent, include_dates=True)
        assert "Filing Date: 2020-01-01" in result
        assert "Expiry Date: 2040-01-01" in result

    def test_triage_key_claims(self):
        patent = _make_patent()
        triage = MagicMock()
        triage.key_claims = [1, 3, 5]
        result = format_patent_context(patent, triage=triage)
        assert "Priority claims identified in triage: [1, 3, 5]" in result

    def test_no_triage(self):
        patent = _make_patent()
        result = format_patent_context(patent, triage=None)
        assert "Priority claims" not in result

    def test_no_title(self):
        patent = _make_patent(title="")
        result = format_patent_context(patent)
        assert "Title:" not in result

    def test_no_assignees(self):
        patent = _make_patent(assignees=[])
        result = format_patent_context(patent)
        assert "Assignee:" not in result
