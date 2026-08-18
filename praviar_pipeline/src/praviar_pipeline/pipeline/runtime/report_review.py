"""Bounded, integrity-bound payload for the final report review checkpoint."""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from praviar_pipeline.models.report_source_spans import (
    SOURCE_SPAN_ATTESTATION_ALGORITHM,
    SOURCE_SPAN_ATTESTATION_SCHEMA_VERSION,
    ClaimSourceSpanMap,
    verify_source_span_attestation,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

REPORT_REVIEW_SCHEMA_VERSION: Literal["report-review/v1"] = "report-review/v1"
REPORT_REVIEW_DIGEST_DOMAIN = "praviar:report-review-checkpoint:v1"
REPORT_REVIEW_EXECUTIVE_SUMMARY_MAX_CHARS = 1_200
ReportReviewRisk = Literal["high", "medium", "low", "clear"]


class ReportReviewClaimLedger(BaseModel):
    """Safe aggregate metadata for the report's private claim/source ledger."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    assertion_count: int = Field(ge=0)
    source_span_count: int = Field(ge=0)
    needs_review_count: int = Field(ge=0)
    unsupported_count: int = Field(ge=0)
    attestation_key_ids: list[str] = Field(default_factory=list, max_length=16)


class ReportReviewCheckpointContext(BaseModel):
    """JSON-safe reviewer preview plus a receipt for the exact bound evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["report-review/v1"] = REPORT_REVIEW_SCHEMA_VERSION
    checkpoint_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=256)
    report_id: str = Field(min_length=1, max_length=256)
    overall_risk: ReportReviewRisk
    patent_count: int = Field(ge=0)
    analysis_failure_count: int = Field(ge=0)
    executive_summary_excerpt: str = Field(max_length=REPORT_REVIEW_EXECUTIVE_SUMMARY_MAX_CHARS)
    executive_summary_truncated: bool
    claim_ledger: ReportReviewClaimLedger
    prompt_hash_count: int = Field(ge=1)
    review_payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _required_identifier(value: object, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise RuntimeError(f"report review {field_name} is required")
    if len(normalized) > 256 or any(ord(char) < 32 for char in normalized):
        raise RuntimeError(f"report review {field_name} is invalid")
    return normalized


def _validated_prompt_hashes(prompt_hashes: Mapping[str, str]) -> dict[str, str]:
    if not prompt_hashes:
        raise RuntimeError("report review requires prompt hashes")

    normalized: dict[str, str] = {}
    for raw_name, raw_digest in prompt_hashes.items():
        name = str(raw_name or "").strip()
        digest = str(raw_digest or "").strip().lower()
        if (
            not name
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise RuntimeError("report review prompt hashes are invalid")
        normalized[name] = digest

    if len(normalized) != len(prompt_hashes):
        raise RuntimeError("report review prompt hash names must be unique")
    return dict(sorted(normalized.items()))


def _validated_attestation_key_ids(
    claim_source_span_map: ClaimSourceSpanMap,
    *,
    report_id: str,
    evidence_attestation_key_id: str,
    evidence_attestation_key: bytes,
) -> list[str]:
    key_id = str(evidence_attestation_key_id or "").strip()
    if not key_id or len(evidence_attestation_key) < 32:
        raise RuntimeError("report review evidence attestation key is unavailable")

    attestation_key_ids: set[str] = set()
    for span in claim_source_span_map.spans.values():
        if span.source_type != "verified_claim_text":
            continue
        if (
            span.evidence_attestation_schema_version != SOURCE_SPAN_ATTESTATION_SCHEMA_VERSION
            or span.evidence_attestation_algorithm != SOURCE_SPAN_ATTESTATION_ALGORITHM
            or span.evidence_attestation_key_id != key_id
            or span.evidence_attestation_subject_id != report_id
            or not verify_source_span_attestation(
                span,
                verification_key=evidence_attestation_key,
                expected_subject_id=report_id,
            )
        ):
            raise RuntimeError(
                "report review verified claim source span attestation is missing or invalid"
            )
        attestation_key_ids.add(span.evidence_attestation_key_id)

    return sorted(attestation_key_ids)


def _executive_summary_preview(report: Any) -> tuple[str, bool]:
    risk_summary = getattr(report, "risk_summary", None)
    full_summary = str(getattr(risk_summary, "executive_summary", "") or "").strip()
    if not full_summary:
        raise RuntimeError("report review executive summary is required")
    truncated = len(full_summary) > REPORT_REVIEW_EXECUTIVE_SUMMARY_MAX_CHARS
    excerpt = full_summary[:REPORT_REVIEW_EXECUTIVE_SUMMARY_MAX_CHARS]
    return excerpt, truncated


def _digest_bound_checkpoint_id(run_id: str, review_payload_sha256: str) -> str:
    safe_run_id = re.sub(r"[^A-Za-z0-9._-]+", "_", run_id).strip("._-")
    safe_run_id = safe_run_id[:64] or "run"
    return f"{safe_run_id}:report_review:{review_payload_sha256[:16]}"


def build_report_review_checkpoint_context(
    *,
    report: Any,
    run_id: str,
    analysis_failure_count: int,
    prompt_hashes: Mapping[str, str],
    evidence_attestation_key_id: str,
    evidence_attestation_key: bytes,
) -> dict[str, Any]:
    """Build the bounded public payload and bind it to private provenance.

    The emitted context includes only the bounded executive-summary excerpt. It
    omits full prompt hashes, source-span excerpts and source text, evidence HMAC
    receipts, and key material. The SHA-256 receipt covers those exact private
    values, however, so any mutation produces a different review receipt.
    """

    report_id = _required_identifier(
        getattr(report, "report_id", ""),
        field_name="report_id",
    )
    public_run_id = _required_identifier(run_id or report_id, field_name="run_id")
    normalized_prompt_hashes = _validated_prompt_hashes(prompt_hashes)

    raw_ledger = getattr(report, "claim_source_span_map", None)
    if not isinstance(raw_ledger, ClaimSourceSpanMap):
        raise RuntimeError("report review requires a validated claim source span map")
    attestation_key_ids = _validated_attestation_key_ids(
        raw_ledger,
        report_id=report_id,
        evidence_attestation_key_id=evidence_attestation_key_id,
        evidence_attestation_key=evidence_attestation_key,
    )

    risk_summary = getattr(report, "risk_summary", None)
    overall_risk = (
        str(getattr(getattr(risk_summary, "overall_risk", None), "value", "") or "").strip().lower()
    )
    if overall_risk not in {"high", "medium", "low", "clear"}:
        raise RuntimeError("report review overall risk is invalid")
    excerpt, summary_truncated = _executive_summary_preview(report)
    claim_ledger = ReportReviewClaimLedger(
        assertion_count=len(raw_ledger.entries),
        source_span_count=len(raw_ledger.spans),
        needs_review_count=raw_ledger.needs_review_count,
        unsupported_count=raw_ledger.unsupported_customer_visible_claim_count,
        attestation_key_ids=attestation_key_ids,
    )
    public_payload: dict[str, Any] = {
        "schema_version": REPORT_REVIEW_SCHEMA_VERSION,
        "run_id": public_run_id,
        "report_id": report_id,
        "overall_risk": overall_risk,
        "patent_count": len(getattr(report, "patent_analyses", []) or []),
        "analysis_failure_count": analysis_failure_count,
        "executive_summary_excerpt": excerpt,
        "executive_summary_truncated": summary_truncated,
        "claim_ledger": claim_ledger.model_dump(mode="json"),
        "prompt_hash_count": len(normalized_prompt_hashes),
    }
    digest_material = {
        "domain": REPORT_REVIEW_DIGEST_DOMAIN,
        "review_payload": public_payload,
        "claim_source_span_map": raw_ledger.model_dump(mode="json"),
        "prompt_hashes": normalized_prompt_hashes,
    }
    review_payload_sha256 = hashlib.sha256(
        json.dumps(
            digest_material,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    context = ReportReviewCheckpointContext(
        **public_payload,
        checkpoint_id=_digest_bound_checkpoint_id(public_run_id, review_payload_sha256),
        review_payload_sha256=review_payload_sha256,
    )
    return context.model_dump(mode="json")
