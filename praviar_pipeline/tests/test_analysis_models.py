from __future__ import annotations

import pytest
from pydantic import ValidationError

from praviar_pipeline.errors import LLMResponseError
from praviar_pipeline.models.analysis import (
    AnalysisEvaluation,
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    MultiPerspectiveSynthesis,
    PatentAnalysis,
    PerspectiveAnalysis,
    RiskLevel,
)


def test_analysis_barrel_preserves_claim_and_patent_defaults() -> None:
    analysis = PatentAnalysis(
        patent_id="US123",
        risk_level="HIGH",
        risk_summary="summary",
        claims_analyzed=[
            ClaimAnalysis(
                claim_number=1,
                claim_type="independent",
                overall_status="not_met",
                elements=[
                    ClaimElement(
                        element_number=1,
                        element_text="x",
                        status="Not Met",
                        reasoning="reason",
                    )
                ],
            )
        ],
    )

    # Casing and spacing drift normalises cleanly via the barrel re-exports.
    assert analysis.risk_level is RiskLevel.HIGH
    assert analysis.claims_analyzed[0].elements[0].status is ElementStatus.NOT_MET


def test_unrecognised_risk_bearing_values_fail_loud() -> None:
    """Malformed risk_level / element status must raise, not silently default.

    Silently coercing these to a lower band is the silent-zero defect: it
    would drop a blocking patent from invalidity assessment.

    claim_type is intentionally NOT risk-bearing in the same way: without a
    compiled-grammar constraint, the model often returns subject-matter
    terminology ('composition-of-matter') instead of structural dependency
    ('independent'/'dependent'). We coerce to 'independent' (FTO-conservative:
    all claims included in risk scoring) rather than raising and dropping the
    entire analysis.
    """
    with pytest.raises(LLMResponseError):
        PatentAnalysis(patent_id="US123", risk_level="unknown", risk_summary="summary")

    with pytest.raises(LLMResponseError):
        ClaimElement(element_number=1, element_text="x", status="not a status", reasoning="r")

    # claim_type coerces to 'independent' rather than raising — FTO-conservative default
    claim = ClaimAnalysis(claim_number=1, claim_type="composition", overall_status="not_met")
    assert claim.claim_type == "independent"


def test_analysis_barrel_preserves_perspective_and_evaluation_models() -> None:
    perspective = PerspectiveAnalysis(perspective="patent attorney")
    evaluation = AnalysisEvaluation(overall_quality="needs revision")

    # Harmless casing/spacing drift is normalized.
    assert perspective.perspective.value == "patent_attorney"
    assert evaluation.overall_quality == "needs_revision"

    # Unknown governed output fails instead of inventing a quality state.
    with pytest.raises(ValidationError):
        AnalysisEvaluation(overall_quality="not_good")

    # Risk-bearing enum drift fails loud.
    with pytest.raises(LLMResponseError):
        MultiPerspectiveSynthesis(synthesized_risk="bad")


def test_uncertainty_and_citation_fields_default_empty() -> None:
    """New per-finding fields default cleanly so existing fixtures still parse.

    Task 2.4: an element/claim built without the new fields is still valid and
    the fields read as empty strings, preserving behaviour for existing-shaped
    inputs and old checkpoints.
    """
    element = ClaimElement(
        element_number=1,
        element_text="a stabiliser",
        status="met",
        reasoning="reason",
    )
    assert element.uncertainty_note == ""
    assert element.spec_citation == ""

    claim = ClaimAnalysis(
        claim_number=1,
        claim_type="independent",
        overall_status="met",
    )
    assert claim.uncertainty_note == ""


def test_uncertainty_and_citation_fields_parse_from_llm_output() -> None:
    """Per-finding uncertainty/citation fields parse from a fixture LLM payload.

    Task 2.4: the Step 4 prompt instructs the model to emit a per-element
    spec_citation and uncertainty_note plus a claim-level uncertainty_note. The
    parser (Pydantic model_validate) must read them.
    """
    llm_output = {
        "patent_id": "US7851188B2",
        "risk_level": "medium",
        "risk_summary": "One independent claim is partially met.",
        "claims_analyzed": [
            {
                "claim_number": 1,
                "claim_type": "independent",
                "overall_status": "unclear",
                "uncertainty_note": (
                    "The term 'stabiliser' is construed narrowly; scope turns "
                    "on a single specification passage."
                ),
                "elements": [
                    {
                        "element_number": 1,
                        "element_text": "a stabiliser",
                        "status": "unclear",
                        "reasoning": "Construed term, evidence thin.",
                        "spec_citation": "col. 6, lines 3-19",
                        "uncertainty_note": (
                            "Specification defines 'stabiliser' as a non-ionic "
                            "surfactant; target excipient class is ambiguous."
                        ),
                    }
                ],
            }
        ],
    }

    analysis = PatentAnalysis.model_validate(llm_output)
    element = analysis.claims_analyzed[0].elements[0]
    assert element.spec_citation == "col. 6, lines 3-19"
    assert "non-ionic" in element.uncertainty_note
    assert "construed narrowly" in analysis.claims_analyzed[0].uncertainty_note


def test_element_id_field_name_drift_coerced() -> None:
    """Without compiled-grammar, model emits 'element_id' instead of 'element_number'.

    The _normalize_element_id model_validator maps 'element_id' -> 'element_number'
    and extracts the integer prefix from values like '1.1'.
    """
    element = ClaimElement.model_validate(
        {"element_id": "1.1", "element_text": "x", "status": "met", "reasoning": "r"}
    )
    assert element.element_number == 1

    element2 = ClaimElement.model_validate(
        {"element_id": "3", "element_text": "x", "status": "not_met", "reasoning": "r"}
    )
    assert element2.element_number == 3


def test_claim_number_string_coerced_to_int() -> None:
    """Without compiled-grammar, model emits descriptive strings for claim_number.

    The _coerce_claim_number validator extracts the leading integer from values
    like '1 (inferred from abstract)'.
    """
    claim = ClaimAnalysis(
        claim_number="1 (inferred from abstract)",  # type: ignore[arg-type]
        claim_type="independent",
        overall_status="met",
    )
    assert claim.claim_number == 1

    claim2 = ClaimAnalysis(
        claim_number="12b",  # type: ignore[arg-type]
        claim_type="dependent",
        depends_on=1,
        overall_status="not_met",
    )
    assert claim2.claim_number == 12


def test_design_around_strings_are_rejected() -> None:
    """A string cannot invent the claim element that a design-around avoids."""
    with pytest.raises(ValidationError):
        PatentAnalysis.model_validate(
            {
                "patent_id": "US1234567B2",
                "risk_level": "low",
                "risk_summary": "test",
                "design_around_suggestions": [
                    "No design-around needed — nicotinamide does not infringe."
                ],
            }
        )


def test_patent_analysis_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        PatentAnalysis.model_validate(
            {
                "patent_id": "US1234567B2",
                "risk_level": "low",
                "risk_summary": "test",
                "unreviewed_conclusion": "clear",
            }
        )


@pytest.mark.parametrize("element_avoided", [None, "unknown", 0])
def test_design_around_rejects_missing_or_invented_element(element_avoided) -> None:
    with pytest.raises(ValidationError):
        PatentAnalysis.model_validate(
            {
                "patent_id": "US1234567B2",
                "risk_level": "low",
                "risk_summary": "test",
                "design_around_suggestions": [
                    {"element_avoided": element_avoided, "suggestion": "change group"}
                ],
            }
        )


def test_design_around_requires_element_reference() -> None:
    with pytest.raises(ValidationError):
        PatentAnalysis.model_validate(
            {
                "patent_id": "US1234567B2",
                "risk_level": "low",
                "risk_summary": "test",
                "design_around_suggestions": [{"suggestion": "change group"}],
            }
        )
