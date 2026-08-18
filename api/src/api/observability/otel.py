"""OpenTelemetry setup — traces to Honeycomb (OTLP/HTTP) + Cloud Trace.

Wires OTEL instrumentation into FastAPI + SQLAlchemy + asyncio:
    - FastAPI request spans
    - SQLAlchemy query spans (server-side query timing)
    - httpx outbound spans (for external API calls)
    - Anthropic / OpenAI SDK spans where instrumented

Exporter strategy:
    - Honeycomb via OTLP/HTTP (`HONEYCOMB_API_KEY` secret)
    - Cloud Trace via Cloud Run runtime SA (`roles/cloudtrace.agent`, no API key)

Both exporters can be enabled simultaneously — Honeycomb gets the rich
high-cardinality drill-down, Cloud Trace gets the GCP-native correlation
with logs and metrics.

Per 10-gcp-architecture.md §8: 4 SLOs defined in Cloud Monitoring; OTEL
spans feed the latency SLOs and provide trace IDs that show up in Cloud
Logging's structured `logging.googleapis.com/trace` field.

Usage:
    # In app_setup.py before FastAPI startup:
    from api.observability import configure_otel
    configure_otel(app, settings)

    # On shutdown:
    from api.observability import shutdown_otel
    await shutdown_otel()
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

import structlog
from google.auth.exceptions import (
    DefaultCredentialsError,
    GoogleAuthError,
    RefreshError,
)

logger = structlog.get_logger()

_tracer_provider: Any = None
_meter_provider: Any = None


def configure_otel(app: Any | None, settings: Any) -> None:
    """Initialize OTEL exporters and instrument FastAPI + SQLAlchemy.

    Idempotent: subsequent calls are no-ops.

    Pass `app=None` when calling from a Celery worker_process_init handler;
    FastAPI instrumentation is skipped but all exporters and SQLAlchemy/HTTPX
    instrumentation still run.

    Reads from settings:
        - `honeycomb_api_key` (optional — if empty, only Cloud Trace exports)
        - `gcp_project_id` (required for Cloud Trace and Cloud Monitoring OTLP)
        - `deployment_env` (used as deployment.environment resource attribute)
        - `release_version` (used as service.version, falls back to "dev")
    """
    global _tracer_provider, _meter_provider
    if _tracer_provider is not None:
        return

    honeycomb_api_key = settings.honeycomb_api_key
    if honeycomb_api_key and honeycomb_api_key.startswith("placeholder"):
        honeycomb_api_key = ""
    gcp_project_id = settings.gcp_project_id
    app_env = settings.app_env
    deployment_env = getattr(settings, "deployment_env", app_env)

    if not honeycomb_api_key and not gcp_project_id:
        logger.info(
            "otel_disabled",
            reason="neither HONEYCOMB_API_KEY nor GCP_PROJECT_ID set",
        )
        return

    # Lazy imports — OTEL deps only loaded when observability is wired.

    try:
        trace = import_module("opentelemetry.trace")
        resource_cls = import_module("opentelemetry.sdk.resources").Resource
        tracer_provider_cls = import_module("opentelemetry.sdk.trace").TracerProvider
        batch_span_processor_cls = import_module(
            "opentelemetry.sdk.trace.export"
        ).BatchSpanProcessor
        fastapi_instrumentor_cls = import_module(
            "opentelemetry.instrumentation.fastapi"
        ).FastAPIInstrumentor
        sqlalchemy_instrumentor_cls = import_module(
            "opentelemetry.instrumentation.sqlalchemy"
        ).SQLAlchemyInstrumentor
        httpx_client_instrumentor_cls = import_module(
            "opentelemetry.instrumentation.httpx"
        ).HTTPXClientInstrumentor
    except ImportError as exc:
        logger.warning(
            "otel_imports_unavailable",
            error=str(exc),
            hint=(
                "install opentelemetry-sdk plus FastAPI, SQLAlchemy, and HTTPX "
                "instrumentation packages"
            ),
        )
        return

    resource = resource_cls.create(
        {
            "service.name": "praviar-api",
            "service.namespace": "praviar",
            "service.version": settings.release_version,
            "deployment.environment": deployment_env,
        }
    )

    provider = tracer_provider_cls(resource=resource)

    # Honeycomb exporter — OTLP/HTTP.
    if honeycomb_api_key:
        try:
            otlp_span_exporter_cls = import_module(
                "opentelemetry.exporter.otlp.proto.http.trace_exporter"
            ).OTLPSpanExporter
            honeycomb_exporter = otlp_span_exporter_cls(
                endpoint="https://api.honeycomb.io/v1/traces",
                headers={"x-honeycomb-team": honeycomb_api_key},
            )
            provider.add_span_processor(batch_span_processor_cls(honeycomb_exporter))
            logger.info("otel_honeycomb_exporter_enabled")
        except ImportError as exc:
            logger.warning("otel_honeycomb_exporter_unavailable", error=str(exc), exc_info=True)

    # Cloud Trace exporter — runtime SA's roles/cloudtrace.agent, no API key.
    # CloudTraceSpanExporter() eagerly opens a gRPC channel to googleapis.com
    # and asks for Application Default Credentials at construction time. When
    # ADC is unavailable (local dev without `gcloud auth login`, CI without
    # WIF) this raises DefaultCredentialsError and crashes the app. Catching
    # broadly so the API still boots — Honeycomb traces still ship.
    if gcp_project_id:
        try:
            cloud_trace_span_exporter_cls = import_module(
                "opentelemetry.exporter.cloud_trace"
            ).CloudTraceSpanExporter
            cloud_trace_exporter = cloud_trace_span_exporter_cls(project_id=gcp_project_id)
            provider.add_span_processor(batch_span_processor_cls(cloud_trace_exporter))
            logger.info("otel_cloud_trace_exporter_enabled", project_id=gcp_project_id)
        except ImportError as exc:
            logger.warning("otel_cloud_trace_exporter_unavailable", error=str(exc), exc_info=True)
        except (DefaultCredentialsError, GoogleAuthError, RefreshError) as exc:
            # ADC missing or expired — the API must still boot so Honeycomb
            # traces ship even when running locally without `gcloud auth`.
            logger.warning(
                "otel_cloud_trace_exporter_init_failed",
                error=str(exc),
                hint=(
                    "ADC not configured; run `gcloud auth application-default login` "
                    "or set GOOGLE_APPLICATION_CREDENTIALS"
                ),
            )

    trace.set_tracer_provider(provider)
    _tracer_provider = provider

    # Instrument frameworks. SQLAlchemy auto-discovers engines created after this call;
    # the first engine in api/db/session.py is created lazily so this always lands first.
    # CeleryInstrumentor is NOT called here — it must be called inside worker_process_init
    # in celery_app.py (Celery forks workers; OTel state initialised before the fork
    # is duplicated incorrectly across child processes).
    if app is not None:
        fastapi_instrumentor_cls.instrument_app(app, excluded_urls="health,metrics")
    sqlalchemy_instrumentor_cls().instrument(enable_commenter=True)
    httpx_client_instrumentor_cls().instrument()

    logger.info("otel_configured", env=deployment_env, app_env=app_env)


async def shutdown_otel() -> None:
    """Flush spans and shutdown providers on FastAPI shutdown."""
    global _tracer_provider
    if _tracer_provider is not None:
        try:
            _tracer_provider.shutdown()
            logger.info("otel_shutdown")
        except (RuntimeError, OSError, TimeoutError) as exc:
            # Shutdown can fail if exporters are mid-flush against a dead
            # network or already-released resources. Log and move on so the
            # FastAPI shutdown lifecycle still completes cleanly.
            logger.warning("otel_shutdown_failed", error=str(exc), exc_info=True)
        _tracer_provider = None
