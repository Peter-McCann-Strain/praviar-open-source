"""Adaptive Step 4 escalation decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from praviar_pipeline.models.analysis import RiskLevel

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.drawing import DrawingEvidenceStore
    from praviar_pipeline.models.patent import PatentHit
    from praviar_pipeline.models.triage import TriageResult


WORLD_CLASS_EXECUTION_PROFILE = "world_class_adaptive"
SINGLE_PASS_STAGE = "single_pass"
AGENTIC_ESCALATION_STAGE = "agentic_escalation"
EVALUATOR_REANALYSIS_GATE = "evaluator_reanalysis"
PERSPECTIVE_REVIEW_GATE = "perspective_review"
SOURCE_SPAN_GATE = "source_span_exactness"


@dataclass(frozen=True, slots=True)
class AdaptiveExecutionPlan:
    """Computed execution plan for one patent in the unified adaptive path."""

    execution_profile: str
    stages: tuple[str, ...]
    escalation_required: bool
    escalation_reasons: tuple[str, ...]
    drawing_influence_enabled: bool
    quality_gates: tuple[str, ...] = (
        EVALUATOR_REANALYSIS_GATE,
        PERSPECTIVE_REVIEW_GATE,
        SOURCE_SPAN_GATE,
    )

    def to_metadata(self) -> dict[str, object]:
        return {
            "execution_profile": self.execution_profile,
            "stages": list(self.stages),
            "escalation_required": self.escalation_required,
            "escalation_reasons": list(self.escalation_reasons),
            "drawing_influence_enabled": self.drawing_influence_enabled,
            "quality_gates": list(self.quality_gates),
        }


_HIGH_RISK_TERMS = {
    "blocking",
    "high",
    "injunction",
    "assert",
    "assertion",
    "license",
    "licence",
    "literal",
    "markush",
    "formula",
}


def dedupe_reasons(reasons: list[str]) -> list[str]:
    """Return reasons in first-seen order without duplicates."""
    return list(dict.fromkeys(reason for reason in reasons if reason))


def claim_analysis_escalation_reasons(
    *,
    patent: PatentHit,
    triage: TriageResult | None,
    drawing_evidence: DrawingEvidenceStore | None,
    global_reasons: list[str] | None = None,
) -> list[str]:
    """Return reasons for routing a patent into the agentic escalation stage."""
    reasons = list(global_reasons or [])

    claims_text = patent.claims_text or ""
    claim_text_lower = claims_text.lower()
    if len(claims_text) > 24000:
        reasons.append("long_or_dense_claim_set")
    if "markush" in claim_text_lower or "formula i" in claim_text_lower:
        reasons.append("markush_or_formula_claim_language")

    if drawing_evidence and drawing_evidence.has_structures(patent.patent_id):
        reasons.append("drawing_structure_evidence")

    if triage is not None:
        raw_relevance = getattr(triage, "relevance", "")
        relevance = getattr(raw_relevance, "value", raw_relevance)
        blocking_text = str(getattr(triage, "blocking_potential", "") or "").lower()
        has_key_claims = bool(getattr(triage, "key_claims", []) or [])
        confidence = float(getattr(triage, "confidence", 1.0) or 0.0)
        has_high_risk_terms = bool(_HIGH_RISK_TERMS & set(blocking_text.split()))
        if relevance == "relevant" and (has_key_claims or has_high_risk_terms):
            reasons.append("high_risk_triage")
        if relevance in {"relevant", "possibly_relevant"} and confidence < 0.65:
            reasons.append("triage_uncertainty")

    return dedupe_reasons(reasons)


def build_adaptive_execution_plan(
    *,
    patent: PatentHit,
    triage: TriageResult | None,
    drawing_evidence: DrawingEvidenceStore | None,
    global_reasons: list[str] | None = None,
) -> AdaptiveExecutionPlan:
    reasons = tuple(
        claim_analysis_escalation_reasons(
            patent=patent,
            triage=triage,
            drawing_evidence=drawing_evidence,
            global_reasons=global_reasons,
        )
    )
    escalation_required = bool(reasons)
    stages = (
        (AGENTIC_ESCALATION_STAGE,)
        if escalation_required
        else (SINGLE_PASS_STAGE, EVALUATOR_REANALYSIS_GATE)
    )
    return AdaptiveExecutionPlan(
        execution_profile=WORLD_CLASS_EXECUTION_PROFILE,
        stages=stages,
        escalation_required=escalation_required,
        escalation_reasons=reasons,
        drawing_influence_enabled=bool(
            drawing_evidence and drawing_evidence.has_structures(patent.patent_id)
        ),
    )


def stamp_analysis_execution(
    analysis: PatentAnalysis,
    *,
    stage: str,
    escalation_reasons: list[str] | None = None,
    execution_plan: AdaptiveExecutionPlan | None = None,
) -> PatentAnalysis:
    """Attach internal execution metadata to a Step 4 analysis."""
    reasons = dedupe_reasons(list(escalation_reasons or []))
    analysis.analysis_execution_profile = WORLD_CLASS_EXECUTION_PROFILE
    analysis.analysis_stage = stage
    analysis.analysis_escalated = stage == AGENTIC_ESCALATION_STAGE
    analysis.analysis_escalation_reasons = reasons
    if execution_plan is not None:
        analysis.analysis_execution_plan = execution_plan.to_metadata()
    return analysis


def mark_analysis_quality_gate_failure(
    analysis: PatentAnalysis,
    failure: str,
) -> PatentAnalysis:
    """Mark analysis output as requiring review because a quality gate failed."""
    failures = dedupe_reasons(
        [*list(getattr(analysis, "analysis_quality_gate_failures", []) or []), failure]
    )
    analysis.analysis_quality_gate_failures = failures
    analysis.analysis_review_required = True
    plan = dict(getattr(analysis, "analysis_execution_plan", {}) or {})
    plan["quality_gate_failures"] = failures
    plan["review_required"] = True
    analysis.analysis_execution_plan = plan
    return analysis


def analysis_needs_perspective_review(analysis: PatentAnalysis) -> bool:
    """Return whether multi-perspective review should run for this analysis."""
    if getattr(analysis, "analysis_escalated", False):
        return True
    return analysis.risk_level in {RiskLevel.HIGH, RiskLevel.MEDIUM}
