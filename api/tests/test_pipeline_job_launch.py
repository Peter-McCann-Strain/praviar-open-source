"""Durable Cloud Tasks → Cloud Run Jobs pipeline handoff contracts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from api.db.models import AnalysisStatus
from api.services.pipeline_job_launcher import CloudRunPipelineJobLauncher
from api.services.pipeline_launch import (
    PIPELINE_JOB_LAUNCH_RESERVATION_TTL,
    reserve_pipeline_job_execution,
)


def _analysis(**overrides):
    values = {
        "status": AnalysisStatus.PENDING,
        "pipeline_execution_id": None,
        "pipeline_lease_expires_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_pipeline_job_reservation_reuses_execution_fence_for_duplicate_delivery() -> None:
    now = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
    analysis = _analysis()

    first = reserve_pipeline_job_execution(analysis, now=now)
    repeated = reserve_pipeline_job_execution(
        analysis,
        now=now + timedelta(minutes=1),
    )

    assert first.launchable is True
    assert first.reused is False
    assert repeated.execution_id == first.execution_id
    assert repeated.reused is True
    assert analysis.pipeline_lease_expires_at == now + PIPELINE_JOB_LAUNCH_RESERVATION_TTL


def test_pipeline_job_reservation_replaces_expired_execution_fence() -> None:
    now = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
    stale_execution_id = uuid.uuid4()
    analysis = _analysis(
        pipeline_execution_id=stale_execution_id,
        pipeline_lease_expires_at=now - timedelta(seconds=1),
    )

    replacement = reserve_pipeline_job_execution(analysis, now=now)

    assert replacement.execution_id != stale_execution_id
    assert replacement.reused is False
    assert analysis.pipeline_execution_id == replacement.execution_id


def test_pipeline_job_reservation_does_not_relaunch_terminal_analysis() -> None:
    analysis = _analysis(status=AnalysisStatus.COMPLETED)

    reservation = reserve_pipeline_job_execution(analysis)

    assert reservation.status == "already_completed"
    assert reservation.launchable is False


@pytest.mark.asyncio
async def test_cloud_run_job_launcher_posts_fenced_environment_without_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = MagicMock()
    response.json.return_value = {
        "name": "projects/project-1/locations/us-central1/operations/op-1"
    }
    session = MagicMock()
    session.post.return_value = response
    google_auth = SimpleNamespace(default=MagicMock(return_value=(object(), "project-1")))
    google_requests = SimpleNamespace(AuthorizedSession=MagicMock(return_value=session))

    def import_fake(name: str):
        return google_auth if name == "google.auth" else google_requests

    monkeypatch.setattr(
        "api.services.pipeline_job_launcher.import_module",
        import_fake,
    )
    launcher = CloudRunPipelineJobLauncher(
        job_name="projects/project-1/locations/us-central1/jobs/pipeline-worker",
        hard_budget_usd=15.0,
    )

    receipt = await launcher.launch(
        analysis_id="analysis-1",
        org_id="org-1",
        execution_id="execution-1",
    )

    assert receipt.operation_name.endswith("/operations/op-1")
    payload = session.post.call_args.kwargs["json"]
    environment = {
        item["name"]: item["value"] for item in payload["overrides"]["containerOverrides"][0]["env"]
    }
    assert environment == {
        "PRAVIAR_PIPELINE_ANALYSIS_ID": "analysis-1",
        "PRAVIAR_PIPELINE_ORG_ID": "org-1",
        "PRAVIAR_PIPELINE_EXECUTION_ID": "execution-1",
        "PIPELINE_LLM_HARD_BUDGET_USD": "15",
    }
    response.raise_for_status.assert_called_once_with()
    session.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_cloud_run_job_launcher_rejects_response_without_operation_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = MagicMock()
    response.json.return_value = {}
    session = MagicMock()
    session.post.return_value = response
    google_auth = SimpleNamespace(default=MagicMock(return_value=(object(), "project-1")))
    google_requests = SimpleNamespace(AuthorizedSession=MagicMock(return_value=session))
    monkeypatch.setattr(
        "api.services.pipeline_job_launcher.import_module",
        lambda name: google_auth if name == "google.auth" else google_requests,
    )
    launcher = CloudRunPipelineJobLauncher(
        job_name="projects/project-1/locations/us-central1/jobs/pipeline-worker",
        hard_budget_usd=15.0,
    )

    with pytest.raises(RuntimeError, match="omitted the operation name"):
        await launcher.launch(
            analysis_id="analysis-1",
            org_id="org-1",
            execution_id="execution-1",
        )
