from __future__ import annotations

from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.pipeline.analysis.risk import compute_risk_from_elements


def _claim_status(statuses: tuple[ElementStatus, ...]) -> ElementStatus:
    if not statuses:
        return ElementStatus.NOT_MET
    if ElementStatus.NOT_MET in statuses:
        return ElementStatus.NOT_MET
    if ElementStatus.UNCLEAR in statuses:
        return ElementStatus.UNCLEAR
    if ElementStatus.PARTIALLY_MET in statuses:
        return ElementStatus.PARTIALLY_MET
    return ElementStatus.MET


def _analysis(*statuses: ElementStatus, claim_type: str = "independent") -> PatentAnalysis:
    return PatentAnalysis(
        patent_id="US123",
        title="Test",
        claims_analyzed=[
            ClaimAnalysis(
                claim_number=1,
                claim_type=claim_type,
                elements=[
                    ClaimElement(
                        element_number=index + 1,
                        element_text=f"element {index + 1}",
                        status=status,
                        reasoning="x",
                        confidence=0.9,
                    )
                    for index, status in enumerate(statuses)
                ],
                overall_status=_claim_status(statuses),
                overall_confidence=0.9,
            )
        ],
        risk_level=RiskLevel.LOW,
        risk_summary="summary",
    )


def test_compute_risk_from_elements_high() -> None:
    assert (
        compute_risk_from_elements(_analysis(ElementStatus.MET, ElementStatus.MET))
        == RiskLevel.HIGH
    )


def test_compute_risk_from_elements_medium_when_no_not_met_and_some_met() -> None:
    assert (
        compute_risk_from_elements(_analysis(ElementStatus.MET, ElementStatus.UNCLEAR))
        == RiskLevel.MEDIUM
    )


def test_compute_risk_from_elements_low_when_partial_but_not_satisfied() -> None:
    assert (
        compute_risk_from_elements(_analysis(ElementStatus.PARTIALLY_MET, ElementStatus.NOT_MET))
        == RiskLevel.LOW
    )


def test_compute_risk_from_elements_clear_when_nothing_met() -> None:
    assert (
        compute_risk_from_elements(_analysis(ElementStatus.NOT_MET, ElementStatus.NOT_MET))
        == RiskLevel.CLEAR
    )


def test_compute_risk_from_elements_medium_when_all_unclear() -> None:
    assert (
        compute_risk_from_elements(_analysis(ElementStatus.UNCLEAR, ElementStatus.UNCLEAR))
        == RiskLevel.MEDIUM
    )


def test_compute_risk_from_elements_medium_when_not_met_and_unclear() -> None:
    assert (
        compute_risk_from_elements(_analysis(ElementStatus.NOT_MET, ElementStatus.UNCLEAR))
        == RiskLevel.MEDIUM
    )


def test_compute_risk_from_elements_medium_when_partial_and_unclear() -> None:
    assert (
        compute_risk_from_elements(_analysis(ElementStatus.PARTIALLY_MET, ElementStatus.UNCLEAR))
        == RiskLevel.MEDIUM
    )


def test_compute_risk_from_elements_medium_when_claim_has_no_elements() -> None:
    assert compute_risk_from_elements(_analysis()) == RiskLevel.MEDIUM


def test_compute_risk_from_elements_medium_when_any_independent_claim_empty() -> None:
    analysis = PatentAnalysis(
        patent_id="US123",
        title="Test",
        claims_analyzed=[
            ClaimAnalysis(
                claim_number=1,
                claim_type="independent",
                elements=[],
                overall_status=ElementStatus.UNCLEAR,
                overall_confidence=0.0,
            ),
            ClaimAnalysis(
                claim_number=2,
                claim_type="independent",
                elements=[
                    ClaimElement(
                        element_number=1,
                        element_text="element 1",
                        status=ElementStatus.NOT_MET,
                        reasoning="x",
                        confidence=0.9,
                    )
                ],
                overall_status=ElementStatus.NOT_MET,
                overall_confidence=0.9,
            ),
        ],
        risk_level=RiskLevel.LOW,
        risk_summary="summary",
    )

    assert compute_risk_from_elements(analysis) == RiskLevel.MEDIUM


def test_compute_risk_from_elements_high_still_wins_with_empty_claim() -> None:
    analysis = PatentAnalysis(
        patent_id="US123",
        title="Test",
        claims_analyzed=[
            ClaimAnalysis(
                claim_number=1,
                claim_type="independent",
                elements=[],
                overall_status=ElementStatus.UNCLEAR,
                overall_confidence=0.0,
            ),
            ClaimAnalysis(
                claim_number=2,
                claim_type="independent",
                elements=[
                    ClaimElement(
                        element_number=1,
                        element_text="element 1",
                        status=ElementStatus.MET,
                        reasoning="x",
                        confidence=0.9,
                    )
                ],
                overall_status=ElementStatus.MET,
                overall_confidence=0.9,
            ),
        ],
        risk_level=RiskLevel.LOW,
        risk_summary="summary",
    )

    assert compute_risk_from_elements(analysis) == RiskLevel.HIGH
