"""Result-collection helpers for batch patent analysis."""

from __future__ import annotations

from praviar_pipeline.models.report import AnalysisFailure
from praviar_pipeline.utils.safe_diagnostics import (
    safe_exception_type,
    safe_failure_message,
)


def build_analysis_failure(*, patent_id: str, error: BaseException, settings) -> AnalysisFailure:
    diagnostic = safe_failure_message("patent analysis", error)
    return AnalysisFailure(
        patent_id=patent_id,
        step="step4_analyze",
        error_type=safe_exception_type(error),
        error_message=diagnostic[: settings.analysis_error_msg_max_chars],
        recoverable=isinstance(error, (ConnectionError, TimeoutError)),
    )


def log_analysis_failure(*, patent, error: BaseException, logger) -> None:
    logger.error(
        "patent_analysis_failed",
        error_type=safe_exception_type(error),
    )


def log_batch_summary(*, analyses: list, failures: list, compound_name: str, logger) -> None:
    if failures:
        logger.error(
            "analysis_failures_total",
            count=len(failures),
        )

    logger.info(
        "deep_analysis_complete",
        analyzed=len(analyses),
        failed=len(failures),
        high_risk=sum(1 for analysis in analyses if analysis.risk_level.value == "high"),
        medium_risk=sum(1 for analysis in analyses if analysis.risk_level.value == "medium"),
    )
