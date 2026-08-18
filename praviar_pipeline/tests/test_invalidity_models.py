"""Tests for invalidity Pydantic models — ClaimChartEntry, ClaimChart,
GrahamFactors, EnablementScreening.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from praviar_pipeline.models import (
    ClaimChart,
    ClaimChartEntry,
    EnablementScreening,
    GrahamFactors,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_entry_yes() -> ClaimChartEntry:
    return ClaimChartEntry(
        element_number=1,
        element_text="A compound of formula (I)",
        prior_art_reference_id="US5000000",
        prior_art_disclosure="Compound X in Table 1 matches formula (I)",
        citation_location="Col. 5, lines 10-20",
        disclosed="yes",
    )


@pytest.fixture
def sample_entry_no() -> ClaimChartEntry:
    return ClaimChartEntry(
        element_number=2,
        element_text="wherein R1 is a C1-C4 alkyl group",
        prior_art_reference_id="US5000000",
        prior_art_disclosure="No alkyl substituent disclosed",
        disclosed="no",
    )


@pytest.fixture
def sample_entry_partial() -> ClaimChartEntry:
    return ClaimChartEntry(
        element_number=3,
        element_text="a pharmaceutically acceptable salt thereof",
        prior_art_reference_id="US5000000",
        prior_art_disclosure="Sodium salt disclosed but not other salts",
        disclosed="partial",
        notes="Only one salt form shown",
    )


# ---------------------------------------------------------------------------
# ClaimChartEntry
# ---------------------------------------------------------------------------


class TestClaimChartEntry:
    def test_construction(self, sample_entry_yes: ClaimChartEntry):
        assert sample_entry_yes.element_number == 1
        assert sample_entry_yes.disclosed == "yes"
        assert sample_entry_yes.citation_location == "Col. 5, lines 10-20"

    def test_defaults(self):
        entry = ClaimChartEntry(
            element_number=1,
            element_text="text",
            prior_art_reference_id="REF1",
            prior_art_disclosure="disc",
            disclosed="yes",
        )
        assert entry.citation_location == ""
        assert entry.notes == ""

    def test_element_number_must_be_positive(self):
        with pytest.raises(ValidationError):
            ClaimChartEntry(
                element_number=0,
                element_text="text",
                prior_art_reference_id="REF1",
                prior_art_disclosure="disc",
                disclosed="yes",
            )

    def test_disclosed_literal_values(self):
        for val in ("yes", "no", "partial"):
            entry = ClaimChartEntry(
                element_number=1,
                element_text="text",
                prior_art_reference_id="REF1",
                prior_art_disclosure="disc",
                disclosed=val,
            )
            assert entry.disclosed == val

    def test_invalid_disclosed_value(self):
        with pytest.raises(ValidationError):
            ClaimChartEntry(
                element_number=1,
                element_text="text",
                prior_art_reference_id="REF1",
                prior_art_disclosure="disc",
                disclosed="maybe",
            )

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError, match="extra"):
            ClaimChartEntry(
                element_number=1,
                element_text="text",
                prior_art_reference_id="REF1",
                prior_art_disclosure="disc",
                disclosed="yes",
                bogus_field="should fail",
            )

    def test_serialization_roundtrip(self, sample_entry_yes: ClaimChartEntry):
        data = sample_entry_yes.model_dump(mode="json")
        restored = ClaimChartEntry.model_validate(data)
        assert restored.element_number == sample_entry_yes.element_number
        assert restored.disclosed == sample_entry_yes.disclosed


# ---------------------------------------------------------------------------
# ClaimChart (with auto-coverage validator)
# ---------------------------------------------------------------------------


class TestClaimChart:
    def test_all_disclosed_yes(self, sample_entry_yes: ClaimChartEntry):
        """When all entries are disclosed='yes', all_elements_disclosed should be True."""
        another_yes = ClaimChartEntry(
            element_number=2,
            element_text="another element",
            prior_art_reference_id="US5000000",
            prior_art_disclosure="Also disclosed",
            disclosed="yes",
        )
        chart = ClaimChart(
            patent_id="US7851188B2",
            claim_number=1,
            prior_art_reference_id="US5000000",
            entries=[sample_entry_yes, another_yes],
        )
        assert chart.all_elements_disclosed is True

    def test_not_all_disclosed(
        self,
        sample_entry_yes: ClaimChartEntry,
        sample_entry_no: ClaimChartEntry,
    ):
        """When any entry is not 'yes', all_elements_disclosed should be False."""
        chart = ClaimChart(
            patent_id="US7851188B2",
            claim_number=1,
            prior_art_reference_id="US5000000",
            entries=[sample_entry_yes, sample_entry_no],
        )
        assert chart.all_elements_disclosed is False

    def test_partial_counts_as_not_fully_disclosed(
        self,
        sample_entry_yes: ClaimChartEntry,
        sample_entry_partial: ClaimChartEntry,
    ):
        """partial != 'yes', so all_elements_disclosed should be False."""
        chart = ClaimChart(
            patent_id="US7851188B2",
            claim_number=1,
            prior_art_reference_id="US5000000",
            entries=[sample_entry_yes, sample_entry_partial],
        )
        assert chart.all_elements_disclosed is False

    def test_empty_entries_keeps_default(self):
        """With no entries, all_elements_disclosed stays at its default (False)."""
        chart = ClaimChart(
            patent_id="US7851188B2",
            claim_number=1,
            prior_art_reference_id="US5000000",
        )
        assert chart.all_elements_disclosed is False
        assert chart.entries == []

    def test_auto_coverage_overrides_explicit_value(self, sample_entry_no: ClaimChartEntry):
        """Even if you pass all_elements_disclosed=True, the validator recalculates."""
        chart = ClaimChart(
            patent_id="US7851188B2",
            claim_number=1,
            prior_art_reference_id="US5000000",
            entries=[sample_entry_no],
            all_elements_disclosed=True,  # Should be overridden to False
        )
        assert chart.all_elements_disclosed is False

    def test_chart_summary(self, sample_entry_yes: ClaimChartEntry):
        chart = ClaimChart(
            patent_id="US7851188B2",
            claim_number=1,
            prior_art_reference_id="US5000000",
            entries=[sample_entry_yes],
            chart_summary="Element 1 fully anticipated",
        )
        assert chart.chart_summary == "Element 1 fully anticipated"

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError, match="extra"):
            ClaimChart(
                patent_id="US123",
                claim_number=1,
                prior_art_reference_id="REF1",
                unknown_field="nope",
            )

    def test_serialization_roundtrip(self, sample_entry_yes: ClaimChartEntry):
        chart = ClaimChart(
            patent_id="US7851188B2",
            claim_number=1,
            prior_art_reference_id="US5000000",
            entries=[sample_entry_yes],
        )
        data = chart.model_dump(mode="json")
        restored = ClaimChart.model_validate(data)
        assert restored.patent_id == chart.patent_id
        assert len(restored.entries) == 1
        assert restored.all_elements_disclosed is True


# ---------------------------------------------------------------------------
# GrahamFactors
# ---------------------------------------------------------------------------


class TestGrahamFactors:
    def test_construction(self):
        gf = GrahamFactors(
            scope_and_content="Prior art covers fermentation of organic acids",
            differences_from_prior_art="Use of specific strain not taught",
            level_of_ordinary_skill="PhD in microbiology or chemical engineering",
            overall_obviousness_assessment="Moderately obvious based on known fermentation art",
        )
        assert gf.scope_and_content.startswith("Prior art")
        assert gf.overall_obviousness_assessment.startswith("Moderately")

    def test_optional_secondary_considerations(self):
        gf = GrahamFactors(
            scope_and_content="scope",
            differences_from_prior_art="differences",
            level_of_ordinary_skill="skill",
            overall_obviousness_assessment="assessment",
            commercial_success="Product has $10M annual sales",
            long_felt_need="Industry sought bio-based route for decades",
            failure_of_others="Three companies failed at scale-up",
            unexpected_results="Yield exceeded expectations by 2x",
        )
        assert gf.commercial_success != ""
        assert gf.long_felt_need != ""
        assert gf.failure_of_others != ""
        assert gf.unexpected_results != ""

    def test_defaults_for_optional_fields(self):
        gf = GrahamFactors(
            scope_and_content="scope",
            differences_from_prior_art="differences",
            level_of_ordinary_skill="skill",
            overall_obviousness_assessment="assessment",
        )
        assert gf.commercial_success == ""
        assert gf.long_felt_need == ""
        assert gf.failure_of_others == ""
        assert gf.unexpected_results == ""

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError, match="extra"):
            GrahamFactors(
                scope_and_content="scope",
                differences_from_prior_art="diff",
                level_of_ordinary_skill="skill",
                overall_obviousness_assessment="assessment",
                bogus="nope",
            )

    def test_serialization_roundtrip(self):
        gf = GrahamFactors(
            scope_and_content="scope",
            differences_from_prior_art="diff",
            level_of_ordinary_skill="PhD",
            overall_obviousness_assessment="Obvious",
        )
        data = gf.model_dump(mode="json")
        restored = GrahamFactors.model_validate(data)
        assert restored.scope_and_content == gf.scope_and_content
        assert restored.overall_obviousness_assessment == gf.overall_obviousness_assessment


# ---------------------------------------------------------------------------
# EnablementScreening
# ---------------------------------------------------------------------------


class TestEnablementScreening:
    def test_defaults(self):
        es = EnablementScreening()
        assert es.genus_claim_detected is False
        assert es.genus_indicators == []
        assert es.specification_enables_full_scope == "unclear"
        assert es.amgen_v_sanofi_flags == []
        assert es.reasoning == ""

    def test_genus_claim_detected(self):
        es = EnablementScreening(
            genus_claim_detected=True,
            genus_indicators=[
                "Markush structure",
                "broad functional group definitions",
            ],
            specification_enables_full_scope="no",
            amgen_v_sanofi_flags=[
                "genus defined by function rather than structure",
                "specification discloses only 2 species",
            ],
            reasoning="Claim defines genus of compounds by activity, "
            "specification enables only narrow subset.",
        )
        assert es.genus_claim_detected is True
        assert len(es.genus_indicators) == 2
        assert es.specification_enables_full_scope == "no"
        assert len(es.amgen_v_sanofi_flags) == 2

    def test_specification_enables_literal_values(self):
        for val in ("yes", "no", "unclear"):
            es = EnablementScreening(specification_enables_full_scope=val)
            assert es.specification_enables_full_scope == val

    def test_invalid_specification_value(self):
        with pytest.raises(ValidationError):
            EnablementScreening(specification_enables_full_scope="maybe")

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError, match="extra"):
            EnablementScreening(bogus="nope")

    def test_serialization_roundtrip(self):
        es = EnablementScreening(
            genus_claim_detected=True,
            genus_indicators=["Markush"],
            specification_enables_full_scope="no",
            reasoning="Not enabled",
        )
        data = es.model_dump(mode="json")
        restored = EnablementScreening.model_validate(data)
        assert restored.genus_claim_detected is True
        assert restored.genus_indicators == ["Markush"]
