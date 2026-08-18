"""Pool-leakage tests: app.current_org_id is reset on connection checkin.

Unit test: always runs, validates the handler function directly.
Integration test: requires RUN_POSTGRES_RLS_TESTS=1 and a live asyncpg DATABASE_URL.

Background: asyncpg task cancellation (SQLAlchemy #12099) can leave a connection
returned to the pool with app.current_org_id still set at session scope. Without the
checkin event handler, the next request would inherit a previous tenant's org_id.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

pytestmark_integration = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_RLS_TESTS") != "1",
    reason="pool-leakage integration tests run in the dedicated CI job (RUN_POSTGRES_RLS_TESTS=1)",
)


def test_checkin_handler_executes_reset() -> None:
    """Unit: checkin handler resets tenant and public-share GUCs."""
    from api.db.session import _reset_org_id_on_checkin

    cursor = MagicMock()
    dbapi_conn = MagicMock()
    dbapi_conn.cursor.return_value = cursor

    _reset_org_id_on_checkin(dbapi_conn, None)

    cursor.execute.assert_any_call("RESET app.current_org_id")
    cursor.execute.assert_any_call("RESET app.public_share_grant_hash")
    cursor.execute.assert_any_call("RESET app.api_key_hash")
    assert cursor.execute.call_count == 3
    cursor.close.assert_called_once()


@pytestmark_integration
@pytest.mark.asyncio
async def test_pool_org_id_is_reset_on_checkin() -> None:
    """Integration: org_id set at session scope is cleared when the connection returns to the pool.

    Uses pool_size=1 so the same physical connection is reused across two engine.connect()
    calls. The first connection sets app.current_org_id at session scope (not LOCAL),
    simulating the state left by an asyncpg task cancellation (SQLAlchemy #12099). After
    checkin the second connection must see an empty or default value, proving the registered
    pool event handler fired correctly — not just that the handler function works in isolation.
    """
    from sqlalchemy import event, text
    from sqlalchemy.ext.asyncio import create_async_engine

    from api.db.session import _reset_org_id_on_checkin

    database_url = os.environ["DATABASE_URL"]
    if not database_url.startswith("postgresql+asyncpg://"):
        pytest.skip("pool-leakage test requires a real asyncpg PostgreSQL DATABASE_URL")

    engine = create_async_engine(database_url, pool_size=1, max_overflow=0)
    # Register the production checkin handler on this test engine.
    event.listen(engine.sync_engine, "checkin", _reset_org_id_on_checkin)

    try:
        # Connection 1: set GUC at session scope, then return to pool.
        async with engine.connect() as conn:
            await conn.execute(text("SET app.current_org_id = 'leak-sentinel-org'"))
            result = await conn.execute(text("SHOW app.current_org_id"))
            assert result.scalar() == "leak-sentinel-org", "precondition: GUC should be set"
        # conn exits scope here — connection checks back into the pool; checkin event fires.

        # Connection 2: must see a cleared GUC (pool reuses the same physical connection).
        async with engine.connect() as conn2:
            result2 = await conn2.execute(text("SHOW app.current_org_id"))
            value = result2.scalar()
            assert value != "leak-sentinel-org", (
                f"Pool checkin event did not reset app.current_org_id; got '{value}'"
            )
    finally:
        await engine.dispose()
