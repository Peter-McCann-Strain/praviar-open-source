"""Candidate selection helpers for doctrine of equivalents analysis."""

from __future__ import annotations

from typing import TypedDict

from praviar_pipeline.models.analysis import ElementStatus, PatentAnalysis


class DoECandidate(TypedDict):
    """Claim element candidate payload used throughout Step 5."""

    patent_id: str
    claim_number: int
    element_number: int
    element_text: str
    element_reasoning: str


def find_doe_candidates(analyses: list[PatentAnalysis]) -> list[DoECandidate]:
    """Identify every material near-miss limitation that requires DoE review."""
    candidates: list[DoECandidate] = []
    for analysis in analyses:
        for claim in analysis.claims_analyzed:
            for element in claim.elements:
                if element.status in (ElementStatus.NOT_MET, ElementStatus.PARTIALLY_MET):
                    candidates.append(
                        {
                            "patent_id": analysis.patent_id,
                            "claim_number": claim.claim_number,
                            "element_number": element.element_number,
                            "element_text": element.element_text,
                            "element_reasoning": element.reasoning,
                        }
                    )
    return candidates


def rank_and_limit_candidates(
    candidates: list[DoECandidate],
    analyses: list[PatentAnalysis],
    max_candidates: int,
) -> list[DoECandidate]:
    """Prioritize high-risk patents before truncating the candidate set."""
    risk_order = {"high": 0, "medium": 1, "low": 2, "clear": 3}
    risk_by_patent = {analysis.patent_id: analysis.risk_level.value for analysis in analyses}
    ranked = sorted(
        candidates,
        key=lambda candidate: risk_order.get(
            risk_by_patent.get(candidate["patent_id"], "medium"),
            1,
        ),
    )
    return ranked[:max_candidates]
