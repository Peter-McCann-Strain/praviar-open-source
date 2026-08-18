"""Tests for the lightweight authenticated capability contract."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_admin_principal_capabilities_match_governed_admin_actions(
    admin_client,
):
    client, _db = admin_client

    response = await client.get("/api/v1/principal/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["role"] == "admin"
    assert payload["can_create_analysis"] is True
    assert payload["can_view_review_queue"] is True
    assert payload["can_resolve_review"] is True
    assert payload["can_export_report"] is True
    assert payload["can_share_report"] is True
    assert payload["can_view_billing"] is True
    assert payload["can_manage_billing"] is True
    assert payload["risk_ratings_restricted"] is False
    assert payload["api_key_report_export_scope_available"] is False


@pytest.mark.asyncio
async def test_scientist_principal_capabilities_preserve_review_triage_without_counsel_actions(
    scientist_client,
):
    client, _db = scientist_client

    response = await client.get("/api/v1/principal/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["role"] == "scientist"
    assert payload["can_create_analysis"] is True
    assert payload["can_view_review_queue"] is True
    assert payload["can_assign_review"] is True
    assert payload["can_escalate_review"] is True
    assert payload["can_resolve_review"] is False
    assert payload["risk_ratings_restricted"] is True
    assert payload["can_export_report"] is False
    assert payload["can_share_report"] is False
    assert payload["can_deliver_report"] is False
    assert payload["can_view_billing"] is True
    assert payload["can_manage_billing"] is False


@pytest.mark.asyncio
async def test_client_principal_capabilities_are_read_only(client_role_client):
    client, _db = client_role_client

    response = await client.get("/api/v1/principal/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["role"] == "client"
    assert payload["can_create_analysis"] is False
    assert payload["can_view_patents"] is False
    assert payload["can_view_review_queue"] is False
    assert payload["can_create_batch"] is False
    assert payload["can_manage_config"] is False
    assert payload["can_export_report"] is False
    assert payload["can_share_report"] is False
    assert payload["can_view_billing"] is True
    assert payload["can_manage_billing"] is False
