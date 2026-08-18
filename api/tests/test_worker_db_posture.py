from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        database_url="postgresql+asyncpg://user:pass@localhost/db",
        worker_db_pool_size=7,
        worker_db_max_overflow=2,
        worker_db_pool_timeout=11.0,
        db_statement_timeout_ms=12345,
    )


def test_pipeline_worker_sync_engine_has_bounded_db_posture(monkeypatch) -> None:
    from api.workers import tasks

    tasks._sync_engine = None
    engine = MagicMock()
    create_engine = MagicMock(return_value=engine)
    monkeypatch.setattr("api.config.get_settings", lambda: _settings())

    with patch("sqlalchemy.create_engine", create_engine):
        assert tasks._get_sync_engine() is engine

    create_engine.assert_called_once()
    kwargs = create_engine.call_args.kwargs
    assert kwargs["pool_size"] == 7
    assert kwargs["max_overflow"] == 2
    assert kwargs["pool_timeout"] == 11.0
    assert kwargs["connect_args"]["options"] == "-c statement_timeout=12345"
    tasks._sync_engine = None


def test_email_worker_sync_engine_has_bounded_db_posture(monkeypatch) -> None:
    from api.workers import email_task_runtime

    email_task_runtime._sync_engine = None
    engine = MagicMock()
    create_engine = MagicMock(return_value=engine)
    monkeypatch.setattr("api.config.get_settings", lambda: _settings())

    with patch("sqlalchemy.create_engine", create_engine):
        assert email_task_runtime.get_sync_engine() is engine

    create_engine.assert_called_once()
    kwargs = create_engine.call_args.kwargs
    assert kwargs["max_overflow"] == 2
    assert kwargs["pool_timeout"] == 11.0
    assert kwargs["connect_args"]["options"] == "-c statement_timeout=12345"
    email_task_runtime._sync_engine = None
