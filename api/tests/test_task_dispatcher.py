"""Task dispatcher contract tests."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from api.config import APISettings
from api.services import task_dispatcher
from api.services.task_dispatcher import CLOUD_TASK_DISPATCH_DEADLINE_SECONDS
from api.workers.email_task_weekly import DIGEST_RECONCILIATION_RETRY_AFTER_SECONDS
from api.workers.task_exports import (
    EXPORT_PROCESSING_LEASE_BUFFER_SECONDS,
    MAX_EXPORT_RETRYABLE_FAILURE_ATTEMPTS,
    MIN_EXPORT_PROCESSING_LEASE_SECONDS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TERRAFORM_DURATION_RE = re.compile(r'^"?(\d+)s"?$')


class _FakeHttpMethod:
    POST = "POST"


class _FakeHttpRequest:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeOidcToken:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeTask:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeDuration:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeCreateTaskRequest:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeCloudTasksClient:
    def __init__(self, *, duplicate: bool = False) -> None:
        self.duplicate = duplicate
        self.requests = []

    def queue_path(self, project_id: str, region: str, queue_id: str) -> str:
        return f"projects/{project_id}/locations/{region}/queues/{queue_id}"

    def create_task(self, *, request):
        self.requests.append(request)
        if self.duplicate:
            raise AlreadyExists("task already exists")
        return SimpleNamespace(name=request.task.name)


class AlreadyExists(Exception):  # noqa: N818 - mirrors google.api_core.exceptions.AlreadyExists
    pass


def _install_fake_cloud_tasks(
    monkeypatch: pytest.MonkeyPatch, client: _FakeCloudTasksClient
) -> None:
    fake_tasks_v2 = ModuleType("google.cloud.tasks_v2")
    fake_tasks_v2.CloudTasksClient = lambda: client  # type: ignore[attr-defined]
    fake_tasks_v2.CreateTaskRequest = _FakeCreateTaskRequest  # type: ignore[attr-defined]
    fake_tasks_v2.HttpMethod = _FakeHttpMethod  # type: ignore[attr-defined]
    fake_tasks_v2.HttpRequest = _FakeHttpRequest  # type: ignore[attr-defined]
    fake_tasks_v2.OidcToken = _FakeOidcToken  # type: ignore[attr-defined]
    fake_tasks_v2.Task = _FakeTask  # type: ignore[attr-defined]
    fake_protobuf = ModuleType("google.protobuf")
    fake_duration_pb2 = ModuleType("google.protobuf.duration_pb2")
    fake_duration_pb2.Duration = _FakeDuration  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", ModuleType("google"))
    monkeypatch.setitem(sys.modules, "google.cloud", ModuleType("google.cloud"))
    monkeypatch.setitem(sys.modules, "google.cloud.tasks_v2", fake_tasks_v2)
    monkeypatch.setitem(sys.modules, "google.protobuf", fake_protobuf)
    monkeypatch.setitem(sys.modules, "google.protobuf.duration_pb2", fake_duration_pb2)


def _active_terraform_source(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(re.split(r"\s*(?:#|//)", line, maxsplit=1)[0] for line in source.splitlines())


def _read_active_terraform_block_assignments(source: str, block_name: str) -> dict[str, str]:
    source = _active_terraform_source(source)
    block_match = re.search(rf"\b{re.escape(block_name)}\s*\{{", source)
    if block_match is None:
        raise AssertionError(f"{block_name} block is missing")

    assignments: dict[str, str] = {}
    depth = 1
    for line in source[block_match.end() :].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        depth += stripped.count("{")
        depth -= stripped.count("}")
        if depth <= 0:
            return assignments
        assignment_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$", stripped)
        if assignment_match:
            assignments[assignment_match.group(1)] = assignment_match.group(2).strip()

    raise AssertionError(f"{block_name} block is not closed")


def _terraform_duration_seconds(value: str) -> int:
    duration_match = TERRAFORM_DURATION_RE.match(value)
    if duration_match is None:
        raise AssertionError(f"Unsupported Terraform duration literal: {value}")
    return int(duration_match.group(1))


def _retry_elapsed_seconds(
    *, max_attempts: int, min_backoff: int, max_backoff: int, max_doublings: int
) -> list[int]:
    elapsed = 0
    schedule = []
    for retry_index in range(max(0, max_attempts - 1)):
        delay = min_backoff * (2**retry_index) if retry_index < max_doublings else max_backoff
        elapsed += min(delay, max_backoff)
        schedule.append(elapsed)
    return schedule


def test_terraform_retry_config_parser_ignores_commented_values():
    retry_config = _read_active_terraform_block_assignments(
        """
        # retry_config {
        #   max_attempts = 3
        # }
        retry_config {
          # max_attempts = 3
          max_attempts = 15 # old max_attempts = 3
          /* max_retry_duration = "120s" */
          max_retry_duration = "3600s"
        }
        """,
        "retry_config",
    )

    assert retry_config["max_attempts"] == "15"
    assert retry_config["max_retry_duration"] == '"3600s"'


def test_export_cloud_tasks_retry_policy_covers_worker_retry_contract():
    terraform_source = (REPO_ROOT / "infra/terraform/modules/cloud_tasks/main.tf").read_text(
        encoding="utf-8"
    )
    retry_config = _read_active_terraform_block_assignments(
        terraform_source,
        "retry_config",
    )
    max_attempts = int(retry_config["max_attempts"])
    retry_window_seconds = _terraform_duration_seconds(retry_config["max_retry_duration"])
    worker_hard_limit_seconds = int(APISettings.model_fields["celery_hard_time_limit"].default)
    worker_processing_lease_seconds = (
        max(worker_hard_limit_seconds, MIN_EXPORT_PROCESSING_LEASE_SECONDS)
        + EXPORT_PROCESSING_LEASE_BUFFER_SECONDS
    )
    retry_schedule_seconds = _retry_elapsed_seconds(
        max_attempts=max_attempts,
        min_backoff=_terraform_duration_seconds(retry_config["min_backoff"]),
        max_backoff=_terraform_duration_seconds(retry_config["max_backoff"]),
        max_doublings=int(retry_config["max_doublings"]),
    )

    assert max_attempts >= MAX_EXPORT_RETRYABLE_FAILURE_ATTEMPTS
    assert retry_window_seconds >= worker_processing_lease_seconds
    assert retry_window_seconds >= CLOUD_TASK_DISPATCH_DEADLINE_SECONDS
    assert any(elapsed >= worker_processing_lease_seconds for elapsed in retry_schedule_seconds)


def test_weekly_digest_cloud_tasks_retry_policy_covers_reconciliation_delay():
    terraform_source = (REPO_ROOT / "infra/terraform/modules/cloud_tasks/main.tf").read_text(
        encoding="utf-8"
    )
    retry_config = _read_active_terraform_block_assignments(
        terraform_source,
        "retry_config",
    )
    retry_window_seconds = _terraform_duration_seconds(retry_config["max_retry_duration"])
    retry_schedule_seconds = _retry_elapsed_seconds(
        max_attempts=int(retry_config["max_attempts"]),
        min_backoff=_terraform_duration_seconds(retry_config["min_backoff"]),
        max_backoff=_terraform_duration_seconds(retry_config["max_backoff"]),
        max_doublings=int(retry_config["max_doublings"]),
    )

    assert retry_window_seconds >= DIGEST_RECONCILIATION_RETRY_AFTER_SECONDS
    assert any(
        elapsed >= DIGEST_RECONCILIATION_RETRY_AFTER_SECONDS for elapsed in retry_schedule_seconds
    )


@pytest.mark.asyncio
async def test_celery_dispatcher_uses_pipeline_task(monkeypatch: pytest.MonkeyPatch):
    task = MagicMock()
    task.delay.return_value = SimpleNamespace(id="celery-123")
    monkeypatch.setattr(
        "api.workers.tasks.run_fto_pipeline",
        task,
    )

    task_id = await task_dispatcher.CeleryDispatcher().dispatch_pipeline_run(
        analysis_id="analysis-1",
        org_id="org-1",
    )

    assert task_id == "celery-123"
    task.delay.assert_called_once_with("analysis-1", org_id="org-1")


@pytest.mark.asyncio
async def test_celery_dispatcher_forwards_pipeline_org_context(
    monkeypatch: pytest.MonkeyPatch,
):
    task = MagicMock()
    task.delay.return_value = SimpleNamespace(id="celery-123")
    monkeypatch.setattr(
        "api.workers.tasks.run_fto_pipeline",
        task,
    )

    task_id = await task_dispatcher.CeleryDispatcher().dispatch_pipeline_run(
        analysis_id="analysis-1",
        org_id="org-1",
    )

    assert task_id == "celery-123"
    task.delay.assert_called_once_with("analysis-1", org_id="org-1")


@pytest.mark.asyncio
async def test_celery_dispatcher_uses_export_task(monkeypatch: pytest.MonkeyPatch):
    task = MagicMock()
    task.delay.return_value = SimpleNamespace(id="celery-export-123")
    monkeypatch.setattr(
        "api.workers.tasks.run_export",
        task,
    )

    task_id = await task_dispatcher.CeleryDispatcher().dispatch_export_job(
        export_job_id="export-1",
        org_id="org-1",
    )

    assert task_id == "celery-export-123"
    task.delay.assert_called_once_with("export-1", org_id="org-1")


@pytest.mark.asyncio
async def test_celery_dispatcher_uses_faithfulness_task(monkeypatch: pytest.MonkeyPatch):
    task = MagicMock()
    task.delay.return_value = SimpleNamespace(id="celery-faithfulness-123")
    monkeypatch.setattr(
        "api.workers.tasks.compute_faithfulness_scores",
        task,
    )

    task_id = await task_dispatcher.CeleryDispatcher().dispatch_faithfulness_scores(
        analysis_id="analysis-1",
        org_id="org-1",
    )

    assert task_id == "celery-faithfulness-123"
    task.delay.assert_called_once_with("analysis-1", org_id="org-1")


@pytest.mark.asyncio
async def test_celery_dispatcher_uses_monitor_scan_task(monkeypatch: pytest.MonkeyPatch):
    task = MagicMock()
    task.delay.return_value = SimpleNamespace(id="celery-monitor-123")
    monkeypatch.setattr(
        "api.workers.monitor_tasks.run_monitor_scan",
        task,
    )

    task_id = await task_dispatcher.CeleryDispatcher().dispatch_monitor_scan(
        monitor_id="monitor-1",
        org_id="org-1",
        force_full_refresh=True,
        dedupe_key="ignored-by-celery",
    )

    assert task_id == "celery-monitor-123"
    task.delay.assert_called_once_with("monitor-1", org_id="org-1", force_full_refresh=True)


@pytest.mark.asyncio
async def test_celery_dispatcher_uses_monitor_alert_email_task(
    monkeypatch: pytest.MonkeyPatch,
):
    task = MagicMock()
    task.delay.return_value = SimpleNamespace(id="celery-monitor-alert-123")
    monkeypatch.setattr(
        "api.workers.email_tasks.send_monitor_alert_email",
        task,
    )

    task_id = await task_dispatcher.CeleryDispatcher().dispatch_monitor_alert_email(
        user_id="user-1",
        monitor_id="monitor-1",
        alert_id="alert-1",
        org_id="org-1",
    )

    assert task_id == "celery-monitor-alert-123"
    task.delay.assert_called_once_with("user-1", "monitor-1", "alert-1", org_id="org-1")


@pytest.mark.asyncio
async def test_celery_dispatcher_uses_weekly_digest_task(monkeypatch: pytest.MonkeyPatch):
    task = MagicMock()
    task.delay.return_value = SimpleNamespace(id="celery-weekly-digest-123")
    monkeypatch.setattr(
        "api.workers.email_tasks.send_weekly_digest",
        task,
    )

    task_id = await task_dispatcher.CeleryDispatcher().dispatch_weekly_digest(
        dedupe_key="2026-W23",
    )

    assert task_id == "celery-weekly-digest-123"
    task.delay.assert_called_once_with()


def test_cloud_tasks_dispatcher_requires_prod_contract(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        task_dispatcher,
        "get_settings",
        lambda: SimpleNamespace(
            pipeline_dispatch="cloud_tasks",
            gcp_project_id="",
            gcp_region="us-central1",
            cloud_tasks_queue_id="",
            workers_service_url="",
            tasks_invoker_sa_email="",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        "api.config.get_settings",
        lambda: SimpleNamespace(
            pipeline_dispatch="cloud_tasks",
            gcp_project_id="",
            gcp_region="us-central1",
            cloud_tasks_queue_id="",
            workers_service_url="",
            tasks_invoker_sa_email="",
        ),
    )

    with pytest.raises(RuntimeError, match="Cloud Tasks dispatch"):
        task_dispatcher.build_dispatcher()


def test_build_dispatcher_rejects_prod_celery(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "api.config.get_settings",
        lambda: SimpleNamespace(pipeline_dispatch="celery", app_env="prod"),
    )

    with pytest.raises(RuntimeError, match="Celery dispatch is not permitted"):
        task_dispatcher.build_dispatcher()


def test_build_dispatcher_rejects_unknown_backend(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "api.config.get_settings",
        lambda: SimpleNamespace(pipeline_dispatch="sidecar", app_env="test"),
    )

    with pytest.raises(RuntimeError, match="Unsupported PIPELINE_DISPATCH"):
        task_dispatcher.build_dispatcher()


@pytest.mark.asyncio
async def test_cloud_tasks_dispatcher_uses_deterministic_task_name(
    monkeypatch: pytest.MonkeyPatch,
):
    client = _FakeCloudTasksClient()
    _install_fake_cloud_tasks(monkeypatch, client)
    dispatcher = task_dispatcher.CloudTasksDispatcher(
        project_id="project-1",
        region="us-central1",
        queue_id="pipeline",
        workers_url="https://workers.example.com/",
        invoker_service_account_email="tasks@example.iam.gserviceaccount.com",
    )

    task_id = await dispatcher.dispatch_pipeline_run(
        analysis_id="analysis-1",
        org_id="org-1",
    )

    expected_name = (
        "projects/project-1/locations/us-central1/queues/pipeline/tasks/pipeline-analysis-1"
    )
    assert task_id == expected_name
    assert client.requests[0].task.name == expected_name
    request = client.requests[0].task.http_request
    assert request.url == "https://workers.example.com/internal/run-pipeline"
    assert request.oidc_token.audience == "https://workers.example.com"
    assert json.loads(request.body.decode()) == {"analysis_id": "analysis-1", "org_id": "org-1"}
    assert (
        client.requests[0].task.dispatch_deadline.seconds
        == task_dispatcher.PIPELINE_LAUNCH_DISPATCH_DEADLINE_SECONDS
    )
    assert task_dispatcher.CLOUD_TASK_DISPATCH_DEADLINE_SECONDS <= 30 * 60
    assert task_dispatcher.PIPELINE_LAUNCH_DISPATCH_DEADLINE_SECONDS >= 15


@pytest.mark.asyncio
async def test_cloud_tasks_dispatcher_forwards_pipeline_org_context(
    monkeypatch: pytest.MonkeyPatch,
):
    client = _FakeCloudTasksClient()
    _install_fake_cloud_tasks(monkeypatch, client)
    dispatcher = task_dispatcher.CloudTasksDispatcher(
        project_id="project-1",
        region="us-central1",
        queue_id="pipeline",
        workers_url="https://workers.example.com/",
        invoker_service_account_email="tasks@example.iam.gserviceaccount.com",
    )

    await dispatcher.dispatch_pipeline_run(analysis_id="analysis-1", org_id="org-1")

    request = client.requests[0].task.http_request
    assert json.loads(request.body.decode()) == {
        "analysis_id": "analysis-1",
        "org_id": "org-1",
    }


@pytest.mark.asyncio
async def test_cloud_tasks_pipeline_reconciliation_uses_fresh_task_generation(
    monkeypatch: pytest.MonkeyPatch,
):
    client = _FakeCloudTasksClient()
    _install_fake_cloud_tasks(monkeypatch, client)
    dispatcher = task_dispatcher.CloudTasksDispatcher(
        project_id="project-1",
        region="us-central1",
        queue_id="pipeline",
        workers_url="https://workers.example.com/",
        invoker_service_account_email="tasks@example.iam.gserviceaccount.com",
    )

    task_id = await dispatcher.dispatch_pipeline_run(
        analysis_id="analysis-1",
        org_id="org-1",
        reconciliation_key="stale-0123456789abcdef",  # gitleaks:allow
    )

    expected_name = (
        "projects/project-1/locations/us-central1/queues/pipeline/tasks/"
        "pipeline-analysis-1-reconcile-stale-0123456789abcdef"
    )
    assert task_id == expected_name
    assert client.requests[0].task.name == expected_name
    assert json.loads(client.requests[0].task.http_request.body.decode()) == {
        "analysis_id": "analysis-1",
        "org_id": "org-1",
    }


@pytest.mark.asyncio
async def test_cloud_tasks_pipeline_reconciliation_rejects_unsafe_task_key(
    monkeypatch: pytest.MonkeyPatch,
):
    client = _FakeCloudTasksClient()
    _install_fake_cloud_tasks(monkeypatch, client)
    dispatcher = task_dispatcher.CloudTasksDispatcher(
        project_id="project-1",
        region="us-central1",
        queue_id="pipeline",
        workers_url="https://workers.example.com/",
        invoker_service_account_email="tasks@example.iam.gserviceaccount.com",
    )

    with pytest.raises(ValueError, match="reconciliation key"):
        await dispatcher.dispatch_pipeline_run(
            analysis_id="analysis-1",
            org_id="org-1",
            reconciliation_key="../unsafe",
        )

    assert client.requests == []


@pytest.mark.asyncio
async def test_cloud_tasks_dispatcher_dispatches_export_job(
    monkeypatch: pytest.MonkeyPatch,
):
    client = _FakeCloudTasksClient()
    _install_fake_cloud_tasks(monkeypatch, client)
    dispatcher = task_dispatcher.CloudTasksDispatcher(
        project_id="project-1",
        region="us-central1",
        queue_id="pipeline",
        workers_url="https://workers.example.com/",
        invoker_service_account_email="tasks@example.iam.gserviceaccount.com",
    )

    task_id = await dispatcher.dispatch_export_job(export_job_id="export-1", org_id="org-1")

    expected_name = "projects/project-1/locations/us-central1/queues/pipeline/tasks/export-export-1"
    assert task_id == expected_name
    assert client.requests[0].task.name == expected_name
    request = client.requests[0].task.http_request
    assert request.url == "https://workers.example.com/internal/run-export"
    assert request.oidc_token.audience == "https://workers.example.com"
    assert json.loads(request.body.decode()) == {"export_job_id": "export-1", "org_id": "org-1"}


@pytest.mark.asyncio
async def test_cloud_tasks_dispatcher_dispatches_faithfulness_scoring(
    monkeypatch: pytest.MonkeyPatch,
):
    client = _FakeCloudTasksClient()
    _install_fake_cloud_tasks(monkeypatch, client)
    dispatcher = task_dispatcher.CloudTasksDispatcher(
        project_id="project-1",
        region="us-central1",
        queue_id="pipeline",
        workers_url="https://workers.example.com/",
        invoker_service_account_email="tasks@example.iam.gserviceaccount.com",
    )

    task_id = await dispatcher.dispatch_faithfulness_scores(
        analysis_id="analysis-1",
        org_id="org-1",
    )

    expected_name = (
        "projects/project-1/locations/us-central1/queues/pipeline/tasks/faithfulness-analysis-1"
    )
    assert task_id == expected_name
    assert client.requests[0].task.name == expected_name
    request = client.requests[0].task.http_request
    assert request.url == "https://workers.example.com/internal/run-faithfulness"
    assert request.oidc_token.audience == "https://workers.example.com"
    assert json.loads(request.body.decode()) == {"analysis_id": "analysis-1", "org_id": "org-1"}


@pytest.mark.asyncio
async def test_cloud_tasks_dispatcher_dispatches_monitor_scan(
    monkeypatch: pytest.MonkeyPatch,
):
    client = _FakeCloudTasksClient()
    _install_fake_cloud_tasks(monkeypatch, client)
    dispatcher = task_dispatcher.CloudTasksDispatcher(
        project_id="project-1",
        region="us-central1",
        queue_id="pipeline",
        workers_url="https://workers.example.com/",
        invoker_service_account_email="tasks@example.iam.gserviceaccount.com",
    )

    task_id = await dispatcher.dispatch_monitor_scan(
        monitor_id="monitor-1",
        org_id="org-1",
        force_full_refresh=False,
        dedupe_key="scheduled-2026060112-monitor-1",
    )

    expected_name = (
        "projects/project-1/locations/us-central1/queues/pipeline/tasks/"
        "monitor-scan-scheduled-2026060112-monitor-1"
    )
    assert task_id == expected_name
    assert client.requests[0].task.name == expected_name
    request = client.requests[0].task.http_request
    assert request.url == "https://workers.example.com/internal/run-monitor-scan"
    assert request.oidc_token.audience == "https://workers.example.com"
    assert json.loads(request.body.decode()) == {
        "monitor_id": "monitor-1",
        "org_id": "org-1",
        "force_full_refresh": False,
    }


@pytest.mark.asyncio
async def test_cloud_tasks_dispatcher_dispatches_monitor_alert_email(
    monkeypatch: pytest.MonkeyPatch,
):
    client = _FakeCloudTasksClient()
    _install_fake_cloud_tasks(monkeypatch, client)
    dispatcher = task_dispatcher.CloudTasksDispatcher(
        project_id="project-1",
        region="us-central1",
        queue_id="pipeline",
        workers_url="https://workers.example.com/",
        invoker_service_account_email="tasks@example.iam.gserviceaccount.com",
    )

    task_id = await dispatcher.dispatch_monitor_alert_email(
        user_id="user-1",
        monitor_id="monitor-1",
        alert_id="alert-1",
        org_id="org-1",
    )

    expected_name = (
        "projects/project-1/locations/us-central1/queues/pipeline/tasks/monitor-alert-email-alert-1"
    )
    assert task_id == expected_name
    assert client.requests[0].task.name == expected_name
    request = client.requests[0].task.http_request
    assert request.url == "https://workers.example.com/internal/run-monitor-alert-email"
    assert request.oidc_token.audience == "https://workers.example.com"
    assert json.loads(request.body.decode()) == {
        "user_id": "user-1",
        "monitor_id": "monitor-1",
        "alert_id": "alert-1",
        "org_id": "org-1",
    }


@pytest.mark.asyncio
async def test_cloud_tasks_dispatcher_dispatches_weekly_digest(
    monkeypatch: pytest.MonkeyPatch,
):
    client = _FakeCloudTasksClient()
    _install_fake_cloud_tasks(monkeypatch, client)
    dispatcher = task_dispatcher.CloudTasksDispatcher(
        project_id="project-1",
        region="us-central1",
        queue_id="pipeline",
        workers_url="https://workers.example.com/",
        invoker_service_account_email="tasks@example.iam.gserviceaccount.com",
    )

    task_id = await dispatcher.dispatch_weekly_digest(dedupe_key="2026-W23")

    expected_name = (
        "projects/project-1/locations/us-central1/queues/pipeline/tasks/weekly-digest-2026-W23"
    )
    assert task_id == expected_name
    assert client.requests[0].task.name == expected_name
    request = client.requests[0].task.http_request
    assert request.url == "https://workers.example.com/internal/run-weekly-digest"
    assert request.oidc_token.audience == "https://workers.example.com"
    assert json.loads(request.body.decode()) == {"dedupe_key": "2026-W23"}


@pytest.mark.asyncio
async def test_cloud_tasks_dispatcher_fans_out_tenant_delivery_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
):
    client = _FakeCloudTasksClient()
    _install_fake_cloud_tasks(monkeypatch, client)
    dispatcher = task_dispatcher.CloudTasksDispatcher(
        project_id="project-1",
        region="us-central1",
        queue_id="pipeline",
        reconciliation_queue_id="reconciliation",
        workers_url="https://workers.example.com/",
        invoker_service_account_email="tasks@example.iam.gserviceaccount.com",
    )
    org_id = "0d66ac6a-f4fe-4895-8b16-6a0b2ed29d19"
    dedupe_key = f"{org_id}-2026071404-01"

    task_id = await dispatcher.dispatch_external_report_delivery_reconciliation(
        org_id=org_id,
        dedupe_key=dedupe_key,
    )

    expected_name = (
        "projects/project-1/locations/us-central1/queues/reconciliation/tasks/"
        f"report-delivery-reconcile-{dedupe_key}"
    )
    assert task_id == expected_name
    request = client.requests[0].task.http_request
    assert request.url == (
        "https://workers.example.com/internal/run-external-report-delivery-reconciliation-org"
    )
    assert json.loads(request.body.decode()) == {
        "org_id": org_id,
        "dedupe_key": dedupe_key,
    }


@pytest.mark.asyncio
async def test_cloud_tasks_dispatcher_persists_delivery_sweep_continuation(
    monkeypatch: pytest.MonkeyPatch,
):
    client = _FakeCloudTasksClient()
    _install_fake_cloud_tasks(monkeypatch, client)
    dispatcher = task_dispatcher.CloudTasksDispatcher(
        project_id="project-1",
        region="us-central1",
        queue_id="pipeline",
        reconciliation_queue_id="reconciliation",
        workers_url="https://workers.example.com/",
        invoker_service_account_email="tasks@example.iam.gserviceaccount.com",
    )
    cursor = "00000000-0000-0000-0000-000000000064"
    sweep_id = "2026071404-01"
    dedupe_key = f"{sweep_id}-{cursor}"

    task_id = await dispatcher.dispatch_external_report_delivery_reconciliation_sweep(
        cursor=cursor,
        sweep_id=sweep_id,
        dedupe_key=dedupe_key,
    )

    expected_name = (
        "projects/project-1/locations/us-central1/queues/reconciliation/tasks/"
        f"report-delivery-reconcile-sweep-{dedupe_key}"
    )
    assert task_id == expected_name
    request = client.requests[0].task.http_request
    assert request.url == (
        "https://workers.example.com/internal/run-external-report-delivery-reconciliation"
    )
    assert json.loads(request.body.decode()) == {
        "cursor": cursor,
        "sweep_id": sweep_id,
    }


@pytest.mark.asyncio
async def test_cloud_tasks_dispatcher_treats_duplicate_task_as_dispatched(
    monkeypatch: pytest.MonkeyPatch,
):
    client = _FakeCloudTasksClient(duplicate=True)
    _install_fake_cloud_tasks(monkeypatch, client)
    dispatcher = task_dispatcher.CloudTasksDispatcher(
        project_id="project-1",
        region="us-central1",
        queue_id="pipeline",
        workers_url="https://workers.example.com",
        invoker_service_account_email="tasks@example.iam.gserviceaccount.com",
    )

    task_id = await dispatcher.dispatch_pipeline_run(
        analysis_id="analysis-1",
        org_id="org-1",
    )

    assert (
        task_id
        == "projects/project-1/locations/us-central1/queues/pipeline/tasks/pipeline-analysis-1"
    )
    assert len(client.requests) == 1
