"""Artifact builders for the evidence-fabric runtime substrate.

This module consolidates the internal adapter registry, the adapter
coverage ledger, the artifact builders, the adapter-result helpers and the
top-level evidence-artifact and adapter-result builders.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from praviar_pipeline.models.report import (
    EvidenceAdapterKind,
    EvidenceAdapterResult,
    EvidenceArtifact,
    EvidenceArtifactType,
    EvidenceAuthorityTier,
    EvidenceCollectionState,
    RecordComponentStatusValue,
)
from praviar_pipeline.models.report_common import SourceStatus
from praviar_pipeline.models.search_loop import CoverageGap
from praviar_pipeline.pipeline.report.evidence_index_patent_helpers import derive_jurisdiction
from praviar_pipeline.pipeline.report.evidence_index_shared import unique_strings
from praviar_pipeline.pipeline.runtime.evidence_policy import COMPONENT_DESCRIPTIONS

if TYPE_CHECKING:
    from praviar_pipeline.models.equivalents import DoEAssessment
    from praviar_pipeline.models.invalidity import InvalidityAssessment
    from praviar_pipeline.models.report_evidence_records import (
        ClaimProgramDecision,
        PatentEvidenceRecord,
    )


@dataclass(frozen=True, slots=True)
class AdapterDefinition:
    adapter_name: str
    adapter_kind: EvidenceAdapterKind
    default_authority_tier: EvidenceAuthorityTier
    expected_components: tuple[str, ...] = ()
    freshness_note: str = ""
    supports_authoritative_findings: bool = False


_ADAPTER_REGISTRY: dict[str, AdapterDefinition] = {
    "pubchem_sdq": AdapterDefinition(
        adapter_name="pubchem_sdq",
        adapter_kind=EvidenceAdapterKind.SEARCH,
        default_authority_tier=EvidenceAuthorityTier.SUPPORTING,
        freshness_note="Search-source record captured during the current pipeline run.",
    ),
    "bigquery": AdapterDefinition(
        adapter_name="bigquery",
        adapter_kind=EvidenceAdapterKind.SEARCH,
        default_authority_tier=EvidenceAuthorityTier.SUPPORTING,
        expected_components=("claims_text",),
        freshness_note="Index-backed patent record captured during the current pipeline run.",
    ),
    "patentsview": AdapterDefinition(
        adapter_name="patentsview",
        adapter_kind=EvidenceAdapterKind.SEARCH,
        default_authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
        expected_components=("claims_text",),
        freshness_note=(
            "PatentsView public-record payload captured during the current pipeline run."
        ),
        supports_authoritative_findings=True,
    ),
    "epo_search": AdapterDefinition(
        adapter_name="epo_search",
        adapter_kind=EvidenceAdapterKind.SEARCH,
        default_authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
        freshness_note="EPO search record captured during the current pipeline run.",
        supports_authoritative_findings=True,
    ),
    "uspto_odp": AdapterDefinition(
        adapter_name="uspto_odp",
        adapter_kind=EvidenceAdapterKind.LEGAL_RECORD,
        default_authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
        expected_components=("us_prosecution_context", "us_file_wrapper_dossier"),
        freshness_note="Official USPTO ODP record captured during the current pipeline run.",
        supports_authoritative_findings=True,
    ),
    "epo_register": AdapterDefinition(
        adapter_name="epo_register",
        adapter_kind=EvidenceAdapterKind.LEGAL_RECORD,
        default_authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
        expected_components=("ep_register_context",),
        freshness_note="Official EPO register record captured during the current pipeline run.",
        supports_authoritative_findings=True,
    ),
    "ptab": AdapterDefinition(
        adapter_name="ptab",
        adapter_kind=EvidenceAdapterKind.LEGAL_RECORD,
        default_authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
        expected_components=("ptab_record",),
        freshness_note="Official PTAB record captured during the current pipeline run.",
        supports_authoritative_findings=True,
    ),
    "orange_book": AdapterDefinition(
        adapter_name="orange_book",
        adapter_kind=EvidenceAdapterKind.REGULATORY,
        default_authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
        expected_components=("orange_book_record",),
        freshness_note="Official FDA Orange Book record captured during the current pipeline run.",
        supports_authoritative_findings=True,
    ),
    "purple_book": AdapterDefinition(
        adapter_name="purple_book",
        adapter_kind=EvidenceAdapterKind.REGULATORY,
        default_authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
        freshness_note="Official FDA Purple Book record captured during the current pipeline run.",
        supports_authoritative_findings=True,
    ),
    "family_record": AdapterDefinition(
        adapter_name="family_record",
        adapter_kind=EvidenceAdapterKind.DERIVED,
        default_authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
        expected_components=("family_context",),
        freshness_note="Family context was normalized during the current pipeline run.",
        supports_authoritative_findings=True,
    ),
    "step4_analyze": AdapterDefinition(
        adapter_name="step4_analyze",
        adapter_kind=EvidenceAdapterKind.PIPELINE,
        default_authority_tier=EvidenceAuthorityTier.SUPPORTING,
        expected_components=("claim_level_analysis",),
        freshness_note="Claim-analysis evidence was generated during the current pipeline run.",
    ),
    "step5_doe": AdapterDefinition(
        adapter_name="step5_doe",
        adapter_kind=EvidenceAdapterKind.PIPELINE,
        default_authority_tier=EvidenceAuthorityTier.SUPPORTING,
        freshness_note="DoE evidence was generated during the current pipeline run.",
    ),
    "step6_invalidity": AdapterDefinition(
        adapter_name="step6_invalidity",
        adapter_kind=EvidenceAdapterKind.PIPELINE,
        default_authority_tier=EvidenceAuthorityTier.SUPPORTING,
        freshness_note="Invalidity evidence was generated during the current pipeline run.",
    ),
    "step7_verification": AdapterDefinition(
        adapter_name="step7_verification",
        adapter_kind=EvidenceAdapterKind.PIPELINE,
        default_authority_tier=EvidenceAuthorityTier.SUPPORTING,
        expected_components=("verification",),
        freshness_note="Verification evidence was generated during the current pipeline run.",
    ),
    "step4b_critic": AdapterDefinition(
        adapter_name="step4b_critic",
        adapter_kind=EvidenceAdapterKind.PIPELINE,
        default_authority_tier=EvidenceAuthorityTier.SUPPORTING,
        freshness_note="Critic-review evidence was generated during the current pipeline run.",
    ),
    "coverage_policy": AdapterDefinition(
        adapter_name="coverage_policy",
        adapter_kind=EvidenceAdapterKind.POLICY,
        default_authority_tier=EvidenceAuthorityTier.DISCOVERY,
        freshness_note="Coverage-policy gap evidence was derived during the current pipeline run.",
    ),
    "normalized_report": AdapterDefinition(
        adapter_name="normalized_report",
        adapter_kind=EvidenceAdapterKind.DERIVED,
        default_authority_tier=EvidenceAuthorityTier.DISCOVERY,
        freshness_note="Derived from normalized report evidence.",
    ),
}


_ARTIFACT_COMPONENTS: dict[EvidenceArtifactType, tuple[str, ...]] = {
    EvidenceArtifactType.CLAIMS_TEXT: ("claims_text",),
    EvidenceArtifactType.FAMILY_CONTEXT: ("family_context",),
    EvidenceArtifactType.PROSECUTION_DOSSIER: ("us_prosecution_context", "us_file_wrapper_dossier"),
    EvidenceArtifactType.EP_REGISTER_RECORD: ("ep_register_context",),
    EvidenceArtifactType.PTAB_RECORD: ("ptab_record",),
    EvidenceArtifactType.ORANGE_BOOK_RECORD: ("orange_book_record",),
    EvidenceArtifactType.CLAIM_ANALYSIS: ("claim_level_analysis",),
    EvidenceArtifactType.VERIFICATION: ("verification",),
}


_PROSECUTION_CONTEXT_BASES = {
    "amendments",
    "continuity",
    "office_actions",
    "us_prosecution_context",
    "us_prosecution_record",
}


_FILE_WRAPPER_BASES = {"file_wrapper_dossier", "us_file_wrapper_dossier"}


def iter_artifact_source_names(artifact) -> list[str]:
    raw = str(getattr(artifact, "source_name", "") or "")
    if not raw:
        return []
    return [name.strip() for name in raw.split(",") if name.strip()]


def adapter_definition_for(source_name: str) -> AdapterDefinition:
    if source_name in _ADAPTER_REGISTRY:
        return _ADAPTER_REGISTRY[source_name]
    lowered = source_name.lower()
    if lowered.startswith("step"):
        return AdapterDefinition(
            adapter_name=source_name,
            adapter_kind=EvidenceAdapterKind.PIPELINE,
            default_authority_tier=EvidenceAuthorityTier.SUPPORTING,
            freshness_note="Pipeline-derived evidence captured during the current pipeline run.",
        )
    return AdapterDefinition(
        adapter_name=source_name,
        adapter_kind=EvidenceAdapterKind.DERIVED,
        default_authority_tier=EvidenceAuthorityTier.DISCOVERY,
        freshness_note="Derived from normalized report evidence.",
    )


def authority_tier_for_adapter(
    source_name: str,
    *,
    authoritative_sources: set[str],
    supporting_sources: set[str],
) -> EvidenceAuthorityTier:
    if source_name in authoritative_sources:
        return EvidenceAuthorityTier.AUTHORITATIVE
    if source_name in supporting_sources:
        return EvidenceAuthorityTier.SUPPORTING
    return adapter_definition_for(source_name).default_authority_tier


def _artifact_components(artifact: EvidenceArtifact) -> tuple[str, ...]:
    artifact_type = artifact.artifact_type
    if artifact_type != EvidenceArtifactType.PROSECUTION_DOSSIER:
        return _ARTIFACT_COMPONENTS.get(artifact_type, ())

    record_basis = {
        str(value).strip()
        for value in list(getattr(artifact, "record_basis", []) or [])
        if str(value).strip()
    }
    if not record_basis:
        return _ARTIFACT_COMPONENTS[EvidenceArtifactType.PROSECUTION_DOSSIER]

    covered_components: list[str] = []
    if record_basis.intersection(_PROSECUTION_CONTEXT_BASES):
        covered_components.append("us_prosecution_context")
    if record_basis.intersection(_FILE_WRAPPER_BASES):
        covered_components.append("us_file_wrapper_dossier")
    return tuple(covered_components)


def derive_covered_components(artifacts: list[EvidenceArtifact]) -> list[str]:
    return unique_strings(
        [component for artifact in artifacts for component in _artifact_components(artifact)]
    )


def iter_policy_adapter_names(required_components: set[str] | list[str]) -> list[str]:
    """Return registry adapter names implied by the active record policy."""
    required = set(required_components or [])
    if not required:
        return []
    return sorted(
        definition.adapter_name
        for definition in _ADAPTER_REGISTRY.values()
        if required.intersection(definition.expected_components)
    )


def adapter_status_for_entry(entry) -> SourceStatus:
    value = getattr(getattr(entry, "status", None), "value", getattr(entry, "status", "ok"))
    if value == "failed":
        return SourceStatus.FAILED
    if value == "not_configured":
        return SourceStatus.NOT_CONFIGURED
    if value == "skipped":
        return SourceStatus.SKIPPED
    return SourceStatus.OK


def _component_status_value(component_status) -> str:
    return getattr(
        getattr(component_status, "status", None),
        "value",
        str(getattr(component_status, "status", "") or ""),
    )


def _record_mentions_source(record, source_name: str) -> bool:
    return source_name in (
        set(getattr(record, "source_names", []) or [])
        | set(getattr(record, "authoritative_source_names", []) or [])
        | set(getattr(record, "supporting_source_names", []) or [])
    )


def _fallback_target_patent_ids(
    *,
    expected_components: list[str],
    known_patent_ids: list[str],
) -> list[str]:
    if not expected_components:
        return []
    if any(component.startswith("us_") for component in expected_components) or any(
        component in {"ptab_record", "orange_book_record"} for component in expected_components
    ):
        return [patent_id for patent_id in known_patent_ids if patent_id.upper().startswith("US")]
    if any(component.startswith("ep_") for component in expected_components):
        return [patent_id for patent_id in known_patent_ids if patent_id.upper().startswith("EP")]
    return list(known_patent_ids)


def build_adapter_collection_ledger(
    *,
    source_name: str,
    patent_records,
    expected_components: list[str],
    required_components: set[str],
    artifacts: list[EvidenceArtifact],
    known_patent_ids: list[str],
    status: SourceStatus,
) -> tuple[EvidenceCollectionState, bool, list[str], list[str], list[str]]:
    """Derive adapter target and coverage state from the patent component ledger."""
    target_patent_ids: list[str] = []
    missing_patent_ids: list[str] = []
    covered_patent_ids = unique_strings(
        [artifact.patent_id for artifact in artifacts if artifact.patent_id]
    )
    required_before_clear = False

    for record in patent_records or []:
        relevant_statuses = [
            component_status
            for component_status in getattr(record, "component_statuses", []) or []
            if (
                component_status.component in expected_components
                and _component_status_value(component_status)
                != RecordComponentStatusValue.NOT_APPLICABLE.value
                and (
                    component_status.source_name == source_name
                    or _record_mentions_source(record, source_name)
                )
            )
        ]
        if not relevant_statuses:
            continue
        target_patent_ids.append(record.patent_id)
        if any(
            getattr(status_item, "required_before_clear", False)
            for status_item in relevant_statuses
        ):
            required_before_clear = True
        if any(
            _component_status_value(status_item)
            in {
                RecordComponentStatusValue.MISSING.value,
                RecordComponentStatusValue.FAILED.value,
            }
            for status_item in relevant_statuses
        ):
            missing_patent_ids.append(record.patent_id)

    fallback_target_patent_ids = _fallback_target_patent_ids(
        expected_components=expected_components,
        known_patent_ids=known_patent_ids,
    )
    target_patent_ids = unique_strings(
        target_patent_ids + covered_patent_ids + fallback_target_patent_ids
    )
    if not required_before_clear and fallback_target_patent_ids:
        required_before_clear = bool(set(expected_components).intersection(required_components))
    missing_patent_ids = unique_strings(
        missing_patent_ids
        + [
            patent_id
            for patent_id in target_patent_ids
            if patent_id not in covered_patent_ids and expected_components
        ]
    )

    if status in {SourceStatus.FAILED, SourceStatus.NOT_CONFIGURED}:
        collection_state = EvidenceCollectionState.FAILED
    elif target_patent_ids:
        if not missing_patent_ids:
            collection_state = EvidenceCollectionState.COLLECTED
        elif covered_patent_ids:
            collection_state = EvidenceCollectionState.PARTIAL
        else:
            collection_state = EvidenceCollectionState.MISSING
    elif (
        required_before_clear
        and expected_components
        and (missing_patent_ids or (not artifacts and status == SourceStatus.SKIPPED))
    ):
        collection_state = EvidenceCollectionState.MISSING
    elif artifacts:
        collection_state = EvidenceCollectionState.COLLECTED
    else:
        collection_state = EvidenceCollectionState.NOT_APPLICABLE

    return (
        collection_state,
        required_before_clear,
        target_patent_ids,
        covered_patent_ids,
        missing_patent_ids,
    )


def build_patent_record_artifacts(
    record: PatentEvidenceRecord,
    claim_programs: list[ClaimProgramDecision],
) -> list[EvidenceArtifact]:
    """Build all patent-record-backed artifacts for a single material patent."""
    artifacts: list[EvidenceArtifact] = []
    patent_node_id = f"patent:{record.patent_id}"
    family_node_ids = [f"family:{record.family_id}"] if record.family_id else []
    authority_tier = (
        EvidenceAuthorityTier.AUTHORITATIVE
        if record.authoritative_source_names
        else EvidenceAuthorityTier.SUPPORTING
        if record.supporting_source_names
        else EvidenceAuthorityTier.DISCOVERY
    )

    artifacts.append(
        EvidenceArtifact(
            artifact_id=f"{record.patent_id}:search_hit",
            artifact_type=EvidenceArtifactType.SEARCH_HIT,
            source_name=",".join(record.source_names),
            authority_tier=authority_tier,
            jurisdiction=record.jurisdiction,
            patent_id=record.patent_id,
            family_id=record.family_id,
            summary="Patent was retained as a material record in the final matter.",
            record_basis=record.source_names,
            linked_node_ids=[patent_node_id, *family_node_ids],
        )
    )
    if record.has_claims_text:
        primary_source_name = (record.authoritative_source_names or record.source_names or [""])[0]
        artifacts.append(
            EvidenceArtifact(
                artifact_id=f"{record.patent_id}:claims_text",
                artifact_type=EvidenceArtifactType.CLAIMS_TEXT,
                source_name=primary_source_name,
                authority_tier=authority_tier,
                jurisdiction=record.jurisdiction,
                patent_id=record.patent_id,
                family_id=record.family_id,
                summary="Full claims text was available for the final record.",
                record_basis=["claims_text"],
                linked_node_ids=[patent_node_id],
            )
        )
    if record.has_family_context:
        artifacts.append(
            EvidenceArtifact(
                artifact_id=f"{record.patent_id}:family_context",
                artifact_type=EvidenceArtifactType.FAMILY_CONTEXT,
                source_name="family_record",
                authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
                jurisdiction=record.jurisdiction,
                patent_id=record.patent_id,
                family_id=record.family_id,
                summary="Patent family context was normalized for the final matter.",
                record_basis=["family_record"],
                linked_node_ids=[patent_node_id, *family_node_ids],
            )
        )
    if record.has_us_file_wrapper_dossier or record.has_us_prosecution_context:
        record_basis = list(record.prosecution_dossier_sections or []) or ["us_prosecution_record"]
        if record.has_us_file_wrapper_dossier and "file_wrapper_dossier" not in record_basis:
            record_basis.append("file_wrapper_dossier")
        prosecution_source_name = (
            "uspto_odp"
            if record.has_us_file_wrapper_dossier
            else (record.authoritative_source_names or record.source_names or [""])[0]
        )
        prosecution_authority_tier = (
            EvidenceAuthorityTier.AUTHORITATIVE
            if record.has_us_file_wrapper_dossier
            else authority_tier
        )
        artifacts.append(
            EvidenceArtifact(
                artifact_id=f"{record.patent_id}:prosecution",
                artifact_type=EvidenceArtifactType.PROSECUTION_DOSSIER,
                source_name=prosecution_source_name,
                authority_tier=prosecution_authority_tier,
                jurisdiction=record.jurisdiction,
                patent_id=record.patent_id,
                family_id=record.family_id,
                summary=(
                    "U.S. prosecution and file-wrapper context was captured."
                    if record.has_us_file_wrapper_dossier
                    else "U.S. prosecution context was captured."
                ),
                record_basis=record_basis,
                linked_node_ids=[patent_node_id],
            )
        )
    if record.has_ep_register_context:
        artifacts.append(
            EvidenceArtifact(
                artifact_id=f"{record.patent_id}:ep_register",
                artifact_type=EvidenceArtifactType.EP_REGISTER_RECORD,
                source_name="epo_register",
                authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
                jurisdiction=record.jurisdiction,
                patent_id=record.patent_id,
                family_id=record.family_id,
                summary="EP register context was captured for the final record.",
                record_basis=["ep_register_record"],
                linked_node_ids=[patent_node_id],
            )
        )
    if record.has_ptab_proceedings:
        artifacts.append(
            EvidenceArtifact(
                artifact_id=f"{record.patent_id}:ptab",
                artifact_type=EvidenceArtifactType.PTAB_RECORD,
                source_name="ptab",
                authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
                jurisdiction=record.jurisdiction,
                patent_id=record.patent_id,
                family_id=record.family_id,
                summary="PTAB history was captured for the final record.",
                record_basis=["ptab_record"],
                linked_node_ids=[patent_node_id],
            )
        )
    if record.has_orange_book_listing:
        artifacts.append(
            EvidenceArtifact(
                artifact_id=f"{record.patent_id}:orange_book",
                artifact_type=EvidenceArtifactType.ORANGE_BOOK_RECORD,
                source_name="orange_book",
                authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
                jurisdiction=record.jurisdiction,
                patent_id=record.patent_id,
                family_id=record.family_id,
                summary="Orange Book context was captured for the final record.",
                record_basis=["orange_book_record"],
                linked_node_ids=[patent_node_id],
            )
        )
    if record.analysis_completed:
        artifacts.append(
            EvidenceArtifact(
                artifact_id=f"{record.patent_id}:claim_analysis",
                artifact_type=EvidenceArtifactType.CLAIM_ANALYSIS,
                source_name="step4_analyze",
                authority_tier=EvidenceAuthorityTier.SUPPORTING,
                jurisdiction=record.jurisdiction,
                patent_id=record.patent_id,
                family_id=record.family_id,
                summary="Claim analysis was completed for this patent.",
                record_basis=["claim_level_analysis"],
                linked_node_ids=[patent_node_id],
            )
        )
    for decision in claim_programs:
        if decision.claim_number <= 0:
            continue
        artifacts.append(
            EvidenceArtifact(
                artifact_id=f"{record.patent_id}:claim:{decision.claim_number}",
                artifact_type=EvidenceArtifactType.CLAIM_ANALYSIS,
                source_name="step4_analyze",
                authority_tier=EvidenceAuthorityTier.SUPPORTING,
                jurisdiction=record.jurisdiction,
                patent_id=record.patent_id,
                family_id=record.family_id,
                claim_number=decision.claim_number,
                summary="Claim-program decision captured for this claim.",
                record_basis=decision.missing_components or ["claim_program"],
                linked_node_ids=[
                    patent_node_id,
                    f"claim:{record.patent_id}:{decision.claim_number}",
                ],
            )
        )

    return artifacts


def build_doe_artifacts(doe_assessments: list[DoEAssessment]) -> list[EvidenceArtifact]:
    """Build DoE artifacts from recorded assessments."""
    return [
        EvidenceArtifact(
            artifact_id=(
                f"{assessment.patent_id}:doe:{assessment.claim_number}:{assessment.element_number}"
            ),
            artifact_type=EvidenceArtifactType.DOE_ASSESSMENT,
            source_name="step5_doe",
            authority_tier=EvidenceAuthorityTier.SUPPORTING,
            jurisdiction=derive_jurisdiction(assessment.patent_id),
            patent_id=assessment.patent_id,
            claim_number=assessment.claim_number,
            summary="Doctrine of equivalents assessment captured for this element.",
            record_basis=["doe_assessment"],
            linked_node_ids=[
                f"patent:{assessment.patent_id}",
                f"claim:{assessment.patent_id}:{assessment.claim_number}",
            ],
        )
        for assessment in doe_assessments
    ]


def build_invalidity_artifacts(
    invalidity_assessments: list[InvalidityAssessment],
) -> list[EvidenceArtifact]:
    """Build invalidity artifacts from recorded assessments."""
    return [
        EvidenceArtifact(
            artifact_id=f"{assessment.patent_id}:invalidity",
            artifact_type=EvidenceArtifactType.INVALIDITY_ASSESSMENT,
            source_name="step6_invalidity",
            authority_tier=EvidenceAuthorityTier.SUPPORTING,
            jurisdiction=derive_jurisdiction(assessment.patent_id),
            patent_id=assessment.patent_id,
            summary="Invalidity assessment captured for this patent.",
            record_basis=["invalidity_assessment"],
            linked_node_ids=[f"patent:{assessment.patent_id}"],
        )
        for assessment in invalidity_assessments
    ]


def build_critic_artifact() -> EvidenceArtifact:
    """Build the portfolio-level critic artifact."""
    return EvidenceArtifact(
        artifact_id="critic:portfolio",
        artifact_type=EvidenceArtifactType.CRITIC_REVIEW,
        source_name="step4b_critic",
        authority_tier=EvidenceAuthorityTier.SUPPORTING,
        summary="Portfolio-level critic review was completed for the matter.",
        record_basis=["critic_review"],
        linked_node_ids=[],
    )


def build_verification_artifact() -> EvidenceArtifact:
    """Build the final deterministic verification artifact."""
    return EvidenceArtifact(
        artifact_id="verification:final",
        artifact_type=EvidenceArtifactType.VERIFICATION,
        source_name="step7_verification",
        authority_tier=EvidenceAuthorityTier.SUPPORTING,
        summary="Deterministic verification results were recorded for the final matter.",
        record_basis=["verification"],
        linked_node_ids=[],
    )


def build_coverage_gap_artifacts(coverage_gaps) -> list[EvidenceArtifact]:
    """Build normalized coverage-gap artifacts."""
    return [
        EvidenceArtifact(
            artifact_id=f"coverage_gap:{index}",
            artifact_type=EvidenceArtifactType.COVERAGE_GAP,
            source_name="coverage_policy",
            authority_tier=EvidenceAuthorityTier.DISCOVERY,
            summary=gap.description,
            record_basis=[gap.gap_type],
            linked_node_ids=[],
        )
        for index, gap in enumerate(coverage_gaps, start=1)
    ]


def group_artifacts_by_source(
    evidence_artifacts: list[EvidenceArtifact],
) -> dict[str, list[EvidenceArtifact]]:
    """Group artifacts under each source name they declare."""
    artifacts_by_source: dict[str, list[EvidenceArtifact]] = defaultdict(list)
    for artifact in evidence_artifacts:
        for source_name in iter_artifact_source_names(artifact):
            artifacts_by_source[source_name].append(artifact)
    return artifacts_by_source


def build_adapter_result(
    *,
    source_name: str,
    artifacts: list[EvidenceArtifact],
    patent_records=None,
    authoritative_sources: set[str],
    supporting_sources: set[str],
    required_components: set[str],
    known_patent_ids: list[str] | None = None,
    status,
    entry_error_message: str = "",
) -> EvidenceAdapterResult:
    """Build a normalized adapter result for one source name."""
    definition = adapter_definition_for(source_name)
    authority_tier = authority_tier_for_adapter(
        source_name,
        authoritative_sources=authoritative_sources,
        supporting_sources=supporting_sources,
    )
    covered_components = derive_covered_components(artifacts)
    expected_components = list(definition.expected_components)
    if required_components:
        expected_components = [
            component for component in expected_components if component in required_components
        ]
    missing_components = [
        component for component in expected_components if component not in covered_components
    ]
    (
        collection_state,
        required_before_clear,
        target_patent_ids,
        covered_patent_ids,
        missing_patent_ids,
    ) = build_adapter_collection_ledger(
        source_name=source_name,
        patent_records=patent_records,
        expected_components=expected_components,
        required_components=required_components,
        artifacts=artifacts,
        known_patent_ids=list(known_patent_ids or []),
        status=status,
    )
    warnings: list[str] = []
    if status == SourceStatus.FAILED:
        warnings.append(entry_error_message or "source query failed")
    elif status == SourceStatus.NOT_CONFIGURED:
        warnings.append(entry_error_message or "source is not configured")
    if not artifacts and expected_components:
        warnings.append(
            "Required adapter was not queried or produced no artifacts for: "
            + ", ".join(expected_components)
            + "."
        )
    if missing_components:
        warnings.append(
            "Missing expected record components: " + ", ".join(missing_components) + "."
        )

    return EvidenceAdapterResult(
        adapter_name=source_name,
        adapter_kind=definition.adapter_kind,
        authority_tier=authority_tier,
        status=status,
        collection_state=collection_state,
        required_before_clear=required_before_clear,
        target_patent_ids=target_patent_ids,
        covered_patent_ids=covered_patent_ids,
        missing_patent_ids=missing_patent_ids,
        artifacts=artifacts,
        warnings=warnings,
        freshness_note=definition.freshness_note if artifacts else "",
        artifact_count=len(artifacts),
        covered_components=covered_components,
        expected_components=expected_components,
        missing_components=missing_components,
        supports_authoritative_findings=definition.supports_authoritative_findings,
    )


def build_coverage_gaps(*, report, coverage_context, record_completeness) -> list[CoverageGap]:
    """Build normalized coverage gaps for the final matter record."""
    gaps: list[CoverageGap] = []
    final_assessment = getattr(
        getattr(report, "search_loop_result", None),
        "final_assessment",
        None,
    )
    if final_assessment:
        gaps.extend(list(getattr(final_assessment, "gaps_identified", []) or []))

    for component in record_completeness.missing_components:
        gaps.append(
            CoverageGap(
                gap_type=f"missing_{component}",
                description=COMPONENT_DESCRIPTIONS.get(component, component),
                suggested_action=(
                    f"Collect and normalize {component} before issuing "
                    "a positive clearance conclusion."
                ),
            )
        )

    for source_name in coverage_context.coverage_summary.failed_source_names:
        gaps.append(
            CoverageGap(
                gap_type="source_failure",
                description=f"Evidence source '{source_name}' did not complete successfully.",
                suggested_action=f"Retry or replace source '{source_name}' before final clearance.",
            )
        )

    unique: dict[tuple[str, str], CoverageGap] = {}
    for gap in gaps:
        key = (gap.gap_type, gap.description)
        unique.setdefault(key, gap)
    return list(unique.values())


def build_evidence_artifacts(
    *,
    report,
    matter_evidence_index,
    claim_program_decisions,
    coverage_gaps,
) -> list[EvidenceArtifact]:
    """Build evidence artifacts from the current finalized matter record."""
    artifacts: list[EvidenceArtifact] = []
    claim_programs_by_patent: dict[str, list[ClaimProgramDecision]] = defaultdict(list)
    for decision in claim_program_decisions:
        claim_programs_by_patent[decision.patent_id].append(decision)

    for record in matter_evidence_index.patent_records:
        artifacts.extend(
            build_patent_record_artifacts(
                record,
                claim_programs_by_patent.get(record.patent_id, []),
            )
        )

    artifacts.extend(build_doe_artifacts(getattr(report, "doe_assessments", []) or []))
    artifacts.extend(
        build_invalidity_artifacts(getattr(report, "invalidity_assessments", []) or [])
    )
    if getattr(report, "critic_report", None):
        artifacts.append(build_critic_artifact())
    artifacts.append(build_verification_artifact())
    artifacts.extend(build_coverage_gap_artifacts(coverage_gaps))

    return artifacts


def build_evidence_adapter_results(
    *,
    report,
    matter_evidence_index,
    evidence_artifacts,
    record_completeness=None,
) -> list[EvidenceAdapterResult]:
    """Build standardized adapter results from current source and evidence state."""
    artifacts_by_source = group_artifacts_by_source(evidence_artifacts)

    results: list[EvidenceAdapterResult] = []
    authoritative_sources = set(matter_evidence_index.authoritative_source_names)
    supporting_sources = set(matter_evidence_index.supporting_source_names)
    patent_records = list(getattr(matter_evidence_index, "patent_records", []) or [])
    known_patent_ids = unique_strings(
        [record.patent_id for record in patent_records]
        + [
            artifact.patent_id
            for artifact in evidence_artifacts
            if getattr(artifact, "patent_id", "")
        ]
    )
    required_components = set(getattr(record_completeness, "required_components", []) or [])

    for entry in getattr(report.source_health, "entries", []) or []:
        source_name = entry.source
        status = adapter_status_for_entry(entry)
        results.append(
            build_adapter_result(
                source_name=source_name,
                artifacts=artifacts_by_source.get(source_name, []),
                patent_records=patent_records,
                authoritative_sources=authoritative_sources,
                supporting_sources=supporting_sources,
                required_components=required_components,
                known_patent_ids=known_patent_ids,
                status=status,
                entry_error_message=entry.error_message or "",
            )
        )

    known_sources = {result.adapter_name for result in results}
    policy_sources = set(iter_policy_adapter_names(required_components))
    for source_name in sorted((set(artifacts_by_source) | policy_sources) - known_sources):
        artifacts = artifacts_by_source.get(source_name, [])
        status = (
            SourceStatus.OK
            if artifacts
            else SourceStatus.NOT_CONFIGURED
            if source_name in policy_sources
            else SourceStatus.SKIPPED
        )
        results.append(
            build_adapter_result(
                source_name=source_name,
                artifacts=artifacts,
                patent_records=patent_records,
                authoritative_sources=authoritative_sources,
                supporting_sources=supporting_sources,
                required_components=required_components,
                known_patent_ids=known_patent_ids,
                status=status,
            )
        )

    return results
