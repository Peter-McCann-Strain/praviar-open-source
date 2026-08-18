"""Public shared-report access helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from ipaddress import ip_address
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

from api.services.report_access import (
    build_governed_report_summary,
    require_completed_report_payload,
)

PUBLIC_RISK_LEVELS = {"high", "medium", "low", "clear"}
PUBLIC_KEY_PATENT_LIMIT = 3
PUBLIC_EVIDENCE_LIMITATION_LIMIT = 6
PUBLIC_SOURCE_LABELS = {
    "patentsview": "PatentsView",
    "pubchem_sdq": "PubChem SDQ",
    "bigquery": "Google patent datasets",
    "google_patents": "Google Patents",
    "google_patents_public_datasets": "Google patent datasets",
    "epo_ops": "EPO OPS",
    "uspto": "USPTO",
}
PUBLIC_EVIDENCE_HOSTS = frozenset(
    {
        "patents.google.com",
        "worldwide.espacenet.com",
        "register.epo.org",
        "patentscope.wipo.int",
        "patentcenter.uspto.gov",
        "ppubs.uspto.gov",
    }
)
PUBLIC_STANDARD_LIMITATIONS = [
    "Markush and generic claim coverage may require manual claim construction.",
    "Prosecution history, patent-term, and register status should be verified before reliance.",
    "Prior-art exhaustiveness and validity opinions are outside this shared screening artifact.",
    "Confidence bands describe available evidence quality, not a legal clearance opinion.",
]
PATENT_REFERENCE_PATTERN = re.compile(r"^[A-Z]{1,4}[-A-Z0-9]{3,40}$", re.IGNORECASE)
SENSITIVE_DIAGNOSTIC_PATTERN = re.compile(
    r"(postgres(?:ql)?://|sk_(?:live|test)_|prv_live_|bearer\s+|select\s+.+\s+from\s+|"
    r"traceback|/users/|/var/|/tmp/|\\|praviar-prod|bigquery\s+dataset)",
    re.IGNORECASE | re.DOTALL,
)


def build_shared_report_payload(analysis) -> dict:
    """Build the public response shape for a shared report."""
    report_data = require_completed_report_payload(
        analysis,
        status_code=410,
        title="Gone",
        detail="Shared report is unavailable",
    )
    summary = build_governed_report_summary(
        analysis,
        summary_status_code=410,
        summary_title="Gone",
        summary_detail="Shared report is unavailable",
    )
    share_expires_at = analysis.__dict__.get("_share_expires_at")
    recipient_email = analysis.__dict__.get("_share_recipient_email")
    view_number = analysis.__dict__.get("_share_view_number")
    access_expires_at = analysis.__dict__.get("_share_access_expires_at")
    share_id = analysis.__dict__.get("_share_id")
    report_fingerprint = analysis.__dict__.get("_share_report_fingerprint")
    if (
        not recipient_email
        or not isinstance(view_number, int)
        or access_expires_at is None
        or not share_id
        or not report_fingerprint
    ):
        raise RuntimeError("Verified recipient attribution is missing")
    report_id = _text(report_data.get("report_id")) or str(analysis.id)
    source_snapshot_at = _text(report_data.get("source_snapshot_at"))
    pipeline_version = _text(report_data.get("praviar_pipeline_version"))
    model_versions = sorted(
        {
            text
            for value in _mapping(report_data.get("llm_models_used")).values()
            if (text := _text(value))
        }
    )
    key_patents = _shared_key_patents(report_data, summary["overall_risk"])
    evidence_limitations = _shared_evidence_limitations(report_data)
    total_material_patents = _shared_total_material_patents(report_data)
    return {
        "compound_name": analysis.compound_name or "",
        "report_id": report_id,
        "share_id": str(share_id),
        "packet_version": "recipient-bound-share-v2",
        "source_snapshot_at": source_snapshot_at,
        "pipeline_version": pipeline_version,
        "model_version": ", ".join(model_versions)[:240],
        "integrity_digest": str(report_fingerprint),
        "overall_risk": summary["overall_risk"] or "",
        "blocking_patents_count": summary["blocking_patents_count"],
        "total_patents_found": summary["total_patents_found"],
        "executive_summary": summary["executive_summary"],
        "key_findings": _shared_key_findings(report_data),
        "generated_at": _report_generated_at(report_data, analysis),
        "key_patents": key_patents,
        "source_coverage": _shared_source_coverage(report_data),
        "jurisdiction_scope": _shared_jurisdiction_scope(report_data),
        "evidence_limitations": evidence_limitations,
        "integrity_summary": _shared_integrity_summary(report_data),
        "total_material_patents": total_material_patents,
        "omitted_key_patents_count": max(total_material_patents - len(key_patents), 0),
        "omitted_limitations_count": max(
            len(_shared_evidence_limitation_candidates(report_data)) - len(evidence_limitations),
            0,
        ),
        "standard_limitations": PUBLIC_STANDARD_LIMITATIONS,
        "intended_use": (
            "Read-only external FTO screening packet for qualified patent counsel review."
        ),
        "ai_system_notice": (
            "AI-assisted patent landscape analysis; outputs require human review before reliance."
        ),
        "reliance_boundary": "Not a legal clearance opinion or freedom-to-operate opinion.",
        "review_status": _shared_review_status(analysis),
        "share_expires_at": share_expires_at.isoformat() if share_expires_at else "",
        "verified_recipient_email": recipient_email,
        "attributable_view_number": view_number,
        "verified_session_expires_at": access_expires_at.isoformat(),
    }


def _text(value: object) -> str:
    return str(value or "").strip()


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _strings(value: object) -> list[str]:
    items = value if isinstance(value, list) else [value]
    return [text for item in items if (text := _text(item))]


def _non_negative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _risk(value: object, fallback: object = "") -> str:
    risk = _text(value).lower()
    fallback_risk = _text(fallback).lower()
    if risk in PUBLIC_RISK_LEVELS:
        return risk
    if fallback_risk in PUBLIC_RISK_LEVELS:
        return fallback_risk
    return "medium"


def _first_text(*values: object) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _report_generated_at(report_data: Mapping[str, Any], analysis) -> str:
    generated_at = _text(report_data.get("generated_at"))
    if generated_at:
        return generated_at
    updated_at = getattr(analysis, "updated_at", None)
    return updated_at.isoformat() if updated_at else ""


def _shared_key_findings(report_data: Mapping[str, Any]) -> list[str]:
    risk_summary = _mapping(report_data.get("risk_summary"))
    key_risks = _strings(risk_summary.get("key_risks"))
    if key_risks:
        return key_risks[:4]

    decision = _mapping(report_data.get("clearance_decision"))
    reasoning = _strings(decision.get("decision_reasoning"))
    if reasoning:
        return reasoning[:4]

    return []


def _shared_key_patents(
    report_data: Mapping[str, Any], overall_risk: object
) -> list[dict[str, str]]:
    seen: set[str] = set()
    claim_program = _claim_program_summary(report_data)
    blocking_patent_ids = {
        patent_id.upper() for patent_id in _strings(claim_program.get("blocking_patent_ids"))
    }
    medium_risk_patent_ids = {
        patent_id.upper() for patent_id in _strings(claim_program.get("medium_risk_patent_ids"))
    }
    risk_rank = {"high": 0, "medium": 1, "low": 2, "clear": 3}
    candidate_patents: list[tuple[tuple[int, int, int, int, int], dict[str, str]]] = []

    def add_candidate(
        *,
        assignee: str = "",
        expiry: str = "",
        index: int,
        is_blocking: bool = False,
        patent_number: str,
        risk_level: str,
        source_reference: str = "",
        source_rank: int,
        source_url: str = "",
    ) -> None:
        normalized_patent_number = patent_number.upper()
        if normalized_patent_number in seen:
            return
        seen.add(normalized_patent_number)
        if is_blocking or normalized_patent_number in blocking_patent_ids:
            risk_level = "high"
        elif (
            normalized_patent_number in medium_risk_patent_ids
            and risk_rank.get(risk_level, 4) > risk_rank["medium"]
        ):
            risk_level = "medium"
        explicit_blocker_rank = (
            0 if is_blocking or normalized_patent_number in blocking_patent_ids else 1
        )
        claim_program_rank = 0 if normalized_patent_number in medium_risk_patent_ids else 1
        candidate_patents.append(
            (
                (
                    explicit_blocker_rank,
                    risk_rank.get(risk_level, 4),
                    claim_program_rank,
                    source_rank,
                    index,
                ),
                {
                    "patent_number": patent_number,
                    "risk_level": risk_level,
                    "assignee": assignee,
                    "expiry": expiry,
                    "patent_url": _public_patent_url(patent_number, source_url),
                    "source_reference": _public_patent_source_reference(
                        source_reference,
                        has_patent_url=bool(_public_patent_url(patent_number, source_url)),
                    ),
                },
            )
        )

    for index, patent in enumerate(_list(report_data.get("patent_analyses"))):
        if not isinstance(patent, Mapping):
            continue
        patent_number = _first_text(
            patent.get("patent_id"),
            patent.get("id"),
            patent.get("publication_number"),
            patent.get("patent_number"),
        )
        if not patent_number:
            continue
        risk_level = _risk(patent.get("risk_level"), overall_risk)
        add_candidate(
            assignee=_first_text(patent.get("assignee"), patent.get("owner")),
            expiry=_first_text(patent.get("expiry_date"), patent.get("expiration_date")),
            index=index,
            is_blocking=patent.get("is_blocking") is True or patent.get("blocking") is True,
            patent_number=patent_number,
            risk_level=risk_level,
            source_reference=_first_text(
                patent.get("source_reference"),
                patent.get("source_name"),
                patent.get("source"),
                patent.get("data_source"),
            ),
            source_rank=0,
            source_url=_first_text(
                patent.get("patent_url"),
                patent.get("source_url"),
                patent.get("url"),
                patent.get("external_url"),
            ),
        )

    coverage = _coverage_summary(report_data)
    fallback_candidates = [
        *(
            (patent_number, "high", 1, index)
            for index, patent_number in enumerate(
                _strings(claim_program.get("blocking_patent_ids"))
            )
        ),
        *(
            (patent_number, "medium", 2, index)
            for index, patent_number in enumerate(
                _strings(claim_program.get("medium_risk_patent_ids"))
            )
        ),
        *(
            (patent_number, _risk(overall_risk), 3, index)
            for index, patent_number in enumerate(_strings(coverage.get("reviewed_patent_ids")))
        ),
    ]
    for patent_number, risk_level, source_rank, index in fallback_candidates:
        add_candidate(
            index=index,
            is_blocking=patent_number.upper() in blocking_patent_ids,
            patent_number=patent_number,
            risk_level=_risk(risk_level, overall_risk),
            source_reference="Google Patents",
            source_rank=source_rank,
        )

    return [
        patent
        for _, patent in sorted(candidate_patents, key=lambda item: item[0])[
            :PUBLIC_KEY_PATENT_LIMIT
        ]
    ]


def _coverage_summary(report_data: Mapping[str, Any]) -> Mapping[str, Any]:
    decision = _mapping(report_data.get("clearance_decision"))
    audit = _mapping(decision.get("decision_audit"))
    return _mapping(audit.get("coverage_summary"))


def _claim_program_summary(report_data: Mapping[str, Any]) -> Mapping[str, Any]:
    decision = _mapping(report_data.get("clearance_decision"))
    audit = _mapping(decision.get("decision_audit"))
    return _mapping(audit.get("claim_program_summary"))


def _shared_source_coverage(report_data: Mapping[str, Any]) -> list[str]:
    coverage = _coverage_summary(report_data)
    sources = (
        _strings(coverage.get("successful_source_names"))
        or _strings(coverage.get("queried_source_names"))
        or _strings(coverage.get("supporting_source_names"))
    )
    return _public_source_labels(sources, limit=5)


def _shared_jurisdiction_scope(report_data: Mapping[str, Any]) -> list[str]:
    decision_scope = _mapping(report_data.get("decision_scope"))
    certification_scope = _mapping(report_data.get("certification_scope"))
    jurisdictions = (
        _strings(report_data.get("target_jurisdictions"))
        or _strings(decision_scope.get("jurisdictions"))
        or _strings(certification_scope.get("certified_jurisdictions"))
    )
    if jurisdictions:
        return jurisdictions[:6]

    decisions = []
    for decision in _list(report_data.get("jurisdiction_decisions")):
        if isinstance(decision, Mapping):
            jurisdiction = _text(decision.get("jurisdiction"))
            if jurisdiction:
                decisions.append(jurisdiction)
    return decisions[:6]


def _shared_evidence_limitations(report_data: Mapping[str, Any]) -> list[str]:
    return _shared_evidence_limitation_candidates(report_data)[:PUBLIC_EVIDENCE_LIMITATION_LIMIT]


def _shared_evidence_limitation_candidates(report_data: Mapping[str, Any]) -> list[str]:
    coverage = _coverage_summary(report_data)
    decision = _mapping(report_data.get("clearance_decision"))
    audit = _mapping(decision.get("decision_audit"))
    integrity = _shared_integrity_summary(report_data)
    limitations: list[str] = []

    if integrity["metadata_inconsistent"]:
        limitations.append("Report metadata counts require verification")
    if not integrity["evidence_sufficient_for_clearance"]:
        limitations.append("Evidence coverage is screening-only until listed gaps are reviewed")
    if integrity["affected_patents_count"] > 0:
        limitations.append(
            "1 patent analysis requires review"
            if integrity["affected_patents_count"] == 1
            else f"{integrity['affected_patents_count']} patent analyses require review"
        )
    if integrity["recoverable_failures_count"] > 0:
        limitations.append(
            f"{integrity['recoverable_failures_count']} recoverable processing issue"
            f"{'' if integrity['recoverable_failures_count'] == 1 else 's'}"
        )
    if integrity["data_limitations_count"] > 0:
        limitations.append(
            f"{integrity['data_limitations_count']} data coverage limitation"
            f"{'' if integrity['data_limitations_count'] == 1 else 's'} detected"
        )
    for failed_source in _strings(coverage.get("failed_source_names")):
        source_label = _public_source_label(failed_source)
        if source_label == "Evidence source":
            limitations.append("One evidence source coverage failed")
        else:
            limitations.append(f"{source_label} source coverage failed")
    for missing_patent in _strings(coverage.get("patents_missing_claims")):
        patent_reference = _public_patent_reference(missing_patent)
        if patent_reference:
            limitations.append(f"{patent_reference} missing claim text")
        else:
            limitations.append("A material patent is missing claim text")
    for raw_gap in _strings(coverage.get("verification_gaps")):
        limitations.append(_public_limitation_category(raw_gap))
    for raw_reason in _strings(audit.get("insufficiency_reasons")):
        limitations.append(_public_limitation_category(raw_reason))
    return _unique_public_limitations(limitations)


def _shared_integrity_summary(report_data: Mapping[str, Any]) -> dict[str, int | bool]:
    coverage = _coverage_summary(report_data)
    decision = _mapping(report_data.get("clearance_decision"))
    audit = _mapping(decision.get("decision_audit"))
    analysis_failures = [
        failure
        for failure in _list(report_data.get("analysis_failures"))
        if isinstance(failure, Mapping)
    ]
    data_limitations = [
        limitation
        for limitation in _list(report_data.get("data_limitations"))
        if isinstance(limitation, Mapping)
    ]
    reported_counts = [
        count
        for count in (
            len(analysis_failures),
            _non_negative_int(audit.get("analysis_failures_count")),
            len(_strings(coverage.get("failed_analysis_patent_ids"))),
        )
        if count is not None
    ]
    affected_patents_count = max(reported_counts, default=0)
    recoverable_failures_count = sum(
        1 for failure in analysis_failures if failure.get("recoverable") is True
    )
    data_limitations_count = len(data_limitations)
    failed_sources_count = len(_strings(coverage.get("failed_source_names")))
    verification_gap_count = len(_strings(coverage.get("verification_gaps"))) + len(
        _strings(audit.get("insufficiency_reasons"))
    )
    missing_claim_count = len(_strings(coverage.get("patents_missing_claims")))
    evidence_sufficient = audit.get("evidence_sufficient_for_clearance")

    return {
        "affected_patents_count": affected_patents_count,
        "recoverable_failures_count": min(recoverable_failures_count, affected_patents_count),
        "needs_review_count": max(affected_patents_count - recoverable_failures_count, 0),
        "data_limitations_count": data_limitations_count,
        "source_caveats_count": (
            data_limitations_count
            + failed_sources_count
            + verification_gap_count
            + missing_claim_count
        ),
        "evidence_sufficient_for_clearance": evidence_sufficient is not False,
        "metadata_inconsistent": len(set(reported_counts)) > 1,
    }


def _shared_total_material_patents(report_data: Mapping[str, Any]) -> int:
    risk_summary = _mapping(report_data.get("risk_summary"))
    decision = _mapping(report_data.get("clearance_decision"))
    audit = _mapping(decision.get("decision_audit"))
    coverage = _coverage_summary(report_data)
    patent_ids = {
        patent_id
        for patent_id in (
            _first_text(
                patent.get("patent_id"),
                patent.get("id"),
                patent.get("publication_number"),
                patent.get("patent_number"),
            )
            for patent in _list(report_data.get("patent_analyses"))
            if isinstance(patent, Mapping)
        )
        if patent_id
    }
    counts = [
        len(patent_ids),
        len(_strings(coverage.get("reviewed_patent_ids"))),
        _non_negative_int(audit.get("material_patents_reviewed")),
        _non_negative_int(risk_summary.get("total_patents_analyzed")),
    ]
    return max((count for count in counts if count is not None), default=0)


def _public_source_labels(sources: list[str], *, limit: int) -> list[str]:
    labels: list[str] = []
    for source in sources:
        label = _public_source_label(source, fallback="")
        if label:
            labels.append(label)
        if len(labels) >= limit:
            break
    return _unique_public_limitations(labels)[:limit]


def _public_source_label(source: str, fallback: str = "Evidence source") -> str:
    normalized = _text(source).lower().replace("-", "_").replace(" ", "_")
    if normalized in PUBLIC_SOURCE_LABELS:
        return PUBLIC_SOURCE_LABELS[normalized]
    if not normalized:
        return fallback
    if SENSITIVE_DIAGNOSTIC_PATTERN.search(source):
        return fallback
    return fallback


def _public_patent_reference(value: str) -> str:
    candidate = _text(value)
    if PATENT_REFERENCE_PATTERN.fullmatch(candidate):
        return candidate
    return ""


def _public_patent_url(patent_number: str, source_url: str = "") -> str:
    patent_reference = _public_patent_reference(patent_number)
    if patent_reference:
        return f"https://patents.google.com/patent/{quote(patent_reference, safe='')}"
    return _https_url(source_url)


def _https_url(value: str) -> str:
    """Return one normalized public evidence URL from the explicit allowlist."""
    url = _text(value)
    if not url:
        return ""
    parsed = urlparse(url)
    try:
        hostname = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        return ""
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or hostname not in PUBLIC_EVIDENCE_HOSTS
    ):
        return ""
    try:
        ip_address(hostname)
    except ValueError:
        pass
    else:
        return ""
    return urlunparse(("https", hostname, parsed.path or "/", "", parsed.query, ""))


def _public_patent_source_reference(value: str, *, has_patent_url: bool) -> str:
    explicit_label = _public_source_label(value, fallback="")
    if explicit_label:
        return explicit_label
    return "Google Patents" if has_patent_url else ""


def _public_limitation_category(value: str) -> str:
    text = _text(value)
    lower = text.lower()
    if not text or SENSITIVE_DIAGNOSTIC_PATTERN.search(text):
        return "Evidence caveat requires counsel review"
    if "claim" in lower:
        return "Claim text or claim-level evidence requires review"
    if "prosecution" in lower or "file wrapper" in lower or "file-wrapper" in lower:
        return "Prosecution history context requires review"
    if "register" in lower or "status" in lower:
        return "Patent register/status context requires review"
    if "family" in lower:
        return "Patent family context requires review"
    if "source" in lower or "provider" in lower or "coverage" in lower:
        return "Source coverage requires review"
    return "Evidence caveat requires counsel review"


def _unique_public_limitations(limitations: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for limitation in limitations:
        cleaned = _text(limitation)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        unique.append(cleaned)
    return unique


def _shared_review_status(analysis) -> str:
    review_status = analysis.__dict__.get("_share_review_status")
    status = getattr(review_status, "status", review_status)
    return _text(getattr(status, "value", status))
