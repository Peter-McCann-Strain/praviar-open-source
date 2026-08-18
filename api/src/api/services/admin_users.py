"""User-query and user-mutation helpers for admin dashboards.

Consolidates the former admin user family:
  admin_users        -- user listing queries
  admin_user_roles   -- user-role mutation helpers
  admin_user_invites -- user invite helpers
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any, Protocol, TypeGuard, cast
from urllib.parse import quote

import httpx
import structlog
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import ClerkAdminOperation, Organization, User, UserRole
from api.errors import APIError, problem_type_uri
from api.schemas.admin import InviteRequest, UpdateUserRoleRequest, UserSummary
from api.services.admin_health import AdminUserPage
from api.services.admin_query_utils import execute_paged_query, load_id_map

logger = structlog.get_logger()

CLERK_API_VERSION = "2026-05-12"
PRAVIAR_ROLE_METADATA_VERSION = 1
PRAVIAR_INVITATION_OPERATION_KEY = "praviar_invitation_operation_id"
NON_ADMIN_INVITE_ROLES = frozenset({UserRole.ATTORNEY, UserRole.SCIENTIST, UserRole.CLIENT})
_CLERK_RETRYABLE_STATUS_CODES = frozenset({408, 429, *range(500, 600)})
_ADMIN_OPERATION_TERMINAL_STATES = frozenset({"completed", "failed"})
_ADMIN_OPERATION_TERMINAL_FAILURE_TYPE = problem_type_uri("admin-operation-terminal-failure")
_PARTIAL_METADATA_ROLE_REJECTION_PREFIX = "clerk_role_rejected_after_metadata_"
_PARTIAL_METADATA_ROLE_REJECTION_RE = re.compile(
    rf"{re.escape(_PARTIAL_METADATA_ROLE_REJECTION_PREFIX)}(4\d{{2}})"
)
# Clerk timestamps are compared with PostgreSQL's wall clock only after the
# canonical org->principal->operation locks are held. Five minutes tolerates
# ordinary provider/DB clock drift without accepting arbitrarily future-dated
# authority snapshots.
_PROVIDER_TIMESTAMP_FUTURE_SKEW = timedelta(minutes=5)


class _KnownClerkRejectionError(APIError):
    """A provider 4xx that proves the attempted mutation was rejected."""

    def __init__(self, status_code: int) -> None:
        self.provider_status_code = status_code
        super().__init__(
            502,
            "Bad Gateway",
            f"Clerk rejected the request ({status_code})",
            type_uri=_ADMIN_OPERATION_TERMINAL_FAILURE_TYPE,
        )


async def _database_clock(db: AsyncSession) -> datetime:
    value = await db.scalar(select(func.clock_timestamp()))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise APIError(503, "Service Unavailable", "Database authority clock is unavailable")
    return value.astimezone(UTC)


def _validate_provider_authority_timestamp(
    provider_updated_at: datetime,
    *,
    database_now: datetime,
    watermarks: tuple[datetime | None, ...],
) -> None:
    if provider_updated_at > database_now + _PROVIDER_TIMESTAMP_FUTURE_SKEW:
        raise APIError(409, "Conflict", "Clerk returned a future-dated membership snapshot")
    watermark = max((value for value in watermarks if value is not None), default=None)
    if watermark is not None and provider_updated_at < watermark:
        raise APIError(409, "Conflict", "Clerk returned a stale membership snapshot")


def _partial_metadata_role_rejection_status(error_code: object) -> int | None:
    if not isinstance(error_code, str):
        return None
    match = _PARTIAL_METADATA_ROLE_REJECTION_RE.fullmatch(error_code)
    if match is None:
        return None
    status_code = int(match.group(1))
    if status_code in _CLERK_RETRYABLE_STATUS_CODES:
        return None
    return status_code


def _secret_value(value: object) -> str:
    getter = getattr(value, "get_secret_value", None)
    return str(getter() if callable(getter) else value or "")


def _admin_operation_hmac_secret(settings) -> str:
    secret = _secret_value(getattr(settings, "api_key_hmac_secret", "")).strip()
    if not secret:
        raise APIError(
            503,
            "Service Unavailable",
            "Admin operation privacy HMAC is not configured",
        )
    return secret


def _admin_operation_digests(
    *,
    settings,
    org_id: uuid.UUID,
    idempotency_key: str,
    request_payload: dict[str, object],
) -> tuple[str, str]:
    canonical = json.dumps(request_payload, sort_keys=True, separators=(",", ":"))
    request_hash = hashlib.sha256(canonical.encode()).hexdigest()
    secret = _admin_operation_hmac_secret(settings)
    digest = hmac.new(
        secret.encode(),
        b"clerk-admin-operation:v1\0" + org_id.bytes + b"\0" + idempotency_key.encode(),
        hashlib.sha256,
    ).hexdigest()
    return digest, request_hash


def _privacy_email_digest(*, settings, org_id: uuid.UUID, email: str) -> str:
    secret = _admin_operation_hmac_secret(settings)
    return hmac.new(
        secret.encode(),
        b"admin-invite-email:v1\0" + org_id.bytes + b"\0" + email.strip().casefold().encode(),
        hashlib.sha256,
    ).hexdigest()


async def _claim_admin_operation(
    db: AsyncSession,
    *,
    settings,
    org_id: uuid.UUID,
    admin_id: uuid.UUID,
    operation_type: str,
    idempotency_key: str,
    request_payload: dict[str, object],
    target_user_id: uuid.UUID | None,
    target_email_normalized: str | None,
    requested_role: str,
    write_audit_log_fn,
    requested_action: str,
    requested_details: dict[str, object],
) -> tuple[ClerkAdminOperation, bool]:
    valid_roles = {role.value for role in UserRole}
    valid_shape = (
        operation_type == "role_update"
        and target_user_id is not None
        and target_email_normalized is None
    ) or (
        operation_type == "invite"
        and target_user_id is None
        and bool(target_email_normalized)
        and requested_role != UserRole.ADMIN.value
    )
    if not valid_shape or requested_role not in valid_roles:
        raise APIError(409, "Conflict", "Admin operation target or role shape is invalid")
    key_digest, request_hash = _admin_operation_digests(
        settings=settings,
        org_id=org_id,
        idempotency_key=idempotency_key,
        request_payload=request_payload,
    )

    # A canonical organization lock serializes claims even when no scope row
    # exists yet, closing the partial-unique-index race before provider I/O.
    await _lock_org(db, org_id=org_id)

    async def _load() -> ClerkAdminOperation | None:
        return (
            await db.execute(
                select(ClerkAdminOperation)
                .where(
                    ClerkAdminOperation.org_id == org_id,
                    ClerkAdminOperation.client_key_digest == key_digest,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    async def _load_open_scope() -> ClerkAdminOperation | None:
        scope_query = select(ClerkAdminOperation).where(
            ClerkAdminOperation.org_id == org_id,
            ClerkAdminOperation.operation_type == operation_type,
            ClerkAdminOperation.state.not_in(_ADMIN_OPERATION_TERMINAL_STATES),
        )
        if operation_type == "role_update":
            scope_query = scope_query.where(ClerkAdminOperation.target_user_id == target_user_id)
        else:
            scope_query = scope_query.where(
                ClerkAdminOperation.target_email_normalized == target_email_normalized
            )
        return (await db.execute(scope_query.with_for_update())).scalar_one_or_none()

    operation = await _load()
    if operation is not None:
        if operation.request_hash != request_hash:
            raise APIError(
                409,
                "Conflict",
                "Idempotency-Key was already used with a different admin request",
            )
        return operation, False

    scoped_operation = await _load_open_scope()
    if scoped_operation is not None:
        if scoped_operation.request_hash == request_hash:
            return scoped_operation, False
        raise APIError(
            409,
            "Conflict",
            "A different admin operation for this target requires reconciliation",
        )

    operation = ClerkAdminOperation(
        id=uuid.uuid4(),
        org_id=org_id,
        initiated_by=admin_id,
        operation_type=operation_type,
        client_key_digest=key_digest,
        request_hash=request_hash,
        state="requested",
        target_user_id=target_user_id,
        target_email_normalized=target_email_normalized,
        requested_role=requested_role,
    )
    db.add(operation)
    try:
        await write_audit_log_fn(
            db,
            org_id=org_id,
            user_id=admin_id,
            action=requested_action,
            details={"operation_id": str(operation.id), **requested_details},
            fail_closed=True,
        )
        await db.commit()
        return operation, True
    except IntegrityError as exc:
        await db.rollback()
        operation = await _load()
        if operation is None:
            operation = await _load_open_scope()
        if operation is None:
            raise
        if operation.request_hash != request_hash:
            raise APIError(
                409,
                "Conflict",
                "Idempotency-Key was already used with a different admin request",
            ) from exc
        return operation, False
    except Exception:
        await db.rollback()
        raise


async def _load_admin_operation_by_id(
    db: AsyncSession,
    *,
    operation_id: uuid.UUID,
    for_update: bool,
) -> ClerkAdminOperation:
    query = select(ClerkAdminOperation).where(ClerkAdminOperation.id == operation_id)
    if for_update:
        query = query.with_for_update().execution_options(populate_existing=True)
    operation = (await db.execute(query)).scalar_one_or_none()
    if operation is None:
        raise APIError(409, "Conflict", "Admin operation no longer exists")
    return operation


def _can_terminally_fail_without_reconciliation(
    operation: ClerkAdminOperation,
    exc: Exception,
) -> bool:
    if operation.state == "requested":
        return True
    return isinstance(exc, _KnownClerkRejectionError) and operation.provider_updated_at is None


def _is_partial_metadata_role_rejection(
    operation: ClerkAdminOperation,
    exc: Exception,
) -> bool:
    """Return whether Clerk rejected only the coarse-role step of a demotion."""
    return (
        isinstance(exc, _KnownClerkRejectionError)
        and operation.operation_type == "role_update"
        and operation.state == "role_call_started"
        and operation.provider_updated_at is not None
        and operation.requested_role != UserRole.ADMIN.value
    )


def _terminalize_role_failure(
    target_user: User,
    *,
    operation: ClerkAdminOperation,
    exc: Exception,
    denied_at: datetime,
) -> bool:
    """Terminalize a proven rejection and return whether metadata was partially applied."""
    partial_metadata_accepted = _is_partial_metadata_role_rejection(operation, exc)
    if partial_metadata_accepted:
        assert isinstance(exc, _KnownClerkRejectionError)
        assert operation.provider_updated_at is not None
        # Clerk accepted the least-privilege app-role metadata but rejected the
        # coarse-role mutation. Keep the principal denied without leaving a
        # terminal operation as its owner. The requested local role is safe to
        # persist because every auth path still rejects the generic deny marker.
        if target_user.membership_permission_denied_by_operation_id == operation.id:
            target_user.membership_permission_denied_by_operation_id = None
        if target_user.membership_permission_denied_at is None:
            target_user.membership_permission_denied_at = denied_at
        target_user.membership_permission_convergence_operation_id = operation.id
        target_user.role = UserRole(operation.requested_role)
        target_user.membership_updated_at = max(
            target_user.membership_updated_at,
            operation.provider_updated_at,
        )
        operation.last_error_code = (
            f"{_PARTIAL_METADATA_ROLE_REJECTION_PREFIX}{exc.provider_status_code}"
        )[:64]
    else:
        _clear_operation_owned_denial(target_user, operation=operation)
        operation.last_error_code = (
            f"clerk_{exc.provider_status_code}"
            if isinstance(exc, _KnownClerkRejectionError)
            else type(exc).__name__
        )[:64]
    operation.state = "failed"
    return partial_metadata_accepted


def _raise_failed_operation() -> None:
    raise APIError(
        409,
        "Conflict",
        "This admin operation previously failed; submit a new Idempotency-Key",
    )


# ---------------------------------------------------------------------------
# User listing  (formerly admin_users)
# ---------------------------------------------------------------------------


def _build_user_page_queries(
    *,
    org_id: uuid.UUID | None,
) -> tuple:
    base_query = select(User).where(User.membership_active.is_(True))
    count_query = select(func.count()).select_from(User).where(User.membership_active.is_(True))
    if org_id:
        base_query = base_query.where(User.org_id == org_id)
        count_query = count_query.where(User.org_id == org_id)
    return base_query, count_query


async def _load_org_names(
    db: AsyncSession,
    *,
    users: list[User],
) -> dict[uuid.UUID, str]:
    org_ids = {user.org_id for user in users}
    return await load_id_map(
        db,
        model=Organization,
        id_column=Organization.id,
        value_column=Organization.name,
        ids=org_ids,
    )


async def list_users_page_impl(
    db: AsyncSession,
    *,
    org_id: uuid.UUID | None,
    page: int,
    per_page: int,
) -> AdminUserPage:
    """Return a paginated list of users, optionally filtered by organisation."""
    base_query, count_query = _build_user_page_queries(org_id=org_id)
    total, users = await execute_paged_query(
        db,
        base_query=base_query,
        count_query=count_query,
        order_by=User.created_at.desc(),
        page=page,
        per_page=per_page,
    )
    org_names = await _load_org_names(db, users=users)

    items = [
        UserSummary(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role.value,
            org_id=user.org_id,
            org_name=org_names.get(user.org_id, ""),
            last_active_at=user.last_active_at,
            membership_active=user.membership_active,
            membership_synchronized=(
                user.membership_permission_denied_at is None
                and bool(user.clerk_membership_id)
                and (
                    (user.clerk_membership_role == "admin" and user.role == UserRole.ADMIN)
                    or (
                        user.clerk_membership_role == "member"
                        and user.role in NON_ADMIN_INVITE_ROLES
                    )
                )
            ),
            created_at=user.created_at,
        )
        for user in users
    ]
    return AdminUserPage(items=items, total=total)


# ---------------------------------------------------------------------------
# User-role mutations  (formerly admin_user_roles)
# ---------------------------------------------------------------------------


async def _load_target_user(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    for_update: bool = False,
) -> User:
    query = select(User).where(User.id == user_id)
    if for_update:
        query = query.with_for_update().execution_options(populate_existing=True)
    target_user = (await db.execute(query)).scalar_one_or_none()
    if not target_user:
        raise APIError(404, "Not Found", "User not found")
    return target_user


def _require_same_org(
    target_user: User,
    *,
    admin_org_id: uuid.UUID,
) -> None:
    if target_user.org_id != admin_org_id:
        raise APIError(403, "Forbidden", "Cannot modify users outside your organisation")


def _parse_user_role(role: str) -> UserRole:
    try:
        return UserRole(role)
    except ValueError as exc:
        raise APIError(400, "Bad Request", f"Invalid role: {role}") from exc


async def _guard_last_admin_demotion(
    db: AsyncSession,
    *,
    target_user: User,
    admin_org_id: uuid.UUID,
    new_role: UserRole,
    for_update: bool,
    require_synchronized_authority: bool = False,
) -> None:
    if target_user.role != UserRole.ADMIN or new_role == UserRole.ADMIN:
        return
    query = select(User.id).where(
        User.org_id == admin_org_id,
        User.role == UserRole.ADMIN,
        User.membership_active.is_(True),
        User.membership_permission_denied_at.is_(None),
    )
    if require_synchronized_authority:
        query = query.where(
            User.clerk_membership_id.is_not(None),
            User.clerk_membership_role == "admin",
        )
    if for_update:
        query = query.with_for_update()
    admin_ids = (await db.execute(query)).scalars().all()
    remaining_admins = len(admin_ids) - (1 if target_user.id in admin_ids else 0)
    if remaining_admins < 1:
        raise APIError(
            409,
            "Conflict",
            "Cannot demote the last admin. Promote another user to admin first.",
        )


async def _lock_org(db: AsyncSession, *, org_id: uuid.UUID) -> Organization:
    org = (
        await db.execute(
            select(Organization)
            .where(Organization.id == org_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if org is None:
        raise APIError(404, "Not Found", "Organization not found")
    return org


async def _reserve_role_change(
    db: AsyncSession,
    *,
    target_user_id: uuid.UUID,
    admin_org_id: uuid.UUID,
    new_role: UserRole,
    operation_id: uuid.UUID,
) -> tuple[Organization, User, ClerkAdminOperation]:
    """Serialize role changes and deny stale local authority before provider I/O."""
    org = await _lock_org(db, org_id=admin_org_id)
    target_user = await _load_target_user(db, user_id=target_user_id, for_update=True)
    _require_same_org(target_user, admin_org_id=admin_org_id)
    await _guard_last_admin_demotion(
        db,
        target_user=target_user,
        admin_org_id=admin_org_id,
        new_role=new_role,
        for_update=True,
        require_synchronized_authority=True,
    )
    operation = await _load_admin_operation_by_id(
        db,
        operation_id=operation_id,
        for_update=True,
    )
    if (
        operation.org_id != admin_org_id
        or operation.operation_type != "role_update"
        or operation.target_user_id != target_user.id
        or operation.requested_role != new_role.value
        or operation.state in _ADMIN_OPERATION_TERMINAL_STATES
    ):
        raise APIError(409, "Conflict", "Role operation authority changed")
    database_now = await _database_clock(db)
    if target_user.role != new_role or target_user.membership_permission_denied_at is not None:
        if (
            target_user.membership_permission_denied_by_operation_id is not None
            and target_user.membership_permission_denied_by_operation_id != operation.id
        ):
            raise APIError(409, "Conflict", "Role operation denial ownership changed")
        if target_user.membership_permission_denied_at is None:
            target_user.membership_permission_denied_at = database_now
        target_user.membership_permission_denied_by_operation_id = operation.id
    # Always release the canonical org→principal→operation locks before Clerk I/O.
    await db.commit()
    return org, target_user, operation


def _clear_operation_owned_denial(
    target_user: User,
    *,
    operation: ClerkAdminOperation,
) -> None:
    """Clear fail-closed authority only for the operation that acquired it."""
    if target_user.membership_permission_denied_by_operation_id == operation.id:
        target_user.membership_permission_denied_at = None
        target_user.membership_permission_denied_by_operation_id = None


@dataclass(frozen=True)
class _RoleOperationSnapshot:
    org_id: uuid.UUID
    clerk_org_id: str
    target_user_id: uuid.UUID
    clerk_user_id: str
    clerk_membership_id: str
    operation_id: uuid.UUID
    requested_role: str
    denial_required: bool


@dataclass(frozen=True)
class _InviteOperationSnapshot:
    org_id: uuid.UUID
    clerk_org_id: str
    inviter_user_id: uuid.UUID
    inviter_clerk_user_id: str
    operation_id: uuid.UUID
    target_email_normalized: str
    requested_role: str


@dataclass(frozen=True)
class _InviteProviderRequest:
    snapshot: _InviteOperationSnapshot
    invitations_url: str
    memberships_url: str
    email: str
    inviter_clerk_user_id: str
    secret_key: str
    expected_metadata: dict[str, object]


class _ClerkInviteHttpClient(Protocol):
    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, int],
    ) -> httpx.Response: ...

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
    ) -> httpx.Response: ...


def _invite_operation_snapshot(
    *,
    clerk_org_id: str,
    inviter_user_id: uuid.UUID,
    inviter_clerk_user_id: str,
    operation: ClerkAdminOperation,
) -> _InviteOperationSnapshot:
    if (
        not clerk_org_id
        or not inviter_clerk_user_id
        or operation.operation_type != "invite"
        or not operation.target_email_normalized
    ):
        raise APIError(409, "Conflict", "Clerk invitation operation is not synchronized")
    return _InviteOperationSnapshot(
        org_id=operation.org_id,
        clerk_org_id=clerk_org_id,
        inviter_user_id=inviter_user_id,
        inviter_clerk_user_id=inviter_clerk_user_id,
        operation_id=operation.id,
        target_email_normalized=operation.target_email_normalized,
        requested_role=operation.requested_role,
    )


def _role_operation_snapshot(
    *,
    org: Organization,
    target_user: User,
    operation: ClerkAdminOperation,
) -> _RoleOperationSnapshot:
    if (
        not org.clerk_org_id
        or not target_user.clerk_user_id
        or not target_user.clerk_membership_id
        or operation.operation_type != "role_update"
        or operation.org_id != org.id
        or operation.target_user_id != target_user.id
    ):
        raise APIError(409, "Conflict", "Clerk role operation is not synchronized")
    return _RoleOperationSnapshot(
        org_id=org.id,
        clerk_org_id=org.clerk_org_id,
        target_user_id=target_user.id,
        clerk_user_id=target_user.clerk_user_id,
        clerk_membership_id=target_user.clerk_membership_id,
        operation_id=operation.id,
        requested_role=operation.requested_role,
        denial_required=target_user.membership_permission_denied_at is not None,
    )


async def _lock_role_operation_snapshot(
    db: AsyncSession,
    *,
    snapshot: _RoleOperationSnapshot,
    expected_states: frozenset[str],
) -> tuple[Organization, User, ClerkAdminOperation]:
    """Reacquire org→principal→operation and reject a changed authority snapshot."""
    org = await _lock_org(db, org_id=snapshot.org_id)
    target_user = await _load_target_user(
        db,
        user_id=snapshot.target_user_id,
        for_update=True,
    )
    operation = await _load_admin_operation_by_id(
        db,
        operation_id=snapshot.operation_id,
        for_update=True,
    )
    if (
        org.clerk_org_id != snapshot.clerk_org_id
        or target_user.org_id != snapshot.org_id
        or target_user.clerk_user_id != snapshot.clerk_user_id
        or target_user.clerk_membership_id != snapshot.clerk_membership_id
        or not target_user.membership_active
        or operation.org_id != snapshot.org_id
        or operation.operation_type != "role_update"
        or operation.target_user_id != snapshot.target_user_id
        or operation.requested_role != snapshot.requested_role
        or operation.state not in expected_states
    ):
        raise APIError(409, "Conflict", "Role operation authority changed")
    if snapshot.denial_required and (
        target_user.membership_permission_denied_at is None
        or target_user.membership_permission_denied_by_operation_id != operation.id
    ):
        raise APIError(409, "Conflict", "Role operation denial ownership changed")
    return org, target_user, operation


async def _transition_role_operation(
    db: AsyncSession,
    *,
    snapshot: _RoleOperationSnapshot,
    expected_states: frozenset[str],
    new_state: str,
    provider_updated_at: datetime | None = None,
) -> tuple[Organization, User, ClerkAdminOperation]:
    locked = await _lock_role_operation_snapshot(
        db,
        snapshot=snapshot,
        expected_states=expected_states,
    )
    target_user = locked[1]
    operation = locked[2]
    if provider_updated_at is not None:
        _validate_provider_authority_timestamp(
            provider_updated_at,
            database_now=await _database_clock(db),
            watermarks=(
                target_user.membership_updated_at,
                operation.provider_updated_at,
            ),
        )
    operation.state = new_state
    if provider_updated_at is not None:
        operation.provider_updated_at = max(
            operation.provider_updated_at or provider_updated_at,
            provider_updated_at,
        )
    operation.last_error_code = None
    await db.commit()
    return locked


async def _verify_role_provider_snapshot(
    db: AsyncSession,
    *,
    snapshot: _RoleOperationSnapshot,
    expected_states: frozenset[str],
    provider_updated_at: datetime,
) -> None:
    """Validate a provider read under canonical locks, then release for I/O."""
    _, target_user, operation = await _lock_role_operation_snapshot(
        db,
        snapshot=snapshot,
        expected_states=expected_states,
    )
    _validate_provider_authority_timestamp(
        provider_updated_at,
        database_now=await _database_clock(db),
        watermarks=(target_user.membership_updated_at, operation.provider_updated_at),
    )
    await db.commit()


async def _lock_invite_operation_snapshot(
    db: AsyncSession,
    *,
    snapshot: _InviteOperationSnapshot,
    expected_states: frozenset[str],
) -> tuple[Organization, User, ClerkAdminOperation]:
    org = await _lock_org(db, org_id=snapshot.org_id)
    inviter = await _load_target_user(
        db,
        user_id=snapshot.inviter_user_id,
        for_update=True,
    )
    operation = await _load_admin_operation_by_id(
        db,
        operation_id=snapshot.operation_id,
        for_update=True,
    )
    if (
        org.clerk_org_id != snapshot.clerk_org_id
        or inviter.org_id != snapshot.org_id
        or inviter.clerk_user_id != snapshot.inviter_clerk_user_id
        or not inviter.membership_active
        or inviter.membership_permission_denied_at is not None
        or inviter.clerk_membership_role != "admin"
        or inviter.role != UserRole.ADMIN
        or operation.org_id != snapshot.org_id
        or operation.operation_type != "invite"
        or operation.target_email_normalized != snapshot.target_email_normalized
        or operation.requested_role != snapshot.requested_role
        or operation.state not in expected_states
    ):
        raise APIError(409, "Conflict", "Invitation operation authority changed")
    return org, inviter, operation


async def _transition_invite_operation(
    db: AsyncSession,
    *,
    snapshot: _InviteOperationSnapshot,
    expected_states: frozenset[str],
    new_state: str,
    provider_resource_id: str | None = None,
) -> ClerkAdminOperation:
    _, _, operation = await _lock_invite_operation_snapshot(
        db,
        snapshot=snapshot,
        expected_states=expected_states,
    )
    operation.state = new_state
    if provider_resource_id is not None:
        operation.provider_resource_id = provider_resource_id
    operation.last_error_code = None
    await db.commit()
    return operation


async def _verify_invite_operation_before_provider_read(
    db: AsyncSession,
    *,
    snapshot: _InviteOperationSnapshot,
    expected_state: str,
) -> None:
    await _lock_invite_operation_snapshot(
        db,
        snapshot=snapshot,
        expected_states=frozenset({expected_state}),
    )
    await db.commit()


async def _commit_operation_audit(
    db: AsyncSession,
    *,
    write_audit_log_fn,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    action: str,
    details: dict[str, object],
) -> None:
    try:
        await write_audit_log_fn(
            db,
            org_id=org_id,
            user_id=user_id,
            action=action,
            details=details,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def _record_operation_outcome(
    db: AsyncSession,
    *,
    write_audit_log_fn,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    action: str,
    details: dict[str, object],
) -> None:
    """Best-effort terminal trace; the committed requested intent remains authoritative."""
    try:
        await _commit_operation_audit(
            db,
            write_audit_log_fn=write_audit_log_fn,
            org_id=org_id,
            user_id=user_id,
            action=action,
            details=details,
        )
    except Exception:
        logger.error(
            "admin_operation_outcome_audit_failed",
            action=action,
            operation_id=details.get("operation_id"),
            exc_info=True,
        )


def _provider_failure_action(*, prefix: str, exc: Exception) -> str:
    if isinstance(exc, APIError) and "outcome is unknown" in exc.detail.casefold():
        return f"{prefix}.outcome_unknown"
    return f"{prefix}.failed"


def _require_idempotency_key(value: str | None) -> str:
    if (
        value is None
        or not 16 <= len(value) <= 128
        or any(ord(char) < 0x21 or ord(char) > 0x7E for char in value)
    ):
        raise APIError(
            400,
            "Bad Request",
            "Idempotency-Key must contain 16 to 128 visible ASCII characters",
        )
    return value


async def update_user_role_for_admin_impl(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    admin_org_id: uuid.UUID,
    admin_id: uuid.UUID,
    body: UpdateUserRoleRequest,
    write_audit_log_fn,
    settings,
    http_client_cls,
    idempotency_key: str | None = None,
) -> None:
    """Update the role of a user within the admin's organisation."""
    idempotency_key = _require_idempotency_key(idempotency_key)
    target_user = await _load_target_user(db, user_id=user_id)
    _require_same_org(target_user, admin_org_id=admin_org_id)
    new_role = _parse_user_role(body.role)
    previous_role = target_user.role.value
    await _guard_last_admin_demotion(
        db,
        target_user=target_user,
        admin_org_id=admin_org_id,
        new_role=new_role,
        for_update=False,
        require_synchronized_authority=settings.app_env == "prod",
    )

    durable_operation, _created = await _claim_admin_operation(
        db,
        settings=settings,
        org_id=admin_org_id,
        admin_id=admin_id,
        operation_type="role_update",
        idempotency_key=idempotency_key,
        request_payload={
            "operation_type": "role_update",
            "target_user_id": str(target_user.id),
            "requested_role": new_role.value,
        },
        target_user_id=target_user.id,
        target_email_normalized=None,
        requested_role=new_role.value,
        write_audit_log_fn=write_audit_log_fn,
        requested_action="admin.user_role.update_requested",
        requested_details={
            "target_user_id": str(target_user.id),
            "previous_role": target_user.role.value,
            "requested_role": new_role.value,
        },
    )
    operation_id = str(durable_operation.id)
    durable_operation_id = durable_operation.id
    if durable_operation.state == "completed":
        return
    if durable_operation.state == "failed":
        _raise_failed_operation()
    if settings.app_env == "prod":
        provider_accepted = False
        try:
            org = (
                await db.execute(select(Organization).where(Organization.id == admin_org_id))
            ).scalar_one_or_none()
            if org is None:
                raise APIError(404, "Not Found", "Organization not found")
            _require_clerk_role_update_ready(
                target_user=target_user,
                org=org,
                settings=settings,
            )
            # Reacquire and recheck the last-admin invariant, persist the
            # operation-owned denial snapshot, then release every row lock
            # before the first Clerk call.
            org, target_user, reserved_operation = await _reserve_role_change(
                db,
                target_user_id=user_id,
                admin_org_id=admin_org_id,
                new_role=new_role,
                operation_id=durable_operation_id,
            )
            durable_operation = reserved_operation
            _require_clerk_role_update_ready(
                target_user=target_user,
                org=org,
                settings=settings,
            )
            role_snapshot = _role_operation_snapshot(
                org=org,
                target_user=target_user,
                operation=durable_operation,
            )
            await _update_user_role_in_clerk(
                target_user=target_user,
                org=org,
                new_role=new_role,
                settings=settings,
                http_client_cls=http_client_cls,
                db=db,
                operation=durable_operation,
            )
            provider_accepted = durable_operation.state in {
                "metadata_accepted",
                "role_accepted",
            }
            # Step commits intentionally release the external-call boundary.
            # Reacquire the canonical org→target→operation lock order before
            # converging local authority from the accepted provider state.
            org, target_user, durable_operation = await _lock_role_operation_snapshot(
                db,
                snapshot=role_snapshot,
                expected_states=frozenset({"metadata_accepted", "role_accepted"}),
            )
            if durable_operation.id != durable_operation_id:
                raise APIError(
                    409,
                    "Conflict",
                    "Role operation authority changed",
                )
            await _guard_last_admin_demotion(
                db,
                target_user=target_user,
                admin_org_id=admin_org_id,
                new_role=new_role,
                for_update=True,
                require_synchronized_authority=True,
            )
            target_user.clerk_membership_role = "admin" if new_role == UserRole.ADMIN else "member"
            if durable_operation.provider_updated_at is not None:
                target_user.membership_updated_at = max(
                    target_user.membership_updated_at,
                    durable_operation.provider_updated_at,
                )
            target_user.role = new_role
            _clear_operation_owned_denial(
                target_user,
                operation=durable_operation,
            )
            durable_operation.state = "completed"
            await write_audit_log_fn(
                db,
                org_id=admin_org_id,
                user_id=admin_id,
                action="admin.user_role.updated",
                details={
                    "operation_id": operation_id,
                    "target_user_id": str(target_user.id),
                    "previous_role": (previous_role),
                    "new_role": target_user.role.value,
                    "provider_accepted": provider_accepted,
                    "provider_updated_at": (
                        durable_operation.provider_updated_at.isoformat()
                        if durable_operation.provider_updated_at is not None
                        else None
                    ),
                },
                fail_closed=True,
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            await _lock_org(db, org_id=admin_org_id)
            target_user = await _load_target_user(db, user_id=user_id, for_update=True)
            durable_operation = await _load_admin_operation_by_id(
                db,
                operation_id=durable_operation_id,
                for_update=True,
            )
            if _can_terminally_fail_without_reconciliation(
                durable_operation, exc
            ) or _is_partial_metadata_role_rejection(durable_operation, exc):
                partial_metadata_accepted = _terminalize_role_failure(
                    target_user,
                    operation=durable_operation,
                    exc=exc,
                    denied_at=await _database_clock(db),
                )
                await write_audit_log_fn(
                    db,
                    org_id=admin_org_id,
                    user_id=admin_id,
                    action="admin.user_role.update.failed",
                    details={
                        "operation_id": operation_id,
                        "target_user_id": str(user_id),
                        "requested_role": new_role.value,
                        "provider_accepted": partial_metadata_accepted,
                        "partial_metadata_accepted": partial_metadata_accepted,
                        "authority_denied_pending_convergence": partial_metadata_accepted,
                        "terminal_reason": durable_operation.last_error_code,
                        "terminal": True,
                        "error_type": type(exc).__name__,
                    },
                    fail_closed=True,
                )
                await db.commit()
                if isinstance(exc, APIError):
                    exc.type_uri = _ADMIN_OPERATION_TERMINAL_FAILURE_TYPE
                raise
            provider_accepted = durable_operation.state in {
                "metadata_accepted",
                "role_accepted",
                "completed",
            }
            action = (
                "admin.user_role.update_reconciliation_required"
                if provider_accepted
                else (
                    "admin.user_role.update.outcome_unknown"
                    if durable_operation.state not in {"requested", "failed"}
                    else _provider_failure_action(prefix="admin.user_role.update", exc=exc)
                )
            )
            await _record_operation_outcome(
                db,
                write_audit_log_fn=write_audit_log_fn,
                org_id=admin_org_id,
                user_id=admin_id,
                action=action,
                details={
                    "operation_id": operation_id,
                    "target_user_id": str(user_id),
                    "requested_role": new_role.value,
                    "provider_accepted": provider_accepted,
                    "error_type": type(exc).__name__,
                },
            )
            raise
    else:
        try:
            target_user.role = new_role
            durable_operation.state = "completed"
            await write_audit_log_fn(
                db,
                org_id=admin_org_id,
                user_id=admin_id,
                action="admin.user_role.updated",
                details={
                    "operation_id": operation_id,
                    "target_user_id": str(target_user.id),
                    "previous_role": previous_role,
                    "new_role": target_user.role.value,
                },
                fail_closed=True,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    logger.info(
        "admin_role_changed",
        target_user_id=str(user_id),
        new_role=body.role,
        admin_id=str(admin_id),
    )


# ---------------------------------------------------------------------------
# User invites  (formerly admin_user_invites)
# ---------------------------------------------------------------------------


def _require_invitable_role(role: str) -> None:
    if role == "admin":
        raise APIError(403, "Forbidden", "Cannot create admin users via invite")


def _praviar_role_metadata(role: UserRole | str) -> dict[str, object]:
    role_value = role.value if isinstance(role, UserRole) else role
    try:
        parsed_role = UserRole(role_value)
    except ValueError as exc:
        raise APIError(400, "Bad Request", "Invalid Praviar invitation role") from exc
    if parsed_role not in NON_ADMIN_INVITE_ROLES:
        raise APIError(403, "Forbidden", "Cannot assign admin through member metadata")
    return {
        "praviar_role_version": PRAVIAR_ROLE_METADATA_VERSION,
        "praviar_role": parsed_role.value,
    }


def _clerk_headers(*, secret_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {secret_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Clerk-API-Version": CLERK_API_VERSION,
    }


def _require_clerk_json(response: httpx.Response, *, operation: str) -> dict:
    if response.status_code not in (200, 201):
        raise APIError(502, "Bad Gateway", f"Clerk returned {response.status_code}")
    try:
        data = response.json()
    except ValueError as exc:
        raise APIError(502, "Bad Gateway", f"Clerk returned invalid {operation} data") from exc
    if not isinstance(data, dict):
        raise APIError(502, "Bad Gateway", f"Clerk returned invalid {operation} data")
    return data


def _raise_if_known_clerk_rejection(response: httpx.Response) -> None:
    if (
        400 <= response.status_code < 500
        and response.status_code not in _CLERK_RETRYABLE_STATUS_CODES
    ):
        raise _KnownClerkRejectionError(response.status_code)


def _validate_invitation_response(
    response: httpx.Response,
    *,
    clerk_org_id: str,
    email: str,
    public_metadata: dict[str, object],
) -> None:
    data = _require_clerk_json(response, operation="organization invitation")
    if (
        not isinstance(data.get("id"), str)
        or not data["id"].strip()
        or str(data.get("organization_id") or "") != clerk_org_id
        or str(data.get("email_address") or "").casefold() != email.casefold()
        or data.get("role") != "org:member"
        or data.get("status") not in {"pending", "accepted"}
        or not _governed_metadata_matches(data.get("public_metadata"), public_metadata)
    ):
        raise APIError(502, "Bad Gateway", "Clerk returned mismatched invitation data")


def _membership_response_identity(
    data: dict,
) -> tuple[str, str, str, str, dict, datetime]:
    organization = data.get("organization")
    public_user = data.get("public_user_data")
    metadata = data.get("public_metadata")
    if (
        not isinstance(organization, dict)
        or not isinstance(public_user, dict)
        or not isinstance(metadata, dict)
    ):
        raise APIError(502, "Bad Gateway", "Clerk returned invalid membership data")
    updated_at = data.get("updated_at")
    if isinstance(updated_at, bool) or not isinstance(updated_at, int) or updated_at <= 0:
        raise APIError(502, "Bad Gateway", "Clerk returned invalid membership data")
    try:
        updated_at_datetime = datetime.fromtimestamp(updated_at / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise APIError(502, "Bad Gateway", "Clerk returned invalid membership data") from exc
    return (
        str(data.get("id") or ""),
        str(organization.get("id") or ""),
        str(public_user.get("user_id") or ""),
        str(data.get("role") or ""),
        metadata,
        updated_at_datetime,
    )


def _validate_membership_response(
    response: httpx.Response,
    *,
    target_user: User,
    clerk_org_id: str,
    expected_clerk_role: str,
    expected_metadata: dict[str, object] | None,
) -> datetime:
    data = _require_clerk_json(response, operation="membership")
    membership_id, response_org_id, response_user_id, role, metadata, updated_at = (
        _membership_response_identity(data)
    )
    if (
        membership_id != target_user.clerk_membership_id
        or response_org_id != clerk_org_id
        or response_user_id != target_user.clerk_user_id
        or role != expected_clerk_role
        or (
            expected_metadata is not None
            and not _governed_metadata_matches(metadata, expected_metadata)
        )
    ):
        raise APIError(502, "Bad Gateway", "Clerk returned mismatched membership data")
    return updated_at


def _governed_metadata_matches(actual: object, expected: dict[str, object]) -> bool:
    """Compare only Praviar-governed keys while preserving provider-owned data."""
    return isinstance(actual, dict) and all(
        actual.get(key) == value for key, value in expected.items()
    )


def _require_clerk_role_update_ready(
    *,
    target_user: User,
    org: Organization,
    settings,
) -> None:
    secret_key = str(getattr(settings, "clerk_secret_key", "") or "").strip()
    if not secret_key:
        raise APIError(503, "Service Unavailable", "Clerk membership updates are not configured")
    if (
        not target_user.membership_active
        or not target_user.clerk_membership_id
        or target_user.clerk_membership_role not in {"admin", "member"}
        or not org.clerk_org_id
    ):
        raise APIError(409, "Conflict", "Clerk membership is not synchronized")
    if target_user.clerk_membership_role == "admin" and target_user.role != UserRole.ADMIN:
        raise APIError(409, "Conflict", "Clerk membership authority is inconsistent")
    if (
        target_user.clerk_membership_role == "member"
        and target_user.role not in NON_ADMIN_INVITE_ROLES
    ):
        raise APIError(409, "Conflict", "Clerk membership authority is inconsistent")


async def _update_user_role_in_clerk(
    *,
    target_user: User,
    org: Organization,
    new_role: UserRole,
    settings,
    http_client_cls,
    db: AsyncSession,
    operation: ClerkAdminOperation,
) -> None:
    _require_clerk_role_update_ready(
        target_user=target_user,
        org=org,
        settings=settings,
    )
    snapshot = _role_operation_snapshot(
        org=org,
        target_user=target_user,
        operation=operation,
    )
    secret_key = str(settings.clerk_secret_key).strip()
    desired_clerk_role = "org:admin" if new_role == UserRole.ADMIN else "org:member"
    membership_url = (
        "https://api.clerk.com/v1/organizations/"
        f"{quote(snapshot.clerk_org_id, safe='')}/memberships/"
        f"{quote(snapshot.clerk_user_id, safe='')}"
    )
    metadata_url = f"{membership_url}/metadata"
    # Clerk does not document mutation idempotency. The locally persisted call
    # boundary is the sole mutation guard, so no provider key or retry is used.
    headers = _clerk_headers(secret_key=secret_key)
    metadata = None if new_role == UserRole.ADMIN else _praviar_role_metadata(new_role)

    from api.circuit_breaker import CircuitOpenError, clerk_breaker

    current_state = operation.state
    # The caller may have arrived with canonical locks (especially explicit
    # reconciliation). Release them before the first provider read.
    await db.commit()

    async def _call_clerk() -> None:
        nonlocal current_state
        async with http_client_cls(timeout=httpx.Timeout(10.0, connect=5.0)) as client:

            async def _current_membership() -> tuple[dict, datetime]:
                response = await client.get(membership_url, headers=headers)
                data = _require_clerk_json(response, operation="membership")
                updated_at = _validate_membership_response(
                    response,
                    target_user=target_user,
                    clerk_org_id=snapshot.clerk_org_id,
                    expected_clerk_role=str(data.get("role") or ""),
                    expected_metadata=None,
                )
                return data, updated_at

            # For demotion, persist the least-privilege app role metadata before
            # dropping coarse Clerk admin authority. A partial failure leaves
            # local admin unchanged and auth reconciliation fails closed.
            if metadata is not None and current_state in {
                "requested",
                "metadata_call_started",
            }:
                may_mutate = current_state == "requested"
                if current_state == "requested":
                    await _transition_role_operation(
                        db,
                        snapshot=snapshot,
                        expected_states=frozenset({"requested"}),
                        new_state="metadata_call_started",
                    )
                    operation.state = "metadata_call_started"
                    current_state = "metadata_call_started"
                current_data, current_updated_at = await _current_membership()
                await _verify_role_provider_snapshot(
                    db,
                    snapshot=snapshot,
                    expected_states=frozenset({"metadata_call_started"}),
                    provider_updated_at=current_updated_at,
                )
                if _governed_metadata_matches(current_data.get("public_metadata"), metadata):
                    await _transition_role_operation(
                        db,
                        snapshot=snapshot,
                        expected_states=frozenset({"metadata_call_started"}),
                        new_state="metadata_accepted",
                        provider_updated_at=current_updated_at,
                    )
                    operation.state = "metadata_accepted"
                    operation.provider_updated_at = current_updated_at
                    current_state = "metadata_accepted"
                elif not may_mutate:
                    raise APIError(
                        503,
                        "Service Unavailable",
                        "Clerk membership update outcome is unknown",
                    )
                else:
                    existing_metadata = current_data.get("public_metadata")
                    merged_metadata = (
                        dict(existing_metadata) if isinstance(existing_metadata, dict) else {}
                    )
                    merged_metadata.update(metadata)
                    metadata_response = await client.patch(
                        metadata_url,
                        headers=headers,
                        json={"public_metadata": merged_metadata},
                    )
                    if metadata_response.status_code in _CLERK_RETRYABLE_STATUS_CODES:
                        raise APIError(
                            503,
                            "Service Unavailable",
                            "Clerk membership update outcome is unknown",
                        )
                    _raise_if_known_clerk_rejection(metadata_response)
                    metadata_updated_at = _validate_membership_response(
                        metadata_response,
                        target_user=target_user,
                        clerk_org_id=snapshot.clerk_org_id,
                        expected_clerk_role=f"org:{target_user.clerk_membership_role}",
                        expected_metadata=metadata,
                    )
                    await _transition_role_operation(
                        db,
                        snapshot=snapshot,
                        expected_states=frozenset({"metadata_call_started"}),
                        new_state="metadata_accepted",
                        provider_updated_at=metadata_updated_at,
                    )
                    operation.state = "metadata_accepted"
                    operation.provider_updated_at = metadata_updated_at
                    current_state = "metadata_accepted"

            if (
                target_user.clerk_membership_role != desired_clerk_role.removeprefix("org:")
                and current_state != "role_accepted"
            ):
                starting_state = "metadata_accepted" if metadata is not None else "requested"
                may_mutate = current_state == starting_state
                if may_mutate:
                    await _transition_role_operation(
                        db,
                        snapshot=snapshot,
                        expected_states=frozenset({starting_state}),
                        new_state="role_call_started",
                    )
                    operation.state = "role_call_started"
                    current_state = "role_call_started"
                current_data, current_updated_at = await _current_membership()
                await _verify_role_provider_snapshot(
                    db,
                    snapshot=snapshot,
                    expected_states=frozenset({"role_call_started"}),
                    provider_updated_at=current_updated_at,
                )
                desired_metadata_matches = metadata is None or _governed_metadata_matches(
                    current_data.get("public_metadata"), metadata
                )
                if current_data.get("role") == desired_clerk_role and desired_metadata_matches:
                    await _transition_role_operation(
                        db,
                        snapshot=snapshot,
                        expected_states=frozenset({"role_call_started"}),
                        new_state="role_accepted",
                        provider_updated_at=current_updated_at,
                    )
                    operation.state = "role_accepted"
                    operation.provider_updated_at = current_updated_at
                    current_state = "role_accepted"
                    return
                if not may_mutate:
                    raise APIError(
                        503,
                        "Service Unavailable",
                        "Clerk membership update outcome is unknown",
                    )
                role_response = await client.patch(
                    membership_url,
                    headers=headers,
                    json={"role": desired_clerk_role},
                )
                if role_response.status_code in _CLERK_RETRYABLE_STATUS_CODES:
                    raise APIError(
                        503,
                        "Service Unavailable",
                        "Clerk membership update outcome is unknown",
                    )
                _raise_if_known_clerk_rejection(role_response)
                role_updated_at = _validate_membership_response(
                    role_response,
                    target_user=target_user,
                    clerk_org_id=snapshot.clerk_org_id,
                    expected_clerk_role=desired_clerk_role,
                    expected_metadata=metadata,
                )
                await _transition_role_operation(
                    db,
                    snapshot=snapshot,
                    expected_states=frozenset({"role_call_started"}),
                    new_state="role_accepted",
                    provider_updated_at=role_updated_at,
                )
                operation.state = "role_accepted"
                operation.provider_updated_at = role_updated_at
                current_state = "role_accepted"
            elif current_state not in {
                "metadata_accepted",
                "role_accepted",
            }:
                accepted_state = "role_accepted" if metadata is None else "metadata_accepted"
                await _transition_role_operation(
                    db,
                    snapshot=snapshot,
                    expected_states=frozenset({current_state}),
                    new_state=accepted_state,
                )
                operation.state = accepted_state
                current_state = accepted_state

    try:
        await clerk_breaker.call(_call_clerk)
    except CircuitOpenError as exc:
        raise APIError(503, "Service Unavailable", "Clerk is temporarily unavailable") from exc
    except httpx.RequestError as exc:
        raise APIError(
            503,
            "Service Unavailable",
            "Clerk membership update outcome is unknown",
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise APIError(502, "Bad Gateway", f"Clerk returned {exc.response.status_code}") from exc

    # Local authority is converged only by the caller after reacquiring the
    # same canonical snapshot and writing its audit event atomically.


def _validate_invite_operation_request(
    *,
    body: InviteRequest,
    clerk_org_id: str,
    inviter_clerk_user_id: str,
    inviter_user_id: uuid.UUID | None,
    settings,
    operation: ClerkAdminOperation,
) -> _InviteOperationSnapshot:
    if not settings.clerk_secret_key:
        raise APIError(
            503,
            "Service Unavailable",
            "Clerk is not configured for production invites",
        )
    snapshot = _invite_operation_snapshot(
        clerk_org_id=clerk_org_id,
        inviter_user_id=inviter_user_id or operation.initiated_by,
        inviter_clerk_user_id=inviter_clerk_user_id,
        operation=operation,
    )
    if (
        body.email.strip().casefold() != snapshot.target_email_normalized
        or body.role != snapshot.requested_role
    ):
        raise APIError(409, "Conflict", "Invitation operation request changed")
    return snapshot


def _build_invite_provider_request(
    *,
    body: InviteRequest,
    snapshot: _InviteOperationSnapshot,
    secret_key: str,
    operation: ClerkAdminOperation,
) -> _InviteProviderRequest:
    expected_metadata = _praviar_role_metadata(body.role)
    expected_metadata[PRAVIAR_INVITATION_OPERATION_KEY] = str(operation.id)
    escaped_org_id = quote(snapshot.clerk_org_id, safe="")
    return _InviteProviderRequest(
        snapshot=snapshot,
        invitations_url=(f"https://api.clerk.com/v1/organizations/{escaped_org_id}/invitations"),
        memberships_url=(f"https://api.clerk.com/v1/organizations/{escaped_org_id}/memberships"),
        email=body.email,
        inviter_clerk_user_id=snapshot.inviter_clerk_user_id,
        secret_key=secret_key,
        expected_metadata=expected_metadata,
    )


def _parse_clerk_collection_page(
    response: httpx.Response,
) -> tuple[list[Any], object]:
    if response.status_code != 200:
        raise APIError(
            503,
            "Service Unavailable",
            "Clerk invitation outcome is unknown",
        )
    try:
        payload = response.json()
        rows = payload.get("data")
        total_count = payload.get("total_count")
    except (AttributeError, ValueError) as exc:
        raise APIError(
            503,
            "Service Unavailable",
            "Clerk invitation outcome is unknown",
        ) from exc
    if not isinstance(rows, list):
        raise APIError(
            503,
            "Service Unavailable",
            "Clerk invitation outcome is unknown",
        )
    return rows, total_count


def _is_matching_clerk_invitation(
    row: object,
    *,
    request: _InviteProviderRequest,
) -> TypeGuard[dict[str, Any]]:
    return (
        isinstance(row, dict)
        and str(row.get("organization_id") or "") == request.snapshot.clerk_org_id
        and str(row.get("email_address") or "").casefold() == request.email.casefold()
        and row.get("role") == "org:member"
        and _governed_metadata_matches(
            row.get("public_metadata"),
            request.expected_metadata,
        )
    )


def _is_matching_clerk_membership(
    row: object,
    *,
    request: _InviteProviderRequest,
) -> TypeGuard[dict[str, Any]]:
    if not isinstance(row, dict):
        return False
    organization = row.get("organization")
    public_user = row.get("public_user_data")
    organization_id = organization.get("id") if isinstance(organization, dict) else ""
    identifier = public_user.get("identifier") if isinstance(public_user, dict) else ""
    return (
        str(organization_id or "") == request.snapshot.clerk_org_id
        and str(identifier or "").casefold() == request.email.casefold()
        and row.get("role") == "org:member"
        and _governed_metadata_matches(
            row.get("public_metadata"),
            request.expected_metadata,
        )
    )


async def _find_clerk_collection_matches(
    client: _ClerkInviteHttpClient,
    *,
    url: str,
    headers: dict[str, str],
    matches: Callable[[object], bool],
) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = await client.get(
            url,
            headers=headers,
            params={"limit": 100, "offset": offset},
        )
        rows, total_count = _parse_clerk_collection_page(response)
        found.extend(cast(dict[str, Any], row) for row in rows if matches(row))
        offset += len(rows)
        if not rows or (isinstance(total_count, int) and offset >= total_count) or len(rows) < 100:
            return found


def _normalize_reconciled_invitation(
    match: dict[str, Any],
    *,
    request: _InviteProviderRequest,
) -> httpx.Response:
    if "organization_id" in match:
        return httpx.Response(200, json=match)
    # Clerk may remove an accepted invitation from invitation listings. Keep
    # the accepted membership identity while normalizing the validation shape.
    return httpx.Response(
        200,
        json={
            "id": str(match.get("id") or ""),
            "organization_id": request.snapshot.clerk_org_id,
            "email_address": request.email,
            "role": "org:member",
            "status": "pending",
            "public_metadata": match.get("public_metadata"),
        },
    )


async def _reconcile_started_clerk_invite(
    client: _ClerkInviteHttpClient,
    *,
    db: AsyncSession,
    request: _InviteProviderRequest,
) -> httpx.Response:
    await _verify_invite_operation_before_provider_read(
        db,
        snapshot=request.snapshot,
        expected_state="invite_call_started",
    )
    headers = _clerk_headers(secret_key=request.secret_key)
    matches = await _find_clerk_collection_matches(
        client,
        url=request.invitations_url,
        headers=headers,
        matches=partial(_is_matching_clerk_invitation, request=request),
    )
    if not matches:
        matches = await _find_clerk_collection_matches(
            client,
            url=request.memberships_url,
            headers=headers,
            matches=partial(_is_matching_clerk_membership, request=request),
        )
    if len(matches) != 1:
        raise APIError(
            503,
            "Service Unavailable",
            "Clerk invitation outcome is unknown",
        )
    return _normalize_reconciled_invitation(matches[0], request=request)


async def _submit_clerk_invite(
    client: _ClerkInviteHttpClient,
    *,
    db: AsyncSession,
    request: _InviteProviderRequest,
    operation: ClerkAdminOperation,
) -> httpx.Response:
    await _transition_invite_operation(
        db,
        snapshot=request.snapshot,
        expected_states=frozenset({"requested"}),
        new_state="invite_call_started",
    )
    operation.state = "invite_call_started"
    response = await client.post(
        request.invitations_url,
        headers=_clerk_headers(secret_key=request.secret_key),
        json={
            "inviter_user_id": request.inviter_clerk_user_id,
            "email_address": request.email,
            "role": "org:member",
            "public_metadata": request.expected_metadata,
        },
    )
    if response.status_code in _CLERK_RETRYABLE_STATUS_CODES:
        raise APIError(
            503,
            "Service Unavailable",
            "Clerk invitation outcome is unknown",
        )
    return response


async def _call_clerk_invite_provider(
    *,
    initial_state: str,
    request: _InviteProviderRequest,
    http_client_cls,
    db: AsyncSession,
    operation: ClerkAdminOperation,
) -> httpx.Response:
    async with http_client_cls(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
        if initial_state == "invite_call_started":
            return await _reconcile_started_clerk_invite(
                client,
                db=db,
                request=request,
            )
        return await _submit_clerk_invite(
            client,
            db=db,
            request=request,
            operation=operation,
        )


async def _accept_clerk_invitation_response(
    response: httpx.Response,
    *,
    db: AsyncSession,
    request: _InviteProviderRequest,
    operation: ClerkAdminOperation,
) -> str:
    if response.status_code not in (200, 201):
        _raise_if_known_clerk_rejection(response)
        raise APIError(502, "Bad Gateway", f"Clerk returned {response.status_code}")
    _validate_invitation_response(
        response,
        clerk_org_id=request.snapshot.clerk_org_id,
        email=request.email,
        public_metadata=request.expected_metadata,
    )
    invitation_id = str(response.json()["id"])
    await _transition_invite_operation(
        db,
        snapshot=request.snapshot,
        expected_states=frozenset({"invite_call_started"}),
        new_state="provider_accepted",
        provider_resource_id=invitation_id,
    )
    operation.state = "provider_accepted"
    operation.provider_resource_id = invitation_id
    return invitation_id


async def _invite_user_in_prod(
    *,
    body: InviteRequest,
    clerk_org_id: str,
    inviter_clerk_user_id: str,
    inviter_user_id: uuid.UUID | None = None,
    settings,
    http_client_cls,
    db: AsyncSession,
    operation: ClerkAdminOperation,
) -> str:
    snapshot = _validate_invite_operation_request(
        body=body,
        clerk_org_id=clerk_org_id,
        inviter_clerk_user_id=inviter_clerk_user_id,
        inviter_user_id=inviter_user_id,
        settings=settings,
        operation=operation,
    )
    initial_state = operation.state
    # Explicit reconciliation enters with operation/authority locks. No Clerk
    # read or mutation may execute until they are released.
    await db.commit()

    from api.circuit_breaker import CircuitOpenError, clerk_breaker

    request = _build_invite_provider_request(
        body=body,
        snapshot=snapshot,
        secret_key=settings.clerk_secret_key,
        operation=operation,
    )
    try:
        response = cast(
            httpx.Response,
            await clerk_breaker.call(
                partial(
                    _call_clerk_invite_provider,
                    initial_state=initial_state,
                    request=request,
                    http_client_cls=http_client_cls,
                    db=db,
                    operation=operation,
                )
            ),
        )
    except CircuitOpenError as exc:
        raise APIError(503, "Service Unavailable", "Clerk is temporarily unavailable") from exc
    except httpx.RequestError as exc:
        raise APIError(
            503,
            "Service Unavailable",
            "Clerk invitation outcome is unknown",
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise APIError(502, "Bad Gateway", f"Clerk returned {exc.response.status_code}") from exc
    return await _accept_clerk_invitation_response(
        response,
        db=db,
        request=request,
        operation=operation,
    )


async def _invite_user_in_dev(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    body: InviteRequest,
) -> None:
    try:
        role = UserRole(body.role)
    except ValueError as exc:
        raise APIError(422, "Unprocessable Entity", f"Invalid role: {body.role!r}") from exc

    existing = await db.execute(select(User).where(User.org_id == org_id, User.email == body.email))
    if existing.scalar_one_or_none():
        raise APIError(409, "Conflict", "User with this email already exists")

    db.add(
        User(
            clerk_user_id=f"dev_{body.email}",
            org_id=org_id,
            email=body.email,
            role=role,
        )
    )


async def _load_clerk_invite_authority(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    admin_id: uuid.UUID,
    for_update: bool,
) -> tuple[Organization, User]:
    org: Organization | None
    if for_update:
        org = await _lock_org(db, org_id=org_id)
    else:
        org = (
            await db.execute(select(Organization).where(Organization.id == org_id))
        ).scalar_one_or_none()
    inviter_query = select(User).where(
        User.id == admin_id,
        User.org_id == org_id,
        User.membership_active.is_(True),
        User.membership_permission_denied_at.is_(None),
        User.clerk_membership_role == "admin",
        User.role == UserRole.ADMIN,
    )
    if for_update:
        inviter_query = inviter_query.with_for_update().execution_options(populate_existing=True)
    inviter = (await db.execute(inviter_query)).scalar_one_or_none()
    if org is None or not org.clerk_org_id:
        raise APIError(409, "Conflict", "Clerk organization is not synchronized")
    if inviter is None or not inviter.clerk_user_id:
        raise APIError(409, "Conflict", "Clerk admin membership is not synchronized")
    return org, inviter


async def invite_user_to_org_impl(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    admin_id: uuid.UUID,
    body: InviteRequest,
    settings,
    http_client_cls,
    write_audit_log_fn,
    idempotency_key: str | None = None,
) -> None:
    """Invite a user to an organisation, routing to Clerk or local dev creation."""
    _require_invitable_role(body.role)
    idempotency_key = _require_idempotency_key(idempotency_key)
    normalized_email = body.email.strip().casefold()
    durable_operation, _created = await _claim_admin_operation(
        db,
        settings=settings,
        org_id=org_id,
        admin_id=admin_id,
        operation_type="invite",
        idempotency_key=idempotency_key,
        request_payload={
            "operation_type": "invite",
            "email": normalized_email,
            "requested_role": body.role,
        },
        target_user_id=None,
        target_email_normalized=normalized_email,
        requested_role=body.role,
        write_audit_log_fn=write_audit_log_fn,
        requested_action="admin.user_invite.requested",
        requested_details={
            "email": normalized_email,
            "requested_role": body.role,
        },
    )
    operation_id = str(durable_operation.id)
    durable_operation_id = durable_operation.id
    if durable_operation.state == "completed":
        return
    if durable_operation.state == "failed":
        _raise_failed_operation()

    if settings.app_env == "prod":
        provider_accepted = False
        try:
            if not str(getattr(settings, "clerk_secret_key", "") or "").strip():
                raise APIError(
                    503,
                    "Service Unavailable",
                    "Clerk is not configured for production invites",
                )
            await _load_clerk_invite_authority(
                db,
                org_id=org_id,
                admin_id=admin_id,
                for_update=False,
            )
            org, inviter = await _load_clerk_invite_authority(
                db,
                org_id=org_id,
                admin_id=admin_id,
                for_update=True,
            )
            invite_snapshot = _invite_operation_snapshot(
                clerk_org_id=org.clerk_org_id,
                inviter_user_id=inviter.id,
                inviter_clerk_user_id=inviter.clerk_user_id,
                operation=durable_operation,
            )
            if durable_operation.state == "provider_accepted":
                if not durable_operation.provider_resource_id:
                    raise APIError(
                        503,
                        "Service Unavailable",
                        "Clerk invitation outcome is unknown",
                    )
                invitation_id = durable_operation.provider_resource_id
            else:
                invitation_id = await _invite_user_in_prod(
                    body=body,
                    clerk_org_id=org.clerk_org_id,
                    inviter_user_id=inviter.id,
                    inviter_clerk_user_id=inviter.clerk_user_id,
                    settings=settings,
                    http_client_cls=http_client_cls,
                    db=db,
                    operation=durable_operation,
                )
            _, _, durable_operation = await _lock_invite_operation_snapshot(
                db,
                snapshot=invite_snapshot,
                expected_states=frozenset({"provider_accepted"}),
            )
            provider_accepted = True
            durable_operation.state = "completed"
            await write_audit_log_fn(
                db,
                org_id=org_id,
                user_id=admin_id,
                action="admin.user_invited",
                details={
                    "operation_id": operation_id,
                    "email": body.email,
                    "role": body.role,
                    "environment": settings.app_env,
                    "provider_invitation_id": invitation_id,
                    "provider_accepted": provider_accepted,
                },
                fail_closed=True,
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            await _lock_org(db, org_id=org_id)
            durable_operation = await _load_admin_operation_by_id(
                db,
                operation_id=durable_operation_id,
                for_update=True,
            )
            if _can_terminally_fail_without_reconciliation(durable_operation, exc):
                durable_operation.state = "failed"
                durable_operation.last_error_code = (
                    f"clerk_{exc.provider_status_code}"
                    if isinstance(exc, _KnownClerkRejectionError)
                    else type(exc).__name__
                )[:64]
                await write_audit_log_fn(
                    db,
                    org_id=org_id,
                    user_id=admin_id,
                    action="admin.user_invite.failed",
                    details={
                        "operation_id": operation_id,
                        "email": body.email,
                        "requested_role": body.role,
                        "provider_accepted": False,
                        "terminal": True,
                        "error_type": type(exc).__name__,
                    },
                    fail_closed=True,
                )
                await db.commit()
                if isinstance(exc, APIError):
                    exc.type_uri = _ADMIN_OPERATION_TERMINAL_FAILURE_TYPE
                raise
            provider_accepted = durable_operation.state in {
                "provider_accepted",
                "completed",
            }
            action = (
                "admin.user_invite.reconciliation_required"
                if provider_accepted
                else (
                    "admin.user_invite.outcome_unknown"
                    if durable_operation.state not in {"requested", "failed"}
                    else _provider_failure_action(prefix="admin.user_invite", exc=exc)
                )
            )
            await _record_operation_outcome(
                db,
                write_audit_log_fn=write_audit_log_fn,
                org_id=org_id,
                user_id=admin_id,
                action=action,
                details={
                    "operation_id": operation_id,
                    "email": body.email,
                    "requested_role": body.role,
                    "provider_accepted": provider_accepted,
                    "error_type": type(exc).__name__,
                },
            )
            raise
    else:
        try:
            await _invite_user_in_dev(
                db,
                org_id=org_id,
                body=body,
            )
            durable_operation.state = "completed"
            await write_audit_log_fn(
                db,
                org_id=org_id,
                user_id=admin_id,
                action="admin.user_invited",
                details={
                    "operation_id": operation_id,
                    "email": body.email,
                    "role": body.role,
                    "environment": settings.app_env,
                },
                fail_closed=True,
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            if not isinstance(exc, APIError):
                raise
            await _lock_org(db, org_id=org_id)
            durable_operation = await _load_admin_operation_by_id(
                db,
                operation_id=durable_operation_id,
                for_update=True,
            )
            durable_operation.state = "failed"
            durable_operation.last_error_code = type(exc).__name__[:64]
            await write_audit_log_fn(
                db,
                org_id=org_id,
                user_id=admin_id,
                action="admin.user_invite.failed",
                details={
                    "operation_id": operation_id,
                    "email": body.email,
                    "requested_role": body.role,
                    "terminal": True,
                    "error_type": type(exc).__name__,
                },
                fail_closed=True,
            )
            await db.commit()
            raise
    email_digest = _privacy_email_digest(settings=settings, org_id=org_id, email=body.email)
    logger.info(
        "admin_invite_sent",
        org_id=str(org_id),
        operation_id=operation_id,
        email_digest=email_digest,
        role=body.role,
        admin_id=str(admin_id),
    )


def _admin_operation_status(operation: ClerkAdminOperation) -> dict[str, object]:
    recovery_available = (
        operation.state == "failed"
        and operation.operation_type == "role_update"
        and operation.target_user_id is not None
        and operation.requested_role in {role.value for role in NON_ADMIN_INVITE_ROLES}
        and _partial_metadata_role_rejection_status(operation.last_error_code) is not None
    )
    return {
        "operation_id": operation.id,
        "operation_type": operation.operation_type,
        "state": operation.state,
        "outcome_confirmed": operation.state == "completed",
        "reconciliation_required": (
            operation.state not in {"completed", "failed"} or recovery_available
        ),
        "recovery_available": recovery_available,
        "recovery_action": "retry_rejected_role" if recovery_available else None,
        "provider_resource_id": operation.provider_resource_id,
        "target_user_id": operation.target_user_id,
        "target_email_normalized": operation.target_email_normalized,
        "requested_role": operation.requested_role,
        "updated_at": operation.updated_at,
    }


async def _begin_partial_role_recovery(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    admin_id: uuid.UUID,
    operation_id: uuid.UUID,
    target_user_id: uuid.UUID,
    write_audit_log_fn,
) -> ClerkAdminOperation:
    """Reopen only an exactly correlated, definitely rejected coarse-role call."""
    await _lock_org(db, org_id=org_id)
    target_user = await _load_target_user(
        db,
        user_id=target_user_id,
        for_update=True,
    )
    operation = await _load_admin_operation_by_id(
        db,
        operation_id=operation_id,
        for_update=True,
    )
    if (
        operation.org_id != org_id
        or target_user.org_id != org_id
        or operation.operation_type != "role_update"
        or operation.target_user_id != target_user.id
        or operation.state != "failed"
        or operation.requested_role not in {role.value for role in NON_ADMIN_INVITE_ROLES}
        or _partial_metadata_role_rejection_status(operation.last_error_code) is None
        or target_user.membership_permission_denied_at is None
        or target_user.membership_permission_denied_by_operation_id is not None
        or target_user.membership_permission_convergence_operation_id != operation.id
        or target_user.role.value != operation.requested_role
        or not target_user.membership_active
    ):
        raise APIError(409, "Conflict", "Partial role recovery authority changed")

    # The previous non-retryable 4xx proves the coarse-role mutation was not
    # accepted. Metadata is already accepted, so only that exact step may be
    # retried. Move deny ownership atomically before any provider read.
    target_user.membership_permission_convergence_operation_id = None
    target_user.membership_permission_denied_by_operation_id = operation.id
    operation.state = "metadata_accepted"
    operation.last_error_code = None
    try:
        await write_audit_log_fn(
            db,
            org_id=org_id,
            user_id=admin_id,
            action="admin.user_role.partial_recovery_requested",
            details={
                "operation_id": str(operation.id),
                "target_user_id": str(target_user.id),
                "recovery_action": "retry_rejected_role",
                "least_privilege_denial_retained": True,
            },
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return operation


async def list_admin_operations_impl(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    limit: int = 50,
) -> dict[str, object]:
    """Return recent org-scoped operation state for refresh-safe recovery."""
    open_predicate = ClerkAdminOperation.state.not_in(_ADMIN_OPERATION_TERMINAL_STATES)
    eligible_predicate = or_(
        open_predicate,
        ClerkAdminOperation.updated_at >= datetime.now(UTC) - timedelta(hours=24),
    )
    open_total = int(
        (
            await db.execute(
                select(func.count())
                .select_from(ClerkAdminOperation)
                .where(
                    ClerkAdminOperation.org_id == org_id,
                    open_predicate,
                )
            )
        ).scalar_one()
    )
    operations = list(
        (
            await db.execute(
                select(ClerkAdminOperation)
                .where(
                    ClerkAdminOperation.org_id == org_id,
                    eligible_predicate,
                )
                .order_by(
                    case((open_predicate, 0), else_=1),
                    ClerkAdminOperation.updated_at.desc(),
                    ClerkAdminOperation.id,
                )
                .limit(limit + 1)
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [_admin_operation_status(operation) for operation in operations[:limit]],
        "open_total": open_total,
        "has_more": len(operations) > limit,
    }


async def reconcile_admin_operation_impl(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    admin_id: uuid.UUID,
    operation_id: uuid.UUID,
    settings,
    http_client_cls,
    write_audit_log_fn,
    recovery_action: str | None = None,
) -> dict[str, object]:
    """Reconcile one durable operation without repeating an uncertain mutation."""
    operation = (
        await db.execute(
            select(ClerkAdminOperation).where(
                ClerkAdminOperation.id == operation_id,
                ClerkAdminOperation.org_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if operation is None:
        raise APIError(404, "Not Found", "Admin operation not found")
    if operation.state in _ADMIN_OPERATION_TERMINAL_STATES and recovery_action is None:
        return _admin_operation_status(operation)
    if operation.state == "completed":
        raise APIError(409, "Conflict", "Completed operations cannot be recovered")
    if operation.state == "failed":
        if recovery_action != "retry_rejected_role":
            raise APIError(409, "Conflict", "This failed operation has no safe recovery action")
        if operation.target_user_id is None:
            raise APIError(409, "Conflict", "Role recovery target is incomplete")
        operation = await _begin_partial_role_recovery(
            db,
            org_id=org_id,
            admin_id=admin_id,
            operation_id=operation.id,
            target_user_id=operation.target_user_id,
            write_audit_log_fn=write_audit_log_fn,
        )
    elif recovery_action is not None:
        raise APIError(409, "Conflict", "Recovery actions apply only to failed operations")
    operation_id = operation.id
    # Even a plain SELECT opens a transaction. End it before any provider I/O;
    # each provider call has its own explicit pre/post canonical lock phase.
    await db.commit()

    if operation.operation_type == "invite":
        if not operation.target_email_normalized:
            raise APIError(409, "Conflict", "Invitation operation is incomplete")
        try:
            org, inviter = await _load_clerk_invite_authority(
                db,
                org_id=org_id,
                admin_id=admin_id,
                for_update=True,
            )
            invite_snapshot = _invite_operation_snapshot(
                clerk_org_id=org.clerk_org_id,
                inviter_user_id=inviter.id,
                inviter_clerk_user_id=inviter.clerk_user_id,
                operation=operation,
            )
            if operation.state in {"requested", "invite_call_started"}:
                await _invite_user_in_prod(
                    body=InviteRequest(
                        email=operation.target_email_normalized,
                        role=operation.requested_role,
                    ),
                    clerk_org_id=org.clerk_org_id,
                    inviter_user_id=inviter.id,
                    inviter_clerk_user_id=inviter.clerk_user_id,
                    settings=settings,
                    http_client_cls=http_client_cls,
                    db=db,
                    operation=operation,
                )
            _, _, operation = await _lock_invite_operation_snapshot(
                db,
                snapshot=invite_snapshot,
                expected_states=frozenset({"provider_accepted"}),
            )
        except Exception as exc:
            await db.rollback()
            await _lock_org(db, org_id=org_id)
            operation = await _load_admin_operation_by_id(
                db, operation_id=operation_id, for_update=True
            )
            if _can_terminally_fail_without_reconciliation(operation, exc):
                operation.state = "failed"
                operation.last_error_code = (
                    f"clerk_{exc.provider_status_code}"
                    if isinstance(exc, _KnownClerkRejectionError)
                    else type(exc).__name__
                )[:64]
                await write_audit_log_fn(
                    db,
                    org_id=org_id,
                    user_id=admin_id,
                    action="admin.user_invite.reconcile_failed",
                    details={
                        "operation_id": str(operation.id),
                        "terminal": True,
                        "error_type": type(exc).__name__,
                    },
                    fail_closed=True,
                )
                await db.commit()
                if isinstance(exc, APIError):
                    exc.type_uri = _ADMIN_OPERATION_TERMINAL_FAILURE_TYPE
            raise
        if operation.state == "provider_accepted":
            operation.state = "completed"
            await write_audit_log_fn(
                db,
                org_id=org_id,
                user_id=admin_id,
                action="admin.user_invite.reconciled",
                details={
                    "operation_id": str(operation.id),
                    "provider_invitation_id": operation.provider_resource_id,
                    "provider_accepted": True,
                },
                fail_closed=True,
            )
            await db.commit()
        return _admin_operation_status(operation)

    if operation.target_user_id is None:
        raise APIError(409, "Conflict", "Role operation is incomplete")
    target_user_id = operation.target_user_id
    new_role = _parse_user_role(operation.requested_role)
    org, target_user, reserved_operation = await _reserve_role_change(
        db,
        target_user_id=target_user_id,
        admin_org_id=org_id,
        new_role=new_role,
        operation_id=operation.id,
    )
    operation = reserved_operation
    previous_role = target_user.role.value
    role_snapshot = _role_operation_snapshot(
        org=org,
        target_user=target_user,
        operation=operation,
    )
    try:
        await _update_user_role_in_clerk(
            target_user=target_user,
            org=org,
            new_role=new_role,
            settings=settings,
            http_client_cls=http_client_cls,
            db=db,
            operation=operation,
        )
    except Exception as exc:
        await db.rollback()
        await _lock_org(db, org_id=org_id)
        target_user = await _load_target_user(db, user_id=target_user_id, for_update=True)
        operation = await _load_admin_operation_by_id(
            db, operation_id=operation_id, for_update=True
        )
        if _can_terminally_fail_without_reconciliation(
            operation, exc
        ) or _is_partial_metadata_role_rejection(operation, exc):
            partial_metadata_accepted = _terminalize_role_failure(
                target_user,
                operation=operation,
                exc=exc,
                denied_at=await _database_clock(db),
            )
            await write_audit_log_fn(
                db,
                org_id=org_id,
                user_id=admin_id,
                action="admin.user_role.reconcile_failed",
                details={
                    "operation_id": str(operation.id),
                    "target_user_id": str(target_user.id),
                    "provider_accepted": partial_metadata_accepted,
                    "partial_metadata_accepted": partial_metadata_accepted,
                    "authority_denied_pending_convergence": partial_metadata_accepted,
                    "terminal_reason": operation.last_error_code,
                    "terminal": True,
                    "error_type": type(exc).__name__,
                },
                fail_closed=True,
            )
            await db.commit()
            if isinstance(exc, APIError):
                exc.type_uri = _ADMIN_OPERATION_TERMINAL_FAILURE_TYPE
        raise
    org, target_user, operation = await _lock_role_operation_snapshot(
        db,
        snapshot=role_snapshot,
        expected_states=frozenset({"metadata_accepted", "role_accepted"}),
    )
    await _guard_last_admin_demotion(
        db,
        target_user=target_user,
        admin_org_id=org_id,
        new_role=new_role,
        for_update=True,
        require_synchronized_authority=True,
    )
    target_user.role = new_role
    target_user.clerk_membership_role = "admin" if new_role == UserRole.ADMIN else "member"
    _clear_operation_owned_denial(target_user, operation=operation)
    if operation.provider_updated_at is not None:
        target_user.membership_updated_at = max(
            target_user.membership_updated_at, operation.provider_updated_at
        )
    operation.state = "completed"
    await write_audit_log_fn(
        db,
        org_id=org_id,
        user_id=admin_id,
        action="admin.user_role.reconciled",
        details={
            "operation_id": str(operation.id),
            "target_user_id": str(target_user.id),
            "previous_role": previous_role,
            "new_role": new_role.value,
            "provider_updated_at": (
                operation.provider_updated_at.isoformat()
                if operation.provider_updated_at is not None
                else None
            ),
        },
        fail_closed=True,
    )
    await db.commit()
    return _admin_operation_status(operation)
