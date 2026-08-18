"""Shared access checks for report-derived surfaces."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypeVar, cast

from praviar_pipeline.certification_receipt import verify_certification_receipt
from praviar_pipeline.models.patent import ClaimTextProvenance, PatentSource
from praviar_pipeline.models.report import ClaimProgramDecision
from praviar_pipeline.models.report_source_spans import (
    ClaimAssertionSupport,
    ClaimSourceSpanMap,
    SourceSpanReference,
    verify_source_span_attestation,
)
from praviar_pipeline.pipeline.runtime.evidence_policy import COMPONENT_TO_CATEGORY
from praviar_pipeline.report_certification_binding import (
    ReportCertificationVerificationKeyRing,
    verify_report_certification_binding,
)
from praviar_pipeline.utils.patent_ids import (
    canonical_publication_id,
    publication_jurisdiction,
)
from pydantic import ValidationError

from api.config import get_settings
from api.db.models import AnalysisStatus
from api.errors import APIError
from api.schemas.reports_core import RiskSummaryResponse
from api.schemas.reports_tracking_evidence import (
    MatterEvidenceIndexResponse,
    MatterStoreResponse,
    RecordCompletenessResponse,
)
from api.services.risk_access import RISK_RESTRICTION_SUMMARY

SUPPORT_STATUSES = {"supported", "unsupported", "needs_review"}
RISK_LEVELS = {"high", "medium", "low", "clear"}
PASSING_VERIFICATION_ASSESSMENTS = {"PASS", "PASS_WITH_CORRECTIONS"}
MIN_VERIFICATION_ACCURACY = 0.95
EVIDENCE_GRADE_SOURCE_SPAN_TYPES = {"verified_claim_text"}
PATENT_SUPPORT_SOURCE_SPAN_TYPES = {
    "verified_claim_text",
    "specification_citation",
}
ReviewerDecisionT = TypeVar("ReviewerDecisionT")


@dataclass(frozen=True)
class ClaimSourceSpanReviewFinding:
    assertion_id: str
    patent_id: str
    claim_number: int | None
    element_number: int | None
    report_section: str
    assertion_text: str
    support_status: str


@dataclass(frozen=True)
class _ClaimRiskParity:
    blocking_patent_ids: set[str]
    contested_patent_ids: set[str]
    medium_risk_patent_ids: set[str]
    analysis_ids: set[str]


@dataclass(frozen=True)
class _JurisdictionParity:
    coverage_reviewed_ids: set[str]
    reviewed_us_ids: set[str]
    reviewed_ep_ids: set[str]
    reviewed_by_jurisdiction: dict[str, set[str]]
    material_outcomes: list[str]


@dataclass(frozen=True)
class _CertificationIdentity:
    receipt_id: str
    receipt_sha: str
    pipeline_sha: str
    source_tree_sha: str
    issuer_verifier_id: str
    key_id: str
    gate_run_id: str
    aggregate_sha: str
    scope_lane_ids: set[str]
    receipt_dsse: str


def analysis_status_value(status: object) -> str:
    status_value = getattr(status, "status", status)
    return str(getattr(status_value, "value", status_value) or "").lower()


def normalize_report_trust_mode(report_data: Mapping[str, Any] | None) -> str:
    """Return the stable legacy source-mode label for report-derived records.

    The unified adaptive pipeline does not persist a public ``trust_mode`` in
    its canonical report document.  API response models have historically
    represented that absence as ``explorer``.  Monitor creation, hydration,
    and workspace summaries must use the same normalization so provenance is
    never persisted as an ambiguous empty string.
    """
    raw_value = report_data.get("trust_mode") if isinstance(report_data, Mapping) else None
    trust_mode = str(raw_value or "explorer").strip().lower()
    if trust_mode in {"explorer", "counsel", "monitor"}:
        return trust_mode
    return "explorer"


def _coerce_claim_source_span_map(support_map: object) -> ClaimSourceSpanMap:
    if isinstance(support_map, ClaimSourceSpanMap):
        return support_map
    if isinstance(support_map, Mapping):
        try:
            return ClaimSourceSpanMap.model_validate(support_map)
        except ValidationError as exc:
            raise ValueError("claim_source_span_map failed schema validation") from exc
    raise ValueError("report_data.claim_source_span_map is required for completed analyses")


def _entry_needs_reviewer_decision(entry: ClaimAssertionSupport) -> bool:
    return bool(entry.customer_visible) and (
        bool(entry.review_required) or entry.support_status == "needs_review"
    )


def claim_source_span_review_findings(
    report_data: Mapping[str, Any],
) -> list[ClaimSourceSpanReviewFinding]:
    """Return customer-visible claim assertions that need reviewer decisions."""
    support_map = report_data.get("claim_source_span_map")
    if support_map is None:
        return []

    source_map = _coerce_claim_source_span_map(support_map)
    findings: list[ClaimSourceSpanReviewFinding] = []
    for entry in source_map.entries:
        if not _entry_needs_reviewer_decision(entry):
            continue
        findings.append(
            ClaimSourceSpanReviewFinding(
                assertion_id=entry.assertion_id,
                patent_id=entry.patent_id,
                claim_number=entry.claim_number,
                element_number=entry.element_number,
                report_section=entry.report_section,
                assertion_text=entry.assertion_text,
                support_status=entry.support_status,
            )
        )
    return findings


def reviewable_finding_keys(
    report_data: Mapping[str, Any] | None,
) -> set[tuple[str, str]]:
    """Return canonical reviewer-decision targets present in the report."""
    if not isinstance(report_data, Mapping):
        return set()

    raw_candidates = (
        report_data.get("patent_analyses")
        or report_data.get("patents")
        or report_data.get("analyses")
        or []
    )
    candidates = raw_candidates if isinstance(raw_candidates, list) else []

    findings: set[tuple[str, str]] = set()
    for entry in candidates:
        if not isinstance(entry, Mapping):
            continue
        patent_id = str(
            entry.get("patent_id")
            or entry.get("id")
            or entry.get("publication_number")
            or entry.get("patent_number")
            or ""
        ).strip()
        if patent_id:
            findings.add(("patent", patent_id))

    for entry in claim_source_span_review_findings(report_data):
        finding_ref = entry.assertion_id.strip()
        if finding_ref:
            findings.add(("claim_element", finding_ref))
    return findings


def reviewer_decision_finding_key(decision: object) -> tuple[str, str]:
    if isinstance(decision, Mapping):
        finding_type = decision.get("finding_type", "")
        finding_ref = decision.get("finding_ref", "")
    else:
        finding_type = getattr(decision, "finding_type", "")
        finding_ref = getattr(decision, "finding_ref", "")
    return (str(finding_type).strip(), str(finding_ref).strip())


def report_payload_fingerprint(report_data: Mapping[str, Any]) -> str:
    """Return a stable fingerprint for the completed report payload."""
    serialized = json.dumps(
        report_data,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def reviewer_decision_report_fingerprint(decision: object) -> str:
    if isinstance(decision, Mapping):
        fingerprint = decision.get("report_fingerprint", "")
    else:
        fingerprint = getattr(decision, "report_fingerprint", "")
    return str(fingerprint or "").strip()


def filter_current_reviewer_decisions(
    report_data: Mapping[str, Any] | None,
    decisions: Iterable[ReviewerDecisionT],
) -> list[ReviewerDecisionT]:
    """Keep only reviewer decisions targeting findings in the current report."""
    if not isinstance(report_data, Mapping):
        return []
    current_keys = reviewable_finding_keys(report_data)
    current_fingerprint = report_payload_fingerprint(report_data)
    return [
        decision
        for decision in decisions
        if reviewer_decision_finding_key(decision) in current_keys
        and reviewer_decision_report_fingerprint(decision) == current_fingerprint
    ]


def require_no_pending_claim_source_span_reviews(
    report_data: Mapping[str, Any],
    *,
    status_code: int = 409,
    title: str = "Conflict",
    detail: str = "Report has claim evidence requiring reviewer approval before sharing",
) -> None:
    if claim_source_span_review_findings(report_data):
        raise APIError(status_code, title, detail)


def _validate_supported_source_spans(
    entry: ClaimAssertionSupport,
    source_map: ClaimSourceSpanMap,
) -> None:
    if not entry.source_span_ids:
        raise ValueError("supported customer-visible claims must include source_span_ids")

    has_evidence_grade_span = False
    for span_id in entry.source_span_ids:
        span = source_map.spans.get(span_id)
        if span is None:
            raise ValueError("supported customer-visible claims reference missing spans")
        if span.span_id != span_id:
            raise ValueError(
                "supported customer-visible claims reference mismatched source span ids"
            )
        if not span.excerpt.strip():
            raise ValueError("supported customer-visible claims reference empty source spans")
        if entry.patent_id and span.patent_id != entry.patent_id:
            raise ValueError(
                "supported customer-visible claims reference source span patent mismatch"
            )
        if entry.claim_number is not None and span.claim_number != entry.claim_number:
            raise ValueError(
                "supported customer-visible claims reference source span claim mismatch"
            )
        if entry.element_number is not None and span.element_number != entry.element_number:
            raise ValueError(
                "supported customer-visible claims reference source span element mismatch"
            )
        if span.source_type in EVIDENCE_GRADE_SOURCE_SPAN_TYPES:
            if not (
                span.source_document_id.strip()
                and span.source_name.strip()
                and span.source_text_sha256.strip()
                and span.source_retrieved_at.strip()
                and span.source_artifact_locator.strip()
                and span.collector_identity.strip()
                and span.collector_version.strip()
                and span.provenance_cassette_sha256.strip()
            ):
                raise ValueError(
                    "verified claim source spans require complete artifact-grade provenance"
                )
            has_evidence_grade_span = True

    if not has_evidence_grade_span:
        raise ValueError(
            "supported customer-visible claims must include evidence-grade source spans"
        )


def validate_claim_source_span_map(support_map: object) -> dict[str, int]:
    source_map = _coerce_claim_source_span_map(support_map)

    if source_map.unsupported_customer_visible_claim_count != 0:
        raise ValueError("claim_source_span_map.unsupported_customer_visible_claim_count must be 0")

    needs_review_count = 0
    for entry in source_map.entries:
        support_status = entry.support_status
        if support_status not in SUPPORT_STATUSES:
            raise ValueError("claim_source_span_map entry support_status is invalid")
        customer_visible = entry.customer_visible
        if customer_visible and support_status == "unsupported":
            raise ValueError("claim_source_span_map contains unsupported customer-visible claims")
        if support_status == "needs_review":
            needs_review_count += 1
        if customer_visible and support_status == "supported":
            _validate_supported_source_spans(entry, source_map)
    if source_map.needs_review_count != needs_review_count:
        raise ValueError("claim_source_span_map.needs_review_count must match entries")

    return {
        "claim_source_span_entry_count": len(source_map.entries),
        "claim_source_span_count": len(source_map.spans),
        "needs_review_count": needs_review_count,
        "unsupported_customer_visible_claim_count": 0,
    }


def _allows_empty_claim_source_span_map(report_data: Mapping[str, Any]) -> bool:
    patent_analyses = report_data.get("patent_analyses")
    if not isinstance(patent_analyses, list) or patent_analyses:
        return False

    return _normalize_int(report_data.get("total_patents_found")) == 0


def validate_report_source_span_provenance(
    report_data: Mapping[str, Any],
) -> dict[str, int]:
    summary = validate_claim_source_span_map(report_data.get("claim_source_span_map"))
    if (
        summary["claim_source_span_entry_count"] == 0 or summary["claim_source_span_count"] == 0
    ) and not _allows_empty_claim_source_span_map(report_data):
        raise ValueError("claim_source_span_map must include source-span provenance")

    source_map = _coerce_claim_source_span_map(report_data.get("claim_source_span_map"))
    report_id = str(report_data.get("report_id") or "").strip()
    if not report_id:
        raise ValueError("report_id is required for source-span provenance")
    patent_details = report_data.get("patent_details")
    detail_map = patent_details if isinstance(patent_details, Mapping) else {}
    for entry in source_map.entries:
        if not (entry.customer_visible and entry.support_status == "supported"):
            continue
        for span_id in entry.source_span_ids:
            span = source_map.spans.get(span_id)
            if span is None or span.source_type != "verified_claim_text":
                continue
            detail = detail_map.get(span.patent_id)
            if not isinstance(detail, Mapping):
                raise ValueError("verified claim source span lacks patent source record")
            claims_text = str(detail.get("claims_text") or "")
            claims_source = str(detail.get("claims_text_source") or "").strip()
            try:
                span_provenance = _claim_text_provenance_from_span(span)
                detail_provenance = ClaimTextProvenance.model_validate(
                    detail.get("claims_text_provenance")
                )
            except (TypeError, ValueError, ValidationError) as exc:
                raise ValueError(
                    "verified claim source span has invalid artifact-grade provenance"
                ) from exc
            synthetic_fixture = span_provenance.source == PatentSource.SYNTHETIC_FIXTURE
            if synthetic_fixture and get_settings().app_env != "dev":
                raise ValueError("synthetic claim provenance is only publishable in development")
            supports_claim_text = span_provenance.supports(
                claims_text,
                span.patent_id,
            )
            if synthetic_fixture:
                supports_claim_text = bool(
                    span_provenance.retrieval_complete
                    and span_provenance.claim_numbers
                    and span_provenance.independent_claim_numbers
                    and span_provenance.source_document_id == span.patent_id
                    and hashlib.sha256(claims_text.encode("utf-8")).hexdigest()
                    == span_provenance.artifact_sha256
                )
            else:
                try:
                    keyring = get_settings().checkpoint_integrity_keys
                    verification_key = keyring.verification_key(span.evidence_attestation_key_id)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "verified claim source span uses an unavailable evidence key"
                    ) from exc
                supports_claim_text = verify_source_span_attestation(
                    span,
                    verification_key=verification_key,
                    expected_subject_id=report_id,
                )
            if (
                span.source_document_id != span.patent_id
                or not claims_source
                or span.source_name != claims_source
                or span.excerpt not in claims_text
                or span_provenance != detail_provenance
                or not supports_claim_text
            ):
                raise ValueError("verified claim source span does not match patent source record")

    return summary


def _claim_text_provenance_from_span(span: SourceSpanReference) -> ClaimTextProvenance:
    """Reconstruct and validate the complete claim-text cassette at the API boundary."""
    return ClaimTextProvenance.model_validate(
        {
            "schema_version": span.provenance_schema_version,
            "source": span.source_name,
            "source_document_id": span.source_document_id,
            "retrieved_at": span.source_retrieved_at,
            "artifact_locator": span.source_artifact_locator,
            "artifact_sha256": span.source_text_sha256,
            "collector_identity": span.collector_identity,
            "collector_version": span.collector_version,
            "claim_numbers": tuple(span.claim_numbers),
            "independent_claim_numbers": tuple(span.independent_claim_numbers),
            "retrieval_complete": span.retrieval_complete,
            "cassette_sha256": span.provenance_cassette_sha256,
        }
    )


def require_report_source_span_provenance(
    report_data: Mapping[str, Any],
    *,
    status_code: int = 404,
    title: str = "Not Found",
    detail: str = "Report not yet available",
) -> None:
    try:
        validate_report_source_span_provenance(report_data)
    except ValueError as exc:
        raise APIError(status_code, title, detail) from exc


def _verification_dict(report_data: Mapping[str, Any]) -> Mapping[str, Any]:
    verification = report_data.get("verification")
    if not isinstance(verification, Mapping):
        raise ValueError("report verification metadata is required")
    return verification


def _verification_summary_dict(report_data: Mapping[str, Any]) -> Mapping[str, Any]:
    verification_summary = report_data.get("verification_summary")
    if not isinstance(verification_summary, Mapping):
        raise ValueError("report verification_summary metadata is required")
    return verification_summary


def _has_report_claims(report_data: Mapping[str, Any]) -> bool:
    source_map = report_data.get("claim_source_span_map")
    if isinstance(source_map, Mapping):
        entries = source_map.get("entries")
        if isinstance(entries, list) and entries:
            return True
    patent_analyses = report_data.get("patent_analyses")
    return isinstance(patent_analyses, list) and bool(patent_analyses)


def _dict_value(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_value(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _non_empty_strings(value: object) -> list[str]:
    values = _list_value(value)
    return [str(item).strip() for item in values if str(item or "").strip()]


def _decision_value(value: object) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _supported_claim_source_patent_ids(report_data: Mapping[str, Any]) -> set[str]:
    support_map = _dict_value(report_data.get("claim_source_span_map"))
    spans = support_map.get("spans")
    span_map = spans if isinstance(spans, Mapping) else {}
    patent_ids: set[str] = set()
    for entry in _list_value(support_map.get("entries")):
        if not isinstance(entry, Mapping):
            continue
        if str(entry.get("support_status") or "").strip().lower() != "supported":
            continue
        if entry.get("customer_visible") is not True:
            continue
        source_span_ids = _non_empty_strings(entry.get("source_span_ids"))
        if not source_span_ids:
            continue
        entry_patent_id = str(entry.get("patent_id") or "").strip()
        entry_has_evidence_grade_span = False
        for span_id in source_span_ids:
            span = span_map.get(span_id)
            if not isinstance(span, Mapping):
                continue
            if str(span.get("source_type") or "").strip() not in PATENT_SUPPORT_SOURCE_SPAN_TYPES:
                continue
            entry_has_evidence_grade_span = True
            span_patent_id = str(span.get("patent_id") or "").strip()
            if span_patent_id:
                patent_ids.add(span_patent_id)
        if entry_has_evidence_grade_span and entry_patent_id:
            patent_ids.add(entry_patent_id)
    return patent_ids


def _patent_analysis_ids(report_data: Mapping[str, Any]) -> set[str]:
    patent_ids: set[str] = set()
    for analysis in _list_value(report_data.get("patent_analyses")):
        if isinstance(analysis, Mapping):
            patent_id = str(analysis.get("patent_id") or "").strip()
            if patent_id:
                patent_ids.add(patent_id)
    return patent_ids


def _clearance_decision_dict(report_data: Mapping[str, Any]) -> Mapping[str, Any]:
    return _dict_value(report_data.get("clearance_decision"))


def _clearance_audit_dict(report_data: Mapping[str, Any]) -> Mapping[str, Any]:
    return _dict_value(_clearance_decision_dict(report_data).get("decision_audit"))


def _coverage_summary_dict(report_data: Mapping[str, Any]) -> Mapping[str, Any]:
    return _dict_value(_clearance_audit_dict(report_data).get("coverage_summary"))


def _reviewed_patent_ids(report_data: Mapping[str, Any]) -> set[str]:
    return set(_non_empty_strings(_coverage_summary_dict(report_data).get("reviewed_patent_ids")))


def _decisive_references(report_data: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    refs = _clearance_audit_dict(report_data).get("decisive_references")
    return [ref for ref in _list_value(refs) if isinstance(ref, Mapping)]


def _decisive_reference_patent_ids(report_data: Mapping[str, Any]) -> set[str]:
    patent_ids: set[str] = set()
    for ref in _decisive_references(report_data):
        patent_id = str(ref.get("patent_id") or "").strip()
        if patent_id:
            patent_ids.add(patent_id)
    return patent_ids


def _jurisdiction_material_patent_ids(report_data: Mapping[str, Any]) -> set[str]:
    patent_ids: set[str] = set()
    for decision in _list_value(report_data.get("jurisdiction_decisions")):
        if not isinstance(decision, Mapping):
            continue
        patent_ids.update(_non_empty_strings(decision.get("reviewed_patent_ids")))
        patent_ids.update(_non_empty_strings(decision.get("blocking_patent_ids")))
    return patent_ids


def _claim_program_material_patent_ids(report_data: Mapping[str, Any]) -> set[str]:
    claim_program_summary = _dict_value(
        _clearance_audit_dict(report_data).get("claim_program_summary")
    )
    patent_ids: set[str] = set()
    for field in (
        "blocking_patent_ids",
        "contested_patent_ids",
        "medium_risk_patent_ids",
    ):
        patent_ids.update(_non_empty_strings(claim_program_summary.get(field)))
    return patent_ids


def _evidence_inventory_patent_ids(report_data: Mapping[str, Any]) -> set[str]:
    patent_ids: set[str] = set()

    for artifact in _list_value(report_data.get("evidence_artifacts")):
        if isinstance(artifact, Mapping):
            patent_ids.update(_non_empty_strings([artifact.get("patent_id")]))

    for dossier in _list_value(report_data.get("prosecution_dossiers")):
        if isinstance(dossier, Mapping):
            patent_ids.update(_non_empty_strings([dossier.get("patent_id")]))

    evidence_index = _dict_value(report_data.get("matter_evidence_index"))
    for record in _list_value(evidence_index.get("patent_records")):
        if isinstance(record, Mapping):
            patent_ids.update(_non_empty_strings([record.get("patent_id")]))
    for record in _list_value(evidence_index.get("family_records")):
        if not isinstance(record, Mapping):
            continue
        patent_ids.update(_non_empty_strings([record.get("broadest_patent_id")]))
        patent_ids.update(_non_empty_strings(record.get("material_patent_ids")))
        patent_ids.update(_non_empty_strings(record.get("blocking_patent_ids")))

    return patent_ids


def _material_report_patent_ids(report_data: Mapping[str, Any]) -> set[str]:
    return (
        _patent_analysis_ids(report_data)
        | _reviewed_patent_ids(report_data)
        | _decisive_reference_patent_ids(report_data)
        | _jurisdiction_material_patent_ids(report_data)
        | _claim_program_material_patent_ids(report_data)
        | _evidence_inventory_patent_ids(report_data)
    )


def _aligned_supported_material_patent_ids(report_data: Mapping[str, Any]) -> set[str]:
    supported_source_ids = _supported_claim_source_patent_ids(report_data)
    material_ids = _material_report_patent_ids(report_data)
    if not material_ids:
        return supported_source_ids
    return material_ids & supported_source_ids


def _has_aligned_source_span_support_for_ids(
    report_data: Mapping[str, Any],
    patent_ids: set[str],
) -> bool:
    return bool(patent_ids & _supported_claim_source_patent_ids(report_data))


def _has_true_zero_patent_clear(report_data: Mapping[str, Any]) -> bool:
    """Return false until an independently evidenced true-zero contract exists."""
    return False


def _has_material_patent_support(report_data: Mapping[str, Any]) -> bool:
    return bool(_aligned_supported_material_patent_ids(report_data))


def validate_material_report_assertion_provenance(report_data: Mapping[str, Any]) -> dict[str, int]:
    """Validate top-line customer-visible assertions have deterministic support."""
    unsupported_patent_analysis_ids = _patent_analysis_ids(
        report_data
    ) - _supported_claim_source_patent_ids(report_data)
    if unsupported_patent_analysis_ids:
        raise ValueError("patent_analyses contain patents without aligned source-span support")

    unsupported_material_patent_ids = _material_report_patent_ids(
        report_data
    ) - _supported_claim_source_patent_ids(report_data)
    if unsupported_material_patent_ids:
        raise ValueError("material report patents lack aligned source-span support")

    risk_summary = _dict_value(report_data.get("risk_summary"))
    overall_risk = _decision_value(risk_summary.get("overall_risk"))
    if overall_risk in {"high", "medium"} and not _has_material_patent_support(report_data):
        raise ValueError("risk_summary overall_risk lacks material patent support")
    if overall_risk == "clear" and not (
        _has_true_zero_patent_clear(report_data) or _has_material_patent_support(report_data)
    ):
        raise ValueError("risk_summary clear conclusion lacks search or patent support")

    clearance_decision = _clearance_decision_dict(report_data)
    decision = _decision_value(clearance_decision.get("decision"))
    decisive_refs = _decisive_references(report_data)
    coverage = _coverage_summary_dict(report_data)
    claim_program_summary = _dict_value(
        _clearance_audit_dict(report_data).get("claim_program_summary")
    )
    blocking_patent_ids = _non_empty_strings(claim_program_summary.get("blocking_patent_ids"))
    insufficiency_reasons = _non_empty_strings(
        _clearance_audit_dict(report_data).get("insufficiency_reasons")
    )
    if decision == "clear" and not (_has_true_zero_patent_clear(report_data) or decisive_refs):
        raise ValueError("clearance_decision clear conclusion lacks decisive references")
    if (
        decision == "clear"
        and not _has_true_zero_patent_clear(report_data)
        and not _has_aligned_source_span_support_for_ids(
            report_data,
            _decisive_reference_patent_ids(report_data),
        )
    ):
        raise ValueError("clearance_decision clear conclusion lacks aligned source-span support")
    blocking_support_ids = set(blocking_patent_ids) | _decisive_reference_patent_ids(report_data)
    if decision == "blocked" and not blocking_support_ids:
        raise ValueError("clearance_decision blocked conclusion lacks blocking evidence")
    if decision == "blocked" and not _has_aligned_source_span_support_for_ids(
        report_data,
        blocking_support_ids,
    ):
        raise ValueError("clearance_decision blocked conclusion lacks aligned source-span support")
    if (
        decision == "unclear"
        and not _has_true_zero_patent_clear(report_data)
        and not (
            _non_empty_strings(coverage.get("reviewed_patent_ids"))
            or insufficiency_reasons
            or decisive_refs
        )
    ):
        raise ValueError("clearance_decision unclear conclusion lacks review or gap evidence")

    for index, jurisdiction_decision in enumerate(
        _list_value(report_data.get("jurisdiction_decisions"))
    ):
        if not isinstance(jurisdiction_decision, Mapping):
            continue
        jurisdiction = str(jurisdiction_decision.get("jurisdiction") or index).strip()
        jurisdiction_label = jurisdiction or str(index)
        jurisdiction_outcome = _decision_value(jurisdiction_decision.get("decision"))
        reviewed_ids = _non_empty_strings(jurisdiction_decision.get("reviewed_patent_ids"))
        blocking_ids = _non_empty_strings(jurisdiction_decision.get("blocking_patent_ids"))
        gate_failures = _non_empty_strings(jurisdiction_decision.get("gate_failures"))
        reasoning = _non_empty_strings(jurisdiction_decision.get("reasoning"))
        if jurisdiction_outcome == "clear" and not (
            _has_true_zero_patent_clear(report_data) or reviewed_ids
        ):
            raise ValueError(
                f"jurisdiction_decisions[{jurisdiction_label}] clear conclusion "
                "lacks reviewed patent evidence"
            )
        if (
            jurisdiction_outcome == "clear"
            and reviewed_ids
            and not _has_aligned_source_span_support_for_ids(report_data, set(reviewed_ids))
        ):
            raise ValueError(
                f"jurisdiction_decisions[{jurisdiction_label}] clear conclusion "
                "lacks aligned source-span support"
            )
        if jurisdiction_outcome == "blocked" and not (blocking_ids or reviewed_ids):
            raise ValueError(
                f"jurisdiction_decisions[{jurisdiction_label}] blocked conclusion "
                "lacks blocking patent evidence"
            )
        if (
            jurisdiction_outcome == "blocked"
            and (blocking_ids or reviewed_ids)
            and not _has_aligned_source_span_support_for_ids(
                report_data,
                set(blocking_ids) | set(reviewed_ids),
            )
        ):
            raise ValueError(
                f"jurisdiction_decisions[{jurisdiction_label}] blocked conclusion "
                "lacks aligned source-span support"
            )
        if jurisdiction_outcome == "unclear" and not (
            reviewed_ids or gate_failures or reasoning or _has_true_zero_patent_clear(report_data)
        ):
            raise ValueError(
                f"jurisdiction_decisions[{jurisdiction_label}] unclear conclusion "
                "lacks review or gap evidence"
            )

    return {
        "material_patent_support_count": len(_aligned_supported_material_patent_ids(report_data)),
        "decisive_reference_count": len(decisive_refs),
    }


def _string_set(value: object) -> set[str]:
    return set(_non_empty_strings(value))


def _claim_id_patent_ids(value: object) -> set[str]:
    patent_ids: set[str] = set()
    for claim_id in _non_empty_strings(value):
        patent_id = claim_id.partition("#claim")[0].strip()
        if patent_id:
            patent_ids.add(patent_id)
    return patent_ids


def _patent_jurisdiction(patent_id: str) -> str:
    return cast(str, publication_jurisdiction(patent_id))


def _patent_analysis_risk_sets(
    report_data: Mapping[str, Any],
) -> tuple[set[str], set[str], set[str]]:
    high: set[str] = set()
    medium: set[str] = set()
    clear: set[str] = set()
    seen: set[str] = set()
    for item in _list_value(report_data.get("patent_analyses")):
        if not isinstance(item, Mapping):
            raise ValueError("patent_analyses contains a non-object entry")
        raw_patent_id = str(item.get("patent_id") or "").strip()
        if not raw_patent_id:
            raise ValueError("patent_analyses patent IDs must be nonempty and unique")
        patent_id = canonical_publication_id(raw_patent_id)
        if patent_id in seen:
            raise ValueError("patent_analyses patent IDs must be nonempty and unique")
        seen.add(patent_id)
        risk = _decision_value(item.get("risk_level"))
        if risk == "high":
            high.add(patent_id)
        elif risk == "medium":
            medium.add(patent_id)
        elif risk in {"clear", "low"}:
            clear.add(patent_id)
        else:
            raise ValueError(f"patent_analyses[{patent_id}] risk_level is invalid")
    return high, medium, clear


def _derived_claim_program_summary(
    report_data: Mapping[str, Any],
) -> dict[str, int | set[str]]:
    decisions = _list_value(report_data.get("claim_program_decisions"))
    blocking_claim_ids: set[str] = set()
    contested_claim_ids: set[str] = set()
    medium_claim_ids: set[str] = set()
    strong_invalidity_ids: set[str] = set()
    insufficient_ids: set[str] = set()
    blocking_patent_ids: set[str] = set()
    contested_patent_ids: set[str] = set()
    medium_patent_ids: set[str] = set()
    fallback_count = 0
    seen_programs: dict[tuple[str, int], tuple[object, ...]] = {}
    positive_claim_patent_ids: set[str] = set()
    fallback_patent_ids: set[str] = set()

    for item in decisions:
        if not isinstance(item, Mapping):
            raise ValueError("claim_program_decisions contains a non-object entry")
        raw_patent_id = str(item.get("patent_id") or "").strip()
        if not raw_patent_id:
            raise ValueError("claim_program_decisions patent_id is required")
        patent_id = canonical_publication_id(raw_patent_id)
        raw_claim_number = item.get("claim_number")
        if isinstance(raw_claim_number, bool) or not isinstance(raw_claim_number, int):
            raise ValueError("claim_program_decisions claim_number must be an integer")
        claim_number = raw_claim_number
        if claim_number < 0:
            raise ValueError("claim_program_decisions claim_number cannot be negative")
        program_identity = (patent_id, claim_number)
        fingerprint = (
            _decision_value(item.get("literal_risk")),
            _decision_value(item.get("doe_risk")),
            _decision_value(item.get("invalidity_strength")),
            item.get("evidence_sufficient"),
            tuple(sorted(_non_empty_strings(item.get("missing_components")))),
        )
        if program_identity in seen_programs:
            if seen_programs[program_identity] != fingerprint:
                raise ValueError("contradictory duplicate claim-program decision")
            continue
        seen_programs[program_identity] = fingerprint
        if claim_number == 0:
            if patent_id in positive_claim_patent_ids:
                raise ValueError(
                    "claim-program whole-document fallback cannot coexist with positive claims"
                )
            fallback_patent_ids.add(patent_id)
        else:
            if patent_id in fallback_patent_ids:
                raise ValueError(
                    "claim-program whole-document fallback cannot coexist with positive claims"
                )
            positive_claim_patent_ids.add(patent_id)
        claim_id = f"{patent_id}#claim{claim_number}" if claim_number > 0 else patent_id
        fallback_count = len(fallback_patent_ids)
        literal_risk = _decision_value(item.get("literal_risk"))
        doe_risk = _decision_value(item.get("doe_risk"))
        strong_invalidity = _decision_value(item.get("invalidity_strength")) == "strong"
        if strong_invalidity:
            strong_invalidity_ids.add(claim_id)
        if item.get("evidence_sufficient") is not True:
            insufficient_ids.add(claim_id)
        if "high" in {literal_risk, doe_risk}:
            if strong_invalidity:
                contested_claim_ids.add(claim_id)
                contested_patent_ids.add(patent_id)
            else:
                blocking_claim_ids.add(claim_id)
                blocking_patent_ids.add(patent_id)
        elif "medium" in {literal_risk, doe_risk}:
            medium_claim_ids.add(claim_id)
            medium_patent_ids.add(patent_id)

    contested_patent_ids = contested_patent_ids - blocking_patent_ids
    medium_patent_ids = medium_patent_ids - blocking_patent_ids - contested_patent_ids
    return {
        "total_claim_programs_reviewed": sum(
            1 for _patent_id, claim_number in seen_programs if claim_number > 0
        ),
        "patent_level_fallback_count": fallback_count,
        "blocking_claim_ids": blocking_claim_ids,
        "contested_claim_ids": contested_claim_ids,
        "medium_risk_claim_ids": medium_claim_ids,
        "claims_with_strong_invalidity": strong_invalidity_ids,
        "claims_with_insufficient_evidence": insufficient_ids,
        "blocking_patent_ids": blocking_patent_ids,
        "contested_patent_ids": contested_patent_ids,
        "medium_risk_patent_ids": medium_patent_ids,
    }


def _governed_executive_summary(
    *,
    decision: str,
    blocker_count: int,
    analyzed_count: int,
) -> str:
    return (
        f"Clearance decision: {decision.upper()}. {blocker_count} blocking "
        f"patent{'s' if blocker_count != 1 else ''} identified from "
        f"{analyzed_count} analyzed."
    )


def _claim_program_parity_projection(value: object) -> dict[tuple[str, int], tuple[object, ...]]:
    projection: dict[tuple[str, int], tuple[object, ...]] = {}
    positive_claim_patent_ids: set[str] = set()
    fallback_patent_ids: set[str] = set()
    for item in _list_value(value):
        if not isinstance(item, Mapping):
            raise ValueError("claim-program parity collection contains a non-object entry")
        try:
            normalized = ClaimProgramDecision.model_validate(item).model_dump(mode="python")
        except (TypeError, ValueError, ValidationError) as exc:
            raise ValueError(
                "claim-program parity collection contains an invalid decision"
            ) from exc
        patent_id = canonical_publication_id(str(normalized.get("patent_id") or "").strip())
        claim_number = normalized.get("claim_number")
        if isinstance(claim_number, bool) or not isinstance(claim_number, int):
            raise ValueError("claim-program parity claim_number must be an integer")
        if claim_number < 0:
            raise ValueError("claim-program parity claim_number cannot be negative")
        identity = (patent_id, claim_number)
        if claim_number == 0:
            if patent_id in positive_claim_patent_ids:
                raise ValueError(
                    "claim-program whole-document fallback cannot coexist with positive claims"
                )
            fallback_patent_ids.add(patent_id)
        else:
            if patent_id in fallback_patent_ids:
                raise ValueError(
                    "claim-program whole-document fallback cannot coexist with positive claims"
                )
            positive_claim_patent_ids.add(patent_id)
        fingerprint = (
            str(normalized.get("jurisdiction") or "").strip().upper(),
            str(normalized.get("literal_outcome") or "").strip().lower(),
            _decision_value(normalized.get("literal_risk")),
            _decision_value(normalized.get("doe_risk")),
            _decision_value(normalized.get("invalidity_strength")),
            tuple(sorted(_non_empty_strings(normalized.get("prosecution_risk_flags")))),
            _decision_value(normalized.get("prosecution_risk_level")),
            _decision_value(normalized.get("post_grant_risk_level")),
            normalized.get("scope_constrained"),
            tuple(sorted(_non_empty_strings(normalized.get("future_risk_flags")))),
            _decision_value(normalized.get("commercial_severity")),
            normalized.get("evidence_sufficient"),
            tuple(sorted(_non_empty_strings(normalized.get("missing_components")))),
            tuple(sorted(_non_empty_strings(normalized.get("record_basis")))),
            tuple(_non_empty_strings(normalized.get("rationale"))),
        )
        if identity in projection and projection[identity] != fingerprint:
            raise ValueError("contradictory duplicate claim-program decision")
        projection[identity] = fingerprint
    return projection


def _validate_authority_coverage_parity(
    authority_coverage: Mapping[str, Any],
    matter_evidence_index: Mapping[str, Any],
    record_completeness: Mapping[str, Any],
) -> None:
    required_fields = {
        "policy",
        "authoritative_source_names",
        "supporting_source_names",
        "authoritative_categories_covered",
        "authoritative_categories_missing",
        "patents_with_authoritative_records",
        "patents_without_authoritative_records",
        "clearance_grade_ready_patents",
    }
    if set(authority_coverage) != required_fields:
        raise ValueError("authority_coverage is incomplete")
    patent_records = _list_value(matter_evidence_index.get("patent_records"))
    records_with_authority = sum(
        1
        for record in patent_records
        if isinstance(record, Mapping)
        and _non_empty_strings(record.get("authoritative_record_categories"))
    )
    expected_counts = {
        "patents_with_authoritative_records": records_with_authority,
        "patents_without_authoritative_records": max(
            0,
            _normalize_int(matter_evidence_index.get("material_patent_count"))
            - records_with_authority,
        ),
        "clearance_grade_ready_patents": len(
            _string_set(matter_evidence_index.get("clearance_grade_ready_patent_ids"))
        ),
    }
    for field_name, expected in expected_counts.items():
        if _normalize_int(authority_coverage.get(field_name), -1) != expected:
            raise ValueError(f"authority_coverage {field_name} does not match evidence index")
    if _string_set(authority_coverage.get("authoritative_source_names")) != _string_set(
        matter_evidence_index.get("authoritative_source_names")
    ):
        raise ValueError("authority_coverage authoritative sources do not match evidence index")
    if _string_set(authority_coverage.get("supporting_source_names")) != _string_set(
        matter_evidence_index.get("supporting_source_names")
    ):
        raise ValueError("authority_coverage supporting sources do not match evidence index")
    covered_categories = {
        category
        for record in patent_records
        if isinstance(record, Mapping)
        for category in _non_empty_strings(record.get("authoritative_record_categories"))
    }
    required_categories = {
        COMPONENT_TO_CATEGORY[component]
        for component in _non_empty_strings(record_completeness.get("required_components"))
        if component in COMPONENT_TO_CATEGORY
    }
    missing_categories = required_categories - covered_categories
    if (
        _string_set(authority_coverage.get("authoritative_categories_covered"))
        != covered_categories
    ):
        raise ValueError("authority_coverage covered categories do not match evidence index")
    if (
        _string_set(authority_coverage.get("authoritative_categories_missing"))
        != missing_categories
    ):
        raise ValueError(
            "authority_coverage missing categories do not match record-completeness policy"
        )


def _require_mapping_field(
    parent: Mapping[str, Any],
    field_name: str,
    *,
    context: str = "report_data",
) -> Mapping[str, Any]:
    value = parent.get(field_name)
    if not isinstance(value, Mapping):
        raise ValueError(f"{context}.{field_name} is required")
    return value


def _validate_commercial_exposure(
    commercial_exposure: Mapping[str, Any],
    *,
    blocking_patent_ids: set[str],
) -> None:
    required_fields = {
        "damages_injunction_risk",
        "business_severity",
        "blocking_patent_ids",
        "rationale",
        "summary",
    }
    if set(commercial_exposure) != required_fields:
        raise ValueError("commercial_exposure is incomplete")
    if _decision_value(commercial_exposure.get("damages_injunction_risk")) not in {
        "high",
        "elevated",
        "uncertain",
        "moderate",
        "limited",
    }:
        raise ValueError("commercial_exposure damages/injunction risk is invalid")
    if _decision_value(commercial_exposure.get("business_severity")) not in {
        "high",
        "medium",
        "low",
    }:
        raise ValueError("commercial_exposure business severity is invalid")
    if _string_set(commercial_exposure.get("blocking_patent_ids")) != blocking_patent_ids:
        raise ValueError("commercial_exposure blocker IDs do not match governed blockers")
    if not _non_empty_strings(commercial_exposure.get("rationale")):
        raise ValueError("commercial_exposure rationale is required")
    if not str(commercial_exposure.get("summary") or "").strip():
        raise ValueError("commercial_exposure summary is required")


def _semantic_parity_inputs(
    report_data: Mapping[str, Any],
) -> tuple[
    str,
    Mapping[str, Any],
    Mapping[str, Any],
    Mapping[str, Any],
    Mapping[str, Any],
    list[Mapping[str, Any]],
]:
    clearance_decision = _clearance_decision_dict(report_data)
    decision = _decision_value(clearance_decision.get("decision"))
    if decision not in {"clear", "unclear", "blocked"}:
        raise ValueError("clearance_decision decision is invalid")

    audit = _clearance_audit_dict(report_data)
    coverage = _coverage_summary_dict(report_data)
    claim_program = _dict_value(audit.get("claim_program_summary"))
    risk_summary = _dict_value(report_data.get("risk_summary"))
    raw_jurisdiction_decisions = _list_value(report_data.get("jurisdiction_decisions"))
    jurisdiction_decisions = [
        item for item in raw_jurisdiction_decisions if isinstance(item, Mapping)
    ]
    if len(jurisdiction_decisions) != len(raw_jurisdiction_decisions):
        raise ValueError("jurisdiction_decisions contains a non-object entry")

    jurisdictions = [str(item.get("jurisdiction") or "").strip() for item in jurisdiction_decisions]
    if any(not jurisdiction for jurisdiction in jurisdictions) or len(jurisdictions) != len(
        set(jurisdictions)
    ):
        raise ValueError("jurisdiction_decisions jurisdictions must be nonempty and unique")
    return decision, audit, coverage, claim_program, risk_summary, jurisdiction_decisions


def _claim_program_risk_sets(
    report_data: Mapping[str, Any],
    claim_program: Mapping[str, Any],
) -> tuple[set[str], set[str], set[str]]:
    blocking_patent_ids = _string_set(claim_program.get("blocking_patent_ids"))
    contested_patent_ids = _string_set(claim_program.get("contested_patent_ids"))
    medium_risk_patent_ids = _string_set(claim_program.get("medium_risk_patent_ids"))
    risk_sets = (blocking_patent_ids, contested_patent_ids, medium_risk_patent_ids)
    if any(
        left & right for index, left in enumerate(risk_sets) for right in risk_sets[index + 1 :]
    ):
        raise ValueError("claim_program_summary patent risk IDs must be disjoint")

    for field_name, expected in _derived_claim_program_summary(report_data).items():
        if isinstance(expected, int):
            if _normalize_int(claim_program.get(field_name), -1) != expected:
                raise ValueError(
                    f"claim_program_summary {field_name} does not match claim decisions"
                )
        elif _string_set(claim_program.get(field_name)) != expected:
            raise ValueError(f"claim_program_summary {field_name} does not match claim decisions")
    return blocking_patent_ids, contested_patent_ids, medium_risk_patent_ids


def _validate_patent_and_claim_risk_parity(
    report_data: Mapping[str, Any],
    claim_program: Mapping[str, Any],
    *,
    blocking_patent_ids: set[str],
    contested_patent_ids: set[str],
    medium_risk_patent_ids: set[str],
) -> _ClaimRiskParity:
    analysis_high, analysis_medium, analysis_clear = _patent_analysis_risk_sets(report_data)
    analysis_ids = analysis_high | analysis_medium | analysis_clear
    if analysis_ids:
        if analysis_high != blocking_patent_ids | contested_patent_ids:
            raise ValueError("patent_analyses high-risk IDs do not match blocking/contested IDs")
        if analysis_medium != medium_risk_patent_ids:
            raise ValueError("patent_analyses medium-risk IDs do not match medium-risk IDs")
        if analysis_clear & (blocking_patent_ids | contested_patent_ids | medium_risk_patent_ids):
            raise ValueError("patent_analyses clear IDs overlap governed risk IDs")

    claim_blocking_patents = _claim_id_patent_ids(claim_program.get("blocking_claim_ids"))
    claim_contested_patents = (
        _claim_id_patent_ids(claim_program.get("contested_claim_ids")) - claim_blocking_patents
    )
    claim_medium_patents = (
        _claim_id_patent_ids(claim_program.get("medium_risk_claim_ids"))
        - claim_blocking_patents
        - claim_contested_patents
    )
    if (
        claim_blocking_patents != blocking_patent_ids
        or claim_contested_patents != contested_patent_ids
        or claim_medium_patents != medium_risk_patent_ids
    ):
        raise ValueError("claim_program_summary claim risks do not match patent risk IDs")
    return _ClaimRiskParity(
        blocking_patent_ids=blocking_patent_ids,
        contested_patent_ids=contested_patent_ids,
        medium_risk_patent_ids=medium_risk_patent_ids,
        analysis_ids=analysis_ids,
    )


def _validated_jurisdiction_decision(
    item: Mapping[str, Any],
    reviewed_by_jurisdiction: Mapping[str, set[str]],
) -> tuple[str, str, set[str], set[str]]:
    jurisdiction = str(item.get("jurisdiction") or "").strip()
    outcome = _decision_value(item.get("decision"))
    if outcome not in {"clear", "unclear", "blocked"}:
        raise ValueError(f"jurisdiction_decisions[{jurisdiction}] decision is invalid")
    reviewed_ids = _string_set(item.get("reviewed_patent_ids"))
    blocker_ids = _string_set(item.get("blocking_patent_ids"))
    if reviewed_ids != reviewed_by_jurisdiction.get(jurisdiction, set()):
        raise ValueError(
            f"jurisdiction_decisions[{jurisdiction}] reviewed IDs do not match patent IDs"
        )
    if any(_patent_jurisdiction(patent_id) != jurisdiction for patent_id in blocker_ids):
        raise ValueError(f"jurisdiction_decisions[{jurisdiction}] blocker jurisdiction is invalid")
    gate_failures = _non_empty_strings(item.get("gate_failures"))
    if blocker_ids - reviewed_ids:
        raise ValueError(
            f"jurisdiction_decisions[{jurisdiction}] blockers are not reviewed patents"
        )
    if outcome == "blocked" and not blocker_ids:
        raise ValueError(
            f"jurisdiction_decisions[{jurisdiction}] blocked decision has zero blockers"
        )
    if outcome == "clear" and (
        blocker_ids
        or gate_failures
        or item.get("evidence_sufficient_for_clearance") is not True
        or item.get("supports_positive_clearance") is not True
        or item.get("local_review_required") is True
    ):
        raise ValueError(
            f"jurisdiction_decisions[{jurisdiction}] clear decision has unresolved signals"
        )
    return jurisdiction, outcome, reviewed_ids, blocker_ids


def _validate_jurisdiction_parity(
    jurisdiction_decisions: list[Mapping[str, Any]],
    coverage: Mapping[str, Any],
    *,
    blocking_patent_ids: set[str],
) -> _JurisdictionParity:
    coverage_reviewed_ids = _string_set(coverage.get("reviewed_patent_ids"))
    reviewed_by_jurisdiction: dict[str, set[str]] = {}
    for patent_id in coverage_reviewed_ids:
        reviewed_by_jurisdiction.setdefault(_patent_jurisdiction(patent_id), set()).add(patent_id)

    jurisdiction_blocking_ids: set[str] = set()
    jurisdiction_reviewed_ids: set[str] = set()
    represented_jurisdictions: set[str] = set()
    material_outcomes: list[str] = []
    for item in jurisdiction_decisions:
        jurisdiction, outcome, reviewed_ids, blocker_ids = _validated_jurisdiction_decision(
            item,
            reviewed_by_jurisdiction,
        )
        represented_jurisdictions.add(jurisdiction)
        jurisdiction_reviewed_ids.update(reviewed_ids)
        jurisdiction_blocking_ids.update(blocker_ids)
        if reviewed_ids or blocker_ids:
            material_outcomes.append(outcome)

    if jurisdiction_blocking_ids != blocking_patent_ids:
        raise ValueError(
            "jurisdiction_decisions blocking IDs do not match claim_program_summary blockers"
        )
    if any(
        patent_ids and jurisdiction not in represented_jurisdictions
        for jurisdiction, patent_ids in reviewed_by_jurisdiction.items()
    ):
        raise ValueError("jurisdiction_decisions omit a material patent jurisdiction")
    if jurisdiction_reviewed_ids != coverage_reviewed_ids:
        raise ValueError("jurisdiction_decisions reviewed IDs do not match decision audit coverage")
    reviewed_us_ids = _string_set(coverage.get("reviewed_us_patent_ids"))
    reviewed_ep_ids = _string_set(coverage.get("reviewed_ep_patent_ids"))
    if reviewed_us_ids != reviewed_by_jurisdiction.get("US", set()):
        raise ValueError("coverage reviewed_us_patent_ids do not match derived jurisdiction")
    if reviewed_ep_ids != reviewed_by_jurisdiction.get("EP", set()):
        raise ValueError("coverage reviewed_ep_patent_ids do not match derived jurisdiction")
    return _JurisdictionParity(
        coverage_reviewed_ids=coverage_reviewed_ids,
        reviewed_us_ids=reviewed_us_ids,
        reviewed_ep_ids=reviewed_ep_ids,
        reviewed_by_jurisdiction=reviewed_by_jurisdiction,
        material_outcomes=material_outcomes,
    )


def _validate_audit_coverage_counts(
    audit: Mapping[str, Any],
    coverage: Mapping[str, Any],
    jurisdiction: _JurisdictionParity,
) -> None:
    count_contracts = (
        ("queried_sources_count", len(_string_set(coverage.get("queried_source_names")))),
        ("successful_sources_count", len(_string_set(coverage.get("successful_source_names")))),
        (
            "authoritative_sources_count",
            len(_string_set(coverage.get("authoritative_source_names"))),
        ),
        ("material_patents_reviewed", len(jurisdiction.coverage_reviewed_ids)),
        ("material_us_patents", len(_string_set(coverage.get("reviewed_us_patent_ids")))),
        ("material_ep_patents", len(_string_set(coverage.get("reviewed_ep_patent_ids")))),
        ("analysis_failures_count", len(_string_set(coverage.get("failed_analysis_patent_ids")))),
        (
            "clearance_grade_ready_patents",
            len(_string_set(coverage.get("clearance_grade_ready_patent_ids"))),
        ),
        ("incomplete_material_patents", len(_string_set(coverage.get("incomplete_patent_ids")))),
        (
            "clearance_grade_ready_families",
            len(_string_set(coverage.get("clearance_grade_ready_family_ids"))),
        ),
        ("incomplete_material_families", len(_string_set(coverage.get("incomplete_family_ids")))),
    )
    for field_name, expected_count in count_contracts:
        if _normalize_int(audit.get(field_name), -1) != expected_count:
            raise ValueError(f"decision_audit {field_name} does not match coverage")

    derived_counts = (
        (
            "patents_with_claims",
            len(
                jurisdiction.coverage_reviewed_ids
                - _string_set(coverage.get("patents_missing_claims"))
            ),
        ),
        (
            "patents_with_family",
            len(
                jurisdiction.coverage_reviewed_ids
                - _string_set(coverage.get("patents_missing_family_context"))
            ),
        ),
        (
            "us_patents_with_prosecution_context",
            len(
                jurisdiction.reviewed_us_ids
                - _string_set(coverage.get("us_patents_missing_prosecution_context"))
            ),
        ),
        (
            "us_patents_with_file_wrapper_dossier",
            len(
                jurisdiction.reviewed_us_ids
                - _string_set(coverage.get("us_patents_missing_file_wrapper_dossier"))
            ),
        ),
        (
            "ep_patents_with_register_context",
            len(
                jurisdiction.reviewed_ep_ids
                - _string_set(coverage.get("ep_patents_missing_register_context"))
            ),
        ),
    )
    for field_name, expected_count in derived_counts:
        if _normalize_int(audit.get(field_name), -1) != expected_count:
            raise ValueError(f"decision_audit {field_name} does not match coverage")


def _analysis_failure_ids(report_data: Mapping[str, Any]) -> set[str]:
    failure_ids: set[str] = set()
    for item in _list_value(report_data.get("analysis_failures")):
        if not isinstance(item, Mapping):
            raise ValueError("analysis_failures contains a non-object entry")
        patent_id = str(item.get("patent_id") or "").strip()
        if not patent_id:
            raise ValueError("analysis_failures patent_id is required")
        failure_ids.add(patent_id)
    return failure_ids


def _validate_analysis_funnel_parity(
    report_data: Mapping[str, Any],
    audit: Mapping[str, Any],
    coverage: Mapping[str, Any],
    risk_summary: Mapping[str, Any],
    *,
    analysis_ids: set[str],
) -> int:
    derived_claim_patent_ids = {
        canonical_publication_id(str(item.get("patent_id") or "").strip())
        for item in _list_value(report_data.get("claim_program_decisions"))
        if isinstance(item, Mapping) and str(item.get("patent_id") or "").strip()
    }
    analysis_count = len(analysis_ids or derived_claim_patent_ids)
    if _normalize_int(risk_summary.get("total_patents_analyzed"), -1) != analysis_count:
        raise ValueError("risk_summary total_patents_analyzed does not match patent analyses")

    audit_trail = _dict_value(report_data.get("audit_trail"))
    total_found = _normalize_int(report_data.get("total_patents_found"), -1)
    after_triage = _normalize_int(report_data.get("patents_after_triage"), -1)
    discovered = _normalize_int(audit_trail.get("total_patents_discovered"), -1)
    after_hard_filter = _normalize_int(audit_trail.get("patents_after_hard_filter"), -1)
    after_ranking = _normalize_int(audit_trail.get("patents_after_ranking"), -1)
    audit_after_triage = _normalize_int(audit_trail.get("patents_after_triage"), -1)
    audit_analyzed = _normalize_int(audit_trail.get("patents_analyzed"), -1)
    if total_found != discovered:
        raise ValueError("total_patents_found does not match audit trail discovery count")
    if after_triage != audit_after_triage:
        raise ValueError("patents_after_triage does not match audit trail")
    if audit_analyzed != analysis_count:
        raise ValueError("audit trail patents_analyzed does not match patent analyses")
    report_failure_ids = _analysis_failure_ids(report_data)
    if report_failure_ids & analysis_ids:
        raise ValueError("analysis failures overlap completed patent analyses")
    if after_triage != analysis_count + len(report_failure_ids):
        raise ValueError("patents_after_triage does not match analyses plus failures")
    if not (
        total_found >= after_hard_filter >= after_ranking >= after_triage >= analysis_count >= 0
    ):
        raise ValueError("search funnel counts are not monotonic")
    if _string_set(audit.get("failed_sources")) != _string_set(coverage.get("failed_source_names")):
        raise ValueError("decision_audit failed_sources does not match coverage")
    if report_failure_ids != _string_set(coverage.get("failed_analysis_patent_ids")):
        raise ValueError("decision_audit analysis failures do not match report failures")
    source_health = _dict_value(report_data.get("source_health"))
    report_failed_sources = {
        str(item.get("source") or "").strip()
        for item in _list_value(source_health.get("entries"))
        if isinstance(item, Mapping)
        and _decision_value(item.get("status")) == "failed"
        and str(item.get("source") or "").strip()
    }
    if report_failed_sources != _string_set(audit.get("failed_sources")):
        raise ValueError("decision_audit failed_sources does not match source health")
    return analysis_count


def _validate_risk_summary_parity(
    risk_summary: Mapping[str, Any],
    *,
    decision: str,
    blocking_patent_ids: set[str],
) -> int:
    governed_risk = {"clear": "clear", "unclear": "medium", "blocked": "high"}[decision]
    if _decision_value(risk_summary.get("overall_risk")) != governed_risk:
        raise ValueError("risk_summary overall_risk does not match clearance_decision")
    blocker_count = len(blocking_patent_ids)
    if _normalize_int(risk_summary.get("blocking_patents_count"), -1) != blocker_count:
        raise ValueError("risk_summary blocking_patents_count does not match blocker IDs")
    analyzed_count = _normalize_int(risk_summary.get("total_patents_analyzed"), -1)
    if analyzed_count < 0:
        raise ValueError("risk_summary total_patents_analyzed is invalid")
    expected_summary = _governed_executive_summary(
        decision=decision,
        blocker_count=blocker_count,
        analyzed_count=analyzed_count,
    )
    if str(risk_summary.get("executive_summary") or "").strip() != expected_summary:
        raise ValueError("risk_summary executive_summary is not the governed summary")
    return blocker_count


def _has_unresolved_audit_signals(
    audit: Mapping[str, Any],
    coverage: Mapping[str, Any],
    claim_program: Mapping[str, Any],
) -> bool:
    return bool(
        _non_empty_strings(audit.get("failed_sources"))
        or _non_empty_strings(audit.get("insufficiency_reasons"))
        or _non_empty_strings(audit.get("evidence_warnings"))
        or _normalize_int(audit.get("analysis_failures_count"))
        or _normalize_int(audit.get("incomplete_material_patents"))
        or _normalize_int(audit.get("incomplete_material_families"))
        or _non_empty_strings(coverage.get("verification_gaps"))
        or _non_empty_strings(coverage.get("patents_missing_claims"))
        or _non_empty_strings(coverage.get("patents_missing_claim_level_analysis"))
        or _non_empty_strings(coverage.get("patents_missing_authoritative_records"))
        or _non_empty_strings(coverage.get("patents_missing_family_context"))
        or _non_empty_strings(coverage.get("failed_analysis_patent_ids"))
        or _non_empty_strings(claim_program.get("claims_with_insufficient_evidence"))
    )


def _validate_evidence_sufficiency_and_rollup(
    report_data: Mapping[str, Any],
    audit: Mapping[str, Any],
    coverage: Mapping[str, Any],
    claim_program: Mapping[str, Any],
    jurisdiction_decisions: list[Mapping[str, Any]],
    jurisdiction: _JurisdictionParity,
    *,
    decision: str,
) -> tuple[bool, bool]:
    unresolved_signals = _has_unresolved_audit_signals(audit, coverage, claim_program)
    evidence_sufficient = audit.get("evidence_sufficient_for_clearance") is True
    if evidence_sufficient and unresolved_signals:
        raise ValueError("decision_audit evidence sufficiency contradicts unresolved signals")
    if (
        evidence_sufficient
        and _string_set(coverage.get("clearance_grade_ready_patent_ids"))
        != jurisdiction.coverage_reviewed_ids
    ):
        raise ValueError("decision_audit evidence sufficiency contradicts clearance-ready patents")
    if evidence_sufficient and any(
        item.get("evidence_sufficient_for_clearance") is not True
        for item in jurisdiction_decisions
        if _non_empty_strings(item.get("reviewed_patent_ids"))
    ):
        raise ValueError("decision_audit evidence sufficiency contradicts jurisdiction evidence")

    if any(outcome == "blocked" for outcome in jurisdiction.material_outcomes):
        expected_decision = "blocked"
    elif evidence_sufficient and (
        (
            jurisdiction.material_outcomes
            and all(outcome == "clear" for outcome in jurisdiction.material_outcomes)
        )
        or _has_true_zero_patent_clear(report_data)
    ):
        expected_decision = "clear"
    else:
        expected_decision = "unclear"
    if decision != expected_decision:
        raise ValueError("clearance_decision does not match jurisdiction decision rollup")
    return unresolved_signals, evidence_sufficient


def _require_lower_hex(value: str, *, length: int, message: str) -> None:
    if len(value) != length or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(message)


def _certification_identity(certification_scope: Mapping[str, Any]) -> _CertificationIdentity:
    receipt_id = str(certification_scope.get("evidence_receipt_id") or "").strip()
    receipt_sha = str(certification_scope.get("evidence_receipt_sha256") or "").strip()
    pipeline_sha = str(certification_scope.get("evidence_pipeline_git_sha") or "").strip()
    source_tree_sha = str(certification_scope.get("evidence_source_tree_sha256") or "").strip()
    if not receipt_id:
        raise ValueError("clearance_decision clear requires a certification receipt id")
    required_ids: dict[str, str] = {}
    for field_name in (
        "evidence_issuer_verifier_id",
        "evidence_key_id",
        "evidence_gate_run_id",
    ):
        required_ids[field_name] = str(certification_scope.get(field_name) or "").strip()
        if not required_ids[field_name]:
            raise ValueError(f"clearance_decision clear requires certification {field_name}")
    scope_lane_ids = set(_non_empty_strings(certification_scope.get("verified_lane_ids")))
    if not scope_lane_ids:
        raise ValueError("clearance_decision clear requires an atomically verified lane")
    aggregate_sha = str(
        certification_scope.get("evidence_benchmark_aggregate_sha256") or ""
    ).strip()
    _require_lower_hex(
        aggregate_sha,
        length=64,
        message="clearance_decision clear certification aggregate hash is invalid",
    )
    _require_lower_hex(
        receipt_sha,
        length=64,
        message="clearance_decision clear certification receipt hash is invalid",
    )
    _require_lower_hex(
        pipeline_sha,
        length=40,
        message="clearance_decision clear certification pipeline SHA is invalid",
    )
    _require_lower_hex(
        source_tree_sha,
        length=64,
        message="clearance_decision clear certification source-tree hash is invalid",
    )
    receipt_dsse = str(certification_scope.get("evidence_receipt_dsse") or "").strip()
    if not receipt_dsse:
        raise ValueError("clearance_decision clear requires an embedded DSSE receipt")
    return _CertificationIdentity(
        receipt_id=receipt_id,
        receipt_sha=receipt_sha,
        pipeline_sha=pipeline_sha,
        source_tree_sha=source_tree_sha,
        issuer_verifier_id=required_ids["evidence_issuer_verifier_id"],
        key_id=required_ids["evidence_key_id"],
        gate_run_id=required_ids["evidence_gate_run_id"],
        aggregate_sha=aggregate_sha,
        scope_lane_ids=scope_lane_ids,
        receipt_dsse=receipt_dsse,
    )


def _validate_certification_receipt(identity: _CertificationIdentity) -> None:
    access_receipt = verify_certification_receipt(
        get_settings(),
        receipt_json=identity.receipt_dsse,
        subject_verification="signed_receipt",
    )
    if not access_receipt.verified:
        raise ValueError(
            "clearance_decision clear certification receipt is not currently valid: "
            + ", ".join(access_receipt.failures)
        )
    receipt_lane_ids = {lane.lane_id for lane in access_receipt.certified_lanes}
    if (
        access_receipt.receipt_id != identity.receipt_id
        or access_receipt.receipt_sha256 != identity.receipt_sha
        or access_receipt.pipeline_git_sha != identity.pipeline_sha
        or access_receipt.source_tree_sha256 != identity.source_tree_sha
        or access_receipt.issuer_verifier_id != identity.issuer_verifier_id
        or access_receipt.key_id != identity.key_id
        or access_receipt.gate_run_id != identity.gate_run_id
        or access_receipt.benchmark_aggregate_sha256 != identity.aggregate_sha
        or not identity.scope_lane_ids
        or not identity.scope_lane_ids <= receipt_lane_ids
    ):
        raise ValueError(
            "clearance_decision clear certification scope does not match its DSSE receipt"
        )


def _validate_certification_expiry(certification_scope: Mapping[str, Any]) -> None:
    try:
        evidence_expires_at = datetime.fromisoformat(
            str(certification_scope.get("evidence_expires_at") or "").replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError("clearance_decision clear certification expiry is invalid") from exc
    if (
        evidence_expires_at.tzinfo is None
        or evidence_expires_at.utcoffset() is None
        or evidence_expires_at.astimezone(UTC) <= datetime.now(UTC)
    ):
        raise ValueError("clearance_decision clear certification evidence is expired")


def _validate_clear_decision_scope(
    report_data: Mapping[str, Any],
    reviewed_by_jurisdiction: Mapping[str, set[str]],
    *,
    analysis_id: str | None,
    org_id: str | None,
) -> None:
    if (analysis_id is None) != (org_id is None):
        raise ValueError("clearance_decision clear requires complete report owner context")
    decision_scope = _dict_value(report_data.get("decision_scope"))
    supporting_scope = _dict_value(report_data.get("supporting_scope"))
    certification_scope = _dict_value(report_data.get("certification_scope"))
    decision_jurisdictions = _string_set(decision_scope.get("jurisdictions"))
    supporting_jurisdictions = _string_set(supporting_scope.get("jurisdictions"))
    certified_jurisdictions = _string_set(certification_scope.get("certified_jurisdictions"))
    if _decision_value(report_data.get("cohort_status")) != "certified":
        raise ValueError("clearance_decision clear requires a certified cohort")
    if decision_scope.get("supports_positive_clearance") is not True:
        raise ValueError("clearance_decision clear exceeds decision scope")
    if certification_scope.get("current_matter_type_certified") is not True:
        raise ValueError("clearance_decision clear requires a certified matter type")
    if certification_scope.get("evidence_verified") is not True:
        raise ValueError(
            "clearance_decision clear requires verified release certification evidence"
        )
    if certification_scope.get("evidence_verification_status") != "valid":
        raise ValueError("clearance_decision clear requires valid certification status")
    if _non_empty_strings(certification_scope.get("evidence_failures")):
        raise ValueError("clearance_decision clear has certification evidence failures")
    identity = _certification_identity(certification_scope)
    _validate_certification_receipt(identity)
    _validate_certification_expiry(certification_scope)
    if certification_scope.get("attorney_supervision_required") is True:
        raise ValueError("clearance_decision clear requires unresolved attorney supervision")
    material_jurisdictions = set(reviewed_by_jurisdiction)
    if not material_jurisdictions <= decision_jurisdictions:
        raise ValueError("clearance_decision clear exceeds decision jurisdictions")
    if not material_jurisdictions <= certified_jurisdictions:
        raise ValueError("clearance_decision clear exceeds certified jurisdictions")
    if material_jurisdictions & supporting_jurisdictions:
        raise ValueError("clearance_decision clear includes supporting-only jurisdictions")


def _validate_clear_decision_signals(
    risk_summary: Mapping[str, Any],
    risk: _ClaimRiskParity,
    *,
    unresolved_audit_signals: bool,
    audit_evidence_sufficient: bool,
) -> None:
    if (
        unresolved_audit_signals
        or risk.blocking_patent_ids
        or risk.contested_patent_ids
        or risk.medium_risk_patent_ids
        or not audit_evidence_sufficient
        or _non_empty_strings(risk_summary.get("key_risks"))
    ):
        raise ValueError("clearance_decision clear has unresolved, medium, or blocking signals")


def _validate_report_binding(
    report_data: Mapping[str, Any],
    *,
    analysis_id: str | None,
    org_id: str | None,
) -> None:
    if (analysis_id is None) != (org_id is None):
        raise ValueError("report certification binding requires both analysis and organization IDs")
    report_binding_failures = verify_report_certification_binding(
        report_data,
        keyring=ReportCertificationVerificationKeyRing.from_json(
            get_settings().report_certification_public_keyring
        ),
        expected_analysis_id=analysis_id,
        expected_org_id=org_id,
    )
    if report_binding_failures:
        raise ValueError(
            "report certification binding is invalid: " + ", ".join(report_binding_failures)
        )


def _validate_governed_blocker_surfaces(
    report_data: Mapping[str, Any],
    *,
    blocking_patent_ids: set[str],
) -> None:
    blocker_reference_ids = {
        str(reference.get("patent_id") or "").strip()
        for reference in _decisive_references(report_data)
        if _decision_value(reference.get("category")) == "blocking_patent"
        and str(reference.get("patent_id") or "").strip()
    }
    if blocker_reference_ids != blocking_patent_ids:
        raise ValueError("decision_audit decisive blocker references do not match blocker IDs")
    commercial_exposure = _require_mapping_field(report_data, "commercial_exposure")
    _validate_commercial_exposure(
        commercial_exposure,
        blocking_patent_ids=blocking_patent_ids,
    )


def _validate_matter_store_parity(
    report_data: Mapping[str, Any],
    matter_store: Mapping[str, Any],
) -> None:
    canonical_programs = _claim_program_parity_projection(
        report_data.get("claim_program_decisions")
    )
    matter_store_programs = matter_store.get("claim_program_decisions")
    if not isinstance(matter_store_programs, list):
        raise ValueError("matter_store claim-program decisions are required")
    if _claim_program_parity_projection(matter_store_programs) != canonical_programs:
        raise ValueError("matter_store claim-program decisions do not match canonical decisions")

    matter_evidence_index = _require_mapping_field(report_data, "matter_evidence_index")
    matter_store_evidence_index = _require_mapping_field(
        matter_store,
        "matter_evidence_index",
        context="matter_store",
    )
    if matter_store_evidence_index != matter_evidence_index:
        raise ValueError("matter_store evidence index does not match canonical evidence index")
    record_completeness = _require_mapping_field(report_data, "record_completeness")
    matter_store_completeness = _require_mapping_field(
        matter_store,
        "record_completeness",
        context="matter_store",
    )
    if matter_store_completeness != record_completeness:
        raise ValueError("matter_store record_completeness does not match canonical completeness")
    authority_coverage = _require_mapping_field(report_data, "authority_coverage")
    _validate_authority_coverage_parity(
        authority_coverage,
        matter_evidence_index,
        record_completeness,
    )
    matter_store_authority = _require_mapping_field(
        matter_store,
        "authority_coverage",
        context="matter_store",
    )
    if matter_store_authority != authority_coverage:
        raise ValueError("matter_store authority_coverage does not match canonical coverage")
    _validate_authority_coverage_parity(
        matter_store_authority,
        matter_evidence_index,
        record_completeness,
    )


def validate_report_semantic_parity(
    report_data: Mapping[str, Any],
    *,
    analysis_id: str | None = None,
    org_id: str | None = None,
) -> dict[str, int | str]:
    """Reject drift between the governed decision and every published summary surface."""
    decision, audit, coverage, claim_program, risk_summary, jurisdiction_decisions = (
        _semantic_parity_inputs(report_data)
    )
    blocking_patent_ids, contested_patent_ids, medium_risk_patent_ids = _claim_program_risk_sets(
        report_data, claim_program
    )
    matter_store = _require_mapping_field(report_data, "matter_store")
    risk = _validate_patent_and_claim_risk_parity(
        report_data,
        claim_program,
        blocking_patent_ids=blocking_patent_ids,
        contested_patent_ids=contested_patent_ids,
        medium_risk_patent_ids=medium_risk_patent_ids,
    )

    jurisdiction = _validate_jurisdiction_parity(
        jurisdiction_decisions,
        coverage,
        blocking_patent_ids=blocking_patent_ids,
    )
    _validate_audit_coverage_counts(audit, coverage, jurisdiction)
    _validate_analysis_funnel_parity(
        report_data,
        audit,
        coverage,
        risk_summary,
        analysis_ids=risk.analysis_ids,
    )
    blocker_count = _validate_risk_summary_parity(
        risk_summary,
        decision=decision,
        blocking_patent_ids=blocking_patent_ids,
    )

    unresolved_audit_signals, audit_evidence_sufficient = _validate_evidence_sufficiency_and_rollup(
        report_data,
        audit,
        coverage,
        claim_program,
        jurisdiction_decisions,
        jurisdiction,
        decision=decision,
    )
    if decision == "clear":
        _validate_clear_decision_scope(
            report_data,
            jurisdiction.reviewed_by_jurisdiction,
            analysis_id=analysis_id,
            org_id=org_id,
        )
        _validate_clear_decision_signals(
            risk_summary,
            risk,
            unresolved_audit_signals=unresolved_audit_signals,
            audit_evidence_sufficient=audit_evidence_sufficient,
        )
    if decision == "clear" or analysis_id is not None or org_id is not None:
        _validate_report_binding(
            report_data,
            analysis_id=analysis_id,
            org_id=org_id,
        )
    if decision == "blocked" and not blocking_patent_ids:
        raise ValueError("clearance_decision blocked has zero blockers")
    _validate_governed_blocker_surfaces(
        report_data,
        blocking_patent_ids=blocking_patent_ids,
    )
    _validate_matter_store_parity(report_data, matter_store)

    return {
        "decision": decision,
        "blocking_patent_count": blocker_count,
        "jurisdiction_decision_count": len(jurisdiction_decisions),
    }


def validate_report_publishability(
    report_data: Mapping[str, Any],
    *,
    analysis_id: str | None = None,
    org_id: str | None = None,
) -> dict[str, int | float | str]:
    """Validate that a completed report is safe to serve or export."""
    try:
        MatterEvidenceIndexResponse.model_validate(report_data.get("matter_evidence_index"))
        RecordCompletenessResponse.model_validate(report_data.get("record_completeness"))
        MatterStoreResponse.model_validate(report_data.get("matter_store"))
    except ValidationError as exc:
        raise ValueError("report evidence substrate failed schema validation") from exc
    source_span_summary = validate_report_source_span_provenance(report_data)
    material_assertion_summary = validate_material_report_assertion_provenance(report_data)
    semantic_summary = validate_report_semantic_parity(
        report_data,
        analysis_id=analysis_id,
        org_id=org_id,
    )
    verification = _verification_dict(report_data)
    verification_summary = _verification_summary_dict(report_data)

    checks = verification.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("report verification checks are required")
    failed_checks = [
        check
        for check in checks
        if not isinstance(check, Mapping) or check.get("passed") is not True
    ]
    if failed_checks:
        raise ValueError("report verification contains failed checks")

    for boolean_field in (
        "all_citations_valid",
        "all_claims_grounded",
        "all_entities_valid",
        "dates_consistent",
        "risk_levels_justified",
    ):
        if verification.get(boolean_field) is not True:
            raise ValueError(f"report verification {boolean_field} must be true")

    issues = verification.get("issues")
    if issues not in (None, []):
        raise ValueError("report verification issues must be empty")

    claim_counts: dict[str, int] = {}
    for field_name in (
        "total_claims_checked",
        "claims_correct",
        "claims_incorrect",
        "claims_unverifiable",
    ):
        value = verification_summary.get(field_name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(
                f"report verification_summary {field_name} must be a non-negative integer"
            )
        claim_counts[field_name] = value

    total_claims_checked = claim_counts["total_claims_checked"]
    claims_correct = claim_counts["claims_correct"]
    claims_incorrect = claim_counts["claims_incorrect"]
    claims_unverifiable = claim_counts["claims_unverifiable"]
    categorized_claims = claims_correct + claims_incorrect + claims_unverifiable
    if categorized_claims != total_claims_checked:
        raise ValueError(
            "report verification_summary categorized claim counts must equal total_claims_checked"
        )

    accuracy_value = verification_summary.get("factual_accuracy_rate")
    if not isinstance(accuracy_value, int | float) or isinstance(accuracy_value, bool):
        raise ValueError("report verification_summary factual_accuracy_rate must be numeric")
    accuracy = float(accuracy_value)
    if not math.isfinite(accuracy) or not 0.0 <= accuracy <= 1.0:
        raise ValueError(
            "report verification_summary factual_accuracy_rate must be finite and between 0 and 1"
        )
    expected_accuracy = claims_correct / total_claims_checked if total_claims_checked else 0.0
    if abs(accuracy - expected_accuracy) > 0.001:
        raise ValueError(
            "report verification_summary factual_accuracy_rate does not match claim counts"
        )

    if claims_incorrect != 0:
        raise ValueError("report verification_summary claims_incorrect must be 0")

    if claims_unverifiable != 0:
        raise ValueError("report verification_summary claims_unverifiable must be 0")

    corrections_needed = verification_summary.get("corrections_needed")
    if corrections_needed not in (None, []):
        raise ValueError("report verification_summary corrections_needed must be empty")

    if _has_report_claims(report_data) and total_claims_checked <= 0:
        raise ValueError("report verification_summary total_claims_checked must be positive")
    if accuracy < MIN_VERIFICATION_ACCURACY:
        raise ValueError("report verification_summary factual_accuracy_rate is below threshold")

    assessment = str(verification_summary.get("overall_assessment") or "").strip().upper()
    if assessment not in PASSING_VERIFICATION_ASSESSMENTS:
        raise ValueError("report verification_summary overall_assessment is not publishable")
    derived_assessment = (
        "ERROR"
        if total_claims_checked == 0
        else ("FAIL" if claims_incorrect or claims_unverifiable or corrections_needed else "PASS")
    )
    if derived_assessment not in PASSING_VERIFICATION_ASSESSMENTS:
        raise ValueError(
            "report verification_summary independently derived assessment is not publishable"
        )

    return {
        **source_span_summary,
        **material_assertion_summary,
        **semantic_summary,
        "verification_check_count": len(checks),
        "factual_accuracy_rate": accuracy,
        "overall_assessment": assessment,
    }


def require_report_publishability(
    report_data: Mapping[str, Any],
    *,
    analysis_id: str | None = None,
    org_id: str | None = None,
    status_code: int = 404,
    title: str = "Not Found",
    detail: str = "Report not yet available",
) -> None:
    try:
        validate_report_publishability(
            report_data,
            analysis_id=analysis_id,
            org_id=org_id,
        )
    except ValueError as exc:
        raise APIError(status_code, title, detail) from exc


def require_completed_report_payload(
    analysis: object,
    *,
    status_code: int = 404,
    title: str = "Not Found",
    detail: str = "Report not yet available",
) -> dict[str, Any]:
    if analysis_status_value(getattr(analysis, "status", None)) != AnalysisStatus.COMPLETED.value:
        raise APIError(status_code, title, detail)

    report_data = getattr(analysis, "report_data", None)
    if not isinstance(report_data, dict) or not report_data:
        raise APIError(status_code, title, detail)
    require_report_publishability(
        report_data,
        analysis_id=str(getattr(analysis, "id", "") or ""),
        org_id=str(getattr(analysis, "org_id", "") or ""),
        status_code=status_code,
        title=title,
        detail=detail,
    )

    return report_data


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _normalize_int(value: object, fallback: object = 0) -> int:
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError):
        try:
            return int(cast(Any, fallback))
        except (TypeError, ValueError):
            return 0


def build_governed_report_summary(
    analysis: object,
    *,
    risk_ratings_restricted: bool = False,
    summary_status_code: int = 500,
    summary_title: str = "Internal Server Error",
    summary_detail: str = "Report summary failed schema validation - contact support",
) -> dict[str, Any]:
    """Build customer-visible summary fields from the governed report payload."""
    report_data = require_completed_report_payload(analysis)
    try:
        risk_summary = RiskSummaryResponse.model_validate(report_data.get("risk_summary"))
    except ValidationError as exc:
        raise APIError(summary_status_code, summary_title, summary_detail) from exc

    decision = _decision_value(_dict_value(report_data.get("clearance_decision")).get("decision"))
    governed_risk = {
        "clear": "clear",
        "unclear": "medium",
        "blocked": "high",
    }.get(decision)
    if governed_risk is None:
        raise APIError(summary_status_code, summary_title, summary_detail)
    claim_program = _dict_value(
        _dict_value(_dict_value(report_data.get("clearance_decision")).get("decision_audit")).get(
            "claim_program_summary"
        )
    )
    blocking_count = len(_non_empty_strings(claim_program.get("blocking_patent_ids")))
    analyzed_count = risk_summary.total_patents_analyzed

    if risk_ratings_restricted:
        return {
            "overall_risk": None,
            "blocking_patents_count": None,
            "total_patents_found": _normalize_int(
                report_data.get("total_patents_found"),
                risk_summary.total_patents_analyzed,
            ),
            "executive_summary": RISK_RESTRICTION_SUMMARY,
            "risk_ratings_restricted": True,
        }

    return {
        "overall_risk": governed_risk,
        "blocking_patents_count": blocking_count,
        "total_patents_found": _normalize_int(
            report_data.get("total_patents_found"),
            risk_summary.total_patents_analyzed,
        ),
        "executive_summary": (
            f"Clearance decision: {decision.upper()}. {blocking_count} blocking "
            f"patent{'s' if blocking_count != 1 else ''} identified from "
            f"{analyzed_count} analyzed."
        ),
        "risk_ratings_restricted": False,
    }
