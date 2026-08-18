"""Live PostgreSQL canary for the privileged cross-tenant worker role.

The tenant suite proves the API role is NOBYPASSRLS. This separate suite proves
the scheduler's distinct worker credential is non-superuser BYPASSRLS and can
perform its intended cross-organization due-monitor discovery.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.services.monitor_runtime import load_due_monitor_refs
from api.workers.monitor_tasks import _assert_worker_has_bypassrls

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_WORKER_RLS_TESTS") != "1",
    reason="privileged worker RLS canary runs in the dedicated PostgreSQL CI job",
)


@pytest.mark.asyncio
async def test_worker_role_is_distinct_non_superuser_bypassrls_and_reads_due_monitors() -> None:
    database_url = os.environ["DATABASE_URL"]
    if not database_url.startswith("postgresql+asyncpg://"):
        pytest.fail("Worker RLS canary requires a real asyncpg PostgreSQL DATABASE_URL")

    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    monitor_a, monitor_b = uuid.uuid4(), uuid.uuid4()

    try:
        async with engine.begin() as conn:
            role = (
                await conn.execute(
                    text(
                        """
                        SELECT current_user, rolsuper, rolbypassrls
                        FROM pg_roles
                        WHERE rolname = current_user
                        """
                    )
                )
            ).one()
            assert role[0] == "praviar_worker"
            assert role[1] is False
            assert role[2] is True

            await conn.execute(
                text(
                    """
                    INSERT INTO organizations (id, clerk_org_id, name, slug)
                    VALUES
                      (:org_a, :clerk_a, 'Worker Canary Org A', :slug_a),
                      (:org_b, :clerk_b, 'Worker Canary Org B', :slug_b)
                    """
                ),
                {
                    "org_a": org_a,
                    "clerk_a": f"org_{org_a.hex}",
                    "slug_a": f"worker-canary-a-{org_a.hex}",
                    "org_b": org_b,
                    "clerk_b": f"org_{org_b.hex}",
                    "slug_b": f"worker-canary-b-{org_b.hex}",
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO users (id, clerk_user_id, org_id, email, full_name, role)
                    VALUES
                      (:user_a, :clerk_ua, :org_a, :email_a, 'Worker A', 'admin'),
                      (:user_b, :clerk_ub, :org_b, :email_b, 'Worker B', 'admin')
                    """
                ),
                {
                    "user_a": user_a,
                    "clerk_ua": f"user_{user_a.hex}",
                    "org_a": org_a,
                    "email_a": f"{user_a.hex}@worker-canary.test",
                    "user_b": user_b,
                    "clerk_ub": f"user_{user_b.hex}",
                    "org_b": org_b,
                    "email_b": f"{user_b.hex}@worker-canary.test",
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO monitors (
                        id, org_id, user_id,
                        compound_smiles, compound_name,
                        schedule, is_active,
                        jurisdiction_bundle, target_jurisdictions,
                        strategy_version, monitoring_strategy,
                        watch_targets, last_run_mode, last_run_status,
                        last_run_summary, last_patent_count,
                        cached_patent_ids, last_snapshot
                    ) VALUES
                      (
                        :monitor_a, :org_a, :user_a,
                        'C', 'Worker Canary A', 'weekly', true,
                        'custom', '[]'::jsonb, '2026-04-monitor-v1', '{}'::jsonb,
                        '[]'::jsonb, '', '', '', 0, '[]'::jsonb, '{}'::jsonb
                      ),
                      (
                        :monitor_b, :org_b, :user_b,
                        'CC', 'Worker Canary B', 'weekly', true,
                        'custom', '[]'::jsonb, '2026-04-monitor-v1', '{}'::jsonb,
                        '[]'::jsonb, '', '', '', 0, '[]'::jsonb, '{}'::jsonb
                      )
                    """
                ),
                {
                    "monitor_a": monitor_a,
                    "org_a": org_a,
                    "user_a": user_a,
                    "monitor_b": monitor_b,
                    "org_b": org_b,
                    "user_b": user_b,
                },
            )

        async with session_factory() as session, session.begin():
            await _assert_worker_has_bypassrls(session)
            due_refs = await load_due_monitor_refs(session)

        assert (monitor_a, org_a) in due_refs
        assert (monitor_b, org_b) in due_refs

    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM monitors WHERE id IN (:monitor_a, :monitor_b)"),
                {"monitor_a": monitor_a, "monitor_b": monitor_b},
            )
            await conn.execute(
                text("DELETE FROM users WHERE id IN (:user_a, :user_b)"),
                {"user_a": user_a, "user_b": user_b},
            )
            await conn.execute(
                text("DELETE FROM organizations WHERE id IN (:org_a, :org_b)"),
                {"org_a": org_a, "org_b": org_b},
            )
        await engine.dispose()
