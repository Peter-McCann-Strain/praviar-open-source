"""Hostile tests for versioned exact-domain external sharing policy."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Request
from pydantic import ValidationError

from api.errors import APIError
from api.routes.external_sharing_policy import patch_policy
from api.schemas.external_sharing import (
    ExternalSharingPolicy,
    ExternalSharingPolicyImpact,
    ExternalSharingPolicyUpdateRequest,
)
from api.services import external_sharing_policy as policy_service

NOW = datetime(2026, 7, 14, 1, 0, tzinfo=UTC)


class _Result:
    def __init__(self, *, scalar=None, rows=None, one=None):
        self._scalar = scalar
        self._rows = rows or []
        self._one = one

    def scalar_one_or_none(self):
        return self._scalar

    def all(self):
        return self._rows

    def one(self):
        return self._one


def _organization(
    *,
    mode: str = "approved_domains_only",
    domains: list[str] | None = None,
    version: int = 1,
):
    return SimpleNamespace(
        settings={"unrelated": {"preserved": True}},
        external_sharing_policy_mode=mode,
        external_sharing_approved_domains=domains or [],
        external_sharing_policy_version=version,
    )


@pytest.mark.parametrize(
    "domain",
    ["*.example.com", ".example.com", "counsel@example.com", "https://example.com", "localhost"],
)
def test_policy_rejects_wildcards_suffixes_addresses_urls_and_single_labels(domain: str):
    with pytest.raises(ValidationError):
        ExternalSharingPolicy(
            mode="approved_domains_only",
            approved_domains=[domain],
        )


def test_policy_normalizes_deduplicates_and_sorts_exact_idna_domains():
    policy = ExternalSharingPolicy(
        mode="approved_domains_only",
        approved_domains=[
            "BÜCHER.Example.",
            "xn--bcher-kva.example",
            "Counsel.Example",
        ],
        version=7,
    )

    assert policy.approved_domains == [
        "counsel.example",
        "xn--bcher-kva.example",
    ]
    assert policy.version == 7


def test_open_policy_cannot_hide_unused_allowlist_rules():
    with pytest.raises(ValidationError):
        ExternalSharingPolicy(mode="open", approved_domains=["example.com"])


def test_absent_policy_is_deny_all_and_legacy_json_is_ignored():
    organization = SimpleNamespace(
        settings={
            "external_sharing_policy": {
                "mode": "open",
                "approved_domains": [],
            }
        }
    )

    policy = policy_service._policy_from_organization(organization)

    assert policy == ExternalSharingPolicy(
        mode="approved_domains_only",
        approved_domains=[],
        version=1,
    )
    with pytest.raises(APIError) as exc_info:
        policy_service.require_recipient_domain_allowed(
            policy,
            recipient_domain="example.com",
        )
    assert exc_info.value.status == 403


def test_malformed_legacy_policy_is_removed_not_coerced_into_authorization():
    organization = SimpleNamespace(
        settings={
            "external_sharing_policy": {
                "mode": "open-ish",
                "approved_domains": ["*.example.com"],
            }
        }
    )

    assert policy_service._policy_from_organization(organization) == ExternalSharingPolicy()


def test_malformed_dedicated_policy_columns_fail_closed():
    organization = _organization(mode="wildcard", domains=["*.example.com"], version=0)

    with pytest.raises(APIError) as exc_info:
        policy_service._policy_from_organization(organization)

    assert exc_info.value.status == 500


def test_approved_domain_matching_is_exact_not_suffix_based():
    policy = ExternalSharingPolicy(
        mode="approved_domains_only",
        approved_domains=["example.com"],
    )
    policy_service.require_recipient_domain_allowed(policy, recipient_domain="example.com")

    with pytest.raises(APIError) as exc_info:
        policy_service.require_recipient_domain_allowed(
            policy,
            recipient_domain="sub.example.com",
        )

    assert exc_info.value.status == 403


@pytest.mark.asyncio
async def test_stale_admin_version_is_rejected_under_org_lock_before_impact_query():
    organization = _organization(mode="open", version=2)
    db = AsyncMock()
    db.execute.return_value = _Result(scalar=organization)
    request = ExternalSharingPolicyUpdateRequest(
        mode="approved_domains_only",
        approved_domains=[],
        expected_version=1,
        confirm_destructive=True,
    )

    with pytest.raises(APIError) as exc_info:
        await policy_service.update_external_sharing_policy(
            db,
            org_id=uuid.uuid4(),
            request=request,
        )

    assert exc_info.value.status == 409
    assert exc_info.value.title == "Policy version conflict"
    assert db.execute.await_count == 1
    assert db.execute.await_args.args[0]._for_update_arg is not None
    assert organization.external_sharing_policy_version == 2


@pytest.mark.asyncio
async def test_server_returns_authoritative_destructive_preview_without_mutation():
    org_id = uuid.uuid4()
    organization = _organization(mode="open", version=1)
    active_candidate = SimpleNamespace(
        id=uuid.uuid4(),
        analysis_id=uuid.uuid4(),
        recipient_domain="blocked.example",
        invitation_sent_at=NOW,
    )
    pending_candidate = SimpleNamespace(
        id=uuid.uuid4(),
        analysis_id=uuid.uuid4(),
        recipient_domain="pending.example",
        invitation_sent_at=None,
    )
    db = AsyncMock()
    db.execute.side_effect = [
        _Result(scalar=organization),
        _Result(rows=[active_candidate, pending_candidate]),
    ]

    preview = await policy_service.update_external_sharing_policy(
        db,
        org_id=org_id,
        request=ExternalSharingPolicyUpdateRequest(
            mode="approved_domains_only",
            approved_domains=["approved.example"],
            expected_version=1,
            confirm_destructive=False,
        ),
        now_fn=lambda _timezone: NOW,
    )

    assert preview.confirmation_required is True
    assert preview.impact == ExternalSharingPolicyImpact(
        active_grant_count=1,
        pending_grant_count=1,
        total_grant_count=2,
    )
    assert len(preview.proposal_digest) == 64
    assert db.execute.await_count == 2
    assert organization.external_sharing_policy_mode == "open"
    assert organization.external_sharing_policy_version == 1
    candidate_statement = db.execute.await_args_list[1].args[0]
    rendered = str(candidate_statement)
    compiled_values = tuple(candidate_statement.compile().params.values())
    delivery_states = {
        value
        for parameter in compiled_values
        for value in (parameter if isinstance(parameter, tuple | list) else (parameter,))
        if isinstance(value, str)
    }
    assert "external_report_grants.delivery_state" in rendered
    assert "external_report_grants.invitation_sent_at IS NOT NULL" in rendered
    assert "external_report_grants.invitation_sent_at IS NULL" in rendered
    assert {
        "active",
        "prepared",
        "dispatching",
        "provider_accepted",
        "outcome_unknown",
    }.issubset(delivery_states)
    assert {"rejected", "cancelled"}.isdisjoint(delivery_states)


@pytest.mark.asyncio
async def test_confirmed_tightening_revokes_grants_invalidates_proofs_and_increments_version():
    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    grant_id = uuid.uuid4()
    organization = _organization(mode="open", version=4)
    analysis = SimpleNamespace(
        share_active_grant_count=1,
        share_active_until=NOW + timedelta(days=7),
    )
    db = AsyncMock()
    db.execute.side_effect = [
        _Result(scalar=organization),
        _Result(
            rows=[
                SimpleNamespace(
                    id=grant_id,
                    analysis_id=analysis_id,
                    recipient_domain="blocked.example",
                    invitation_sent_at=NOW,
                )
            ]
        ),
        _Result(),
        _Result(scalar=analysis),
        _Result(one=(0, None)),
    ]

    proposal_digest = policy_service._proposal_digest(
        org_id=org_id,
        current_version=4,
        mode="approved_domains_only",
        approved_domains=["approved.example"],
        impacted_grants=(
            policy_service.PolicyRevokedGrant(
                id=grant_id,
                analysis_id=analysis_id,
                recipient_domain="blocked.example",
                invitation_sent_at=NOW,
            ),
        ),
    )
    updated = await policy_service.update_external_sharing_policy(
        db,
        org_id=org_id,
        request=ExternalSharingPolicyUpdateRequest(
            mode="approved_domains_only",
            approved_domains=["approved.example"],
            expected_version=4,
            confirm_destructive=True,
            proposal_digest=proposal_digest,
        ),
        now_fn=lambda _timezone: NOW,
    )

    assert organization.settings == {"unrelated": {"preserved": True}}
    assert organization.external_sharing_policy_mode == "approved_domains_only"
    assert organization.external_sharing_approved_domains == ["approved.example"]
    assert organization.external_sharing_policy_version == 5
    assert updated.policy.version == 5
    assert [grant.id for grant in updated.impacted_grants] == [grant_id]
    assert analysis.share_active_grant_count == 0
    assert analysis.share_active_until is None
    revoke_statement = db.execute.await_args_list[2].args[0]
    updated_columns = {column.name for column in revoke_statement._values}
    assert {
        "revoked_at",
        "delivery_state",
        "delivery_terminal_at",
        "delivery_token_ciphertext",
        "verification_code_hash",
        "verification_expires_at",
        "verification_sent_at",
        "verification_consumed_at",
        "access_secret_hash",
        "access_expires_at",
    }.issubset(updated_columns)


@pytest.mark.asyncio
async def test_changed_impact_digest_is_rejected_before_any_mutation_or_audit():
    organization = _organization(mode="open", version=8)
    candidate = SimpleNamespace(
        id=uuid.uuid4(),
        analysis_id=uuid.uuid4(),
        recipient_domain="blocked.example",
        invitation_sent_at=None,
    )
    db = AsyncMock()
    db.execute.side_effect = [
        _Result(scalar=organization),
        _Result(rows=[candidate]),
    ]

    with pytest.raises(APIError) as exc_info:
        await policy_service.update_external_sharing_policy(
            db,
            org_id=uuid.uuid4(),
            request=ExternalSharingPolicyUpdateRequest(
                mode="approved_domains_only",
                approved_domains=[],
                expected_version=8,
                confirm_destructive=True,
                proposal_digest="0" * 64,
            ),
            now_fn=lambda _timezone: NOW,
        )

    assert exc_info.value.status == 409
    assert exc_info.value.title == "Policy proposal changed"
    assert db.execute.await_count == 2
    assert organization.external_sharing_policy_mode == "open"
    assert organization.external_sharing_policy_version == 8


@pytest.mark.asyncio
async def test_policy_route_rolls_back_if_any_revocation_audit_write_fails():
    org_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), org_id=org_id)
    db = AsyncMock()
    updated = policy_service.ExternalSharingPolicyUpdate(
        previous_policy=ExternalSharingPolicy(mode="open", version=1),
        policy=ExternalSharingPolicy(
            mode="approved_domains_only",
            approved_domains=["approved.example"],
            version=2,
        ),
        impacted_grants=(
            policy_service.PolicyRevokedGrant(
                id=uuid.uuid4(),
                analysis_id=uuid.uuid4(),
                recipient_domain="blocked.example",
                invitation_sent_at=NOW,
            ),
        ),
        impact=ExternalSharingPolicyImpact(
            active_grant_count=1,
            pending_grant_count=0,
            total_grant_count=1,
        ),
        proposal_digest="1" * 64,
        confirmation_required=False,
    )
    body = ExternalSharingPolicyUpdateRequest(
        mode="approved_domains_only",
        approved_domains=["approved.example"],
        expected_version=1,
        confirm_destructive=True,
        proposal_digest="1" * 64,
    )
    request = Request(
        {
            "type": "http",
            "method": "PATCH",
            "path": "/admin/external-sharing-policy",
            "headers": [],
            "client": ("203.0.113.5", 443),
        }
    )
    with (
        patch(
            "api.routes.external_sharing_policy.update_external_sharing_policy",
            new=AsyncMock(return_value=updated),
        ),
        patch(
            "api.routes.external_sharing_policy.write_audit_log",
            new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
        ),
        pytest.raises(RuntimeError, match="audit unavailable"),
    ):
        await patch_policy(body, user, db, request)

    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_policy_route_returns_typed_preview_with_zero_mutation_audit():
    org_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), org_id=org_id)
    db = AsyncMock()
    preview = policy_service.ExternalSharingPolicyUpdate(
        previous_policy=ExternalSharingPolicy(mode="open", version=3),
        policy=ExternalSharingPolicy(
            mode="approved_domains_only",
            approved_domains=["approved.example"],
            version=3,
        ),
        impacted_grants=(
            policy_service.PolicyRevokedGrant(
                id=uuid.uuid4(),
                analysis_id=uuid.uuid4(),
                recipient_domain="blocked.example",
                invitation_sent_at=NOW,
            ),
        ),
        impact=ExternalSharingPolicyImpact(
            active_grant_count=1,
            pending_grant_count=0,
            total_grant_count=1,
        ),
        proposal_digest="a" * 64,
        confirmation_required=True,
    )
    body = ExternalSharingPolicyUpdateRequest(
        mode="approved_domains_only",
        approved_domains=["approved.example"],
        expected_version=3,
        confirm_destructive=False,
    )
    request = Request(
        {
            "type": "http",
            "method": "PATCH",
            "path": "/admin/external-sharing-policy",
            "headers": [],
            "client": ("203.0.113.5", 443),
        }
    )
    with (
        patch(
            "api.routes.external_sharing_policy.update_external_sharing_policy",
            new=AsyncMock(return_value=preview),
        ),
        patch(
            "api.routes.external_sharing_policy.write_audit_log",
            new=AsyncMock(),
        ) as audit,
    ):
        response = await patch_policy(body, user, db, request)

    assert response.status == "confirmation_required"
    assert response.proposal_digest == "a" * 64
    assert response.impact.total_grant_count == 1
    audit.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_policy_endpoints_are_admin_only(scientist_client):
    client, _db = scientist_client

    get_response = await client.get("/api/v1/admin/external-sharing-policy")
    patch_response = await client.patch(
        "/api/v1/admin/external-sharing-policy",
        json={
            "mode": "open",
            "approved_domains": [],
            "expected_version": 1,
            "confirm_destructive": False,
        },
    )

    assert get_response.status_code == 403
    assert patch_response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_read_and_update_versioned_policy(admin_client):
    client, db = admin_client
    current = ExternalSharingPolicy(
        mode="approved_domains_only",
        approved_domains=["approved.example"],
        version=3,
    )
    updated = policy_service.ExternalSharingPolicyUpdate(
        previous_policy=current,
        policy=current.model_copy(update={"version": 4}),
        impacted_grants=(),
        impact=ExternalSharingPolicyImpact(
            active_grant_count=0,
            pending_grant_count=0,
            total_grant_count=0,
        ),
        proposal_digest="2" * 64,
        confirmation_required=False,
    )
    with patch(
        "api.routes.external_sharing_policy.get_external_sharing_policy",
        new=AsyncMock(return_value=current),
    ):
        get_response = await client.get("/api/v1/admin/external-sharing-policy")

    assert get_response.status_code == 200
    assert get_response.json()["version"] == 3

    with (
        patch(
            "api.routes.external_sharing_policy.update_external_sharing_policy",
            new=AsyncMock(return_value=updated),
        ) as update_policy,
        patch(
            "api.routes.external_sharing_policy.write_audit_log",
            new=AsyncMock(),
        ) as audit,
    ):
        patch_response = await client.patch(
            "/api/v1/admin/external-sharing-policy",
            json={
                "mode": "approved_domains_only",
                "approved_domains": ["APPROVED.Example."],
                "expected_version": 3,
                "confirm_destructive": False,
            },
        )

    assert patch_response.status_code == 200
    assert patch_response.json()["version"] == 4
    assert patch_response.json()["status"] == "applied"
    assert patch_response.json()["revoked_grant_count"] == 0
    assert update_policy.await_args.kwargs["request"].expected_version == 3
    audit_details = audit.await_args.kwargs["details"]
    assert audit_details["previous_policy"] == current.model_dump()
    assert audit_details["new_policy"]["version"] == 4
    assert audit_details["version_transition"] == {"from": 3, "to": 4}
    assert audit_details["normalized_diff"] == {
        "mode_changed": False,
        "approved_domains_added": [],
        "approved_domains_removed": [],
    }
    assert audit_details["impact"] == {
        "active_grant_count": 0,
        "pending_grant_count": 0,
        "total_grant_count": 0,
        "revoked_grant_count": 0,
    }
    assert audit_details["confirmation"] == {
        "destructive_confirmed": False,
        "proposal_digest": None,
    }
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_admin_policy_api_rejects_missing_version_and_wildcards(admin_client):
    client, _db = admin_client
    with patch(
        "api.routes.external_sharing_policy.update_external_sharing_policy",
        new=AsyncMock(),
    ) as update_policy:
        missing_version = await client.patch(
            "/api/v1/admin/external-sharing-policy",
            json={
                "mode": "approved_domains_only",
                "approved_domains": ["example.com"],
                "confirm_destructive": True,
            },
        )
        wildcard = await client.patch(
            "/api/v1/admin/external-sharing-policy",
            json={
                "mode": "approved_domains_only",
                "approved_domains": ["*.example.com"],
                "expected_version": 1,
                "confirm_destructive": True,
            },
        )
        missing_confirmation = await client.patch(
            "/api/v1/admin/external-sharing-policy",
            json={
                "mode": "open",
                "approved_domains": [],
                "expected_version": 1,
            },
        )

    assert missing_version.status_code == 422
    assert wildcard.status_code == 422
    assert missing_confirmation.status_code == 422
    update_policy.assert_not_awaited()


def test_policy_migration_is_dedicated_versioned_and_deny_all_by_default():
    source = Path(
        "alembic/versions/b1c2d3e4f5a6_add_versioned_external_sharing_policy.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision: str | Sequence[str] | None = "z0a1b2c3d4e5"' in source
    assert "external_sharing_policy_mode" in source
    assert "external_sharing_approved_domains" in source
    assert "external_sharing_policy_version" in source
    assert 'server_default="approved_domains_only"' in source
    assert "server_default=sa.text(\"'[]'::jsonb\")" in source
    assert "settings = settings - 'external_sharing_policy'" in source
    assert "Deliberate authorization reset" in source
    assert "do not coerce even well-formed legacy JSON" in source
