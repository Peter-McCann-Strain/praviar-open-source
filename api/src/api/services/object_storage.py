"""Google Cloud Storage object operations.

Thin wrapper around `google.cloud.storage.Client` providing the object operations
the application uses: upload, signed URL, download, delete, and guarded prefix
deletion. The wrapper exists
so the call sites in the API and pipeline don't import the underlying SDK
directly — easier to test, easier to swap providers.

Replaces the never-implemented R2 storage paths declared in
`api/src/api/config.py` (per the GCP migration in 10-gcp-architecture.md §6.4 —
the R2 settings existed but no code paths used them, so this is a greenfield
implementation, not a rewrite).

Auth: relies on Application Default Credentials (ADC). When running on Cloud
Run, the runtime service account (`praviar-api` or `praviar-workers`) has
`roles/storage.objectAdmin` granted by the IAM Terraform module. Locally,
`gcloud auth application-default login` works.

Usage:
    from api.services.object_storage import ObjectStorage

    storage = ObjectStorage(bucket="praviar-prod-reports")
    storage.upload_bytes("reports/abc123.pdf", b"<pdf bytes>", content_type="application/pdf")
    url = storage.signed_url("reports/abc123.pdf", expires_minutes=15)
    storage.delete_blob("reports/abc123.pdf")
    storage.delete_prefix("exports/tenant-id/")
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from importlib import import_module
from typing import IO, Any, cast
from urllib.parse import quote

import structlog

from api.metrics import record_provider_call
from api.observability.spans import record_span_exception, start_span

logger = structlog.get_logger()

DEFAULT_DOWNLOAD_CHUNK_SIZE_BYTES = 1024 * 1024
MAX_DOWNLOAD_CHUNK_SIZE_BYTES = 8 * 1024 * 1024


def _record_storage_call(operation: str, started: float, status: str) -> None:
    record_provider_call(
        provider="gcs",
        operation=f"object_storage.{operation}",
        duration_s=time.perf_counter() - started,
        errored=status != "success",
    )


@dataclass(frozen=True)
class GCSUri:
    bucket: str
    blob_path: str


def parse_gs_uri(uri: str) -> GCSUri:
    """Parse a gs://bucket/blob URI and reject malformed object references."""
    if not uri.startswith("gs://"):
        raise ValueError("GCS URI must start with gs://")
    remainder = uri.removeprefix("gs://")
    bucket, separator, blob_path = remainder.partition("/")
    if not bucket or not separator or not blob_path:
        raise ValueError("GCS URI must include a bucket and object path")
    if blob_path.startswith("/") or ".." in blob_path.split("/"):
        raise ValueError("GCS object path must not contain traversal segments")
    return GCSUri(bucket=bucket, blob_path=blob_path)


class ObjectStorage:
    """Thin GCS wrapper. One instance per logical bucket.

    The internal `_client` and `_bucket` are typed `Any` because the
    `google-cloud-storage` SDK ships incomplete type stubs that Pyright
    cannot follow through bucket → blob → operation chains. The runtime
    behavior matches the documented SDK signatures.
    """

    _client: Any
    _bucket: Any

    def __init__(
        self,
        bucket: str,
        project: str | None = None,
        *,
        operation_timeout: float = 30.0,
    ) -> None:
        storage = import_module("google.cloud.storage")
        self._client = storage.Client(project=project) if project else storage.Client()
        self._bucket_name = bucket
        self._bucket = self._client.bucket(bucket)
        self._operation_timeout = operation_timeout

    @property
    def bucket(self) -> str:
        return self._bucket_name

    def upload_bytes(
        self,
        blob_path: str,
        data: bytes,
        *,
        content_type: str | None = None,
        cache_control: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Upload bytes. Returns the gs:// URI."""
        started = time.perf_counter()
        with start_span(
            "object_storage.upload_bytes",
            {"storage.bucket": self._bucket_name, "storage.operation": "upload_bytes"},
        ) as span:
            try:
                blob = self._bucket.blob(blob_path)
                if cache_control is not None:
                    blob.cache_control = cache_control
                if metadata is not None:
                    blob.metadata = metadata
                blob.upload_from_string(
                    data,
                    content_type=content_type,
                    timeout=self._operation_timeout,
                )
            except Exception as exc:
                record_span_exception(span, exc)
                _record_storage_call("upload_bytes", started, "error")
                raise
        _record_storage_call("upload_bytes", started, "success")
        logger.info(
            "object_storage.uploaded",
            bucket=self._bucket_name,
            blob_path=blob_path,
            size=len(data),
            content_type=content_type,
        )
        return f"gs://{self._bucket_name}/{blob_path}"

    def upload_file(
        self,
        blob_path: str,
        file_obj: IO[bytes],
        *,
        content_type: str | None = None,
        cache_control: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Upload from a file-like object. Returns the gs:// URI."""
        started = time.perf_counter()
        with start_span(
            "object_storage.upload_file",
            {"storage.bucket": self._bucket_name, "storage.operation": "upload_file"},
        ) as span:
            try:
                blob = self._bucket.blob(blob_path)
                if cache_control is not None:
                    blob.cache_control = cache_control
                if metadata is not None:
                    blob.metadata = metadata
                blob.upload_from_file(
                    file_obj,
                    content_type=content_type,
                    timeout=self._operation_timeout,
                )
            except Exception as exc:
                record_span_exception(span, exc)
                _record_storage_call("upload_file", started, "error")
                raise
        _record_storage_call("upload_file", started, "success")
        logger.info(
            "object_storage.uploaded_file",
            bucket=self._bucket_name,
            blob_path=blob_path,
            content_type=content_type,
        )
        return f"gs://{self._bucket_name}/{blob_path}"

    def signed_url(
        self,
        blob_path: str,
        *,
        expires_minutes: int = 15,
        method: str = "GET",
        response_disposition: str | None = None,
        response_type: str | None = None,
    ) -> str:
        """V4 signed URL. 15-minute expiry is the safe default for customer-facing report URLs."""
        started = time.perf_counter()
        with start_span(
            "object_storage.signed_url",
            {"storage.bucket": self._bucket_name, "storage.operation": "signed_url"},
        ) as span:
            try:
                blob = self._bucket.blob(blob_path)
                url = cast(
                    str,
                    blob.generate_signed_url(
                        version="v4",
                        expiration=timedelta(minutes=expires_minutes),
                        method=method,
                        response_disposition=response_disposition,
                        response_type=response_type,
                    ),
                )
            except Exception as exc:
                record_span_exception(span, exc)
                _record_storage_call("signed_url", started, "error")
                raise
        _record_storage_call("signed_url", started, "success")
        return url

    def download_blob(self, blob_path: str) -> bytes:
        """Download blob contents as bytes."""
        started = time.perf_counter()
        with start_span(
            "object_storage.download_blob",
            {"storage.bucket": self._bucket_name, "storage.operation": "download_blob"},
        ) as span:
            try:
                blob = self._bucket.blob(blob_path)
                data = cast(bytes, blob.download_as_bytes(timeout=self._operation_timeout))
            except Exception as exc:
                record_span_exception(span, exc)
                _record_storage_call("download_blob", started, "error")
                raise
        _record_storage_call("download_blob", started, "success")
        return data

    def iter_blob(
        self,
        blob_path: str,
        *,
        chunk_size: int = DEFAULT_DOWNLOAD_CHUNK_SIZE_BYTES,
    ) -> Iterator[bytes]:
        """Stream a blob in bounded chunks without buffering the full object."""
        if not 0 < chunk_size <= MAX_DOWNLOAD_CHUNK_SIZE_BYTES:
            raise ValueError(
                f"chunk_size must be between 1 and {MAX_DOWNLOAD_CHUNK_SIZE_BYTES} bytes"
            )

        started = time.perf_counter()
        completed = False
        with start_span(
            "object_storage.iter_blob",
            {"storage.bucket": self._bucket_name, "storage.operation": "iter_blob"},
        ) as span:
            try:
                blob = self._bucket.blob(blob_path)
                with blob.open(
                    "rb",
                    chunk_size=chunk_size,
                    timeout=self._operation_timeout,
                ) as source:
                    while chunk := source.read(chunk_size):
                        yield cast(bytes, chunk)
                completed = True
            except Exception as exc:
                record_span_exception(span, exc)
                raise
            finally:
                _record_storage_call(
                    "iter_blob",
                    started,
                    "success" if completed else "error",
                )

    def delete_blob(self, blob_path: str) -> None:
        """Delete a blob. Idempotent: missing blob is treated as success."""
        started = time.perf_counter()
        with start_span(
            "object_storage.delete_blob",
            {"storage.bucket": self._bucket_name, "storage.operation": "delete_blob"},
        ) as span:
            blob = self._bucket.blob(blob_path)
            try:
                blob.delete(timeout=self._operation_timeout)
                logger.info("object_storage.deleted", bucket=self._bucket_name, blob_path=blob_path)
            except Exception as exc:
                if "404" not in str(exc):
                    record_span_exception(span, exc)
                    _record_storage_call("delete_blob", started, "error")
                    raise
                logger.info(
                    "object_storage.delete_already_gone",
                    bucket=self._bucket_name,
                    blob_path=blob_path,
                )
        _record_storage_call("delete_blob", started, "success")

    def delete_prefix(self, prefix: str) -> int:
        """Delete and verify every object under an exact, bounded prefix.

        Prefix deletion is intentionally stricter than the GCS SDK. Callers
        must provide a directory-like prefix ending in ``/`` so a tenant key
        such as ``exports/org-a/`` can never match ``exports/org-ab/...``.
        Missing prefixes are treated as an idempotent success.
        """
        prefix_parts = prefix[:-1].split("/") if prefix.endswith("/") else []
        if (
            not prefix
            or prefix.startswith("/")
            or not prefix.endswith("/")
            or ".." in prefix.split("/")
            or len(prefix_parts) < 2
            or any(not part for part in prefix_parts)
        ):
            raise ValueError("GCS deletion prefix must be a bounded relative path ending in '/'")

        started = time.perf_counter()
        deleted = 0
        with start_span(
            "object_storage.delete_prefix",
            {
                "storage.bucket": self._bucket_name,
                "storage.operation": "delete_prefix",
                "storage.prefix": prefix,
            },
        ) as span:
            try:
                blobs = list(
                    self._client.list_blobs(
                        self._bucket_name,
                        prefix=prefix,
                        timeout=self._operation_timeout,
                    )
                )
                for blob in blobs:
                    blob_name = cast(str, blob.name)
                    if not blob_name.startswith(prefix):
                        raise RuntimeError(
                            "GCS returned an object outside the requested deletion prefix"
                        )
                    try:
                        blob.delete(timeout=self._operation_timeout)
                        deleted += 1
                    except Exception as exc:
                        if "404" not in str(exc):
                            raise

                remaining = list(
                    self._client.list_blobs(
                        self._bucket_name,
                        prefix=prefix,
                        max_results=1,
                        timeout=self._operation_timeout,
                    )
                )
                if remaining:
                    raise RuntimeError(
                        "GCS prefix deletion could not verify that every object was removed"
                    )
            except Exception as exc:
                record_span_exception(span, exc)
                _record_storage_call("delete_prefix", started, "error")
                raise

        _record_storage_call("delete_prefix", started, "success")
        logger.info(
            "object_storage.prefix_deleted",
            bucket=self._bucket_name,
            prefix=prefix,
            deleted=deleted,
        )
        return deleted

    def exists(self, blob_path: str) -> bool:
        started = time.perf_counter()
        with start_span(
            "object_storage.exists",
            {"storage.bucket": self._bucket_name, "storage.operation": "exists"},
        ) as span:
            try:
                exists = bool(self._bucket.blob(blob_path).exists(timeout=self._operation_timeout))
            except Exception as exc:
                record_span_exception(span, exc)
                _record_storage_call("exists", started, "error")
                raise
        _record_storage_call("exists", started, "success")
        return exists


def content_disposition_attachment(filename: str) -> str:
    """Build a standards-friendly attachment content disposition."""
    safe_fallback = "".join(
        ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in filename
    ).strip("._")
    if not safe_fallback:
        safe_fallback = "export"
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{safe_fallback}\"; filename*=UTF-8''{encoded}"
