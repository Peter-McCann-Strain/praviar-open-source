"""Policy builders for the evidence-fabric runtime substrate."""

from __future__ import annotations

from praviar_pipeline.models.report import AuthorityCoverage, RecordCompleteness
from praviar_pipeline.pipeline.report.evidence_index_shared import unique_strings
from praviar_pipeline.pipeline.runtime.decisioning_metrics import (
    CLEARANCE_CRITIC_MIN_QUALITY,
    _has_clearance_blocking_critic_findings,
)

DEFAULT_REQUIRED_RECORD_COMPONENTS_BY_PROFILE = {
    "world_class_us_ep": [
        "claims_text",
        "claim_level_analysis",
        "authoritative_records",
        "family_context",
        "us_file_wrapper_dossier",
        "ep_register_context",
        "verification",
    ],
    "screening": [
        "claims_text",
        "claim_level_analysis",
        "authoritative_records",
        "family_context",
        "verification",
    ],
}

COMPONENT_TO_CATEGORY = {
    "authoritative_records": "authoritative_search_source",
    "family_context": "family_record",
    "us_prosecution_context": "us_prosecution_record",
    "us_file_wrapper_dossier": "us_file_wrapper_dossier",
    "ep_register_context": "ep_register_record",
    "ptab_record": "ptab_record",
    "orange_book_record": "orange_book_record",
}

COMPONENT_DESCRIPTIONS = {
    "claims_text": "Full claims text is required for a clearance-grade record.",
    "claim_level_analysis": "Claim-level analysis is required for a clearance-grade record.",
    "authoritative_records": (
        "Authoritative legal-record support is required for a clearance-grade record."
    ),
    "family_context": "Patent-family context is required for a clearance-grade record.",
    "us_prosecution_context": (
        "U.S. prosecution context is required for a clearance-grade record."
    ),
    "us_file_wrapper_dossier": (
        "A dossier-grade U.S. file wrapper is required for a clearance-grade record."
    ),
    "ep_register_context": (
        "EP register and opposition context is required for a clearance-grade record."
    ),
    "verification": "Deterministic verification must pass before a matter can be cleared.",
}


def resolve_required_record_components(settings, coverage_context) -> list[str]:
    """Resolve the required record components for the current matter policy."""
    configured = list(getattr(settings, "required_record_components", []) or [])
    if configured:
        required = configured
    else:
        profile = str(
            getattr(settings, "clearance_threshold_profile", "world_class_us_ep")
            or "world_class_us_ep"
        )
        required = DEFAULT_REQUIRED_RECORD_COMPONENTS_BY_PROFILE.get(
            profile,
            DEFAULT_REQUIRED_RECORD_COMPONENTS_BY_PROFILE["world_class_us_ep"],
        )

    if coverage_context.us_patents == 0:
        required = [component for component in required if not component.startswith("us_")]
    if coverage_context.ep_patents == 0:
        required = [component for component in required if not component.startswith("ep_")]

    return unique_strings(required)


def build_record_completeness(
    *,
    report,
    coverage_context,
    settings,
    reviewed_patent_ids: set[str] | None = None,
    jurisdictions: list[str] | None = None,
) -> RecordCompleteness:
    """Build record-completeness policy evaluation from current coverage state."""
    required_components = resolve_required_record_components(settings, coverage_context)
    jurisdiction_set = set(jurisdictions or [])
    if jurisdiction_set:
        if "US" not in jurisdiction_set:
            required_components = [
                component for component in required_components if not component.startswith("us_")
            ]
        if "EP" not in jurisdiction_set:
            required_components = [
                component for component in required_components if not component.startswith("ep_")
            ]
    summary = coverage_context.coverage_summary
    reviewed_set = reviewed_patent_ids

    def _has_scoped(values: list[str]) -> bool:
        if reviewed_set is None:
            return bool(values)
        return any(value in reviewed_set for value in values)

    missing_components: list[str] = []
    if "claims_text" in required_components and _has_scoped(summary.patents_missing_claims):
        missing_components.append("claims_text")
    if "claim_level_analysis" in required_components and _has_scoped(
        summary.patents_missing_claim_level_analysis
    ):
        missing_components.append("claim_level_analysis")
    if "authoritative_records" in required_components and _has_scoped(
        summary.patents_missing_authoritative_records
    ):
        missing_components.append("authoritative_records")
    if "family_context" in required_components and _has_scoped(
        summary.patents_missing_family_context
    ):
        missing_components.append("family_context")
    if "us_prosecution_context" in required_components and _has_scoped(
        summary.us_patents_missing_prosecution_context
    ):
        missing_components.append("us_prosecution_context")
    if "us_file_wrapper_dossier" in required_components and _has_scoped(
        summary.us_patents_missing_file_wrapper_dossier
    ):
        missing_components.append("us_file_wrapper_dossier")
    if "ep_register_context" in required_components and _has_scoped(
        summary.ep_patents_missing_register_context
    ):
        missing_components.append("ep_register_context")
    if "verification" in required_components and summary.verification_gaps:
        missing_components.append("verification")

    blocking_gaps = [
        COMPONENT_DESCRIPTIONS[component]
        for component in missing_components
        if component in COMPONENT_DESCRIPTIONS
    ]
    if any(
        reviewed_set is None or failure.patent_id in reviewed_set
        for failure in report.analysis_failures
    ):
        blocking_gaps.append("Patent analyses failed before the matter decision was finalized.")
    if report.data_limitations:
        blocking_gaps.append("Documented data limitations remain on the final matter record.")
    critic_report = getattr(report, "critic_report", None)
    if (
        reviewed_set is None
        and critic_report
        and getattr(critic_report, "overall_quality_score", 0.0) < CLEARANCE_CRITIC_MIN_QUALITY
    ):
        blocking_gaps.append("Critic review quality remained below clearance grade.")
    if _has_clearance_blocking_critic_findings(critic_report, reviewed_set):
        blocking_gaps.append("Critic review surfaced major or critical unresolved issues.")

    evaluated_jurisdictions = jurisdictions or [
        jurisdiction
        for jurisdiction, patent_ids in coverage_context.jurisdiction_patents.items()
        if patent_ids
    ]
    return RecordCompleteness(
        profile=str(
            getattr(settings, "clearance_threshold_profile", "world_class_us_ep")
            or "world_class_us_ep"
        ),
        matter_type=str(getattr(settings, "matter_type", "small_molecule") or "small_molecule"),
        jurisdictions=sorted(evaluated_jurisdictions),
        required_components=required_components,
        missing_components=missing_components,
        blocking_gaps=unique_strings(blocking_gaps),
        clearance_grade_ready=not missing_components and not blocking_gaps,
    )


def build_authority_coverage(
    *,
    matter_evidence_index,
    record_completeness,
    settings,
) -> AuthorityCoverage:
    """Summarize authority-tier coverage for the final matter record."""
    covered_categories = unique_strings(
        [
            category
            for record in matter_evidence_index.patent_records
            for category in record.authoritative_record_categories
        ]
    )
    required_categories = unique_strings(
        [
            COMPONENT_TO_CATEGORY[component]
            for component in record_completeness.required_components
            if component in COMPONENT_TO_CATEGORY
        ]
    )
    missing_categories = [
        category for category in required_categories if category not in covered_categories
    ]
    patents_with_authoritative_records = sum(
        1
        for record in matter_evidence_index.patent_records
        if record.authoritative_record_categories
    )

    return AuthorityCoverage(
        policy=str(
            getattr(settings, "source_authority_policy", "official_plus_licensed")
            or "official_plus_licensed"
        ),
        authoritative_source_names=list(matter_evidence_index.authoritative_source_names),
        supporting_source_names=list(matter_evidence_index.supporting_source_names),
        authoritative_categories_covered=covered_categories,
        authoritative_categories_missing=missing_categories,
        patents_with_authoritative_records=patents_with_authoritative_records,
        patents_without_authoritative_records=max(
            0,
            matter_evidence_index.material_patent_count - patents_with_authoritative_records,
        ),
        clearance_grade_ready_patents=len(matter_evidence_index.clearance_grade_ready_patent_ids),
    )
