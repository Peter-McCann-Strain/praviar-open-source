"""Centralized logging configuration for the Praviar Pipeline pipeline.

Provides:
- structlog with contextvars for correlation IDs across async tasks
- Dev mode: pretty console output with colors
- Prod mode: JSON lines for log aggregators (Datadog, ELK, etc.)
- Truncation of large values to prevent prompt/response blowup in logs
- Pipeline-scoped context binding (run_id, compound metadata, step)
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import uuid
from typing import Any

import structlog

from praviar_pipeline.logging_processors import (
    add_otel_context,
    add_service_context,
    mask_secret_values,
    truncate_event_values,
)
from praviar_pipeline.logging_runtime import ProgressTracker, StepTimer

__all__ = [
    "ProgressTracker",
    "StepTimer",
    "bind_compound_context",
    "bind_pipeline_context",
    "bind_step_context",
    "configure_logging",
    "log_llm_call",
]

# ── Custom Processors ────────────────────────────────────────────────────────


def _get_log_truncation_max() -> int:
    """Get log truncation max from settings (fallback to 1000 if settings unavailable).

    Settings may not be importable during early startup (circular import),
    so we catch ImportError/RuntimeError and fall back to env var / default.
    """
    try:
        from praviar_pipeline.config import get_settings

        return get_settings().log_truncation_max_chars
    except (
        Exception
    ) as exc:  # Intentional broad catch: Settings can fail many ways during early startup
        # This is expected during early startup before Settings is ready.
        # Use stdlib logging since structlog may not be configured yet.
        logging.getLogger("praviar_pipeline.logging_config").debug(
            "Settings unavailable for log_truncation_max, using default 1000: %s",
            type(exc).__name__,
        )
        return 1000


def _mask_secrets(
    logger: Any,
    method_name: str,
    event_dict: dict,
) -> dict:
    """Redact known secret patterns from all string values in log events."""
    return mask_secret_values(event_dict)


def _truncate_large_values(
    logger: Any,
    method_name: str,
    event_dict: dict,
) -> dict:
    """Truncate any string value over the configured max chars to prevent log blowup."""
    return truncate_event_values(event_dict, max_len=_get_log_truncation_max())


def _add_otel_context(
    logger: Any,
    method_name: str,
    event_dict: dict,
) -> dict:
    """Inject OpenTelemetry trace_id and span_id into every log event.

    Degrades gracefully if opentelemetry-api is not installed.
    """
    return add_otel_context(event_dict)


def _add_service_context(
    logger: Any,
    method_name: str,
    event_dict: dict,
) -> dict:
    """Add service-level metadata to every log event."""
    return add_service_context(event_dict, service="praviar_pipeline")


# ── Configuration ────────────────────────────────────────────────────────────


def _resolve_log_level() -> str:
    """Resolve log level from Settings, falling back to os.getenv if Settings is unavailable.

    Settings is the single source of truth, but logging may be configured
    before Settings is importable (e.g. during module-level initialization).
    """
    try:
        from praviar_pipeline.config import get_settings

        level = get_settings().log_level
        return level.upper()
    except (
        Exception
    ) as exc:  # Intentional broad catch: Settings can fail many ways during early startup
        # Fall back to env var only when Settings fails to load
        fallback = os.getenv("LOG_LEVEL", "INFO").upper()
        logging.getLogger("praviar_pipeline.logging_config").warning(
            "Settings unavailable for log_level, falling back to LOG_LEVEL env var (%s): %s",
            fallback,
            type(exc).__name__,
        )
        return fallback


def configure_logging(*, debug: bool | None = None) -> None:
    """Configure structlog for the Praviar Pipeline pipeline.

    Call once at startup. Uses Settings.log_level (preferred) or LOG_LEVEL
    env var (fallback when Settings is not yet available).

    Args:
        debug: Force debug mode. If None, auto-detect from Settings/LOG_LEVEL.
    """
    if debug is None:
        log_level_str = _resolve_log_level()
        debug = log_level_str == "DEBUG"

    log_level = logging.DEBUG if debug else getattr(logging, _resolve_log_level(), logging.INFO)

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,  # MUST be first — picks up bind_contextvars()
        _add_otel_context,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_service_context,
        _mask_secrets,
        _truncate_large_values,
    ]

    if debug or sys.stderr.isatty():
        # Dev: pretty console with colors
        processors.append(
            structlog.dev.ConsoleRenderer(
                exception_formatter=structlog.dev.RichTracebackFormatter(show_locals=False),
            )
        )
    else:
        # Prod: JSON lines for log aggregators
        processors.extend(
            [
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ]
        )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


# ── Pipeline Context Helpers ─────────────────────────────────────────────────


def bind_pipeline_context(*, compound_input: str) -> str:
    """Bind pipeline-scoped context. Returns the generated run_id.

    Call at the start of each pipeline run. All subsequent log calls
    in any file will include these fields automatically. Compound inputs are
    confidential customer material, so only metadata is attached.
    """
    run_id = str(uuid.uuid4())[:8]
    stripped = compound_input.strip()
    input_type = "smiles_like" if any(ch in stripped for ch in "=#[]()@") else "text_identifier"
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        run_id=run_id,
        compound_input_sha256=hashlib.sha256(compound_input.encode("utf-8")).hexdigest(),
        compound_input_length=len(compound_input),
        compound_input_type=input_type,
    )
    return run_id


def bind_step_context(step: str) -> None:
    """Bind the current pipeline step to log context."""
    structlog.contextvars.bind_contextvars(step=step)


def bind_compound_context(*, name: str, cid: int) -> None:
    """Bind non-identifying resolved-compound metadata after step 1."""
    structlog.contextvars.bind_contextvars(
        resolved_compound_name_length=len(name),
        resolved_compound_cid_present=cid > 0,
    )


# ── LLM Call Logger ──────────────────────────────────────────────────────────


def _get_model_pricing() -> dict[str, tuple[float, float]]:
    """Get model pricing from settings (single source of truth).

    Falls back to empty dict if Settings is unavailable, and logs a warning
    so the caller knows pricing data is missing.
    """
    try:
        from praviar_pipeline.config import get_settings

        s = get_settings()
        return {
            s.claude_deep_model: (s.cost_per_million_input_opus, s.cost_per_million_output_opus),
            s.claude_analysis_model: (
                s.cost_per_million_input_sonnet,
                s.cost_per_million_output_sonnet,
            ),
            s.claude_triage_model: (
                s.cost_per_million_input_haiku,
                s.cost_per_million_output_haiku,
            ),
        }
    except (
        Exception
    ) as exc:  # Intentional broad catch: Settings can fail many ways during early startup
        logging.getLogger("praviar_pipeline.logging_config").warning(
            "Settings unavailable for model pricing — fallback defaults in use: %s",
            type(exc).__name__,
        )
        return {}


def log_llm_call(
    *,
    purpose: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    duration_s: float,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    tool_calls: int = 0,
    stop_reason: str = "",
) -> float:
    """Log a single LLM API call with token usage and cost.

    Returns the estimated cost in USD.
    """
    pricing = _get_model_pricing()
    input_price, output_price = pricing.get(model, (3.0, 15.0))
    cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000

    structlog.get_logger().info(
        "llm_call",
        purpose=purpose,
        model=model.split("-")[-1] if "-" in model else model,  # short name
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_creation_tokens=cache_creation_tokens,
        cost_usd=round(cost, 4),
        duration_s=round(duration_s, 2),
        tool_calls=tool_calls,
        stop_reason=stop_reason,
    )
    return cost
