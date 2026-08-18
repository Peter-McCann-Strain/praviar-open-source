from types import SimpleNamespace

from praviar_pipeline.models.report import (
    ActionType,
    ClearanceOutcome,
)
from praviar_pipeline.pipeline.report.governed_actions import (
    build_governed_action_items,
    build_governed_key_risks,
)


def _clearance_outputs(
    outcome: ClearanceOutcome,
    *,
    blocking_claim_ids: list[str] | None = None,
    decisions: list[object] | None = None,
) -> dict:
    return {
        "clearance_decision": SimpleNamespace(
            decision=outcome,
            decision_audit=SimpleNamespace(
                claim_program_summary=SimpleNamespace(
                    blocking_claim_ids=blocking_claim_ids or [],
                )
            ),
        ),
        "decision_scope": SimpleNamespace(jurisdictions=["US"]),
        "claim_program_decisions": decisions or [],
    }


def test_doe_blocker_uses_governed_decision_not_upstream_risk_label() -> None:
    report = SimpleNamespace(
        patent_analyses=[
            SimpleNamespace(
                patent_id="US123B2",
                risk_level="medium",
                design_around_suggestions=[],
            ),
            SimpleNamespace(
                patent_id="EP999B1",
                risk_level="high",
                design_around_suggestions=[],
            ),
        ],
        invalidity_assessments=[],
    )
    outputs = _clearance_outputs(
        ClearanceOutcome.BLOCKED,
        blocking_claim_ids=["US123B2#claim1"],
        decisions=[
            SimpleNamespace(
                patent_id="US123B2",
                jurisdiction="US",
                evidence_sufficient=True,
                missing_components=[],
            ),
            SimpleNamespace(
                patent_id="EP999B1",
                jurisdiction="EP",
                evidence_sufficient=True,
                missing_components=[],
            ),
        ],
    )

    items = build_governed_action_items(report, outputs)

    assert [item.action_type for item in items] == [
        ActionType.HALT,
        ActionType.LICENSE,
    ]
    assert all(item.patent_ids == ["US123B2"] for item in items)
    assert "verify current ownership" in items[1].description
    assert "EP999B1" not in " ".join(item.description for item in items)


def test_design_around_requires_validated_structure() -> None:
    unvalidated = SimpleNamespace(
        suggestion="Change the scaffold.",
        smiles=None,
        rdkit_valid=None,
        pharmacophore_preserved=None,
        tanimoto_to_original=None,
    )
    validated = SimpleNamespace(
        suggestion="Evaluate a validated analogue.",
        smiles="CCO",
        rdkit_valid=True,
        pharmacophore_preserved=True,
        tanimoto_to_original=0.62,
    )
    outputs = _clearance_outputs(
        ClearanceOutcome.BLOCKED,
        blocking_claim_ids=["US123B2#claim1"],
    )

    unvalidated_items = build_governed_action_items(
        SimpleNamespace(
            patent_analyses=[
                SimpleNamespace(
                    patent_id="US123B2",
                    design_around_suggestions=[unvalidated],
                )
            ],
            invalidity_assessments=[],
        ),
        outputs,
    )
    validated_items = build_governed_action_items(
        SimpleNamespace(
            patent_analyses=[
                SimpleNamespace(
                    patent_id="US123B2",
                    design_around_suggestions=[validated],
                )
            ],
            invalidity_assessments=[],
        ),
        outputs,
    )

    assert ActionType.DESIGN_AROUND not in {item.action_type for item in unvalidated_items}
    assert ActionType.LICENSE in {item.action_type for item in unvalidated_items}
    assert ActionType.DESIGN_AROUND in {item.action_type for item in validated_items}
    assert ActionType.LICENSE not in {item.action_type for item in validated_items}


def test_unclear_outcome_withholds_mitigation_and_risk_acceptance() -> None:
    outputs = _clearance_outputs(
        ClearanceOutcome.UNCLEAR,
        decisions=[
            SimpleNamespace(
                patent_id="US123B2",
                jurisdiction="US",
                evidence_sufficient=False,
                missing_components=[
                    "primary_legal_status",
                    "analysis_context_binding",
                ],
            ),
            SimpleNamespace(
                patent_id="EP999B1",
                jurisdiction="EP",
                evidence_sufficient=False,
                missing_components=["national_legal_status"],
            ),
        ],
    )
    report = SimpleNamespace(patent_analyses=[], invalidity_assessments=[])

    items = build_governed_action_items(report, outputs)

    assert [item.action_type for item in items] == [
        ActionType.HALT,
        ActionType.MONITOR,
    ]
    assert all("EP999B1" not in item.patent_ids for item in items)
    assert not {
        ActionType.ACCEPT_RISK,
        ActionType.DESIGN_AROUND,
        ActionType.LICENSE,
        ActionType.CHALLENGE_IPR,
    }.intersection(item.action_type for item in items)


def test_clear_outcome_has_no_automated_mitigation_action() -> None:
    report = SimpleNamespace(patent_analyses=[], invalidity_assessments=[])

    assert (
        build_governed_action_items(
            report,
            _clearance_outputs(ClearanceOutcome.CLEAR),
        )
        == []
    )
    assert build_governed_key_risks(_clearance_outputs(ClearanceOutcome.CLEAR)) == []


def test_key_risks_use_only_governed_target_scope_decisions() -> None:
    blocked = _clearance_outputs(
        ClearanceOutcome.BLOCKED,
        blocking_claim_ids=["US123B2#claim1"],
        decisions=[
            SimpleNamespace(
                patent_id="US123B2",
                jurisdiction="US",
                evidence_sufficient=True,
                missing_components=[],
            ),
            SimpleNamespace(
                patent_id="EP999B1",
                jurisdiction="EP",
                evidence_sufficient=False,
                missing_components=["national_legal_status"],
            ),
        ],
    )

    risks = build_governed_key_risks(blocked)

    assert len(risks) == 1
    assert "US123B2" in risks[0]
    assert "EP999B1" not in risks[0]


def test_unclear_key_risks_name_governed_record_gaps_not_raw_risk_labels() -> None:
    outputs = _clearance_outputs(
        ClearanceOutcome.UNCLEAR,
        decisions=[
            SimpleNamespace(
                patent_id="US123B2",
                jurisdiction="US",
                evidence_sufficient=False,
                missing_components=[
                    "analysis_context_binding",
                    "primary_legal_status",
                ],
            ),
            SimpleNamespace(
                patent_id="EP999B1",
                jurisdiction="EP",
                evidence_sufficient=False,
                missing_components=["national_legal_status"],
            ),
        ],
    )

    assert build_governed_key_risks(outputs) == [
        (
            "Unresolved target-scope record for US123B2: "
            "analysis_context_binding, primary_legal_status."
        )
    ]
