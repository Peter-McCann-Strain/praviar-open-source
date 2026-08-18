"""Source-span support map for customer-visible claim assertions."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from praviar_pipeline.models.patent import ClaimTextProvenance

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis_claims import ClaimAnalysis, ClaimElement
    from praviar_pipeline.models.analysis_patent import PatentAnalysis
    from praviar_pipeline.models.patent import PatentHit

SupportStatus = Literal["supported", "unsupported", "needs_review"]
SourceSpanKind = Literal[
    "claim_text",
    "verified_claim_text",
    "element_evidence",
    "specification_citation",
    "claim_reasoning",
]

SOURCE_SPAN_ATTESTATION_SCHEMA_VERSION = "source-span-attestation-v1"
SOURCE_SPAN_ATTESTATION_ALGORITHM = "HMAC-SHA256"
SOURCE_SPAN_ATTESTATION_DOMAIN = "praviar:verified-claim-source-span:v1"


class SourceSpanReference(BaseModel):
    """Stable reference to a report/source span used to support an assertion."""

    model_config = ConfigDict(extra="forbid")

    span_id: str
    source_type: SourceSpanKind
    patent_id: str = ""
    claim_number: int | None = None
    element_number: int | None = None
    citation: str = ""
    excerpt: str = ""
    source_document_id: str = ""
    source_name: str = ""
    source_text_sha256: str = ""
    source_retrieved_at: str = ""
    source_artifact_locator: str = ""
    collector_identity: str = ""
    collector_version: str = ""
    provenance_schema_version: str = ""
    claim_numbers: list[int] = Field(default_factory=list)
    independent_claim_numbers: list[int] = Field(default_factory=list)
    retrieval_complete: bool = False
    provenance_cassette_sha256: str = ""
    evidence_attestation_schema_version: str = ""
    evidence_attestation_algorithm: str = ""
    evidence_attestation_key_id: str = ""
    evidence_attestation_subject_id: str = ""
    evidence_attestation_hmac_sha256: str = ""


class ClaimAssertionSupport(BaseModel):
    """Support status for one customer-visible claim assertion."""

    model_config = ConfigDict(extra="forbid")

    assertion_id: str
    patent_id: str = ""
    claim_number: int | None = None
    element_number: int | None = None
    report_section: str
    assertion_text: str
    source_span_ids: list[str] = Field(default_factory=list)
    support_status: SupportStatus = "needs_review"
    customer_visible: StrictBool = True
    review_required: StrictBool = False


class ClaimSourceSpanMap(BaseModel):
    """Claim assertion support ledger emitted with every report."""

    model_config = ConfigDict(extra="forbid")

    generated_from: str = "pipeline_claim_analysis"
    entries: list[ClaimAssertionSupport] = Field(default_factory=list)
    spans: dict[str, SourceSpanReference] = Field(default_factory=dict)
    unsupported_customer_visible_claim_count: int = 0
    needs_review_count: int = 0


@dataclass(frozen=True, slots=True)
class _SourceSpanBuildContext:
    patent_details: dict[str, dict[str, Any]]
    trusted_patent_hits_by_id: dict[str, PatentHit]
    signing_enabled: bool
    evidence_attestation_key_id: str
    evidence_attestation_key: bytes | None
    evidence_attestation_subject_id: str


@dataclass(frozen=True, slots=True)
class _ElementContext:
    patent_id: str
    claim_number: int | None
    element_number: int | None
    element_text: str
    reasoning: str
    status: str


@dataclass(frozen=True, slots=True)
class _ClaimTextSupport:
    provenance: ClaimTextProvenance | None
    source_name: str
    verified: bool


class UnsupportedCustomerVisibleClaimError(RuntimeError):
    """Raised when unsupported customer-visible legal assertions would ship."""

    def __init__(self, entries: list[ClaimAssertionSupport]) -> None:
        self.assertion_ids = [entry.assertion_id for entry in entries]
        preview = ", ".join(self.assertion_ids[:5])
        if len(self.assertion_ids) > 5:
            preview += ", ..."
        super().__init__(
            "unsupported customer-visible claim assertions detected "
            f"({len(self.assertion_ids)}): {preview}"
        )


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _source_span_attestation_message(span: SourceSpanReference) -> bytes:
    payload = span.model_dump(mode="json")
    payload["evidence_attestation_hmac_sha256"] = ""
    return json.dumps(
        {
            "domain": SOURCE_SPAN_ATTESTATION_DOMAIN,
            "source_span": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def verify_source_span_attestation(
    span: SourceSpanReference,
    *,
    verification_key: bytes,
    expected_subject_id: str,
) -> bool:
    """Verify a durable receipt issued from an in-memory trusted claim cassette."""
    if (
        span.source_type != "verified_claim_text"
        or span.evidence_attestation_schema_version != SOURCE_SPAN_ATTESTATION_SCHEMA_VERSION
        or span.evidence_attestation_algorithm != SOURCE_SPAN_ATTESTATION_ALGORITHM
        or not span.evidence_attestation_key_id
        or span.evidence_attestation_subject_id != expected_subject_id
        or len(verification_key) < 32
        or len(span.evidence_attestation_hmac_sha256) != 64
    ):
        return False
    expected = hmac.new(
        verification_key,
        _source_span_attestation_message(span),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, span.evidence_attestation_hmac_sha256)


def issue_source_span_attestation(
    span: SourceSpanReference,
    *,
    signing_key: bytes,
    key_id: str,
    subject_id: str,
) -> SourceSpanReference:
    """Issue a report-bound receipt after the runtime trust boundary has passed."""
    if span.source_type != "verified_claim_text":
        raise ValueError("only verified claim-text spans may receive evidence receipts")
    if len(signing_key) < 32:
        raise ValueError("source-span attestation keys must contain at least 32 bytes")
    if not key_id or not subject_id:
        raise ValueError("source-span attestation key and subject identifiers are required")
    unsigned = span.model_copy(
        update={
            "evidence_attestation_schema_version": (SOURCE_SPAN_ATTESTATION_SCHEMA_VERSION),
            "evidence_attestation_algorithm": SOURCE_SPAN_ATTESTATION_ALGORITHM,
            "evidence_attestation_key_id": key_id,
            "evidence_attestation_subject_id": subject_id,
            "evidence_attestation_hmac_sha256": "",
        }
    )
    signature = hmac.new(
        signing_key,
        _source_span_attestation_message(unsigned),
        hashlib.sha256,
    ).hexdigest()
    return unsigned.model_copy(update={"evidence_attestation_hmac_sha256": signature})


def _add_span(
    spans: dict[str, SourceSpanReference],
    *,
    source_type: SourceSpanKind,
    patent_id: str,
    claim_number: int | None,
    element_number: int | None,
    excerpt: str,
    citation: str = "",
    source_document_id: str = "",
    source_name: str = "",
    source_text_sha256: str = "",
    source_retrieved_at: str = "",
    source_artifact_locator: str = "",
    collector_identity: str = "",
    collector_version: str = "",
    provenance_schema_version: str = "",
    claim_numbers: list[int] | None = None,
    independent_claim_numbers: list[int] | None = None,
    retrieval_complete: bool = False,
    provenance_cassette_sha256: str = "",
    evidence_attestation_key_id: str = "",
    evidence_attestation_key: bytes | None = None,
    evidence_attestation_subject_id: str = "",
) -> str:
    span_id = _stable_id(
        "span",
        source_type,
        patent_id,
        claim_number or "",
        element_number or "",
        citation,
        excerpt,
        source_document_id,
        source_name,
        source_text_sha256,
        source_retrieved_at,
        source_artifact_locator,
        collector_identity,
        collector_version,
        provenance_schema_version,
        *(claim_numbers or []),
        *(independent_claim_numbers or []),
        retrieval_complete,
        provenance_cassette_sha256,
        evidence_attestation_subject_id,
    )
    span = SourceSpanReference(
        span_id=span_id,
        source_type=source_type,
        patent_id=patent_id,
        claim_number=claim_number,
        element_number=element_number,
        citation=citation,
        excerpt=excerpt,
        source_document_id=source_document_id,
        source_name=source_name,
        source_text_sha256=source_text_sha256,
        source_retrieved_at=source_retrieved_at,
        source_artifact_locator=source_artifact_locator,
        collector_identity=collector_identity,
        collector_version=collector_version,
        provenance_schema_version=provenance_schema_version,
        claim_numbers=list(claim_numbers or []),
        independent_claim_numbers=list(independent_claim_numbers or []),
        retrieval_complete=retrieval_complete,
        provenance_cassette_sha256=provenance_cassette_sha256,
        evidence_attestation_schema_version=(
            SOURCE_SPAN_ATTESTATION_SCHEMA_VERSION if evidence_attestation_key is not None else ""
        ),
        evidence_attestation_algorithm=(
            SOURCE_SPAN_ATTESTATION_ALGORITHM if evidence_attestation_key is not None else ""
        ),
        evidence_attestation_key_id=(
            evidence_attestation_key_id if evidence_attestation_key is not None else ""
        ),
        evidence_attestation_subject_id=(
            evidence_attestation_subject_id if evidence_attestation_key is not None else ""
        ),
    )
    if evidence_attestation_key is not None:
        span = issue_source_span_attestation(
            span,
            signing_key=evidence_attestation_key,
            key_id=evidence_attestation_key_id,
            subject_id=evidence_attestation_subject_id,
        )
    spans[span_id] = span
    return span_id


def _missing_claim_coverage_entry(
    *,
    patent_id: str,
    risk_level: str,
    claim_number: int | None = None,
) -> ClaimAssertionSupport:
    assertion_id = _stable_id(
        "assertion",
        patent_id,
        claim_number or "",
        risk_level,
        "missing_claim_source_span_coverage",
    )
    claim_label = f"claim {claim_number}" if claim_number is not None else "claim analysis"
    return ClaimAssertionSupport(
        assertion_id=assertion_id,
        patent_id=patent_id,
        claim_number=claim_number,
        report_section="claim_source_span_coverage",
        assertion_text=(
            f"{risk_level.upper()} patent {patent_id or '<unknown>'} has no "
            f"source-span coverage for {claim_label}."
        ),
        source_span_ids=[],
        support_status="unsupported",
        customer_visible=True,
        review_required=True,
    )


def _trusted_patent_hits_by_id(
    trusted_patent_hits: list[Any] | None,
) -> dict[str, PatentHit]:
    return {
        str(getattr(hit, "patent_id", "") or ""): hit
        for hit in (trusted_patent_hits or [])
        if str(getattr(hit, "patent_id", "") or "")
    }


def _source_span_build_context(
    *,
    patent_details: dict[str, dict[str, Any]],
    trusted_patent_hits: list[Any] | None,
    evidence_attestation_key_id: str,
    evidence_attestation_key: bytes | None,
    evidence_attestation_subject_id: str,
) -> _SourceSpanBuildContext:
    trusted_hits_by_id = _trusted_patent_hits_by_id(trusted_patent_hits)
    signing_enabled = bool(
        evidence_attestation_key is not None
        and len(evidence_attestation_key) >= 32
        and evidence_attestation_key_id
        and evidence_attestation_subject_id
    )
    return _SourceSpanBuildContext(
        patent_details=patent_details,
        trusted_patent_hits_by_id=trusted_hits_by_id,
        signing_enabled=signing_enabled,
        evidence_attestation_key_id=evidence_attestation_key_id,
        evidence_attestation_key=evidence_attestation_key,
        evidence_attestation_subject_id=evidence_attestation_subject_id,
    )


def _element_context(
    element: ClaimElement,
    *,
    patent_id: str,
    claim_number: int | None,
) -> _ElementContext:
    return _ElementContext(
        patent_id=patent_id,
        claim_number=claim_number,
        element_number=getattr(element, "element_number", None),
        element_text=str(getattr(element, "element_text", "") or "").strip(),
        reasoning=str(getattr(element, "reasoning", "") or "").strip(),
        status=_enum_value(getattr(element, "status", "")),
    )


def _claim_text_support(
    element: _ElementContext,
    context: _SourceSpanBuildContext,
) -> _ClaimTextSupport:
    detail = context.patent_details.get(element.patent_id) or {}
    source_claims_text = str(detail.get("claims_text") or "")
    provenance_payload = detail.get("claims_text_provenance")
    try:
        provenance = ClaimTextProvenance.model_validate(provenance_payload)
    except (TypeError, ValueError):
        provenance = None
    source_name = provenance.source.value if provenance else ""
    trusted_hit = context.trusted_patent_hits_by_id.get(element.patent_id)
    runtime_provenance = getattr(
        trusted_hit,
        "claims_text_provenance",
        None,
    )
    runtime_claims_text = str(getattr(trusted_hit, "claims_text", "") or "")
    verified = bool(
        element.element_text
        and source_claims_text
        and element.element_text in source_claims_text
        and provenance
        and runtime_claims_text == source_claims_text
        and isinstance(runtime_provenance, ClaimTextProvenance)
        and runtime_provenance.model_dump(mode="json") == provenance.model_dump(mode="json")
        and runtime_provenance.supports(source_claims_text, element.patent_id)
        and context.signing_enabled
    )
    return _ClaimTextSupport(
        provenance=provenance,
        source_name=source_name,
        verified=verified,
    )


def _element_source_span_ids(
    element: _ElementContext,
    *,
    context: _SourceSpanBuildContext,
    spans: dict[str, SourceSpanReference],
) -> tuple[list[str], str]:
    support = _claim_text_support(element, context)
    source_span_ids: list[str] = []
    verified_span_id = ""
    if element.element_text:
        source_span_ids.append(
            _add_span(
                spans,
                source_type="claim_text",
                patent_id=element.patent_id,
                claim_number=element.claim_number,
                element_number=element.element_number,
                excerpt=element.element_text,
            )
        )
    if support.verified and support.provenance is not None:
        provenance = support.provenance
        verified_span_id = _add_span(
            spans,
            source_type="verified_claim_text",
            patent_id=element.patent_id,
            claim_number=element.claim_number,
            element_number=element.element_number,
            excerpt=element.element_text,
            citation=f"{element.patent_id} claim {element.claim_number}",
            source_document_id=element.patent_id,
            source_name=support.source_name,
            source_text_sha256=provenance.artifact_sha256,
            source_retrieved_at=provenance.retrieved_at.isoformat(),
            source_artifact_locator=provenance.artifact_locator,
            collector_identity=provenance.collector_identity,
            collector_version=provenance.collector_version,
            provenance_schema_version=provenance.schema_version,
            claim_numbers=list(provenance.claim_numbers),
            independent_claim_numbers=list(provenance.independent_claim_numbers),
            retrieval_complete=provenance.retrieval_complete,
            provenance_cassette_sha256=provenance.cassette_sha256,
            evidence_attestation_key_id=context.evidence_attestation_key_id,
            evidence_attestation_key=context.evidence_attestation_key,
            evidence_attestation_subject_id=context.evidence_attestation_subject_id,
        )
        source_span_ids.append(verified_span_id)
    # Model-authored evidence and citations must not be laundered into the
    # retrieved source-span ledger. Reasoning remains explicit review context.
    if element.reasoning:
        source_span_ids.append(
            _add_span(
                spans,
                source_type="claim_reasoning",
                patent_id=element.patent_id,
                claim_number=element.claim_number,
                element_number=element.element_number,
                excerpt=element.reasoning,
            )
        )
    return source_span_ids, verified_span_id


def _append_element_assertions(
    entries: list[ClaimAssertionSupport],
    *,
    element: _ElementContext,
    source_span_ids: list[str],
    verified_span_id: str,
) -> None:
    assertion_id = _stable_id(
        "assertion",
        element.patent_id,
        element.claim_number or "",
        element.element_number or "",
        element.status,
        element.element_text,
    )
    entries.append(
        ClaimAssertionSupport(
            assertion_id=assertion_id,
            patent_id=element.patent_id,
            claim_number=element.claim_number,
            element_number=element.element_number,
            report_section="claim_element_analysis",
            assertion_text=(
                f"Claim {element.claim_number} element {element.element_number} "
                f"was assessed as {element.status or 'unknown'}."
            ),
            source_span_ids=source_span_ids,
            support_status="needs_review",
            customer_visible=True,
            review_required=True,
        )
    )
    if verified_span_id:
        entries.append(
            ClaimAssertionSupport(
                assertion_id=_stable_id(
                    "assertion-source",
                    element.patent_id,
                    element.claim_number or "",
                    element.element_number or "",
                    element.element_text,
                ),
                patent_id=element.patent_id,
                claim_number=element.claim_number,
                element_number=element.element_number,
                report_section="verified_claim_text",
                assertion_text=(
                    f"Claim {element.claim_number} contains the quoted limitation "
                    f"for element {element.element_number}."
                ),
                source_span_ids=[verified_span_id],
                support_status="supported",
                customer_visible=True,
                review_required=False,
            )
        )


def _append_element_support(
    entries: list[ClaimAssertionSupport],
    spans: dict[str, SourceSpanReference],
    *,
    element: ClaimElement,
    patent_id: str,
    claim_number: int | None,
    context: _SourceSpanBuildContext,
) -> None:
    element_context = _element_context(
        element,
        patent_id=patent_id,
        claim_number=claim_number,
    )
    source_span_ids, verified_span_id = _element_source_span_ids(
        element_context,
        context=context,
        spans=spans,
    )
    _append_element_assertions(
        entries,
        element=element_context,
        source_span_ids=source_span_ids,
        verified_span_id=verified_span_id,
    )


def _append_claim_support(
    entries: list[ClaimAssertionSupport],
    spans: dict[str, SourceSpanReference],
    *,
    claim: ClaimAnalysis,
    patent_id: str,
    risk_level: str,
    high_or_medium: bool,
    context: _SourceSpanBuildContext,
) -> None:
    claim_number = getattr(claim, "claim_number", None)
    elements = list(getattr(claim, "elements", []) or [])
    if high_or_medium and not elements:
        entries.append(
            _missing_claim_coverage_entry(
                patent_id=patent_id,
                risk_level=risk_level,
                claim_number=claim_number,
            )
        )
        return
    for element in elements:
        _append_element_support(
            entries,
            spans,
            element=element,
            patent_id=patent_id,
            claim_number=claim_number,
            context=context,
        )


def _append_analysis_support(
    entries: list[ClaimAssertionSupport],
    spans: dict[str, SourceSpanReference],
    *,
    analysis: PatentAnalysis,
    context: _SourceSpanBuildContext,
) -> None:
    patent_id = str(getattr(analysis, "patent_id", "") or "")
    risk_level = _enum_value(getattr(analysis, "risk_level", ""))
    high_or_medium = risk_level in {"high", "medium"}
    claims = list(getattr(analysis, "claims_analyzed", []) or [])
    if high_or_medium and not claims:
        entries.append(
            _missing_claim_coverage_entry(
                patent_id=patent_id,
                risk_level=risk_level,
            )
        )
        return
    for claim in claims:
        _append_claim_support(
            entries,
            spans,
            claim=claim,
            patent_id=patent_id,
            risk_level=risk_level,
            high_or_medium=high_or_medium,
            context=context,
        )


def build_claim_source_span_map(
    patent_analyses: list[Any],
    patent_details: dict[str, dict[str, Any]] | None = None,
    *,
    trusted_patent_hits: list[Any] | None = None,
    evidence_attestation_key_id: str = "",
    evidence_attestation_key: bytes | None = None,
    evidence_attestation_subject_id: str = "",
) -> ClaimSourceSpanMap:
    """Build a deterministic support ledger from claim-level analyses.

    This is a structural ledger, not a substitute for counsel-reviewed source
    extraction. It makes unsupported or review-needed claim assertions explicit
    so downstream gates can fail closed instead of relying on prose inspection.
    """
    entries: list[ClaimAssertionSupport] = []
    spans: dict[str, SourceSpanReference] = {}
    patent_details = patent_details or {}
    context = _source_span_build_context(
        patent_details=patent_details,
        trusted_patent_hits=trusted_patent_hits,
        evidence_attestation_key_id=evidence_attestation_key_id,
        evidence_attestation_key=evidence_attestation_key,
        evidence_attestation_subject_id=evidence_attestation_subject_id,
    )
    for analysis in patent_analyses:
        _append_analysis_support(
            entries,
            spans,
            analysis=analysis,
            context=context,
        )

    unsupported_count = sum(
        1 for entry in entries if entry.customer_visible and entry.support_status == "unsupported"
    )
    needs_review_count = sum(1 for entry in entries if entry.support_status == "needs_review")
    return ClaimSourceSpanMap(
        entries=entries,
        spans=spans,
        unsupported_customer_visible_claim_count=unsupported_count,
        needs_review_count=needs_review_count,
    )


def ensure_no_unsupported_customer_visible_claims(
    support_map: ClaimSourceSpanMap,
) -> None:
    """Fail closed before a customer-visible report can carry unsupported claims."""
    unsupported = [
        entry
        for entry in support_map.entries
        if entry.customer_visible and entry.support_status == "unsupported"
    ]
    if unsupported:
        raise UnsupportedCustomerVisibleClaimError(unsupported)
