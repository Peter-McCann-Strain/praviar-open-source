from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from praviar_pipeline.checkpoint import (
    DEV_CHECKPOINT_HMAC_KEYRING_SECRET,
    CheckpointIntegrityKeyRing,
)
from praviar_pipeline.models.audit import SearchQueryPlan  # noqa: TC001
from praviar_pipeline.models.markush_evidence import (
    MarkushEvidenceReceipt,
    build_markush_evidence_receipt,
)
from praviar_pipeline.models.report import SourceHealth
from praviar_pipeline.models.search import ExpandedSearchQueries
from praviar_pipeline.models.search_loop import SearchLoopResult
from praviar_pipeline.pipeline.runtime.audit import build_search_query_plan
from praviar_pipeline.pipeline.search.markush_evidence import (
    evaluate_markush_clearance_evidence,
)

_SMILES = "CC(=O)OC1=CC=CC=C1C(=O)O"
_ORG_ID = "00000000-0000-4000-8000-000000000001"
_CONTROLS = b"\x89PNG\r\n\x1a\n" + b"PATENTSCOPE control panel evidence"
_LIMITATIONS = [
    "PATENTSCOPE does not document a stable chemical-search workbook schema.",
    "The receipt records retrieval evidence and does not establish claim construction.",
]
_INTEGRITY_KEYS = CheckpointIntegrityKeyRing.from_secret(DEV_CHECKPOINT_HMAC_KEYRING_SECRET)


def _verified_receipt(*, executed_at: datetime | None = None) -> MarkushEvidenceReceipt:
    source_executed_at = executed_at or datetime.now(UTC) - timedelta(days=1)
    return build_markush_evidence_receipt(
        status="verified_manual",
        organization_id=_ORG_ID,
        target_structure=_SMILES,
        query_structure=_SMILES,
        query_role="target_compound",
        chemical_search_mode="substructure",
        markush_method="formula_matching",
        markush_match_mode="substructure",
        wipo_query_field=None,
        family_grouping_enabled=True,
        limitations=_LIMITATIONS,
        executed_at=source_executed_at,
        server_imported_at=source_executed_at + timedelta(hours=1),
        analyst_identity="analyst:user-1",
        reviewer_identity="reviewer:user-2",
        artifact_bytes=b"immutable PATENTSCOPE export fixture",
        artifact_filename="patentscope-results.xlsx",
        artifact_media_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        controls_artifact_bytes=_CONTROLS,
        controls_artifact_filename="patentscope-controls.png",
        controls_artifact_media_type="image/png",
        result_count=2,
        selected_publication_ids=["WO-2020123456-A1", "EP-1234567-B1"],
        attestation_key_id=_INTEGRITY_KEYS.active_key_id,
        attestation_key=_INTEGRITY_KEYS.active_key(),
    )


def _settings(**updates):
    values = {
        "search_allowed_jurisdictions": ["US", "EP"],
        "search_enable_pubchem": True,
        "search_enable_pubchem_genus": True,
        "search_enable_surechembl": False,
        "search_enable_bigquery": True,
        "search_enable_patcid": False,
        "search_enable_ncbi_patent_sequence": True,
        "ops_consumer_key": "",
        "ops_consumer_secret": "",
        "patentsview_api_key": "",
        "kipris_api_key": "",
        "patentscope_username": "",
        "patentscope_password": "",
        "require_verified_manual_markush": True,
        "markush_evidence_max_age_days": 35,
        "markush_evidence_receipt": None,
        "checkpoint_integrity_keys": _INTEGRITY_KEYS,
    }
    values.update(updates)
    return SimpleNamespace(**values)


def _query_plan(receipt: MarkushEvidenceReceipt | None = None) -> SearchQueryPlan:
    return build_search_query_plan(
        compound=SimpleNamespace(
            name="aspirin",
            canonical_smiles=_SMILES,
            scaffold_smiles="c1ccccc1",
            inchi_key="BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
            pubchem_cid=2244,
            synonyms=[],
            cas_numbers=["50-78-2"],
            compound_type="small_molecule",
            protein_subunit_sequences=[],
        ),
        expanded_queries=ExpandedSearchQueries(),
        search_loop_result=SearchLoopResult(),
        source_health=SourceHealth(),
        settings=_settings(markush_evidence_receipt=receipt),
    )


def test_verified_receipt_binds_original_artifact_query_and_selection() -> None:
    receipt = _verified_receipt()

    assert receipt.status == "verified_manual"
    assert receipt.organization_id == _ORG_ID
    assert len(receipt.target_structure_sha256) == 64
    assert receipt.chemical_search_mode == "substructure"
    assert receipt.markush_method == "formula_matching"
    assert receipt.markush_match_mode == "substructure"
    assert receipt.wipo_query_field is None
    assert receipt.selected_publication_ids == ["WO2020123456A1", "EP1234567B1"]
    assert receipt.imported_artifact_sha256 is not None
    assert receipt.imported_artifact_size_bytes == len(b"immutable PATENTSCOPE export fixture")
    assert len(receipt.selected_publication_ids_sha256) == 64
    assert len(receipt.receipt_sha256) == 64

    tampered = receipt.model_dump(mode="json")
    tampered["result_count"] = 3
    with pytest.raises(ValidationError, match="receipt digest mismatch"):
        MarkushEvidenceReceipt.model_validate(tampered)


def test_verified_receipt_requires_independent_reviewer_and_complete_artifact() -> None:
    with pytest.raises(ValidationError, match="must be distinct"):
        build_markush_evidence_receipt(
            status="verified_manual",
            organization_id=_ORG_ID,
            target_structure=_SMILES,
            query_structure=_SMILES,
            query_role="target_compound",
            chemical_search_mode="substructure",
            markush_method="formula_matching",
            markush_match_mode="substructure",
            wipo_query_field=None,
            family_grouping_enabled=True,
            limitations=_LIMITATIONS,
            executed_at=datetime.now(UTC) - timedelta(minutes=1),
            server_imported_at=datetime.now(UTC),
            analyst_identity="same-user",
            reviewer_identity="same-user",
            artifact_bytes=b"fixture",
            artifact_filename="results.xlsx",
            artifact_media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            controls_artifact_bytes=_CONTROLS,
            controls_artifact_filename="controls.png",
            controls_artifact_media_type="image/png",
            result_count=0,
            attestation_key_id=_INTEGRITY_KEYS.active_key_id,
            attestation_key=_INTEGRITY_KEYS.active_key(),
        )

    with pytest.raises(ValidationError, match="is incomplete"):
        build_markush_evidence_receipt(
            status="verified_manual",
            organization_id=_ORG_ID,
            target_structure=_SMILES,
            query_structure=_SMILES,
            query_role="target_compound",
            chemical_search_mode="substructure",
            markush_method="formula_matching",
            markush_match_mode="substructure",
            wipo_query_field=None,
            family_grouping_enabled=True,
            limitations=_LIMITATIONS,
            executed_at=datetime.now(UTC) - timedelta(minutes=1),
            server_imported_at=datetime.now(UTC),
            analyst_identity="analyst",
            reviewer_identity="reviewer",
            result_count=0,
            attestation_key_id=_INTEGRITY_KEYS.active_key_id,
            attestation_key=_INTEGRITY_KEYS.active_key(),
        )


def test_query_plan_rejects_receipt_for_a_different_structure() -> None:
    receipt = build_markush_evidence_receipt(
        status="verified_manual",
        organization_id=_ORG_ID,
        target_structure=_SMILES,
        query_structure="CCO",
        query_role="target_compound",
        chemical_search_mode="substructure",
        markush_method="formula_matching",
        markush_match_mode="substructure",
        wipo_query_field=None,
        family_grouping_enabled=True,
        limitations=_LIMITATIONS,
        executed_at=datetime.now(UTC) - timedelta(minutes=1),
        server_imported_at=datetime.now(UTC),
        analyst_identity="analyst",
        reviewer_identity="reviewer",
        artifact_bytes=b"fixture",
        artifact_filename="results.xlsx",
        artifact_media_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        controls_artifact_bytes=_CONTROLS,
        controls_artifact_filename="controls.png",
        controls_artifact_media_type="image/png",
        result_count=0,
        attestation_key_id=_INTEGRITY_KEYS.active_key_id,
        attestation_key=_INTEGRITY_KEYS.active_key(),
    )

    with pytest.raises(ValidationError, match="not bound to this query plan"):
        _query_plan(receipt)


def test_query_plan_and_clearance_evaluation_accept_fresh_verified_receipt() -> None:
    receipt = _verified_receipt()
    plan = _query_plan(receipt)
    report = SimpleNamespace(
        compound=SimpleNamespace(compound_type="small_molecule"),
        audit_trail=SimpleNamespace(query_plan=plan),
    )

    evaluation = evaluate_markush_clearance_evidence(
        report,
        _settings(),
        now=datetime.now(UTC),
    )

    assert plan.true_markush_coverage_status == "verified_manual"
    assert plan.markush_evidence == receipt
    assert evaluation.eligible_for_positive_clearance is True
    assert evaluation.status == "verified_manual"
    assert evaluation.receipt_sha256 == receipt.receipt_sha256


def test_clearance_evaluation_fails_closed_for_absent_and_stale_evidence() -> None:
    absent_report = SimpleNamespace(
        compound=SimpleNamespace(compound_type="small_molecule"),
        audit_trail=SimpleNamespace(query_plan=_query_plan()),
    )
    absent = evaluate_markush_clearance_evidence(absent_report, _settings())
    assert absent.eligible_for_positive_clearance is False
    assert absent.status == "not_run"

    stale_receipt = _verified_receipt(executed_at=datetime.now(UTC) - timedelta(days=36))
    stale_report = SimpleNamespace(
        compound=SimpleNamespace(compound_type="small_molecule"),
        audit_trail=SimpleNamespace(query_plan=_query_plan(stale_receipt)),
    )
    stale = evaluate_markush_clearance_evidence(
        stale_report,
        _settings(),
        now=datetime.now(UTC),
    )
    assert stale.eligible_for_positive_clearance is False
    assert stale.status == "incomplete"
    assert stale.age_days == 36
    assert "stale" in stale.failure_reasons[0]


def test_clearance_evaluation_rejects_a_validly_shaped_forged_attestation() -> None:
    forged = build_markush_evidence_receipt(
        status="verified_manual",
        organization_id=_ORG_ID,
        target_structure=_SMILES,
        query_structure=_SMILES,
        query_role="target_compound",
        chemical_search_mode="substructure",
        markush_method="formula_matching",
        markush_match_mode="substructure",
        wipo_query_field=None,
        family_grouping_enabled=True,
        limitations=_LIMITATIONS,
        executed_at=datetime.now(UTC) - timedelta(minutes=1),
        server_imported_at=datetime.now(UTC),
        analyst_identity="analyst",
        reviewer_identity="reviewer",
        artifact_bytes=b"fixture",
        artifact_filename="results.xlsx",
        artifact_media_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        controls_artifact_bytes=_CONTROLS,
        controls_artifact_filename="controls.png",
        controls_artifact_media_type="image/png",
        result_count=0,
        attestation_key_id=_INTEGRITY_KEYS.active_key_id,
        attestation_key=b"forged-attestation-key-material-000",
    )
    report = SimpleNamespace(
        compound=SimpleNamespace(compound_type="small_molecule"),
        audit_trail=SimpleNamespace(query_plan=_query_plan(forged)),
    )

    evaluation = evaluate_markush_clearance_evidence(report, _settings())

    assert evaluation.eligible_for_positive_clearance is False
    assert evaluation.status == "incomplete"
    assert "attestation is invalid" in evaluation.failure_reasons[0]


def test_enumeration_receipt_requires_exact_modes_and_enum_field() -> None:
    receipt = build_markush_evidence_receipt(
        status="not_run",
        organization_id=_ORG_ID,
        target_structure=_SMILES,
        query_structure=_SMILES,
        query_role="target_compound",
        chemical_search_mode="exact",
        markush_method="enumeration",
        markush_match_mode="exact",
        wipo_query_field="ENUM",
        family_grouping_enabled=True,
        limitations=_LIMITATIONS,
    )

    assert receipt.markush_method == "enumeration"
    assert receipt.wipo_query_field == "ENUM"

    with pytest.raises(
        ValidationError,
        match="enumeration requires exact chemical and Markush matching",
    ):
        build_markush_evidence_receipt(
            status="not_run",
            organization_id=_ORG_ID,
            target_structure=_SMILES,
            query_structure=_SMILES,
            query_role="target_compound",
            chemical_search_mode="substructure",
            markush_method="enumeration",
            markush_match_mode="exact",
            wipo_query_field="ENUM",
            family_grouping_enabled=True,
            limitations=_LIMITATIONS,
        )


def test_formula_matching_receipt_rejects_enum_field() -> None:
    with pytest.raises(ValidationError, match="ENUM is valid only"):
        build_markush_evidence_receipt(
            status="not_run",
            organization_id=_ORG_ID,
            target_structure=_SMILES,
            query_structure=_SMILES,
            query_role="target_compound",
            chemical_search_mode="substructure",
            markush_method="formula_matching",
            markush_match_mode="substructure",
            wipo_query_field="ENUM",
            family_grouping_enabled=True,
            limitations=_LIMITATIONS,
        )


def test_demo_fixture_must_explicitly_disable_markush_clearance_gate() -> None:
    report = SimpleNamespace(
        compound=SimpleNamespace(compound_type="small_molecule"),
        audit_trail=SimpleNamespace(query_plan=_query_plan()),
    )

    evaluation = evaluate_markush_clearance_evidence(
        report,
        _settings(require_verified_manual_markush=False),
    )

    assert evaluation.required is False
    assert evaluation.eligible_for_positive_clearance is True
    assert evaluation.status == "not_required"
