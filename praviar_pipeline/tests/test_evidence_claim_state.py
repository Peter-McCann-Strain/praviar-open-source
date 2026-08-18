from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.pipeline.runtime.evidence_claims import (
    build_future_risk_maps,
    build_prosecution_claim_state,
    missing_components_for_patent,
    post_grant_risk_level,
    prosecution_flags_for_claim,
    prosecution_flags_for_patent,
)


def test_build_prosecution_claim_state_distinguishes_claim_scoped_flags() -> None:
    state = build_prosecution_claim_state(
        [
            SimpleNamespace(
                patent_id="US1",
                narrowing_signal=False,
                terminal_disclaimer=False,
                pending_family_signal=False,
                ptab_challenged=False,
                ep_opposition_event_count=0,
                ep_limitation_event_count=0,
                ep_revocation_event_count=0,
                ep_lapse_event_count=0,
                ep_register_status="",
                record_basis=["uspto_odp", "family_members"],
                rejected_claim_numbers=[1],
                narrowing_claim_numbers=[1],
                estoppel_risk_flags=[
                    "after_final_response_history",
                    "continuation_lineage",
                ],
                rejection_bases=["103"],
            )
        ]
    )

    assert set(prosecution_flags_for_claim("US1", 1, state)) >= {
        "after_final_response_history",
        "continuation_lineage",
        "rejected_during_prosecution",
        "narrowed_claim_scope",
        "rejection_103",
    }
    assert "after_final_response_history" not in prosecution_flags_for_claim("US1", 2, state)
    assert "rejection_103" not in prosecution_flags_for_claim("US1", 2, state)
    assert "continuation_lineage" in prosecution_flags_for_claim("US1", 2, state)
    assert "after_final_response_history" in prosecution_flags_for_patent("US1", state)
    assert state.record_basis_by_patent["US1"] == ["uspto_odp", "family_members"]


def test_missing_components_and_future_risk_maps_project_runtime_gaps() -> None:
    coverage_summary = SimpleNamespace(
        patents_missing_claims={"US1"},
        patents_missing_claim_level_analysis=set(),
        patents_missing_authoritative_records={"US1"},
        patents_missing_family_context=set(),
        us_patents_missing_prosecution_context={"US1"},
        us_patents_missing_file_wrapper_dossier=set(),
        ep_patents_missing_register_context=set(),
        verification_gaps=["missing-ledger"],
    )

    missing = missing_components_for_patent(
        patent_id="US1",
        coverage_summary=coverage_summary,
        required_components={
            "claims_text",
            "authoritative_records",
            "us_prosecution_context",
            "verification",
        },
    )
    future_risk_by_patent, future_basis_by_patent = build_future_risk_maps(
        [
            SimpleNamespace(
                patent_id="US1",
                risk_type="ep_opposition",
                record_basis=["epo_register"],
            )
        ]
    )

    assert missing == [
        "claims_text",
        "authoritative_records",
        "us_prosecution_context",
        "verification",
    ]
    assert future_risk_by_patent["US1"] == ["ep_opposition"]
    assert future_basis_by_patent["US1"] == ["epo_register"]
    assert post_grant_risk_level(["ep_limitation_history"], []) == "medium"
    assert post_grant_risk_level([], ["ep_opposition"]) == "high"
