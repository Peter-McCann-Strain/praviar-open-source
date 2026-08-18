"""Pluggable async task dispatcher — Celery or Cloud Tasks backends.

The pipeline workers historically run via Celery + Redis broker. The GCP
migration introduces Cloud Tasks as the production dispatcher, with the
Celery path preserved for local dev and the nightly benchmark batch
(>30 minute jobs use Cloud Run Jobs triggered by Cloud Scheduler — outside
this dispatcher).

Selection is via `settings.pipeline_dispatch` (Literal["celery", "cloud_tasks"]).
The Cloud Tasks backend pulls additional settings (`gcp_project_id`, `gcp_region`,
`cloud_tasks_queue_id`, `workers_service_url`, `tasks_invoker_sa_email`).
The Celery backend remains the local/test default.

Per 10-gcp-architecture.md §6.5.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import structlog

from api.services.blocking_sdk import run_blocking_sdk_call

logger = structlog.get_logger()

TASK_DISPATCH_TIMEOUT_SECONDS = 10.0
# Google Cloud Tasks HTTP targets accept at most 30 minutes. Pipeline tasks
# only launch a durable Cloud Run Job and therefore use the much shorter
# control-plane deadline below.
CLOUD_TASK_DISPATCH_DEADLINE_SECONDS = 30 * 60
PIPELINE_LAUNCH_DISPATCH_DEADLINE_SECONDS = 60
_PIPELINE_RECONCILIATION_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def _pipeline_task_id(analysis_id: str, reconciliation_key: str | None) -> str:
    """Use a fresh task-name generation for an explicit repair dispatch."""
    if reconciliation_key is None:
        return analysis_id
    if not _PIPELINE_RECONCILIATION_KEY_PATTERN.fullmatch(reconciliation_key):
        raise ValueError(
            "Pipeline reconciliation key must contain 1 to 80 ASCII letters, "
            "digits, underscores, or hyphens"
        )
    return f"{analysis_id}-reconcile-{reconciliation_key}"


def _is_cloud_task_already_exists(exc: Exception) -> bool:
    """Return true for google.api_core.exceptions.AlreadyExists without importing eagerly."""
    try:
        from google.api_core import exceptions as google_exceptions
    except Exception:
        return type(exc).__name__ == "AlreadyExists"
    else:
        if isinstance(exc, google_exceptions.AlreadyExists):
            return True
    return type(exc).__name__ == "AlreadyExists"


class TaskDispatcher(ABC):
    """Pluggable async task dispatcher."""

    @abstractmethod
    async def dispatch_pipeline_run(
        self,
        *,
        analysis_id: str,
        org_id: str,
        reconciliation_key: str | None = None,
    ) -> str:
        """Dispatch a pipeline run. Returns a task ID."""

    @abstractmethod
    async def dispatch_export_job(self, *, export_job_id: str, org_id: str) -> str:
        """Dispatch an export job. Returns a task ID."""

    @abstractmethod
    async def dispatch_faithfulness_scores(
        self,
        *,
        analysis_id: str,
        org_id: str,
    ) -> str:
        """Dispatch shadow faithfulness scoring. Returns a task ID."""

    @abstractmethod
    async def dispatch_monitor_scan(
        self,
        *,
        monitor_id: str,
        org_id: str,
        force_full_refresh: bool = False,
        dedupe_key: str | None = None,
    ) -> str:
        """Dispatch one monitor scan. Returns a task ID."""

    @abstractmethod
    async def dispatch_monitor_alert_email(
        self,
        *,
        user_id: str,
        monitor_id: str,
        alert_id: str,
        org_id: str,
    ) -> str:
        """Dispatch one monitor alert email. Returns a task ID."""

    @abstractmethod
    async def dispatch_weekly_digest(self, *, dedupe_key: str | None = None) -> str:
        """Dispatch the weekly digest sweep. Returns a task ID."""

    @abstractmethod
    async def dispatch_external_report_delivery_reconciliation(
        self,
        *,
        org_id: str,
        dedupe_key: str,
        continuation: int = 0,
    ) -> str:
        """Dispatch one tenant-scoped invitation reconciliation task."""

    @abstractmethod
    async def dispatch_external_report_delivery_reconciliation_sweep(
        self,
        *,
        cursor: str,
        sweep_id: str,
        dedupe_key: str,
    ) -> str:
        """Dispatch one durable continuation page for the global sweep."""


class CeleryDispatcher(TaskDispatcher):
    """Local-dev + test dispatcher — delegates to the existing Celery app.

    Import is lazy so the Celery dependency only loads when this backend is selected.
    """

    async def dispatch_pipeline_run(
        self,
        *,
        analysis_id: str,
        org_id: str,
        reconciliation_key: str | None = None,
    ) -> str:
        # Import lazily — the celery task module may not exist in all build profiles.
        from importlib import import_module

        tasks_module = import_module("api.workers.tasks")
        task = tasks_module.run_fto_pipeline
        result = await run_blocking_sdk_call(
            "celery.pipeline.delay",
            task.delay,
            analysis_id,
            org_id=org_id,
            timeout_seconds=TASK_DISPATCH_TIMEOUT_SECONDS,
            max_attempts=1,
            logger_override=logger,
        )
        logger.info(
            "task_dispatcher.celery.dispatched",
            analysis_id=analysis_id,
            org_id=org_id,
            reconciliation_key=reconciliation_key,
            celery_task_id=result.id,
        )
        return str(result.id)

    async def dispatch_export_job(self, *, export_job_id: str, org_id: str) -> str:
        from importlib import import_module

        tasks_module = import_module("api.workers.tasks")
        task = tasks_module.run_export
        result = await run_blocking_sdk_call(
            "celery.export.delay",
            task.delay,
            export_job_id,
            org_id=org_id,
            timeout_seconds=TASK_DISPATCH_TIMEOUT_SECONDS,
            max_attempts=1,
            logger_override=logger,
        )
        logger.info(
            "task_dispatcher.celery.export_dispatched",
            export_job_id=export_job_id,
            org_id=org_id,
            celery_task_id=result.id,
        )
        return str(result.id)

    async def dispatch_faithfulness_scores(
        self,
        *,
        analysis_id: str,
        org_id: str,
    ) -> str:
        from importlib import import_module

        tasks_module = import_module("api.workers.tasks")
        task = tasks_module.compute_faithfulness_scores
        result = await run_blocking_sdk_call(
            "celery.faithfulness_uq.delay",
            task.delay,
            analysis_id,
            org_id=org_id,
            timeout_seconds=TASK_DISPATCH_TIMEOUT_SECONDS,
            max_attempts=1,
            logger_override=logger,
        )
        logger.info(
            "task_dispatcher.celery.faithfulness_uq_dispatched",
            analysis_id=analysis_id,
            org_id=org_id,
            celery_task_id=result.id,
        )
        return str(result.id)

    async def dispatch_monitor_scan(
        self,
        *,
        monitor_id: str,
        org_id: str,
        force_full_refresh: bool = False,
        dedupe_key: str | None = None,
    ) -> str:
        from importlib import import_module

        monitor_tasks_module = import_module("api.workers.monitor_tasks")
        task = monitor_tasks_module.run_monitor_scan
        result = await run_blocking_sdk_call(
            "celery.monitor_scan.delay",
            task.delay,
            monitor_id,
            org_id=org_id,
            force_full_refresh=force_full_refresh,
            timeout_seconds=TASK_DISPATCH_TIMEOUT_SECONDS,
            max_attempts=1,
            logger_override=logger,
        )
        logger.info(
            "task_dispatcher.celery.monitor_scan_dispatched",
            monitor_id=monitor_id,
            org_id=org_id,
            force_full_refresh=force_full_refresh,
            dedupe_key=dedupe_key,
            celery_task_id=result.id,
        )
        return str(result.id)

    async def dispatch_monitor_alert_email(
        self,
        *,
        user_id: str,
        monitor_id: str,
        alert_id: str,
        org_id: str,
    ) -> str:
        from importlib import import_module

        email_tasks_module = import_module("api.workers.email_tasks")
        task = email_tasks_module.send_monitor_alert_email
        result = await run_blocking_sdk_call(
            "celery.monitor_alert_email.delay",
            task.delay,
            user_id,
            monitor_id,
            alert_id,
            org_id=org_id,
            timeout_seconds=TASK_DISPATCH_TIMEOUT_SECONDS,
            max_attempts=1,
            logger_override=logger,
        )
        logger.info(
            "task_dispatcher.celery.monitor_alert_email_dispatched",
            user_id=user_id,
            monitor_id=monitor_id,
            alert_id=alert_id,
            org_id=org_id,
            celery_task_id=result.id,
        )
        return str(result.id)

    async def dispatch_weekly_digest(self, *, dedupe_key: str | None = None) -> str:
        from importlib import import_module

        email_tasks_module = import_module("api.workers.email_tasks")
        task = email_tasks_module.send_weekly_digest
        result = await run_blocking_sdk_call(
            "celery.weekly_digest.delay",
            task.delay,
            timeout_seconds=TASK_DISPATCH_TIMEOUT_SECONDS,
            max_attempts=1,
            logger_override=logger,
        )
        logger.info(
            "task_dispatcher.celery.weekly_digest_dispatched",
            dedupe_key=dedupe_key,
            celery_task_id=result.id,
        )
        return str(result.id)

    async def dispatch_external_report_delivery_reconciliation(
        self,
        *,
        org_id: str,
        dedupe_key: str,
        continuation: int = 0,
    ) -> str:
        from importlib import import_module

        tasks_module = import_module("api.workers.tasks")
        task = tasks_module.reconcile_external_report_deliveries_for_org
        result = await run_blocking_sdk_call(
            "celery.external_report_delivery_reconciliation.delay",
            task.delay,
            org_id,
            dedupe_key,
            continuation,
            timeout_seconds=TASK_DISPATCH_TIMEOUT_SECONDS,
            max_attempts=1,
            logger_override=logger,
        )
        logger.info(
            "task_dispatcher.celery.external_report_delivery_reconciliation_dispatched",
            org_id=org_id,
            dedupe_key=dedupe_key,
            celery_task_id=result.id,
        )
        return str(result.id)

    async def dispatch_external_report_delivery_reconciliation_sweep(
        self,
        *,
        cursor: str,
        sweep_id: str,
        dedupe_key: str,
    ) -> str:
        from importlib import import_module

        tasks_module = import_module("api.workers.tasks")
        task = tasks_module.dispatch_external_report_delivery_reconciliation_sweep
        result = await run_blocking_sdk_call(
            "celery.external_report_delivery_reconciliation_sweep.delay",
            task.delay,
            cursor,
            sweep_id,
            timeout_seconds=TASK_DISPATCH_TIMEOUT_SECONDS,
            max_attempts=1,
            logger_override=logger,
        )
        return str(result.id)


class CloudTasksDispatcher(TaskDispatcher):
    """Production dispatcher — Cloud Tasks → workers Cloud Run service via OIDC."""

    _tasks_v2: Any
    _client: Any

    def __init__(
        self,
        *,
        project_id: str,
        region: str,
        queue_id: str,
        workers_url: str,
        invoker_service_account_email: str,
        reconciliation_queue_id: str | None = None,
    ) -> None:
        # Lazy import via importlib — google-cloud-tasks is an optional dep
        # added during W2-C. Pyright cannot statically validate the symbol;
        # runtime behavior follows the documented SDK.
        from importlib import import_module

        self._tasks_v2 = import_module("google.cloud.tasks_v2")
        self._client = self._tasks_v2.CloudTasksClient()
        self._queue_path = self._client.queue_path(project_id, region, queue_id.split("/")[-1])
        self._reconciliation_queue_path = self._client.queue_path(
            project_id,
            region,
            (reconciliation_queue_id or queue_id).split("/")[-1],
        )
        self._workers_url = workers_url.rstrip("/")
        self._invoker_sa = invoker_service_account_email

    async def dispatch_pipeline_run(
        self,
        *,
        analysis_id: str,
        org_id: str,
        reconciliation_key: str | None = None,
    ) -> str:
        return await self._dispatch_http_task(
            task_prefix="pipeline",
            task_id=_pipeline_task_id(analysis_id, reconciliation_key),
            endpoint="/internal/run-pipeline",
            body={"analysis_id": analysis_id, "org_id": org_id},
            log_fields={
                "analysis_id": analysis_id,
                "org_id": org_id,
                "reconciliation_key": reconciliation_key,
            },
            dispatch_deadline_seconds=PIPELINE_LAUNCH_DISPATCH_DEADLINE_SECONDS,
        )

    async def dispatch_export_job(self, *, export_job_id: str, org_id: str) -> str:
        return await self._dispatch_http_task(
            task_prefix="export",
            task_id=export_job_id,
            endpoint="/internal/run-export",
            body={"export_job_id": export_job_id, "org_id": org_id},
            log_fields={"export_job_id": export_job_id, "org_id": org_id},
        )

    async def dispatch_faithfulness_scores(
        self,
        *,
        analysis_id: str,
        org_id: str,
    ) -> str:
        return await self._dispatch_http_task(
            task_prefix="faithfulness",
            task_id=analysis_id,
            endpoint="/internal/run-faithfulness",
            body={"analysis_id": analysis_id, "org_id": org_id},
            log_fields={"analysis_id": analysis_id, "org_id": org_id},
        )

    async def dispatch_monitor_scan(
        self,
        *,
        monitor_id: str,
        org_id: str,
        force_full_refresh: bool = False,
        dedupe_key: str | None = None,
    ) -> str:
        mode = "full" if force_full_refresh else "scheduled"
        task_id = dedupe_key or f"{mode}-{monitor_id}"
        return await self._dispatch_http_task(
            task_prefix="monitor-scan",
            task_id=task_id,
            endpoint="/internal/run-monitor-scan",
            body={
                "monitor_id": monitor_id,
                "org_id": org_id,
                "force_full_refresh": force_full_refresh,
            },
            log_fields={
                "monitor_id": monitor_id,
                "org_id": org_id,
                "force_full_refresh": str(force_full_refresh),
                "dedupe_key": task_id,
            },
        )

    async def dispatch_monitor_alert_email(
        self,
        *,
        user_id: str,
        monitor_id: str,
        alert_id: str,
        org_id: str,
    ) -> str:
        return await self._dispatch_http_task(
            task_prefix="monitor-alert-email",
            task_id=alert_id,
            endpoint="/internal/run-monitor-alert-email",
            body={
                "user_id": user_id,
                "monitor_id": monitor_id,
                "alert_id": alert_id,
                "org_id": org_id,
            },
            log_fields={
                "user_id": user_id,
                "monitor_id": monitor_id,
                "alert_id": alert_id,
                "org_id": org_id,
            },
        )

    async def dispatch_weekly_digest(self, *, dedupe_key: str | None = None) -> str:
        task_id = dedupe_key or datetime.now(UTC).strftime("%G-W%V")
        return await self._dispatch_http_task(
            task_prefix="weekly-digest",
            task_id=task_id,
            endpoint="/internal/run-weekly-digest",
            body={"dedupe_key": task_id},
            log_fields={"dedupe_key": task_id},
        )

    async def dispatch_external_report_delivery_reconciliation(
        self,
        *,
        org_id: str,
        dedupe_key: str,
        continuation: int = 0,
    ) -> str:
        body: dict[str, Any] = {"org_id": org_id, "dedupe_key": dedupe_key}
        if continuation:
            body["continuation"] = continuation
        return await self._dispatch_http_task(
            task_prefix="report-delivery-reconcile",
            task_id=dedupe_key,
            endpoint="/internal/run-external-report-delivery-reconciliation-org",
            body=body,
            log_fields={
                "org_id": org_id,
                "dedupe_key": dedupe_key,
                "continuation": continuation,
            },
            queue_path=self._reconciliation_queue_path,
        )

    async def dispatch_external_report_delivery_reconciliation_sweep(
        self,
        *,
        cursor: str,
        sweep_id: str,
        dedupe_key: str,
    ) -> str:
        return await self._dispatch_http_task(
            task_prefix="report-delivery-reconcile-sweep",
            task_id=dedupe_key,
            endpoint="/internal/run-external-report-delivery-reconciliation",
            body={"cursor": cursor, "sweep_id": sweep_id},
            log_fields={
                "cursor": cursor,
                "sweep_id": sweep_id,
                "dedupe_key": dedupe_key,
            },
            queue_path=self._reconciliation_queue_path,
        )

    async def _dispatch_http_task(
        self,
        *,
        task_prefix: str,
        task_id: str,
        endpoint: str,
        body: dict[str, Any],
        log_fields: dict[str, Any],
        queue_path: str | None = None,
        dispatch_deadline_seconds: int = CLOUD_TASK_DISPATCH_DEADLINE_SECONDS,
    ) -> str:
        from google.protobuf import duration_pb2

        tasks_v2 = self._tasks_v2

        resolved_queue_path = queue_path or self._queue_path
        task_name = f"{resolved_queue_path}/tasks/{task_prefix}-{task_id}"

        task = tasks_v2.Task(
            name=task_name,
            http_request=tasks_v2.HttpRequest(
                http_method=tasks_v2.HttpMethod.POST,
                url=f"{self._workers_url}{endpoint}",
                headers={"Content-Type": "application/json"},
                body=json.dumps(body).encode(),
                oidc_token=tasks_v2.OidcToken(
                    service_account_email=self._invoker_sa,
                    audience=self._workers_url,
                ),
            ),
            dispatch_deadline=duration_pb2.Duration(seconds=dispatch_deadline_seconds),
        )

        duplicate_task = False
        create_request = tasks_v2.CreateTaskRequest(parent=resolved_queue_path, task=task)

        def create_task_once() -> Any:
            nonlocal duplicate_task
            try:
                return self._client.create_task(request=create_request)
            except Exception as exc:
                if not _is_cloud_task_already_exists(exc):
                    raise
                duplicate_task = True
                return SimpleNamespace(name=task_name)

        created = await run_blocking_sdk_call(
            "cloud_tasks.create_task",
            create_task_once,
            timeout_seconds=TASK_DISPATCH_TIMEOUT_SECONDS,
            max_attempts=1,
            logger_override=logger,
        )
        if duplicate_task:
            logger.info(
                "task_dispatcher.cloud_tasks.duplicate_ignored",
                **log_fields,
                cloud_task_name=task_name,
            )
            return task_name

        logger.info(
            "task_dispatcher.cloud_tasks.dispatched",
            **log_fields,
            cloud_task_name=created.name,
        )
        return str(created.name)


def build_dispatcher() -> TaskDispatcher:
    """Factory — chooses backend based on settings.pipeline_dispatch.

    The GCP-specific settings (`gcp_project_id`, etc.) are accessed via getattr
    so this module imports cleanly before W2-B extends APISettings.
    """
    from api.config import get_settings

    settings = get_settings()
    backend = getattr(settings, "pipeline_dispatch", "celery")

    if backend == "cloud_tasks":
        required = {
            "GCP_PROJECT_ID": getattr(settings, "gcp_project_id", ""),
            "CLOUD_TASKS_QUEUE_ID": getattr(settings, "cloud_tasks_queue_id", ""),
            "RECONCILIATION_CLOUD_TASKS_QUEUE_ID": getattr(
                settings,
                "reconciliation_cloud_tasks_queue_id",
                "",
            ),
            "WORKERS_SERVICE_URL": getattr(settings, "workers_service_url", ""),
            "TASKS_INVOKER_SA_EMAIL": getattr(settings, "tasks_invoker_sa_email", ""),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(
                "Cloud Tasks dispatch is configured but required settings are missing: "
                + ", ".join(missing)
            )
        return CloudTasksDispatcher(
            project_id=getattr(settings, "gcp_project_id", ""),
            region=getattr(settings, "gcp_region", "us-central1"),
            queue_id=getattr(settings, "cloud_tasks_queue_id", ""),
            reconciliation_queue_id=getattr(
                settings,
                "reconciliation_cloud_tasks_queue_id",
                "",
            ),
            workers_url=getattr(settings, "workers_service_url", ""),
            invoker_service_account_email=getattr(settings, "tasks_invoker_sa_email", ""),
        )

    if backend == "celery":
        if getattr(settings, "app_env", None) == "prod":
            raise RuntimeError(
                "Celery dispatch is not permitted when APP_ENV=prod; "
                "set PIPELINE_DISPATCH=cloud_tasks."
            )
        return CeleryDispatcher()

    raise RuntimeError(f"Unsupported PIPELINE_DISPATCH={backend!r}")
