"""Adversarial tests for immutable export receipt bindings."""

from __future__ import annotations

import copy
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from api.db.models import ExportFormat
from api.services.export_receipts import (
    ExportReceiptIntegrityError,
    export_manifest_hash,
    export_manifest_signature,
    verify_export_receipt,
)


def _valid_job() -> SimpleNamespace:
    completed_at = datetime.now(UTC)
    job_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    file_url = f"gs://praviar-exports/exports/org/{analysis_id}/{job_id}/execution/report.pdf"
    artifact_sha256 = hashlib.sha256(b"verified artifact").hexdigest()
    report_payload_sha256 = hashlib.sha256(b"verified report").hexdigest()
    manifest = {
        "version": "export-manifest-v1",
        "generated_at": completed_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "job": {"id": str(job_id), "analysis_id": str(analysis_id)},
        "artifact": {
            "file_size_bytes": 17,
            "format": "pdf",
            "sha256": artifact_sha256,
            "storage_locator_hash": hashlib.sha256(file_url.encode()).hexdigest(),
        },
        "report": {"fingerprint": report_payload_sha256},
    }
    manifest_hash = export_manifest_hash(manifest)
    return SimpleNamespace(
        id=job_id,
        analysis_id=analysis_id,
        format=ExportFormat.PDF,
        file_url=file_url,
        file_size_bytes=17,
        artifact_sha256=artifact_sha256,
        report_payload_sha256=report_payload_sha256,
        completed_at=completed_at,
        manifest_schema_version="export-manifest-v1",
        manifest_snapshot=manifest,
        manifest_hash=manifest_hash,
        manifest_signature=export_manifest_signature(manifest_hash),
    )


def test_completed_export_receipt_verifies_every_binding() -> None:
    verify_export_receipt(_valid_job())


def test_manifest_mutation_without_matching_digest_fails_closed() -> None:
    job = _valid_job()
    job.manifest_snapshot["artifact"]["format"] = "docx"

    with pytest.raises(ExportReceiptIntegrityError, match="manifest digest"):
        verify_export_receipt(job)


@pytest.mark.parametrize(
    ("field", "mutate"),
    [
        (
            "job identity",
            lambda job: job.manifest_snapshot["job"].update(id=str(uuid.uuid4())),
        ),
        (
            "analysis identity",
            lambda job: job.manifest_snapshot["job"].update(analysis_id=str(uuid.uuid4())),
        ),
        (
            "artifact digest",
            lambda job: job.manifest_snapshot["artifact"].update(sha256="a" * 64),
        ),
        (
            "report fingerprint",
            lambda job: job.manifest_snapshot["report"].update(fingerprint="b" * 64),
        ),
        (
            "artifact size",
            lambda job: job.manifest_snapshot["artifact"].update(file_size_bytes=18),
        ),
        (
            "artifact format",
            lambda job: job.manifest_snapshot["artifact"].update(format="docx"),
        ),
        (
            "storage locator",
            lambda job: job.manifest_snapshot["artifact"].update(storage_locator_hash="d" * 64),
        ),
        (
            "completion timestamp",
            lambda job: job.manifest_snapshot.update(
                completed_at=(job.completed_at + timedelta(seconds=1)).isoformat()
            ),
        ),
    ],
)
def test_rehashed_manifest_cannot_replace_job_bindings(field: str, mutate) -> None:
    job = _valid_job()
    job.manifest_snapshot = copy.deepcopy(job.manifest_snapshot)
    mutate(job)
    job.manifest_hash = export_manifest_hash(job.manifest_snapshot)
    job.manifest_signature = export_manifest_signature(job.manifest_hash)

    with pytest.raises(ExportReceiptIntegrityError, match=field):
        verify_export_receipt(job)


def test_rehashed_manifest_without_signing_key_fails_closed() -> None:
    job = _valid_job()
    job.manifest_snapshot = copy.deepcopy(job.manifest_snapshot)
    job.manifest_snapshot["artifact"]["format"] = "docx"
    job.manifest_hash = export_manifest_hash(job.manifest_snapshot)

    with pytest.raises(ExportReceiptIntegrityError, match="manifest signature"):
        verify_export_receipt(job)
