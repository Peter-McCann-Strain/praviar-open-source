from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

from api.workers import email_task_actions


class _FakeTask:
    MaxRetriesExceededError = RuntimeError

    def retry(self, exc):  # pragma: no cover - not expected in this test
        raise AssertionError(f"retry should not be called: {exc!r}")


class _FakeSession:
    def __init__(self, db):
        self._db = db

    def __enter__(self):
        return self._db

    def __exit__(self, exc_type, exc, tb):
        return False


def test_send_welcome_email_task_smoke(monkeypatch):
    user = SimpleNamespace(
        email="new.user@example.com",
        full_name="",
        welcome_email_sent_at=None,
    )
    fake_db = SimpleNamespace(
        get=lambda model, object_id, **kwargs: user if object_id == "user-1" else None,
        commit=lambda: None,
    )
    sent_payload = {}

    monkeypatch.setattr(email_task_actions, "Session", lambda engine: _FakeSession(fake_db))
    monkeypatch.setattr(email_task_actions, "get_sync_engine", lambda: object())

    async def _fake_send_email_async(coro_factory):
        class _Client:
            async def send_welcome(self, **kwargs):
                sent_payload.update(kwargs)
                return SimpleNamespace(success=True, message_id="welcome-1", error=None)

        return await coro_factory(_Client())

    monkeypatch.setattr(email_task_actions, "send_email_async", _fake_send_email_async)
    monkeypatch.setattr(email_task_actions, "run_async", lambda coro: asyncio.run(coro))

    result = email_task_actions.send_welcome_email_task(_FakeTask(), "user-1")

    assert sent_payload == {
        "user_email": "new.user@example.com",
        "user_name": "new.user@example.com",
        "role": "client",
    }
    assert result == {
        "status": "sent",
        "message_id": "welcome-1",
        "error": None,
    }


def test_send_analysis_complete_email_skips_cross_org_payload(monkeypatch):
    user = SimpleNamespace(
        email="attorney@example.com",
        full_name="Attorney",
        org_id=uuid.uuid4(),
    )
    analysis = SimpleNamespace(
        org_id=uuid.uuid4(),
        compound_name="Semaglutide",
        compound_input="semaglutide",
        overall_risk="high",
    )

    def _get(model, _object_id, **kwargs):
        return user if model.__name__ == "User" else analysis

    fake_db = SimpleNamespace(get=_get)
    monkeypatch.setattr(email_task_actions, "Session", lambda engine: _FakeSession(fake_db))
    monkeypatch.setattr(email_task_actions, "get_sync_engine", lambda: object())
    monkeypatch.setattr(email_task_actions, "bind_org_to_sync_session", lambda db, org_id: None)
    monkeypatch.setattr(
        email_task_actions,
        "run_async",
        lambda _coro: (_ for _ in ()).throw(AssertionError("email should not send")),
    )

    result = email_task_actions.send_analysis_complete_email_task(
        _FakeTask(),
        "user-1",
        "analysis-1",
    )

    assert result == {"status": "skipped", "reason": "tenant mismatch"}


def test_send_monitor_alert_email_skips_cross_org_payload(monkeypatch):
    user = SimpleNamespace(
        email="scientist@example.com",
        full_name="Scientist",
        org_id=uuid.uuid4(),
    )
    monitor = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        compound_name="Aspirin",
        compound_smiles="CC(=O)Oc1ccccc1C(O)=O",
    )
    alert = SimpleNamespace(monitor_id=monitor.id, new_patent_count=2)

    def _get(model, _object_id, **kwargs):
        return {
            "User": user,
            "Monitor": monitor,
            "MonitorAlert": alert,
        }[model.__name__]

    fake_db = SimpleNamespace(get=_get)
    monkeypatch.setattr(email_task_actions, "Session", lambda engine: _FakeSession(fake_db))
    monkeypatch.setattr(email_task_actions, "get_sync_engine", lambda: object())
    monkeypatch.setattr(email_task_actions, "bind_org_to_sync_session", lambda db, org_id: None)
    monkeypatch.setattr(
        email_task_actions,
        "run_async",
        lambda _coro: (_ for _ in ()).throw(AssertionError("email should not send")),
    )

    result = email_task_actions.send_monitor_alert_email_task(
        _FakeTask(),
        "user-1",
        "monitor-1",
        "alert-1",
        str(uuid.uuid4()),
    )

    assert result == {"status": "skipped", "reason": "tenant mismatch"}


def test_send_monitor_alert_email_skips_payload_org_mismatch(monkeypatch):
    org_id = uuid.uuid4()
    user = SimpleNamespace(
        email="scientist@example.com",
        full_name="Scientist",
        org_id=org_id,
    )
    monitor = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=org_id,
        compound_name="Aspirin",
        compound_smiles="CC(=O)Oc1ccccc1C(O)=O",
    )
    alert = SimpleNamespace(monitor_id=monitor.id, new_patent_count=2)

    def _get(model, _object_id, **kwargs):
        return {
            "User": user,
            "Monitor": monitor,
            "MonitorAlert": alert,
        }[model.__name__]

    fake_db = SimpleNamespace(get=_get)
    monkeypatch.setattr(email_task_actions, "Session", lambda engine: _FakeSession(fake_db))
    monkeypatch.setattr(email_task_actions, "get_sync_engine", lambda: object())
    monkeypatch.setattr(email_task_actions, "bind_org_to_sync_session", lambda db, org_id: None)
    monkeypatch.setattr(
        email_task_actions,
        "run_async",
        lambda _coro: (_ for _ in ()).throw(AssertionError("email should not send")),
    )

    result = email_task_actions.send_monitor_alert_email_task(
        _FakeTask(),
        "user-1",
        "monitor-1",
        "alert-1",
        str(uuid.uuid4()),
    )

    assert result == {"status": "skipped", "reason": "tenant mismatch"}


def test_send_monitor_alert_email_skips_alert_for_different_monitor(monkeypatch):
    org_id = uuid.uuid4()
    user = SimpleNamespace(
        email="scientist@example.com",
        full_name="Scientist",
        org_id=org_id,
    )
    monitor = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=org_id,
        compound_name="Aspirin",
        compound_smiles="CC(=O)Oc1ccccc1C(O)=O",
    )
    alert = SimpleNamespace(monitor_id=uuid.uuid4(), new_patent_count=2)

    def _get(model, _object_id, **kwargs):
        return {
            "User": user,
            "Monitor": monitor,
            "MonitorAlert": alert,
        }[model.__name__]

    fake_db = SimpleNamespace(get=_get)
    monkeypatch.setattr(email_task_actions, "Session", lambda engine: _FakeSession(fake_db))
    monkeypatch.setattr(email_task_actions, "get_sync_engine", lambda: object())
    monkeypatch.setattr(email_task_actions, "bind_org_to_sync_session", lambda db, org_id: None)
    monkeypatch.setattr(
        email_task_actions,
        "run_async",
        lambda _coro: (_ for _ in ()).throw(AssertionError("email should not send")),
    )

    result = email_task_actions.send_monitor_alert_email_task(
        _FakeTask(),
        "user-1",
        "monitor-1",
        "alert-1",
        str(org_id),
    )

    assert result == {"status": "skipped", "reason": "monitor alert mismatch"}


def test_retry_email_task_normalizes_failure(monkeypatch):
    events = []

    class _RetryTask:
        MaxRetriesExceededError = RuntimeError

        def retry(self, exc):
            events.append(str(exc))
            raise self.MaxRetriesExceededError()

    result = email_task_actions.retry_email_task(
        _RetryTask(),
        RuntimeError("boom"),
        failure_event="email_task_welcome_failed",
        max_retries_event="email_task_welcome_max_retries",
        log_kwargs={"user_id": "user-1"},
    )

    assert events == ["boom"]
    assert result == {"status": "failed", "error": "boom"}


def _install_fake_session(monkeypatch, fake_db):
    monkeypatch.setattr(email_task_actions, "Session", lambda engine: _FakeSession(fake_db))
    monkeypatch.setattr(email_task_actions, "get_sync_engine", lambda: object())
    monkeypatch.setattr(email_task_actions, "bind_org_to_sync_session", lambda db, org_id: None)


def test_analysis_complete_skips_missing_user(monkeypatch):
    fake_db = SimpleNamespace(get=lambda model, object_id, **kwargs: None)
    _install_fake_session(monkeypatch, fake_db)

    result = email_task_actions.send_analysis_complete_email_task(
        _FakeTask(), "missing-user", "analysis-1"
    )

    assert result == {"status": "skipped", "reason": "user or analysis not found"}


def test_analysis_complete_skips_missing_analysis(monkeypatch):
    user = SimpleNamespace(org_id=uuid.uuid4())

    def _get(model, object_id, **kwargs):
        return user if model.__name__ == "User" else None

    _install_fake_session(monkeypatch, SimpleNamespace(get=_get))

    result = email_task_actions.send_analysis_complete_email_task(
        _FakeTask(), "user-1", "missing-analysis"
    )

    assert result == {"status": "skipped", "reason": "user or analysis not found"}


def test_analysis_complete_skips_already_sent(monkeypatch):
    org_id = uuid.uuid4()
    user = SimpleNamespace(org_id=org_id)
    analysis = SimpleNamespace(org_id=org_id, completion_email_sent_at="earlier")

    def _get(model, object_id, **kwargs):
        return user if model.__name__ == "User" else analysis

    _install_fake_session(monkeypatch, SimpleNamespace(get=_get))

    result = email_task_actions.send_analysis_complete_email_task(
        _FakeTask(), "user-1", "analysis-1"
    )

    assert result == {"status": "skipped", "reason": "already_sent"}


def test_analysis_complete_sends_and_records_delivery(monkeypatch):
    org_id = uuid.uuid4()
    user = SimpleNamespace(org_id=org_id)
    analysis = SimpleNamespace(org_id=org_id, completion_email_sent_at=None)
    commits = []

    def _get(model, object_id, **kwargs):
        return user if model.__name__ == "User" else analysis

    fake_db = SimpleNamespace(get=_get, commit=lambda: commits.append("commit"))
    _install_fake_session(monkeypatch, fake_db)
    monkeypatch.setattr(
        email_task_actions,
        "build_analysis_complete_send_kwargs",
        lambda **kwargs: {"analysis_id": "analysis-1"},
    )

    async def _send_email(coro_factory):
        client = SimpleNamespace(
            send_analysis_complete=lambda **kwargs: asyncio.sleep(
                0,
                result=SimpleNamespace(success=True, message_id="analysis-mail", error=None),
            )
        )
        return await coro_factory(client)

    monkeypatch.setattr(email_task_actions, "send_email_async", _send_email)
    monkeypatch.setattr(email_task_actions, "run_async", asyncio.run)

    result = email_task_actions.send_analysis_complete_email_task(
        _FakeTask(), "user-1", "analysis-1"
    )

    assert result["status"] == "sent"
    assert result["message_id"] == "analysis-mail"
    assert analysis.completion_email_sent_at is not None
    assert commits == ["commit"]


def test_analysis_complete_normalizes_runtime_failure(monkeypatch):
    monkeypatch.setattr(email_task_actions, "get_sync_engine", lambda: object())
    monkeypatch.setattr(
        email_task_actions,
        "Session",
        lambda engine: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    monkeypatch.setattr(
        email_task_actions,
        "retry_email_task",
        lambda task, exc, **kwargs: {"status": "retried", "error": str(exc), **kwargs},
    )

    result = email_task_actions.send_analysis_complete_email_task(
        _FakeTask(), "user-1", "analysis-1"
    )

    assert result["status"] == "retried"
    assert result["error"] == "database unavailable"
    assert result["failure_event"] == "email_task_analysis_complete_failed"


def _monitor_entities(*, sent_at=None):
    org_id = uuid.uuid4()
    monitor = SimpleNamespace(id=uuid.uuid4(), org_id=org_id)
    return (
        org_id,
        SimpleNamespace(org_id=org_id),
        monitor,
        SimpleNamespace(monitor_id=monitor.id, email_sent_at=sent_at),
    )


def test_monitor_alert_skips_missing_data(monkeypatch):
    _install_fake_session(
        monkeypatch,
        SimpleNamespace(get=lambda model, object_id, **kwargs: None),
    )

    result = email_task_actions.send_monitor_alert_email_task(
        _FakeTask(), "user-1", "monitor-1", "alert-1", str(uuid.uuid4())
    )

    assert result == {"status": "skipped", "reason": "data not found"}


def test_monitor_alert_skips_already_sent(monkeypatch):
    org_id, user, monitor, alert = _monitor_entities(sent_at="earlier")

    def _get(model, object_id, **kwargs):
        return {"User": user, "Monitor": monitor, "MonitorAlert": alert}[model.__name__]

    _install_fake_session(monkeypatch, SimpleNamespace(get=_get))

    result = email_task_actions.send_monitor_alert_email_task(
        _FakeTask(), "user-1", "monitor-1", "alert-1", str(org_id)
    )

    assert result == {"status": "skipped", "reason": "already_sent"}


def test_monitor_alert_sends_and_records_delivery(monkeypatch):
    org_id, user, monitor, alert = _monitor_entities()
    commits = []

    def _get(model, object_id, **kwargs):
        return {"User": user, "Monitor": monitor, "MonitorAlert": alert}[model.__name__]

    _install_fake_session(
        monkeypatch,
        SimpleNamespace(get=_get, commit=lambda: commits.append("commit")),
    )
    monkeypatch.setattr(
        email_task_actions,
        "build_monitor_alert_send_kwargs",
        lambda **kwargs: {"monitor_id": "monitor-1"},
    )

    async def _send_email(coro_factory):
        client = SimpleNamespace(
            send_monitor_alert=lambda **kwargs: asyncio.sleep(
                0,
                result=SimpleNamespace(success=True, message_id="alert-mail", error=None),
            )
        )
        return await coro_factory(client)

    monkeypatch.setattr(email_task_actions, "send_email_async", _send_email)
    monkeypatch.setattr(email_task_actions, "run_async", asyncio.run)

    result = email_task_actions.send_monitor_alert_email_task(
        _FakeTask(), "user-1", "monitor-1", "alert-1", str(org_id)
    )

    assert result["status"] == "sent"
    assert alert.email_sent_at is not None
    assert commits == ["commit"]


def test_monitor_alert_normalizes_runtime_failure(monkeypatch):
    monkeypatch.setattr(email_task_actions, "get_sync_engine", lambda: object())
    monkeypatch.setattr(
        email_task_actions,
        "Session",
        lambda engine: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    monkeypatch.setattr(
        email_task_actions,
        "retry_email_task",
        lambda task, exc, **kwargs: {"status": "retried", "error": str(exc), **kwargs},
    )

    result = email_task_actions.send_monitor_alert_email_task(
        _FakeTask(), "user-1", "monitor-1", "alert-1", str(uuid.uuid4())
    )

    assert result["status"] == "retried"
    assert result["failure_event"] == "email_task_monitor_alert_failed"


def test_welcome_skips_missing_and_already_sent_users(monkeypatch):
    _install_fake_session(
        monkeypatch,
        SimpleNamespace(get=lambda model, object_id, **kwargs: None),
    )
    assert email_task_actions.send_welcome_email_task(_FakeTask(), "missing") == {
        "status": "skipped",
        "reason": "user not found",
    }

    user = SimpleNamespace(welcome_email_sent_at="earlier")
    _install_fake_session(
        monkeypatch,
        SimpleNamespace(get=lambda model, object_id, **kwargs: user),
    )
    assert email_task_actions.send_welcome_email_task(_FakeTask(), "user-1") == {
        "status": "skipped",
        "reason": "already_sent",
    }


def test_welcome_normalizes_runtime_failure(monkeypatch):
    monkeypatch.setattr(email_task_actions, "get_sync_engine", lambda: object())
    monkeypatch.setattr(
        email_task_actions,
        "Session",
        lambda engine: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    monkeypatch.setattr(
        email_task_actions,
        "retry_email_task",
        lambda task, exc, **kwargs: {"status": "retried", "error": str(exc), **kwargs},
    )

    result = email_task_actions.send_welcome_email_task(_FakeTask(), "user-1")

    assert result["status"] == "retried"
    assert result["failure_event"] == "email_task_welcome_failed"
