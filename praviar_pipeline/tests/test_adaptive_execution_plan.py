from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.pipeline.analysis.adaptive_decision import (
    AGENTIC_ESCALATION_STAGE,
    SINGLE_PASS_STAGE,
    build_adaptive_execution_plan,
)


class DrawingEvidence:
    def __init__(self, patent_ids: set[str]) -> None:
        self._patent_ids = patent_ids

    def has_structures(self, patent_id: str) -> bool:
        return patent_id in self._patent_ids


def _patent(**kwargs):
    return SimpleNamespace(
        patent_id=kwargs.get("patent_id", "US12345678B2"),
        claims_text=kwargs.get("claims_text", "1. A simple method claim."),
    )


def _triage(**kwargs):
    return SimpleNamespace(
        relevance=SimpleNamespace(value=kwargs.get("relevance", "possibly_relevant")),
        blocking_potential=kwargs.get("blocking_potential", ""),
        key_claims=kwargs.get("key_claims", []),
        confidence=kwargs.get("confidence", 0.9),
    )


def test_adaptive_plan_keeps_clear_matters_on_single_pass_stage() -> None:
    plan = build_adaptive_execution_plan(
        patent=_patent(),
        triage=_triage(confidence=0.9),
        drawing_evidence=None,
        global_reasons=[],
    )

    assert plan.escalation_required is False
    assert plan.stages[0] == SINGLE_PASS_STAGE


def test_adaptive_plan_escalates_from_dense_uncertain_markush_and_drawing_signals() -> None:
    plan = build_adaptive_execution_plan(
        patent=_patent(claims_text=("Markush Formula I " + "x" * 25000)),
        triage=_triage(confidence=0.41),
        drawing_evidence=DrawingEvidence({"US12345678B2"}),
        global_reasons=["weak_source_health"],
    )

    assert plan.escalation_required is True
    assert plan.stages == (AGENTIC_ESCALATION_STAGE,)
    assert set(plan.escalation_reasons) >= {
        "long_or_dense_claim_set",
        "markush_or_formula_claim_language",
        "triage_uncertainty",
        "drawing_structure_evidence",
        "weak_source_health",
    }
    assert plan.drawing_influence_enabled is True
