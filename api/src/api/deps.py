"""Shared FastAPI dependencies."""

from __future__ import annotations

import asyncio
import inspect
import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, cast

import jwt
import structlog
from fastapi import Depends, Request, status
from jwt.exceptions import PyJWKClientConnectionError
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import write_audit_log
from api.auth.clerk import clerk_v2_org_context, verify_clerk_token
from api.circuit_breaker import CircuitOpenError
from api.config import APISettings, get_settings
from api.db.models import Organization, User, UserRole
from api.db.session import bind_current_org_to_session, get_db
from api.errors import APIError
from api.observability.spans import set_current_span_attributes
from api.schemas.apikeys import APIKeyScope
from api.services.apikeys import authenticate_api_key
from api.services.clerk_webhooks import NON_ADMIN_USER_ROLES, bootstrap_clerk_membership

logger = structlog.get_logger()

DEV_TOKEN = "dev-token"
DEV_CLERK_USER_ID = "dev_user_local"

# Organization states that must reject tenant authentication. ``pending`` is
# deliberately excluded so customers retain access during the 30-day recovery
# window. Once provider cleanup starts, no request may create fresh data behind
# the erasure fence.
_AUTH_BLOCKED_DELETION_STATUSES = frozenset(
    {"billing_cancellation_pending", "archive_deletion_pending", "erased"}
)
_CLERK_PRINCIPAL_RACE_CONSTRAINTS = frozenset(
    {
        "organizations_clerk_org_id_key",
        "uq_users_clerk_user_org",
        "uq_users_clerk_membership_id",
    }
)


@dataclass(frozen=True)
class _ClerkPrincipal:
    user_id: str
    org_id: str
    org_role: str | None


_PrincipalRow = Sequence[object]


def _integrity_constraint_name(exc: IntegrityError) -> str | None:
    orig = exc.orig
    direct = getattr(orig, "constraint_name", None)
    if isinstance(direct, str):
        return direct
    cause = getattr(orig, "__cause__", None)
    nested = getattr(cause, "constraint_name", None)
    return nested if isinstance(nested, str) else None


def _membership_authority_is_consistent(user: User, *, token_org_role: str | None) -> bool:
    if (
        not user.clerk_membership_id
        or not user.membership_active
        or getattr(user, "membership_deleted_at", None) is not None
        or getattr(user, "membership_permission_denied_at", None) is not None
        or user.clerk_membership_role != token_org_role
    ):
        return False
    if token_org_role == "admin":
        return user.role == UserRole.ADMIN
    if token_org_role == "member":
        return user.role in NON_ADMIN_USER_ROLES
    return False


def _bind_authenticated_context(user: object, *, org_id: object) -> None:
    context = {"org_id": str(org_id)}
    span_attributes = {"tenant.id": str(org_id)}
    user_id = getattr(user, "id", None)
    if user_id:
        context["user_id"] = str(user_id)
        span_attributes["enduser.id"] = str(user_id)
    api_key_id = getattr(user, "api_key_id", None)
    actor_type = "api_key" if api_key_id else "clerk_user"
    context["actor_type"] = actor_type
    span_attributes["enduser.actor_type"] = actor_type
    if api_key_id:
        context["api_key_id"] = str(api_key_id)
        span_attributes["enduser.api_key_id"] = str(api_key_id)
    structlog.contextvars.bind_contextvars(**context)
    set_current_span_attributes(span_attributes)


def _bind_request_actor(request: Request, principal: object) -> None:
    """Attach non-secret actor attribution for downstream audit writes."""
    api_key_id = getattr(principal, "api_key_id", None)
    request.state.auth_actor_type = "api_key" if api_key_id else "clerk_user"
    request.state.auth_api_key_id = str(api_key_id) if api_key_id else None


# ── Centralized RBAC ─────────────────────────────────────────────────────────

PERMISSION_MATRIX: dict[str, set[UserRole]] = {
    "analysis.create": {UserRole.ADMIN, UserRole.ATTORNEY, UserRole.SCIENTIST},
    "analysis.delete": {UserRole.ADMIN, UserRole.ATTORNEY},
    "analysis.view": {UserRole.ADMIN, UserRole.ATTORNEY, UserRole.SCIENTIST, UserRole.CLIENT},
    "report.view_full": {UserRole.ADMIN, UserRole.ATTORNEY, UserRole.SCIENTIST},
    "report.view_summary": {UserRole.ADMIN, UserRole.ATTORNEY, UserRole.SCIENTIST, UserRole.CLIENT},
    "report.share": {UserRole.ADMIN, UserRole.ATTORNEY},
    "report.export": {UserRole.ADMIN, UserRole.ATTORNEY, UserRole.SCIENTIST},
    "comment.create": {UserRole.ADMIN, UserRole.ATTORNEY, UserRole.SCIENTIST},
    "reviewer_decision.create": {UserRole.ADMIN, UserRole.ATTORNEY},
    "reviewer_decision.view": {UserRole.ADMIN, UserRole.ATTORNEY},
    "claimed_use_receipt.issue": {UserRole.ATTORNEY},
    "claimed_use_receipt.view": {UserRole.ADMIN, UserRole.ATTORNEY},
    "claimed_use_receipt.revoke": {UserRole.ADMIN, UserRole.ATTORNEY},
    "checkpoint_decision.create": {UserRole.ADMIN, UserRole.ATTORNEY, UserRole.SCIENTIST},
    "config.manage": {UserRole.ADMIN, UserRole.ATTORNEY},
    "admin.view": {UserRole.ADMIN},
    "admin.manage_users": {UserRole.ADMIN},
    "billing.view": {
        UserRole.ADMIN,
        UserRole.ATTORNEY,
        UserRole.SCIENTIST,
        UserRole.CLIENT,
    },
    "billing.manage": {UserRole.ADMIN},
    "monitor.manage": {UserRole.ADMIN, UserRole.ATTORNEY, UserRole.SCIENTIST},
    "batch.create": {UserRole.ADMIN, UserRole.ATTORNEY, UserRole.SCIENTIST},
    "apikey.manage": {UserRole.ADMIN},
}


def require_permission(permission: str):
    """FastAPI dependency that checks role-based permission."""

    async def _checker(user: Annotated[User, Depends(get_current_user)]) -> User:
        allowed_roles = PERMISSION_MATRIX.get(permission, set())
        if user.role not in allowed_roles:
            raise APIError(
                status.HTTP_403_FORBIDDEN,
                "Forbidden",
                f"Insufficient permissions: requires {permission}",
            )
        return user

    return _checker


@dataclass(frozen=True)
class APIKeyPrincipal:
    """Minimal user-like principal for scoped server-to-server API keys."""

    id: uuid.UUID
    org_id: uuid.UUID
    role: UserRole
    api_key_id: uuid.UUID
    api_key_scopes: tuple[str, ...]
    clerk_user_id: str = "api_key"
    email: str = "api-key@praviar.local"
    full_name: str = "Scoped API key"


AuthenticatedPrincipal = User | APIKeyPrincipal


async def _resolve_current_user_with_overrides(request: Request, db: AsyncSession) -> User:
    app = getattr(request, "app", None)
    override = getattr(app, "dependency_overrides", {}).get(get_current_user)
    if override is not None:
        resolved = override()
        if inspect.isawaitable(resolved):
            return cast(User, await resolved)
        return cast(User, resolved)
    return await get_current_user(request, db)


async def get_authenticated_principal(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthenticatedPrincipal:
    """Authenticate one Clerk user or scoped API-key principal per request.

    Route-level rate limiters and permission checks must share this exact
    dependency so FastAPI's dependency cache authenticates the presented
    credential once.  API-key scope authorization remains a separate,
    route-specific check below; this resolver only establishes identity and
    tenant context.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        api_key = await authenticate_api_key(token, db)
        if api_key is not None:
            principal = APIKeyPrincipal(
                id=api_key.user_id,
                org_id=api_key.org_id,
                role=UserRole.SCIENTIST,
                api_key_id=api_key.id,
                api_key_scopes=tuple(api_key.scopes or ()),
            )
            _bind_authenticated_context(principal, org_id=principal.org_id)
            _bind_request_actor(request, principal)
            return principal

    user = await _resolve_current_user_with_overrides(request, db)
    _bind_request_actor(request, user)
    return user


def require_permission_or_api_key_scope(permission: str, api_key_scope: APIKeyScope):
    """Allow a Clerk user with RBAC permission or an API key with one explicit scope."""

    async def _checker(
        principal: Annotated[AuthenticatedPrincipal, Depends(get_authenticated_principal)],
    ) -> AuthenticatedPrincipal:
        if isinstance(principal, APIKeyPrincipal):
            if api_key_scope not in principal.api_key_scopes:
                raise APIError(
                    status.HTTP_403_FORBIDDEN,
                    "Forbidden",
                    f"API key scope required: {api_key_scope}",
                )
            return principal

        allowed_roles = PERMISSION_MATRIX.get(permission, set())
        if principal.role not in allowed_roles:
            raise APIError(
                status.HTTP_403_FORBIDDEN,
                "Forbidden",
                f"Insufficient permissions: requires {permission}",
            )
        return principal

    return _checker


def _require_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        logger.warning("auth_missing_bearer", path=request.url.path)
        raise APIError(
            status.HTTP_401_UNAUTHORIZED,
            "Unauthorized",
            "Missing or invalid authorization header",
        )
    return auth_header.removeprefix("Bearer ").strip()


def _dev_auth_bypass_enabled(settings: APISettings, *, token: str) -> bool:
    return settings.allow_dev_auth_bypass and settings.app_env == "dev" and token == DEV_TOKEN


async def _resolve_dev_user(request: Request, db: AsyncSession) -> User:
    test_org_header = request.headers.get("X-Test-Org-Id", "").strip()
    if test_org_header:
        try:
            test_org_id = uuid.UUID(test_org_header)
        except ValueError as exc:
            raise APIError(
                status.HTTP_401_UNAUTHORIZED,
                "Unauthorized",
                "Invalid X-Test-Org-Id header",
            ) from exc
        dev_user = User(
            id=uuid.uuid5(uuid.NAMESPACE_URL, f"dev-user:{test_org_id}"),
            clerk_user_id=f"{DEV_CLERK_USER_ID}:{test_org_id}",
            org_id=test_org_id,
            email="dev@praviar.local",
            full_name="Praviar Dev User",
            role=UserRole.ADMIN,
        )
        await bind_current_org_to_session(db, dev_user.org_id)
        _bind_authenticated_context(dev_user, org_id=dev_user.org_id)
        return dev_user

    result = await db.execute(select(User).where(User.clerk_user_id == DEV_CLERK_USER_ID))
    stored_dev_user = result.scalar_one_or_none()
    if stored_dev_user is None:
        raise APIError(
            status.HTTP_404_NOT_FOUND,
            "Not Found",
            "Dev user not found. Run the seed script to create it.",
        )
    await bind_current_org_to_session(db, stored_dev_user.org_id)
    _bind_authenticated_context(stored_dev_user, org_id=stored_dev_user.org_id)
    return stored_dev_user


async def _verify_clerk_principal(token: str) -> _ClerkPrincipal:
    try:
        # PyJWKClient uses urllib for cache refreshes. Keep that blocking work
        # off the async request loop even when the key is normally cache-resident.
        payload = await asyncio.to_thread(verify_clerk_token, token)
        token_org_context = clerk_v2_org_context(payload)
    except CircuitOpenError as exc:
        retry_after_seconds = max(1, math.ceil(exc.retry_after_s))
        logger.warning(
            "clerk_jwks_circuit_open",
            retry_after_seconds=retry_after_seconds,
        )
        raise APIError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Service Unavailable",
            "Authentication provider is temporarily unavailable",
            retry_after_seconds=retry_after_seconds,
        ) from exc
    except PyJWKClientConnectionError as exc:
        logger.warning(
            "clerk_jwks_connection_failed",
            error_type=type(exc).__name__,
        )
        raise APIError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Service Unavailable",
            "Authentication provider is temporarily unavailable",
            retry_after_seconds=5,
        ) from exc
    except (jwt.PyJWTError, ValueError) as exc:
        logger.warning("token_verification_failed", error_type=type(exc).__name__)
        raise APIError(
            status.HTTP_401_UNAUTHORIZED,
            "Unauthorized",
            "Invalid authentication token",
        ) from exc

    clerk_user_id = payload.get("sub", "")
    token_org_id = token_org_context[0] if token_org_context is not None else None
    token_org_role = token_org_context[1] if token_org_context is not None else None
    if token_org_id is None:
        raise APIError(
            status.HTTP_403_FORBIDDEN,
            "Organization Required",
            "Select an organization before continuing.",
        )
    return _ClerkPrincipal(
        user_id=clerk_user_id,
        org_id=token_org_id,
        org_role=token_org_role,
    )


def _principal_query(principal: _ClerkPrincipal) -> Select[tuple[User, str | None, str]]:
    # Resolve the user and tenant-erasure state in one round-trip. Erasure keeps
    # the user row for FK integrity, so authentication must inspect the org too.
    return (
        select(User, Organization.deletion_status, Organization.clerk_org_id)
        .join(Organization, User.org_id == Organization.id)
        .where(
            User.clerk_user_id == principal.user_id,
            User.membership_active.is_(True),
            User.membership_deleted_at.is_(None),
            User.membership_permission_denied_at.is_(None),
            Organization.clerk_org_id == principal.org_id,
        )
    )


def _reject_blocked_organization(row: _PrincipalRow | None, *, clerk_user_id: str) -> None:
    if row is None or row[1] not in _AUTH_BLOCKED_DELETION_STATUSES:
        return
    user = cast(User, row[0])
    logger.warning(
        "auth_rejected_org_erasure",
        clerk_user_id=clerk_user_id,
        org_id=str(user.org_id),
        deletion_status=row[1],
    )
    raise APIError(
        status.HTTP_403_FORBIDDEN,
        "Forbidden",
        "This organization is being deleted or has been deleted.",
    )


def _principal_needs_reconciliation(
    row: _PrincipalRow | None,
    *,
    token_org_role: str | None,
) -> bool:
    persisted_user = cast(User, row[0]) if row is not None else None
    return persisted_user is None or not _membership_authority_is_consistent(
        persisted_user,
        token_org_role=token_org_role,
    )


async def _bootstrap_membership(
    db: AsyncSession,
    principal: _ClerkPrincipal,
    *,
    settings: APISettings,
) -> None:
    await bootstrap_clerk_membership(
        db,
        clerk_user_id=principal.user_id,
        clerk_org_id=principal.org_id,
        token_org_role=principal.org_role or "",
        settings=settings,
        write_audit_log_fn=write_audit_log,
    )


async def _retry_membership_after_organization_race(
    db: AsyncSession,
    principal: _ClerkPrincipal,
    *,
    settings: APISettings,
) -> None:
    try:
        await _bootstrap_membership(db, principal, settings=settings)
        await db.commit()
    except IntegrityError as retry_exc:
        await db.rollback()
        retry_constraint = _integrity_constraint_name(retry_exc)
        if retry_constraint not in {
            "uq_users_clerk_user_org",
            "uq_users_clerk_membership_id",
        }:
            raise
        logger.info(
            "clerk_membership_bootstrap_user_race_lost",
            clerk_user_id=principal.user_id,
            clerk_org_id=principal.org_id,
            constraint=retry_constraint,
        )
    except Exception:
        await db.rollback()
        raise


async def _reconcile_clerk_principal(
    db: AsyncSession,
    principal: _ClerkPrincipal,
    *,
    settings: APISettings,
) -> None:
    # End the principal lookup transaction before Clerk I/O. Bootstrap performs
    # the provider read first, then applies its snapshot in a fresh transaction.
    await db.rollback()
    try:
        await _bootstrap_membership(db, principal, settings=settings)
        # Persist first-login reconciliation before a read-only handler returns.
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        constraint_name = _integrity_constraint_name(exc)
        if constraint_name not in _CLERK_PRINCIPAL_RACE_CONSTRAINTS:
            raise
        if constraint_name == "organizations_clerk_org_id_key":
            # An organization.created delivery may have won only the org insert.
            # Retry the authoritative principal upsert once against that org.
            await _retry_membership_after_organization_race(db, principal, settings=settings)
            return
        logger.info(
            "clerk_membership_bootstrap_race_lost",
            clerk_user_id=principal.user_id,
            clerk_org_id=principal.org_id,
            constraint=constraint_name,
        )
    except Exception:
        await db.rollback()
        raise


async def _resolve_clerk_principal_row(
    db: AsyncSession,
    principal: _ClerkPrincipal,
    *,
    settings: APISettings,
) -> _PrincipalRow | None:
    principal_query = _principal_query(principal)
    row = (await db.execute(principal_query)).first()
    _reject_blocked_organization(row, clerk_user_id=principal.user_id)

    if _principal_needs_reconciliation(row, token_org_role=principal.org_role):
        await _reconcile_clerk_principal(db, principal, settings=settings)
        row = (await db.execute(principal_query)).first()
    return row


def _require_authorized_user(row: _PrincipalRow | None, principal: _ClerkPrincipal) -> User:
    if row is None:
        logger.warning("auth_user_not_found", clerk_user_id=principal.user_id)
        raise APIError(
            status.HTTP_404_NOT_FOUND,
            "Not Found",
            "User not found. Please complete onboarding.",
        )

    db_user = cast(User, row[0])
    _reject_blocked_organization(row, clerk_user_id=principal.user_id)

    clerk_org_id = row[2]
    if principal.org_id != clerk_org_id:
        logger.warning(
            "auth_rejected_org_mismatch",
            clerk_user_id=principal.user_id,
            org_id=str(db_user.org_id),
            clerk_org_id=clerk_org_id,
            token_org_id=principal.org_id,
        )
        raise APIError(
            status.HTTP_403_FORBIDDEN,
            "Forbidden",
            "The authenticated organization does not match this workspace.",
        )

    # Clerk admin maps exactly to local admin. Clerk members may hold only one
    # of the explicitly non-admin application roles carried in metadata.
    if not _membership_authority_is_consistent(
        db_user,
        token_org_role=principal.org_role,
    ):
        logger.warning(
            "auth_rejected_membership_role_mismatch",
            clerk_user_id=principal.user_id,
            org_id=str(db_user.org_id),
            token_org_role=principal.org_role,
            persisted_membership_role=db_user.clerk_membership_role,
            persisted_local_role=db_user.role.value,
        )
        raise APIError(
            status.HTTP_403_FORBIDDEN,
            "Forbidden",
            "Organization membership is not synchronized.",
        )
    return db_user


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Extract and verify Clerk JWT, then resolve to local User row.

    When explicitly enabled for local development, accepts "dev-token" and
    returns the dev user.
    Raises 401 if token is missing/invalid, 404 if user not in DB.

    T1-07 JWT audit (2026-05-20):
    - All end-user API routes depend on this function via get_current_user or require_permission.
    - verify_clerk_token() (api/auth/clerk.py) validates: alg=RS256 (rejects "none"),
      iss, exp, nbf, Clerk v2 claims, and azp against the configured app/CORS
      origin allowlist. JWKs are fetched from Clerk and cached with TTL.
    - Internal routes (api/routes/internal.py) use google-auth OIDC validation via
      Cloud Tasks — not Clerk JWTs; covered by a separate OIDC dependency.
    - Webhooks (routes/webhooks.py, webhooks_stripe.py) verify Svix and Stripe HMAC
      signatures respectively — not Clerk JWTs; no JWT path exists there.
    - No route reads Authorization headers outside this dependency. Confirmed by:
      grep -r "request.headers" api/src/api/routes/ (no raw Bearer reads found).
    - Verdict: RFC 8725 coverage is complete on all three authentication paths.
    """
    token = _require_bearer_token(request)
    settings = get_settings()

    if _dev_auth_bypass_enabled(settings, token=token):
        return await _resolve_dev_user(request, db)

    principal = await _verify_clerk_principal(token)
    row = await _resolve_clerk_principal_row(db, principal, settings=settings)
    db_user = _require_authorized_user(row, principal)

    # RLS: bind org_id to the current transaction and to future transactions
    # opened by this request's SQLAlchemy session.
    await bind_current_org_to_session(db, db_user.org_id)
    _bind_authenticated_context(db_user, org_id=db_user.org_id)
    return db_user


# Type alias for dependency injection
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentPrincipal = Annotated[AuthenticatedPrincipal, Depends(get_authenticated_principal)]
DBSession = Annotated[AsyncSession, Depends(get_db)]
