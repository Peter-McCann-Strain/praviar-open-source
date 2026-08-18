"""Endpoint contract tests for /api/v1/billing routes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.ratelimit import authenticated_org_user_rate_limit_key
from api.schemas.billing import CreditPackId, PlanTier


@pytest.mark.asyncio
async def test_get_billing_status_delegates_to_service(admin_client):
    c, _db = admin_client
    payload = {
        "org_id": uuid.uuid4(),
        "plan": "starter",
        "stripe_customer_id": "cus_test",
        "stripe_subscription_id": "sub_test",
        "subscription_status": "active",
        "current_period_start": datetime(2026, 4, 1, tzinfo=UTC),
        "current_period_end": datetime(2026, 5, 1, tzinfo=UTC),
        "analyses_used": 4,
        "analyses_limit": 8,
        "cancel_at_period_end": False,
    }

    with patch(
        "api.routes.billing.get_billing_status_data",
        new=AsyncMock(return_value=payload),
    ) as service:
        resp = await c.get("/api/v1/billing/status")

    assert resp.status_code == 200
    assert resp.json()["plan"] == "starter"
    assert resp.json()["analyses_used"] == 4
    assert resp.json()["can_manage_billing"] is True
    service.assert_awaited_once()
    assert service.await_args is not None
    assert service.await_args.kwargs["org_id"] is not None


@pytest.mark.asyncio
async def test_get_billing_status_preserves_effective_lapsed_capacity_contract(
    admin_client,
):
    c, _db = admin_client
    payload = {
        "org_id": uuid.uuid4(),
        "plan": "pro",
        "subscription_status": "past_due",
        "analyses_used": 5,
        "analyses_limit": 7,
        "included_analyses_limit": 3,
        "purchased_credits_balance": 2,
        "purchased_credits_used": 0,
    }

    with patch(
        "api.routes.billing.get_billing_status_data",
        new=AsyncMock(return_value=payload),
    ):
        resp = await c.get("/api/v1/billing/status")

    assert resp.status_code == 200
    assert resp.json() == {
        **payload,
        "org_id": str(payload["org_id"]),
        "can_manage_billing": True,
        "stripe_customer_id": None,
        "stripe_subscription_id": None,
        "current_period_start": None,
        "current_period_end": None,
        "cancel_at_period_end": False,
    }


@pytest.mark.asyncio
async def test_create_checkout_session_delegates_to_service(admin_client):
    c, _db = admin_client
    payload = {"checkout_url": "https://checkout.example.com/session", "session_id": "cs_test"}

    with patch(
        "api.routes.billing.create_checkout_session_data",
        new=AsyncMock(return_value=payload),
    ) as service:
        resp = await c.post(
            "/api/v1/billing/checkout",
            json={"plan_id": "starter", "success_url": "", "cancel_url": ""},
        )

    assert resp.status_code == 200
    assert resp.json() == payload
    service.assert_awaited_once()
    assert service.await_args is not None
    assert service.await_args.kwargs["plan_id"] == PlanTier.STARTER


@pytest.mark.asyncio
async def test_create_credit_pack_checkout_session_delegates_to_service(admin_client):
    c, _db = admin_client
    payload = {"checkout_url": "https://checkout.example.com/credits", "session_id": "cs_credit"}

    with patch(
        "api.routes.billing.create_credit_pack_checkout_session_data",
        new=AsyncMock(return_value=payload),
    ) as service:
        resp = await c.post(
            "/api/v1/billing/credit-packs/checkout",
            json={
                "credit_pack_id": "portfolio_5",
                "success_url": "",
                "cancel_url": "",
            },
        )

    assert resp.status_code == 200
    assert resp.json() == payload
    service.assert_awaited_once()
    assert service.await_args is not None
    assert service.await_args.kwargs["credit_pack_id"] == CreditPackId.PORTFOLIO_5


@pytest.mark.asyncio
async def test_billing_viewer_can_request_credit_capacity(scientist_client):
    c, _db = scientist_client
    request_id = uuid.uuid4()
    requested_at = datetime(2026, 7, 16, tzinfo=UTC)
    payload = {
        "notified_admins": 2,
        "request_id": request_id,
        "requested_at": requested_at,
        "status": "sent",
    }

    with patch(
        "api.routes.billing.create_credit_capacity_request_data",
        new=AsyncMock(return_value=payload),
    ) as service:
        resp = await c.post(
            "/api/v1/billing/credit-capacity-requests",
            json={"requested_reports": 1, "source": "analysis_launch"},
        )

    assert resp.status_code == 201
    assert resp.json() == {
        "notified_admins": 2,
        "request_id": str(request_id),
        "requested_at": "2026-07-16T00:00:00Z",
        "status": "sent",
    }
    service.assert_awaited_once()
    assert service.await_args is not None
    assert service.await_args.kwargs["requested_reports"] == 1
    assert service.await_args.kwargs["source"] == "analysis_launch"
    assert service.await_args.kwargs["user"].role.value == "scientist"


@pytest.mark.asyncio
async def test_client_cannot_request_credit_capacity(client_role_client):
    c, _db = client_role_client

    resp = await c.post(
        "/api/v1/billing/credit-capacity-requests",
        json={"requested_reports": 1, "source": "analysis_launch"},
    )

    assert resp.status_code == 403
    assert "analysis.create" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_credit_capacity_request_validates_requested_reports(scientist_client):
    c, _db = scientist_client

    resp = await c.post(
        "/api/v1/billing/credit-capacity-requests",
        json={"requested_reports": 0, "source": "analysis_launch"},
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_scientist_lists_only_role_scoped_credit_capacity_requests(
    scientist_client,
):
    c, _db = scientist_client
    request_id = uuid.uuid4()
    requester_id = uuid.uuid4()
    payload = {
        "items": [
            {
                "id": request_id,
                "requester_user_id": requester_id,
                "requester_name": "Rina Scientist",
                "requested_reports": 1,
                "source": "analysis_launch",
                "status": "pending",
                "notified_admins": 1,
                "requested_at": datetime(2026, 7, 16, tzinfo=UTC),
                "resolved_at": None,
                "resolved_by_user_id": None,
                "resolution_note": None,
                "fulfillment_credit_ledger_id": None,
            }
        ],
        "total": 1,
        "page": 1,
        "per_page": 20,
    }

    with patch(
        "api.routes.billing.list_credit_capacity_requests_data",
        new=AsyncMock(return_value=payload),
    ) as service:
        resp = await c.get(
            "/api/v1/billing/credit-capacity-requests",
            params={"status": "pending", "per_page": 20},
        )

    assert resp.status_code == 200
    assert resp.json()["items"][0]["id"] == str(request_id)
    assert service.await_args is not None
    assert service.await_args.kwargs["request_status"] == "pending"
    assert service.await_args.kwargs["user"].role.value == "scientist"


@pytest.mark.asyncio
async def test_client_cannot_list_credit_capacity_requests(client_role_client):
    c, _db = client_role_client

    resp = await c.get("/api/v1/billing/credit-capacity-requests")

    assert resp.status_code == 403
    assert "analysis.create" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_admin_resolves_credit_capacity_request(admin_client):
    c, _db = admin_client
    request_id = uuid.uuid4()
    payload = {
        "id": request_id,
        "requester_user_id": uuid.uuid4(),
        "requester_name": "Rina Scientist",
        "requested_reports": 1,
        "source": "analysis_launch",
        "status": "declined",
        "notified_admins": 1,
        "requested_at": datetime(2026, 7, 16, tzinfo=UTC),
        "resolved_at": datetime(2026, 7, 16, 1, tzinfo=UTC),
        "resolved_by_user_id": uuid.uuid4(),
        "resolution_note": "Not approved.",
        "fulfillment_credit_ledger_id": None,
    }

    with patch(
        "api.routes.billing.resolve_credit_capacity_request_data",
        new=AsyncMock(return_value=payload),
    ) as service:
        resp = await c.post(
            f"/api/v1/billing/credit-capacity-requests/{request_id}/resolve",
            json={"status": "declined", "note": "Not approved."},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "declined"
    assert service.await_args is not None
    assert service.await_args.kwargs["request_id"] == request_id
    assert service.await_args.kwargs["resolution_status"] == "declined"


@pytest.mark.asyncio
async def test_admin_decline_requires_explanatory_note(admin_client):
    c, _db = admin_client
    request_id = uuid.uuid4()

    with patch(
        "api.routes.billing.resolve_credit_capacity_request_data",
        new=AsyncMock(),
    ) as service:
        resp = await c.post(
            f"/api/v1/billing/credit-capacity-requests/{request_id}/resolve",
            json={"status": "declined", "note": "  "},
        )

    assert resp.status_code == 422
    assert "decline reason" in str(resp.json()).lower()
    service.assert_not_awaited()


@pytest.mark.asyncio
async def test_scientist_cannot_resolve_credit_capacity_request(scientist_client):
    c, _db = scientist_client

    resp = await c.post(
        f"/api/v1/billing/credit-capacity-requests/{uuid.uuid4()}/resolve",
        json={"status": "fulfilled"},
    )

    assert resp.status_code == 403
    assert "billing.manage" in resp.json()["detail"]


def test_authenticated_credit_request_rate_key_is_org_and_user_scoped():
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    request = MagicMock()
    request.state = SimpleNamespace(
        rate_limit_org_id=str(org_id),
        rate_limit_user_id=str(user_id),
    )

    assert authenticated_org_user_rate_limit_key(request) == (f"org-user:{org_id}:{user_id}")

    request.state = SimpleNamespace()
    with pytest.raises(RuntimeError, match="identity is unavailable"):
        authenticated_org_user_rate_limit_key(request)


@pytest.mark.asyncio
async def test_credit_pack_reconciliation_delegates_with_current_scope(admin_client):
    c, _db = admin_client
    session_id = "cs_test_reconciliation123"
    payload = {"status": "pending", "session_id": session_id}

    with patch(
        "api.routes.billing.get_credit_pack_checkout_reconciliation_data",
        new=AsyncMock(return_value=payload),
    ) as service:
        resp = await c.get(
            "/api/v1/billing/credit-packs/reconciliation",
            params={"session_id": session_id},
        )

    assert resp.status_code == 200
    assert resp.json() == payload
    assert resp.headers["cache-control"] == "private, no-store"
    assert resp.headers["pragma"] == "no-cache"
    service.assert_awaited_once()
    assert service.await_args is not None
    assert service.await_args.kwargs["org_id"] is not None
    assert service.await_args.kwargs["user_id"] is not None
    assert service.await_args.kwargs["session_id"] == session_id


@pytest.mark.asyncio
async def test_credit_pack_reconciliation_rejects_invalid_session_id(admin_client):
    c, _db = admin_client

    resp = await c.get(
        "/api/v1/billing/credit-packs/reconciliation",
        params={"session_id": "not-a-stripe-session"},
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_portal_session_delegates_to_service(admin_client):
    c, _db = admin_client
    payload = {"portal_url": "https://billing.example.com/portal"}

    with patch(
        "api.routes.billing.create_portal_session_data",
        new=AsyncMock(return_value=payload),
    ) as service:
        resp = await c.post("/api/v1/billing/portal")

    assert resp.status_code == 200
    assert resp.json() == payload
    service.assert_awaited_once()
    assert service.await_args is not None
    assert service.await_args.kwargs["org_id"] is not None


@pytest.mark.asyncio
async def test_get_usage_summary_delegates_to_service(admin_client):
    c, _db = admin_client
    payload = {
        "org_id": uuid.uuid4(),
        "plan": "starter",
        "analyses_used": 9,
        "analyses_limit": 8,
        "usage_pct": 100.0,
        "cost_this_month_cents": 45_000,
        "overage_analyses": 1,
        "period_start": datetime(2026, 4, 1, tzinfo=UTC),
        "period_end": datetime(2026, 5, 1, tzinfo=UTC),
    }

    with patch(
        "api.routes.billing.get_usage_summary_data",
        new=AsyncMock(return_value=payload),
    ) as service:
        resp = await c.get("/api/v1/billing/usage")

    assert resp.status_code == 200
    assert resp.json()["cost_this_month_cents"] == 45_000
    service.assert_awaited_once()
    assert service.await_args is not None
    assert service.await_args.kwargs["org_id"] is not None


@pytest.mark.asyncio
async def test_list_invoices_delegates_to_service(admin_client):
    c, _db = admin_client
    payload = {"invoices": [], "has_more": False}

    with patch(
        "api.routes.billing.list_invoice_data",
        new=AsyncMock(return_value=payload),
    ) as service:
        resp = await c.get("/api/v1/billing/invoices")

    assert resp.status_code == 200
    assert resp.json() == payload
    service.assert_awaited_once()
    assert service.await_args is not None
    assert service.await_args.kwargs["org_id"] is not None


@pytest.mark.asyncio
async def test_billing_viewers_receive_read_only_capability(scientist_client):
    c, _db = scientist_client

    status_payload = {
        "org_id": uuid.uuid4(),
        "plan": "starter",
        "analyses_used": 4,
        "analyses_limit": 8,
    }
    usage_payload = {
        "org_id": status_payload["org_id"],
        "plan": "starter",
        "analyses_used": 4,
        "analyses_limit": 8,
        "usage_pct": 50,
        "cost_this_month_cents": 0,
        "currency": "usd",
        "overage_analyses": 0,
    }
    with (
        patch(
            "api.routes.billing.get_billing_status_data",
            new=AsyncMock(return_value=status_payload),
        ),
        patch(
            "api.routes.billing.get_usage_summary_data",
            new=AsyncMock(return_value=usage_payload),
        ),
        patch(
            "api.routes.billing.list_invoice_data",
            new=AsyncMock(return_value={"invoices": [], "has_more": False}),
        ),
        patch(
            "api.routes.billing.get_credit_pack_checkout_reconciliation_data",
            new=AsyncMock(
                return_value={
                    "status": "pending",
                    "session_id": "cs_test_viewer123",
                }
            ),
        ),
    ):
        status = await c.get("/api/v1/billing/status")
        usage = await c.get("/api/v1/billing/usage")
        invoices = await c.get("/api/v1/billing/invoices")
        reconciliation = await c.get(
            "/api/v1/billing/credit-packs/reconciliation",
            params={"session_id": "cs_test_viewer123"},
        )

    assert [response.status_code for response in (status, usage, invoices, reconciliation)] == [
        200,
        200,
        200,
        200,
    ]
    assert status.json()["can_manage_billing"] is False


@pytest.mark.asyncio
async def test_billing_mutations_require_admin_role(scientist_client):
    c, _db = scientist_client

    responses = [
        await c.post(
            "/api/v1/billing/checkout",
            json={"plan_id": "starter", "success_url": "", "cancel_url": ""},
        ),
        await c.post(
            "/api/v1/billing/credit-packs/checkout",
            json={"credit_pack_id": "portfolio_5", "success_url": "", "cancel_url": ""},
        ),
        await c.post("/api/v1/billing/portal"),
    ]

    assert [response.status_code for response in responses] == [403, 403, 403]
