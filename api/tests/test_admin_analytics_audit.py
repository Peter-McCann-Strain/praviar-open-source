"""Focused tests for admin analytics audit helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from api.schemas.admin_analytics import AuditLogEntryExtended
from api.services.admin_analytics import (
    get_audit_log_page_impl,
    render_audit_log_csv,
    sanitize_audit_details,
)


@pytest.mark.asyncio
async def test_get_audit_log_page_impl_builds_user_emails(mock_db):
    audit_entry = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        action="analysis.created",
        user_id=uuid.uuid4(),
        analysis_id=uuid.uuid4(),
        details={"compound": "aspirin"},
        ip_address="127.0.0.1",
        created_at=datetime(2026, 4, 11, tzinfo=UTC),
    )
    count_result = SimpleNamespace(scalar_one=lambda: 1)
    logs_result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [audit_entry]))
    users_result = SimpleNamespace(all=lambda: [(audit_entry.user_id, "user@praviar.io")])
    mock_db.execute.side_effect = [count_result, logs_result, users_result]

    page = await get_audit_log_page_impl(
        mock_db,
        action=None,
        user_id=None,
        start_date=None,
        end_date=None,
        page=1,
        per_page=50,
        sort="desc",
    )

    assert page.total == 1
    assert page.items[0].user_email == "user@praviar.io"
    assert page.has_next is False


@pytest.mark.asyncio
async def test_get_audit_log_page_impl_redacts_sensitive_details(mock_db):
    audit_entry = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        action="api_key.created",
        user_id=uuid.uuid4(),
        analysis_id=None,
        details={
            "key_id": "key_123",
            "api_key": "sk_live_should_not_escape",
            "nested": {
                "connection_string": "postgresql://user:password@db.example/app",
                "reason": "rotation",
            },
        },
        ip_address="127.0.0.1",
        created_at=datetime(2026, 4, 11, tzinfo=UTC),
    )
    count_result = SimpleNamespace(scalar_one=lambda: 1)
    logs_result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [audit_entry]))
    users_result = SimpleNamespace(all=lambda: [(audit_entry.user_id, "admin@praviar.io")])
    mock_db.execute.side_effect = [count_result, logs_result, users_result]

    page = await get_audit_log_page_impl(
        mock_db,
        action=None,
        user_id=None,
        start_date=None,
        end_date=None,
        page=1,
        per_page=50,
        sort="desc",
    )

    details = page.items[0].details
    assert details["key_id"] == "key_123"
    assert details["api_key"] == "[redacted]"
    assert details["nested"]["connection_string"] == "[redacted]"
    assert details["nested"]["reason"] == "rotation"


def test_render_audit_log_csv_redacts_sensitive_details():
    item = AuditLogEntryExtended(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        action="billing.checkout.created",
        user_id=uuid.uuid4(),
        user_email="admin@praviar.io",
        analysis_id=None,
        details={
            "credit_pack_id": "portfolio_5",
            "bearer": "Bearer token-secret-value",
        },
        ip_address="127.0.0.1",
        created_at=datetime(2026, 4, 11, tzinfo=UTC),
    )

    csv_payload = render_audit_log_csv([item])

    assert "token-secret-value" not in csv_payload
    assert "[redacted]" in csv_payload
    assert "portfolio_5" in csv_payload


def test_render_audit_log_csv_neutralizes_formula_after_leading_controls():
    item = AuditLogEntryExtended(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        action=' \t=HYPERLINK("https://evil.example")',
        user_id=uuid.uuid4(),
        user_email="@attacker.example",
        analysis_id=None,
        details={"safe": True},
        ip_address="127.0.0.1",
        created_at=datetime(2026, 4, 11, tzinfo=UTC),
    )

    csv_payload = render_audit_log_csv([item])

    assert "' \t=HYPERLINK" in csv_payload
    assert "'@attacker.example" in csv_payload


def test_audit_sanitizer_preserves_uuid_actor_reference_but_rejects_secret_shape():
    api_key_id = uuid.uuid4()

    assert sanitize_audit_details({"api_key_id": str(api_key_id)}) == {
        "api_key_id": str(api_key_id)
    }
    assert sanitize_audit_details({"api_key_id": "prv_live_" + ("a" * 43)}) == {
        "api_key_id": "[redacted]"
    }


@pytest.mark.asyncio
async def test_get_audit_log_page_impl_rejects_invalid_dates(mock_db):
    with pytest.raises(ValueError, match="date filter must be an ISO-8601"):
        await get_audit_log_page_impl(
            mock_db,
            action="analysis.created",
            user_id=None,
            start_date="not-a-date",
            end_date="still-not-a-date",
            page=1,
            per_page=50,
            sort="asc",
        )

    mock_db.execute.assert_not_awaited()
