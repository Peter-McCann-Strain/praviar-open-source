from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.models.report import (
    EvidenceArtifact,
    EvidenceArtifactType,
    EvidenceAuthorityTier,
)
from praviar_pipeline.models.report_common import SourceStatus
from praviar_pipeline.pipeline.runtime.evidence_artifacts import (
    build_adapter_result,
    build_patent_record_artifacts,
    group_artifacts_by_source,
)


def test_build_patent_record_artifacts_preserves_claim_program_artifact_ids():
    record = SimpleNamespace(
        patent_id="US1234567B2",
        family_id="fam-1",
        source_names=["epo_search", "patentsview"],
        authoritative_source_names=["epo_search"],
        supporting_source_names=["patentsview"],
        jurisdiction="US",
        has_claims_text=True,
        has_family_context=True,
        has_us_file_wrapper_dossier=False,
        has_us_prosecution_context=True,
        prosecution_dossier_sections=["office_actions"],
        has_ep_register_context=False,
        has_ptab_proceedings=False,
        has_orange_book_listing=False,
        analysis_completed=True,
    )
    claim_programs = [
        SimpleNamespace(
            claim_number=1,
            missing_components=[],
        )
    ]

    artifacts = build_patent_record_artifacts(record, claim_programs)

    assert artifacts[0].artifact_type == EvidenceArtifactType.SEARCH_HIT
    assert artifacts[0].authority_tier == EvidenceAuthorityTier.AUTHORITATIVE
    assert any(artifact.artifact_type == EvidenceArtifactType.CLAIMS_TEXT for artifact in artifacts)
    prosecution_artifact = next(
        artifact
        for artifact in artifacts
        if artifact.artifact_type == EvidenceArtifactType.PROSECUTION_DOSSIER
    )
    assert prosecution_artifact.source_name == "epo_search"
    assert prosecution_artifact.record_basis == ["office_actions"]
    assert any(artifact.artifact_id == "US1234567B2:claim:1" for artifact in artifacts)


def test_build_adapter_result_adds_required_source_warning_for_missing_artifacts():
    result = build_adapter_result(
        source_name="epo_register",
        artifacts=[],
        authoritative_sources=set(),
        supporting_sources=set(),
        required_components={"ep_register_context"},
        status=SourceStatus.SKIPPED,
    )

    assert result.expected_components == ["ep_register_context"]
    assert result.missing_components == ["ep_register_context"]
    assert result.warnings == [
        "Required adapter was not queried or produced no artifacts for: ep_register_context.",
        "Missing expected record components: ep_register_context.",
    ]


def test_group_artifacts_by_source_expands_comma_separated_source_names():
    artifacts = [
        EvidenceArtifact(
            artifact_id="US123:search_hit",
            artifact_type=EvidenceArtifactType.SEARCH_HIT,
            source_name="epo_search,patentsview",
            authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
            patent_id="US123",
            summary="test",
            record_basis=["search_hit"],
            linked_node_ids=["patent:US123"],
        )
    ]

    grouped = group_artifacts_by_source(artifacts)

    assert grouped["epo_search"][0].artifact_id == "US123:search_hit"
    assert grouped["patentsview"][0].artifact_id == "US123:search_hit"
