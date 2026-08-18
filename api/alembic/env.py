"""Alembic environment configuration for async migrations."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from api.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Read the database URL directly from the environment so the migration job
# does not trigger full-application settings validation (Stripe, Sentry, etc.
# are irrelevant to schema migrations).
_db_url = os.environ.get("DATABASE_URL") or os.environ.get("BOOTSTRAP_DATABASE_URL")
if not _db_url:
    from api.config import get_settings

    _db_url = get_settings().database_url
config.set_main_option("sqlalchemy.url", _db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    # Switch to a migration role without BYPASSRLS in production so RLS policies
    # apply to the migration session. The role must exist in the target DB;
    # it is a no-op only in dev/test environments where the role may not exist.
    import logging

    alembic_logger = logging.getLogger("alembic.env")
    _app_env = os.environ.get("APP_ENV", "dev")
    if _app_env not in ("dev", "test"):
        try:
            connection.execute(text("SET ROLE alembic_runner"))
        except Exception as exc:
            alembic_logger.error(
                "alembic_runner_role_unavailable: %s. Refusing to run migrations "
                "without the expected migration role.",
                exc,
            )
            raise RuntimeError(
                "alembic_runner_role_unavailable: refusing to run migrations without SET ROLE"
            ) from exc
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
        await connection.commit()
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
