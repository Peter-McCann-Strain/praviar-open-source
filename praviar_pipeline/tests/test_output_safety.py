"""Regression tests for model/customer-visible diagnostic sanitization."""

from __future__ import annotations

import pytest

from praviar_pipeline.output_safety import (
    DIAGNOSTIC_SANITIZER_SCHEMA_VERSION,
    SAFE_PROCESSING_FAILURE_DETAIL,
    SAFE_PROVIDER_FAILURE_DETAIL,
    SAFE_PROVIDER_NOT_CONFIGURED_DETAIL,
    DiagnosticClassification,
    DiagnosticFieldRule,
    DiagnosticSanitizerSchema,
    safe_processing_error_detail,
    safe_source_error_detail,
    sanitize_error_fields_for_output,
)


@pytest.mark.parametrize(
    "diagnostic",
    [
        "401 for https://api.openalex.org/works?api_key=SUPERSECRET&q=aspirin",
        "GET https://apis.data.go.kr/patent?ServiceKey=KIPRISSECRET",
        "Authorization: Bearer provider-token-value",
        "postgresql://admin:database-password@db.internal/praviar",
        "/srv/praviar/private/provider-cache.json: permission denied",
        "SELECT * FROM private_patents WHERE tenant_id='secret-org'",
    ],
)
def test_output_error_sanitizers_never_echo_protected_diagnostics(diagnostic: str) -> None:
    source_detail = safe_source_error_detail(diagnostic, status="failed")
    processing_detail = safe_processing_error_detail(diagnostic)

    assert source_detail == SAFE_PROVIDER_FAILURE_DETAIL
    assert processing_detail == SAFE_PROCESSING_FAILURE_DETAIL
    assert diagnostic not in source_detail
    assert diagnostic not in processing_detail
    assert "SUPERSECRET" not in source_detail
    assert "provider-token-value" not in processing_detail


def test_not_configured_source_uses_stable_user_safe_explanation() -> None:
    detail = safe_source_error_detail(
        "OPENALEX_API_KEY missing; attempted api_key=SUPERSECRET",
        status="not_configured",
    )

    assert detail == SAFE_PROVIDER_NOT_CONFIGURED_DETAIL
    assert "OPENALEX" not in detail
    assert "SUPERSECRET" not in detail


def test_pdf_payload_boundary_recursively_replaces_every_error_message() -> None:
    payload = {
        "source_health": {
            "entries": [
                {
                    "source": "openalex",
                    "error_message": "https://api.openalex.org?api_key=SUPERSECRET",
                }
            ]
        },
        "analysis_failures": [{"error_message": "Authorization: Bearer provider-token-value"}],
    }

    sanitized = sanitize_error_fields_for_output(payload)

    assert sanitized["source_health"]["entries"][0]["error_message"] == (
        SAFE_PROVIDER_FAILURE_DETAIL
    )
    assert sanitized["analysis_failures"][0]["error_message"] == (SAFE_PROCESSING_FAILURE_DETAIL)
    assert "SUPERSECRET" not in str(sanitized)
    assert "provider-token-value" not in str(sanitized)


def test_typed_diagnostic_schema_covers_provider_fields_without_name_matching() -> None:
    payload = {
        "provider": {
            "detail": "Bearer SECRET-DETAIL",
            "diagnostic": "postgresql://SECRET-DIAGNOSTIC",
            "exception": "SECRET-EXCEPTION",
            "url": "https://provider.invalid?token=SECRET-URL",
            "provider_payload": {"trace": "SECRET-PROVIDER"},
            "public_url": "https://patents.example/publication/123",
        }
    }
    schema = DiagnosticSanitizerSchema(
        fields=tuple(
            DiagnosticFieldRule(
                path=("provider", field_name),
                classification=DiagnosticClassification.PROCESSING,
            )
            for field_name in (
                "detail",
                "diagnostic",
                "exception",
                "url",
                "provider_payload",
            )
        )
    )

    sanitized = sanitize_error_fields_for_output(payload, schema=schema)

    assert schema.schema_version == DIAGNOSTIC_SANITIZER_SCHEMA_VERSION
    for field_name in ("detail", "diagnostic", "exception", "url", "provider_payload"):
        assert sanitized["provider"][field_name] == SAFE_PROCESSING_FAILURE_DETAIL
    assert sanitized["provider"]["public_url"] == payload["provider"]["public_url"]
    assert "SECRET" not in str(sanitized)
