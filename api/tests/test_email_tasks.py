from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from api.workers import email_tasks
from api.workers.email_task_weekly import DIGEST_RECONCILIATION_RETRY_AFTER_SECONDS


def test_send_welcome_email_wrapper_delegates(monkeypatch):
    called = {}

    def _fake_helper(task, user_id):
        called["task"] = task
        called["user_id"] = user_id
        return {"status": "sent", "message_id": "welcome-1", "error": None}

    monkeypatch.setattr(email_tasks, "send_welcome_email_task", _fake_helper)

    result = email_tasks.send_welcome_email.run("user-1")

    assert called["user_id"] == "user-1"
    assert result == {
        "status": "sent",
        "message_id": "welcome-1",
        "error": None,
    }


def test_send_monitor_alert_email_wrapper_delegates(monkeypatch):
    called = {}

    def _fake_helper(task, user_id, monitor_id, alert_id, org_id):
        called["task"] = task
        called["user_id"] = user_id
        called["monitor_id"] = monitor_id
        called["alert_id"] = alert_id
        called["org_id"] = org_id
        return {"status": "sent", "message_id": "alert-1", "error": None}

    monkeypatch.setattr(email_tasks, "send_monitor_alert_email_task", _fake_helper)

    result = email_tasks.send_monitor_alert_email.run(
        "user-1",
        "monitor-1",
        "alert-1",
        "org-1",
    )

    assert called["user_id"] == "user-1"
    assert called["monitor_id"] == "monitor-1"
    assert called["alert_id"] == "alert-1"
    assert called["org_id"] == "org-1"
    assert result == {
        "status": "sent",
        "message_id": "alert-1",
        "error": None,
    }


def test_execute_monitor_alert_email_uses_terminal_task_adapter(monkeypatch):
    called = {}

    def _fake_helper(task, user_id, monitor_id, alert_id, org_id):
        called["task"] = task
        called["user_id"] = user_id
        called["monitor_id"] = monitor_id
        called["alert_id"] = alert_id
        called["org_id"] = org_id
        return {"status": "failed", "error": "smtp unavailable"}

    monkeypatch.setattr(email_tasks, "send_monitor_alert_email_task", _fake_helper)

    result = email_tasks.execute_monitor_alert_email(
        user_id="user-1",
        monitor_id="monitor-1",
        alert_id="alert-1",
        org_id="org-1",
    )

    assert isinstance(called["task"], email_tasks._TerminalEmailTask)
    assert called["user_id"] == "user-1"
    assert called["monitor_id"] == "monitor-1"
    assert called["alert_id"] == "alert-1"
    assert called["org_id"] == "org-1"
    assert result == {"status": "failed", "error": "smtp unavailable"}


def test_send_weekly_digest_wrapper_delegates(monkeypatch):
    called = {}

    def _fake_helper(task):
        called["task"] = task
        return {"status": "completed", "sent": 1, "errors": 0}

    monkeypatch.setattr(email_tasks, "send_weekly_digest_task", _fake_helper)

    result = email_tasks.send_weekly_digest.run()

    assert "task" in called
    assert result == {"status": "completed", "sent": 1, "errors": 0}


def test_send_weekly_digest_wrapper_retries_pending_reconciliation(monkeypatch):
    def _fake_helper(task):  # noqa: ARG001
        return {
            "status": "retry_later",
            "reason": "digest_delivery_reconciliation_pending",
            "retry_after_seconds": DIGEST_RECONCILIATION_RETRY_AFTER_SECONDS,
        }

    retry = MagicMock(side_effect=RuntimeError("retry scheduled"))
    monkeypatch.setattr(email_tasks, "send_weekly_digest_task", _fake_helper)
    monkeypatch.setattr(email_tasks.send_weekly_digest, "retry", retry)

    with pytest.raises(RuntimeError, match="retry scheduled"):
        email_tasks.send_weekly_digest.run()

    retry.assert_called_once_with(
        countdown=DIGEST_RECONCILIATION_RETRY_AFTER_SECONDS,
    )


def test_execute_weekly_digest_uses_terminal_task_adapter(monkeypatch):
    called = {}

    def _fake_helper(task):
        called["task"] = task
        return {"status": "completed", "sent": 1, "errors": 0}

    monkeypatch.setattr(email_tasks, "send_weekly_digest_task", _fake_helper)

    result = email_tasks.execute_weekly_digest()

    assert isinstance(called["task"], email_tasks._TerminalEmailTask)
    assert result == {"status": "completed", "sent": 1, "errors": 0}
