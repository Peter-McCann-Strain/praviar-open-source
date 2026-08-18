from __future__ import annotations

from praviar_pipeline.models.report_decisioning import (
    ClearanceDecision,
    CommercialExposure,
    EvidenceCoverageSummary,
    ProsecutionDossier,
)


def test_clearance_decision_uses_nested_defaults() -> None:
    decision = ClearanceDecision()

    assert decision.decision.value == "unclear"
    assert decision.decision_audit.coverage_summary == EvidenceCoverageSummary()
    assert decision.decision_audit.decisive_references == []


def test_prosecution_dossier_and_commercial_exposure_keep_public_shape() -> None:
    dossier = ProsecutionDossier(patent_id="US1234567B2")
    exposure = CommercialExposure()

    assert dossier.patent_id == "US1234567B2"
    assert dossier.source_name == "uspto_odp"
    assert exposure.blocking_patent_ids == []
