"""Regression tests for the silent-zero defect (Task 2.1).

A real Freedom-to-Operate report (semaglutide) came back with
``invalidity_count: 0`` and ``action_items: 0`` for a 19-patent landscape
that contained HIGH-risk patents. ``invalidity_count`` is not an independent
counter: it is ``len(invalidity_assessments)``, and Step 6 only assesses
patents whose ``risk_level`` is HIGH or MEDIUM.

The root cause was a silent enum fallback. Risk-bearing enum fields
(``risk_level`` and the per-element ``status`` that feeds the deterministic
risk computation) were parsed through ``coerce_enum_value``, which quietly
substituted a ``default`` for any unrecognised LLM value. A malformed status
collapsed to ``unclear``; older deterministic risk logic then walked all-unclear
elements down to ``RiskLevel.CLEAR``; the patent dropped out of the Step 6
``to_assess`` filter, and no invalidity assessment or action item was produced.

That silent default-on-bad-input violates the repository's "no fallbacks,
fail loud" rule. The fixes make the risk-bearing parsers raise
``LLMResponseError`` on unrecognised input instead of defaulting, and keep
genuine all-unclear ambiguity in the reviewable MEDIUM-risk lane.
"""

from __future__ import annotations

import pytest

from praviar_pipeline.errors import LLMResponseError
from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.analysis_validation import coerce_enum_value
from praviar_pipeline.pipeline.analysis.risk import compute_risk_from_elements
from praviar_pipeline.pipeline.invalidity.orchestration import build_invalidity_context


def _patent_with_element_status(status: str) -> dict:
    """Build raw LLM-shaped analysis data with a single claim element."""
    normalized_status = status.strip().lower().replace(" ", "_")
    return {
        "patent_id": "US123456B2",
        "title": "Semaglutide formulation",
        "claims_analyzed": [
            {
                "claim_number": 1,
                "claim_type": "independent",
                "elements": [
                    {
                        "element_number": 1,
                        "element_text": "a GLP-1 analogue",
                        "status": status,
                        "reasoning": "Exact match against the target compound",
                        "confidence": 0.95,
                        "evidence": "Claim 1 recites the analogue verbatim",
                    }
                ],
                "overall_status": ("not_met" if normalized_status == "not_met" else "met"),
                "overall_confidence": 0.95,
            }
        ],
        "risk_level": "high",
        "risk_summary": "All elements met",
    }


def test_malformed_risk_level_fails_loud() -> None:
    """A risk_level the LLM emits in an unrecognised form must raise, not default.

    Before the fix this silently coerced to RiskLevel.MEDIUM.
    """
    with pytest.raises(LLMResponseError, match="governed enum") as excinfo:
        coerce_enum_value(
            "blocking",
            valid_values={level.value for level in RiskLevel},
            default=RiskLevel.MEDIUM.value,
            log_event="risk_level_coerced",
            raise_on_unknown=True,
        )
    assert "blocking" not in str(excinfo.value)


def test_malformed_element_status_fails_loud_on_patent_analysis() -> None:
    """A claim element with an unrecognised status must raise during parsing.

    Before the fix the bad status silently became ``unclear``, which dragged
    the deterministic risk computation down to CLEAR and dropped the patent
    from invalidity assessment.
    """
    with pytest.raises(LLMResponseError, match="governed enum") as excinfo:
        PatentAnalysis.model_validate(_patent_with_element_status("infringed"))
    assert "infringed" not in str(excinfo.value)


def test_common_status_drift_still_normalises() -> None:
    """Genuine formatting drift such as 'Not Met' must still parse cleanly.

    The fix adds ``replace_spaces`` normalisation alongside the fail-loud
    behaviour so harmless casing/spacing variants are not turned into hard
    errors.
    """
    analysis = PatentAnalysis.model_validate(_patent_with_element_status("Not Met"))
    assert analysis.claims_analyzed[0].elements[0].status is ElementStatus.NOT_MET


def test_all_unclear_elements_remain_reviewable_and_reach_step6() -> None:
    """All-unclear elements must not become CLEAR or drop from Step 6.

    Ambiguity-only claim analysis is insufficient evidence for a non-infringement
    clear. It remains MEDIUM risk so downstream invalidity/review workflows see it.
    """
    all_unclear = PatentAnalysis(
        patent_id="US123456B2",
        title="Semaglutide formulation",
        claims_analyzed=[
            ClaimAnalysis(
                claim_number=1,
                claim_type="independent",
                elements=[
                    ClaimElement(
                        element_number=1,
                        element_text="a GLP-1 analogue",
                        status=ElementStatus.UNCLEAR,
                        reasoning="x",
                        confidence=0.5,
                    )
                ],
                overall_status=ElementStatus.UNCLEAR,
                overall_confidence=0.5,
            )
        ],
        risk_level=RiskLevel.HIGH,
        risk_summary="summary",
    )

    assert compute_risk_from_elements(all_unclear) is RiskLevel.MEDIUM

    all_unclear.risk_level = RiskLevel.MEDIUM
    context = build_invalidity_context(
        [all_unclear],
        None,
        compound_name="semaglutide",
        logger=__import__("structlog").get_logger(),
    )
    assert context.to_assess == [all_unclear]


def test_blocking_patent_survives_to_step6() -> None:
    """A correctly parsed HIGH-risk patent must reach the Step 6 to_assess list."""
    blocking = PatentAnalysis.model_validate(_patent_with_element_status("met"))
    assert compute_risk_from_elements(blocking) is RiskLevel.HIGH

    blocking.risk_level = RiskLevel.HIGH
    context = build_invalidity_context(
        [blocking],
        None,
        compound_name="semaglutide",
        logger=__import__("structlog").get_logger(),
    )
    assert context.to_assess == [blocking]
