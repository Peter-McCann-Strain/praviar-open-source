"""Summary validation helpers for report generation."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from praviar_pipeline.config import get_settings
from praviar_pipeline.models.analysis import PatentAnalysis, RiskLevel

if TYPE_CHECKING:
    from praviar_pipeline.models.invalidity import InvalidityAssessment

_RECOMMENDATION_KEYWORDS = ("recommend", "should", "consider", "advise", "next step")
_US_PATENT_ID_RE = re.compile(r"US\s*(?:\d[\d,\s]{5,})(?:[A-Z]\d?)?")
_INVALIDITY_STRENGTH_SORT_KEY = {"strong": 0, "moderate": 1, "weak": 2}


def _validate_executive_summary(
    summary: str,
    analyses: list[PatentAnalysis],
    overall_risk: RiskLevel,
) -> tuple[bool, list[str]]:
    """Validate the executive summary for completeness and accuracy."""
    issues: list[str] = []

    if overall_risk.value not in summary.lower():
        issues.append(f"Summary does not mention the risk level '{overall_risk.value}'")

    high_risk = [analysis for analysis in analyses if analysis.risk_level == RiskLevel.HIGH]
    for analysis in high_risk:
        patent_id_normalized = analysis.patent_id.replace("-", "").replace(" ", "")
        if patent_id_normalized not in summary.replace("-", "").replace(" ", "").replace(",", ""):
            issues.append(f"Summary does not mention HIGH-risk patent {analysis.patent_id}")

    if not any(keyword in summary.lower() for keyword in _RECOMMENDATION_KEYWORDS):
        issues.append("Summary does not contain actionable recommendations")

    settings = get_settings()
    word_count = len(summary.split())
    if word_count < settings.summary_word_count_min:
        issues.append(
            f"Summary too short ({word_count} words, minimum {settings.summary_word_count_min})"
        )
    if word_count > settings.summary_word_count_max:
        issues.append(
            f"Summary too long ({word_count} words, maximum {settings.summary_word_count_max})"
        )

    mentioned_ids = set(_US_PATENT_ID_RE.findall(summary))
    known_ids = {
        patent_id
        for analysis in analyses
        for patent_id in (analysis.patent_id, analysis.patent_id.replace(",", ""))
    }
    hallucinated = {
        mentioned_id.strip()
        for mentioned_id in mentioned_ids
        if mentioned_id.replace(",", "").replace(" ", "") not in known_ids
    }
    if hallucinated:
        issues.append(f"Summary mentions unknown patent IDs: {hallucinated}")

    return len(issues) == 0, issues


def _build_invalidity_summary_lines(
    invalidity_assessments: list[InvalidityAssessment],
    limit: int,
) -> list[str]:
    sorted_assessments = sorted(
        invalidity_assessments,
        key=lambda assessment: _INVALIDITY_STRENGTH_SORT_KEY.get(
            assessment.overall_invalidity_strength, 3
        ),
    )
    return [
        (
            f"- {assessment.patent_id}: {assessment.overall_invalidity_strength} "
            f"({assessment.reasoning})"
        )
        for assessment in sorted_assessments[:limit]
    ]
