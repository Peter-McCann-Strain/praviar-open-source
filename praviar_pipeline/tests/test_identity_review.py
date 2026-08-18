from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from praviar_pipeline.models.compound import ResolvedCompound
from praviar_pipeline.models.hitl import CheckpointDecision, CheckpointType
from praviar_pipeline.pipeline.identity_review import build_identity_review_context
from praviar_pipeline.pipeline.resolution.identity_derivations import (
    derive_prodrug_candidates,
    enumerate_tautomer_candidates,
)
from praviar_pipeline.pipeline.runtime.pipeline_steps import SearchStepResult
from praviar_pipeline.pipeline.runtime.run_execution import (
    RunCallbacks,
    execute_resolution_to_search_flow,
)


def _compound(**overrides) -> ResolvedCompound:
    values = {
        "name": "Test chiral ester",
        "canonical_smiles": "C[C@H](O)C(=O)OC",
        "inchi": "InChI=1S/C5H10O3/example",
        "inchi_key": "AAAAAAAAAAAAAA-BBBBBBBBBB-C",
        "pubchem_cid": 123,
        "synonyms": ["Test chiral ester", "Research code TCE-1"],
        "cas_numbers": ["12345-67-8"],
        "molecular_formula": "C5H10O3",
        "molecular_weight": 118.13,
        "scaffold_smiles": "C1CC1",
        "free_base_smiles": "C[C@H](O)C(=O)OC",
        "stereo_stripped_smiles": "CC(O)C(=O)OC",
        "prodrug_pattern": "ester_prodrug",
        "original_input": "C[C@H](O)C(=O)OC",
        "input_type": "smiles",
    }
    values.update(overrides)
    return ResolvedCompound(**values)


def _settings(**overrides) -> SimpleNamespace:
    values = {
        "product_context": {"salt_polymorph_form": "Hydrochloride, Form A"},
        "search_enable_pubchem": True,
        "search_enable_bigquery": True,
        "search_enable_surechembl": True,
        "search_enable_patcid": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_identity_review_packet_binds_resolved_identity_and_exact_search_envelope() -> None:
    context = build_identity_review_context(
        _compound(),
        settings=_settings(),
        run_id="run-123",
    )

    assert context["schema_version"] == "identity-review/v2"
    assert context["checkpoint_id"].startswith("run-123:identity_review:")
    assert len(context["identity_fingerprint"]) == 64
    assert context["comparison"]["outcome"] == "exact_match"
    assert context["resolved_identity"]["source_authority"] == "PubChem"
    assert context["resolved_identity"]["authoritative_record_present"] is True
    assert context["downstream_state"] == "search_blocked_pending_identity_approval"

    lanes = {lane["lane_id"]: lane for lane in context["search_envelope"]}
    assert lanes["canonical_structure"]["values"] == ["C[C@H](O)C(=O)OC"]
    assert lanes["stereo_stripped_structure"]["differs_from_canonical"] is True
    assert lanes["stereo_stripped_structure"]["enabled"] is True
    assert lanes["inchikey"]["sources"] == [
        "PatCID",
        "BigQuery chemical annotations",
    ]

    variants = {assessment["variant"]: assessment for assessment in context["variant_assessments"]}
    assert variants["salt_or_product_form"]["declared_value"] == "Hydrochloride, Form A"
    assert variants["stereochemistry"]["status"] == "derived_search_form"
    assert variants["tautomer"]["status"] == "not_modeled"
    assert variants["tautomer"]["requires_attention"] is True
    assert variants["prodrug"]["status"] == "candidate_detected"
    assert "no active-form lane" in variants["prodrug"]["search_effect"]


def test_identity_review_fingerprint_changes_when_product_form_changes() -> None:
    first = build_identity_review_context(
        _compound(),
        settings=_settings(product_context={"salt_polymorph_form": "Free base, Form I"}),
        run_id="run-123",
    )
    second = build_identity_review_context(
        _compound(),
        settings=_settings(product_context={"salt_polymorph_form": "Hydrochloride, Form II"}),
        run_id="run-123",
    )

    assert first["identity_fingerprint"] != second["identity_fingerprint"]
    assert first["checkpoint_id"] != second["checkpoint_id"]


def test_identity_review_fingerprints_and_exposes_derived_structure_receipts() -> None:
    source = "CC(=O)Oc1ccccc1C(=O)O"
    tautomers = enumerate_tautomer_candidates(source)
    prodrug = derive_prodrug_candidates(source)
    compound = _compound(
        canonical_smiles=source,
        free_base_smiles=source,
        stereo_stripped_smiles=source,
        tautomer_enumeration=tautomers,
        prodrug_candidates=prodrug.candidates,
        unsupported_prodrug_motifs=prodrug.unsupported_motifs,
        prodrug_pattern=prodrug.detected_motifs[0],
        original_input=source,
    )

    context = build_identity_review_context(
        compound,
        settings=_settings(),
        run_id="run-derived",
    )
    lanes = {lane["lane_id"]: lane for lane in context["search_envelope"]}
    variants = {assessment["variant"]: assessment for assessment in context["variant_assessments"]}

    assert lanes["validated_tautomer_structures"]["enabled"] is True
    assert lanes["prodrug_parent_hypotheses"]["values"] == ["O=C(O)c1ccccc1O"]
    assert variants["tautomer"]["status"] == "derived_search_form"
    assert variants["prodrug"]["status"] == "derived_search_form"
    assert context["derivation_evidence"]["tautomer_enumeration"]["status"] == "completed"
    assert (
        context["derivation_evidence"]["prodrug_candidates"][0]["candidate_id"]
        == prodrug.candidates[0].candidate_id
    )
    assert "explicitly hypothetical" in context["approval_attestation"]

    without_hypothesis = build_identity_review_context(
        compound.model_copy(update={"prodrug_candidates": []}),
        settings=_settings(),
        run_id="run-derived",
    )
    assert context["identity_fingerprint"] != without_hypothesis["identity_fingerprint"]


def test_identity_review_accepts_exact_primary_complete_gsrs_protein_record() -> None:
    context = build_identity_review_context(
        _compound(
            name="ADALIMUMAB",
            compound_type="biologic",
            canonical_smiles="",
            inchi="",
            inchi_key="",
            pubchem_cid=None,
            bla_number="",
            scaffold_smiles="",
            free_base_smiles="",
            stereo_stripped_smiles="",
            prodrug_pattern=None,
            original_input="adalimumab",
            input_type="name",
            unii="FYS6T7F842",
            gsrs_uuid="49c070a0-3b9f-4617-86ad-d5551a84fbab",
            gsrs_substance_class="protein",
            gsrs_definition_type="PRIMARY",
            gsrs_definition_level="COMPLETE",
            gsrs_record_version="119",
            gsrs_names_last_updated="2026-07-25",
            gsrs_record_last_updated="2025-09-19",
        ),
        settings=_settings(),
        run_id="run-gsrs",
    )

    assert context["resolved_identity"]["identity_source"] == "fda_gsrs"
    assert context["resolved_identity"]["authoritative_record_present"] is True
    assert "not approval status" in context["resolved_identity"]["source_authority"]
    lanes = {lane["lane_id"]: lane for lane in context["search_envelope"]}
    assert lanes["fda_gsrs_identity"]["values"] == [
        "FYS6T7F842",
        "49c070a0-3b9f-4617-86ad-d5551a84fbab",
    ]


def test_identity_review_is_explicit_about_biologic_variant_limits() -> None:
    context = build_identity_review_context(
        _compound(
            name="Examplemab",
            compound_type="biologic",
            canonical_smiles="",
            inchi="",
            inchi_key="",
            pubchem_cid=None,
            bla_number="761234",
            reference_product="Examplemab reference",
            scaffold_smiles="",
            free_base_smiles="",
            stereo_stripped_smiles="",
            prodrug_pattern=None,
            original_input="Examplemab",
            input_type="name",
        ),
        settings=_settings(),
        run_id="run-biologic",
    )

    assert context["resolved_identity"]["source_authority"] == "FDA Purple Book"
    assert context["resolved_identity"]["authoritative_record_present"] is True
    assert {assessment["status"] for assessment in context["variant_assessments"]} == {
        "not_applicable"
    }
    assert all(assessment["requires_attention"] for assessment in context["variant_assessments"])


@pytest.mark.asyncio
async def test_identity_checkpoint_runs_after_resolution_and_before_query_expansion() -> None:
    compound = _compound()
    event_order: list[str] = []
    state = SimpleNamespace(
        completed_step=0,
        user_input=compound.original_input,
        compound=None,
        expanded_queries=None,
        patent_hits=[],
        source_health=None,
        search_funnel=[],
        search_loop_result=None,
        regulatory_exclusivity=None,
        timing_data=[],
        settings=SimpleNamespace(drawing_analysis_enabled=False),
    )

    def save_checkpoint(step: int) -> None:
        state.completed_step = max(state.completed_step, step)

    callbacks = RunCallbacks(
        notify=MagicMock(),
        raise_if_cancelled=MagicMock(),
        save_checkpoint=save_checkpoint,
        make_timing=MagicMock(),
    )

    async def resolve(**_kwargs):
        event_order.append("resolve")
        return compound

    async def review(_state, _callbacks):
        event_order.append("identity_review")

    async def expand(**_kwargs):
        event_order.append("expand")
        return SimpleNamespace()

    async def search(**_kwargs):
        event_order.append("search")
        return SearchStepResult([], None, [], None)

    with (
        patch(
            "praviar_pipeline.pipeline.runtime.run_execution.run_resolution_step",
            new=resolve,
        ),
        patch(
            "praviar_pipeline.pipeline.runtime.run_execution._await_identity_checkpoint",
            new=review,
        ),
        patch(
            "praviar_pipeline.pipeline.runtime.run_execution.run_query_expansion_step",
            new=expand,
        ),
        patch(
            "praviar_pipeline.pipeline.runtime.run_execution.run_search_step",
            new=search,
        ),
        patch(
            "praviar_pipeline.pipeline.runtime.run_execution.run_regulatory_enrichment",
            new=AsyncMock(return_value=None),
        ),
    ):
        await execute_resolution_to_search_flow(state=state, callbacks=callbacks)

    assert event_order == ["resolve", "identity_review", "expand", "search"]


@pytest.mark.asyncio
async def test_required_identity_checkpoint_accepts_only_persisted_approval() -> None:
    compound = _compound()
    notify = MagicMock()
    settings = _settings(
        hitl_enabled=False,
        hitl_checkpoints=[],
        hitl_auto_skip_minutes=1,
        identity_review_required=True,
    )

    async def provider(checkpoint_type, context):
        assert checkpoint_type == CheckpointType.IDENTITY_REVIEW
        assert context["identity_fingerprint"]
        return CheckpointDecision(
            checkpoint_type=CheckpointType.IDENTITY_REVIEW,
            action="approve",
            reviewer_id="reviewer-1",
        )

    from praviar_pipeline.pipeline.runtime.run_execution import _await_identity_checkpoint

    await _await_identity_checkpoint(
        SimpleNamespace(compound=compound, settings=settings, run_id="run-123"),
        RunCallbacks(
            notify=notify,
            raise_if_cancelled=MagicMock(),
            save_checkpoint=MagicMock(),
            make_timing=MagicMock(),
            checkpoint_decision_provider=provider,
            checkpoint_poll_interval_seconds=0,
        ),
    )

    payload = notify.call_args.args[3]
    assert payload["checkpoint_type"] == "identity_review"
    assert payload["requires_response"] is True
    assert payload["context"]["downstream_state"] == ("search_blocked_pending_identity_approval")
