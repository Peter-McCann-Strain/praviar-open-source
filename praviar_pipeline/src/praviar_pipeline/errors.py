"""Custom exception hierarchy for Praviar Pipeline pipeline.

Every exception carries structured metadata (source, step) so callers can
build SourceHealth records without parsing error messages.
"""

from __future__ import annotations


class PraviarPipelineError(Exception):
    """Base exception for all Praviar Pipeline errors."""

    def __init__(
        self,
        message: str,
        *,
        source: str = "",
        step: str = "",
    ) -> None:
        self.source = source
        self.step = step
        super().__init__(message)


# ── Search errors ────────────────────────────────────────────────────────────


class SearchError(PraviarPipelineError):
    """Error during patent search phase."""


class AllSourcesFailedError(SearchError):
    """Every search source failed — no patents to analyze."""

    def __init__(self, failures: dict[str, str]) -> None:
        self.failures = failures
        detail = "; ".join(f"{k}: {v}" for k, v in failures.items())
        super().__init__(
            f"All search sources failed: {detail}",
            step="search",
        )


class SearchSourceFailedError(SearchError):
    """One or more required search sources failed or were not configured."""

    def __init__(self, failures: dict[str, str]) -> None:
        self.failures = failures
        detail = "; ".join(f"{k}: {v}" for k, v in failures.items())
        super().__init__(
            f"Required search source failure: {detail}",
            step="search",
        )


# ── Client errors ────────────────────────────────────────────────────────────


class ClientError(PraviarPipelineError):
    """Error communicating with an external API."""


class RetryableError(PraviarPipelineError):
    """Transient error that may succeed on retry.

    Use isinstance(exc, RetryableError) to decide whether to retry
    or mark as permanent failure in AnalysisFailure.recoverable.
    """


class AuthenticationError(ClientError):
    """API key is missing, invalid, or expired."""


class EPOCredentialsMissingError(AuthenticationError):
    """EPO OPS consumer key/secret is not configured.

    Distinct from ``AuthenticationError`` (credentials present but rejected) so
    orchestrators can mark EPO OPS as NOT_CONFIGURED rather than FAILED
    (source outage). Subclass of ``AuthenticationError`` so existing
    ``AuthenticationError`` handlers still cover it.
    """

    def __init__(self, detail: str = "EPO OPS consumer key/secret not configured") -> None:
        super().__init__(detail, source="epo_ops")


class PatCIDDatabaseNotFoundError(ClientError):
    """PatCID SQLite database file not found."""

    def __init__(self, path: str) -> None:
        super().__init__(
            f"PatCID database not found at: {path}",
            source="patcid",
        )


class SourceUnavailableError(ClientError):
    """A data source failed in a way that means its results are missing from this run.

    Raise when a 404/5xx/timeout/parse-error prevents the client from
    delivering data the pipeline would otherwise use. The orchestrator
    (pipeline.search.orchestration.run_source) catches this and records
    a SourceHealthEntry(status=FAILED), so the report can surface the gap
    instead of silently omitting results.

    Do NOT raise for semantic "not found" cases (e.g., a compound name the
    API legitimately does not know) — those are expected empty results,
    not source failures.
    """

    def __init__(
        self,
        source: str,
        detail: str,
        *,
        status_code: int | None = None,
    ) -> None:
        self.detail = detail
        self.status_code = status_code
        message = (
            f"{source} unavailable: {detail} (HTTP {status_code})"
            if status_code is not None
            else f"{source} unavailable: {detail}"
        )
        super().__init__(message, source=source, step="client")


# ── Configuration / data errors ──────────────────────────────────────────────


class ConfigurationError(PraviarPipelineError):
    """Invalid or incomplete configuration (caught at startup)."""


class InsufficientDataError(PraviarPipelineError):
    """Not enough data to produce a reliable report."""


class InvalidityAssessmentError(PraviarPipelineError):
    """A required invalidity assessment operation failed.

    The message is deliberately fixed. Upstream failures may embed request
    URLs, query strings, or credentials in their exception text, so callers
    must retain only separately structured, non-sensitive diagnostics.
    """

    def __init__(self, *, failure_types: tuple[str, ...] = ()) -> None:
        self.failure_types = failure_types
        super().__init__(
            "Invalidity assessment failed",
            step="invalidity",
        )


class DoEAssessmentError(PraviarPipelineError):
    """A required doctrine-of-equivalents candidate assessment failed."""

    def __init__(self, *, failure_types: tuple[str, ...] = ()) -> None:
        self.failure_types = failure_types
        super().__init__(
            "Doctrine-of-equivalents assessment failed",
            step="doe",
        )


class DrawingAnalysisError(PraviarPipelineError):
    """A required configured drawing analysis operation failed."""

    def __init__(self, *, failure_types: tuple[str, ...] = ()) -> None:
        self.failure_types = failure_types
        super().__init__(
            "Patent drawing analysis failed",
            step="drawing_analysis",
        )


class DrawingExecutionError(PraviarPipelineError):
    """A live drawing stage failed before trustworthy evidence was produced."""

    def __init__(
        self,
        message: str,
        *,
        step: str,
        failure_types: tuple[str, ...] = (),
    ) -> None:
        self.failure_types = failure_types
        super().__init__(message, step=step)


class DrawingAcquisitionError(DrawingExecutionError):
    """Live drawing-page acquisition failed without a successful fallback."""

    def __init__(self, *, failure_types: tuple[str, ...] = ()) -> None:
        super().__init__(
            "Patent drawing acquisition failed",
            step="drawing_acquisition",
            failure_types=failure_types,
        )


class DrawingSegmentationError(DrawingExecutionError):
    """Live drawing segmentation failed for at least one fetched page."""

    def __init__(self, *, failure_types: tuple[str, ...] = ()) -> None:
        super().__init__(
            "Patent drawing segmentation failed",
            step="drawing_segmentation",
            failure_types=failure_types,
        )


class PipelineCancelledError(PraviarPipelineError):
    """Pipeline execution was cancelled by the caller."""


class RuntimeBudgetExceededError(PraviarPipelineError):
    """Pipeline exceeded its configured runtime budget."""

    def __init__(
        self,
        message: str,
        *,
        step: str = "",
        deadline_epoch: float | None = None,
        elapsed_seconds: float | None = None,
    ) -> None:
        self.deadline_epoch = deadline_epoch
        self.elapsed_seconds = elapsed_seconds
        super().__init__(message, step=step)


class PaidCallBudgetExceededError(PraviarPipelineError):
    """A paid provider call would exceed the configured per-run hard budget."""

    def __init__(
        self,
        message: str,
        *,
        model: str = "",
        projected_usd: float | None = None,
        hard_budget_usd: float | None = None,
    ) -> None:
        self.projected_usd = projected_usd
        self.hard_budget_usd = hard_budget_usd
        super().__init__(message, source=model, step="paid_call_budget")


class LLMResponseError(PraviarPipelineError):
    """LLM returned unparseable or invalid response."""

    def __init__(self, message: str, *, model: str = "", step: str = ""):
        super().__init__(message, source=model, step=step)


class RateLimitError(RetryableError, ClientError):
    """Persistent rate limit exceeded after retries."""


class ReportIntegrityError(PraviarPipelineError):
    """Deterministic post-verification check found a blocking inconsistency.

    Raised after the LLM verification layer when a rule-based check
    (see ``pipeline.report.deterministic_checks``) detects a hard
    inconsistency that makes the report unsafe to publish — e.g.
    ``claims_analyzed > total_claims`` or overall risk downgraded below
    per-patent max risk. The orchestrator catches this and marks the
    analysis as FAILED with the violation details.
    """

    def __init__(
        self,
        message: str,
        *,
        violations: list[dict] | None = None,
        step: str = "report_verification",
    ) -> None:
        self.violations = violations or []
        super().__init__(message, step=step)
