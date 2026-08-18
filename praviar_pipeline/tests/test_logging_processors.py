from __future__ import annotations

from praviar_pipeline.logging_processors import (
    add_service_context,
    mask_secret_values,
    truncate_event_values,
)


def test_mask_secret_values_redacts_known_patterns() -> None:
    event = {
        "api_key": 'api_key="sk-ant-api03-secret-value"',
        "auth": "Bearer abc123token",
        "compound_name": "Customer molecule PVR-42",
        "nested": {
            "recipient_email": "buyer@example.com",
            "safe_status": "complete",
        },
        "error": (
            "failed at postgresql://user:password@db.example/praviar?access_token=query-secret"
        ),
    }

    masked = mask_secret_values(event)

    assert "***REDACTED***" in masked["api_key"]
    assert "***REDACTED***" in masked["auth"]
    assert masked["compound_name"] == "***REDACTED***"
    assert masked["nested"] == {
        "recipient_email": "***REDACTED***",
        "safe_status": "complete",
    }
    assert "password" not in masked["error"]
    assert "query-secret" not in masked["error"]


def test_truncate_event_values_bounds_long_strings() -> None:
    truncated = truncate_event_values({"payload": "x" * 12}, max_len=5)

    assert truncated["payload"] == "xxxxx... [12 chars]"


def test_add_service_context_sets_default_only_once() -> None:
    assert add_service_context({})["service"] == "praviar_pipeline"
    assert add_service_context({"service": "custom"})["service"] == "custom"
