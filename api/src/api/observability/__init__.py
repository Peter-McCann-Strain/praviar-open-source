"""Observability — OTEL tracing + structured logging.

The OTEL exporter ships traces to Honeycomb via OTLP/HTTP. Cloud Run also
ingests traces locally into Cloud Trace via the runtime SA's
`roles/cloudtrace.agent`.

Per 10-gcp-architecture.md §8.
"""

from api.observability.otel import configure_otel, shutdown_otel

__all__ = ["configure_otel", "shutdown_otel"]
