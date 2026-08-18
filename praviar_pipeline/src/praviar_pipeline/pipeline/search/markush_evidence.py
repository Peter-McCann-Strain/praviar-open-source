"""Clearance-gate evaluation for supervised PATENTSCOPE Markush evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from praviar_pipeline.models.markush_evidence import (
    MarkushEvidenceReceipt,
    verify_markush_evidence_attestation,
)


class MarkushClearanceEvidenceEvaluation(BaseModel):
    """Deterministic, presentation-safe status for the clearance gate."""

    model_config = ConfigDict(extra="forbid")

    required: bool
    eligible_for_positive_clearance: bool
    status: Literal[
        "not_required",
        "verified_manual",
        "not_run",
        "incomplete",
        "unavailable",
    ]
    age_days: int | None = Field(default=None, ge=0)
    receipt_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    failure_reasons: list[str] = Field(default_factory=list)


def evaluate_markush_clearance_evidence(
    report,
    settings,
    *,
    now: datetime | None = None,
) -> MarkushClearanceEvidenceEvaluation:
    """Evaluate the explicit small-molecule Markush evidence requirement.

    Callers should append ``failure_reasons`` to their existing clearance
    insufficiency ledger before computing a positive decision. This helper does
    not mutate the report and cannot turn missing evidence into a soft warning.
    """
    compound_type = str(
        getattr(getattr(report, "compound", None), "compound_type", "") or ""
    ).strip()
    required = bool(getattr(settings, "require_verified_manual_markush", True)) and (
        compound_type == "small_molecule"
    )
    if not required:
        return MarkushClearanceEvidenceEvaluation(
            required=False,
            eligible_for_positive_clearance=True,
            status="not_required",
        )

    audit_trail = getattr(report, "audit_trail", None)
    query_plan = getattr(audit_trail, "query_plan", None)
    raw_receipt = getattr(query_plan, "markush_evidence", None)
    if raw_receipt is None:
        return MarkushClearanceEvidenceEvaluation(
            required=True,
            eligible_for_positive_clearance=False,
            status="not_run",
            failure_reasons=[
                "A verified manual PATENTSCOPE Markush search receipt is required "
                "before this small-molecule matter can support positive clearance."
            ],
        )

    receipt = MarkushEvidenceReceipt.model_validate(raw_receipt)
    if receipt.status != "verified_manual":
        return MarkushClearanceEvidenceEvaluation(
            required=True,
            eligible_for_positive_clearance=False,
            status=receipt.status,
            receipt_sha256=receipt.receipt_sha256,
            failure_reasons=[
                "PATENTSCOPE Markush evidence is "
                f"{receipt.status.replace('_', ' ')} rather than independently verified."
            ],
        )

    integrity_keys = getattr(settings, "checkpoint_integrity_keys", None)
    if integrity_keys is None or receipt.attestation_key_id is None:
        return MarkushClearanceEvidenceEvaluation(
            required=True,
            eligible_for_positive_clearance=False,
            status="incomplete",
            receipt_sha256=receipt.receipt_sha256,
            failure_reasons=["PATENTSCOPE Markush evidence lacks a verifiable server attestation."],
        )
    try:
        attestation_key = integrity_keys.verification_key(receipt.attestation_key_id)
    except ValueError:
        return MarkushClearanceEvidenceEvaluation(
            required=True,
            eligible_for_positive_clearance=False,
            status="incomplete",
            receipt_sha256=receipt.receipt_sha256,
            failure_reasons=["PATENTSCOPE Markush evidence uses an unavailable attestation key."],
        )
    if not verify_markush_evidence_attestation(
        receipt,
        attestation_key=attestation_key,
    ):
        return MarkushClearanceEvidenceEvaluation(
            required=True,
            eligible_for_positive_clearance=False,
            status="incomplete",
            receipt_sha256=receipt.receipt_sha256,
            failure_reasons=["PATENTSCOPE Markush evidence server attestation is invalid."],
        )

    checked_at = (now or datetime.now(UTC)).astimezone(UTC)
    if receipt.executed_at is None:  # protected by the receipt model; defensive totality
        raise ValueError("verified Markush receipt lacks execution time")
    age_days = (checked_at.date() - receipt.executed_at.astimezone(UTC).date()).days
    maximum_age_days = int(getattr(settings, "markush_evidence_max_age_days", 35))
    if age_days < 0:
        return MarkushClearanceEvidenceEvaluation(
            required=True,
            eligible_for_positive_clearance=False,
            status="incomplete",
            receipt_sha256=receipt.receipt_sha256,
            failure_reasons=["PATENTSCOPE Markush evidence execution time is in the future."],
        )
    if age_days > maximum_age_days:
        return MarkushClearanceEvidenceEvaluation(
            required=True,
            eligible_for_positive_clearance=False,
            status="incomplete",
            age_days=age_days,
            receipt_sha256=receipt.receipt_sha256,
            failure_reasons=[
                "PATENTSCOPE Markush evidence is stale "
                f"({age_days} days old; maximum {maximum_age_days})."
            ],
        )
    return MarkushClearanceEvidenceEvaluation(
        required=True,
        eligible_for_positive_clearance=True,
        status="verified_manual",
        age_days=age_days,
        receipt_sha256=receipt.receipt_sha256,
    )
