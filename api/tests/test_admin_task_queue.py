from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from api.services.admin_health import (
    _inspect_celery_queue,
    get_task_queue_summary_impl,
    task_from_celery_payload,
)


def test_task_from_celery_payload_normalizes_missing_fields() -> None:
    task = task_from_celery_payload({"id": "job-1"}, status="active")

    assert task.id == "job-1"
    assert task.name == ""
    assert task.args == []
    assert task.status == "active"


def test_inspect_celery_queue_normalizes_active_reserved_and_scheduled() -> None:
    inspect = type(
        "Inspect",
        (),
        {
            "active": lambda self: {"worker-1": [{"id": "a1", "name": "task.active", "args": [1]}]},
            "reserved": lambda self: {
                "worker-1": [{"id": "r1", "name": "task.reserved", "args": [2]}]
            },
            "scheduled": lambda self: {"worker-1": [object(), object()]},
        },
    )()

    summary = _inspect_celery_queue(inspect=inspect)

    assert [task.id for task in summary.active] == ["a1"]
    assert summary.active[0].status == "active"
    assert [task.id for task in summary.reserved] == ["r1"]
    assert summary.reserved[0].status == "reserved"
    assert summary.scheduled_count == 2


def test_cloud_tasks_queue_summary_is_not_reported_as_local_celery_queue() -> None:
    settings = SimpleNamespace(
        pipeline_dispatch="cloud_tasks",
        gcp_project_id="praviar-prod",
        gcp_region="us-central1",
        cloud_tasks_queue_id="analysis-jobs",
        workers_service_url="https://workers.praviar.io",
        tasks_invoker_sa_email="tasks@praviar-prod.iam.gserviceaccount.com",
    )

    summary = get_task_queue_summary_impl(settings=settings)

    assert summary.backend == "cloud_tasks"
    assert summary.inspectable is False
    assert summary.active == []
    assert summary.reserved == []
    assert summary.scheduled_count == 0


def test_task_queue_error_does_not_disclose_exception_details(monkeypatch) -> None:
    secret = "redis://:password@internal-queue:6379/0"

    def _raise(timeout):
        del timeout
        raise RuntimeError(secret)

    fake_celery_app = SimpleNamespace(control=SimpleNamespace(inspect=_raise))
    monkeypatch.setattr("api.workers.celery_app.celery_app", fake_celery_app)

    with patch("api.services.admin_health.logger.warning") as warning:
        summary = get_task_queue_summary_impl(settings=SimpleNamespace(pipeline_dispatch="celery"))

    assert summary.detail == "Task queue inspection failed"
    assert secret not in summary.detail
    assert secret not in repr(warning.call_args)
    assert warning.call_args.kwargs["error_type"] == "RuntimeError"
