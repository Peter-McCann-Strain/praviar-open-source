"""Integrity contract for completed export receipts.

The manifest is stored beside the export job so every consumer can re-check the
same bindings before exposing either metadata or artifact bytes.  This detects
partial writes, accidental record drift, and tampering that changes a receipt
field without recomputing the complete manifest.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime
from typing import Any

from api.config import get_settings
from api.external_report_delivery_keyring import ExternalReportDeliveryKeyRing

EXPORT_MANIFEST_SCHEMA_VERSION = "export-manifest-v1"
EXPORT_RECEIPT_SIGNATURE_DOMAIN = b"praviar:export-receipt:v1\x00"


class ExportReceiptIntegrityError(RuntimeError):
    """A completed export no longer matches its retained manifest."""


def export_manifest_hash(snapshot: dict[str, Any]) -> str:
    """Return the canonical SHA-256 digest for an export manifest."""
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _export_receipt_hmac_key() -> bytes:
    settings = get_settings()
    keyring = ExternalReportDeliveryKeyRing.from_secret(
        settings.external_report_delivery_keyring_secret.get_secret_value()
    )
    return keyring.operation_hmac_key


def export_manifest_signature(manifest_hash: str) -> str:
    """Sign one canonical manifest digest with the configured operation key."""
    normalized_hash = _hex_sha256(manifest_hash)
    if normalized_hash is None:
        raise ValueError("export manifest hash is invalid")
    return hmac.new(
        _export_receipt_hmac_key(),
        EXPORT_RECEIPT_SIGNATURE_DOMAIN + normalized_hash.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def _hex_sha256(value: object) -> str | None:
    if not isinstance(value, str) or len(value) != 64:
        return None
    normalized = value.lower()
    try:
        bytes.fromhex(normalized)
    except ValueError:
        return None
    return normalized


def _mapping(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return value


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value) or "")


def verify_export_receipt(job: object) -> None:
    """Revalidate every immutable job-to-manifest binding.

    The verifier intentionally accepts an object rather than a database model so
    workers, routes, and focused tests all exercise one exact contract.
    """
    manifest = _mapping(getattr(job, "manifest_snapshot", None))
    if not manifest:
        raise ExportReceiptIntegrityError("export manifest is unavailable")

    schema_version = str(getattr(job, "manifest_schema_version", "") or "")
    if (
        schema_version != EXPORT_MANIFEST_SCHEMA_VERSION
        or manifest.get("version") != schema_version
    ):
        raise ExportReceiptIntegrityError("export manifest schema is invalid")

    retained_manifest_hash = _hex_sha256(getattr(job, "manifest_hash", None))
    if retained_manifest_hash is None or export_manifest_hash(manifest) != retained_manifest_hash:
        raise ExportReceiptIntegrityError("export manifest digest does not match")
    retained_signature = _hex_sha256(getattr(job, "manifest_signature", None))
    if retained_signature is None or not hmac.compare_digest(
        export_manifest_signature(retained_manifest_hash),
        retained_signature,
    ):
        raise ExportReceiptIntegrityError("export manifest signature does not match")

    job_manifest = _mapping(manifest.get("job"))
    artifact = _mapping(manifest.get("artifact"))
    report = _mapping(manifest.get("report"))
    if job_manifest is None or artifact is None or report is None:
        raise ExportReceiptIntegrityError("export manifest bindings are incomplete")

    if str(job_manifest.get("id", "")) != str(getattr(job, "id", "")):
        raise ExportReceiptIntegrityError("export manifest job identity does not match")
    if str(job_manifest.get("analysis_id", "")) != str(getattr(job, "analysis_id", "")):
        raise ExportReceiptIntegrityError("export manifest analysis identity does not match")

    artifact_sha256 = _hex_sha256(getattr(job, "artifact_sha256", None))
    if artifact_sha256 is None or _hex_sha256(artifact.get("sha256")) != artifact_sha256:
        raise ExportReceiptIntegrityError("export artifact digest binding does not match")

    report_sha256 = _hex_sha256(getattr(job, "report_payload_sha256", None))
    if report_sha256 is None or _hex_sha256(report.get("fingerprint")) != report_sha256:
        raise ExportReceiptIntegrityError("export report fingerprint does not match")

    file_size_bytes = getattr(job, "file_size_bytes", None)
    if (
        not isinstance(file_size_bytes, int)
        or file_size_bytes <= 0
        or artifact.get("file_size_bytes") != file_size_bytes
    ):
        raise ExportReceiptIntegrityError("export artifact size binding does not match")

    if str(artifact.get("format", "")) != _enum_value(getattr(job, "format", None)):
        raise ExportReceiptIntegrityError("export artifact format binding does not match")

    file_url = str(getattr(job, "file_url", "") or "")
    locator_hash = _hex_sha256(artifact.get("storage_locator_hash"))
    if (
        not file_url
        or locator_hash is None
        or hashlib.sha256(file_url.encode("utf-8")).hexdigest() != locator_hash
    ):
        raise ExportReceiptIntegrityError("export storage locator binding does not match")

    completed_at = getattr(job, "completed_at", None)
    if not isinstance(completed_at, datetime):
        raise ExportReceiptIntegrityError("export completion timestamp is unavailable")
    if manifest.get("completed_at") != completed_at.isoformat():
        raise ExportReceiptIntegrityError("export completion timestamp binding does not match")
