"""Deterministic risk classification helpers for Step 4 analysis."""

from __future__ import annotations

import structlog

from praviar_pipeline.models.analysis import ElementStatus, PatentAnalysis, RiskLevel

logger = structlog.get_logger()


def compute_risk_from_elements(analysis: PatentAnalysis) -> RiskLevel:
    """Compute risk level deterministically from element statuses."""
    independent = [c for c in analysis.claims_analyzed if c.claim_type == "independent"]
    if not independent:
        independent = analysis.claims_analyzed
    if not independent:
        logger.warning("empty_claims_defaulting_to_medium")
        return RiskLevel.MEDIUM
    for claim in independent:
        if claim.elements and all(e.status == ElementStatus.MET for e in claim.elements):
            return RiskLevel.HIGH

    empty_claims = [claim.claim_number for claim in independent if not claim.elements]
    if empty_claims:
        logger.warning(
            "empty_claim_elements_defaulting_to_medium",
        )
        return RiskLevel.MEDIUM

    for claim in independent:
        statuses = {e.status for e in claim.elements}
        if statuses == {ElementStatus.UNCLEAR}:
            logger.info(
                "unclear_claim_elements_defaulting_to_medium",
            )
            return RiskLevel.MEDIUM

    for claim in independent:
        statuses = {e.status for e in claim.elements}
        if ElementStatus.UNCLEAR in statuses:
            logger.info(
                "ambiguous_claim_elements_defaulting_to_medium",
            )
            return RiskLevel.MEDIUM

    for claim in independent:
        if not claim.elements:
            continue
        statuses = {e.status for e in claim.elements}
        if ElementStatus.NOT_MET not in statuses and (
            ElementStatus.MET in statuses or ElementStatus.PARTIALLY_MET in statuses
        ):
            return RiskLevel.MEDIUM

    for claim in independent:
        if any(
            e.status in (ElementStatus.MET, ElementStatus.PARTIALLY_MET) for e in claim.elements
        ):
            return RiskLevel.LOW

    return RiskLevel.CLEAR
