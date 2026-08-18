"""Metrics, gate evaluation and certification-scope helpers for clearance decisioning.

This module consolidates the pure metrics and reasoning helpers, the explicit
clearance-grade gate evaluation, and the certification-scope contract builder
used by deterministic top-line clearance decisioning.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from praviar_pipeline.certification_receipt import verify_certification_receipt
from praviar_pipeline.models.report import (
    CertificationScope,
    ClearanceOutcome,
    CohortStatus,
    DecisionScope,
)
from praviar_pipeline.utils.patent_ids import publication_jurisdiction

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis import RiskLevel


CLEARANCE_CRITIC_MIN_QUALITY = 0.95


def derive_jurisdiction(patent_id: str, detail: dict | None = None) -> str:
    derived = publication_jurisdiction(patent_id)
    if detail:
        jurisdiction = str(detail.get("jurisdiction", "")).upper()
        if jurisdiction and jurisdiction != derived:
            raise ValueError("patent detail jurisdiction contradicts publication identifier")
    return derived


def coverage_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0
    return max(0.0, min(1.0, numerator / denominator))


def score_evidence_quality(
    *,
    source_ok_ratio: float,
    claims_ratio: float,
    family_ratio: float,
    us_prosecution_ratio: float,
    ep_register_ratio: float,
) -> float:
    return round(
        min(
            1.0,
            (source_ok_ratio * 0.35)
            + (claims_ratio * 0.25)
            + (family_ratio * 0.15)
            + (us_prosecution_ratio * 0.15)
            + (ep_register_ratio * 0.10),
        ),
        2,
    )


def build_evidence_warnings(
    *,
    report,
    required_record_components: list[str],
    queried_sources: int,
    successful_sources: int,
    material_patent_count: int,
    claims_ratio: float,
    patents_missing_claim_level_analysis: int,
    patents_missing_authoritative_records: int,
    us_patents: int,
    us_patents_with_prosecution_context: int,
    us_patents_with_file_wrapper_dossier: int,
    ep_patents: int,
    ep_patents_with_register_context: int,
    reviewed_patent_ids: set[str] | None = None,
) -> list[str]:
    warnings: list[str] = []
    required = set(required_record_components or [])
    analysis_failures = [
        failure
        for failure in report.analysis_failures
        if reviewed_patent_ids is None or failure.patent_id in reviewed_patent_ids
    ]

    if analysis_failures:
        warnings.append(
            f"{len(analysis_failures)} patent analyses failed and were "
            "excluded from final reasoning."
        )
    if report.source_health.failed_sources:
        warnings.append(
            "Search sources failed during collection: "
            f"{', '.join(report.source_health.failed_sources)}."
        )
    if queried_sources == 0:
        warnings.append("No search sources were recorded for the final matter.")
    elif successful_sources == 0:
        warnings.append(
            "No search source succeeded, so the matter cannot be cleared on the available record."
        )
    if material_patent_count == 0:
        warnings.append("No material patents were reviewed; that is not sufficient for clearance.")
    elif us_patents == 0 and ep_patents == 0:
        warnings.append(
            "No material US or EP patents were reviewed, so core-jurisdiction "
            "clearance is not established."
        )
    if "claims_text" in required and claims_ratio < 1.0 and report.patent_analyses:
        warnings.append(
            "Not every analyzed patent had full claims text attached to the final matter record."
        )
    if "claim_level_analysis" in required and patents_missing_claim_level_analysis:
        warnings.append(
            "Some analyzed patents lack claim-level analysis in the final matter record."
        )
    if "authoritative_records" in required and patents_missing_authoritative_records:
        warnings.append(
            "Some analyzed patents still lack authoritative record support beyond discovery search."
        )
    if (
        "us_prosecution_context" in required
        and us_patents
        and us_patents_with_prosecution_context < us_patents
    ):
        warnings.append("Some analyzed US patents lack full prosecution/file-wrapper context.")
    if (
        "us_file_wrapper_dossier" in required
        and us_patents
        and us_patents_with_file_wrapper_dossier < us_patents
    ):
        warnings.append("Some analyzed US patents still lack dossier-grade file-wrapper coverage.")
    if (
        "ep_register_context" in required
        and ep_patents
        and ep_patents_with_register_context < ep_patents
    ):
        warnings.append("Some analyzed EP patents lack complete register/opposition context.")

    warnings.extend(limitation.description for limitation in report.data_limitations[:5])
    return warnings


def build_decision_reasoning(
    *,
    overall_risk: RiskLevel,
    decision: ClearanceOutcome,
    evidence_quality: float,
    evidence_sufficient: bool,
    material_patent_count: int,
    blocking_patent_ids: list[str],
    blocking_claim_ids: list[str],
    contested_claim_ids: list[str],
    medium_risk_claim_ids: list[str],
    inactive_coverage_claim_ids: list[str],
    insufficiency_reasons: list[str],
    warnings: list[str],
) -> list[str]:
    reasoning = [
        (
            f"Upstream claim-coverage risk screen is {overall_risk.value}; the final "
            "clearance outcome separately applies trusted status, accused-act, temporal, "
            "family, invalidity, and evidence-sufficiency gates."
        ),
        f"Material patents reviewed: {material_patent_count}.",
        f"Evidence quality score: {evidence_quality:.2f}.",
    ]

    if blocking_patent_ids:
        reasoning.append(
            f"Blocking exposure remains on {len(blocking_patent_ids)} patent(s): "
            f"{', '.join(blocking_patent_ids[:5])}."
        )
        if insufficiency_reasons and any(
            "conflicts with authoritative legal status" in reason.lower()
            or "conflicts with ep register status" in reason.lower()
            for reason in insufficiency_reasons
        ):
            reasoning.append(
                "Authoritative status records conflict with the apparent blocking exposure, "
                "so the matter remains unclear rather than blocked."
            )
        if blocking_claim_ids:
            reasoning.append(
                "Claim-program review identified unmitigated blocking claim exposure on "
                f"{', '.join(blocking_claim_ids[:5])}."
            )
    elif decision == ClearanceOutcome.CLEAR:
        reasoning.append(
            "No material blocking exposure remained after literal infringement, "
            "DoE, invalidity, and evidence sufficiency checks."
        )
        if inactive_coverage_claim_ids:
            reasoning.append(
                "Positive coverage screens were retained, but trusted inactive status "
                "resolved prospective exposure for "
                f"{', '.join(inactive_coverage_claim_ids[:5])}; no past-act or live-family "
                "issue remained in scope."
            )
    elif not evidence_sufficient:
        reasoning.append(
            "The matter lacks enough reviewed evidence to support a positive clearance conclusion."
        )
        if insufficiency_reasons:
            reasoning.append(f"Primary clearance gate failure: {insufficiency_reasons[0]}")
    else:
        reasoning.append(
            "The matter could not be cleared conservatively because material "
            "evidence remains incomplete, mixed, or only low-confidence."
        )
        if contested_claim_ids:
            reasoning.append(
                "Some high-risk claim programs remain contested by strong invalidity positions, "
                "so the matter stays unclear rather than blocked."
            )
        elif medium_risk_claim_ids:
            reasoning.append(
                "Some claim programs still show medium risk under literal or DoE review."
            )

    if warnings:
        reasoning.append(f"Key evidence caveat: {warnings[0]}")

    return reasoning


def _pluralized(count: int, singular: str, plural: str | None = None) -> str:
    if count == 1:
        return singular
    return plural or f"{singular}s"


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result


def _has_clearance_blocking_critic_findings(
    critic_report, patent_ids: set[str] | None = None
) -> bool:
    if not critic_report:
        return False

    for finding in getattr(critic_report, "findings", []) or []:
        severity = getattr(
            getattr(finding, "severity", None), "value", getattr(finding, "severity", "")
        )
        if severity not in {"critical", "major"}:
            continue
        if patent_ids is not None and getattr(finding, "patent_id", "") not in patent_ids:
            continue
        return True

    return False


def build_clearance_gate_failures(
    *,
    report,
    coverage_context,
    reviewed_patent_ids: set[str] | None = None,
) -> list[str]:
    """Return reasons why the final matter record is not clearance-grade."""
    failures: list[str] = []
    coverage_summary = coverage_context.coverage_summary
    required_components = set(getattr(coverage_context, "required_record_components", []) or [])
    reviewed_set = reviewed_patent_ids

    def _scoped(values: list[str]) -> list[str]:
        if reviewed_set is None:
            return list(values)
        return [value for value in values if value in reviewed_set]

    scoped_reviewed_patent_ids = (
        list(coverage_summary.reviewed_patent_ids)
        if reviewed_set is None
        else _scoped(coverage_summary.reviewed_patent_ids)
    )
    scoped_us_patent_ids = _scoped(coverage_summary.reviewed_us_patent_ids)
    scoped_ep_patent_ids = _scoped(coverage_summary.reviewed_ep_patent_ids)

    if coverage_context.queried_sources == 0:
        failures.append("No search sources were recorded for the final matter.")
    elif coverage_context.ok_sources == 0:
        failures.append(
            "No search source succeeded, so the matter cannot be cleared on the available record."
        )

    if not scoped_reviewed_patent_ids:
        failures.append("No material patents were reviewed; that is not sufficient for clearance.")
    elif not scoped_us_patent_ids and not scoped_ep_patent_ids:
        failures.append(
            "No material US or EP patents were reviewed, so core-jurisdiction clearance "
            "is not established."
        )

    missing_claims = _scoped(coverage_summary.patents_missing_claims)
    if "claims_text" in required_components and missing_claims:
        count = len(missing_claims)
        failures.append(
            f"{count} analyzed {_pluralized(count, 'patent')} reached the final matter "
            "record without full claims text."
        )
    if "claim_level_analysis" in required_components and (
        missing_claim_analysis := _scoped(coverage_summary.patents_missing_claim_level_analysis)
    ):
        count = len(missing_claim_analysis)
        failures.append(
            f"{count} analyzed {_pluralized(count, 'patent')} lack claim-level analysis "
            "in the final matter record."
        )
    if "authoritative_records" in required_components and (
        missing_authoritative := _scoped(coverage_summary.patents_missing_authoritative_records)
    ):
        count = len(missing_authoritative)
        failures.append(
            f"{count} analyzed {_pluralized(count, 'patent')} lack authoritative record "
            "support beyond discovery search."
        )
    missing_family = _scoped(coverage_summary.patents_missing_family_context)
    if "family_context" in required_components and missing_family:
        count = len(missing_family)
        failures.append(
            f"{count} analyzed {_pluralized(count, 'patent')} lack complete family context."
        )
    if "us_prosecution_context" in required_components and (
        missing_us_prosecution := _scoped(coverage_summary.us_patents_missing_prosecution_context)
    ):
        count = len(missing_us_prosecution)
        failures.append(
            f"{count} analyzed US {_pluralized(count, 'patent')} lack full "
            "prosecution/file-wrapper context."
        )
    if "us_file_wrapper_dossier" in required_components and (
        missing_us_dossier := _scoped(coverage_summary.us_patents_missing_file_wrapper_dossier)
    ):
        count = len(missing_us_dossier)
        failures.append(
            f"{count} analyzed US {_pluralized(count, 'patent')} lack dossier-grade "
            "file-wrapper coverage."
        )
    if "ep_register_context" in required_components and (
        missing_ep_register := _scoped(coverage_summary.ep_patents_missing_register_context)
    ):
        count = len(missing_ep_register)
        failures.append(
            f"{count} analyzed EP {_pluralized(count, 'patent')} lack complete "
            "register/opposition context."
        )
    analysis_failures = [
        failure
        for failure in report.analysis_failures
        if reviewed_set is None or failure.patent_id in reviewed_set
    ]
    if analysis_failures:
        count = len(analysis_failures)
        failures.append(
            f"{count} patent {_pluralized(count, 'analysis', 'analyses')} failed "
            "before the matter decision was finalized."
        )
    if "verification" in required_components and coverage_summary.verification_gaps:
        failures.append("Deterministic verification did not fully pass for the final matter.")
    if report.data_limitations:
        count = len(report.data_limitations)
        failures.append(
            f"{count} documented data {_pluralized(count, 'limitation')} remain on "
            "the final matter record."
        )
    critic_report = getattr(report, "critic_report", None)
    if (
        reviewed_set is None
        and critic_report
        and getattr(critic_report, "overall_quality_score", 0.0) < CLEARANCE_CRITIC_MIN_QUALITY
    ):
        failures.append("Critic review quality score remained below clearance grade.")
    if _has_clearance_blocking_critic_findings(critic_report, reviewed_set):
        failures.append(
            "Critic review surfaced major or critical analysis issues that prevent a "
            "positive clearance conclusion."
        )

    return _unique(failures)


def build_jurisdiction_gate_failures(
    *,
    jurisdiction: str,
    reviewed_patent_ids: list[str],
    coverage_summary,
    report,
) -> list[str]:
    """Return reasons why a jurisdiction-specific record is not clearance-grade."""
    failures: list[str] = []
    reviewed_set = set(reviewed_patent_ids)
    required_components = set(getattr(coverage_summary, "required_record_components", []) or [])

    if not reviewed_patent_ids:
        failures.append(f"No analyzed patents were mapped directly to {jurisdiction}.")
        return failures

    missing_claims = [
        patent_id
        for patent_id in coverage_summary.patents_missing_claims
        if patent_id in reviewed_set
    ]
    if "claims_text" in required_components and missing_claims:
        count = len(missing_claims)
        failures.append(
            f"{count} analyzed {jurisdiction} {_pluralized(count, 'patent')} lack full claims text."
        )
    missing_claim_level_analysis = [
        patent_id
        for patent_id in coverage_summary.patents_missing_claim_level_analysis
        if patent_id in reviewed_set
    ]
    if "claim_level_analysis" in required_components and missing_claim_level_analysis:
        count = len(missing_claim_level_analysis)
        failures.append(
            f"{count} analyzed {jurisdiction} {_pluralized(count, 'patent')} lack "
            "claim-level analysis."
        )
    missing_authoritative_records = [
        patent_id
        for patent_id in coverage_summary.patents_missing_authoritative_records
        if patent_id in reviewed_set
    ]
    if "authoritative_records" in required_components and missing_authoritative_records:
        count = len(missing_authoritative_records)
        failures.append(
            f"{count} analyzed {jurisdiction} {_pluralized(count, 'patent')} lack "
            "authoritative record support."
        )

    missing_family = [
        patent_id
        for patent_id in coverage_summary.patents_missing_family_context
        if patent_id in reviewed_set
    ]
    if "family_context" in required_components and missing_family:
        count = len(missing_family)
        failures.append(
            f"{count} analyzed {jurisdiction} {_pluralized(count, 'patent')} lack "
            "complete family context."
        )

    if jurisdiction == "US":
        missing_prosecution = [
            patent_id
            for patent_id in coverage_summary.us_patents_missing_prosecution_context
            if patent_id in reviewed_set
        ]
        if "us_prosecution_context" in required_components and missing_prosecution:
            count = len(missing_prosecution)
            failures.append(
                f"{count} analyzed US {_pluralized(count, 'patent')} lack full "
                "prosecution/file-wrapper context."
            )
        missing_file_wrapper_dossier = [
            patent_id
            for patent_id in coverage_summary.us_patents_missing_file_wrapper_dossier
            if patent_id in reviewed_set
        ]
        if "us_file_wrapper_dossier" in required_components and missing_file_wrapper_dossier:
            count = len(missing_file_wrapper_dossier)
            failures.append(
                f"{count} analyzed US {_pluralized(count, 'patent')} lack dossier-grade "
                "file-wrapper coverage."
            )

    if jurisdiction == "EP":
        missing_register = [
            patent_id
            for patent_id in coverage_summary.ep_patents_missing_register_context
            if patent_id in reviewed_set
        ]
        if "ep_register_context" in required_components and missing_register:
            count = len(missing_register)
            failures.append(
                f"{count} analyzed EP {_pluralized(count, 'patent')} lack complete "
                "register/opposition context."
            )

    if any(failure.patent_id in reviewed_set for failure in report.analysis_failures):
        failures.append(
            "At least one patent analysis failed before the matter decision was finalized."
        )
    if "verification" in required_components and coverage_summary.verification_gaps:
        failures.append("Deterministic verification did not fully pass for the final matter.")
    if report.data_limitations:
        failures.append("Documented data limitations remain on the final matter record.")
    critic_report = getattr(report, "critic_report", None)
    if (
        critic_report
        and getattr(critic_report, "overall_quality_score", 0.0) < CLEARANCE_CRITIC_MIN_QUALITY
    ):
        failures.append("Critic review quality score remained below clearance grade.")
    if _has_clearance_blocking_critic_findings(critic_report, reviewed_set):
        failures.append(f"Critic review surfaced major or critical {jurisdiction} analysis issues.")

    return _unique(failures)


_JURISDICTION_SORT_ORDER = {"US": 0, "EP": 1}
_MATTER_TYPE_ASSET_CLASSES = {
    "small_molecule": ["compound"],
    "formulation": ["formulation"],
    "process": ["process"],
    "biologic": ["biologic"],
}


def _normalize_matter_type(raw_value: object) -> str:
    value = str(raw_value or "").strip().lower()
    return value or "unclassified"


def _format_matter_type_label(matter_type: str) -> str:
    return matter_type.replace("_", " ")


def _asset_classes_for_matter_type(matter_type: str) -> list[str]:
    return list(_MATTER_TYPE_ASSET_CLASSES.get(matter_type, [matter_type]))


def _sort_jurisdictions(jurisdictions: list[str]) -> list[str]:
    return sorted(
        (jurisdiction for jurisdiction in jurisdictions if jurisdiction),
        key=lambda jurisdiction: (
            _JURISDICTION_SORT_ORDER.get(jurisdiction, 99),
            jurisdiction,
        ),
    )


def _required_record_components_sha256(settings, coverage_context) -> str:
    values = (
        getattr(settings, "required_record_components", None)
        or getattr(coverage_context, "required_record_components", None)
        or []
    )
    normalized = sorted({str(value or "").strip() for value in values if str(value or "").strip()})
    return hashlib.sha256(
        json.dumps(normalized, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def build_scope_contract(
    report, coverage_context, settings=None
) -> tuple[
    DecisionScope,
    DecisionScope,
    CertificationScope,
    CohortStatus,
    str,
]:
    """Derive the matter's certified decision scope and cohort status."""

    configured_matter_type = _normalize_matter_type(getattr(settings, "matter_type", ""))
    report_matter_type = _normalize_matter_type(getattr(report.compound, "compound_type", ""))
    classified_values = {
        value for value in (configured_matter_type, report_matter_type) if value != "unclassified"
    }
    matter_type = (
        "classification_conflict"
        if len(classified_values) > 1
        else next(iter(classified_values), "unclassified")
    )
    asset_classes = _asset_classes_for_matter_type(matter_type)
    receipt = verify_certification_receipt(settings)
    certified_policy = receipt.policy
    certified_matter_types = (
        list(certified_policy.certified_matter_types) if certified_policy else []
    )
    certified_jurisdictions = (
        list(certified_policy.certified_decision_jurisdictions) if certified_policy else []
    )
    certified_asset_classes = (
        list(certified_policy.certified_asset_classes) if certified_policy else []
    )
    record_components_sha256 = _required_record_components_sha256(settings, coverage_context)
    matching_lanes = [
        lane
        for lane in receipt.certified_lanes
        if lane.matter_type == matter_type
        and lane.asset_class in asset_classes
        and lane.execution_profile == "adaptive"
        and lane.required_record_components_sha256 == record_components_sha256
    ]
    reviewed_jurisdictions = _sort_jurisdictions(
        [
            jurisdiction
            for jurisdiction, patent_ids in coverage_context.jurisdiction_patents.items()
            if patent_ids
        ]
    )
    configured_target_jurisdictions = _sort_jurisdictions(
        list(
            dict.fromkeys(
                str(jurisdiction).strip().upper()
                for jurisdiction in getattr(settings, "target_jurisdictions", []) or []
                if str(jurisdiction).strip()
            )
        )
    )
    requested_decision_jurisdictions = configured_target_jurisdictions or reviewed_jurisdictions
    current_matter_type_certified = receipt.verified and bool(matching_lanes)
    matching_lane_jurisdictions = {lane.jurisdiction for lane in matching_lanes}
    decision_jurisdictions = (
        [
            jurisdiction
            for jurisdiction in requested_decision_jurisdictions
            if jurisdiction in matching_lane_jurisdictions
        ]
        if current_matter_type_certified
        else []
    )
    uncertified_target_jurisdictions = [
        jurisdiction
        for jurisdiction in configured_target_jurisdictions
        if jurisdiction not in matching_lane_jurisdictions
    ]
    supporting_jurisdictions = _sort_jurisdictions(
        list(
            dict.fromkeys(
                [
                    jurisdiction
                    for jurisdiction in reviewed_jurisdictions
                    if jurisdiction not in decision_jurisdictions
                ]
                + uncertified_target_jurisdictions
            )
        )
    )

    if matter_type in {"unclassified", "classification_conflict"}:
        cohort_status = CohortStatus.ATTORNEY_SUPERVISED
        cohort_gate_reason = (
            "Matter classification is missing or conflicts with configured scope; "
            "attorney supervision is required."
        )
    elif not receipt.verified:
        cohort_status = CohortStatus.ATTORNEY_SUPERVISED
        cohort_gate_reason = (
            "No verified release-certification receipt is bound to this pipeline build; "
            "attorney supervision is required."
        )
    elif (
        current_matter_type_certified
        and decision_jurisdictions
        and not uncertified_target_jurisdictions
    ):
        cohort_status = CohortStatus.CERTIFIED
        cohort_gate_reason = ""
    elif current_matter_type_certified:
        cohort_status = CohortStatus.SUPPORTING_ONLY
        if uncertified_target_jurisdictions:
            cohort_gate_reason = (
                "Target jurisdiction(s) "
                f"{', '.join(uncertified_target_jurisdictions)} are outside the certified "
                "decision scope; supporting evidence can raise blocked or unclear outcomes "
                "but cannot justify a positive clearance conclusion."
            )
        else:
            cohort_gate_reason = (
                "No certified decision-scope jurisdiction was selected or reviewed; "
                "supporting-scope evidence can raise blocked or unclear outcomes but "
                "cannot justify a positive clearance conclusion."
            )
    else:
        cohort_status = CohortStatus.ATTORNEY_SUPERVISED
        cohort_gate_reason = (
            f"The {_format_matter_type_label(matter_type)} cohort is not yet certified "
            "for direct positive clearance conclusions; attorney supervision is required."
        )

    if decision_jurisdictions:
        decision_summary = (
            f"{', '.join(decision_jurisdictions)} is within the selected certified "
            "decision scope for this matter and may support a positive clearance "
            "conclusion only when its authoritative record is complete."
        )
    elif current_matter_type_certified:
        decision_summary = (
            "This matter type is within the certified program, but no certified "
            "decision-scope jurisdiction has been reviewed yet."
        )
    else:
        decision_summary = (
            f"{_format_matter_type_label(matter_type).capitalize()} matters are outside "
            "the current certified direct-clearance cohorts."
        )

    if supporting_jurisdictions:
        supporting_summary = (
            f"{', '.join(supporting_jurisdictions)} remains supporting scope only. "
            "Its findings remain visible in the jurisdiction record but cannot change "
            "the selected target-jurisdiction conclusion."
        )
    elif current_matter_type_certified and decision_jurisdictions:
        supporting_summary = "No supporting-only jurisdictions were material in this matter."
    else:
        supporting_summary = (
            "All reviewed jurisdictions remain attorney-supervised supporting scope "
            "for this matter."
        )

    if not receipt.verified:
        certification_summary = (
            "Direct positive clearance is disabled because this runtime has no valid, "
            "unexpired release-certification receipt for its exact source revision."
        )
    elif current_matter_type_certified:
        certification_summary = (
            f"Release receipt {receipt.receipt_id} certifies this matter type for "
            f"{', '.join(certified_jurisdictions)} decision scope. "
        )
        certification_summary += (
            "This matter type is in the certified cohort, but only reviewed decision-scope "
            "jurisdictions may support clear."
        )
    else:
        certification_summary = (
            f"Release receipt {receipt.receipt_id} does not certify this "
            f"{_format_matter_type_label(matter_type)} matter. It remains "
            "attorney-supervised until that cohort is separately validated."
        )

    decision_scope = DecisionScope(
        matter_type=matter_type,
        jurisdictions=decision_jurisdictions,
        asset_classes=asset_classes,
        intended_actions=list(
            dict.fromkeys(
                str(action).strip().lower()
                for action in getattr(settings, "intended_actions", []) or []
                if str(action).strip()
            )
        ),
        supports_positive_clearance=bool(
            decision_jurisdictions and not uncertified_target_jurisdictions
        ),
        summary=decision_summary,
    )
    supporting_scope = DecisionScope(
        matter_type=matter_type,
        jurisdictions=supporting_jurisdictions,
        asset_classes=asset_classes,
        intended_actions=list(
            dict.fromkeys(
                str(action).strip().lower()
                for action in getattr(settings, "intended_actions", []) or []
                if str(action).strip()
            )
        ),
        supports_positive_clearance=False,
        summary=supporting_summary,
    )
    certification_scope = CertificationScope(
        certified_jurisdictions=certified_jurisdictions,
        supported_jurisdictions=(
            list(certified_policy.supported_jurisdictions) if certified_policy else []
        ),
        certified_matter_types=certified_matter_types,
        certified_asset_classes=certified_asset_classes,
        attorney_supervised_matter_types=([] if current_matter_type_certified else [matter_type]),
        attorney_supervised_asset_classes=([] if current_matter_type_certified else asset_classes),
        supporting_only_jurisdictions=supporting_jurisdictions,
        current_matter_type_certified=current_matter_type_certified,
        attorney_supervision_required=cohort_status != CohortStatus.CERTIFIED,
        evidence_verified=receipt.verified,
        evidence_verification_status=("valid" if receipt.verified else "unverified"),
        evidence_receipt_dsse=(
            str(getattr(settings, "certification_release_receipt_json", "") or "")
            if receipt.verified
            else ""
        ),
        evidence_receipt_id=receipt.receipt_id,
        evidence_receipt_sha256=receipt.receipt_sha256,
        evidence_pipeline_git_sha=receipt.pipeline_git_sha,
        evidence_source_tree_sha256=receipt.source_tree_sha256,
        evidence_expires_at=receipt.expires_at,
        evidence_issuer_verifier_id=receipt.issuer_verifier_id,
        evidence_key_id=receipt.key_id,
        evidence_gate_run_id=receipt.gate_run_id,
        evidence_benchmark_aggregate_sha256=receipt.benchmark_aggregate_sha256,
        verified_lane_ids=[lane.lane_id for lane in matching_lanes],
        evidence_failures=list(receipt.failures),
        summary=certification_summary,
    )
    return (
        decision_scope,
        supporting_scope,
        certification_scope,
        cohort_status,
        cohort_gate_reason,
    )
