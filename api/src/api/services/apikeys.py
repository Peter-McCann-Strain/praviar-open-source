"""Business logic for API key management."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import write_audit_log
from api.config import get_settings
from api.db.models import APIKey, Organization
from api.db.session import bind_current_org_to_session
from api.errors import APIError
from api.schemas.apikeys import APIKeyScope, CreateAPIKeyRequest

logger = structlog.get_logger()

API_KEY_NAMESPACE = "prv_live_"
API_KEY_RANDOM_TOKEN_LENGTH = 43
API_KEY_VISIBLE_PREFIX_LENGTH = 20
API_KEY_SHAPE = re.compile(
    rf"^{re.escape(API_KEY_NAMESPACE)}[A-Za-z0-9_-]{{{API_KEY_RANDOM_TOKEN_LENGTH}}}$"
)
_API_KEY_BLOCKED_DELETION_STATUSES = frozenset(
    {"billing_cancellation_pending", "archive_deletion_pending", "erased"}
)


def is_namespaced_api_key(raw_key: str) -> bool:
    """Reject JWTs, legacy keys and malformed credentials before DB access."""
    return bool(API_KEY_SHAPE.fullmatch(raw_key))


def _hash_key(raw: str) -> str:
    """Return an HMAC-SHA256 hex digest of *raw*, keyed with the configured secret.

    Keying the hash prevents offline dictionary attacks even if the key_hash
    column is exfiltrated: an attacker also needs the HMAC secret to derive
    candidate digests.
    """
    secret = get_settings().api_key_hmac_secret.get_secret_value().encode()
    return hmac.new(secret, raw.encode(), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class APIKeySecret:
    api_key: APIKey
    secret_key: str


@dataclass(frozen=True)
class APIKeyPage:
    items: list[APIKey]
    total: int


async def create_api_key(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    body: CreateAPIKeyRequest,
    request: Request,
) -> APIKeySecret:
    if "reports:export" in body.scopes and get_settings().require_attorney_role_for_risk_ratings:
        raise APIError(
            422,
            "Unprocessable Entity",
            "The reports:export API-key scope is unavailable while "
            "restricted risk ratings require an attorney role",
        )

    key_raw = f"{API_KEY_NAMESPACE}{secrets.token_urlsafe(32)}"
    key_hash = _hash_key(key_raw)
    key_prefix = key_raw[:API_KEY_VISIBLE_PREFIX_LENGTH] + "..."

    api_key = APIKey(
        org_id=org_id,
        user_id=user_id,
        name=body.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=list(body.scopes),
        expires_at=body.expires_at,
    )
    db.add(api_key)
    try:
        await db.flush()
        await write_audit_log(
            db,
            org_id=org_id,
            user_id=user_id,
            action="apikey.created",
            details={
                "key_id": str(api_key.id),
                "name": body.name,
                "key_prefix": key_prefix,
                "scopes": list(body.scopes),
                "expires_at": body.expires_at.isoformat(),
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(api_key)

    logger.info(
        "api_key_created",
        key_id=str(api_key.id),
        user_id=str(user_id),
        key_prefix=key_prefix,
        expires_at=body.expires_at.isoformat(),
        scopes=list(body.scopes),
    )
    return APIKeySecret(api_key=api_key, secret_key=key_raw)


async def list_api_keys_for_org(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    page: int,
    per_page: int,
) -> APIKeyPage:
    offset = (page - 1) * per_page
    total_result = await db.execute(
        select(func.count()).select_from(APIKey).where(APIKey.org_id == org_id)
    )
    total = total_result.scalar_one()

    result = await db.execute(
        select(APIKey)
        .where(APIKey.org_id == org_id)
        .order_by(APIKey.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    return APIKeyPage(items=list(result.scalars().all()), total=total)


async def revoke_api_key(
    db: AsyncSession,
    *,
    key_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
) -> None:
    result = await db.execute(
        select(APIKey).where(
            APIKey.id == key_id,
            APIKey.org_id == org_id,
        )
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise APIError(404, "Not Found", "API key not found")

    try:
        api_key.revoked = True
        await db.flush()

        await write_audit_log(
            db,
            org_id=org_id,
            user_id=user_id,
            action="apikey.revoked",
            details={
                "key_id": str(api_key.id),
                "name": api_key.name,
                "key_prefix": api_key.key_prefix,
            },
            request=request,
            fail_closed=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    logger.info("api_key_revoked", key_id=str(key_id), user_id=str(user_id))


async def authenticate_api_key(
    raw_key: str,
    db: AsyncSession,
    *,
    required_scope: APIKeyScope | str | None = None,
) -> APIKey | None:
    """Return the active APIKey row for *raw_key*, or None if invalid/revoked.

    This is the verification path that route middleware will call.  It
    recomputes the HMAC-SHA256 digest of the presented key and uses
    ``hmac.compare_digest()`` for the final comparison so that the check is
    constant-time and not subject to timing-oracle attacks.

    Lookup strategy:
    1. Reject tokens outside the strict ``prv_live_`` credential shape without
       hashing or touching the database.
    2. Bind the candidate HMAC digest as the RLS lookup capability and fetch
       the single non-revoked row for that exact digest.
    3. Compare the row's ``key_hash`` against the recomputed candidate hash
       using ``hmac.compare_digest()``.  This comparison is constant-time
       regardless of where the strings diverge.
    4. Reject rows that are expired or missing a required route scope.
    """
    if not is_namespaced_api_key(raw_key):
        logger.info("api_key_auth_failed", reason="invalid_shape")
        return None

    candidate_hash = _hash_key(raw_key)
    now = datetime.now(UTC)
    await db.execute(select(func.set_config("app.api_key_hash", candidate_hash, True)))

    result = await db.execute(
        select(APIKey).where(
            APIKey.key_hash == candidate_hash,
            APIKey.revoked.is_(False),
        )
    )
    rows = result.scalars().all()

    for api_key in rows:
        if hmac.compare_digest(api_key.key_hash, candidate_hash):
            expires_at = getattr(api_key, "expires_at", None)
            if expires_at is None or expires_at.tzinfo is None or expires_at.utcoffset() is None:
                logger.warning(
                    "api_key_auth_failed",
                    reason="missing_or_naive_expiry",
                    key_id=str(api_key.id),
                    org_id=str(api_key.org_id),
                )
                return None
            if expires_at <= now:
                logger.info(
                    "api_key_auth_failed",
                    reason="expired",
                    key_id=str(api_key.id),
                    org_id=str(api_key.org_id),
                )
                return None

            scopes = set(getattr(api_key, "scopes", []) or [])
            if required_scope is not None and required_scope not in scopes:
                logger.info(
                    "api_key_auth_failed",
                    reason="scope_missing",
                    key_id=str(api_key.id),
                    org_id=str(api_key.org_id),
                    required_scope=required_scope,
                )
                return None

            await bind_current_org_to_session(db, api_key.org_id)
            deletion_status = await db.scalar(
                select(Organization.deletion_status).where(Organization.id == api_key.org_id)
            )
            if deletion_status in _API_KEY_BLOCKED_DELETION_STATUSES:
                logger.warning(
                    "api_key_auth_failed",
                    reason="organization_erasure",
                    key_id=str(api_key.id),
                    org_id=str(api_key.org_id),
                    deletion_status=deletion_status,
                )
                return None
            api_key.last_used_at = now
            await db.flush()
            await db.commit()
            await bind_current_org_to_session(db, api_key.org_id)
            logger.info(
                "api_key_auth_ok",
                key_id=str(api_key.id),
                org_id=str(api_key.org_id),
                required_scope=required_scope,
            )
            return api_key

    logger.info("api_key_auth_failed", reason="not_found_or_revoked")
    return None
