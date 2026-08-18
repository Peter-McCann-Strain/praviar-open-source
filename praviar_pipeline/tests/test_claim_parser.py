"""Tests for deterministic claim pre-parser."""

import pytest

from praviar_pipeline.utils.claim_parser import (
    compute_risk_from_claims,
    format_pre_parsed_claims,
    split_claims,
)


class TestSplitClaims:
    def test_basic_numbered_claims(self):
        text = """1. A method for producing succinic acid comprising fermenting glucose.
2. The method of claim 1, wherein the fermentation is anaerobic.
3. A composition comprising succinic acid and a carrier."""

        claims = split_claims(text)
        assert len(claims) == 3
        assert claims[0].claim_number == 1
        assert claims[1].claim_number == 2
        assert claims[2].claim_number == 3

    def test_independent_vs_dependent(self):
        text = """1. A method for producing succinic acid comprising fermenting glucose.
2. The method of claim 1, wherein the fermentation is anaerobic.
3. A composition comprising succinic acid and a carrier."""

        claims = split_claims(text)
        assert claims[0].claim_type == "independent"
        assert claims[1].claim_type == "dependent"
        assert claims[1].depends_on == 1
        assert claims[2].claim_type == "independent"

    def test_transitional_phrase_extraction(self):
        text = "1. A composition comprising succinic acid and ethanol."
        claims = split_claims(text)
        assert claims[0].transitional_phrase == "comprising"
        assert "composition" in claims[0].preamble.lower()

    def test_consisting_of(self):
        text = "1. A composition consisting of succinic acid and water."
        claims = split_claims(text)
        assert claims[0].transitional_phrase == "consisting of"

    def test_consisting_essentially_of(self):
        text = "1. A method consisting essentially of mixing acid with base."
        claims = split_claims(text)
        assert claims[0].transitional_phrase == "consisting essentially of"

    def test_semicolon_element_splitting(self):
        text = (
            "1. A method comprising: fermenting glucose; recovering succinic acid;"
            " purifying the product."
        )
        claims = split_claims(text)
        elements = claims[0].elements
        assert len(elements) == 3
        assert elements[0].element_number == 1
        assert "fermenting" in elements[0].element_text
        assert elements[2].element_number == 3
        assert "purifying" in elements[2].element_text

    def test_lettered_element_splitting(self):
        text = "1. A composition comprising: (a) succinic acid (b) a polyol (c) a catalyst."
        claims = split_claims(text)
        elements = claims[0].elements
        assert len(elements) >= 3

    def test_empty_text(self):
        assert split_claims("") == []
        assert split_claims("   ") == []

    def test_no_numbered_claims_fallback(self):
        text = "A method comprising fermenting glucose to produce succinic acid."
        claims = split_claims(text)
        assert len(claims) == 1
        assert claims[0].claim_number == 1

    def test_determinism(self):
        """Same input always produces same output — the core guarantee."""
        text = """1. A method for producing succinic acid comprising:
fermenting a carbon source with a recombinant microorganism;
recovering the succinic acid from the fermentation broth.
2. The method of claim 1, wherein the microorganism is E. coli.
3. A composition comprising succinic acid at a purity of at least 99%."""

        # Run 10 times — must be identical
        results = [split_claims(text) for _ in range(10)]
        for i in range(1, 10):
            assert len(results[i]) == len(results[0])
            for j in range(len(results[0])):
                assert results[i][j].claim_number == results[0][j].claim_number
                assert results[i][j].claim_type == results[0][j].claim_type
                assert results[i][j].depends_on == results[0][j].depends_on
                assert len(results[i][j].elements) == len(results[0][j].elements)


class TestComputeRiskFromClaims:
    def test_all_met_is_high(self):
        claims = [
            {
                "claim_type": "independent",
                "elements": [
                    {"status": "met"},
                    {"status": "met"},
                    {"status": "met"},
                ],
            },
        ]
        assert compute_risk_from_claims(claims) == "high"

    def test_met_and_unclear_is_medium(self):
        claims = [
            {
                "claim_type": "independent",
                "elements": [
                    {"status": "met"},
                    {"status": "unclear"},
                    {"status": "partially_met"},
                ],
            },
        ]
        assert compute_risk_from_claims(claims) == "medium"

    def test_some_met_some_not_met_is_low(self):
        claims = [
            {
                "claim_type": "independent",
                "elements": [
                    {"status": "met"},
                    {"status": "not_met"},
                ],
            },
        ]
        assert compute_risk_from_claims(claims) == "low"

    def test_all_not_met_is_clear(self):
        claims = [
            {
                "claim_type": "independent",
                "elements": [
                    {"status": "not_met"},
                    {"status": "not_met"},
                ],
            },
        ]
        assert compute_risk_from_claims(claims) == "clear"

    def test_status_formatting_drift_normalises(self):
        claims = [
            {
                "claim_type": "independent",
                "elements": [
                    {"status": "Not Met"},
                    {"status": "not-met"},
                ],
            },
        ]
        assert compute_risk_from_claims(claims) == "clear"

    def test_claim_type_formatting_drift_normalises(self):
        claims = [
            {
                "claim_type": "Independent Claim",
                "elements": [
                    {"status": "met"},
                ],
            },
        ]
        assert compute_risk_from_claims(claims) == "high"

    def test_unknown_status_fails_loud_instead_of_clear(self):
        claims = [
            {
                "claim_type": "independent",
                "elements": [
                    {"status": "infringed"},
                ],
            },
        ]
        with pytest.raises(ValueError, match="Unsupported claim element status"):
            compute_risk_from_claims(claims)

    def test_unknown_claim_type_fails_loud_instead_of_being_ignored(self):
        claims = [
            {
                "claim_type": "independent",
                "elements": [
                    {"status": "not_met"},
                ],
            },
            {
                "claim_type": "composition",
                "elements": [
                    {"status": "met"},
                ],
            },
        ]
        with pytest.raises(ValueError, match="Unsupported claim type"):
            compute_risk_from_claims(claims)

    def test_unknown_status_with_not_met_fails_loud_instead_of_clear(self):
        claims = [
            {
                "claim_type": "independent",
                "elements": [
                    {"status": "not_met"},
                    {"status": "blocking"},
                ],
            },
        ]
        with pytest.raises(ValueError, match="Unsupported claim element status"):
            compute_risk_from_claims(claims)

    def test_empty_claims_is_medium(self):
        assert compute_risk_from_claims([]) == "medium"

    def test_all_unclear_no_met_is_medium(self):
        """All unclear without any met is insufficient evidence for CLEAR."""
        claims = [
            {
                "claim_type": "independent",
                "elements": [
                    {"status": "unclear"},
                    {"status": "unclear"},
                ],
            },
        ]
        assert compute_risk_from_claims(claims) == "medium"

    def test_not_met_and_unclear_blocks_clear(self):
        claims = [
            {
                "claim_type": "independent",
                "elements": [
                    {"status": "not_met"},
                    {"status": "unclear"},
                ],
            },
        ]
        assert compute_risk_from_claims(claims) == "medium"

    def test_missing_status_blocks_clear(self):
        claims = [
            {
                "claim_type": "independent",
                "elements": [
                    {"status": "not_met"},
                    {},
                ],
            },
        ]
        assert compute_risk_from_claims(claims) == "medium"

    def test_partial_and_unclear_is_medium(self):
        claims = [
            {
                "claim_type": "independent",
                "elements": [
                    {"status": "partially_met"},
                    {"status": "unclear"},
                ],
            },
        ]
        assert compute_risk_from_claims(claims) == "medium"

    def test_unknown_dependent_status_fails_loud_even_when_independent_is_clear(self):
        claims = [
            {
                "claim_type": "independent",
                "elements": [
                    {"status": "not_met"},
                ],
            },
            {
                "claim_type": "dependent",
                "elements": [
                    {"status": "blocking"},
                ],
            },
        ]
        with pytest.raises(ValueError, match="Unsupported claim element status"):
            compute_risk_from_claims(claims)

    def test_empty_independent_claim_blocks_clear(self):
        claims = [
            {
                "claim_type": "independent",
                "elements": [],
            },
            {
                "claim_type": "independent",
                "elements": [
                    {"status": "not_met"},
                ],
            },
        ]
        assert compute_risk_from_claims(claims) == "medium"

    def test_high_still_wins_with_empty_independent_claim(self):
        claims = [
            {
                "claim_type": "independent",
                "elements": [],
            },
            {
                "claim_type": "independent",
                "elements": [
                    {"status": "met"},
                ],
            },
        ]
        assert compute_risk_from_claims(claims) == "high"

    def test_multiple_claims_highest_wins(self):
        claims = [
            {
                "claim_type": "independent",
                "elements": [
                    {"status": "not_met"},
                    {"status": "not_met"},
                ],
            },
            {
                "claim_type": "independent",
                "elements": [
                    {"status": "met"},
                    {"status": "met"},
                ],
            },
        ]
        assert compute_risk_from_claims(claims) == "high"


class TestFormatPreParsedClaims:
    def test_formats_claims(self):
        text = """1. A method comprising: step A; step B.
2. The method of claim 1, wherein step A uses heat."""
        claims = split_claims(text)
        formatted = format_pre_parsed_claims(claims)
        assert "PRE-PARSED CLAIMS" in formatted
        assert "Claim 1 (independent)" in formatted
        assert "Claim 2 (dependent" in formatted
        assert "Element 1:" in formatted
        assert "IMPORTANT: Use the claim structure above" in formatted

    def test_empty_claims(self):
        formatted = format_pre_parsed_claims([])
        assert "No claims could be parsed" in formatted
