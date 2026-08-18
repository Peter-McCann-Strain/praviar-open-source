"""Regression tests for the application-wide structured-log privacy boundary."""

from __future__ import annotations

from api.security import redact_sensitive_log_data


def _redact(payload: dict) -> dict:
    return redact_sensitive_log_data(None, "info", payload)


def test_sensitive_structured_fields_are_redacted_recursively() -> None:
    payload = {
        "event": "analysis_created",
        "org_id": "4d0834e1-5452-4cf2-a338-5bb8dc14ca2e",
        "compound_name": "Customer molecule PVR-42",
        "nested": {
            "recipient_email": "buyer@example.com",
            "subscription_id": "sub_123",
            "safe_status": "cancelled",
        },
        "rows": [{"target_email_normalized": "reviewer@example.com"}],
    }

    redacted = _redact(payload)

    assert redacted == {
        "event": "analysis_created",
        "org_id": "4d0834e1-5452-4cf2-a338-5bb8dc14ca2e",
        "compound_name": "[REDACTED]",
        "nested": {
            "recipient_email": "[REDACTED]",
            "subscription_id": "[REDACTED]",
            "safe_status": "cancelled",
        },
        "rows": [{"target_email_normalized": "[REDACTED]"}],
    }


def test_free_form_messages_scrub_credentials_email_and_public_locators() -> None:
    payload = {
        "event": (
            "failed for buyer@example.com with Bearer header.payload.signature "
            "at postgresql://user:db-password@db.example/praviar and "
            "https://app.example/share/grant-secret?token=query-secret"
        ),
        "error": "provider rejected sk_live_dont_log_me and whsec_dont_log_me",
    }

    redacted = _redact(payload)
    rendered = repr(redacted)

    for forbidden in (
        "buyer@example.com",
        "header.payload.signature",
        "db-password",
        "grant-secret",
        "query-secret",
        "sk_live_dont_log_me",
        "whsec_dont_log_me",
    ):
        assert forbidden not in rendered
    assert "postgresql://[REDACTED]@db.example/praviar" in redacted["event"]
    assert "https://app.example/share/[REDACTED]?token=[REDACTED]" in redacted["event"]


def test_operational_pseudonymous_identifiers_remain_available() -> None:
    payload = {
        "event": "export_failed",
        "request_id": "request-123",
        "org_id": "org-123",
        "analysis_id": "analysis-123",
        "api_key_id": "key-record-123",
        "status": 503,
    }

    assert _redact(payload) == payload
