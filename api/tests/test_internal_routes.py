"""Tests for Cloud Tasks internal worker routes."""

from __future__ import annotations

import base64
import json
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from api.db.models import AnalysisStatus, UserRole
from api.errors import APIError
from api.routes import internal


def _jwt_with_alg(alg: str = "RS256") -> str:
    def _encode(data: dict) -> str:
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    return f"{_encode({'alg': alg, 'typ': 'JWT'})}.{_encode({'sub': 'task'})}.c2ln"


def _request_with_bearer(token: str | None = None) -> Request:
    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "https",
            "path": "/internal/run-pipeline",
            "server": ("workers.example.com", 443),
            "headers": headers,
        }
    )


def _release_canary_request(task_name: str = "release-gate-123") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "https",
            "path": "/internal/release-canary",
            "server": ("candidate-workers.example.com", 443),
            "headers": [
                (b"x-cloudtasks-taskname", task_name.encode("ascii")),
            ],
        }
    )


def _patch_google_oidc(monkeypatch: pytest.MonkeyPatch, claims: dict):
    observed: dict[str, str] = {}

    def _verify_oauth2_token(token, request_obj, audience):
        observed["token"] = token
        observed["audience"] = audience
        observed["request_obj_type"] = type(request_obj).__name__
        return claims

    def _import_module(name: str):
        if name == "google.oauth2.id_token":
            return SimpleNamespace(verify_oauth2_token=_verify_oauth2_token)
        if name == "google.auth.transport.requests":
            return SimpleNamespace(Request=lambda: SimpleNamespace())
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(internal, "import_module", _import_module)
    return observed


@pytest.mark.asyncio
async def test_verify_oidc_token_uses_configured_audience_and_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _jwt_with_alg()
    settings = SimpleNamespace(
        app_env="prod",
        workers_service_url="https://workers.example.com",
        tasks_invoker_sa_email="tasks@example.iam.gserviceaccount.com",
    )
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "https://workers.example.com",
        "email": "tasks@example.iam.gserviceaccount.com",
        "email_verified": True,
    }
    observed = _patch_google_oidc(monkeypatch, claims)
    monkeypatch.setattr(internal, "get_settings", lambda: settings)

    caller = await internal.verify_oidc_token(_request_with_bearer(token))

    assert caller == "tasks@example.iam.gserviceaccount.com"
    assert observed["token"] == token
    assert observed["audience"] == "https://workers.example.com"


@pytest.mark.asyncio
async def test_verify_ledger_oidc_token_requires_api_service_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _jwt_with_alg()
    settings = SimpleNamespace(
        app_env="prod",
        workers_service_url="https://workers.example.com",
        ledger_invoker_sa_email="api@example.iam.gserviceaccount.com",
    )
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "https://workers.example.com",
        "email": "api@example.iam.gserviceaccount.com",
        "email_verified": True,
    }
    _patch_google_oidc(monkeypatch, claims)
    monkeypatch.setattr(internal, "get_settings", lambda: settings)

    assert await internal.verify_ledger_oidc_token(_request_with_bearer(token)) == (
        "api@example.iam.gserviceaccount.com"
    )


@pytest.mark.asyncio
async def test_worker_release_canary_binds_task_and_release_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        release_version="a" * 40,
        service_role="worker",
    )
    monkeypatch.setattr(internal, "get_settings", lambda: settings)

    result = await internal.worker_release_canary(
        internal.WorkerReleaseCanaryRequest(release_sha="a" * 40),
        _release_canary_request(),
        caller_email="tasks@example.iam.gserviceaccount.com",
    )

    assert result == {
        "accepted": True,
        "cloud_task_name": "release-gate-123",
        "release_sha": "a" * 40,
    }


@pytest.mark.asyncio
async def test_worker_release_canary_rejects_wrong_service_or_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        internal,
        "get_settings",
        lambda: SimpleNamespace(release_version="a" * 40, service_role="api"),
    )
    with pytest.raises(APIError) as api_exc:
        await internal.worker_release_canary(
            internal.WorkerReleaseCanaryRequest(release_sha="a" * 40),
            _release_canary_request(),
            caller_email="tasks@example.iam.gserviceaccount.com",
        )
    assert api_exc.value.status == 404

    monkeypatch.setattr(
        internal,
        "get_settings",
        lambda: SimpleNamespace(release_version="a" * 40, service_role="worker"),
    )
    with pytest.raises(APIError) as release_exc:
        await internal.worker_release_canary(
            internal.WorkerReleaseCanaryRequest(release_sha="b" * 40),
            _release_canary_request(),
            caller_email="tasks@example.iam.gserviceaccount.com",
        )
    assert release_exc.value.status == 409


@pytest.mark.asyncio
async def test_claimed_use_ledger_issue_rebinds_actor_and_uses_writer_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        email="counsel@example.com",
        role=UserRole.ATTORNEY,
    )
    analysis_id = uuid.uuid4()
    runtime_db = object()
    writer_db = object()
    load_actor = AsyncMock(return_value=actor)
    issue = AsyncMock(return_value=SimpleNamespace(model_dump=lambda **_kwargs: {"id": "r1"}))

    @asynccontextmanager
    async def _writer_boundary(role: str, *, org_id: uuid.UUID):
        assert role == "writer"
        assert org_id == actor.org_id
        yield writer_db

    monkeypatch.setattr(internal, "_load_ledger_actor", load_actor)
    monkeypatch.setattr(internal, "claimed_use_privileged_session", _writer_boundary)
    monkeypatch.setattr(internal, "issue_claimed_use_receipt", issue)

    request_body = internal.ClaimedUseLedgerIssueRequest(
        analysis_id=analysis_id,
        actor_user_id=actor.id,
        org_id=actor.org_id,
        body={
            "expected_report_id": "report-1",
            "expected_report_fingerprint": "a" * 64,
            "patent_id": "US1234",
            "claim_number": 1,
            "accused_act_index": 0,
            "claimed_use_match": True,
            "product_identity_match": True,
        },
    )
    result = await internal.claimed_use_ledger_issue(
        request_body,
        db=runtime_db,  # type: ignore[arg-type]
        _caller="api@example.iam.gserviceaccount.com",
    )

    assert result == {"id": "r1"}
    load_actor.assert_awaited_once_with(
        runtime_db,
        actor_user_id=actor.id,
        org_id=actor.org_id,
    )
    issue.assert_awaited_once_with(
        writer_db,
        analysis_id=analysis_id,
        user=actor,
        body=request_body.body,
        use_database_boundary=True,
    )


@pytest.mark.asyncio
async def test_claimed_use_ledger_rejects_role_drift_before_privileged_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        email="scientist@example.com",
        role=UserRole.SCIENTIST,
    )
    monkeypatch.setattr(internal, "_load_ledger_actor", AsyncMock(return_value=actor))

    with pytest.raises(APIError) as exc_info:
        await internal.claimed_use_ledger_list(
            internal.ClaimedUseLedgerActorRequest(
                analysis_id=uuid.uuid4(),
                actor_user_id=actor.id,
                org_id=actor.org_id,
            ),
            db=object(),  # type: ignore[arg-type]
            _caller="api@example.iam.gserviceaccount.com",
        )

    assert exc_info.value.status == 403


@pytest.mark.asyncio
async def test_verify_oidc_token_rejects_unexpected_algorithm() -> None:
    with pytest.raises(Exception) as exc_info:
        await internal.verify_oidc_token(_request_with_bearer(_jwt_with_alg("HS256")))

    assert "Unexpected OIDC token algorithm" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("claims_override", "expected_detail"),
    [
        ({"iss": "https://evil.example"}, "Unexpected OIDC issuer"),
        ({"aud": "https://other.example.com"}, "Unexpected OIDC audience"),
        ({"email_verified": False}, "OIDC caller email is not verified"),
        ({"email_verified": None}, "OIDC caller email is not verified"),
        ({"email": "other@example.iam.gserviceaccount.com"}, "Unexpected OIDC caller"),
    ],
)
async def test_verify_oidc_token_rejects_confused_deputy_claims(
    monkeypatch: pytest.MonkeyPatch,
    claims_override: dict,
    expected_detail: str,
) -> None:
    settings = SimpleNamespace(
        app_env="prod",
        workers_service_url="https://workers.example.com",
        tasks_invoker_sa_email="tasks@example.iam.gserviceaccount.com",
    )
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "https://workers.example.com",
        "email": "tasks@example.iam.gserviceaccount.com",
        "email_verified": True,
        **claims_override,
    }
    _patch_google_oidc(monkeypatch, claims)
    monkeypatch.setattr(internal, "get_settings", lambda: settings)

    with pytest.raises(Exception) as exc_info:
        await internal.verify_oidc_token(_request_with_bearer(_jwt_with_alg()))

    assert expected_detail in str(exc_info.value)


@pytest.mark.asyncio
async def test_verify_oidc_token_requires_configured_prod_audience(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        app_env="prod",
        workers_service_url="",
        tasks_invoker_sa_email="tasks@example.iam.gserviceaccount.com",
    )
    monkeypatch.setattr(internal, "get_settings", lambda: settings)

    with pytest.raises(Exception) as exc_info:
        await internal.verify_oidc_token(_request_with_bearer(_jwt_with_alg()))

    assert "OIDC audience is not configured" in str(exc_info.value)


@pytest.mark.asyncio
async def test_verify_oidc_token_requires_configured_prod_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        app_env="prod",
        workers_service_url="https://workers.example.com",
        tasks_invoker_sa_email="",
    )
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "https://workers.example.com",
        "email": "tasks@example.iam.gserviceaccount.com",
        "email_verified": True,
    }
    _patch_google_oidc(monkeypatch, claims)
    monkeypatch.setattr(internal, "get_settings", lambda: settings)

    with pytest.raises(Exception) as exc_info:
        await internal.verify_oidc_token(_request_with_bearer(_jwt_with_alg()))

    assert "OIDC caller is not configured" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_pipeline_persists_fence_before_launching_durable_job() -> None:
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    analysis = SimpleNamespace(
        status=AnalysisStatus.PENDING,
        pipeline_execution_id=None,
        pipeline_lease_expires_at=None,
    )
    db = AsyncMock()
    query_result = MagicMock()
    query_result.scalar_one_or_none.return_value = analysis
    db.execute.return_value = query_result
    events: list[str] = []
    db.commit.side_effect = lambda: events.append("committed")

    async def launch_job(**_kwargs):
        events.append("launched")
        return SimpleNamespace(
            operation_name="projects/project-1/locations/us-central1/operations/op-1"
        )

    launcher = SimpleNamespace(launch=AsyncMock(side_effect=launch_job))

    with (
        patch("api.routes.internal.bind_current_org_to_session", new=AsyncMock()),
        patch(
            "api.services.pipeline_job_launcher.build_pipeline_job_launcher",
            return_value=launcher,
        ),
    ):
        response = await internal.run_pipeline(
            internal.PipelineRunRequest(analysis_id=analysis_id, org_id=org_id),
            db=db,
            caller_email="tasks@example.iam.gserviceaccount.com",
        )

    assert response["accepted"] is True
    assert response["execution"] == "job_accepted"
    assert response["analysis_id"] == str(analysis_id)
    assert response["execution_id"] == str(analysis.pipeline_execution_id)
    assert response["reservation_reused"] is False
    db.commit.assert_awaited_once()
    launcher.launch.assert_awaited_once_with(
        analysis_id=str(analysis_id),
        org_id=str(org_id),
        execution_id=str(analysis.pipeline_execution_id),
    )
    assert events == ["committed", "launched"]


@pytest.mark.asyncio
async def test_run_pipeline_propagates_launch_error_after_persisting_reservation() -> None:
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    analysis = SimpleNamespace(
        status=AnalysisStatus.PENDING,
        pipeline_execution_id=None,
        pipeline_lease_expires_at=None,
    )
    db = AsyncMock()
    query_result = MagicMock()
    query_result.scalar_one_or_none.return_value = analysis
    db.execute.return_value = query_result
    launcher = SimpleNamespace(launch=AsyncMock(side_effect=RuntimeError("launch failed")))

    with (
        patch("api.routes.internal.bind_current_org_to_session", new=AsyncMock()),
        patch(
            "api.services.pipeline_job_launcher.build_pipeline_job_launcher",
            return_value=launcher,
        ),
        pytest.raises(RuntimeError, match="launch failed"),
    ):
        await internal.run_pipeline(
            internal.PipelineRunRequest(analysis_id=analysis_id, org_id=org_id),
            db=db,
            caller_email="tasks@example.iam.gserviceaccount.com",
        )

    db.commit.assert_awaited_once()
    assert analysis.pipeline_execution_id is not None


@pytest.mark.asyncio
async def test_run_pipeline_acknowledges_terminal_analysis_without_launch() -> None:
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    analysis = SimpleNamespace(
        status=AnalysisStatus.COMPLETED,
        pipeline_execution_id=None,
        pipeline_lease_expires_at=None,
    )
    db = AsyncMock()
    query_result = MagicMock()
    query_result.scalar_one_or_none.return_value = analysis
    db.execute.return_value = query_result
    launcher = SimpleNamespace(launch=AsyncMock())

    with (
        patch("api.routes.internal.bind_current_org_to_session", new=AsyncMock()),
        patch(
            "api.services.pipeline_job_launcher.build_pipeline_job_launcher",
            return_value=launcher,
        ),
    ):
        response = await internal.run_pipeline(
            internal.PipelineRunRequest(analysis_id=analysis_id, org_id=org_id),
            db=db,
            caller_email="tasks@example.iam.gserviceaccount.com",
        )

    assert response == {
        "accepted": False,
        "analysis_id": str(analysis_id),
        "execution": "already_completed",
    }
    db.rollback.assert_awaited_once()
    launcher.launch.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_export_executes_before_acknowledging() -> None:
    execute = MagicMock(return_value={"status": "completed", "job_id": "export-1"})
    tasks_module = SimpleNamespace(execute_export_job=execute)

    with patch("api.routes.internal.import_module", return_value=tasks_module):
        response = await internal.run_export(
            internal.ExportRunRequest(export_job_id="export-1", org_id="org-1"),
            caller_email="tasks@example.iam.gserviceaccount.com",
        )

    assert response == {
        "accepted": True,
        "export_job_id": "export-1",
        "execution": "completed",
    }
    execute.assert_called_once_with(export_job_id="export-1", org_id="org-1")


@pytest.mark.asyncio
async def test_run_faithfulness_executes_before_acknowledging() -> None:
    execute = MagicMock(return_value={"status": "completed", "analysis_id": "analysis-1"})
    tasks_module = SimpleNamespace(execute_faithfulness_scores=execute)

    with patch("api.routes.internal.import_module", return_value=tasks_module):
        response = await internal.run_faithfulness(
            internal.FaithfulnessRunRequest(analysis_id="analysis-1", org_id="org-1"),
            caller_email="tasks@example.iam.gserviceaccount.com",
        )

    assert response == {
        "accepted": True,
        "analysis_id": "analysis-1",
        "execution": "completed",
    }
    execute.assert_called_once_with(analysis_id="analysis-1", org_id="org-1")


def test_org_scoped_internal_worker_requests_require_org_id() -> None:
    for model, payload in (
        (internal.PipelineRunRequest, {"analysis_id": "analysis-1"}),
        (internal.ExportRunRequest, {"export_job_id": "export-1"}),
        (internal.FaithfulnessRunRequest, {"analysis_id": "analysis-1"}),
        (internal.MonitorScanRunRequest, {"monitor_id": "monitor-1"}),
        (
            internal.MonitorAlertEmailRunRequest,
            {"user_id": "user-1", "monitor_id": "monitor-1", "alert_id": "alert-1"},
        ),
    ):
        with pytest.raises(ValidationError):
            model(**payload)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_run_monitor_scan_executes_before_acknowledging() -> None:
    execute = MagicMock(return_value={"status": "ok", "monitor_id": "monitor-1"})
    tasks_module = SimpleNamespace(execute_monitor_scan=execute)

    with patch("api.routes.internal.import_module", return_value=tasks_module):
        response = await internal.run_monitor_scan(
            internal.MonitorScanRunRequest(
                monitor_id="monitor-1",
                org_id="org-1",
                force_full_refresh=True,
            ),
            caller_email="tasks@example.iam.gserviceaccount.com",
        )

    assert response == {
        "accepted": True,
        "monitor_id": "monitor-1",
        "execution": "completed",
    }
    execute.assert_called_once_with(
        monitor_id="monitor-1",
        org_id="org-1",
        force_full_refresh=True,
    )


@pytest.mark.asyncio
async def test_run_due_monitor_dispatch_executes_before_acknowledging() -> None:
    dispatch_result = {"due_monitors": 2, "enqueued": 2}
    tasks_module = SimpleNamespace(
        _dispatch_due_monitors_async=AsyncMock(return_value=dispatch_result)
    )

    with patch("api.routes.internal.import_module", return_value=tasks_module):
        response = await internal.run_due_monitor_dispatch(
            caller_email="tasks@example.iam.gserviceaccount.com",
        )

    assert response == {
        "accepted": True,
        "execution": "completed",
    }
    tasks_module._dispatch_due_monitors_async.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_external_report_scheduler_route_only_fans_out_tenant_tasks() -> None:
    dispatch = AsyncMock(
        return_value={
            "organizations": 2,
            "tasks_dispatched": 2,
            "pages": 1,
            "dispatch_concurrency": 16,
        }
    )
    tasks_module = SimpleNamespace(_dispatch_external_report_delivery_reconciliation_async=dispatch)
    with patch("api.routes.internal.import_module", return_value=tasks_module):
        response = await internal.run_external_report_delivery_reconciliation(
            caller_email="scheduler@example.iam.gserviceaccount.com"
        )

    dispatch.assert_awaited_once_with(cursor=None, sweep_id=None)
    assert response["accepted"] is True
    assert response["result"]["tasks_dispatched"] == 2


@pytest.mark.asyncio
async def test_external_report_scheduler_route_resumes_a_durable_cursor() -> None:
    cursor = uuid.uuid4()
    dispatch = AsyncMock(return_value={"tasks_dispatched": 1})
    tasks_module = SimpleNamespace(_dispatch_external_report_delivery_reconciliation_async=dispatch)
    body = internal.ExternalReportDeliverySweepRequest(
        cursor=cursor,
        sweep_id="2026071404-01",
    )
    with patch("api.routes.internal.import_module", return_value=tasks_module):
        response = await internal.run_external_report_delivery_reconciliation(
            body=body,
            caller_email="tasks@example.iam.gserviceaccount.com",
        )

    dispatch.assert_awaited_once_with(
        cursor=str(cursor),
        sweep_id="2026071404-01",
    )
    assert response["accepted"] is True


@pytest.mark.asyncio
async def test_external_report_reconciliation_task_is_tenant_scoped() -> None:
    org_id = uuid.uuid4()
    reconcile = AsyncMock(return_value={"activated": 1})
    tasks_module = SimpleNamespace(_reconcile_external_report_deliveries_for_org=reconcile)
    body = internal.ExternalReportDeliveryReconciliationRequest(
        org_id=org_id,
        dedupe_key=f"{org_id}-2026071404-01",
    )
    with patch("api.routes.internal.import_module", return_value=tasks_module):
        response = await internal.run_external_report_delivery_reconciliation_org(
            body=body,
            caller_email="tasks@example.iam.gserviceaccount.com",
        )

    reconcile.assert_awaited_once_with(
        str(org_id),
        dedupe_key=f"{org_id}-2026071404-01",
        continuation=0,
    )
    assert response == {
        "accepted": True,
        "execution": "completed",
        "result": {"activated": 1},
    }


@pytest.mark.asyncio
async def test_run_monitor_alert_email_executes_before_acknowledging() -> None:
    execute = MagicMock(return_value={"status": "sent", "message_id": "message-1"})
    tasks_module = SimpleNamespace(execute_monitor_alert_email=execute)

    with patch("api.routes.internal.import_module", return_value=tasks_module):
        response = await internal.run_monitor_alert_email(
            internal.MonitorAlertEmailRunRequest(
                user_id="user-1",
                monitor_id="monitor-1",
                alert_id="alert-1",
                org_id="org-1",
            ),
            caller_email="tasks@example.iam.gserviceaccount.com",
        )

    assert response == {
        "accepted": True,
        "alert_id": "alert-1",
        "execution": "completed",
    }
    execute.assert_called_once_with(
        user_id="user-1",
        monitor_id="monitor-1",
        alert_id="alert-1",
        org_id="org-1",
    )


@pytest.mark.asyncio
async def test_run_weekly_digest_executes_before_acknowledging() -> None:
    execute = MagicMock(return_value={"status": "completed", "sent": 1})
    tasks_module = SimpleNamespace(execute_weekly_digest=execute)

    with patch("api.routes.internal.import_module", return_value=tasks_module):
        response = await internal.run_weekly_digest(
            internal.WeeklyDigestRunRequest(dedupe_key="2026-W23"),
            caller_email="tasks@example.iam.gserviceaccount.com",
        )

    assert response == {
        "accepted": True,
        "execution": "completed",
        "dedupe_key": "2026-W23",
    }
    execute.assert_called_once_with()


@pytest.mark.asyncio
async def test_run_weekly_digest_requests_cloud_tasks_retry_for_live_reservation() -> None:
    execute = MagicMock(
        return_value={
            "status": "retry_later",
            "reason": "digest_delivery_reserved",
            "retry_after_seconds": 1860,
        }
    )
    tasks_module = SimpleNamespace(execute_weekly_digest=execute)

    with (
        patch("api.routes.internal.import_module", return_value=tasks_module),
        pytest.raises(RuntimeError, match="digest_delivery_reserved"),
    ):
        await internal.run_weekly_digest(
            internal.WeeklyDigestRunRequest(dedupe_key="2026-W23"),
            caller_email="tasks@example.iam.gserviceaccount.com",
        )

    execute.assert_called_once_with()


@pytest.mark.asyncio
async def test_run_stale_analysis_sweep_executes_reconciliation_before_acknowledging() -> None:
    reconcile = AsyncMock(
        return_value={
            "marked_count": 1,
            "redriven_count": 2,
            "refunded_credits": 1,
            "orgs_checked": 3,
            "error_count": 0,
        }
    )
    maintenance_module = SimpleNamespace(mark_stale_analyses_failed_async=reconcile)

    with patch("api.routes.internal.import_module", return_value=maintenance_module):
        response = await internal.run_stale_analysis_sweep(
            caller_email="scheduler@example.iam.gserviceaccount.com"
        )

    reconcile.assert_awaited_once_with()
    assert response == {
        "accepted": True,
        "execution": "completed",
        "marked_count": 1,
        "redriven_count": 2,
        "refunded_credits": 1,
        "orgs_checked": 3,
        "error_count": 0,
    }


@pytest.mark.asyncio
async def test_run_stale_analysis_sweep_returns_retryable_error_for_partial_failure() -> None:
    reconcile = AsyncMock(
        return_value={
            "marked_count": 0,
            "redriven_count": 0,
            "refunded_credits": 0,
            "orgs_checked": 2,
            "error_count": 1,
        }
    )
    maintenance_module = SimpleNamespace(mark_stale_analyses_failed_async=reconcile)

    with (
        patch("api.routes.internal.import_module", return_value=maintenance_module),
        pytest.raises(internal.APIError) as exc_info,
    ):
        await internal.run_stale_analysis_sweep(
            caller_email="scheduler@example.iam.gserviceaccount.com"
        )

    assert exc_info.value.status == 503
    assert exc_info.value.retry_after_seconds == 60
    assert "1 retryable error" in exc_info.value.detail


def test_execute_export_background_delegates_to_worker_entrypoint() -> None:
    execute = MagicMock(return_value={"status": "completed", "job_id": "export-1"})
    tasks_module = SimpleNamespace(execute_export_job=execute)

    with patch("api.routes.internal.import_module", return_value=tasks_module):
        internal._execute_export_background(export_job_id="export-1", org_id="org-1")

    execute.assert_called_once_with(export_job_id="export-1", org_id="org-1")


def test_execute_faithfulness_background_delegates_to_worker_entrypoint() -> None:
    execute = MagicMock(return_value={"status": "completed", "analysis_id": "analysis-1"})
    tasks_module = SimpleNamespace(execute_faithfulness_scores=execute)

    with patch("api.routes.internal.import_module", return_value=tasks_module):
        internal._execute_faithfulness_background(analysis_id="analysis-1", org_id="org-1")

    execute.assert_called_once_with(analysis_id="analysis-1", org_id="org-1")


def test_execute_monitor_scan_background_delegates_to_worker_entrypoint() -> None:
    execute = MagicMock(return_value={"status": "ok", "monitor_id": "monitor-1"})
    tasks_module = SimpleNamespace(execute_monitor_scan=execute)

    with patch("api.routes.internal.import_module", return_value=tasks_module):
        internal._execute_monitor_scan_background(
            monitor_id="monitor-1",
            org_id="org-1",
            force_full_refresh=True,
        )

    execute.assert_called_once_with(
        monitor_id="monitor-1",
        org_id="org-1",
        force_full_refresh=True,
    )


def test_execute_monitor_alert_email_background_delegates_to_worker_entrypoint() -> None:
    execute = MagicMock(return_value={"status": "sent", "message_id": "message-1"})
    tasks_module = SimpleNamespace(execute_monitor_alert_email=execute)

    with patch("api.routes.internal.import_module", return_value=tasks_module):
        internal._execute_monitor_alert_email_background(
            user_id="user-1",
            monitor_id="monitor-1",
            alert_id="alert-1",
            org_id="org-1",
        )

    execute.assert_called_once_with(
        user_id="user-1",
        monitor_id="monitor-1",
        alert_id="alert-1",
        org_id="org-1",
    )


def test_execute_weekly_digest_background_delegates_to_worker_entrypoint() -> None:
    execute = MagicMock(return_value={"status": "completed", "sent": 1})
    tasks_module = SimpleNamespace(execute_weekly_digest=execute)

    with patch("api.routes.internal.import_module", return_value=tasks_module):
        internal._execute_weekly_digest_background(dedupe_key="2026-W23")

    execute.assert_called_once_with()


def test_execute_faithfulness_background_logs_and_reraises_worker_failure() -> None:
    tasks_module = SimpleNamespace(
        execute_faithfulness_scores=MagicMock(side_effect=RuntimeError("boom"))
    )

    with (
        patch("api.routes.internal.import_module", return_value=tasks_module),
        patch("api.routes.internal.logger") as logger,
        pytest.raises(RuntimeError, match="boom"),
    ):
        internal._execute_faithfulness_background(analysis_id="analysis-1", org_id="org-1")

    logger.error.assert_called_once()


def test_execute_monitor_scan_background_logs_and_reraises_worker_failure() -> None:
    tasks_module = SimpleNamespace(execute_monitor_scan=MagicMock(side_effect=RuntimeError("boom")))

    with (
        patch("api.routes.internal.import_module", return_value=tasks_module),
        patch("api.routes.internal.logger") as logger,
        pytest.raises(RuntimeError, match="boom"),
    ):
        internal._execute_monitor_scan_background(
            monitor_id="monitor-1",
            org_id="org-1",
            force_full_refresh=False,
        )

    logger.error.assert_called_once()


def test_execute_monitor_alert_email_background_logs_and_reraises_worker_failure() -> None:
    tasks_module = SimpleNamespace(
        execute_monitor_alert_email=MagicMock(side_effect=RuntimeError("boom"))
    )

    with (
        patch("api.routes.internal.import_module", return_value=tasks_module),
        patch("api.routes.internal.logger") as logger,
        pytest.raises(RuntimeError, match="boom"),
    ):
        internal._execute_monitor_alert_email_background(
            user_id="user-1",
            monitor_id="monitor-1",
            alert_id="alert-1",
            org_id="org-1",
        )

    logger.error.assert_called_once()


def test_execute_weekly_digest_background_logs_and_reraises_worker_failure() -> None:
    tasks_module = SimpleNamespace(
        execute_weekly_digest=MagicMock(side_effect=RuntimeError("boom"))
    )

    with (
        patch("api.routes.internal.import_module", return_value=tasks_module),
        patch("api.routes.internal.logger") as logger,
        pytest.raises(RuntimeError, match="boom"),
    ):
        internal._execute_weekly_digest_background(dedupe_key="2026-W23")

    logger.error.assert_called_once()


def test_execute_export_background_logs_and_reraises_worker_failure() -> None:
    tasks_module = SimpleNamespace(execute_export_job=MagicMock(side_effect=RuntimeError("boom")))

    with (
        patch("api.routes.internal.import_module", return_value=tasks_module),
        patch("api.routes.internal.logger") as logger,
        pytest.raises(RuntimeError, match="boom"),
    ):
        internal._execute_export_background(export_job_id="export-1", org_id="org-1")

    logger.error.assert_called_once()


def test_execute_export_background_raises_failed_worker_result() -> None:
    execute = MagicMock(return_value={"status": "failed", "error": "export_failed"})
    tasks_module = SimpleNamespace(execute_export_job=execute)

    with (
        patch("api.routes.internal.import_module", return_value=tasks_module),
        patch("api.routes.internal.logger") as logger,
        pytest.raises(RuntimeError, match="Export worker failed for export-1: export_failed"),
    ):
        internal._execute_export_background(export_job_id="export-1", org_id="org-1")

    execute.assert_called_once_with(export_job_id="export-1", org_id="org-1")
    logger.error.assert_called_once()


def test_execute_export_background_terminal_blocked_completes_without_raise() -> None:
    blocked_result = {"status": "blocked", "error": "export_org_mismatch"}
    execute = MagicMock(return_value=blocked_result)
    tasks_module = SimpleNamespace(execute_export_job=execute)

    with (
        patch("api.routes.internal.import_module", return_value=tasks_module),
        patch("api.routes.internal.logger") as logger,
    ):
        result = internal._execute_export_background(export_job_id="export-1", org_id="org-1")

    assert result == blocked_result
    execute.assert_called_once_with(export_job_id="export-1", org_id="org-1")
    logger.error.assert_not_called()


def test_execute_export_background_raises_retry_later_worker_result() -> None:
    execute = MagicMock(
        return_value={
            "status": "retry_later",
            "reason": "processing_lease_active",
            "retry_after_seconds": 30,
        }
    )
    tasks_module = SimpleNamespace(execute_export_job=execute)

    with (
        patch("api.routes.internal.import_module", return_value=tasks_module),
        patch("api.routes.internal.logger") as logger,
        pytest.raises(
            RuntimeError,
            match="Export worker failed for export-1: processing_lease_active",
        ),
    ):
        internal._execute_export_background(export_job_id="export-1", org_id="org-1")

    execute.assert_called_once_with(export_job_id="export-1", org_id="org-1")
    logger.error.assert_called_once()


def test_execute_faithfulness_background_terminal_blocked_completes_without_raise() -> None:
    blocked_result = {"status": "blocked", "analysis_id": "analysis-1"}
    execute = MagicMock(return_value=blocked_result)
    tasks_module = SimpleNamespace(execute_faithfulness_scores=execute)

    with (
        patch("api.routes.internal.import_module", return_value=tasks_module),
        patch("api.routes.internal.logger") as logger,
    ):
        result = internal._execute_faithfulness_background(analysis_id="analysis-1", org_id="org-1")

    assert result == blocked_result
    execute.assert_called_once_with(analysis_id="analysis-1", org_id="org-1")
    logger.error.assert_not_called()
