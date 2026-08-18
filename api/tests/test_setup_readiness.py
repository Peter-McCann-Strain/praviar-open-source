"""Tests for the tenant-scoped setup readiness checklist."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.db.models import OrgPlan, UserRole
from api.schemas.setup_readiness import (
    SetupReadinessItemStatus,
    SetupReadinessOverallStatus,
    SetupReadinessResponse,
)
from api.services.billing_queries import (
    AnalysisCapacitySnapshot,
    get_available_analysis_capacity,
)
from api.services.setup_readiness import (
    _evidence_policy_is_configured,
    get_setup_readiness,
)


def _result(*, scalar=None, row=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.one.return_value = row
    return result


def _user(*, org_id: uuid.UUID | None = None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        org_id=org_id or uuid.uuid4(),
        clerk_user_id="user_123",
        email="buyer@example.com",
        full_name="Buyer",
        role=UserRole.ADMIN,
    )


def _org(*, org_id: uuid.UUID, settings: dict | None = None, **overrides):
    values = {
        "id": org_id,
        "clerk_org_id": "org_123",
        "name": "Buyer Pharma",
        "plan": OrgPlan.PRO,
        "settings": settings or {},
        "sso_enabled": False,
        "sso_domains": [],
        "sso_required": False,
        "sso_status_available": False,
        "sso_last_synced_at": None,
        "max_analyses_per_month": 10,
        "analyses_used_this_month": 2,
        "free_analyses_remaining": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_evidence_policy_readiness_revalidates_persisted_config():
    assert _evidence_policy_is_configured(
        {
            "search_jurisdictions": ["US", "EP"],
            "enable_pubchem": True,
            "max_analysis_patents": 20,
        }
    )
    assert not _evidence_policy_is_configured(
        {
            "search_jurisdictions": ["NOT-A-JURISDICTION"],
            "enable_pubchem": True,
            "max_analysis_patents": 20,
        }
    )


@pytest.mark.asyncio
async def test_setup_readiness_reports_only_persisted_completion_evidence():
    user = _user()
    org = _org(
        org_id=user.org_id,
        settings={
            "default_config": {
                "search_jurisdictions": ["US", "EP"],
                "enable_pubchem": True,
                "max_analysis_patents": 20,
            },
        },
        sso_required=True,
        sso_enabled=True,
        sso_domains=["buyer.example"],
        sso_status_available=True,
        sso_last_synced_at=datetime.now(UTC),
    )
    evidence = SimpleNamespace(
        collaborator_count=3,
        review_capable_count=2,
        analysis_count=2,
        completed_analysis_count=1,
        has_review_handoff=True,
        has_share=False,
        has_export=True,
    )
    db = AsyncMock()
    db.execute.side_effect = [_result(scalar=org), _result(row=evidence)]

    with (
        patch(
            "api.services.setup_readiness.get_available_analysis_capacity",
            new=AsyncMock(
                return_value=AnalysisCapacitySnapshot(
                    available=8,
                    used=2,
                    entitlement_limit=10,
                )
            ),
        ),
        patch(
            "api.services.setup_readiness._primary_us_status_collection_readiness",
            return_value=SimpleNamespace(ready=True, failure_reasons=[]),
        ),
    ):
        response = await get_setup_readiness(db, user=user)

    assert response.overall_status == SetupReadinessOverallStatus.READY
    assert response.completed_items == 8
    assert response.applicable_items == 8
    assert all(item.status == SetupReadinessItemStatus.COMPLETE for item in response.items)
    assert response.items[0].evidence == (
        "Authenticated identity and organization membership are persisted; role admin."
    )
    evidence_policy = next(item for item in response.items if item.id.value == "evidence_policy")
    assert "US primary-status collection and signing are ready" in (evidence_policy.evidence)
    evidence_query = str(db.execute.await_args_list[1].args[0])
    assert re.search(
        r"(?:analysis_review_statuses\.analysis_id = analyses\.id|analyses\.id = analysis_review_statuses\.analysis_id)",
        evidence_query,
    )
    assert "analysis_review_statuses.status" in evidence_query
    assert re.search(
        r"(?:export_jobs\.analysis_id = analyses\.id|analyses\.id = export_jobs\.analysis_id)",
        evidence_query,
    )
    assert evidence_query.count("users.membership_active IS true") == 2
    assert evidence_query.count("users.membership_deleted_at IS NULL") == 2
    assert evidence_query.count("users.membership_permission_denied_at IS NULL") == 2
    assert "analyses.report_data IS NOT NULL" in evidence_query
    assert "analyses.flagged_for_review IS false" in evidence_query


@pytest.mark.asyncio
async def test_setup_readiness_blocks_us_policy_when_primary_status_is_unavailable():
    user = _user()
    org = _org(
        org_id=user.org_id,
        settings={
            "default_config": {
                "search_jurisdictions": ["US"],
                "enable_pubchem": True,
                "max_analysis_patents": 20,
            },
        },
    )
    evidence = SimpleNamespace(
        collaborator_count=2,
        review_capable_count=1,
        analysis_count=1,
        completed_analysis_count=1,
        has_review_handoff=True,
        has_share=True,
        has_export=False,
    )
    db = AsyncMock()
    db.execute.side_effect = [_result(scalar=org), _result(row=evidence)]

    with (
        patch(
            "api.services.setup_readiness.get_available_analysis_capacity",
            new=AsyncMock(
                return_value=AnalysisCapacitySnapshot(
                    available=8,
                    used=2,
                    entitlement_limit=10,
                )
            ),
        ),
        patch(
            "api.services.setup_readiness._primary_us_status_collection_readiness",
            return_value=SimpleNamespace(
                ready=False,
                failure_reasons=[
                    "current_claim_set remains unavailable.",
                    "Maintenance ingestion is not authenticated.",
                ],
            ),
        ),
    ):
        response = await get_setup_readiness(db, user=user)

    evidence_policy = next(item for item in response.items if item.id.value == "evidence_policy")
    assert response.overall_status == SetupReadinessOverallStatus.ACTION_REQUIRED
    assert evidence_policy.status == SetupReadinessItemStatus.ACTION_REQUIRED
    assert "current_claim_set remains unavailable" in evidence_policy.evidence
    assert "Maintenance ingestion is not authenticated" in evidence_policy.evidence


@pytest.mark.asyncio
async def test_setup_readiness_fails_closed_when_workflow_evidence_is_absent():
    user = _user()
    # The dedicated policy column is authoritative after migration; a stale
    # legacy JSON key cannot re-enable or disable the control.
    org = _org(org_id=user.org_id, settings={"sso_required": True})
    evidence = SimpleNamespace(
        collaborator_count=1,
        review_capable_count=1,
        analysis_count=1,
        completed_analysis_count=0,
        has_review_handoff=False,
        has_share=False,
        has_export=False,
    )
    db = AsyncMock()
    db.execute.side_effect = [_result(scalar=org), _result(row=evidence)]

    with patch(
        "api.services.setup_readiness.get_available_analysis_capacity",
        new=AsyncMock(
            return_value=AnalysisCapacitySnapshot(
                available=8,
                used=2,
                entitlement_limit=10,
            )
        ),
    ):
        response = await get_setup_readiness(db, user=user)
    by_id = {item.id.value: item for item in response.items}

    assert response.overall_status == SetupReadinessOverallStatus.ACTION_REQUIRED
    assert by_id["sso"].status == SetupReadinessItemStatus.NOT_REQUIRED
    assert by_id["first_analysis"].status == SetupReadinessItemStatus.ACTION_REQUIRED
    assert "1 total analysis" in by_id["first_analysis"].evidence
    assert by_id["review_handoff"].status == SetupReadinessItemStatus.BLOCKED
    assert by_id["share_export"].status == SetupReadinessItemStatus.BLOCKED
    assert "Complete an analysis" in by_id["share_export"].evidence


@pytest.mark.asyncio
async def test_setup_readiness_requires_enabled_sso_domain_when_policy_requires_sso():
    user = _user()
    org = _org(
        org_id=user.org_id,
        sso_required=True,
        sso_status_available=True,
        sso_last_synced_at=datetime.now(UTC),
    )
    evidence = SimpleNamespace(
        collaborator_count=2,
        review_capable_count=1,
        analysis_count=1,
        completed_analysis_count=1,
        has_review_handoff=True,
        has_share=True,
        has_export=False,
    )
    db = AsyncMock()
    db.execute.side_effect = [_result(scalar=org), _result(row=evidence)]

    with patch(
        "api.services.setup_readiness.get_available_analysis_capacity",
        new=AsyncMock(
            return_value=AnalysisCapacitySnapshot(
                available=8,
                used=2,
                entitlement_limit=10,
            )
        ),
    ):
        response = await get_setup_readiness(db, user=user)
    sso = next(item for item in response.items if item.id.value == "sso")

    assert sso.status == SetupReadinessItemStatus.ACTION_REQUIRED
    assert "requires SSO" in sso.evidence


@pytest.mark.asyncio
async def test_setup_readiness_rejects_cached_active_sso_when_live_status_is_stale():
    user = _user()
    org = _org(
        org_id=user.org_id,
        sso_required=True,
        sso_enabled=True,
        sso_domains=["cached.example"],
        sso_status_available=True,
        sso_last_synced_at=datetime(2026, 7, 13, tzinfo=UTC),
    )
    evidence = SimpleNamespace(
        collaborator_count=2,
        review_capable_count=1,
        analysis_count=1,
        completed_analysis_count=1,
        has_review_handoff=True,
        has_share=True,
        has_export=False,
    )
    db = AsyncMock()
    db.execute.side_effect = [_result(scalar=org), _result(row=evidence)]

    with patch(
        "api.services.setup_readiness.get_available_analysis_capacity",
        new=AsyncMock(
            return_value=AnalysisCapacitySnapshot(
                available=8,
                used=2,
                entitlement_limit=10,
            )
        ),
    ):
        response = await get_setup_readiness(db, user=user)

    sso = next(item for item in response.items if item.id.value == "sso")
    assert sso.status == SetupReadinessItemStatus.ACTION_REQUIRED
    assert "unavailable or stale" in sso.evidence
    assert "cached identity data" in sso.evidence


@pytest.mark.asyncio
async def test_setup_readiness_never_links_scientist_to_admin_only_recovery():
    user = _user()
    user.role = UserRole.SCIENTIST
    org = _org(org_id=user.org_id, sso_required=True)
    evidence = SimpleNamespace(
        collaborator_count=1,
        review_capable_count=0,
        analysis_count=0,
        completed_analysis_count=0,
        has_review_handoff=False,
        has_share=False,
        has_export=False,
    )
    db = AsyncMock()
    db.execute.side_effect = [_result(scalar=org), _result(row=evidence)]

    with patch(
        "api.services.setup_readiness.get_available_analysis_capacity",
        new=AsyncMock(
            return_value=AnalysisCapacitySnapshot(
                available=0,
                used=10,
                entitlement_limit=10,
            )
        ),
    ):
        response = await get_setup_readiness(db, user=user)

    by_id = {item.id.value: item for item in response.items}
    for item_id in ("identity", "collaborators", "billing", "sso"):
        assert by_id[item_id].recovery_href is None
        assert by_id[item_id].recovery_label == "Ask a workspace administrator"
    assert by_id["evidence_policy"].recovery_href is None
    assert by_id["first_analysis"].recovery_href == "/analyses/new"
    assert by_id["review_handoff"].recovery_href is None
    assert by_id["share_export"].recovery_href is None
    assert by_id["share_export"].recovery_label == ("Ask an attorney or authorized delivery owner")


@pytest.mark.asyncio
async def test_capacity_snapshot_uses_live_usage_and_credit_ledger_not_dead_counter():
    org_id = uuid.uuid4()
    org = SimpleNamespace(
        id=org_id,
        plan=OrgPlan.PRO,
        max_analyses_per_month=10,
        subscription_status="active",
        billing_cycle_start=None,
        analyses_used_this_month=999,
    )
    db = AsyncMock()
    usage_result = MagicMock()
    usage_result.scalar_one.return_value = 7
    credit_result = MagicMock()
    credit_result.scalar_one.return_value = 3
    consumed_credit_result = MagicMock()
    consumed_credit_result.scalar_one.return_value = -2
    db.execute.side_effect = [usage_result, credit_result, consumed_credit_result]

    snapshot = await get_available_analysis_capacity(db, org=org)

    assert snapshot.used == 7
    assert snapshot.entitlement_limit == 15
    assert snapshot.available == 8


@pytest.mark.asyncio
async def test_setup_readiness_route_delegates_with_authenticated_user(admin_client):
    client, _db = admin_client
    payload = SetupReadinessResponse(
        overall_status="action_required",
        current_user_role="admin",
        completed_items=1,
        applicable_items=2,
        observed_at="2026-07-13T10:00:00Z",
        items=[
            {
                "id": "identity",
                "label": "Identity and organization",
                "description": "Confirm identity.",
                "status": "complete",
                "owner": "Workspace administrator",
                "recovery_label": "Review workspace settings",
                "recovery_href": "/settings",
                "evidence": "Persisted identity found.",
            },
            {
                "id": "first_analysis",
                "label": "First analysis",
                "description": "Run an analysis.",
                "status": "action_required",
                "owner": "Analysis team",
                "recovery_label": "Start an analysis",
                "recovery_href": "/analyses/new",
                "evidence": "No analysis record found.",
            },
        ],
    )
    with patch(
        "api.routes.setup_readiness.get_setup_readiness",
        new=AsyncMock(return_value=payload),
    ) as service:
        response = await client.get("/api/v1/setup-readiness")

    assert response.status_code == 200
    assert response.json()["current_user_role"] == "admin"
    assert response.json()["items"][1]["status"] == "action_required"
    assert service.await_args is not None
    assert service.await_args.kwargs["user"].org_id is not None


@pytest.mark.asyncio
async def test_setup_readiness_route_is_available_to_non_admin(scientist_client):
    client, _db = scientist_client
    payload = SetupReadinessResponse(
        overall_status="ready",
        current_user_role="scientist",
        completed_items=0,
        applicable_items=0,
        observed_at="2026-07-13T10:00:00Z",
        items=[],
    )
    with patch(
        "api.routes.setup_readiness.get_setup_readiness",
        new=AsyncMock(return_value=payload),
    ):
        response = await client.get("/api/v1/setup-readiness")

    assert response.status_code == 200
    assert response.json()["current_user_role"] == "scientist"
