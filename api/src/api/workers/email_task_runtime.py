"""Runtime helpers for email worker tasks."""

import atexit

_sync_engine = None


def get_sync_engine():
    """Return a cached sync engine for Celery email tasks."""
    global _sync_engine  # noqa: PLW0603
    if _sync_engine is None:
        from sqlalchemy import create_engine

        from api.config import get_settings

        settings = get_settings()
        sync_url = settings.database_url.replace("+asyncpg", "")
        _sync_engine = create_engine(
            sync_url,
            pool_size=3,
            max_overflow=settings.worker_db_max_overflow,
            pool_timeout=settings.worker_db_pool_timeout,
            pool_pre_ping=True,
            pool_recycle=3600,
            connect_args={
                "options": f"-c statement_timeout={settings.db_statement_timeout_ms}",
            },
        )
    return _sync_engine


def dispose_sync_engine() -> None:
    """Dispose the cached sync engine on process exit."""
    global _sync_engine  # noqa: PLW0603
    if _sync_engine is not None:
        _sync_engine.dispose()
        _sync_engine = None


async def send_email_async(coro_factory):
    """Execute an email send coroutine using the configured email client."""
    from api.services.email import get_email_client

    client = get_email_client()
    return await coro_factory(client)


atexit.register(dispose_sync_engine)
