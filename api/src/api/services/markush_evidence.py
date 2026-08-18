"""Stateless, two-actor PATENTSCOPE Markush evidence receipt service."""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import struct
import zipfile
import zlib
from datetime import UTC, datetime

from praviar_pipeline.checkpoint import CheckpointIntegrityKeyRing
from praviar_pipeline.models.markush_evidence import (
    MarkushEvidenceReceipt,
    build_markush_evidence_receipt,
    verify_markush_evidence_attestation,
)

from api.schemas.markush_evidence import (
    MarkushEvidenceImportRequest,
    MarkushEvidenceVerifyRequest,
)

_MAX_ARTIFACT_BYTES = 25 * 1024 * 1024


def _decode_artifact(encoded: str, *, label: str) -> bytes:
    try:
        artifact = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"{label} is malformed") from None
    if not artifact:
        raise ValueError("PATENTSCOPE evidence artifact cannot be empty")
    if len(artifact) > _MAX_ARTIFACT_BYTES:
        raise ValueError("PATENTSCOPE evidence artifact exceeds 25 MiB")
    return artifact


def _validate_patentscope_export(
    artifact: bytes,
    *,
    filename: str,
    media_type: str,
) -> None:
    expected_media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if not filename.lower().endswith(".xlsx") or media_type != expected_media_type:
        raise ValueError("PATENTSCOPE result evidence must be an XLSX export")
    try:
        with zipfile.ZipFile(io.BytesIO(artifact)) as workbook:
            members = set(workbook.namelist())
    except (OSError, zipfile.BadZipFile):
        raise ValueError("PATENTSCOPE result evidence is not a valid XLSX file") from None
    if not {"[Content_Types].xml", "xl/workbook.xml"}.issubset(members):
        raise ValueError("PATENTSCOPE XLSX evidence lacks workbook structure")


def _validate_controls_capture(
    artifact: bytes,
    *,
    filename: str,
    media_type: str,
) -> None:
    if (
        not filename.lower().endswith(".png")
        or media_type != "image/png"
        or not artifact.startswith(b"\x89PNG\r\n\x1a\n")
    ):
        raise ValueError("PATENTSCOPE controls evidence must be a valid PNG capture")
    position = 8
    dimensions: tuple[int, int] | None = None
    saw_image_data = False
    saw_end = False
    while position + 12 <= len(artifact):
        chunk_length = struct.unpack(">I", artifact[position : position + 4])[0]
        chunk_type = artifact[position + 4 : position + 8]
        chunk_end = position + 12 + chunk_length
        if chunk_end > len(artifact):
            break
        chunk_data = artifact[position + 8 : position + 8 + chunk_length]
        expected_crc = struct.unpack(
            ">I",
            artifact[position + 8 + chunk_length : chunk_end],
        )[0]
        if zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF != expected_crc:
            break
        if chunk_type == b"IHDR" and chunk_length == 13 and dimensions is None:
            dimensions = struct.unpack(">II", chunk_data[:8])
        elif chunk_type == b"IDAT":
            saw_image_data = True
        elif chunk_type == b"IEND" and chunk_length == 0:
            saw_end = True
            position = chunk_end
            break
        position = chunk_end
    if (
        not saw_image_data
        or not saw_end
        or position != len(artifact)
        or dimensions is None
        or dimensions[0] < 640
        or dimensions[1] < 360
    ):
        raise ValueError(
            "PATENTSCOPE controls evidence must be a valid PNG capture of at least 640x360 pixels"
        )


def build_analyst_markush_draft(
    body: MarkushEvidenceImportRequest,
    *,
    analyst_user_id: str,
    analyst_org_id: str,
    integrity_keys: CheckpointIntegrityKeyRing,
) -> MarkushEvidenceReceipt:
    """Create an incomplete, content-addressed draft attributed to the actor."""
    artifact = _decode_artifact(body.artifact_base64, label="artifact_base64")
    controls_artifact = _decode_artifact(
        body.controls_artifact_base64,
        label="controls_artifact_base64",
    )
    _validate_patentscope_export(
        artifact,
        filename=body.artifact_filename,
        media_type=body.artifact_media_type,
    )
    _validate_controls_capture(
        controls_artifact,
        filename=body.controls_artifact_filename,
        media_type=body.controls_artifact_media_type,
    )
    return build_markush_evidence_receipt(
        status="incomplete",
        organization_id=analyst_org_id,
        target_structure=body.target_structure,
        query_structure=body.query_structure,
        query_role=body.query_role,
        chemical_search_mode=body.chemical_search_mode,
        markush_method=body.markush_method,
        markush_match_mode=body.markush_match_mode,
        wipo_query_field=body.wipo_query_field,
        family_grouping_enabled=body.family_grouping_enabled,
        limitations=body.limitations,
        executed_at=body.executed_at,
        server_imported_at=datetime.now(UTC),
        analyst_identity=f"user:{analyst_user_id}",
        artifact_bytes=artifact,
        artifact_filename=body.artifact_filename,
        artifact_media_type=body.artifact_media_type,
        controls_artifact_bytes=controls_artifact,
        controls_artifact_filename=body.controls_artifact_filename,
        controls_artifact_media_type=body.controls_artifact_media_type,
        result_count=body.result_count,
        selected_publication_ids=body.selected_publication_ids,
        attestation_key_id=integrity_keys.active_key_id,
        attestation_key=integrity_keys.active_key(),
    )


def verify_analyst_markush_draft(
    body: MarkushEvidenceVerifyRequest,
    *,
    reviewer_user_id: str,
    reviewer_org_id: str,
    integrity_keys: CheckpointIntegrityKeyRing,
) -> MarkushEvidenceReceipt:
    """Re-hash the original artifact and issue a distinct-reviewer receipt."""
    draft = body.draft_receipt
    if draft.status != "incomplete":
        raise ValueError("only an incomplete analyst receipt can be verified")
    if draft.organization_id != reviewer_org_id:
        raise ValueError("Markush evidence cannot cross organization boundaries")
    reviewer_affirmation = (
        body.query_role,
        body.chemical_search_mode,
        body.markush_method,
        body.markush_match_mode,
        body.wipo_query_field,
        body.family_grouping_enabled,
        body.executed_at,
        body.artifact_filename,
        body.artifact_media_type,
        body.controls_artifact_filename,
        body.controls_artifact_media_type,
        body.result_count,
    )
    analyst_record = (
        draft.query_role,
        draft.chemical_search_mode,
        draft.markush_method,
        draft.markush_match_mode,
        draft.wipo_query_field,
        draft.family_grouping_enabled,
        draft.executed_at,
        draft.artifact_filename,
        draft.artifact_media_type,
        draft.controls_artifact_filename,
        draft.controls_artifact_media_type,
        draft.result_count,
    )
    if reviewer_affirmation != analyst_record:
        raise ValueError("reviewer search-control affirmation does not match the analyst import")
    if draft.attestation_key_id is None:
        raise ValueError("analyst draft lacks server attestation")
    try:
        draft_attestation_key = integrity_keys.verification_key(draft.attestation_key_id)
    except ValueError:
        raise ValueError("analyst draft attestation key is unknown") from None
    if not verify_markush_evidence_attestation(
        draft,
        attestation_key=draft_attestation_key,
    ):
        raise ValueError("analyst draft server attestation is invalid")
    reviewer_identity = f"user:{reviewer_user_id}"
    if draft.analyst_identity == reviewer_identity:
        raise ValueError("Markush analyst and reviewer must be distinct")
    artifact = _decode_artifact(body.artifact_base64, label="artifact_base64")
    controls_artifact = _decode_artifact(
        body.controls_artifact_base64,
        label="controls_artifact_base64",
    )
    if hashlib.sha256(artifact).hexdigest() != draft.imported_artifact_sha256:
        raise ValueError("review artifact digest does not match the analyst import")
    if hashlib.sha256(controls_artifact).hexdigest() != draft.controls_artifact_sha256:
        raise ValueError("review controls artifact digest does not match the analyst import")
    _validate_patentscope_export(
        artifact,
        filename=body.artifact_filename,
        media_type=body.artifact_media_type,
    )
    _validate_controls_capture(
        controls_artifact,
        filename=body.controls_artifact_filename,
        media_type=body.controls_artifact_media_type,
    )
    if draft.executed_at is None or draft.analyst_identity is None:
        raise ValueError("analyst draft lacks execution attribution")
    if (
        draft.artifact_filename is None
        or draft.artifact_media_type is None
        or draft.result_count is None
        or draft.controls_artifact_filename is None
        or draft.controls_artifact_media_type is None
        or draft.server_imported_at is None
    ):
        raise ValueError("analyst draft lacks imported artifact metadata")

    verified = build_markush_evidence_receipt(
        status="verified_manual",
        organization_id=draft.organization_id,
        target_structure=body.target_structure,
        query_structure=body.query_structure,
        query_role=body.query_role,
        chemical_search_mode=body.chemical_search_mode,
        markush_method=body.markush_method,
        markush_match_mode=body.markush_match_mode,
        wipo_query_field=body.wipo_query_field,
        family_grouping_enabled=body.family_grouping_enabled,
        limitations=draft.limitations,
        executed_at=body.executed_at,
        server_imported_at=draft.server_imported_at,
        analyst_identity=draft.analyst_identity,
        reviewer_identity=reviewer_identity,
        artifact_bytes=artifact,
        artifact_filename=body.artifact_filename,
        artifact_media_type=body.artifact_media_type,
        controls_artifact_bytes=controls_artifact,
        controls_artifact_filename=body.controls_artifact_filename,
        controls_artifact_media_type=body.controls_artifact_media_type,
        result_count=body.result_count,
        selected_publication_ids=body.selected_publication_ids,
        attestation_key_id=integrity_keys.active_key_id,
        attestation_key=integrity_keys.active_key(),
    )
    if verified.query_structure_sha256 != draft.query_structure_sha256:
        raise ValueError("review query structure does not match the analyst import")
    if verified.target_structure_sha256 != draft.target_structure_sha256:
        raise ValueError("review target structure does not match the analyst import")
    if verified.selected_publication_ids_sha256 != draft.selected_publication_ids_sha256:
        raise ValueError("review selection does not match the analyst import")
    return verified
