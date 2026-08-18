"""Shared helpers for PPTX report slide assembly."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from praviar_pipeline.models.analysis import RiskLevel

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.report import FTOReport


def high_risk_analyses(report: FTOReport) -> list[PatentAnalysis]:
    """Return high-risk analyses sorted for the deep-dive section."""
    analyses = [a for a in report.patent_analyses if a.risk_level == RiskLevel.HIGH]
    analyses.sort(key=lambda a: (a.expiry_date or date.max, a.assignee or ""))
    return analyses
