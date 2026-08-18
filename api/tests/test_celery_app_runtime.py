"""Behavioral tests for Celery worker initialization and async-loop ownership."""

from __future__ import annotations

import builtins
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import opentelemetry.instrumentation as otel_instrumentation
import pytest

from api import observability
from api.workers import celery_app


def test_worker_initialization_configures_and_instruments_otel(monkeypatch) -> None:
    configure = MagicMock()
    instrument = MagicMock()
    instrumentor = MagicMock(return_value=SimpleNamespace(instrument=instrument))
    monkeypatch.setattr(observability, "configure_otel", configure)
    celery_module = SimpleNamespace(CeleryInstrumentor=instrumentor)
    monkeypatch.setitem(sys.modules, "opentelemetry.instrumentation.celery", celery_module)
    monkeypatch.setattr(otel_instrumentation, "celery", celery_module, raising=False)

    celery_app._init_otel_in_worker()

    configure.assert_called_once_with(None, celery_app.settings)
    instrumentor.assert_called_once_with()
    instrument.assert_called_once_with()


def test_worker_initialization_stops_when_base_otel_configuration_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        observability,
        "configure_otel",
        MagicMock(side_effect=RuntimeError("collector unavailable")),
    )

    celery_app._init_otel_in_worker()


def test_worker_initialization_tolerates_missing_optional_celery_instrumentor(monkeypatch) -> None:
    monkeypatch.setattr(observability, "configure_otel", MagicMock())
    original_import = builtins.__import__

    def _import(name, *args, **kwargs):
        if name == "opentelemetry.instrumentation.celery":
            raise ImportError("optional instrumentation absent")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _import)

    celery_app._init_otel_in_worker()


def test_get_event_loop_creates_one_daemon_thread_and_reuses_it(monkeypatch) -> None:
    loop = MagicMock()
    loop.is_closed.return_value = False
    thread = SimpleNamespace(name="celery-asyncio-loop", ident=123, start=MagicMock())
    monkeypatch.setattr(celery_app, "_loop", None)
    monkeypatch.setattr(celery_app, "_thread", None)
    monkeypatch.setattr(celery_app.asyncio, "new_event_loop", lambda: loop)
    thread_factory = MagicMock(return_value=thread)
    monkeypatch.setattr(celery_app.threading, "Thread", thread_factory)

    first = celery_app._get_event_loop()
    second = celery_app._get_event_loop()

    assert first is loop
    assert second is loop
    thread_factory.assert_called_once_with(
        target=loop.run_forever,
        daemon=True,
        name="celery-asyncio-loop",
    )
    thread.start.assert_called_once_with()


def test_shutdown_event_loop_stops_joins_and_clears_owned_state(monkeypatch) -> None:
    loop = MagicMock()
    loop.is_closed.return_value = False
    thread = SimpleNamespace(join=MagicMock(), is_alive=MagicMock(return_value=False))
    monkeypatch.setattr(celery_app, "_loop", loop)
    monkeypatch.setattr(celery_app, "_thread", thread)

    celery_app._shutdown_event_loop()

    loop.call_soon_threadsafe.assert_called_once_with(loop.stop)
    thread.join.assert_called_once_with(timeout=10)
    loop.close.assert_called_once_with()
    assert celery_app._loop is None
    assert celery_app._thread is None


def test_shutdown_event_loop_records_join_timeout_but_still_closes(monkeypatch) -> None:
    loop = MagicMock()
    loop.is_closed.return_value = False
    thread = SimpleNamespace(join=MagicMock(), is_alive=MagicMock(return_value=True))
    log_error = MagicMock()
    monkeypatch.setattr(celery_app, "_loop", loop)
    monkeypatch.setattr(celery_app, "_thread", thread)
    monkeypatch.setattr(celery_app.logger, "error", log_error)

    celery_app._shutdown_event_loop()

    log_error.assert_called_once()
    loop.close.assert_called_once_with()
    assert celery_app._loop is None


def test_run_async_returns_result_from_persistent_loop(monkeypatch) -> None:
    async def _operation() -> str:
        return "done"

    operation = _operation()
    loop = MagicMock()
    future = MagicMock()
    future.result.return_value = "done"
    submit = MagicMock(return_value=future)
    monkeypatch.setattr(celery_app, "_get_event_loop", lambda: loop)
    monkeypatch.setattr(celery_app.asyncio, "run_coroutine_threadsafe", submit)

    try:
        assert celery_app.run_async(operation, timeout=5) == "done"
    finally:
        operation.close()

    submit.assert_called_once_with(operation, loop)
    future.result.assert_called_once_with(timeout=5)


def test_run_async_cancels_future_on_timeout(monkeypatch) -> None:
    async def _operation() -> None:
        return None

    operation = _operation()
    future = MagicMock()
    future.result.side_effect = TimeoutError
    monkeypatch.setattr(celery_app, "_get_event_loop", lambda: MagicMock())
    monkeypatch.setattr(
        celery_app.asyncio,
        "run_coroutine_threadsafe",
        MagicMock(return_value=future),
    )

    try:
        with pytest.raises(TimeoutError):
            celery_app.run_async(operation, timeout=0.1)
    finally:
        operation.close()

    future.cancel.assert_called_once_with()
