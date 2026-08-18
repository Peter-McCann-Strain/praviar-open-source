from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.admin_health import (
    _check_celery_health,
    _check_cloud_tasks_health,
    _check_database_health,
    _check_dispatcher_health,
    _check_redis_health,
    _collect_table_counts,
)


class TestAdminHealthChecks:
    @pytest.mark.asyncio
    async def test_check_database_health_returns_ok(self, mock_db):
        health = await _check_database_health(mock_db)

        assert health.name == "database"
        assert health.status == "ok"

    @pytest.mark.asyncio
    async def test_database_health_error_does_not_disclose_exception_details(self):
        secret = "postgresql://user:secret@internal-db/praviar"
        db = AsyncMock()
        db.execute.side_effect = RuntimeError(secret)

        with patch("api.services.admin_health.logger.warning") as warning:
            health = await _check_database_health(db)

        assert health.status == "error"
        assert health.detail == "Database health check failed"
        assert secret not in health.detail
        assert secret not in repr(warning.call_args)
        assert warning.call_args.kwargs["error_type"] == "RuntimeError"

    @pytest.mark.asyncio
    async def test_check_redis_health_returns_ok(self):
        class FakeRedis:
            def __init__(self):
                self.closed = False

            async def ping(self):
                return None

            async def aclose(self):
                self.closed = True

        fake_redis = FakeRedis()

        health = await _check_redis_health(
            redis_url="redis://example",
            redis_from_url=lambda _url: fake_redis,
        )

        assert health.name == "redis"
        assert health.status == "ok"
        assert fake_redis.closed is True

    @pytest.mark.asyncio
    async def test_check_redis_health_passes_bounded_connection_kwargs(self):
        class FakeRedis:
            async def ping(self):
                return None

            async def aclose(self):
                return None

        redis_from_url = MagicMock(return_value=FakeRedis())

        health = await _check_redis_health(
            redis_url="redis://example",
            redis_from_url=redis_from_url,
            redis_connection_kwargs={
                "socket_connect_timeout": 1.0,
                "socket_timeout": 2.0,
                "health_check_interval": 15,
            },
        )

        assert health.status == "ok"
        redis_from_url.assert_called_once_with(
            "redis://example",
            socket_connect_timeout=1.0,
            socket_timeout=2.0,
            health_check_interval=15,
        )

    @pytest.mark.asyncio
    async def test_redis_health_error_does_not_disclose_exception_details(self):
        secret = "redis://:password@internal-redis:6379/0"

        with patch("api.services.admin_health.logger.warning") as warning:
            health = await _check_redis_health(
                redis_url="redis://example",
                redis_from_url=MagicMock(side_effect=RuntimeError(secret)),
            )

        assert health.status == "error"
        assert health.detail == "Redis health check failed"
        assert secret not in health.detail
        assert secret not in repr(warning.call_args)
        assert warning.call_args.kwargs["error_type"] == "RuntimeError"

    def test_check_celery_health_returns_error_when_workers_missing(self, monkeypatch):
        class FakeInspect:
            def active_queues(self):
                return None

        fake_celery_app = SimpleNamespace(
            control=SimpleNamespace(inspect=lambda timeout: FakeInspect())
        )

        monkeypatch.setattr(
            "api.workers.celery_app.celery_app",
            fake_celery_app,
        )

        health = _check_celery_health()

        assert health.name == "celery"
        assert health.status == "error"
        assert health.detail == "No workers responding"

    def test_check_celery_health_returns_ok_when_workers_are_available(self, monkeypatch):
        class FakeInspect:
            def active_queues(self):
                return {"worker-1": [{"name": "celery"}]}

        fake_celery_app = SimpleNamespace(
            conf=SimpleNamespace(task_default_queue="celery"),
            control=SimpleNamespace(inspect=lambda timeout: FakeInspect()),
        )

        monkeypatch.setattr(
            "api.workers.celery_app.celery_app",
            fake_celery_app,
        )

        health = _check_celery_health()

        assert health.name == "celery"
        assert health.status == "ok"
        assert health.detail == "1 worker(s) on required queue"

    def test_check_celery_health_rejects_worker_on_unrelated_queue(self, monkeypatch):
        class FakeInspect:
            def active_queues(self):
                return {"worker-1": [{"name": "browser-health-only"}]}

        fake_celery_app = SimpleNamespace(
            conf=SimpleNamespace(task_default_queue="celery"),
            control=SimpleNamespace(inspect=lambda timeout: FakeInspect()),
        )
        monkeypatch.setattr("api.workers.celery_app.celery_app", fake_celery_app)

        health = _check_celery_health()

        assert health.status == "error"
        assert health.detail == "No workers subscribed to required queue"

    def test_check_celery_health_fails_closed_without_queue_topology(self, monkeypatch):
        class FakeInspect:
            def active_queues(self):
                return {"worker-1": None}

        fake_celery_app = SimpleNamespace(
            conf=SimpleNamespace(task_default_queue="celery"),
            control=SimpleNamespace(inspect=lambda timeout: FakeInspect()),
        )
        monkeypatch.setattr("api.workers.celery_app.celery_app", fake_celery_app)

        health = _check_celery_health()

        assert health.status == "error"
        assert health.detail == "No workers subscribed to required queue"

    def test_celery_health_error_does_not_disclose_exception_details(self, monkeypatch):
        secret = "amqp://worker:secret@internal-broker/vhost"

        def _raise(timeout):
            del timeout
            raise RuntimeError(secret)

        fake_celery_app = SimpleNamespace(control=SimpleNamespace(inspect=_raise))
        monkeypatch.setattr("api.workers.celery_app.celery_app", fake_celery_app)

        with patch("api.services.admin_health.logger.warning") as warning:
            health = _check_celery_health()

        assert health.status == "error"
        assert health.detail == "Worker health check failed"
        assert secret not in health.detail
        assert secret not in repr(warning.call_args)
        assert warning.call_args.kwargs["error_type"] == "RuntimeError"

    def test_check_cloud_tasks_health_returns_ok_when_configured(self):
        settings = SimpleNamespace(
            gcp_project_id="sentinel-project",
            gcp_region="sentinel-region",
            cloud_tasks_queue_id="sentinel-queue",
            workers_service_url="https://workers.praviar.io",
            tasks_invoker_sa_email="sentinel@sentinel-project.iam.gserviceaccount.com",
        )

        health = _check_cloud_tasks_health(settings)

        assert health.name == "cloud_tasks"
        assert health.status == "ok"
        assert health.detail == "Cloud Tasks configured"
        assert "sentinel" not in health.detail

        platform_health = _check_cloud_tasks_health(settings, include_topology=True)
        assert "sentinel-queue" in platform_health.detail
        assert "sentinel-project" in platform_health.detail
        assert "sentinel-region" in platform_health.detail

    def test_check_cloud_tasks_health_returns_error_when_config_missing(self):
        settings = SimpleNamespace(
            gcp_project_id="",
            gcp_region="us-central1",
            cloud_tasks_queue_id="analysis-jobs",
            workers_service_url="",
            tasks_invoker_sa_email="",
        )

        health = _check_cloud_tasks_health(settings)

        assert health.name == "cloud_tasks"
        assert health.status == "error"
        assert health.detail == "Cloud Tasks configuration incomplete"
        assert "GCP_PROJECT_ID" not in health.detail
        assert "WORKERS_SERVICE_URL" not in health.detail
        assert "TASKS_INVOKER_SA_EMAIL" not in health.detail

        platform_health = _check_cloud_tasks_health(settings, include_topology=True)
        assert "GCP_PROJECT_ID" in platform_health.detail
        assert "WORKERS_SERVICE_URL" in platform_health.detail
        assert "TASKS_INVOKER_SA_EMAIL" in platform_health.detail

    def test_check_dispatcher_health_selects_cloud_tasks(self):
        settings = SimpleNamespace(
            pipeline_dispatch="cloud_tasks",
            gcp_project_id="praviar-prod",
            gcp_region="us-central1",
            cloud_tasks_queue_id="analysis-jobs",
            workers_service_url="https://workers.praviar.io",
            tasks_invoker_sa_email="tasks@praviar-prod.iam.gserviceaccount.com",
        )

        health = _check_dispatcher_health(settings)

        assert health.name == "cloud_tasks"
        assert health.status == "ok"

    @pytest.mark.asyncio
    async def test_collect_table_counts_returns_partial_counts_and_failures(self, mock_db):
        organization_count = SimpleNamespace(scalar_one=lambda: 2)
        analysis_count = SimpleNamespace(scalar_one=lambda: 4)
        mock_db.execute.side_effect = [
            organization_count,
            RuntimeError("users count failed"),
            analysis_count,
        ]

        table_counts, failed_tables = await _collect_table_counts(mock_db)

        assert table_counts == {"organizations": 2, "analyses": 4}
        assert failed_tables == ["users"]
