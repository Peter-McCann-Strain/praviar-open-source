from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from api.services.object_storage import (
    ObjectStorage,
    content_disposition_attachment,
    parse_gs_uri,
)


def _storage(*, project: str | None = None, timeout: float = 7.5):
    blob = MagicMock()
    bucket = MagicMock()
    bucket.blob.return_value = blob
    client = MagicMock()
    client.bucket.return_value = bucket
    storage_module = SimpleNamespace(Client=MagicMock(return_value=client))
    with patch("api.services.object_storage.import_module", return_value=storage_module):
        storage = ObjectStorage("reports", project=project, operation_timeout=timeout)
    return storage, storage_module, client, bucket, blob


def test_parse_gs_uri_returns_bucket_and_nested_object_path() -> None:
    parsed = parse_gs_uri("gs://reports/exports/org-1/report.pdf")

    assert parsed.bucket == "reports"
    assert parsed.blob_path == "exports/org-1/report.pdf"


@pytest.mark.parametrize(
    ("uri", "message"),
    [
        ("https://storage.example/reports/file.pdf", "must start with gs://"),
        ("gs://", "must include a bucket and object path"),
        ("gs://reports", "must include a bucket and object path"),
        ("gs:///file.pdf", "must include a bucket and object path"),
        ("gs://reports//absolute.pdf", "must not contain traversal segments"),
        ("gs://reports/org/../secret.pdf", "must not contain traversal segments"),
    ],
)
def test_parse_gs_uri_rejects_malformed_or_traversing_references(uri: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_gs_uri(uri)


def test_object_storage_constructs_project_client_and_exposes_bucket_name() -> None:
    storage, storage_module, client, _, _ = _storage(project="praviar-test")

    assert storage.bucket == "reports"
    storage_module.Client.assert_called_once_with(project="praviar-test")
    client.bucket.assert_called_once_with("reports")


def test_upload_file_applies_metadata_and_returns_canonical_uri() -> None:
    storage, _, _, _, blob = _storage()
    file_obj = BytesIO(b"report")

    with patch("api.services.object_storage.record_provider_call") as metric:
        uri = storage.upload_file(
            "exports/org-1/report.pdf",
            file_obj,
            content_type="application/pdf",
            cache_control="private, max-age=60",
            metadata={"analysis_id": "analysis-1"},
        )

    assert uri == "gs://reports/exports/org-1/report.pdf"
    assert blob.cache_control == "private, max-age=60"
    assert blob.metadata == {"analysis_id": "analysis-1"}
    blob.upload_from_file.assert_called_once_with(
        file_obj,
        content_type="application/pdf",
        timeout=7.5,
    )
    assert metric.call_args.kwargs["operation"] == "object_storage.upload_file"
    assert metric.call_args.kwargs["errored"] is False


def test_upload_operations_record_provider_and_span_failures() -> None:
    storage, _, _, _, blob = _storage()
    blob.upload_from_string.side_effect = OSError("upload unavailable")

    with (
        patch("api.services.object_storage.record_provider_call") as metric,
        patch("api.services.object_storage.record_span_exception") as record_span,
        pytest.raises(OSError, match="upload unavailable"),
    ):
        storage.upload_bytes(
            "report.pdf",
            b"data",
            cache_control="no-store",
            metadata={"kind": "report"},
        )

    assert blob.cache_control == "no-store"
    assert blob.metadata == {"kind": "report"}
    record_span.assert_called_once()
    assert metric.call_args.kwargs["operation"] == "object_storage.upload_bytes"
    assert metric.call_args.kwargs["errored"] is True


def test_upload_file_records_error_without_reporting_success() -> None:
    storage, _, _, _, blob = _storage()
    blob.upload_from_file.side_effect = RuntimeError("write failed")

    with (
        patch("api.services.object_storage.record_provider_call") as metric,
        patch("api.services.object_storage.record_span_exception") as record_span,
        pytest.raises(RuntimeError, match="write failed"),
    ):
        storage.upload_file("report.pdf", BytesIO(b"report"))

    record_span.assert_called_once()
    assert len(metric.call_args_list) == 1
    assert metric.call_args.kwargs["errored"] is True


def test_signed_url_forwards_download_contract_and_records_success() -> None:
    storage, _, _, _, blob = _storage()
    blob.generate_signed_url.return_value = "https://signed.example/report"

    with patch("api.services.object_storage.record_provider_call") as metric:
        url = storage.signed_url(
            "report.pdf",
            expires_minutes=5,
            method="HEAD",
            response_disposition='attachment; filename="report.pdf"',
            response_type="application/pdf",
        )

    assert url == "https://signed.example/report"
    blob.generate_signed_url.assert_called_once_with(
        version="v4",
        expiration=timedelta(minutes=5),
        method="HEAD",
        response_disposition='attachment; filename="report.pdf"',
        response_type="application/pdf",
    )
    assert metric.call_args.kwargs["operation"] == "object_storage.signed_url"
    assert metric.call_args.kwargs["errored"] is False


@pytest.mark.parametrize(
    ("operation", "invoke"),
    [
        ("signed_url", lambda storage: storage.signed_url("report.pdf")),
        ("download_blob", lambda storage: storage.download_blob("report.pdf")),
        ("exists", lambda storage: storage.exists("report.pdf")),
    ],
)
def test_read_operations_surface_sdk_errors_and_record_failed_metrics(operation, invoke) -> None:
    storage, _, _, _, blob = _storage()
    if operation == "signed_url":
        blob.generate_signed_url.side_effect = OSError("provider down")
    elif operation == "download_blob":
        blob.download_as_bytes.side_effect = OSError("provider down")
    else:
        blob.exists.side_effect = OSError("provider down")

    with (
        patch("api.services.object_storage.record_provider_call") as metric,
        patch("api.services.object_storage.record_span_exception") as record_span,
        pytest.raises(OSError, match="provider down"),
    ):
        invoke(storage)

    record_span.assert_called_once()
    assert metric.call_args.kwargs["operation"] == f"object_storage.{operation}"
    assert metric.call_args.kwargs["errored"] is True


def test_iter_blob_records_failed_metric_when_stream_open_fails() -> None:
    storage, _, _, _, blob = _storage()
    blob.open.side_effect = OSError("stream unavailable")

    with (
        patch("api.services.object_storage.record_provider_call") as metric,
        patch("api.services.object_storage.record_span_exception") as record_span,
        pytest.raises(OSError, match="stream unavailable"),
    ):
        list(storage.iter_blob("report.pdf", chunk_size=1024))

    record_span.assert_called_once()
    assert metric.call_args.kwargs["operation"] == "object_storage.iter_blob"
    assert metric.call_args.kwargs["errored"] is True


def test_delete_blob_treats_not_found_as_idempotent_success() -> None:
    storage, _, _, _, blob = _storage()
    blob.delete.side_effect = RuntimeError("404 object not found")

    with (
        patch("api.services.object_storage.record_provider_call") as metric,
        patch("api.services.object_storage.record_span_exception") as record_span,
    ):
        storage.delete_blob("missing.pdf")

    record_span.assert_not_called()
    assert metric.call_args.kwargs["errored"] is False


def test_delete_blob_surfaces_non_not_found_errors() -> None:
    storage, _, _, _, blob = _storage()
    blob.delete.side_effect = PermissionError("403 forbidden")

    with (
        patch("api.services.object_storage.record_provider_call") as metric,
        patch("api.services.object_storage.record_span_exception") as record_span,
        pytest.raises(PermissionError, match="403 forbidden"),
    ):
        storage.delete_blob("report.pdf")

    record_span.assert_called_once()
    assert metric.call_args.kwargs["errored"] is True


def test_delete_prefix_tolerates_objects_deleted_by_a_concurrent_request() -> None:
    storage, _, client, _, _ = _storage()
    blob = MagicMock(name="raced_blob")
    blob.name = "exports/org-1/report.pdf"
    blob.delete.side_effect = RuntimeError("404 already gone")
    client.list_blobs.side_effect = [[blob], []]

    assert storage.delete_prefix("exports/org-1/") == 0


def test_delete_prefix_surfaces_non_not_found_object_error() -> None:
    storage, _, client, _, _ = _storage()
    blob = MagicMock(name="forbidden_blob")
    blob.name = "exports/org-1/report.pdf"
    blob.delete.side_effect = PermissionError("403 forbidden")
    client.list_blobs.return_value = [blob]

    with (
        patch("api.services.object_storage.record_provider_call") as metric,
        pytest.raises(PermissionError, match="403 forbidden"),
    ):
        storage.delete_prefix("exports/org-1/")

    assert metric.call_args.kwargs["errored"] is True


@pytest.mark.parametrize(
    ("filename", "expected_fallback", "expected_encoded"),
    [
        ("FTO report (final).pdf", "FTO_report__final_.pdf", "FTO%20report%20%28final%29.pdf"),
        ("...", "export", "..."),
        ("résumé.pdf", "résumé.pdf", "r%C3%A9sum%C3%A9.pdf"),
    ],
)
def test_content_disposition_attachment_has_safe_ascii_style_fallback_and_utf8_value(
    filename: str, expected_fallback: str, expected_encoded: str
) -> None:
    disposition = content_disposition_attachment(filename)

    assert f'filename="{expected_fallback}"' in disposition
    assert f"filename*=UTF-8''{expected_encoded}" in disposition
