"""Short control-plane launcher for durable Cloud Run Job pipeline execution."""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import import_module
from typing import Any
from urllib.parse import quote

import structlog

from api.services.blocking_sdk import run_blocking_sdk_call

logger = structlog.get_logger()

PIPELINE_JOB_LAUNCH_TIMEOUT_SECONDS = 10.0
_CLOUD_RUN_JOB_NAME_PATTERN = re.compile(
    r"^projects/(?:[a-z][a-z0-9-]{4,28}[a-z0-9]|[0-9]{6,20})/"
    r"locations/[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?/"
    r"jobs/[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)


@dataclass(frozen=True, slots=True)
class PipelineJobLaunchReceipt:
    """Provider receipt returned after Cloud Run durably accepts a Job execution."""

    operation_name: str


def validate_pipeline_cloud_run_job_name(value: str) -> str:
    """Validate a full Cloud Run v2 Job resource name before building a request URL."""
    normalized = str(value or "").strip()
    if not _CLOUD_RUN_JOB_NAME_PATTERN.fullmatch(normalized):
        raise ValueError(
            "PIPELINE_CLOUD_RUN_JOB_NAME must be a full resource name in the form "
            "projects/{project}/locations/{location}/jobs/{job}"
        )
    return normalized


class CloudRunPipelineJobLauncher:
    """Launch one Cloud Run Job execution without waiting for the data plane."""

    def __init__(self, *, job_name: str, hard_budget_usd: float) -> None:
        self._job_name = validate_pipeline_cloud_run_job_name(job_name)
        if hard_budget_usd <= 0:
            raise ValueError("pipeline LLM hard budget must be positive")
        self._hard_budget_usd = hard_budget_usd

    async def launch(
        self,
        *,
        analysis_id: str,
        org_id: str,
        execution_id: str,
    ) -> PipelineJobLaunchReceipt:
        """Start a Job execution and return only its long-running-operation receipt."""

        def launch_once() -> PipelineJobLaunchReceipt:
            google_auth = import_module("google.auth")
            google_requests = import_module("google.auth.transport.requests")
            credentials, _project_id = google_auth.default(
                scopes=("https://www.googleapis.com/auth/cloud-platform",)
            )
            session = google_requests.AuthorizedSession(credentials)
            try:
                response = session.post(
                    f"https://run.googleapis.com/v2/{quote(self._job_name, safe='/')}:run",
                    json={
                        "overrides": {
                            "containerOverrides": [
                                {
                                    "env": [
                                        {
                                            "name": "PRAVIAR_PIPELINE_ANALYSIS_ID",
                                            "value": analysis_id,
                                        },
                                        {
                                            "name": "PRAVIAR_PIPELINE_ORG_ID",
                                            "value": org_id,
                                        },
                                        {
                                            "name": "PRAVIAR_PIPELINE_EXECUTION_ID",
                                            "value": execution_id,
                                        },
                                        {
                                            "name": "PIPELINE_LLM_HARD_BUDGET_USD",
                                            "value": format(self._hard_budget_usd, ".15g"),
                                        },
                                    ]
                                }
                            ]
                        }
                    },
                    timeout=PIPELINE_JOB_LAUNCH_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                payload: Any = response.json()
            finally:
                session.close()

            operation_name = (
                str(payload.get("name") or "").strip() if isinstance(payload, dict) else ""
            )
            if not operation_name:
                raise RuntimeError("Cloud Run Jobs launch response omitted the operation name")
            return PipelineJobLaunchReceipt(operation_name=operation_name)

        receipt = await run_blocking_sdk_call(
            "cloud_run_jobs.run",
            launch_once,
            timeout_seconds=PIPELINE_JOB_LAUNCH_TIMEOUT_SECONDS,
            max_attempts=1,
            logger_override=logger,
        )
        logger.info(
            "pipeline_job_launcher.accepted",
            analysis_id=analysis_id,
            org_id=org_id,
            execution_id=execution_id,
            operation_name=receipt.operation_name,
        )
        return receipt


def build_pipeline_job_launcher() -> CloudRunPipelineJobLauncher:
    """Build the production Job launcher from the explicit runtime contract."""
    from api.config import get_settings

    settings = get_settings()
    if settings.pipeline_llm_hard_budget_usd is None:
        raise RuntimeError("PIPELINE_LLM_HARD_BUDGET_USD is required for Job launches")
    return CloudRunPipelineJobLauncher(
        job_name=settings.pipeline_cloud_run_job_name,
        hard_budget_usd=settings.pipeline_llm_hard_budget_usd,
    )
