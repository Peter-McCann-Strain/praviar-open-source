from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from praviar_pipeline.logging_config import (
    _get_log_truncation_max,
    _get_model_pricing,
    _resolve_log_level,
)
from praviar_pipeline.ocsr.runner import OCSRRunner
from praviar_pipeline.pipeline.analysis.orchestration_results import (
    build_analysis_failure,
    log_analysis_failure,
)
from praviar_pipeline.pipeline.report_verifier import verify_report
from praviar_pipeline.pipeline.runtime.live_collector_context import (
    collect_uspto_odp_runtime_context_impl,
)
from praviar_pipeline.pipeline.runtime.live_collector_helpers import failed_entry


def _credential_error(sentinel: str) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", f"https://provider.test/data?api_key={sentinel}")
    response = httpx.Response(500, request=request, text=f"echoed={sentinel}")
    return httpx.HTTPStatusError(
        "provider failed",
        request=request,
        response=response,
    )


def _assert_logger_has_no_sentinel(logger: MagicMock, sentinel: str) -> None:
    for call in logger.method_calls:
        assert sentinel not in repr((call.args, call.kwargs))


@pytest.mark.parametrize(
    ("function", "expected"),
    [
        (_get_log_truncation_max, 1000),
        (_resolve_log_level, "INFO"),
        (_get_model_pricing, {}),
    ],
)
def test_early_settings_failures_never_log_exception_text(function, expected) -> None:
    sentinel = "settings-error-embedded-secret-sentinel"
    recording_logger = MagicMock()

    with (
        patch(
            "praviar_pipeline.config.get_settings",
            side_effect=RuntimeError(sentinel),
        ),
        patch(
            "praviar_pipeline.logging_config.logging.getLogger",
            return_value=recording_logger,
        ),
    ):
        assert function() == expected

    _assert_logger_has_no_sentinel(recording_logger, sentinel)


def test_analysis_failure_serialization_and_logs_are_secret_safe() -> None:
    sentinel = "analysis-bearer-and-confidential-claim-sentinel"
    provider_error = _credential_error(sentinel)
    recording_logger = MagicMock()

    failure = build_analysis_failure(
        patent_id="US123",
        error=provider_error,
        settings=SimpleNamespace(analysis_error_msg_max_chars=256),
    )
    log_analysis_failure(
        patent=SimpleNamespace(patent_id="US123"),
        error=provider_error,
        logger=recording_logger,
    )

    assert sentinel not in failure.model_dump_json()
    assert failure.error_type == "HTTPStatusError"
    assert failure.error_message == "patent analysis failed (HTTPStatusError)"
    _assert_logger_has_no_sentinel(recording_logger, sentinel)


@pytest.mark.asyncio
async def test_live_collector_health_and_logs_are_secret_safe() -> None:
    sentinel = "live-collector-query-credential-sentinel"
    provider_error = _credential_error(sentinel)
    recording_logger = MagicMock()

    async def _fetch(_patent_id: str):
        raise provider_error

    with patch(
        "praviar_pipeline.pipeline.runtime.live_collector_context.logger",
        recording_logger,
    ):
        entry, cache = await collect_uspto_odp_runtime_context_impl(
            patent_ids=["US123"],
            prosecution_cache={},
            fetch_prosecution_context_fn=_fetch,
        )

    direct_entry = failed_entry("family_record", provider_error)
    serialized = entry.model_dump_json() + direct_entry.model_dump_json()
    assert sentinel not in serialized
    assert "HTTPStatusError" in serialized
    assert cache == {}
    _assert_logger_has_no_sentinel(recording_logger, sentinel)


@pytest.mark.asyncio
async def test_report_verifier_provider_errors_never_reach_logs() -> None:
    sentinel = "verifier-bearer-customer-prompt-sentinel"
    provider_error = _credential_error(sentinel)
    claude = MagicMock()
    claude._models.analysis = "test-model"
    claude.load_prompt.return_value = "system"
    claude.complete_text = AsyncMock(side_effect=[provider_error, provider_error])
    recording_logger = MagicMock()

    with (
        patch(
            "praviar_pipeline.pipeline.report_verifier.get_settings",
            return_value=SimpleNamespace(report_verification_enabled=True),
        ),
        patch(
            "praviar_pipeline.pipeline.report_verifier.logger",
            recording_logger,
        ),
    ):
        result, input_tokens, output_tokens = await verify_report(
            claude,
            f"confidential report {sentinel}",
            MagicMock(),
        )

    assert result.overall_assessment == "ERROR"
    assert input_tokens == 0
    assert output_tokens == 0
    _assert_logger_has_no_sentinel(recording_logger, sentinel)


@pytest.mark.asyncio
async def test_ocsr_worker_env_and_stderr_are_secret_safe(tmp_path, monkeypatch) -> None:
    sentinel = "ocsr-inherited-api-key-and-structure-sentinel"
    monkeypatch.setenv("OPENAI_API_KEY", sentinel)
    venv = tmp_path / "venv"
    python_path = venv / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("")
    worker = tmp_path / "worker.py"
    worker.write_text("")
    image = tmp_path / "structure.png"
    image.write_bytes(b"png")

    process = MagicMock()
    process.returncode = 9
    process.communicate = AsyncMock(return_value=(b"", f"stderr echoed {sentinel}".encode()))
    create_process = AsyncMock(return_value=process)
    recording_logger = MagicMock()
    runner = OCSRRunner(
        venv_path=venv,
        worker_script=worker,
        tool_name="test-tool",
        env_vars={"OPENAI_API_KEY": sentinel},
    )

    with (
        patch(
            "praviar_pipeline.ocsr.runner.asyncio.create_subprocess_exec",
            create_process,
        ),
        patch("praviar_pipeline.ocsr.runner.logger", recording_logger),
    ):
        result = await runner.predict(image)

    child_env = create_process.await_args.kwargs["env"]
    assert "OPENAI_API_KEY" not in child_env
    assert sentinel not in result.model_dump_json()
    assert "stderr_sha256=" in result.error
    _assert_logger_has_no_sentinel(recording_logger, sentinel)
