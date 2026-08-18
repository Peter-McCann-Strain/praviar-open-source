"""Async SQLAlchemy engine and session factory.

Multi-tenant Row-Level Security (RLS):
    The RLS migrations apply an `org_isolation` policy to every reviewed
    direct org-scoped runtime table. The policy reads the per-session setting
    `app.current_org_id` and restricts row visibility to matching rows. When
    unset, the policy evaluates falsey — sessions without an org context see
    zero rows.

    A per-request ContextVar holds the active org_id; the auth middleware
    (Clerk) populates it after resolving the JWT. `get_db()` consults the
    ContextVar and binds `app.current_org_id` on the
    fresh session. Worker tasks should carry the relevant org_id and bind it
    before their first tenant read. Paths that cannot know an org before lookup
    (for example public share-token lookup) must be explicitly reviewed as
    service-account paths rather than accidentally relying on BYPASSRLS.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

import structlog
from sqlalchemy import event, func, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session as SyncSession
from sqlalchemy.orm import SessionTransaction

from api.config import get_settings

logger = structlog.get_logger()

# Per-request org_id, set by auth middleware after Clerk resolves the JWT.
# When None, `get_db()` skips the RLS tenant binding and the session sees zero
# rows on org-scoped tables (intended fail-closed behavior).
_current_org_id: ContextVar[str | None] = ContextVar("praviar_current_org_id", default=None)


def set_current_org_id(org_id: str | uuid.UUID | None) -> None:
    """Set the org_id for the current request context.

    Called by the Clerk auth middleware once the JWT has resolved to an org.
    Idempotent within a request.
    """
    _current_org_id.set(str(org_id) if org_id is not None else None)


def get_current_org_id() -> str | None:
    """Return the org_id currently bound to this request context, or None."""
    return _current_org_id.get()


async def bind_current_org_to_session(
    session: AsyncSession,
    org_id: str | uuid.UUID | None,
) -> None:
    """Bind tenant context to an already-open async session.

    FastAPI creates the DB dependency before auth resolves the user. That means
    the first transaction may already exist by the time we know `org_id`.
    Calling this immediately after auth both sets the request ContextVar for
    future transactions and applies the transaction-local setting to the active
    transaction.
    """
    set_current_org_id(org_id)
    if org_id is None:
        return
    await session.execute(select(func.set_config("app.current_org_id", str(org_id), True)))


async def bind_public_share_grant_hash_to_session(
    session: AsyncSession,
    grant_hash: str | None,
) -> None:
    """Bind a one-way public grant-token digest for the current transaction."""
    if grant_hash is None:
        return
    await session.execute(select(func.set_config("app.public_share_grant_hash", grant_hash, True)))


def bind_org_to_sync_session(
    session: SyncSession,
    org_id: str | uuid.UUID | None,
) -> None:
    """Bind tenant context to an already-open sync session."""
    if org_id is None:
        session.info.pop("rls_org_id", None)
        return
    org_id_value = str(org_id)
    session.info["rls_org_id"] = org_id_value
    session.execute(select(func.set_config("app.current_org_id", org_id_value, True)))


@event.listens_for(SyncSession, "after_begin")
def _set_rls_context_after_begin(
    session: SyncSession,
    _transaction: SessionTransaction,
    connection: Connection,
) -> None:
    """Apply tenant context to every new SQLAlchemy transaction."""
    org_id = session.info.get("rls_org_id") or _current_org_id.get()
    if org_id is None:
        return
    connection.execute(select(func.set_config("app.current_org_id", str(org_id), True)))


def _reset_org_id_on_checkin(dbapi_connection: Any, _connection_record: Any) -> None:
    """Pool checkin: clear app.current_org_id before the connection returns to the pool.

    Guards against the asyncpg task-cancellation leak (SQLAlchemy #12099).
    A cancelled query can leave a connection with app.current_org_id still set at session
    scope. Without this reset, the next request could inherit a previous tenant's org_id.

    Wraps the RESET in try/except because SQLAlchemy may pass an invalidated DBAPI
    connection (e.g., after a network error). Allowing this handler to raise would prevent
    the connection from being returned to the pool and would cause a pool leak.
    """
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("RESET app.current_org_id")
        cursor.execute("RESET app.public_share_grant_hash")
        cursor.execute("RESET app.api_key_hash")
        cursor.close()
    except Exception:
        logger.warning("rls_checkin_reset_failed", exc_info=True)


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_engine() -> AsyncEngine:
    settings = get_settings()
    eng = create_async_engine(
        settings.database_url,
        echo=bool(settings.debug),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_pre_ping=True,
        pool_recycle=settings.db_pool_recycle,
        connect_args={
            "server_settings": {"statement_timeout": str(settings.db_statement_timeout_ms)},
            "command_timeout": settings.db_command_timeout,
        },
    )
    event.listen(eng.sync_engine, "checkin", _reset_org_id_on_checkin)
    return eng


def get_engine() -> AsyncEngine:
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory  # noqa: PLW0603
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def dispose_engine() -> None:
    global _engine, _session_factory  # noqa: PLW0603
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


class _LazyEngineProxy:
    def __getattr__(self, attr: str) -> Any:
        return getattr(get_engine(), attr)

    async def dispose(self) -> None:
        await dispose_engine()


class _LazySessionFactory:
    def __call__(self, *args: Any, **kwargs: Any) -> AsyncSession:
        return get_async_session_factory()(*args, **kwargs)


engine = _LazyEngineProxy()
async_session_factory = _LazySessionFactory()


@asynccontextmanager
async def pinned_advisory_lock(lock_key: int) -> AsyncIterator[bool]:
    """Acquire a pg_advisory_lock on a dedicated, pinned connection.

    pg_advisory_lock is session-level and bound to the DBAPI connection, not
    to an SQLAlchemy session or transaction. When a session commits, asyncpg
    returns the connection to the pool; any subsequent advisory_unlock call runs
    on a *different* pooled connection and is a silent no-op — leaving the lock
    permanently wedged on the first connection until it is recycled.

    This context manager checks out one dedicated connection and never commits
    it, so the advisory lock lives exactly as long as the ``async with`` block,
    regardless of how many commits the caller's main session makes.

    Yields True if the lock was acquired, False if another session holds it.
    """
    async with get_engine().connect() as conn:
        result = await conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key})
        acquired = bool(result.scalar())
        try:
            yield acquired
        finally:
            if acquired:
                await conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})


async def get_db() -> AsyncGenerator[AsyncSession]:
    """Dependency: yield an async DB session.

    Request handlers own transaction boundaries explicitly. This dependency only
    guarantees rollback-on-error and cleanup, plus RLS org-isolation when the
    current request context has an org_id bound.
    """
    async with async_session_factory() as session:
        try:
            # RLS: bind app.current_org_id for the lifetime of this transaction
            # so the org_isolation policy on org-scoped tables resolves correctly.
            # Sessions without a bound org_id see zero rows on protected tables.
            org_id = _current_org_id.get()
            if org_id is not None:
                await bind_current_org_to_session(session, org_id)
            yield session
        except Exception:
            logger.error("db_session_rollback", exc_info=True)
            await session.rollback()
            raise
        finally:
            set_current_org_id(None)
