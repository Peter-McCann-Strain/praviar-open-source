"""Small OpenTelemetry span helpers for business-operation instrumentation."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from importlib import import_module
from typing import Any

ScalarAttribute = str | bool | int | float


def _safe_attributes(attributes: Mapping[str, object] | None) -> dict[str, ScalarAttribute]:
    safe: dict[str, ScalarAttribute] = {}
    for key, value in (attributes or {}).items():
        if isinstance(value, str | bool | int | float):
            safe[key] = value
    return safe


def set_current_span_attributes(attributes: Mapping[str, object] | None) -> None:
    """Attach non-sensitive scalar attributes to the active span when OTEL is available."""
    safe = _safe_attributes(attributes)
    if not safe:
        return
    try:
        trace = import_module("opentelemetry.trace")
        span = trace.get_current_span()
        if span is not None:
            span.set_attributes(safe)
    except Exception:
        return


@contextmanager
def start_span(name: str, attributes: Mapping[str, object] | None = None) -> Iterator[Any | None]:
    """Start an OTEL span if tracing is installed/configured; otherwise no-op."""
    try:
        trace = import_module("opentelemetry.trace")
        tracer = trace.get_tracer("api")
    except Exception:
        yield None
        return

    with tracer.start_as_current_span(name) as span:
        safe = _safe_attributes(attributes)
        if safe:
            span.set_attributes(safe)
        yield span


def record_span_exception(span: Any | None, exc: BaseException) -> None:
    """Record an exception on a span without making observability a runtime dependency."""
    if span is None:
        return
    try:
        span.record_exception(exc)
        span.set_attribute("error.type", type(exc).__name__)
    except Exception:
        return
