"""SSO configuration service — Clerk Enterprise Connection integration.

Design notes
------------
- Clerk owns all SAML/OIDC metadata. We never parse IdP XML ourselves.
- This service:
    1. Queries the Clerk Backend API for the org's Enterprise Connections.
    2. Syncs the result into the local ``organizations`` row so callers can
       retain the last authoritative SSO identity state.
    3. Logs an audit event on every admin configure action.
- A successful Clerk response is authoritative even when it contains no
  connections. Provider failures preserve cached identity fields but mark them
  explicitly unavailable and stale.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import quote

import httpx
import structlog
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import write_audit_log
from api.config import get_settings
from api.db.models_identity import Organization
from api.errors import APIError
from api.schemas.sso import (
    SSOConfigureRequest,
    SSOConfigureResponse,
    SSOStatusResponse,
    SSOUnavailableReason,
)
from api.services.sso_freshness import sso_status_is_fresh

logger = structlog.get_logger()

_CLERK_API_BASE = "https://api.clerk.com/v1"

# Clerk provider IDs that map to human-readable labels.
_PROVIDER_LABELS: dict[str, str] = {
    "saml_okta": "Okta",
    "saml_microsoft": "Azure AD",
    "saml_google": "Google Workspace",
    "saml_custom": "Custom SAML",
    "oidc_custom": "Custom OIDC",
}


@dataclass(frozen=True, slots=True)
class ClerkConnectionsFetchResult:
    """Typed distinction between authoritative Clerk state and unavailability."""

    available: bool
    connections: tuple[dict[str, Any], ...] = ()
    unavailable_reason: SSOUnavailableReason | None = None

    @classmethod
    def authoritative(cls, connections: list[dict[str, Any]]) -> ClerkConnectionsFetchResult:
        return cls(available=True, connections=tuple(connections))

    @classmethod
    def unavailable(cls, reason: SSOUnavailableReason) -> ClerkConnectionsFetchResult:
        return cls(available=False, unavailable_reason=reason)


def _clerk_headers(secret_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
    }


def _parse_provider_label(provider_id: str | None) -> str | None:
    if not provider_id:
        return None
    return _PROVIDER_LABELS.get(provider_id, provider_id)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _cached_status_fields(org: Organization) -> dict[str, Any]:
    if org.sso_enabled:
        status = "active"
    elif org.sso_provider:
        status = "pending"
    else:
        status = "inactive"
    return {
        "sso_enabled": org.sso_enabled,
        "provider": org.sso_provider,
        "domains": list(org.sso_domains or []),
        "status": status,
    }


async def _fetch_clerk_enterprise_connections(
    *,
    clerk_org_id: str,
    settings,
    http_client_cls=httpx.AsyncClient,
) -> ClerkConnectionsFetchResult:
    """Query the Clerk Backend API for enterprise connections on an org.

    A 200 response is authoritative, including an empty list. Every provider,
    transport, configuration, circuit, or payload failure is typed as
    unavailable so callers cannot mistake it for an authoritative empty state.
    """
    if not settings.clerk_secret_key:
        logger.warning("sso_clerk_secret_missing")
        return ClerkConnectionsFetchResult.unavailable("missing_secret")

    encoded_org_id = quote(clerk_org_id, safe="")
    url = f"{_CLERK_API_BASE}/organizations/{encoded_org_id}/enterprise_connections"

    from api.circuit_breaker import CircuitOpenError, clerk_breaker
    from api.http_utils import retry_with_jitter

    try:

        async def _call_clerk() -> httpx.Response:
            # Share one client across retry attempts to reuse the connection pool.
            async with http_client_cls(timeout=httpx.Timeout(10.0, connect=5.0)) as client:

                async def _fetch() -> httpx.Response:
                    r = await client.get(url, headers=_clerk_headers(settings.clerk_secret_key))
                    if r.status_code in (429, 502, 503, 504):
                        r.raise_for_status()
                    return cast(httpx.Response, r)

                response = await retry_with_jitter(
                    _fetch, max_attempts=3, caller="clerk.enterprise_connections"
                )
                if response.status_code >= 400 and response.status_code != 404:
                    response.raise_for_status()
                return response

        response = await clerk_breaker.call(_call_clerk)
    except CircuitOpenError as exc:
        logger.warning("sso_clerk_circuit_open", retry_after_s=exc.retry_after_s)
        return ClerkConnectionsFetchResult.unavailable("circuit_open")
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "sso_clerk_provider_error",
            status=exc.response.status_code,
        )
        return ClerkConnectionsFetchResult.unavailable("provider_error")
    except httpx.RequestError as exc:
        logger.warning(
            "sso_clerk_fetch_error",
            error_type=type(exc).__name__,
            status=getattr(getattr(exc, "response", None), "status_code", None),
        )
        return ClerkConnectionsFetchResult.unavailable("transport_error")

    if response.status_code == 404:
        logger.warning("sso_clerk_org_not_found", clerk_org_id=clerk_org_id)
        return ClerkConnectionsFetchResult.unavailable("not_found")

    if response.status_code != 200:
        logger.error(
            "sso_clerk_api_error",
            status=response.status_code,
        )
        return ClerkConnectionsFetchResult.unavailable("provider_error")

    try:
        data = response.json()
    except (TypeError, ValueError):
        logger.warning("sso_clerk_malformed_response", payload_type="invalid_json")
        return ClerkConnectionsFetchResult.unavailable("malformed_response")

    if isinstance(data, list):
        connections = data
    elif isinstance(data, dict) and isinstance(data.get("data"), list):
        connections = data["data"]
    else:
        logger.warning(
            "sso_clerk_malformed_response",
            payload_type=type(data).__name__,
        )
        return ClerkConnectionsFetchResult.unavailable("malformed_response")

    if not all(isinstance(connection, dict) for connection in connections):
        logger.warning("sso_clerk_malformed_response", payload_type="connection")
        return ClerkConnectionsFetchResult.unavailable("malformed_response")

    for connection in connections:
        connection_id = connection.get("id")
        provider = connection.get("provider")
        active = connection.get("active")
        domains = connection.get("domains", [])
        if (
            not isinstance(connection_id, str)
            or not connection_id.strip()
            or not isinstance(provider, str)
            or not provider.strip()
            or not isinstance(active, bool)
            or not isinstance(domains, list)
            or not all(
                isinstance(domain, dict)
                and isinstance(domain.get("name"), str)
                and bool(domain["name"].strip())
                for domain in domains
            )
        ):
            logger.warning("sso_clerk_malformed_response", payload_type="connection_fields")
            return ClerkConnectionsFetchResult.unavailable("malformed_response")

    return ClerkConnectionsFetchResult.authoritative(connections)


def _connection_to_status(
    connections: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    """Derive the canonical SSO status fields from a list of Clerk connections."""
    active = [c for c in connections if c.get("active") is True]
    pending = [c for c in connections if not c.get("active") and c.get("id")]

    if active:
        conn = active[0]
        domains = [d.get("name", "") for d in conn.get("domains", []) if d.get("name")]
        return {
            "sso_enabled": True,
            "provider": _parse_provider_label(conn.get("provider")),
            "domains": domains,
            "status": "active",
        }

    if pending:
        conn = pending[0]
        domains = [d.get("name", "") for d in conn.get("domains", []) if d.get("name")]
        return {
            "sso_enabled": False,
            "provider": _parse_provider_label(conn.get("provider")),
            "domains": domains,
            "status": "pending",
        }

    return {
        "sso_enabled": False,
        "provider": None,
        "domains": [],
        "status": "inactive",
    }


async def _load_org(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    for_update: bool = False,
) -> Organization:
    statement = select(Organization).where(Organization.id == org_id)
    if for_update:
        # Serialize the freshness check and SSO policy mutation against status
        # refreshes. A provider failure committed first is observed here; one
        # that begins later cannot create a check/use gap inside this transaction.
        statement = statement.with_for_update()
    result = await db.execute(statement)
    org = result.scalar_one_or_none()
    if org is None:
        raise APIError(404, "Not Found", "Organization not found")
    return org


async def _commit_sso_status(
    db: AsyncSession,
    *,
    org: Organization,
) -> None:
    """Persist SSO status metadata, failing closed when durability is uncertain."""
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning("sso_sync_commit_failed", org_id=str(org.id), exc_info=True)
        try:
            from api.metrics import sso_sync_failures_total

            sso_sync_failures_total.inc()
        except Exception:
            pass
        raise APIError(
            503,
            "Service Unavailable",
            "SSO status could not be persisted; retry before changing SSO configuration",
        ) from exc


def _clerk_dashboard_url(clerk_org_id: str, settings) -> str | None:
    """Return a direct Clerk dashboard link when the domain is configured."""
    if not settings.clerk_domain:
        return None
    # The Clerk dashboard lives at https://dashboard.clerk.com — the org-level
    # SSO section is under /organizations/<org-id>/sso-connections.
    encoded_org_id = quote(clerk_org_id, safe="")
    return f"https://dashboard.clerk.com/organizations/{encoded_org_id}/sso-connections"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get_sso_status(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    http_client_cls=httpx.AsyncClient,
    now_fn: Callable[[], datetime] = _utc_now,
) -> SSOStatusResponse:
    """Return authoritative Clerk state or an explicitly stale cached snapshot."""
    settings = get_settings()
    org = await _load_org(db, org_id=org_id)
    fetch_started_at = now_fn()
    refresh_attempt_id = uuid.uuid4()

    # Claim a durable generation before leaving the database for Clerk. The
    # latest claim wins by database commit order, independent of application
    # clock skew. A completion may publish state only while it still owns this
    # token; this avoids holding a row lock across the network request.
    claim_result = cast(
        CursorResult[Any],
        await db.execute(
            update(Organization)
            .where(Organization.id == org.id)
            .values(
                sso_refresh_attempt_id=refresh_attempt_id,
                sso_last_refresh_started_at=fetch_started_at,
                sso_status_available=False,
            )
            .execution_options(synchronize_session=False)
        ),
    )
    if claim_result.rowcount == 0:
        await db.rollback()
        raise APIError(404, "Not Found", "Organization not found")
    org.sso_refresh_attempt_id = refresh_attempt_id
    org.sso_last_refresh_started_at = fetch_started_at
    # No policy mutation may rely on the previous snapshot while a newer live
    # refresh is unresolved. A crashed request therefore remains fail-closed
    # until the next successful refresh.
    org.sso_status_available = False
    await _commit_sso_status(db, org=org)

    fetch_result = await _fetch_clerk_enterprise_connections(
        clerk_org_id=org.clerk_org_id,
        settings=settings,
        http_client_cls=http_client_cls,
    )

    if fetch_result.available:
        fields = _connection_to_status(fetch_result.connections)
        synced_at = now_fn()
        # A slower success must not overwrite any refresh (success or failure)
        # that claimed the row later.
        sync_result = cast(
            CursorResult[Any],
            await db.execute(
                update(Organization)
                .where(
                    Organization.id == org.id,
                    Organization.sso_refresh_attempt_id == refresh_attempt_id,
                )
                .values(
                    sso_enabled=fields["sso_enabled"],
                    sso_provider=fields["provider"],
                    sso_domains=fields["domains"],
                    sso_status_available=True,
                    sso_last_synced_at=synced_at,
                    sso_last_refresh_started_at=fetch_started_at,
                )
                .execution_options(synchronize_session=False)
            ),
        )
        if sync_result.rowcount != 0:
            # Session synchronization is deliberately disabled so a CAS miss
            # cannot mutate a stale in-memory instance. Mirror the confirmed
            # write explicitly without issuing a second statement.
            org.sso_enabled = fields["sso_enabled"]
            org.sso_provider = fields["provider"]
            org.sso_domains = fields["domains"]
            org.sso_status_available = True
            org.sso_last_synced_at = synced_at
            org.sso_last_refresh_started_at = fetch_started_at
        await _commit_sso_status(db, org=org)
        if sync_result.rowcount == 0:
            await db.refresh(
                org,
                attribute_names=[
                    "sso_enabled",
                    "sso_provider",
                    "sso_domains",
                    "sso_status_available",
                    "sso_last_synced_at",
                    "sso_last_refresh_started_at",
                    "sso_refresh_attempt_id",
                ],
            )
            current_fresh = sso_status_is_fresh(
                available=org.sso_status_available is True,
                last_synced_at=org.sso_last_synced_at,
                now=synced_at,
            )
            current_available = org.sso_status_available is True
            current_fields = _cached_status_fields(org)
            return SSOStatusResponse(
                **current_fields,
                clerk_dashboard_url=(
                    _clerk_dashboard_url(org.clerk_org_id, settings) if current_fresh else None
                ),
                sso_status_available=current_available,
                sso_last_synced_at=org.sso_last_synced_at,
                sso_status_stale=not current_fresh,
                sso_unavailable_reason=None,
            )
        return SSOStatusResponse(
            sso_enabled=fields["sso_enabled"],
            provider=fields["provider"],
            domains=fields["domains"],
            status=fields["status"],
            clerk_dashboard_url=_clerk_dashboard_url(org.clerk_org_id, settings),
            sso_status_available=True,
            sso_last_synced_at=synced_at,
            sso_status_stale=False,
            sso_unavailable_reason=None,
        )

    # Failures participate in the same ordering as successes. This prevents an
    # older success from restoring availability after a newer failure, while
    # also preventing an older failure from invalidating a newer success.
    invalidate_result = cast(
        CursorResult[Any],
        await db.execute(
            update(Organization)
            .where(
                Organization.id == org.id,
                Organization.sso_refresh_attempt_id == refresh_attempt_id,
            )
            .values(
                sso_status_available=False,
                sso_last_refresh_started_at=fetch_started_at,
            )
            .execution_options(synchronize_session=False)
        ),
    )
    if invalidate_result.rowcount != 0:
        org.sso_status_available = False
        org.sso_last_refresh_started_at = fetch_started_at
    await _commit_sso_status(db, org=org)

    if invalidate_result.rowcount == 0:
        await db.refresh(
            org,
            attribute_names=[
                "sso_enabled",
                "sso_provider",
                "sso_domains",
                "sso_status_available",
                "sso_last_synced_at",
                "sso_last_refresh_started_at",
                "sso_refresh_attempt_id",
            ],
        )
        if org.sso_status_available is True:
            fields = _cached_status_fields(org)
            current_fresh = sso_status_is_fresh(
                available=True,
                last_synced_at=org.sso_last_synced_at,
                now=now_fn(),
            )
            return SSOStatusResponse(
                **fields,
                clerk_dashboard_url=(
                    _clerk_dashboard_url(org.clerk_org_id, settings) if current_fresh else None
                ),
                sso_status_available=True,
                sso_last_synced_at=org.sso_last_synced_at,
                sso_status_stale=not current_fresh,
                sso_unavailable_reason=None,
            )

    org.sso_status_available = False
    fields = _cached_status_fields(org)

    return SSOStatusResponse(
        **fields,
        clerk_dashboard_url=None,
        sso_status_available=False,
        sso_last_synced_at=org.sso_last_synced_at,
        sso_status_stale=True,
        sso_unavailable_reason=fetch_result.unavailable_reason,
    )


async def configure_sso(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    body: SSOConfigureRequest,
    request=None,
    http_client_cls=httpx.AsyncClient,
    now_fn: Callable[[], datetime] = _utc_now,
) -> SSOConfigureResponse:
    """Log an admin intent to enable/disable SSO and return setup instructions.

    Full SAML configuration (IdP metadata upload, attribute mapping) is
    completed in the Clerk dashboard — we cannot do it programmatically without
    the IdP XML. This endpoint logs the intent for audit purposes and returns
    the actionable next-steps for the admin.
    """
    settings = get_settings()
    org = await _load_org(db, org_id=org_id, for_update=True)
    if not sso_status_is_fresh(
        available=org.sso_status_available is True,
        last_synced_at=org.sso_last_synced_at,
        now=now_fn(),
    ):
        raise APIError(
            503,
            "Service Unavailable",
            "Live SSO status is unavailable or stale; refresh it before changing configuration",
        )
    org.sso_required = body.enable

    action = "admin.sso.enable_requested" if body.enable else "admin.sso.disable_requested"

    await write_audit_log(
        db,
        org_id=org_id,
        user_id=user_id,
        action=action,
        details={
            "clerk_org_id": org.clerk_org_id,
            "requested_enable": body.enable,
            "sso_required": body.enable,
        },
        request=request,
        fail_closed=True,
    )
    await db.commit()

    dashboard_url = _clerk_dashboard_url(org.clerk_org_id, settings)

    if body.enable:
        next_steps = [
            "Open the Clerk dashboard using the link below.",
            "Navigate to your organization and select 'SSO Connections'.",
            "Choose your Identity Provider (Okta, Azure AD, Google Workspace, or Custom SAML/OIDC).",  # noqa: E501
            "Follow the IdP-specific instructions to upload SAML metadata or configure OIDC.",
            "Add and verify the email domain(s) that should be enforced for SSO.",
            "Return to this page — SSO status updates automatically once the connection is active.",
        ]
        message = (
            "SSO setup requires completing the configuration in your Clerk dashboard. "
            "A deployment operator must own and support the IdP configuration."
        )
    else:
        next_steps = [
            "Open the Clerk dashboard using the link below.",
            "Navigate to your organization's SSO Connections.",
            "Deactivate or delete the existing enterprise connection.",
            "Return to this page once the connection is removed.",
        ]
        message = (
            "To disable SSO, remove the enterprise connection in your Clerk dashboard. "
            "Users will revert to password or social sign-in after the connection is removed."
        )

    logger.info(
        "sso_configure_requested",
        org_id=str(org_id),
        user_id=str(user_id),
        enable=body.enable,
    )

    return SSOConfigureResponse(
        status="instructions_provided",
        message=message,
        next_steps=next_steps,
        clerk_dashboard_url=dashboard_url,
    )
