"""Bootstrap helpers for the BigQuery client."""

from __future__ import annotations

import structlog

from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import ConfigurationError
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

logger = structlog.get_logger()


def create_bigquery_client():
    """Create a BigQuery client from configured credentials."""
    import google.auth
    from google.cloud import bigquery

    settings = get_settings()
    creds_path = settings.google_application_credentials

    credential_failure_type: str | None = None
    try:
        if creds_path:
            credentials, _ = google.auth.load_credentials_from_file(
                creds_path,
                scopes=["https://www.googleapis.com/auth/bigquery"],
            )
            logger.debug(
                "bigquery_credentials_loaded",
                credentials_type=type(credentials).__name__,
            )
        else:
            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/bigquery"]
            )
            logger.debug(
                "bigquery_using_default_credentials",
                credentials_type=type(credentials).__name__,
            )
    except (FileNotFoundError, PermissionError, ValueError, OSError) as exc:
        credential_failure_type = safe_exception_type(exc)
        logger.error("bigquery_no_credentials", error_type=credential_failure_type)
    except Exception as exc:
        credential_failure_type = safe_exception_type(exc)
        logger.error("bigquery_no_credentials", error_type=credential_failure_type)

    if credential_failure_type is not None:
        raise ConfigurationError(
            "BigQuery credentials could not be loaded",
            source="bigquery",
            step="client_bootstrap",
        ) from None

    return bigquery.Client(
        project=settings.bigquery_project_id,
        credentials=credentials,
    )
