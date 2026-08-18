from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from api.services.object_storage import MAX_DOWNLOAD_CHUNK_SIZE_BYTES, ObjectStorage


def test_object_storage_applies_operation_timeout_to_sdk_calls() -> None:
    blob = MagicMock()
    bucket = MagicMock()
    bucket.blob.return_value = blob
    client = MagicMock()
    client.bucket.return_value = bucket
    storage_module = SimpleNamespace(Client=MagicMock(return_value=client))

    with patch("api.services.object_storage.import_module", return_value=storage_module):
        storage = ObjectStorage("reports", operation_timeout=12.5)

    with patch("api.services.object_storage.record_provider_call") as metric:
        storage.upload_bytes("a.pdf", b"data", content_type="application/pdf")
        storage.download_blob("a.pdf")
        storage.delete_blob("a.pdf")
        storage.exists("a.pdf")

    blob.upload_from_string.assert_called_once_with(
        b"data",
        content_type="application/pdf",
        timeout=12.5,
    )
    blob.download_as_bytes.assert_called_once_with(timeout=12.5)
    blob.delete.assert_called_once_with(timeout=12.5)
    blob.exists.assert_called_once_with(timeout=12.5)
    assert [call.kwargs["provider"] for call in metric.call_args_list] == [
        "gcs",
        "gcs",
        "gcs",
        "gcs",
    ]
    assert [call.kwargs["operation"] for call in metric.call_args_list] == [
        "object_storage.upload_bytes",
        "object_storage.download_blob",
        "object_storage.delete_blob",
        "object_storage.exists",
    ]
    assert [call.kwargs["errored"] for call in metric.call_args_list] == [
        False,
        False,
        False,
        False,
    ]


def test_object_storage_deletes_and_verifies_exact_prefix() -> None:
    first_blob = MagicMock(name="first_blob")
    first_blob.name = "exports/org-1/analysis-1/report.pdf"
    second_blob = MagicMock(name="second_blob")
    second_blob.name = "exports/org-1/analysis-2/report.docx"
    client = MagicMock()
    client.list_blobs.side_effect = [[first_blob, second_blob], []]
    client.bucket.return_value = MagicMock()
    storage_module = SimpleNamespace(Client=MagicMock(return_value=client))

    with patch("api.services.object_storage.import_module", return_value=storage_module):
        storage = ObjectStorage("reports", operation_timeout=12.5)

    with patch("api.services.object_storage.record_provider_call") as metric:
        deleted = storage.delete_prefix("exports/org-1/")

    assert deleted == 2
    first_blob.delete.assert_called_once_with(timeout=12.5)
    second_blob.delete.assert_called_once_with(timeout=12.5)
    assert client.list_blobs.call_args_list[0].kwargs == {
        "prefix": "exports/org-1/",
        "timeout": 12.5,
    }
    assert client.list_blobs.call_args_list[1].kwargs == {
        "prefix": "exports/org-1/",
        "max_results": 1,
        "timeout": 12.5,
    }
    assert all(call.args[0] == "reports" for call in client.list_blobs.call_args_list)
    assert metric.call_args.kwargs["operation"] == "object_storage.delete_prefix"
    assert metric.call_args.kwargs["errored"] is False


def test_object_storage_prefix_delete_is_idempotent_when_empty() -> None:
    client = MagicMock()
    client.list_blobs.side_effect = [[], []]
    client.bucket.return_value = MagicMock()
    storage_module = SimpleNamespace(Client=MagicMock(return_value=client))

    with patch("api.services.object_storage.import_module", return_value=storage_module):
        storage = ObjectStorage("reports")

    assert storage.delete_prefix("exports/org-1/") == 0


@pytest.mark.parametrize(
    "prefix",
    [
        "",
        "/",
        "exports",
        "exports/org-1",
        "/exports/org-1/",
        "exports/../org-1/",
        "exports//",
    ],
)
def test_object_storage_rejects_unsafe_deletion_prefix(prefix: str) -> None:
    storage = object.__new__(ObjectStorage)

    with pytest.raises(ValueError, match="bounded relative path"):
        storage.delete_prefix(prefix)


def test_object_storage_refuses_object_outside_requested_prefix() -> None:
    wrong_blob = MagicMock()
    wrong_blob.name = "exports/org-10/report.pdf"
    client = MagicMock()
    client.list_blobs.return_value = [wrong_blob]
    client.bucket.return_value = MagicMock()
    storage_module = SimpleNamespace(Client=MagicMock(return_value=client))

    with patch("api.services.object_storage.import_module", return_value=storage_module):
        storage = ObjectStorage("reports")

    with pytest.raises(RuntimeError, match="outside the requested"):
        storage.delete_prefix("exports/org-1/")
    wrong_blob.delete.assert_not_called()


def test_object_storage_fails_if_prefix_verification_finds_residual_object() -> None:
    blob = MagicMock()
    blob.name = "exports/org-1/report.pdf"
    residual = MagicMock()
    residual.name = "exports/org-1/raced-upload.pdf"
    client = MagicMock()
    client.list_blobs.side_effect = [[blob], [residual]]
    client.bucket.return_value = MagicMock()
    storage_module = SimpleNamespace(Client=MagicMock(return_value=client))

    with patch("api.services.object_storage.import_module", return_value=storage_module):
        storage = ObjectStorage("reports")

    with pytest.raises(RuntimeError, match="could not verify"):
        storage.delete_prefix("exports/org-1/")


def test_object_storage_streams_blob_in_bounded_chunks() -> None:
    blob = MagicMock()
    blob.open.return_value = BytesIO(b"abcdefghij")
    bucket = MagicMock()
    bucket.blob.return_value = blob
    client = MagicMock()
    client.bucket.return_value = bucket
    storage_module = SimpleNamespace(Client=MagicMock(return_value=client))

    with patch("api.services.object_storage.import_module", return_value=storage_module):
        storage = ObjectStorage("reports", operation_timeout=12.5)

    with patch("api.services.object_storage.record_provider_call") as metric:
        chunks = list(storage.iter_blob("a.pdf", chunk_size=4))

    assert chunks == [b"abcd", b"efgh", b"ij"]
    assert all(len(chunk) <= 4 for chunk in chunks)
    blob.open.assert_called_once_with("rb", chunk_size=4, timeout=12.5)
    assert metric.call_args.kwargs["operation"] == "object_storage.iter_blob"
    assert metric.call_args.kwargs["errored"] is False


@pytest.mark.parametrize("chunk_size", [0, -1, MAX_DOWNLOAD_CHUNK_SIZE_BYTES + 1])
def test_object_storage_rejects_unbounded_stream_chunk_size(chunk_size: int) -> None:
    storage = object.__new__(ObjectStorage)

    with pytest.raises(ValueError, match="chunk_size"):
        list(storage.iter_blob("a.pdf", chunk_size=chunk_size))
