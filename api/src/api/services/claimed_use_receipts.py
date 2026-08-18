"""Durable claimed-use counsel receipt issuance and revocation."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from fastapi import Request
from praviar_pipeline.clients.primary_legal_status import (
    PrimaryLegalStatusReceipt,
    PrimaryLegalStatusRequirement,
    resolve_report_bound_primary_legal_status_receipts,
)
from praviar_pipeline.models.accused_acts import (
    AccusedActRecord,
    ClaimedUseMatchReceipt,
    create_claimed_use_match_receipt,
    verify_claimed_use_match_attestation,
)
from praviar_pipeline.models.compound import ResolvedCompound
from praviar_pipeline.utils.claim_parser_parsing import split_claims
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import write_audit_log
from api.config import get_settings
from api.db.models import (
    Analysis,
    AnalysisClaimedUseReceipt,
    AnalysisStatus,
    User,
    UserRole,
)
from api.errors import APIError
from api.schemas.claimed_use_receipts import (
    ClaimedUseEligibleUse,
    ClaimedUseReceiptIssueRequest,
    ClaimedUseReceiptListResponse,
    ClaimedUseReceiptOut,
)
from api.services.report_access import (
    report_payload_fingerprint,
    require_completed_report_payload,
)
from api.services.review_status import (
    invalidate_approved_review_status_for_decision_change,
)

_REQUIRED_US_RELIANCE_SCOPES = (
    "application_prosecution",
    "patent_term",
    "patent_maintenance",
    "post_grant_proceeding",
    "current_claim_set",
)


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalized_patent_id(value: object) -> str:
    return "".join(str(value or "").strip().upper().split())


def _accused_act_snapshot_sha256(record: AccusedActRecord) -> str:
    payload = record.model_dump(mode="json", exclude={"claimed_use_match_receipts"})
    return _canonical_sha256(payload)


async def _load_analysis(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    for_update: bool = False,
) -> Analysis:
    statement = select(Analysis).where(
        Analysis.id == analysis_id,
        Analysis.org_id == org_id,
        Analysis.status != AnalysisStatus.DELETED,
    )
    if for_update:
        statement = statement.with_for_update()
    result = await db.execute(statement)
    analysis = result.scalar_one_or_none()
    if analysis is None:
        raise APIError(404, "Not Found", "Analysis not found")
    return analysis


def _current_report_coordinates(analysis: Analysis) -> tuple[dict, str, str]:
    report_data = require_completed_report_payload(
        analysis,
        status_code=409,
        title="Conflict",
        detail="Claimed-use receipts require a completed publishable report.",
    )
    report_id = str(report_data.get("report_id") or "").strip()
    if not report_id:
        raise APIError(
            409,
            "Conflict",
            "The current report does not have a governed report identity.",
        )
    return report_data, report_id, report_payload_fingerprint(report_data)


def _configured_accused_acts(analysis: Analysis) -> list[AccusedActRecord]:
    config = analysis.config if isinstance(analysis.config, Mapping) else {}
    product_context = config.get("product_context")
    context = product_context if isinstance(product_context, Mapping) else {}
    raw_records = context.get("accused_acts")
    records = raw_records if isinstance(raw_records, list) else []
    try:
        return [AccusedActRecord.model_validate(record) for record in records]
    except (TypeError, ValidationError, ValueError) as exc:
        raise APIError(
            409,
            "Conflict",
            "The saved proposed-use facts are no longer valid and require reconfirmation.",
        ) from exc


def _eligible_uses(records: list[AccusedActRecord]) -> list[ClaimedUseEligibleUse]:
    eligible: list[ClaimedUseEligibleUse] = []
    for index, record in enumerate(records):
        if (
            record.act != "regulatory_submission"
            or record.jurisdiction != "US"
            or record.status not in {"actual", "planned"}
            or record.label_carve_out_state == "complete"
        ):
            continue
        if (
            record.target_product_identity is None
            or record.proposed_indication is None
            or record.proposed_label_use is None
            or record.label_carve_out_state is None
        ):
            continue
        eligible.append(
            ClaimedUseEligibleUse(
                accused_act_index=index,
                jurisdiction=record.jurisdiction,
                actor=record.actor,
                start_date=record.start_date,
                regulatory_path=record.regulatory_path,
                target_product_identity=record.target_product_identity,
                proposed_indication=record.proposed_indication,
                proposed_label_use=record.proposed_label_use,
                label_carve_out_state=record.label_carve_out_state,
            )
        )
    return eligible


def _resolve_proposed_use(
    analysis: Analysis,
    *,
    accused_act_index: int,
) -> tuple[AccusedActRecord, str]:
    records = _configured_accused_acts(analysis)
    if accused_act_index >= len(records):
        raise APIError(
            422,
            "Unprocessable Entity",
            "The selected proposed-use record is outside the analysis launch context.",
        )
    record = records[accused_act_index]
    if record.act != "regulatory_submission":
        raise APIError(
            422,
            "Unprocessable Entity",
            "Claimed-use receipts apply only to a regulatory submission record.",
        )
    if record.jurisdiction != "US":
        raise APIError(
            422,
            "Unprocessable Entity",
            "Claimed-use receipts currently require a US regulatory submission.",
        )
    if record.status not in {"actual", "planned"}:
        raise APIError(
            422,
            "Unprocessable Entity",
            "Denied or hypothetical proposed-use records cannot be attested.",
        )
    if record.label_carve_out_state == "complete":
        raise APIError(
            422,
            "Unprocessable Entity",
            "A complete label carve-out cannot support an affirmative claimed-use match.",
        )
    if any(
        value is None
        for value in (
            record.target_product_identity,
            record.proposed_indication,
            record.proposed_label_use,
            record.label_carve_out_state,
        )
    ):
        raise APIError(
            409,
            "Conflict",
            "The proposed-use record lacks required product, indication, "
            "label, or carve-out facts.",
        )
    return record, _accused_act_snapshot_sha256(record)


def _governed_evidence_references(
    report_data: dict,
    *,
    patent_id: str,
    claim_number: int,
    current_claim_receipt_sha256: str,
    controlling_claim_document_ids: list[str],
) -> list[str]:
    """Resolve exact report-bound evidence identifiers; never accept free text."""
    references = [
        f"primary-legal-status-receipt:sha256:{current_claim_receipt_sha256}",
        *[
            f"controlling-claim-document:{document_id}"
            for document_id in controlling_claim_document_ids
        ],
    ]
    raw_span_map = report_data.get("claim_source_span_map")
    span_map = raw_span_map if isinstance(raw_span_map, Mapping) else {}
    raw_entries = span_map.get("entries")
    entries = raw_entries if isinstance(raw_entries, list) else []
    raw_spans = span_map.get("spans")
    spans = raw_spans if isinstance(raw_spans, Mapping) else {}
    span_ids: set[str] = set()
    for entry in entries:
        if (
            not isinstance(entry, Mapping)
            or _normalized_patent_id(entry.get("patent_id")) != patent_id
            or entry.get("claim_number") != claim_number
            or entry.get("support_status") != "supported"
        ):
            continue
        raw_ids = entry.get("source_span_ids")
        if isinstance(raw_ids, list):
            span_ids.update(str(span_id).strip() for span_id in raw_ids if str(span_id).strip())
    for span_id in sorted(span_ids):
        span = spans.get(span_id)
        if (
            not isinstance(span, Mapping)
            or _normalized_patent_id(span.get("patent_id")) != patent_id
            or span.get("claim_number") != claim_number
        ):
            raise APIError(
                409,
                "Conflict",
                "A governed claim evidence span does not match the selected report claim.",
            )
        span_sha256 = str(span.get("source_text_sha256") or "").strip()
        if len(span_sha256) != 64:
            span_sha256 = _canonical_sha256(dict(span))
        references.append(f"report-source-span:{span_id}:sha256:{span_sha256}")
    return list(dict.fromkeys(references))


def _resolve_current_claim_context(
    report_data: dict,
    *,
    patent_id: str,
    claim_number: int,
) -> tuple[str, str, list[str], list[str]]:
    raw_details = report_data.get("patent_details")
    patent_details = raw_details if isinstance(raw_details, Mapping) else {}
    detail = patent_details.get(patent_id)
    if not isinstance(detail, Mapping):
        raise APIError(
            422,
            "Unprocessable Entity",
            "The patent is not present in the current governed report detail.",
        )
    if _normalized_patent_id(detail.get("patent_id")) != patent_id:
        raise APIError(
            409,
            "Conflict",
            "The report patent detail identity does not match its governed key.",
        )
    claims_text = str(detail.get("claims_text") or "")
    if not claims_text:
        raise APIError(
            409,
            "Conflict",
            "Current controlling claim text is unavailable for this patent.",
        )
    controlling_claim = next(
        (
            parsed_claim
            for parsed_claim in split_claims(claims_text)
            if parsed_claim.claim_number == claim_number
        ),
        None,
    )
    if controlling_claim is None or not controlling_claim.raw_text.strip():
        raise APIError(
            422,
            "Unprocessable Entity",
            "The selected claim is not present in the current controlling claim set.",
        )

    raw_receipts = detail.get("primary_legal_status_receipts")
    receipt_payloads = raw_receipts if isinstance(raw_receipts, list) else []
    try:
        receipts = [
            PrimaryLegalStatusReceipt.model_validate(receipt) for receipt in receipt_payloads
        ]
    except (TypeError, ValidationError, ValueError) as exc:
        raise APIError(
            409,
            "Conflict",
            "The patent legal-status receipt set is malformed.",
        ) from exc
    if not receipts:
        raise APIError(
            409,
            "Conflict",
            "Fresh primary-authority legal-status receipts are unavailable.",
        )

    requirements = [
        PrimaryLegalStatusRequirement(
            patent_id=patent_id,
            evidence_scope=scope,
        )
        for scope in _REQUIRED_US_RELIANCE_SCOPES
    ]
    # require_completed_report_payload() has already verified the report's
    # Ed25519 owner binding. Resolve the receipts inside that signed envelope
    # without granting the API the worker-only HMAC key.
    resolution = resolve_report_bound_primary_legal_status_receipts(
        receipts=receipts,
        requirements=requirements,
        now=datetime.now(UTC),
    )
    if not resolution.coverage.satisfied:
        raise APIError(
            409,
            "Conflict",
            "Fresh, conclusive primary-authority evidence is incomplete: "
            + "; ".join(resolution.coverage.failure_reasons),
        )
    selected = {receipt.evidence_scope: receipt for receipt in resolution.selected_receipts}
    current_claim_receipt = selected.get("current_claim_set")
    if (
        current_claim_receipt is None
        or current_claim_receipt.current_claim_text_sha256
        != hashlib.sha256(claims_text.encode("utf-8")).hexdigest()
        or str(claim_number) not in current_claim_receipt.effective_claim_ids
        or not current_claim_receipt.controlling_claim_document_ids
    ):
        raise APIError(
            409,
            "Conflict",
            "The current-claim receipt does not bind the selected controlling claim text.",
        )
    document_ids = list(current_claim_receipt.controlling_claim_document_ids)
    return (
        controlling_claim.raw_text,
        current_claim_receipt.receipt_sha256,
        document_ids,
        _governed_evidence_references(
            report_data,
            patent_id=patent_id,
            claim_number=claim_number,
            current_claim_receipt_sha256=current_claim_receipt.receipt_sha256,
            controlling_claim_document_ids=document_ids,
        ),
    )


def _resolved_compound(report_data: dict) -> ResolvedCompound:
    try:
        return ResolvedCompound.model_validate(report_data.get("compound"))
    except (TypeError, ValidationError, ValueError) as exc:
        raise APIError(
            409,
            "Conflict",
            "The report does not contain a valid resolved compound identity.",
        ) from exc


def _serialize_row(
    row: AnalysisClaimedUseReceipt,
    *,
    current_report_id: str,
    current_report_fingerprint: str,
    current_accused_act_sha256: str | None,
    user: User,
) -> ClaimedUseReceiptOut:
    try:
        receipt = ClaimedUseMatchReceipt.model_validate(row.receipt_payload)
    except (TypeError, ValidationError, ValueError) as exc:
        raise APIError(
            409,
            "Conflict",
            "A stored claimed-use receipt failed integrity validation.",
        ) from exc
    if (
        row.receipt_sha256 != receipt.receipt_sha256
        or row.analysis_id != receipt.analysis_id
        or row.org_id != receipt.org_id
        or row.report_id != receipt.report_id
        or row.report_fingerprint != receipt.report_fingerprint
        or row.patent_id != receipt.patent_id
        or row.claim_number != receipt.claim_number
        or row.accused_act_index != receipt.accused_act_index
        or row.accused_act_sha256 != receipt.accused_act_sha256
        or row.issuer_user_id != receipt.issuer_user_id
        or row.issued_at.astimezone(UTC) != receipt.verified_at.astimezone(UTC)
    ):
        raise APIError(
            409,
            "Conflict",
            "A stored claimed-use receipt does not match its governed coordinates.",
        )
    try:
        attestation_key = get_settings().claimed_use_attestation_keys.verification_key(
            receipt.attestation_key_id
        )
    except ValueError as exc:
        raise APIError(
            409,
            "Conflict",
            "A stored claimed-use receipt uses an unknown attestation key.",
        ) from exc
    if not verify_claimed_use_match_attestation(
        receipt,
        attestation_key=attestation_key,
    ):
        raise APIError(
            409,
            "Conflict",
            "A stored claimed-use receipt has an invalid server attestation.",
        )
    governs_current_report = (
        row.revoked_at is None
        and row.report_id == current_report_id
        and row.report_fingerprint == current_report_fingerprint
        and current_accused_act_sha256 == row.accused_act_sha256
    )
    return ClaimedUseReceiptOut(
        id=row.id,
        analysis_id=row.analysis_id,
        report_id=row.report_id,
        report_fingerprint=row.report_fingerprint,
        patent_id=row.patent_id,
        claim_number=row.claim_number,
        accused_act_index=row.accused_act_index,
        accused_act_sha256=row.accused_act_sha256,
        receipt=receipt,
        issuer_user_id=row.issuer_user_id,
        reviewer_role=receipt.reviewer_role,
        attestation_statement_version=receipt.attestation_statement_version,
        issued_at=row.issued_at,
        revoked_at=row.revoked_at,
        revoked_by_user_id=row.revoked_by_user_id,
        revocation_reason=row.revocation_reason,
        governs_current_report=governs_current_report,
        can_revoke=bool(
            row.revoked_at is None
            and (user.role == UserRole.ADMIN or row.issuer_user_id == user.id)
        ),
    )


async def issue_claimed_use_receipt(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    user: User,
    body: ClaimedUseReceiptIssueRequest,
    request: Request | None = None,
    use_database_boundary: bool = False,
) -> ClaimedUseReceiptOut:
    """Issue one server-attested receipt from only current governed evidence."""
    if get_settings().app_env == "prod" and not use_database_boundary:
        raise RuntimeError("production claimed-use issuance requires the dedicated writer boundary")
    if user.role != UserRole.ATTORNEY:
        raise APIError(
            403,
            "Forbidden",
            "Only an active attorney member may issue a counsel affirmation.",
        )
    analysis = await _load_analysis(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
        for_update=True,
    )
    report_data, report_id, report_fingerprint = _current_report_coordinates(analysis)
    if (
        body.expected_report_id != report_id
        or body.expected_report_fingerprint != report_fingerprint
    ):
        raise APIError(
            409,
            "Conflict",
            "The report changed; refresh before issuing a claimed-use receipt.",
        )

    proposed_use, accused_act_sha256 = _resolve_proposed_use(
        analysis,
        accused_act_index=body.accused_act_index,
    )
    (
        controlling_claim_text,
        current_claim_receipt_sha256,
        document_ids,
        evidence_references,
    ) = _resolve_current_claim_context(
        report_data,
        patent_id=body.patent_id,
        claim_number=body.claim_number,
    )
    compound = _resolved_compound(report_data)
    issued_at = datetime.now(UTC)
    keyring = get_settings().claimed_use_attestation_keys
    receipt = create_claimed_use_match_receipt(
        analysis_id=analysis_id,
        org_id=user.org_id,
        report_id=report_id,
        report_fingerprint=report_fingerprint,
        accused_act_index=body.accused_act_index,
        accused_act_sha256=accused_act_sha256,
        patent_id=body.patent_id,
        claim_number=body.claim_number,
        controlling_claim_text=controlling_claim_text,
        current_claim_receipt_sha256=current_claim_receipt_sha256,
        controlling_claim_document_ids=document_ids,
        target_product_identity=str(proposed_use.target_product_identity),
        compound=compound,
        proposed_indication=str(proposed_use.proposed_indication),
        proposed_label_use=str(proposed_use.proposed_label_use),
        label_carve_out_state=proposed_use.label_carve_out_state or "unknown",
        issuer_user_id=user.id,
        verified_at=issued_at,
        evidence_references=evidence_references,
        attestation_key_id=keyring.active_key_id,
        attestation_key=keyring.active_key(),
    )
    existing_result = await db.execute(
        select(AnalysisClaimedUseReceipt)
        .where(
            AnalysisClaimedUseReceipt.analysis_id == analysis_id,
            AnalysisClaimedUseReceipt.org_id == user.org_id,
            AnalysisClaimedUseReceipt.report_fingerprint == report_fingerprint,
            AnalysisClaimedUseReceipt.patent_id == body.patent_id,
            AnalysisClaimedUseReceipt.claim_number == body.claim_number,
            AnalysisClaimedUseReceipt.accused_act_sha256 == accused_act_sha256,
            AnalysisClaimedUseReceipt.revoked_at.is_(None),
        )
        .with_for_update()
    )
    if existing_result.scalar_one_or_none() is not None:
        raise APIError(
            409,
            "Conflict",
            "An active receipt already governs this exact report claim and proposed use.",
        )

    try:
        if use_database_boundary:
            payload = receipt.model_dump(mode="json")
            receipt_id = (
                await db.execute(
                    text(
                        "SELECT public.issue_claimed_use_receipt(CAST(:receipt_payload AS jsonb))"
                    ),
                    {
                        "receipt_payload": json.dumps(
                            payload,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    },
                )
            ).scalar_one()
            row = (
                await db.execute(
                    select(AnalysisClaimedUseReceipt)
                    .where(
                        AnalysisClaimedUseReceipt.id == receipt_id,
                        AnalysisClaimedUseReceipt.org_id == user.org_id,
                    )
                    .with_for_update()
                )
            ).scalar_one()
        else:
            row = AnalysisClaimedUseReceipt(
                analysis_id=analysis_id,
                org_id=user.org_id,
                report_id=report_id,
                report_fingerprint=report_fingerprint,
                patent_id=receipt.patent_id,
                claim_number=receipt.claim_number,
                accused_act_index=body.accused_act_index,
                accused_act_sha256=accused_act_sha256,
                receipt_sha256=receipt.receipt_sha256,
                receipt_payload=receipt.model_dump(mode="json"),
                issuer_user_id=user.id,
                issued_at=issued_at,
            )
            db.add(row)
            await db.flush()
        approval_invalidated = await invalidate_approved_review_status_for_decision_change(
            db,
            analysis_id=analysis_id,
            org_id=user.org_id,
            user=user,
        )
        await write_audit_log(
            db,
            org_id=user.org_id,
            user_id=user.id,
            analysis_id=analysis_id,
            action="claimed_use_receipt.issue",
            details={
                "claimed_use_receipt_id": str(row.id),
                "receipt_sha256": row.receipt_sha256,
                "report_id": report_id,
                "report_fingerprint": report_fingerprint,
                "patent_id": row.patent_id,
                "claim_number": row.claim_number,
                "accused_act_index": row.accused_act_index,
                "accused_act_sha256": row.accused_act_sha256,
                "approval_invalidated": approval_invalidated,
            },
            request=request,
            fail_closed=True,
        )
        serialized = _serialize_row(
            row,
            current_report_id=report_id,
            current_report_fingerprint=report_fingerprint,
            current_accused_act_sha256=accused_act_sha256,
            user=user,
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", "")
        if constraint_name in {
            "uq_analysis_claimed_use_receipts_active_subject",
            "uq_analysis_claimed_use_receipts_digest",
        }:
            raise APIError(
                409,
                "Conflict",
                "A concurrent receipt already governs this exact report claim and proposed use.",
            ) from exc
        raise
    except Exception:
        await db.rollback()
        raise
    return serialized


async def list_claimed_use_receipts(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    user: User,
) -> ClaimedUseReceiptListResponse:
    """Return immutable receipt history and current eligible proposed uses."""
    analysis = await _load_analysis(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
    )
    _, report_id, report_fingerprint = _current_report_coordinates(analysis)
    records = _configured_accused_acts(analysis)
    current_use_hashes = {
        index: _accused_act_snapshot_sha256(record) for index, record in enumerate(records)
    }
    result = await db.execute(
        select(AnalysisClaimedUseReceipt)
        .where(
            AnalysisClaimedUseReceipt.analysis_id == analysis_id,
            AnalysisClaimedUseReceipt.org_id == user.org_id,
        )
        .order_by(
            AnalysisClaimedUseReceipt.issued_at.desc(),
            AnalysisClaimedUseReceipt.id,
        )
    )
    rows = list(result.scalars().all())
    return ClaimedUseReceiptListResponse(
        current_report_id=report_id,
        current_report_fingerprint=report_fingerprint,
        eligible_uses=_eligible_uses(records),
        items=[
            _serialize_row(
                row,
                current_report_id=report_id,
                current_report_fingerprint=report_fingerprint,
                current_accused_act_sha256=current_use_hashes.get(row.accused_act_index),
                user=user,
            )
            for row in rows
        ],
    )


async def revoke_claimed_use_receipt(
    db: AsyncSession,
    *,
    analysis_id: uuid.UUID,
    receipt_id: uuid.UUID,
    user: User,
    reason: str,
    request: Request | None = None,
    use_database_boundary: bool = False,
) -> ClaimedUseReceiptOut:
    """Append a reasoned revocation without altering the signed receipt."""
    if get_settings().app_env == "prod" and not use_database_boundary:
        raise RuntimeError(
            "production claimed-use revocation requires the dedicated writer boundary"
        )
    analysis = await _load_analysis(
        db,
        analysis_id=analysis_id,
        org_id=user.org_id,
        for_update=True,
    )
    result = await db.execute(
        select(AnalysisClaimedUseReceipt)
        .where(
            AnalysisClaimedUseReceipt.id == receipt_id,
            AnalysisClaimedUseReceipt.analysis_id == analysis_id,
            AnalysisClaimedUseReceipt.org_id == user.org_id,
        )
        .with_for_update()
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise APIError(404, "Not Found", "Claimed-use receipt not found")
    if row.revoked_at is not None:
        raise APIError(409, "Conflict", "Claimed-use receipt is already revoked")
    if user.role != UserRole.ADMIN and row.issuer_user_id != user.id:
        raise APIError(
            403,
            "Forbidden",
            "Only the issuing attorney or an org admin may revoke this receipt.",
        )
    try:
        _, current_report_id, current_report_fingerprint = _current_report_coordinates(analysis)
        current_records = _configured_accused_acts(analysis)
        current_accused_act_sha256 = (
            _accused_act_snapshot_sha256(current_records[row.accused_act_index])
            if row.accused_act_index < len(current_records)
            else None
        )
    except APIError:
        # Revocation must remain available when a later report is unavailable
        # or unpublishable. In that state the historical receipt cannot govern
        # the current report, but its own signature must still verify below.
        current_report_id = ""
        current_report_fingerprint = ""
        current_accused_act_sha256 = None
    _serialize_row(
        row,
        current_report_id=current_report_id,
        current_report_fingerprint=current_report_fingerprint,
        current_accused_act_sha256=current_accused_act_sha256,
        user=user,
    )
    try:
        revoked_at = datetime.now(UTC)
        if use_database_boundary:
            await db.execute(
                text(
                    "SELECT public.revoke_claimed_use_receipt("
                    "CAST(:receipt_id AS uuid), "
                    "CAST(:org_id AS uuid), "
                    "CAST(:revoked_by_user_id AS uuid), "
                    ":revocation_reason, "
                    "CAST(:revoked_at AS timestamptz))"
                ),
                {
                    "receipt_id": str(row.id),
                    "org_id": str(user.org_id),
                    "revoked_by_user_id": str(user.id),
                    "revocation_reason": reason,
                    "revoked_at": revoked_at,
                },
            )
            await db.refresh(row)
        else:
            row.revoked_at = revoked_at
            row.revoked_by_user_id = user.id
            row.revocation_reason = reason
            await db.flush()
        approval_invalidated = await invalidate_approved_review_status_for_decision_change(
            db,
            analysis_id=analysis_id,
            org_id=user.org_id,
            user=user,
        )
        await write_audit_log(
            db,
            org_id=user.org_id,
            user_id=user.id,
            analysis_id=analysis_id,
            action="claimed_use_receipt.revoke",
            details={
                "claimed_use_receipt_id": str(row.id),
                "receipt_sha256": row.receipt_sha256,
                "report_id": row.report_id,
                "report_fingerprint": row.report_fingerprint,
                "patent_id": row.patent_id,
                "claim_number": row.claim_number,
                "accused_act_sha256": row.accused_act_sha256,
                "revocation_reason": reason,
                "approval_invalidated": approval_invalidated,
            },
            request=request,
            fail_closed=True,
        )
        serialized = _serialize_row(
            row,
            current_report_id=current_report_id,
            current_report_fingerprint=current_report_fingerprint,
            current_accused_act_sha256=current_accused_act_sha256,
            user=user,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return serialized
