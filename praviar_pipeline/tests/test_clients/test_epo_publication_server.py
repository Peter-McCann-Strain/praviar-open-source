from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Literal

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

import praviar_pipeline.clients.epo_publication_server as epo_publication_server
import praviar_pipeline.models.epo_publication as epo_publication_models
from praviar_pipeline.clients.epo_publication_server import (
    BASE_URL,
    EPS_XML_MAX_BYTES,
    EPAtomicCheckpointStore,
    EPCheckpointAdvance,
    EPCheckpointBatchResult,
    EPOPublicationResolutionConfig,
    EPOPublicationServerClient,
)
from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.models.epo_publication import (
    EP_CHECKPOINT_SCHEMA_EPOCH,
    EP_CHECKPOINT_SOURCE_STREAM_ID,
    EPAuthorityAcquisitionManifest,
    EPAuthorityCoverageEvidence,
    EPAuthorityManifestRecord,
    EPCentralProcedureEvidence,
    EPCentralProcedureState,
    EPClaimsResolutionReason,
    EPClaimsResolutionStatus,
    EPControllingClaimsResolution,
    EPRegisterAcquisitionManifest,
    EPRegisterProcedureEvent,
    EPSignedAcquisitionReceipt,
    EPSignedSnapshotHighWaterReceipt,
    EPSMediaArtifact,
    EPSPublicationRecord,
    EPSuspensiveAppealState,
    EPTrustedAcquisitionKey,
    build_ep_acquisition_envelope_sha256,
    build_ep_acquisition_signature_payload,
    build_ep_authority_evidence_binding_sha256,
    build_ep_procedure_evidence_binding_sha256,
    build_ep_snapshot_checkpoint_batch_sha256,
    build_ep_snapshot_checkpoint_envelope_sha256,
    build_ep_snapshot_high_water_signature_payload,
)

PUBLICATION_NUMBER = "1234567"
AS_OF = date(2026, 6, 24)
PDF_BYTES = b"%PDF-1.7\nEPS fixture\n%%EOF\n"
AUTHORITY_ACQUISITION_KEY_ID = "test-epo-authority-acquisition-v1"
REGISTER_ACQUISITION_KEY_ID = "test-epo-register-acquisition-v1"
AUTHORITY_CHECKPOINT_KEY_ID = "test-epo-authority-checkpoint-v1"
REGISTER_CHECKPOINT_KEY_ID = "test-epo-register-checkpoint-v1"
AUTHORITY_ACQUISITION_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(b"\x11" * 32)
REGISTER_ACQUISITION_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(b"\x12" * 32)
AUTHORITY_CHECKPOINT_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(b"\x21" * 32)
REGISTER_CHECKPOINT_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(b"\x22" * 32)


def _trusted_key(
    key_id: str,
    private_key: Ed25519PrivateKey,
    purpose: Literal[
        "authority_acquisition",
        "register_acquisition",
        "authority_checkpoint",
        "register_checkpoint",
    ],
) -> EPTrustedAcquisitionKey:
    return EPTrustedAcquisitionKey(
        key_id=key_id,
        public_key=private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ),
        purpose=purpose,
        not_before=datetime(2020, 1, 1, tzinfo=UTC),
        not_after=datetime(2035, 1, 1, tzinfo=UTC),
        status="active",
        revocation_epoch=0,
    )


AUTHORITY_ACQUISITION_TRUSTED_KEY = _trusted_key(
    AUTHORITY_ACQUISITION_KEY_ID,
    AUTHORITY_ACQUISITION_PRIVATE_KEY,
    "authority_acquisition",
)
REGISTER_ACQUISITION_TRUSTED_KEY = _trusted_key(
    REGISTER_ACQUISITION_KEY_ID,
    REGISTER_ACQUISITION_PRIVATE_KEY,
    "register_acquisition",
)
AUTHORITY_CHECKPOINT_TRUSTED_KEY = _trusted_key(
    AUTHORITY_CHECKPOINT_KEY_ID,
    AUTHORITY_CHECKPOINT_PRIVATE_KEY,
    "authority_checkpoint",
)
REGISTER_CHECKPOINT_TRUSTED_KEY = _trusted_key(
    REGISTER_CHECKPOINT_KEY_ID,
    REGISTER_CHECKPOINT_PRIVATE_KEY,
    "register_checkpoint",
)
TEST_TRUSTED_KEYS = {
    key.key_id: key
    for key in (
        AUTHORITY_ACQUISITION_TRUSTED_KEY,
        REGISTER_ACQUISITION_TRUSTED_KEY,
    )
}
TEST_TRUSTED_CHECKPOINT_KEYS = {
    key.key_id: key
    for key in (
        AUTHORITY_CHECKPOINT_TRUSTED_KEY,
        REGISTER_CHECKPOINT_TRUSTED_KEY,
    )
}


def _signed_receipt(
    manifest: EPAuthorityAcquisitionManifest | EPRegisterAcquisitionManifest,
    manifest_type: Literal["authority", "register"],
    *,
    private_key: Ed25519PrivateKey | None = None,  # gitleaks:allow
    key_id: str | None = None,
) -> EPSignedAcquisitionReceipt:
    return _raw_signed_receipt(
        manifest.model_dump(mode="json"),
        manifest_type,
        private_key=private_key,
        key_id=key_id,
    )


def _raw_signed_receipt(
    payload: object,
    manifest_type: Literal["authority", "register"],
    *,
    private_key: Ed25519PrivateKey | None = None,  # gitleaks:allow
    key_id: str | None = None,
) -> EPSignedAcquisitionReceipt:
    manifest_bytes = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return _receipt_from_manifest_bytes(
        manifest_bytes,
        manifest_type,
        private_key=private_key,
        key_id=key_id,
    )


def _receipt_from_manifest_bytes(
    manifest_bytes: bytes,
    manifest_type: Literal["authority", "register"],
    *,
    private_key: Ed25519PrivateKey | None = None,  # gitleaks:allow
    key_id: str | None = None,
) -> EPSignedAcquisitionReceipt:
    effective_private_key = private_key or (
        AUTHORITY_ACQUISITION_PRIVATE_KEY
        if manifest_type == "authority"
        else REGISTER_ACQUISITION_PRIVATE_KEY
    )
    effective_key_id = key_id or (
        AUTHORITY_ACQUISITION_KEY_ID
        if manifest_type == "authority"
        else REGISTER_ACQUISITION_KEY_ID
    )
    signed_at = datetime.now(UTC)
    schema_version: Literal[
        "epo-authority-acquisition-v1",
        "epo-register-acquisition-v1",
    ] = (
        "epo-authority-acquisition-v1"
        if manifest_type == "authority"
        else "epo-register-acquisition-v1"
    )
    signature_payload = build_ep_acquisition_signature_payload(
        manifest_type=manifest_type,
        manifest_schema_version=schema_version,
        signing_key_id=effective_key_id,
        key_revocation_epoch=0,
        signed_at=signed_at,
        manifest_bytes=manifest_bytes,
    )
    return EPSignedAcquisitionReceipt(
        envelope_version="praviar-epo-acquisition-envelope-v1",
        manifest_type=manifest_type,
        manifest_schema_version=schema_version,
        signing_key_id=effective_key_id,
        key_revocation_epoch=0,
        signed_at=signed_at,
        manifest_bytes=manifest_bytes,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        signature=effective_private_key.sign(signature_payload),
    )


def _high_water_pair(
    procedure: EPCentralProcedureEvidence,
    *,
    required_as_of: date,
    authority_minimum_snapshot_sequence: int = 1,
    register_minimum_snapshot_sequence: int = 1,
    authority_checkpoint_generation: int = 1,
    register_checkpoint_generation: int = 1,
    authority_prior_checkpoint_envelope_sha256: str | None = None,
    register_prior_checkpoint_envelope_sha256: str | None = None,
) -> tuple[EPSignedSnapshotHighWaterReceipt, EPSignedSnapshotHighWaterReceipt]:
    assert procedure.authority_coverage is not None
    assert procedure.acquisition_receipt is not None
    authority_envelope_sha256 = build_ep_acquisition_envelope_sha256(
        procedure.authority_coverage.acquisition_receipt
    )
    register_envelope_sha256 = build_ep_acquisition_envelope_sha256(procedure.acquisition_receipt)
    authority_subject = procedure.source_document_id.removeprefix("EP")
    register_subject = procedure.source_document_id
    checkpoint_batch_sha256 = build_ep_snapshot_checkpoint_batch_sha256(
        source_stream_id=EP_CHECKPOINT_SOURCE_STREAM_ID,
        schema_epoch=EP_CHECKPOINT_SCHEMA_EPOCH,
        authority_subject=authority_subject,
        register_subject=register_subject,
        required_as_of=required_as_of,
        authority_checkpoint_generation=authority_checkpoint_generation,
        register_checkpoint_generation=register_checkpoint_generation,
        authority_prior_checkpoint_envelope_sha256=(authority_prior_checkpoint_envelope_sha256),
        register_prior_checkpoint_envelope_sha256=register_prior_checkpoint_envelope_sha256,
        authority_minimum_snapshot_sequence=authority_minimum_snapshot_sequence,
        register_minimum_snapshot_sequence=register_minimum_snapshot_sequence,
        authority_source_acquisition_envelope_sha256=authority_envelope_sha256,
        register_source_acquisition_envelope_sha256=register_envelope_sha256,
    )

    def build(
        manifest_type: Literal["authority", "register"],
    ) -> EPSignedSnapshotHighWaterReceipt:
        if manifest_type == "authority":
            subject = authority_subject
            checkpoint_generation = authority_checkpoint_generation
            counterpart_envelope_sha256 = register_envelope_sha256
            prior_checkpoint_envelope_sha256 = authority_prior_checkpoint_envelope_sha256
            minimum_snapshot_sequence = authority_minimum_snapshot_sequence
            source_acquisition_envelope_sha256 = authority_envelope_sha256
            signing_key_id = AUTHORITY_CHECKPOINT_KEY_ID
            private_key = AUTHORITY_CHECKPOINT_PRIVATE_KEY
        else:
            subject = register_subject
            checkpoint_generation = register_checkpoint_generation
            counterpart_envelope_sha256 = authority_envelope_sha256
            prior_checkpoint_envelope_sha256 = register_prior_checkpoint_envelope_sha256
            minimum_snapshot_sequence = register_minimum_snapshot_sequence
            source_acquisition_envelope_sha256 = register_envelope_sha256
            signing_key_id = REGISTER_CHECKPOINT_KEY_ID
            private_key = REGISTER_CHECKPOINT_PRIVATE_KEY
        signed_at = datetime.now(UTC)
        signature_payload = build_ep_snapshot_high_water_signature_payload(
            source_stream_id=EP_CHECKPOINT_SOURCE_STREAM_ID,
            schema_epoch=EP_CHECKPOINT_SCHEMA_EPOCH,
            manifest_type=manifest_type,
            subject=subject,
            required_as_of=required_as_of,
            checkpoint_batch_sha256=checkpoint_batch_sha256,
            checkpoint_generation=checkpoint_generation,
            counterpart_source_acquisition_envelope_sha256=counterpart_envelope_sha256,
            prior_checkpoint_envelope_sha256=prior_checkpoint_envelope_sha256,
            minimum_snapshot_sequence=minimum_snapshot_sequence,
            source_acquisition_envelope_sha256=source_acquisition_envelope_sha256,
            signing_key_id=signing_key_id,
            key_revocation_epoch=0,
            signed_at=signed_at,
        )
        return EPSignedSnapshotHighWaterReceipt(
            envelope_version="praviar-epo-high-water-envelope-v1",
            source_stream_id=EP_CHECKPOINT_SOURCE_STREAM_ID,
            schema_epoch=EP_CHECKPOINT_SCHEMA_EPOCH,
            manifest_type=manifest_type,
            subject=subject,
            required_as_of=required_as_of,
            checkpoint_batch_sha256=checkpoint_batch_sha256,
            checkpoint_generation=checkpoint_generation,
            counterpart_source_acquisition_envelope_sha256=counterpart_envelope_sha256,
            prior_checkpoint_envelope_sha256=prior_checkpoint_envelope_sha256,
            minimum_snapshot_sequence=minimum_snapshot_sequence,
            source_acquisition_envelope_sha256=source_acquisition_envelope_sha256,
            signing_key_id=signing_key_id,
            key_revocation_epoch=0,
            signed_at=signed_at,
            signature=private_key.sign(signature_payload),
        )

    return build("authority"), build("register")


class _AtomicMemoryCheckpointStore(EPAtomicCheckpointStore):
    """Test double that implements the production store's atomic contract."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._state: dict[
            tuple[Literal["authority", "register"], str],
            tuple[int, str, int, date, str],
        ] = {}

    async def load_trusted_checkpoint_keys(
        self,
    ) -> dict[str, EPTrustedAcquisitionKey]:
        return dict(TEST_TRUSTED_CHECKPOINT_KEYS)

    async def compare_and_advance_atomic(
        self,
        advances: tuple[EPCheckpointAdvance, EPCheckpointAdvance],
    ) -> EPCheckpointBatchResult:
        async with self._lock:
            authority_advance, register_advance = advances
            authority_checkpoint = authority_advance.checkpoint
            register_checkpoint = register_advance.checkpoint
            batch_sha256 = authority_checkpoint.checkpoint_batch_sha256
            if (
                authority_checkpoint.manifest_type != "authority"
                or register_checkpoint.manifest_type != "register"
                or register_checkpoint.checkpoint_batch_sha256 != batch_sha256
                or authority_checkpoint.counterpart_source_acquisition_envelope_sha256
                != register_checkpoint.source_acquisition_envelope_sha256
                or register_checkpoint.counterpart_source_acquisition_envelope_sha256
                != authority_checkpoint.source_acquisition_envelope_sha256
            ):
                return EPCheckpointBatchResult(
                    status="rejected",
                    persisted_checkpoint_envelope_sha256=(),
                )
            decisions: list[Literal["idempotent", "advance"]] = []
            for advance in advances:
                checkpoint = advance.checkpoint
                key = (
                    checkpoint.manifest_type,
                    checkpoint.subject,
                )
                current = self._state.get(key)
                candidate = (
                    checkpoint.checkpoint_generation,
                    advance.checkpoint_envelope_sha256,
                    advance.source_snapshot_sequence,
                    checkpoint.required_as_of,
                    checkpoint.checkpoint_batch_sha256,
                )
                if current == candidate:
                    decisions.append("idempotent")
                    continue
                if current is None:
                    valid_advance = (
                        checkpoint.checkpoint_generation == 1
                        and checkpoint.prior_checkpoint_envelope_sha256 is None
                    )
                else:
                    valid_advance = (
                        checkpoint.checkpoint_generation == current[0] + 1
                        and checkpoint.prior_checkpoint_envelope_sha256 == current[1]
                        and advance.source_snapshot_sequence > current[2]
                        and checkpoint.required_as_of >= current[3]
                    )
                if not valid_advance:
                    return EPCheckpointBatchResult(
                        status="rejected",
                        persisted_checkpoint_envelope_sha256=(),
                    )
                decisions.append("advance")

            if len(set(decisions)) != 1:
                return EPCheckpointBatchResult(
                    status="rejected",
                    persisted_checkpoint_envelope_sha256=(),
                )
            for advance, decision in zip(advances, decisions, strict=True):
                if decision != "advance":
                    continue
                checkpoint = advance.checkpoint
                key = (
                    checkpoint.manifest_type,
                    checkpoint.subject,
                )
                self._state[key] = (
                    checkpoint.checkpoint_generation,
                    advance.checkpoint_envelope_sha256,
                    advance.source_snapshot_sequence,
                    checkpoint.required_as_of,
                    checkpoint.checkpoint_batch_sha256,
                )
            return EPCheckpointBatchResult(
                status=(
                    "idempotent"
                    if all(decision == "idempotent" for decision in decisions)
                    else "advanced"
                ),
                persisted_checkpoint_envelope_sha256=tuple(
                    advance.checkpoint_envelope_sha256 for advance in advances
                ),
                persisted_checkpoint_batch_sha256=batch_sha256,
            )


def _checkpoint_advances(
    checkpoints: tuple[EPSignedSnapshotHighWaterReceipt, EPSignedSnapshotHighWaterReceipt],
    *,
    source_snapshot_sequence: int,
) -> tuple[EPCheckpointAdvance, EPCheckpointAdvance]:
    authority_checkpoint, register_checkpoint = checkpoints

    def build(checkpoint: EPSignedSnapshotHighWaterReceipt) -> EPCheckpointAdvance:
        return EPCheckpointAdvance(
            checkpoint=checkpoint,
            checkpoint_envelope_sha256=build_ep_snapshot_checkpoint_envelope_sha256(checkpoint),
            source_snapshot_sequence=source_snapshot_sequence,
        )

    return build(authority_checkpoint), build(register_checkpoint)


class _BarrierCheckpointStore(EPAtomicCheckpointStore):
    """Deterministically controls competing calls around one atomic delegate."""

    def __init__(
        self,
        delegate: _AtomicMemoryCheckpointStore,
        checkpoint_batch_sha256: tuple[str, ...],
    ) -> None:
        self._delegate = delegate
        self._entered = {batch_sha256: asyncio.Event() for batch_sha256 in checkpoint_batch_sha256}
        self._release = {batch_sha256: asyncio.Event() for batch_sha256 in checkpoint_batch_sha256}

    async def load_trusted_checkpoint_keys(
        self,
    ) -> dict[str, EPTrustedAcquisitionKey]:
        return await self._delegate.load_trusted_checkpoint_keys()

    async def compare_and_advance_atomic(
        self,
        advances: tuple[EPCheckpointAdvance, EPCheckpointAdvance],
    ) -> EPCheckpointBatchResult:
        batch_sha256 = advances[0].checkpoint.checkpoint_batch_sha256
        entered = self._entered.get(batch_sha256)
        release = self._release.get(batch_sha256)
        if entered is not None and release is not None:
            entered.set()
            await release.wait()
        return await self._delegate.compare_and_advance_atomic(advances)

    async def wait_until_entered(self, checkpoint_batch_sha256: str) -> None:
        await self._entered[checkpoint_batch_sha256].wait()

    def release(self, checkpoint_batch_sha256: str) -> None:
        self._release[checkpoint_batch_sha256].set()


def _record(
    kind: Literal["B1", "B2", "B3", "B9"],
    *,
    publication_date: date,
    effective_date: date | None,
    document_id: str | None = None,
    correction_of: str | None = None,
    correction_sequence: int | None = None,
    exception_code: str = "",
    authority_as_of: date = AS_OF,
) -> EPSPublicationRecord:
    correction_code = "NW" if kind != "B9" else f"W{correction_sequence or 1}"
    return EPSPublicationRecord(
        publication_number=PUBLICATION_NUMBER,
        eps_document_id=document_id or f"EP{PUBLICATION_NUMBER}{correction_code}{kind}",
        kind=kind,
        publication_date=publication_date,
        effective_date=effective_date,
        authority_as_of=authority_as_of,
        authority_exception_code=exception_code,
        correction_of_document_id=correction_of,
        correction_sequence=correction_sequence,
    )


def _procedure(
    *,
    complete: bool = True,
    authority_complete: bool = True,
    state: EPCentralProcedureState = EPCentralProcedureState.CLEAR,
    appeal: EPSuspensiveAppealState = EPSuspensiveAppealState.NOT_APPLICABLE,
    publication_number: str = PUBLICATION_NUMBER,
    record_count: int = 1,
    records: list[EPSPublicationRecord] | None = None,
    coverage_from: date | None = None,
    source_locator: str | None = None,
    binding_override: str | None = None,
    as_of: date = AS_OF,
    snapshot_sequence: int = 1,
) -> EPCentralProcedureEvidence:
    raw = b"<register complete='true'/>" if complete else None
    coverage_start = coverage_from or date(1978, 1, 1)
    default_record = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    if publication_number != PUBLICATION_NUMBER:
        default_record = EPSPublicationRecord.model_validate(
            {
                **default_record.model_dump(mode="python"),
                "publication_number": publication_number,
                "eps_document_id": f"EP{publication_number}NWB1",
            }
        )
    semantic_records = records or [default_record]
    source_document_id = f"EP{publication_number}"
    locator = source_locator or (
        f"https://register.epo.org/application?number={source_document_id}"
    )
    register_sha256 = hashlib.sha256(raw).hexdigest() if raw else None
    authority: EPAuthorityCoverageEvidence | None = None
    if authority_complete:
        authority_raw = (f"official-authority-bundle:{publication_number}:{record_count}").encode()
        authority_sha256 = hashlib.sha256(authority_raw).hexdigest()
        authority_locator = (
            "https://link.epo.org/web/publication-server/authority-file/"
            "EP-Authority-File_202626.csv.zip"
        )
        authority_manifest = EPAuthorityAcquisitionManifest(
            schema_version="epo-authority-acquisition-v1",
            snapshot_sequence=snapshot_sequence,
            acquired_at=datetime.now(UTC),
            publication_number=publication_number,
            source_bundle_sha256=authority_sha256,
            authority_snapshot_locator=authority_locator,
            snapshot_coverage_from=coverage_start,
            snapshot_coverage_through=as_of,
            records=tuple(
                EPAuthorityManifestRecord(
                    publication_number=record.publication_number,
                    eps_document_id=record.eps_document_id,
                    kind=record.kind,
                    publication_date=record.publication_date,
                    authority_exception_code=record.authority_exception_code,
                    correction_of_document_id=record.correction_of_document_id,
                    correction_sequence=record.correction_sequence,
                )
                for record in semantic_records
            ),
        )
        authority = EPAuthorityCoverageEvidence(
            publication_number=publication_number,
            coverage_method="ep_authority_file",
            source_locator=authority_locator,
            coverage_from=coverage_start,
            coverage_through=as_of,
            retrieved_at=datetime.now(UTC),
            record_count=record_count,
            retained_authority_bytes=authority_raw,
            retained_authority_sha256=authority_sha256,
            evidence_binding_sha256=build_ep_authority_evidence_binding_sha256(
                publication_number=publication_number,
                coverage_method="ep_authority_file",
                source_locator=authority_locator,
                coverage_from=coverage_start,
                coverage_through=as_of,
                record_count=record_count,
                retained_authority_sha256=authority_sha256,
            ),
            acquisition_receipt=_signed_receipt(authority_manifest, "authority"),
        )
    register_receipt: EPSignedAcquisitionReceipt | None = None
    if complete and raw is not None:
        ordered_records = sorted(
            semantic_records,
            key=lambda record: record.effective_date or record.publication_date,
        )
        events = tuple(
            EPRegisterProcedureEvent(
                sequence=index,
                event_code=f"DERIVED_{record.kind}",
                event_date=record.effective_date or record.publication_date,
                resulting_state=(
                    state if index == len(ordered_records) else EPCentralProcedureState.CLEAR
                ),
                suspensive_appeal_state=(
                    appeal
                    if index == len(ordered_records)
                    else EPSuspensiveAppealState.NOT_APPLICABLE
                ),
                affected_document_id=record.eps_document_id,
                effective_date=record.effective_date,
            )
            for index, record in enumerate(ordered_records, start=1)
        )
        register_manifest = EPRegisterAcquisitionManifest(
            schema_version="epo-register-acquisition-v1",
            snapshot_sequence=snapshot_sequence,
            acquired_at=datetime.now(UTC),
            source_document_id=source_document_id,
            source_locator=locator,
            as_of=as_of,
            source_artifact_sha256=hashlib.sha256(raw).hexdigest(),
            events=events,
        )
        register_receipt = _signed_receipt(register_manifest, "register")
    return EPCentralProcedureEvidence(
        source_document_id=source_document_id,
        source_locator=locator,
        as_of=as_of,
        retrieved_at=datetime.now(UTC),
        register_complete=complete,
        authority_coverage=authority,
        central_state=state,
        suspensive_appeal_state=appeal,
        retained_register_bytes=raw,
        retained_register_sha256=register_sha256,
        evidence_binding_sha256=(
            binding_override
            if binding_override is not None
            else (
                build_ep_procedure_evidence_binding_sha256(
                    source_document_id=source_document_id,
                    source_locator=locator,
                    as_of=as_of,
                    retained_register_sha256=register_sha256,
                )
                if register_sha256
                else None
            )
        ),
        acquisition_receipt=register_receipt,
    )


def _xml(
    record: EPSPublicationRecord,
    *,
    correction_code: str | None = None,
    claims: tuple[tuple[int, str], ...] = (
        (1, "A compound comprising feature alpha."),
        (2, "The compound of claim 1, comprising feature beta."),
    ),
    doc_number: str = PUBLICATION_NUMBER,
    kind: str | None = None,
    root_language: str = "en",
    proceedings_language: str | None = None,
    claims_language: str | None = None,
    additional_claim_sections: tuple[tuple[str, tuple[tuple[int, str], ...]], ...] = (),
) -> bytes:
    correction = (
        f"<correction-code>{correction_code}</correction-code>"
        if correction_code is not None
        else ""
    )

    def claims_section(
        language: str,
        language_claims: tuple[tuple[int, str], ...],
    ) -> str:
        claim_xml = "".join(
            f'<claim num="{number:04d}"><claim-text>{number}. {text}</claim-text></claim>'
            for number, text in language_claims
        )
        return f'<claims lang="{language}">{claim_xml}</claims>'

    claims_xml = claims_section(claims_language or root_language, claims)
    claims_xml += "".join(
        claims_section(language, language_claims)
        for language, language_claims in additional_claim_sections
    )
    procedure_language = proceedings_language or root_language
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE ep-patent-document PUBLIC "-//EPO//EP PATENT DOCUMENT 1.4//EN" '
        '"ep-patent-document-v1-4.dtd">'
        f'<ep-patent-document id="EP99123456{kind or record.kind}" '
        f'file="EP99123456NW{kind or record.kind}.xml" lang="{root_language}" country="EP" '
        f'doc-number="{doc_number}" kind="{kind or record.kind}" '
        f'date-publ="{record.publication_date:%Y%m%d}">'
        f"<SDOBI><B000><B015EP>{correction}</B015EP></B000>"
        f"<B200><B251EP>{procedure_language}</B251EP></B200></SDOBI>"
        f"{claims_xml}"
        "</ep-patent-document>"
    ).encode()


def _transport(
    records: list[EPSPublicationRecord],
    *,
    xml_by_id: dict[str, bytes] | None = None,
    pdf_by_id: dict[str, bytes] | None = None,
    calls: list[str] | None = None,
) -> httpx.MockTransport:
    by_id = {record.eps_document_id: record for record in records}

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(request.url))
        document_id = request.url.path.split("/")[-2]
        media_format = request.url.path.rsplit(".", 1)[-1]
        record = by_id[document_id]
        if media_format == "xml":
            body = (xml_by_id or {}).get(document_id, _xml(record))
            return httpx.Response(200, content=body, headers={"Content-Type": "application/xml"})
        body = (pdf_by_id or {}).get(document_id, PDF_BYTES)
        return httpx.Response(200, content=body, headers={"Content-Type": "application/pdf"})

    return httpx.MockTransport(handler)


async def _resolve(
    records: list[EPSPublicationRecord],
    procedure: EPCentralProcedureEvidence | None = None,
    *,
    xml_by_id: dict[str, bytes] | None = None,
    pdf_by_id: dict[str, bytes] | None = None,
    trusted_keys: dict[str, EPTrustedAcquisitionKey] | None = None,
):
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        transport=_transport(
            records,
            xml_by_id=xml_by_id,
            pdf_by_id=pdf_by_id,
        ),
    ) as http:
        client = EPOPublicationServerClient(
            client=http,
            retry_delays=(),
            trusted_acquisition_public_keys=trusted_keys or TEST_TRUSTED_KEYS,
        )
        effective_procedure = procedure or _procedure(
            record_count=len(records),
            records=records,
            coverage_from=min(record.publication_date for record in records),
        )
        return await client.resolve_historical_central_claims(
            PUBLICATION_NUMBER,
            records,
            effective_procedure,
            historical_as_of=AS_OF,
        )


@pytest.mark.asyncio
async def test_retains_exact_xml_pdf_hashes_ids_and_dates() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    xml = _xml(b1)
    result = await _resolve([b1], xml_by_id={b1.eps_document_id: xml})

    assert result.status == EPClaimsResolutionStatus.RESOLVED
    assert result.selected_document_id == b1.eps_document_id
    artifact = result.artifacts[0]
    assert artifact.record.kind == "B1"
    assert artifact.record.publication_date == date(2026, 1, 7)
    assert artifact.record.effective_date == date(2026, 1, 7)
    assert artifact.xml_document_id == "EP99123456B1"
    assert artifact.xml_file_name == "EP99123456NWB1.xml"
    assert artifact.xml.raw_bytes == xml
    assert artifact.xml.sha256 == hashlib.sha256(xml).hexdigest()
    assert artifact.pdf.raw_bytes == PDF_BYTES
    assert artifact.pdf.sha256 == hashlib.sha256(PDF_BYTES).hexdigest()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("selected_document_id", "EP1234567NWB2"),
        ("selected_kind", "B3"),
        ("selected_effective_date", date(2026, 1, 8)),
        ("selected_claims_text_sha256", "0" * 64),
    ],
)
async def test_result_validator_binds_every_selected_field_to_exact_artifact(
    field: str,
    replacement: object,
) -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    result = await _resolve([b1])
    payload = result.model_dump(mode="python")
    payload[field] = replacement

    with pytest.raises(ValidationError, match="selected"):
        EPControllingClaimsResolution.model_validate(payload)


@pytest.mark.asyncio
async def test_artifact_model_reparses_xml_and_rejects_forged_derived_fields() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    result = await _resolve([b1])
    artifact_payload = result.artifacts[0].model_dump(mode="python")

    forged_language = {**artifact_payload, "proceedings_language": "fr"}
    with pytest.raises(ValidationError, match="derived fields"):
        type(result.artifacts[0]).model_validate(forged_language)

    forged_text = "1. Forged claim text."
    forged_claims = {
        **artifact_payload,
        "claims_text": forged_text,
        "claims_text_sha256": hashlib.sha256(forged_text.encode()).hexdigest(),
    }
    with pytest.raises(ValidationError, match="derived fields"):
        type(result.artifacts[0]).model_validate(forged_claims)


@pytest.mark.asyncio
async def test_selects_only_language_of_proceedings_claims_not_english_translation() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    multilingual_xml = _xml(
        b1,
        root_language="en",
        proceedings_language="de",
        claims_language="de",
        claims=((1, "Eine Verbindung mit Merkmal alpha."),),
        additional_claim_sections=(
            ("en", ((1, "An English translation that must not control."),)),
        ),
    )

    result = await _resolve(
        [b1],
        xml_by_id={b1.eps_document_id: multilingual_xml},
    )

    assert result.status == EPClaimsResolutionStatus.RESOLVED
    assert result.artifacts[0].xml_root_language == "en"
    assert result.artifacts[0].proceedings_language == "de"
    assert result.artifacts[0].claims_text == "1. Eine Verbindung mit Merkmal alpha."
    assert "English translation" not in result.artifacts[0].claims_text


@pytest.mark.asyncio
async def test_missing_language_of_proceedings_claims_fails_closed() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    translation_only_xml = _xml(
        b1,
        root_language="en",
        proceedings_language="fr",
        claims_language="en",
        claims=((1, "An English translation only."),),
    )

    with pytest.raises(SourceUnavailableError, match="language-of-proceedings"):
        await _resolve(
            [b1],
            xml_by_id={b1.eps_document_id: translation_only_xml},
        )


@pytest.mark.asyncio
async def test_resolves_b2_or_b3_by_explicit_effective_date_not_highest_kind_code() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2025, 1, 8),
        effective_date=date(2025, 1, 8),
    )
    b3 = _record(
        "B3",
        publication_date=date(2026, 2, 4),
        effective_date=date(2026, 2, 1),
    )
    b2 = _record(
        "B2",
        publication_date=date(2026, 6, 3),
        effective_date=date(2026, 6, 1),
    )

    result = await _resolve([b1, b3, b2])

    assert result.status == EPClaimsResolutionStatus.RESOLVED
    assert result.selected_kind == "B2"
    assert result.selected_document_id == b2.eps_document_id


@pytest.mark.asyncio
async def test_b9_complete_reprint_replaces_only_its_exact_target() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    b9 = _record(
        "B9",
        publication_date=date(2026, 2, 4),
        effective_date=date(2026, 2, 4),
        correction_of=b1.eps_document_id,
        correction_sequence=1,
    )
    corrected_xml = _xml(
        b9,
        correction_code="W1B1",
        claims=((1, "A corrected compound claim."),),
    )

    result = await _resolve(
        [b1, b9],
        xml_by_id={b9.eps_document_id: corrected_xml},
    )

    assert result.status == EPClaimsResolutionStatus.RESOLVED
    assert result.selected_kind == "B9"
    assert result.selected_document_id == b9.eps_document_id
    selected = next(
        artifact
        for artifact in result.artifacts
        if artifact.record.eps_document_id == result.selected_document_id
    )
    assert selected.claims_text == "1. A corrected compound claim."


@pytest.mark.asyncio
async def test_b9_xml_correction_target_must_match_manifest_exactly() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    b9 = _record(
        "B9",
        publication_date=date(2026, 2, 4),
        effective_date=date(2026, 2, 4),
        correction_of=b1.eps_document_id,
        correction_sequence=1,
    )
    conflicting_xml = _xml(b9, correction_code="W2B1")

    with pytest.raises(SourceUnavailableError, match="correction linkage"):
        await _resolve(
            [b1, b9],
            xml_by_id={b9.eps_document_id: conflicting_xml},
        )


@pytest.mark.asyncio
async def test_retrograde_first_b9_effective_date_is_indeterminate_without_fetch() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 2, 4),
        effective_date=date(2026, 2, 4),
    )
    retrograde_b9 = _record(
        "B9",
        publication_date=date(2026, 3, 4),
        effective_date=date(2026, 1, 1),
        correction_of=b1.eps_document_id,
        correction_sequence=1,
    )

    result = await _resolve([b1, retrograde_b9])

    assert result.status == EPClaimsResolutionStatus.INDETERMINATE
    assert result.reason == EPClaimsResolutionReason.CORRECTION_CHAIN_INCOMPLETE
    assert result.artifacts == ()


@pytest.mark.asyncio
async def test_retrograde_later_b9_chain_effective_date_is_indeterminate() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    b9_w1 = _record(
        "B9",
        publication_date=date(2026, 2, 4),
        effective_date=date(2026, 2, 4),
        correction_of=b1.eps_document_id,
        correction_sequence=1,
    )
    b9_w2 = _record(
        "B9",
        publication_date=date(2026, 3, 4),
        effective_date=date(2026, 1, 20),
        correction_of=b1.eps_document_id,
        correction_sequence=2,
    )

    result = await _resolve([b1, b9_w1, b9_w2])

    assert result.status == EPClaimsResolutionStatus.INDETERMINATE
    assert result.reason == EPClaimsResolutionReason.CORRECTION_CHAIN_INCOMPLETE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("procedure", "reason"),
    [
        (
            _procedure(state=EPCentralProcedureState.OPPOSITION_PENDING),
            EPClaimsResolutionReason.CENTRAL_PROCEEDING_PENDING,
        ),
        (
            _procedure(
                state=EPCentralProcedureState.APPEAL_PENDING,
                appeal=EPSuspensiveAppealState.UNRESOLVED,
            ),
            EPClaimsResolutionReason.SUSPENSIVE_APPEAL_UNRESOLVED,
        ),
        (
            _procedure(
                state=EPCentralProcedureState.CLEAR,
                appeal=EPSuspensiveAppealState.UNRESOLVED,
            ),
            EPClaimsResolutionReason.SUSPENSIVE_APPEAL_UNRESOLVED,
        ),
        (
            _procedure(complete=False, state=EPCentralProcedureState.UNKNOWN),
            EPClaimsResolutionReason.PROCEDURE_EVIDENCE_MISSING,
        ),
    ],
)
async def test_unresolved_or_missing_procedure_is_indeterminate(
    procedure: EPCentralProcedureEvidence,
    reason: EPClaimsResolutionReason,
) -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )

    result = await _resolve([b1], procedure)

    assert result.status == EPClaimsResolutionStatus.INDETERMINATE
    assert result.reason == reason
    assert result.selected_document_id is None


@pytest.mark.asyncio
async def test_procedure_evidence_for_another_ep_has_explicit_mismatch_reason() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    other_ep_procedure = _procedure(publication_number="7654321")

    result = await _resolve([b1], other_ep_procedure)

    assert result.status == EPClaimsResolutionStatus.INDETERMINATE
    assert result.reason == EPClaimsResolutionReason.PROCEDURE_SUBJECT_MISMATCH
    assert result.artifacts == ()


def test_procedure_evidence_rejects_non_epo_or_subject_mismatched_locator() -> None:
    with pytest.raises(ValidationError, match="locator"):
        _procedure(
            source_locator=("https://register.epo.org/application?number=EP7654321"),
        )
    with pytest.raises(ValidationError, match="locator"):
        _procedure(
            source_locator=(
                f"https://register.epo.org.evil.example/application?number=EP{PUBLICATION_NUMBER}"
            ),
        )


def test_procedure_evidence_rejects_subject_binding_mismatch() -> None:
    with pytest.raises(ValidationError, match="binding does not match EP subject"):
        _procedure(binding_override="0" * 64)


@pytest.mark.asyncio
async def test_self_hashed_fake_authority_bytes_fail_signed_content_binding() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    procedure = _procedure(records=[b1])
    original = procedure.authority_coverage
    assert original is not None
    fake_bytes = b"arbitrary caller authority assertion"
    fake_sha256 = hashlib.sha256(fake_bytes).hexdigest()
    forged_coverage = EPAuthorityCoverageEvidence.model_validate(
        {
            **original.model_dump(mode="python"),
            "retained_authority_bytes": fake_bytes,
            "retained_authority_sha256": fake_sha256,
            "evidence_binding_sha256": build_ep_authority_evidence_binding_sha256(
                publication_number=original.publication_number,
                coverage_method=original.coverage_method,
                source_locator=original.source_locator,
                coverage_from=original.coverage_from,
                coverage_through=original.coverage_through,
                record_count=original.record_count,
                retained_authority_sha256=fake_sha256,
            ),
        }
    )
    forged_procedure = EPCentralProcedureEvidence.model_validate(
        {
            **procedure.model_dump(mode="python"),
            "authority_coverage": forged_coverage,
        }
    )

    result = await _resolve([b1], forged_procedure)

    assert result.reason == EPClaimsResolutionReason.AUTHORITY_CONTENT_MISMATCH
    assert result.artifacts == ()


@pytest.mark.asyncio
async def test_caller_signed_authority_assertion_is_untrusted_without_allowlisted_key() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    procedure = _procedure(records=[b1])
    original = procedure.authority_coverage
    assert original is not None
    attacker_key = Ed25519PrivateKey.from_private_bytes(b"\x22" * 32)
    attacker_receipt = _raw_signed_receipt(
        json.loads(original.acquisition_receipt.manifest_bytes),
        "authority",
        private_key=attacker_key,
        key_id="attacker-controlled-key",
    )
    forged_coverage = EPAuthorityCoverageEvidence.model_validate(
        {
            **original.model_dump(mode="python"),
            "acquisition_receipt": attacker_receipt,
        }
    )
    forged_procedure = EPCentralProcedureEvidence.model_validate(
        {
            **procedure.model_dump(mode="python"),
            "authority_coverage": forged_coverage,
        }
    )

    result = await _resolve([b1], forged_procedure)

    assert result.reason == EPClaimsResolutionReason.AUTHORITY_EVIDENCE_UNTRUSTED


@pytest.mark.asyncio
async def test_no_acquisition_keyring_is_indeterminate_without_network() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    calls: list[str] = []
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        transport=_transport([b1], calls=calls),
    ) as http:
        client = EPOPublicationServerClient(client=http, retry_delays=())
        result = await client.resolve_current_central_claims(
            PUBLICATION_NUMBER,
            [b1],
            _procedure(records=[b1]),
        )

    assert result.reason == EPClaimsResolutionReason.AUTHORITY_EVIDENCE_UNTRUSTED
    assert calls == []


@pytest.mark.asyncio
async def test_one_weekly_url_cannot_assert_continuous_coverage() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    procedure = _procedure(records=[b1])
    original = procedure.authority_coverage
    assert original is not None
    invalid_weekly_manifest = {
        "schema_version": "epo-authority-acquisition-v1",
        "publication_number": PUBLICATION_NUMBER,
        "source_bundle_sha256": original.retained_authority_sha256,
        "authority_snapshot_locator": original.source_locator,
        "snapshot_coverage_from": "1978-01-01",
        "snapshot_coverage_through": "2026-06-01",
        "publication_calendar_locator": (
            "https://data.epo.org/publication-server/rest/v1.2/publication-dates"
        ),
        "publication_calendar_artifact_sha256": "a" * 64,
        "calendar_observed_at": "2026-06-24",
        "publication_dates_after_snapshot": ["2026-06-03", "2026-06-10"],
        "weekly_acquisitions": [
            {
                "publication_date": "2026-06-03",
                "source_locator": (
                    "https://data.epo.org/publication-server/rest/v1.2/"
                    "publication-dates/20260603/patents"
                ),
                "source_artifact_sha256": "b" * 64,
            }
        ],
        "records": [
            {
                "publication_number": PUBLICATION_NUMBER,
                "eps_document_id": b1.eps_document_id,
                "kind": "B1",
                "publication_date": "2026-01-07",
                "authority_exception_code": "",
                "correction_of_document_id": None,
                "correction_sequence": None,
            }
        ],
    }
    invalid_receipt = _raw_signed_receipt(invalid_weekly_manifest, "authority")
    invalid_coverage = EPAuthorityCoverageEvidence.model_validate(
        {
            **original.model_dump(mode="python"),
            "coverage_method": "eps_weekly_publication_lists",
            "evidence_binding_sha256": build_ep_authority_evidence_binding_sha256(
                publication_number=original.publication_number,
                coverage_method="eps_weekly_publication_lists",
                source_locator=original.source_locator,
                coverage_from=original.coverage_from,
                coverage_through=original.coverage_through,
                record_count=original.record_count,
                retained_authority_sha256=original.retained_authority_sha256,
            ),
            "acquisition_receipt": invalid_receipt,
        }
    )
    invalid_procedure = EPCentralProcedureEvidence.model_validate(
        {
            **procedure.model_dump(mode="python"),
            "authority_coverage": invalid_coverage,
        }
    )

    result = await _resolve([b1], invalid_procedure)

    assert result.reason == EPClaimsResolutionReason.AUTHORITY_CONTENT_MISMATCH


@pytest.mark.asyncio
async def test_fake_register_bytes_or_state_fail_signed_semantic_comparison() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    procedure = _procedure(
        records=[b1],
        state=EPCentralProcedureState.CENTRALLY_REVOKED,
    )
    fake_register = b"arbitrary caller register assertion"
    fake_sha256 = hashlib.sha256(fake_register).hexdigest()
    forged_bytes_procedure = EPCentralProcedureEvidence.model_validate(
        {
            **procedure.model_dump(mode="python"),
            "retained_register_bytes": fake_register,
            "retained_register_sha256": fake_sha256,
            "evidence_binding_sha256": build_ep_procedure_evidence_binding_sha256(
                source_document_id=procedure.source_document_id,
                source_locator=procedure.source_locator,
                as_of=procedure.as_of,
                retained_register_sha256=fake_sha256,
            ),
        }
    )
    bytes_result = await _resolve([b1], forged_bytes_procedure)
    assert bytes_result.reason == EPClaimsResolutionReason.PROCEDURE_CONTENT_MISMATCH

    forged_state_procedure = EPCentralProcedureEvidence.model_validate(
        {
            **procedure.model_dump(mode="python"),
            "central_state": EPCentralProcedureState.CLEAR,
        }
    )
    state_result = await _resolve([b1], forged_state_procedure)
    assert state_result.reason == EPClaimsResolutionReason.PROCEDURE_CONTENT_MISMATCH


@pytest.mark.asyncio
async def test_completed_central_revocation_is_terminal_no_claims_and_skips_media() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    calls: list[str] = []
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        transport=_transport([b1], calls=calls),
    ) as http:
        client = EPOPublicationServerClient(
            client=http,
            retry_delays=(),
            trusted_acquisition_public_keys=TEST_TRUSTED_KEYS,
        )
        result = await client.resolve_historical_central_claims(
            PUBLICATION_NUMBER,
            [b1],
            _procedure(state=EPCentralProcedureState.CENTRALLY_REVOKED),
            historical_as_of=AS_OF,
        )

    assert result.status == EPClaimsResolutionStatus.NO_CENTRAL_CLAIMS
    assert result.reason == EPClaimsResolutionReason.CENTRALLY_REVOKED
    assert result.selected_document_id is None
    assert result.artifacts == ()
    assert calls == []


@pytest.mark.asyncio
async def test_central_revocation_with_unresolved_appeal_remains_indeterminate() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )

    result = await _resolve(
        [b1],
        _procedure(
            state=EPCentralProcedureState.CENTRALLY_REVOKED,
            appeal=EPSuspensiveAppealState.UNRESOLVED,
        ),
    )

    assert result.status == EPClaimsResolutionStatus.INDETERMINATE
    assert result.reason == EPClaimsResolutionReason.SUSPENSIVE_APPEAL_UNRESOLVED


def test_register_manifest_rejects_duplicate_effective_assignments() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    with pytest.raises(ValidationError, match="duplicate effective assignments"):
        _procedure(record_count=2, records=[b1, b1])


@pytest.mark.asyncio
async def test_conflicting_same_effective_date_is_indeterminate() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2025, 1, 8),
        effective_date=date(2025, 1, 8),
    )
    b2 = _record(
        "B2",
        publication_date=date(2026, 5, 6),
        effective_date=date(2026, 5, 1),
    )
    b3 = _record(
        "B3",
        publication_date=date(2026, 5, 13),
        effective_date=date(2026, 5, 1),
    )

    result = await _resolve([b1, b2, b3])

    assert result.status == EPClaimsResolutionStatus.INDETERMINATE
    assert result.reason == EPClaimsResolutionReason.CONFLICTING_PUBLICATION


@pytest.mark.asyncio
async def test_missing_b9_correction_sequence_is_indeterminate_without_fetch() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    b9_w2 = _record(
        "B9",
        publication_date=date(2026, 3, 4),
        effective_date=date(2026, 3, 4),
        correction_of=b1.eps_document_id,
        correction_sequence=2,
    )

    result = await _resolve([b1, b9_w2])

    assert result.status == EPClaimsResolutionStatus.INDETERMINATE
    assert result.reason == EPClaimsResolutionReason.CORRECTION_CHAIN_INCOMPLETE
    assert result.artifacts == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("xml_override", "pdf_override", "message"),
    [
        (b"<ep-patent-document", None, "truncated, unsafe, or malformed"),
        (None, b"%PDF-1.7\nmissing eof", "truncated or missing its EOF marker"),
    ],
)
async def test_truncated_or_corrupt_media_never_degrades_silently(
    xml_override: bytes | None,
    pdf_override: bytes | None,
    message: str,
) -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    xml_by_id = {b1.eps_document_id: xml_override} if xml_override is not None else None
    pdf_by_id = {b1.eps_document_id: pdf_override} if pdf_override is not None else None

    with pytest.raises(SourceUnavailableError, match=message):
        await _resolve([b1], xml_by_id=xml_by_id, pdf_by_id=pdf_by_id)


@pytest.mark.asyncio
async def test_duplicate_claim_numbers_are_rejected_as_incomplete() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    bad_xml = _xml(
        b1,
        claims=((1, "First claim."), (1, "Duplicate first claim.")),
    )

    with pytest.raises(SourceUnavailableError, match="truncated, duplicated"):
        await _resolve([b1], xml_by_id={b1.eps_document_id: bad_xml})


@pytest.mark.asyncio
async def test_declared_oversize_xml_is_rejected_without_reading_or_pdf_fallback() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            200,
            content=b"<not-read/>",
            headers={
                "Content-Type": "application/xml",
                "Content-Length": str(EPS_XML_MAX_BYTES + 1),
            },
        )

    async with httpx.AsyncClient(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
    ) as http:
        client = EPOPublicationServerClient(
            client=http,
            retry_delays=(),
            trusted_acquisition_public_keys=TEST_TRUSTED_KEYS,
        )
        with pytest.raises(SourceUnavailableError, match="retained-media limit"):
            await client.resolve_historical_central_claims(
                PUBLICATION_NUMBER,
                [b1],
                _procedure(),
                historical_as_of=AS_OF,
            )

    assert len(calls) == 1
    assert calls[0].endswith("/document.xml")


@pytest.mark.asyncio
async def test_transient_failures_use_bounded_retries_then_exact_media() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    xml_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal xml_attempts
        if request.url.path.endswith(".xml"):
            xml_attempts += 1
            if xml_attempts < 3:
                return httpx.Response(503, headers={"Content-Type": "text/plain"})
            return httpx.Response(
                200,
                content=_xml(b1),
                headers={"Content-Type": "application/xml"},
            )
        return httpx.Response(
            200,
            content=PDF_BYTES,
            headers={"Content-Type": "application/pdf"},
        )

    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    async with httpx.AsyncClient(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
    ) as http:
        client = EPOPublicationServerClient(
            client=http,
            retry_delays=(0.25, 1.0),
            sleep=record_sleep,
            trusted_acquisition_public_keys=TEST_TRUSTED_KEYS,
        )
        result = await client.resolve_historical_central_claims(
            PUBLICATION_NUMBER,
            [b1],
            _procedure(),
            historical_as_of=AS_OF,
        )

    assert result.status == EPClaimsResolutionStatus.RESOLVED
    assert xml_attempts == 3
    assert delays == [0.25, 1.0]


@pytest.mark.asyncio
async def test_manifest_document_404_is_failure_without_kind_probe_or_pdf_fallback() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(404, headers={"Content-Type": "text/plain"})

    async with httpx.AsyncClient(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
    ) as http:
        client = EPOPublicationServerClient(
            client=http,
            retry_delays=(),
            trusted_acquisition_public_keys=TEST_TRUSTED_KEYS,
        )
        with pytest.raises(SourceUnavailableError, match="status 200"):
            await client.resolve_historical_central_claims(
                PUBLICATION_NUMBER,
                [b1],
                _procedure(),
                historical_as_of=AS_OF,
            )

    assert calls == [f"{BASE_URL}/patents/{b1.eps_document_id}/document.xml"]


@pytest.mark.asyncio
async def test_injected_http_client_must_use_exact_canonical_epo_base_url() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=b"not allowed")

    async with httpx.AsyncClient(
        base_url="https://evil.example/publication-server/rest/v1.2",
        transport=httpx.MockTransport(handler),
    ) as http:
        with pytest.raises(ValueError, match="canonical EPO URL"):
            EPOPublicationServerClient(client=http)

    assert calls == []


@pytest.mark.asyncio
async def test_publication_record_count_cap_fails_before_network() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2025, 1, 1),
        effective_date=date(2025, 1, 1),
    )
    corrections = [
        _record(
            "B9",
            publication_date=date(2026, 1, 1) + timedelta(days=index),
            effective_date=date(2026, 1, 1) + timedelta(days=index),
            document_id=f"EP{PUBLICATION_NUMBER}W{index}B9",
            correction_of=b1.eps_document_id,
            correction_sequence=index,
        )
        for index in range(1, 65)
    ]
    records = [b1, *corrections]
    calls: list[str] = []
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        transport=_transport(records, calls=calls),
    ) as http:
        client = EPOPublicationServerClient(
            client=http,
            retry_delays=(),
            trusted_acquisition_public_keys=TEST_TRUSTED_KEYS,
        )
        result = await client.resolve_current_central_claims(
            PUBLICATION_NUMBER,
            records,
            _procedure(record_count=64),
        )

    assert result.reason == EPClaimsResolutionReason.RESOURCE_LIMIT_EXCEEDED
    assert calls == []


@pytest.mark.asyncio
async def test_aggregate_media_cap_stops_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    monkeypatch.setattr(epo_publication_server, "EPS_AGGREGATE_MAX_BYTES", 1)

    def fail_if_artifact_constructed(**_kwargs: object) -> None:
        raise AssertionError("artifact constructed after aggregate budget exhaustion")

    monkeypatch.setattr(
        epo_publication_server,
        "EPSPublicationArtifact",
        fail_if_artifact_constructed,
    )
    with pytest.raises(SourceUnavailableError, match="aggregate resource limit"):
        await _resolve([b1])


def test_media_model_rejects_xml_over_limit_before_artifact_reparse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(epo_publication_models, "EPS_XML_MAX_BYTES", 4)
    raw_bytes = b"12345"
    with pytest.raises(ValidationError, match="model-level byte limit"):
        EPSMediaArtifact(
            media_format="xml",
            source_url=(f"{BASE_URL}/patents/EP{PUBLICATION_NUMBER}NWB1/document.xml"),
            content_type="application/xml",
            retrieved_at=datetime.now(UTC),
            raw_bytes=raw_bytes,
            sha256=hashlib.sha256(raw_bytes).hexdigest(),
        )


@pytest.mark.asyncio
async def test_authority_exception_and_incomplete_manifest_are_indeterminate() -> None:
    b1_exception = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
        exception_code="C",
    )
    exception_result = await _resolve([b1_exception])

    assert exception_result.reason == EPClaimsResolutionReason.AUTHORITY_EXCEPTION_PRESENT

    clean_b1 = b1_exception.model_copy(update={"authority_exception_code": ""})
    incomplete_result = await _resolve(
        [clean_b1],
        _procedure(authority_complete=False),
    )
    assert incomplete_result.reason == EPClaimsResolutionReason.AUTHORITY_MANIFEST_INCOMPLETE


def test_register_manifest_rejects_future_revocation_and_effective_date() -> None:
    with pytest.raises(ValidationError, match="cannot postdate"):
        EPRegisterAcquisitionManifest(
            schema_version="epo-register-acquisition-v1",
            snapshot_sequence=2,
            acquired_at=datetime.now(UTC),
            source_document_id=f"EP{PUBLICATION_NUMBER}",
            source_locator=(f"https://register.epo.org/application?number=EP{PUBLICATION_NUMBER}"),
            as_of=AS_OF,
            source_artifact_sha256="a" * 64,
            events=(
                EPRegisterProcedureEvent(
                    sequence=1,
                    event_code="CENTRAL_REVOCATION",
                    event_date=AS_OF + timedelta(days=1),
                    resulting_state=EPCentralProcedureState.CENTRALLY_REVOKED,
                    suspensive_appeal_state=EPSuspensiveAppealState.RESOLVED,
                    affected_document_id=f"EP{PUBLICATION_NUMBER}NWB1",
                    effective_date=AS_OF + timedelta(days=1),
                ),
            ),
        )


@pytest.mark.asyncio
async def test_redirect_with_valid_xml_body_is_rejected_before_parsing() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            302,
            content=_xml(b1),
            headers={
                "Content-Type": "application/xml",
                "Location": f"{BASE_URL}/patents/{b1.eps_document_id}/document.xml",
            },
        )

    async with httpx.AsyncClient(
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as http:
        client = EPOPublicationServerClient(
            client=http,
            retry_delays=(),
            trusted_acquisition_public_keys=TEST_TRUSTED_KEYS,
        )
        with pytest.raises(SourceUnavailableError, match="status 200"):
            await client.resolve_historical_central_claims(
                PUBLICATION_NUMBER,
                [b1],
                _procedure(records=[b1]),
                historical_as_of=AS_OF,
            )

    assert calls == [f"{BASE_URL}/patents/{b1.eps_document_id}/document.xml"]


@pytest.mark.asyncio
async def test_duplicate_json_keys_are_rejected_even_with_valid_signature() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    procedure = _procedure(records=[b1])
    coverage = procedure.authority_coverage
    assert coverage is not None
    original_bytes = coverage.acquisition_receipt.manifest_bytes
    duplicate_bytes = b'{"schema_version":"epo-authority-acquisition-v1",' + original_bytes[1:]
    forged_receipt = _receipt_from_manifest_bytes(duplicate_bytes, "authority")
    forged_coverage = coverage.model_copy(update={"acquisition_receipt": forged_receipt})
    forged_procedure = procedure.model_copy(update={"authority_coverage": forged_coverage})

    result = await _resolve([b1], forged_procedure)

    assert result.reason == EPClaimsResolutionReason.AUTHORITY_EVIDENCE_UNTRUSTED


@pytest.mark.asyncio
async def test_invalid_signature_is_rejected_before_manifest_json_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    procedure = _procedure(records=[b1])
    coverage = procedure.authority_coverage
    assert coverage is not None
    invalid_receipt = coverage.acquisition_receipt.model_copy(update={"signature": b"\x00" * 64})
    forged_procedure = procedure.model_copy(
        update={
            "authority_coverage": coverage.model_copy(
                update={"acquisition_receipt": invalid_receipt}
            )
        }
    )

    def fail_if_parsed(_raw_bytes: bytes) -> dict[str, object]:
        raise AssertionError("unverified manifest bytes were parsed")

    monkeypatch.setattr(
        epo_publication_server,
        "_parse_canonical_json_object",
        fail_if_parsed,
    )
    result = await _resolve([b1], forged_procedure)

    assert result.reason == EPClaimsResolutionReason.AUTHORITY_EVIDENCE_UNTRUSTED


@pytest.mark.asyncio
async def test_valid_signature_still_rejects_excessive_json_nesting() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    procedure = _procedure(records=[b1])
    coverage = procedure.authority_coverage
    assert coverage is not None
    nested_bytes = (
        b'{"schema_version":"epo-authority-acquisition-v1","nested":'
        + (b"[" * 25)
        + b"0"
        + (b"]" * 25)
        + b"}"
    )
    nested_receipt = _receipt_from_manifest_bytes(nested_bytes, "authority")
    forged_procedure = procedure.model_copy(
        update={
            "authority_coverage": coverage.model_copy(
                update={"acquisition_receipt": nested_receipt}
            )
        }
    )

    result = await _resolve([b1], forged_procedure)

    assert result.reason == EPClaimsResolutionReason.AUTHORITY_EVIDENCE_UNTRUSTED


@pytest.mark.asyncio
async def test_authority_only_key_cannot_verify_register_receipt() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )

    result = await _resolve(
        [b1],
        trusted_keys={AUTHORITY_ACQUISITION_KEY_ID: AUTHORITY_ACQUISITION_TRUSTED_KEY},
    )

    assert result.reason == EPClaimsResolutionReason.PROCEDURE_EVIDENCE_UNTRUSTED


@pytest.mark.asyncio
@pytest.mark.parametrize("key_status", ["expired", "revoked"])
async def test_expired_or_revoked_key_is_rejected(key_status: str) -> None:
    key_data = AUTHORITY_ACQUISITION_TRUSTED_KEY.model_dump(mode="python")
    if key_status == "expired":
        key_data.update(
            {
                "not_after": datetime(2025, 1, 1, tzinfo=UTC),
                "revoked_at": None,
                "status": "active",
            }
        )
    else:
        key_data.update(
            {
                "status": "revoked",
                "revoked_at": datetime.now(UTC),
            }
        )
    trusted_key = EPTrustedAcquisitionKey.model_validate(key_data)
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )

    result = await _resolve(
        [b1],
        trusted_keys={
            **TEST_TRUSTED_KEYS,
            AUTHORITY_ACQUISITION_KEY_ID: trusted_key,
        },
    )

    assert result.reason == EPClaimsResolutionReason.AUTHORITY_EVIDENCE_UNTRUSTED


@pytest.mark.asyncio
async def test_new_floor_then_old_floor_replay_is_rejected_atomically() -> None:
    today = datetime.now(UTC).date()
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
        authority_as_of=today,
    )
    old_procedure = _procedure(records=[b1], as_of=today, snapshot_sequence=1)
    old_authority_floor, old_register_floor = _high_water_pair(
        old_procedure,
        required_as_of=today,
    )
    new_procedure = _procedure(records=[b1], as_of=today, snapshot_sequence=2)
    new_authority_floor, new_register_floor = _high_water_pair(
        new_procedure,
        required_as_of=today,
        authority_minimum_snapshot_sequence=2,
        register_minimum_snapshot_sequence=2,
        authority_checkpoint_generation=2,
        register_checkpoint_generation=2,
        authority_prior_checkpoint_envelope_sha256=(
            build_ep_snapshot_checkpoint_envelope_sha256(old_authority_floor)
        ),
        register_prior_checkpoint_envelope_sha256=(
            build_ep_snapshot_checkpoint_envelope_sha256(old_register_floor)
        ),
    )
    calls: list[str] = []
    store = _AtomicMemoryCheckpointStore()
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        transport=_transport([b1], calls=calls),
    ) as http:
        client = EPOPublicationServerClient(
            client=http,
            retry_delays=(),
            trusted_acquisition_public_keys=TEST_TRUSTED_KEYS,
            resolution_config=EPOPublicationResolutionConfig(max_evidence_age_days=1),
            checkpoint_store=store,
        )
        old_result = await client.resolve_current_central_claims(
            PUBLICATION_NUMBER,
            [b1],
            old_procedure,
            authority_high_water=old_authority_floor,
            register_high_water=old_register_floor,
            required_as_of=today,
        )
        new_result = await client.resolve_current_central_claims(
            PUBLICATION_NUMBER,
            [b1],
            new_procedure,
            authority_high_water=new_authority_floor,
            register_high_water=new_register_floor,
            required_as_of=today,
        )
        calls_before_replay = len(calls)
        replay_result = await client.resolve_current_central_claims(
            PUBLICATION_NUMBER,
            [b1],
            old_procedure,
            authority_high_water=old_authority_floor,
            register_high_water=old_register_floor,
            required_as_of=today,
        )

    assert old_result.status == EPClaimsResolutionStatus.RESOLVED
    assert new_result.status == EPClaimsResolutionStatus.RESOLVED
    assert replay_result.reason == EPClaimsResolutionReason.EVIDENCE_ROLLBACK_DETECTED
    assert replay_result.resolution_mode == "current"
    assert len(calls) == calls_before_replay


@pytest.mark.asyncio
async def test_checkpoint_namespace_does_not_reset_at_required_as_of_boundary() -> None:
    today = datetime.now(UTC).date()
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
        authority_as_of=today,
    )
    generation_one_procedure = _procedure(records=[b1], as_of=today, snapshot_sequence=1)
    generation_one = _high_water_pair(
        generation_one_procedure,
        required_as_of=today,
    )
    generation_one_advances = _checkpoint_advances(
        generation_one,
        source_snapshot_sequence=1,
    )
    store = _AtomicMemoryCheckpointStore()

    initial = await store.compare_and_advance_atomic(generation_one_advances)
    next_day_generation_one = _high_water_pair(
        generation_one_procedure,
        required_as_of=today + timedelta(days=1),
    )
    reset_attempt = await store.compare_and_advance_atomic(
        _checkpoint_advances(next_day_generation_one, source_snapshot_sequence=1)
    )

    assert initial.status == "advanced"
    assert reset_attempt.status == "rejected"


@pytest.mark.asyncio
async def test_checkpoint_store_rejects_backdated_generation_advance() -> None:
    today = datetime.now(UTC).date()
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
        authority_as_of=today,
    )
    generation_one_procedure = _procedure(records=[b1], as_of=today, snapshot_sequence=1)
    generation_one = _high_water_pair(
        generation_one_procedure,
        required_as_of=today,
    )
    store = _AtomicMemoryCheckpointStore()
    initial = await store.compare_and_advance_atomic(
        _checkpoint_advances(generation_one, source_snapshot_sequence=1)
    )
    generation_two_procedure = _procedure(records=[b1], as_of=today, snapshot_sequence=2)
    generation_two = _high_water_pair(
        generation_two_procedure,
        required_as_of=today - timedelta(days=1),
        authority_minimum_snapshot_sequence=2,
        register_minimum_snapshot_sequence=2,
        authority_checkpoint_generation=2,
        register_checkpoint_generation=2,
        authority_prior_checkpoint_envelope_sha256=(
            build_ep_snapshot_checkpoint_envelope_sha256(generation_one[0])
        ),
        register_prior_checkpoint_envelope_sha256=(
            build_ep_snapshot_checkpoint_envelope_sha256(generation_one[1])
        ),
    )
    backdated = await store.compare_and_advance_atomic(
        _checkpoint_advances(generation_two, source_snapshot_sequence=2)
    )

    assert initial.status == "advanced"
    assert backdated.status == "rejected"


@pytest.mark.asyncio
async def test_checkpoint_store_rejects_mixed_idempotent_and_advance_batch() -> None:
    today = datetime.now(UTC).date()
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
        authority_as_of=today,
    )
    old_procedure = _procedure(records=[b1], as_of=today, snapshot_sequence=1)
    old_checkpoints = _high_water_pair(old_procedure, required_as_of=today)
    store = _AtomicMemoryCheckpointStore()
    assert (
        await store.compare_and_advance_atomic(
            _checkpoint_advances(old_checkpoints, source_snapshot_sequence=1)
        )
    ).status == "advanced"
    new_procedure = _procedure(records=[b1], as_of=today, snapshot_sequence=2)
    new_checkpoints = _high_water_pair(
        new_procedure,
        required_as_of=today,
        authority_minimum_snapshot_sequence=2,
        register_minimum_snapshot_sequence=2,
        authority_checkpoint_generation=2,
        register_checkpoint_generation=2,
        authority_prior_checkpoint_envelope_sha256=(
            build_ep_snapshot_checkpoint_envelope_sha256(old_checkpoints[0])
        ),
        register_prior_checkpoint_envelope_sha256=(
            build_ep_snapshot_checkpoint_envelope_sha256(old_checkpoints[1])
        ),
    )
    new_advances = _checkpoint_advances(new_checkpoints, source_snapshot_sequence=2)
    register_advance = new_advances[1]
    register_checkpoint = register_advance.checkpoint
    store._state[("register", register_checkpoint.subject)] = (
        register_checkpoint.checkpoint_generation,
        register_advance.checkpoint_envelope_sha256,
        register_advance.source_snapshot_sequence,
        register_checkpoint.required_as_of,
        register_checkpoint.checkpoint_batch_sha256,
    )

    mixed = await store.compare_and_advance_atomic(new_advances)

    assert mixed.status == "rejected"
    authority_state = store._state[("authority", new_checkpoints[0].subject)]
    assert authority_state[0] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("winner_index", [0, 1])
async def test_concurrent_checkpoint_forks_have_one_deterministic_winner(
    winner_index: int,
) -> None:
    today = datetime.now(UTC).date()
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
        authority_as_of=today,
    )
    generation_one_procedure = _procedure(records=[b1], as_of=today, snapshot_sequence=1)
    generation_one = _high_water_pair(
        generation_one_procedure,
        required_as_of=today,
    )
    delegate = _AtomicMemoryCheckpointStore()
    initial = await delegate.compare_and_advance_atomic(
        _checkpoint_advances(generation_one, source_snapshot_sequence=1)
    )
    assert initial.status == "advanced"
    authority_prior = build_ep_snapshot_checkpoint_envelope_sha256(generation_one[0])
    register_prior = build_ep_snapshot_checkpoint_envelope_sha256(generation_one[1])
    fork_checkpoints = tuple(
        _high_water_pair(
            _procedure(records=[b1], as_of=today, snapshot_sequence=sequence),
            required_as_of=today,
            authority_minimum_snapshot_sequence=sequence,
            register_minimum_snapshot_sequence=sequence,
            authority_checkpoint_generation=2,
            register_checkpoint_generation=2,
            authority_prior_checkpoint_envelope_sha256=authority_prior,
            register_prior_checkpoint_envelope_sha256=register_prior,
        )
        for sequence in (2, 3)
    )
    fork_advances = (
        _checkpoint_advances(fork_checkpoints[0], source_snapshot_sequence=2),
        _checkpoint_advances(fork_checkpoints[1], source_snapshot_sequence=3),
    )
    batch_ids = tuple(pair[0].checkpoint_batch_sha256 for pair in fork_checkpoints)
    store = _BarrierCheckpointStore(delegate, batch_ids)
    tasks = tuple(
        asyncio.create_task(store.compare_and_advance_atomic(advances))
        for advances in fork_advances
    )
    await asyncio.gather(*(store.wait_until_entered(batch_id) for batch_id in batch_ids))

    store.release(batch_ids[winner_index])
    winner = await tasks[winner_index]
    loser_index = 1 - winner_index
    store.release(batch_ids[loser_index])
    loser = await tasks[loser_index]

    assert winner.status == "advanced"
    assert loser.status == "rejected"
    assert (await delegate.compare_and_advance_atomic(fork_advances[winner_index])).status == (
        "idempotent"
    )
    assert (await delegate.compare_and_advance_atomic(fork_advances[loser_index])).status == (
        "rejected"
    )


@pytest.mark.asyncio
async def test_concurrent_new_floor_linearizes_before_old_replay() -> None:
    today = datetime.now(UTC).date()
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
        authority_as_of=today,
    )
    old_procedure = _procedure(records=[b1], as_of=today, snapshot_sequence=1)
    old_checkpoints = _high_water_pair(old_procedure, required_as_of=today)
    old_advances = _checkpoint_advances(old_checkpoints, source_snapshot_sequence=1)
    delegate = _AtomicMemoryCheckpointStore()
    assert (await delegate.compare_and_advance_atomic(old_advances)).status == "advanced"
    new_procedure = _procedure(records=[b1], as_of=today, snapshot_sequence=2)
    new_checkpoints = _high_water_pair(
        new_procedure,
        required_as_of=today,
        authority_minimum_snapshot_sequence=2,
        register_minimum_snapshot_sequence=2,
        authority_checkpoint_generation=2,
        register_checkpoint_generation=2,
        authority_prior_checkpoint_envelope_sha256=(
            build_ep_snapshot_checkpoint_envelope_sha256(old_checkpoints[0])
        ),
        register_prior_checkpoint_envelope_sha256=(
            build_ep_snapshot_checkpoint_envelope_sha256(old_checkpoints[1])
        ),
    )
    new_advances = _checkpoint_advances(new_checkpoints, source_snapshot_sequence=2)
    new_batch = new_checkpoints[0].checkpoint_batch_sha256
    old_batch = old_checkpoints[0].checkpoint_batch_sha256
    store = _BarrierCheckpointStore(delegate, (new_batch, old_batch))
    new_task = asyncio.create_task(store.compare_and_advance_atomic(new_advances))
    old_task = asyncio.create_task(store.compare_and_advance_atomic(old_advances))
    await asyncio.gather(
        store.wait_until_entered(new_batch),
        store.wait_until_entered(old_batch),
    )

    store.release(new_batch)
    new_result = await new_task
    store.release(old_batch)
    old_result = await old_task

    assert new_result.status == "advanced"
    assert old_result.status == "rejected"
    assert (await delegate.compare_and_advance_atomic(new_advances)).status == "idempotent"


@pytest.mark.asyncio
async def test_valid_canonical_current_snapshot_resolves_with_signed_high_water() -> None:
    today = datetime.now(UTC).date()
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
        authority_as_of=today,
    )
    procedure = _procedure(records=[b1], as_of=today)
    authority_floor, register_floor = _high_water_pair(
        procedure,
        required_as_of=today,
    )
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        transport=_transport([b1]),
        follow_redirects=False,
    ) as http:
        client = EPOPublicationServerClient(
            client=http,
            retry_delays=(),
            trusted_acquisition_public_keys=TEST_TRUSTED_KEYS,
            checkpoint_store=_AtomicMemoryCheckpointStore(),
        )
        result = await client.resolve_current_central_claims(
            PUBLICATION_NUMBER,
            [b1],
            procedure,
            authority_high_water=authority_floor,
            register_high_water=register_floor,
            required_as_of=today,
        )

    assert result.status == EPClaimsResolutionStatus.RESOLVED
    assert result.resolution_mode == "current"
    assert result.required_as_of == today


@pytest.mark.asyncio
async def test_caller_checkpoints_cannot_establish_current_state_without_store() -> None:
    today = datetime.now(UTC).date()
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
        authority_as_of=today,
    )
    procedure = _procedure(records=[b1], as_of=today)
    authority_floor, register_floor = _high_water_pair(
        procedure,
        required_as_of=today,
    )
    calls: list[str] = []
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        transport=_transport([b1], calls=calls),
    ) as http:
        client = EPOPublicationServerClient(
            client=http,
            retry_delays=(),
            trusted_acquisition_public_keys=TEST_TRUSTED_KEYS,
        )
        result = await client.resolve_current_central_claims(
            PUBLICATION_NUMBER,
            [b1],
            procedure,
            authority_high_water=authority_floor,
            register_high_water=register_floor,
            required_as_of=today,
        )

    assert result.reason == EPClaimsResolutionReason.CHECKPOINT_STORE_UNAVAILABLE
    assert calls == []


@pytest.mark.asyncio
async def test_checkpoint_binds_complete_signed_acquisition_envelope() -> None:
    today = datetime.now(UTC).date()
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
        authority_as_of=today,
    )
    original_procedure = _procedure(records=[b1], as_of=today)
    coverage = original_procedure.authority_coverage
    assert coverage is not None
    replacement_receipt = _receipt_from_manifest_bytes(
        coverage.acquisition_receipt.manifest_bytes,
        "authority",
    )
    replacement_coverage = coverage.model_copy(update={"acquisition_receipt": replacement_receipt})
    replacement_procedure = original_procedure.model_copy(
        update={"authority_coverage": replacement_coverage}
    )
    authority_floor_for_original_envelope, _original_register_floor = _high_water_pair(
        original_procedure,
        required_as_of=today,
    )
    _replacement_authority_floor, register_floor = _high_water_pair(
        replacement_procedure,
        required_as_of=today,
    )
    assert replacement_receipt.manifest_sha256 == coverage.acquisition_receipt.manifest_sha256
    assert build_ep_acquisition_envelope_sha256(
        replacement_receipt
    ) != build_ep_acquisition_envelope_sha256(coverage.acquisition_receipt)
    assert (
        authority_floor_for_original_envelope.checkpoint_batch_sha256
        != register_floor.checkpoint_batch_sha256
    )
    calls: list[str] = []
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        transport=_transport([b1], calls=calls),
    ) as http:
        client = EPOPublicationServerClient(
            client=http,
            retry_delays=(),
            trusted_acquisition_public_keys=TEST_TRUSTED_KEYS,
            checkpoint_store=_AtomicMemoryCheckpointStore(),
        )
        result = await client.resolve_current_central_claims(
            PUBLICATION_NUMBER,
            [b1],
            replacement_procedure,
            authority_high_water=authority_floor_for_original_envelope,
            register_high_water=register_floor,
            required_as_of=today,
        )

    assert result.reason == EPClaimsResolutionReason.EVIDENCE_ROLLBACK_DETECTED
    assert calls == []


@pytest.mark.asyncio
async def test_checkpoint_key_material_cannot_duplicate_acquisition_key_material() -> None:
    today = datetime.now(UTC).date()
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
        authority_as_of=today,
    )
    procedure = _procedure(records=[b1], as_of=today)
    authority_floor, register_floor = _high_water_pair(
        procedure,
        required_as_of=today,
    )

    class DuplicateMaterialStore(_AtomicMemoryCheckpointStore):
        async def load_trusted_checkpoint_keys(
            self,
        ) -> dict[str, EPTrustedAcquisitionKey]:
            duplicate = AUTHORITY_CHECKPOINT_TRUSTED_KEY.model_copy(
                update={"public_key": AUTHORITY_ACQUISITION_TRUSTED_KEY.public_key}
            )
            return {
                duplicate.key_id: duplicate,
                REGISTER_CHECKPOINT_TRUSTED_KEY.key_id: REGISTER_CHECKPOINT_TRUSTED_KEY,
            }

    calls: list[str] = []
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        transport=_transport([b1], calls=calls),
    ) as http:
        client = EPOPublicationServerClient(
            client=http,
            retry_delays=(),
            trusted_acquisition_public_keys=TEST_TRUSTED_KEYS,
            checkpoint_store=DuplicateMaterialStore(),
        )
        result = await client.resolve_current_central_claims(
            PUBLICATION_NUMBER,
            [b1],
            procedure,
            authority_high_water=authority_floor,
            register_high_water=register_floor,
            required_as_of=today,
        )

    assert result.reason == EPClaimsResolutionReason.EVIDENCE_ROLLBACK_DETECTED
    assert calls == []


@pytest.mark.asyncio
async def test_injected_client_with_redirect_following_enabled_is_rejected() -> None:
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200)),
        follow_redirects=True,
    ) as http:
        with pytest.raises(ValueError, match="disable redirect following"):
            EPOPublicationServerClient(client=http)


@pytest.mark.asyncio
async def test_historical_api_requires_exact_named_snapshot_without_network() -> None:
    b1 = _record(
        "B1",
        publication_date=date(2026, 1, 7),
        effective_date=date(2026, 1, 7),
    )
    calls: list[str] = []
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        transport=_transport([b1], calls=calls),
    ) as http:
        client = EPOPublicationServerClient(
            client=http,
            retry_delays=(),
            trusted_acquisition_public_keys=TEST_TRUSTED_KEYS,
        )
        requested = AS_OF - timedelta(days=1)
        result = await client.resolve_historical_central_claims(
            PUBLICATION_NUMBER,
            [b1],
            _procedure(records=[b1]),
            historical_as_of=requested,
        )

    assert result.reason == EPClaimsResolutionReason.RESOLUTION_AS_OF_MISMATCH
    assert result.resolution_mode == "historical"
    assert result.required_as_of == requested
    assert calls == []
