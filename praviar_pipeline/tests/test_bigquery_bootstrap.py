from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from praviar_pipeline.clients.bigquery_bootstrap import create_bigquery_client


def test_create_bigquery_client_uses_explicit_credentials_file() -> None:
    settings = SimpleNamespace(
        google_application_credentials="/tmp/bigquery-creds.json",
        bigquery_project_id="test-project",
    )
    credentials = object()
    client = MagicMock(name="bigquery-client")

    with (
        patch("praviar_pipeline.clients.bigquery_bootstrap.get_settings", return_value=settings),
        patch(
            "google.auth.load_credentials_from_file",
            return_value=(credentials, None),
        ) as load_credentials,
        patch("google.cloud.bigquery.Client", return_value=client) as client_cls,
    ):
        result = create_bigquery_client()

    assert result is client
    load_credentials.assert_called_once_with(
        "/tmp/bigquery-creds.json",
        scopes=["https://www.googleapis.com/auth/bigquery"],
    )
    client_cls.assert_called_once_with(
        project="test-project",
        credentials=credentials,
    )


def test_create_bigquery_client_falls_back_to_default_credentials() -> None:
    settings = SimpleNamespace(
        google_application_credentials="",
        bigquery_project_id="test-project",
    )
    credentials = object()
    client = MagicMock(name="bigquery-client")

    with (
        patch("praviar_pipeline.clients.bigquery_bootstrap.get_settings", return_value=settings),
        patch("google.auth.default", return_value=(credentials, None)) as default_auth,
        patch("google.cloud.bigquery.Client", return_value=client) as client_cls,
    ):
        result = create_bigquery_client()

    assert result is client
    default_auth.assert_called_once_with(
        scopes=["https://www.googleapis.com/auth/bigquery"],
    )
    client_cls.assert_called_once_with(
        project="test-project",
        credentials=credentials,
    )
