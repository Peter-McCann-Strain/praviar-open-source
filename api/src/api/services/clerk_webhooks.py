"""Fail-closed Clerk organization and membership webhook synchronization."""

from __future__ import annotations

import asyncio
import math
import re
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import httpx
import structlog
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StrictInt,
    StrictStr,
    TypeAdapter,
    ValidationError,
)
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import (
    ClerkAdminOperation,
    ClerkMembershipTombstone,
    Organization,
    User,
    UserRole,
)
from api.db.session import bind_current_org_to_session
from api.errors import APIError
from api.services.billing_policy import plan_limit_for

logger = structlog.get_logger()

DEFAULT_ORG_NAME = "Workspace"
MEMBERSHIP_CREATED = "organizationMembership.created"
MEMBERSHIP_UPDATED = "organizationMembership.updated"
MEMBERSHIP_DELETED = "organizationMembership.deleted"
MEMBERSHIP_EVENT_TYPES = frozenset({MEMBERSHIP_CREATED, MEMBERSHIP_UPDATED, MEMBERSHIP_DELETED})
_ADMIN_OPERATION_TERMINAL_STATES = frozenset({"completed", "failed"})
_PARTIAL_METADATA_ROLE_REJECTION_PREFIX = "clerk_role_rejected_after_metadata_"
_PARTIAL_METADATA_ROLE_REJECTION_RE = re.compile(
    rf"{re.escape(_PARTIAL_METADATA_ROLE_REJECTION_PREFIX)}(4\d{{2}})"
)
_PROVIDER_TIMESTAMP_FUTURE_SKEW = timedelta(minutes=5)

# Clerk webhook roles include the ``org:`` prefix. Session-token-v2 ``o.rol``
# omits it, so the normalized role is persisted separately for exact auth-time
# consistency checks.
CLERK_MEMBERSHIP_ROLE_MAP: dict[str, str] = {
    "org:admin": "admin",
    "org:member": "member",
}
PRAVIAR_ROLE_METADATA_VERSION = 1
PRAVIAR_ROLE_METADATA_KEY = "praviar_role"
PRAVIAR_ROLE_VERSION_KEY = "praviar_role_version"
NON_ADMIN_USER_ROLES = frozenset({UserRole.ATTORNEY, UserRole.SCIENTIST, UserRole.CLIENT})
_EMAIL_ADAPTER = TypeAdapter(EmailStr)
_CLERK_API_VERSION = "2026-05-12"
_CLERK_BOOTSTRAP_TOTAL_TIMEOUT_SECONDS = 3.0
_CLERK_BOOTSTRAP_RETRYABLE = frozenset({408, 429, *range(500, 600)})


async def _database_clock(db: AsyncSession) -> datetime:
    value = await db.scalar(select(func.clock_timestamp()))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise APIError(503, "Service Unavailable", "Database authority clock is unavailable")
    return value.astimezone(UTC)


def _validate_membership_authority_timestamp(
    event_updated_at: datetime,
    *,
    database_now: datetime,
) -> None:
    """Reject unsafe provider time after the canonical principal lock.

    Five minutes is the documented ceiling for ordinary Clerk/PostgreSQL clock
    drift. Locked local/durable watermarks are handled by the caller so stale
    webhook deliveries can be acknowledged without changing authority.
    """
    if event_updated_at > database_now + _PROVIDER_TIMESTAMP_FUTURE_SKEW:
        raise APIError(409, "Conflict", "Clerk returned a future-dated membership snapshot")


class _ClerkOrganization(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: StrictStr
    name: StrictStr = DEFAULT_ORG_NAME


class _ClerkPublicUserData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_id: StrictStr | None = None
    identifier: StrictStr = ""
    first_name: StrictStr | None = None
    last_name: StrictStr | None = None


class _ClerkMembershipEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: StrictStr
    organization: _ClerkOrganization
    public_user_data: _ClerkPublicUserData | None = None
    public_metadata: dict[str, object] = Field(default_factory=dict)
    role: StrictStr
    updated_at: StrictInt


def _free_plan_limit() -> int:
    return plan_limit_for("free")


def _required_text(value: str, *, detail: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise APIError(400, "Bad Request", detail)
    return normalized


def _membership_event_timestamp(updated_at_ms: int) -> datetime:
    if updated_at_ms <= 0:
        raise APIError(400, "Bad Request", "Invalid membership updated_at")
    try:
        return datetime.fromtimestamp(updated_at_ms / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise APIError(400, "Bad Request", "Invalid membership updated_at") from exc


def _parse_membership_event(
    data: dict,
    *,
    event_type: str,
) -> tuple[_ClerkMembershipEvent, str, UserRole | None, datetime, str | None]:
    if event_type not in MEMBERSHIP_EVENT_TYPES:
        raise APIError(400, "Bad Request", "Unsupported membership event type")
    try:
        event = _ClerkMembershipEvent.model_validate(data)
    except ValidationError as exc:
        logger.warning(
            "clerk_membership_payload_invalid",
            event_type=event_type,
            errors=exc.error_count(),
        )
        raise APIError(400, "Bad Request", "Malformed organization membership event") from exc

    _required_text(event.id, detail="Missing membership ID in webhook payload")
    _required_text(event.organization.id, detail="Missing organization ID in webhook payload")
    token_role = CLERK_MEMBERSHIP_ROLE_MAP.get(event.role)
    if token_role is None and event_type != MEMBERSHIP_DELETED:
        logger.warning(
            "clerk_membership_role_rejected",
            membership_id=event.id,
            role=event.role,
        )
        raise APIError(400, "Bad Request", "Unsupported organization membership role")
    # Revocation must not be blocked by a custom or future Clerk role. The
    # normalized token role is ignored on the deletion path.
    normalized_token_role = token_role or "deleted"
    # Deletion must revoke the membership even if optional role metadata is
    # absent or malformed. Role metadata is authority only for active upserts.
    local_role = (
        None
        if event_type == MEMBERSHIP_DELETED
        else _local_role_from_membership(event, token_role=normalized_token_role)
    )
    event_updated_at = _membership_event_timestamp(event.updated_at)

    clerk_user_id = None
    if event.public_user_data is not None and event.public_user_data.user_id is not None:
        clerk_user_id = _required_text(
            event.public_user_data.user_id,
            detail="Missing user ID in membership webhook payload",
        )
    if event_type != MEMBERSHIP_DELETED and clerk_user_id is None:
        raise APIError(400, "Bad Request", "Missing user ID in membership webhook payload")

    return event, normalized_token_role, local_role, event_updated_at, clerk_user_id


def _local_role_from_membership(
    event: _ClerkMembershipEvent,
    *,
    token_role: str,
) -> UserRole | None:
    """Map coarse Clerk authority plus versioned Praviar membership metadata."""
    if token_role == "admin":
        return UserRole.ADMIN

    metadata = event.public_metadata
    if not metadata:
        # Missing metadata never invents or preserves local authority. A newer
        # event for an existing synchronized principal revokes access below.
        logger.warning(
            "clerk_membership_role_metadata_missing",
            membership_id=event.id,
        )
        return None

    version = metadata.get(PRAVIAR_ROLE_VERSION_KEY)
    role_value = metadata.get(PRAVIAR_ROLE_METADATA_KEY)
    if (
        isinstance(version, bool)
        or version != PRAVIAR_ROLE_METADATA_VERSION
        or not isinstance(role_value, str)
    ):
        logger.warning(
            "clerk_membership_role_metadata_invalid",
            membership_id=event.id,
        )
        return None
    try:
        local_role = UserRole(role_value)
    except ValueError:
        logger.warning(
            "clerk_membership_role_metadata_invalid",
            membership_id=event.id,
        )
        return None
    if local_role not in NON_ADMIN_USER_ROLES:
        logger.warning(
            "clerk_membership_role_metadata_invalid",
            membership_id=event.id,
        )
        return None
    return local_role


async def get_or_create_org(
    db: AsyncSession,
    *,
    clerk_org_id: str,
    name: str,
) -> Organization:
    """Return a durable local organization for a verified Clerk org ID."""
    clerk_org_id = _required_text(
        str(clerk_org_id or ""),
        detail="Missing organization ID in webhook payload",
    )
    name = str(name or "").strip() or DEFAULT_ORG_NAME

    # This is the canonical first row lock for every membership webhook and
    # bootstrap mutation. Admin mutations use the same org→user→operation order.
    result = await db.execute(
        select(Organization)
        .where(Organization.clerk_org_id == clerk_org_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    org = result.scalar_one_or_none()
    if org is not None:
        return org

    slug = re.sub(r"[^a-z0-9-]", "-", clerk_org_id.lower())[:100].strip("-")
    org = Organization(
        clerk_org_id=clerk_org_id,
        free_analyses_remaining=_free_plan_limit(),
        max_analyses_per_month=_free_plan_limit(),
        name=name,
        slug=slug,
    )
    db.add(org)
    # A concurrent creator may win this unique insert. Let the transaction roll
    # back and the same Svix delivery retry; catching here would also roll back
    # its transactional receipt and could acknowledge an unreceipted mutation.
    await db.flush()
    logger.info("clerk_org_created", clerk_org_id=clerk_org_id, org_id=str(org.id))
    return org


async def handle_user_created(db: AsyncSession, data: dict) -> dict:
    """Acknowledge identity creation without inventing B2B tenant access.

    Clerk's ``user.created`` payload does not carry the authoritative
    organization-membership collection. Local principals are therefore created
    only by organization-membership events. Historical synthetic personal rows
    remain readable but no new personal tenant is provisioned as a fallback.
    """
    del db
    clerk_user_id = data.get("id")
    if not isinstance(clerk_user_id, str) or not clerk_user_id.strip():
        raise APIError(400, "Bad Request", "Missing user ID in webhook payload")
    logger.info("clerk_user_awaiting_membership", clerk_user_id=clerk_user_id.strip())
    return {"status": "awaiting_membership"}


async def handle_org_created(db: AsyncSession, data: dict) -> dict:
    """Sync a Clerk organization without granting a user role."""
    clerk_org_id = data.get("id")
    if not isinstance(clerk_org_id, str) or not clerk_org_id.strip():
        raise APIError(400, "Bad Request", "Missing org ID in webhook payload")

    existing = await db.execute(
        select(Organization).where(Organization.clerk_org_id == clerk_org_id.strip())
    )
    if existing.scalar_one_or_none() is not None:
        return {"status": "already_exists"}

    slug_value = data.get("slug")
    slug = slug_value.strip() if isinstance(slug_value, str) else ""
    db.add(
        Organization(
            clerk_org_id=clerk_org_id.strip(),
            free_analyses_remaining=_free_plan_limit(),
            max_analyses_per_month=_free_plan_limit(),
            name=str(data.get("name") or "").strip() or DEFAULT_ORG_NAME,
            slug=slug or re.sub(r"[^a-z0-9-]", "-", clerk_org_id.lower()).strip("-"),
        )
    )
    await db.flush()
    return {"status": "ok"}


async def _membership_tombstone(
    db: AsyncSession,
    *,
    membership_id: str,
) -> ClerkMembershipTombstone | None:
    result = await db.execute(
        select(ClerkMembershipTombstone)
        .where(ClerkMembershipTombstone.clerk_membership_id == membership_id)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def _membership_user_candidates(
    db: AsyncSession,
    *,
    membership_id: str,
    clerk_user_id: str,
    org_id: object,
) -> list[User]:
    result = await db.execute(
        select(User)
        .where(
            or_(
                User.clerk_membership_id == membership_id,
                (User.clerk_user_id == clerk_user_id) & (User.org_id == org_id),
            )
        )
        .with_for_update()
    )
    return list(result.scalars().all())


async def _open_role_operation_for_user(
    db: AsyncSession,
    *,
    org_id: object,
    user_id: object,
) -> ClerkAdminOperation | None:
    """Lock the one open role operation after the canonical org and user locks."""
    result = await db.execute(
        select(ClerkAdminOperation)
        .where(
            ClerkAdminOperation.org_id == org_id,
            ClerkAdminOperation.operation_type == "role_update",
            ClerkAdminOperation.target_user_id == user_id,
            ClerkAdminOperation.state.not_in(_ADMIN_OPERATION_TERMINAL_STATES),
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


def _is_exact_partial_role_failure(
    operation: ClerkAdminOperation,
    *,
    operation_id: object,
    org_id: object,
    user_id: object,
) -> bool:
    error_match = (
        _PARTIAL_METADATA_ROLE_REJECTION_RE.fullmatch(operation.last_error_code)
        if isinstance(operation.last_error_code, str)
        else None
    )
    status_code = int(error_match.group(1)) if error_match is not None else None
    return (
        operation.id == operation_id
        and operation.org_id == org_id
        and operation.operation_type == "role_update"
        and operation.target_user_id == user_id
        and operation.state == "failed"
        and operation.requested_role in {role.value for role in NON_ADMIN_USER_ROLES}
        and status_code is not None
        and status_code not in _CLERK_BOOTSTRAP_RETRYABLE
    )


async def _convergence_role_operation_for_user(
    db: AsyncSession,
    *,
    org_id: object,
    user: User,
) -> ClerkAdminOperation | None:
    """Lock and verify the exact terminal partial demotion referenced by the user."""
    operation_id = user.membership_permission_convergence_operation_id
    if operation_id is None:
        return None
    result = await db.execute(
        select(ClerkAdminOperation)
        .where(ClerkAdminOperation.id == operation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    operation = result.scalar_one_or_none()
    if operation is None:
        logger.error(
            "clerk_membership_convergence_operation_missing",
            operation_id=str(operation_id),
            org_id=str(org_id),
            user_id=str(user.id),
        )
        return None
    if not _is_exact_partial_role_failure(
        operation,
        operation_id=operation_id,
        org_id=org_id,
        user_id=user.id,
    ):
        logger.error(
            "clerk_membership_convergence_operation_invalid",
            operation_id=str(operation_id),
            org_id=str(org_id),
            user_id=str(user.id),
        )
        return None
    return operation


def _partial_role_failure_converged(
    *,
    operation: ClerkAdminOperation,
    event: _ClerkMembershipEvent,
    token_role: str,
    local_role: UserRole,
) -> bool:
    """Require exact provider proof before releasing a partial-demotion deny."""
    if token_role == "member":
        return local_role.value == operation.requested_role
    if token_role != "admin":
        return False
    governed_version = event.public_metadata.get(PRAVIAR_ROLE_VERSION_KEY)
    governed_role = event.public_metadata.get(PRAVIAR_ROLE_METADATA_KEY)
    metadata_restored_for_admin = (governed_version is None and governed_role is None) or (
        governed_version == PRAVIAR_ROLE_METADATA_VERSION and governed_role == UserRole.ADMIN.value
    )
    return metadata_restored_for_admin


def _membership_profile(event: _ClerkMembershipEvent) -> tuple[str, str]:
    public_user = event.public_user_data
    if public_user is None:
        return "", ""
    try:
        email = str(_EMAIL_ADAPTER.validate_python(public_user.identifier.strip()))
    except ValidationError as exc:
        raise APIError(
            400,
            "Bad Request",
            "Membership user identifier must be an email address",
        ) from exc
    full_name = " ".join(
        part.strip()
        for part in (public_user.first_name or "", public_user.last_name or "")
        if part.strip()
    )
    return email, full_name


async def _handle_membership_delete(
    db: AsyncSession,
    *,
    event: _ClerkMembershipEvent,
    org: Organization,
    event_updated_at: datetime,
    clerk_user_id: str | None,
) -> dict:
    tombstone = await _membership_tombstone(db, membership_id=event.id)
    user_result = await db.execute(
        select(User)
        .where(
            User.org_id == org.id,
            User.clerk_membership_id == event.id,
        )
        .with_for_update()
    )
    user = user_result.scalar_one_or_none()
    operation = None
    if user is not None:
        if clerk_user_id is not None and user.clerk_user_id != clerk_user_id:
            raise APIError(409, "Conflict", "Membership identity does not match local principal")
        operation = await _open_role_operation_for_user(
            db,
            org_id=org.id,
            user_id=user.id,
        )
    database_now = await _database_clock(db)
    _validate_membership_authority_timestamp(
        event_updated_at,
        database_now=database_now,
    )
    watermark = max(
        (
            value
            for value in (
                user.membership_updated_at if user is not None else None,
                operation.provider_updated_at if operation is not None else None,
            )
            if value is not None
        ),
        default=None,
    )
    if watermark is not None and event_updated_at < watermark:
        return {"status": "ignored_stale", "_terminalized_operation_id": None}

    if tombstone is None:
        tombstone = ClerkMembershipTombstone(
            clerk_membership_id=event.id,
            org_id=org.id,
            clerk_user_id=clerk_user_id,
            event_updated_at=event_updated_at,
            deleted_at=event_updated_at,
        )
        db.add(tombstone)
    elif event_updated_at > tombstone.event_updated_at:
        tombstone.event_updated_at = event_updated_at
        tombstone.deleted_at = event_updated_at
        if clerk_user_id is not None:
            tombstone.clerk_user_id = clerk_user_id

    if user is not None:
        # Deletion is terminal for this external membership ID only after its
        # timestamp has cleared the locked principal/operation watermark.
        user.membership_active = False
        user.membership_permission_denied_at = event_updated_at
        terminalized_operation_id = None
        if operation is not None:
            operation.state = "failed"
            operation.last_error_code = "membership_deleted"
            terminalized_operation_id = str(operation.id)
        # Deletion is a terminal provider fact, not an in-flight operation.
        # Retain the deny timestamp while ensuring a future membership ID can
        # never inherit stale operation ownership.
        user.membership_permission_denied_by_operation_id = None
        user.membership_permission_convergence_operation_id = None
        user.membership_deleted_at = event_updated_at
        user.membership_updated_at = max(user.membership_updated_at, event_updated_at)
    else:
        terminalized_operation_id = None

    await db.flush()
    return {
        "status": "deleted" if user is not None else "tombstoned",
        "_terminalized_operation_id": terminalized_operation_id,
    }


async def _handle_membership_upsert(
    db: AsyncSession,
    *,
    event: _ClerkMembershipEvent,
    org: Organization,
    token_role: str,
    local_role: UserRole | None,
    event_updated_at: datetime,
    clerk_user_id: str,
) -> dict:
    tombstone = await _membership_tombstone(db, membership_id=event.id)
    if tombstone is not None:
        _validate_membership_authority_timestamp(
            event_updated_at,
            database_now=await _database_clock(db),
        )
        logger.warning(
            "clerk_membership_resurrection_blocked",
            membership_id=event.id,
            org_id=str(org.id),
        )
        return {"status": "ignored_deleted"}
    candidates = await _membership_user_candidates(
        db,
        membership_id=event.id,
        clerk_user_id=clerk_user_id,
        org_id=org.id,
    )
    if len(candidates) > 1:
        raise APIError(409, "Conflict", "Membership identity maps to multiple principals")

    user = candidates[0] if candidates else None
    convergence_operation = None
    if user is not None and user.membership_permission_convergence_operation_id is not None:
        convergence_operation = await _convergence_role_operation_for_user(
            db,
            org_id=org.id,
            user=user,
        )
    database_now = await _database_clock(db)
    _validate_membership_authority_timestamp(
        event_updated_at,
        database_now=database_now,
    )
    operation_watermark = (
        convergence_operation.provider_updated_at if convergence_operation is not None else None
    )
    if operation_watermark is not None and event_updated_at < operation_watermark:
        return {"status": "ignored_stale"}

    email, full_name = _membership_profile(event)
    if not email:
        raise APIError(400, "Bad Request", "Missing user identifier in membership payload")

    if not candidates:
        if local_role is None:
            raise APIError(
                409,
                "Conflict",
                "Versioned Praviar membership role metadata is required",
            )
        user = User(
            clerk_user_id=clerk_user_id,
            clerk_membership_id=event.id,
            clerk_membership_role=token_role,
            org_id=org.id,
            email=email,
            full_name=full_name,
            role=local_role,
            membership_active=True,
            membership_permission_denied_at=None,
            membership_permission_denied_by_operation_id=None,
            membership_permission_convergence_operation_id=None,
            membership_updated_at=event_updated_at,
            membership_deleted_at=None,
        )
        db.add(user)
        await db.flush()
        return {"status": "created"}

    assert user is not None
    if user.clerk_user_id != clerk_user_id or user.org_id != org.id:
        raise APIError(409, "Conflict", "Membership identity does not match local principal")

    convergence_operation_id = user.membership_permission_convergence_operation_id
    convergence_confirmed = (
        convergence_operation is not None
        and local_role is not None
        and (
            _partial_role_failure_converged(
                operation=convergence_operation,
                event=event,
                token_role=token_role,
                local_role=local_role,
            )
        )
    )

    if event_updated_at == user.membership_updated_at and not convergence_confirmed:
        exact_authority_echo = (
            user.clerk_membership_id == event.id
            and user.clerk_membership_role == token_role
            and user.membership_active
            and local_role is not None
            and user.role == local_role
        )
        if exact_authority_echo:
            return {"status": "ignored_stale"}
        # Provider milliseconds are not an ordering oracle. A different
        # authority payload at the same instant is ambiguous, so retain the
        # least-privilege role and deactivate access instead of letting the
        # earlier (possibly admin) snapshot win.
        if local_role is not None and local_role != UserRole.ADMIN:
            user.role = local_role
        user.membership_active = False
        if user.membership_permission_denied_by_operation_id is None:
            user.membership_permission_denied_at = database_now
        await db.flush()
        return {"status": "deactivated_timestamp_collision"}

    # A true deletion tombstone is terminal for the exact membership ID. A
    # fail-closed metadata deactivation is different: strictly newer valid
    # authority for that same ID may reactivate the principal.
    if not user.membership_active:
        if user.clerk_membership_id == event.id and user.membership_deleted_at is not None:
            return {"status": "ignored_deleted"}
        if event_updated_at < user.membership_updated_at:
            return {"status": "ignored_stale"}
    elif user.clerk_membership_id not in (None, event.id):
        if event_updated_at < user.membership_updated_at:
            return {"status": "ignored_stale"}
        raise APIError(409, "Conflict", "A different active membership already exists")
    elif user.clerk_membership_id is not None and event_updated_at < user.membership_updated_at:
        return {"status": "ignored_stale"}

    if local_role is None:
        # Only an already-bound membership can be revoked by missing governed
        # metadata. Legacy rows with no external membership ID require an
        # explicit, versioned one-time adoption event.
        if user.clerk_membership_id != event.id:
            raise APIError(
                409,
                "Conflict",
                "Versioned Praviar membership role metadata is required",
            )
        user.clerk_membership_role = token_role
        user.membership_active = False
        if user.membership_permission_denied_by_operation_id is None:
            user.membership_permission_denied_at = event_updated_at
        user.membership_updated_at = event_updated_at
        user.membership_deleted_at = None
        await db.flush()
        return {"status": "deactivated_missing_role_authority"}

    user.clerk_membership_id = event.id
    user.clerk_membership_role = token_role
    # A partial-demotion echo with coarse admin plus the conflicting non-admin
    # metadata is not convergence. Preserve the least-privilege local role and
    # generic deny until Clerk proves either the requested member authority or
    # a clean, explicitly restored admin authority.
    if convergence_operation_id is None or convergence_confirmed:
        user.role = local_role
    user.email = email
    user.full_name = full_name
    user.membership_active = True
    # An in-flight role operation owns its deny marker. Webhook/bootstrap
    # convergence may update provider facts, but only exact operation
    # finalization may release that local authorization boundary.
    if user.membership_permission_denied_by_operation_id is None and (
        convergence_operation_id is None or convergence_confirmed
    ):
        user.membership_permission_denied_at = None
        user.membership_permission_convergence_operation_id = None
    user.membership_updated_at = event_updated_at
    user.membership_deleted_at = None
    await db.flush()
    return {"status": "updated"}


async def handle_membership_event(
    db: AsyncSession,
    data: dict,
    *,
    event_type: str,
    event_id: str | None = None,
    source: str = "clerk_webhook",
    write_audit_log_fn=None,
) -> dict:
    """Apply one exact Clerk organization-membership event monotonically."""
    event, token_role, local_role, event_updated_at, clerk_user_id = _parse_membership_event(
        data,
        event_type=event_type,
    )
    org = await get_or_create_org(
        db,
        clerk_org_id=event.organization.id,
        name=event.organization.name,
    )

    # Tombstones are RLS-protected, and all principal mutations must occur only
    # after the verified external org has resolved to a durable local tenant.
    await bind_current_org_to_session(db, org.id)

    prior_user = None
    if write_audit_log_fn is not None:
        identity_clause = User.clerk_membership_id == event.id
        if clerk_user_id is not None:
            identity_clause = or_(
                identity_clause,
                User.clerk_user_id == clerk_user_id,
            )
        prior_user = (
            (
                await db.execute(
                    select(User)
                    .where(
                        User.org_id == org.id,
                        identity_clause,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .first()
        )
    prior_authority = _membership_authority_snapshot(prior_user)

    if event_type == MEMBERSHIP_DELETED:
        result = await _handle_membership_delete(
            db,
            event=event,
            org=org,
            event_updated_at=event_updated_at,
            clerk_user_id=clerk_user_id,
        )
    else:
        assert clerk_user_id is not None  # validated in _parse_membership_event
        result = await _handle_membership_upsert(
            db,
            event=event,
            org=org,
            token_role=token_role,
            local_role=local_role,
            event_updated_at=event_updated_at,
            clerk_user_id=clerk_user_id,
        )

    terminalized_operation_id = result.pop("_terminalized_operation_id", None)
    if write_audit_log_fn is not None:
        current_user = (
            (
                await db.execute(
                    select(User).where(
                        User.org_id == org.id,
                        User.clerk_membership_id == event.id,
                    )
                )
            )
            .scalars()
            .first()
        )
        await write_audit_log_fn(
            db,
            org_id=org.id,
            user_id=current_user.id if current_user is not None else None,
            action="clerk.membership.authority_changed",
            details={
                "source": source,
                "delivery_event_id": event_id,
                "event_type": event_type,
                "membership_id": event.id,
                "clerk_user_id": clerk_user_id,
                "event_updated_at": event_updated_at.isoformat(),
                "result": result["status"],
                "terminalized_operation_id": terminalized_operation_id,
                "prior_authority": prior_authority,
                "new_authority": _membership_authority_snapshot(current_user),
                "clerk_authority": {
                    "role": event.role,
                    "praviar_role_version": event.public_metadata.get(PRAVIAR_ROLE_VERSION_KEY),
                    "praviar_role": event.public_metadata.get(PRAVIAR_ROLE_METADATA_KEY),
                },
            },
            fail_closed=True,
        )
    return result


def _membership_authority_snapshot(user: User | None) -> dict[str, object] | None:
    if user is None:
        return None
    return {
        "user_id": str(user.id),
        "local_role": user.role.value,
        "membership_active": user.membership_active,
        "membership_permission_denied_at": (
            user.membership_permission_denied_at.isoformat()
            if user.membership_permission_denied_at is not None
            else None
        ),
        "membership_permission_denied_by_operation_id": (
            str(user.membership_permission_denied_by_operation_id)
            if user.membership_permission_denied_by_operation_id is not None
            else None
        ),
        "membership_permission_convergence_operation_id": (
            str(user.membership_permission_convergence_operation_id)
            if user.membership_permission_convergence_operation_id is not None
            else None
        ),
        "clerk_membership_id": user.clerk_membership_id,
        "clerk_membership_role": user.clerk_membership_role,
    }


def _retry_after_seconds(response: httpx.Response) -> float:
    value = response.headers.get("Retry-After", "").strip()
    if not value:
        return 0.05
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if not isinstance(retry_at, datetime):
                raise TypeError("Retry-After did not parse as a datetime")
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 0.05


async def bootstrap_clerk_membership(
    db: AsyncSession,
    *,
    clerk_user_id: str,
    clerk_org_id: str,
    token_org_role: str,
    settings: object,
    write_audit_log_fn,
    http_client_cls=httpx.AsyncClient,
) -> dict:
    """Synchronously reconcile one token-bound Clerk membership on first login."""
    secret_key = str(getattr(settings, "clerk_secret_key", "") or "").strip()
    if not secret_key:
        raise APIError(503, "Service Unavailable", "Clerk membership sync is not configured")
    if token_org_role not in {"admin", "member"}:
        raise APIError(409, "Conflict", "Signed organization role is unsupported")

    url = f"https://api.clerk.com/v1/organizations/{quote(clerk_org_id, safe='')}/memberships"
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Accept": "application/json",
        "Clerk-API-Version": _CLERK_API_VERSION,
    }

    try:
        async with asyncio.timeout(_CLERK_BOOTSTRAP_TOTAL_TIMEOUT_SECONDS):
            async with http_client_cls(
                timeout=httpx.Timeout(2.5, connect=1.0),
            ) as client:
                response: httpx.Response | None = None
                for attempt in range(2):
                    try:
                        response = await client.get(
                            url,
                            headers=headers,
                            params={
                                "user_id": clerk_user_id,
                                "limit": 2,
                                "offset": 0,
                            },
                        )
                    except httpx.RequestError as exc:
                        if attempt == 1:
                            raise APIError(
                                503,
                                "Service Unavailable",
                                "Clerk membership sync is temporarily unavailable",
                            ) from exc
                        await asyncio.sleep(0.05)
                        continue

                    if response.status_code not in _CLERK_BOOTSTRAP_RETRYABLE:
                        break
                    retry_after = _retry_after_seconds(response)
                    if attempt == 1:
                        raise APIError(
                            503,
                            "Service Unavailable",
                            "Clerk membership sync is temporarily unavailable",
                            retry_after_seconds=max(1, math.ceil(retry_after)),
                        )
                    await asyncio.sleep(retry_after)

                assert response is not None
    except TimeoutError as exc:
        raise APIError(
            503,
            "Service Unavailable",
            "Clerk membership sync timed out",
        ) from exc

    if response.status_code != 200:
        raise APIError(
            503,
            "Service Unavailable",
            "Clerk membership sync returned an unexpected response",
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise APIError(
            503,
            "Service Unavailable",
            "Clerk membership sync returned invalid JSON",
        ) from exc
    if not isinstance(payload, dict):
        raise APIError(503, "Service Unavailable", "Clerk membership sync returned invalid data")
    total_count = payload.get("total_count")
    rows = payload.get("data")
    if total_count == 0 and rows == []:
        raise APIError(403, "Forbidden", "No active Clerk organization membership")
    if total_count != 1 or not isinstance(rows, list) or len(rows) != 1:
        raise APIError(409, "Conflict", "Clerk membership lookup was ambiguous")

    membership = rows[0]
    if not isinstance(membership, dict):
        raise APIError(503, "Service Unavailable", "Clerk membership sync returned invalid data")
    event, persisted_token_role, _local_role, _updated_at, persisted_user_id = (
        _parse_membership_event(membership, event_type=MEMBERSHIP_UPDATED)
    )
    if (
        event.organization.id != clerk_org_id
        or persisted_user_id != clerk_user_id
        or persisted_token_role != token_org_role
    ):
        raise APIError(409, "Conflict", "Signed Clerk organization context is stale")

    try:
        return await handle_membership_event(
            db,
            membership,
            event_type=MEMBERSHIP_UPDATED,
            source="clerk_bootstrap",
            write_audit_log_fn=write_audit_log_fn,
        )
    except Exception:
        # Bootstrap is an authentication boundary. An audit write is part of
        # the same transaction as principal convergence and must fail closed.
        await db.rollback()
        raise
