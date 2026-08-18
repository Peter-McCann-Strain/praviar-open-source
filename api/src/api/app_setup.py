"""FastAPI app wiring helpers."""

from __future__ import annotations

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from api.app_lifecycle import RequestLoggingMiddleware
from api.errors import (
    APIError,
    ProblemDetail,
    api_error_handler,
    http_exception_handler,
    rate_limit_exceeded_handler,
    request_validation_error_handler,
)
from api.middleware.input_validation import InputValidationMiddleware
from api.middleware.rate_limit import RateLimitHeaderMiddleware

logger = structlog.get_logger()


def configure_openapi_schema(app: FastAPI) -> None:
    """Ensure manually referenced shared schemas are present in OpenAPI."""
    original_openapi = app.openapi

    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema

        schema = original_openapi()
        schema.setdefault("components", {}).setdefault("schemas", {}).setdefault(
            "ProblemDetail",
            ProblemDetail.model_json_schema(),
        )
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


def _internal_only(request: Request) -> None:
    """Restrict /metrics access to loopback callers or a configured bearer token.

    Two modes:
    1. Loopback (default): accepts 127.0.0.1/::1 — correct on Cloud Run where
       the managed LB never presents a loopback peer IP for external traffic.
    2. Bearer token (opt-in): when METRICS_BEARER_TOKEN is set, requests that
       present a matching "Authorization: Bearer <token>" are also accepted.
       This enables Managed Prometheus scraping and service-mesh topologies
       where the peer IP is a proxy/sidecar address rather than loopback.

    Plain HTTP headers are forgeable by callers that can reach the endpoint, so
    the bearer token path provides no stronger guarantees than the loopback
    check — it only widens accepted callers to those that know the token.
    """
    from api.config import get_settings

    settings = get_settings()

    # Bearer token check (opt-in, takes precedence over peer-IP).
    if settings.metrics_bearer_token:
        import hmac

        auth = request.headers.get("Authorization", "")
        expected = f"Bearer {settings.metrics_bearer_token}"
        if hmac.compare_digest(auth.encode(), expected.encode()):
            return

    allowed_hosts = {"127.0.0.1", "::1"}
    client_host = request.client.host if request.client else None
    if client_host not in allowed_hosts:
        raise HTTPException(status_code=403, detail="metrics access denied")


def configure_observability(app: FastAPI, *, settings) -> None:
    """Initialize OpenTelemetry tracing (Honeycomb + Cloud Trace) on the app.

    Idempotent: no-op when neither HONEYCOMB_API_KEY nor GCP_PROJECT_ID is set.
    Per 10-gcp-architecture.md §8.
    """
    from api.observability import configure_otel

    configure_otel(app, settings)


def configure_sentry(*, settings) -> None:
    """Initialize Sentry when configured."""
    if not settings.sentry_dsn:
        return

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    integrations = [FastApiIntegration(), SqlalchemyIntegration()]

    try:
        from sentry_sdk.integrations.celery import CeleryIntegration

        integrations.append(CeleryIntegration())
        logger.debug("sentry_celery_integration_loaded")
    except ImportError:
        logger.warning(
            "sentry_celery_integration_unavailable",
            reason="sentry_sdk[celery] not installed — worker errors go unreported",
        )

    try:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            profiles_sample_rate=settings.sentry_profiles_sample_rate,
            environment=settings.deployment_env,
            integrations=integrations,
            send_default_pii=False,
        )
        logger.info("sentry_initialized")
    except Exception as exc:
        logger.warning("sentry_init_failed", error=str(exc), dsn_set=bool(settings.sentry_dsn))


def configure_extensions(app: FastAPI) -> None:
    """Register exception handlers, rate limiting, and metrics."""
    from fastapi.exceptions import RequestValidationError
    from prometheus_fastapi_instrumentator import Instrumentator
    from slowapi.errors import RateLimitExceeded

    from api.metrics import pipeline_runs_total  # noqa: F401 -- registers domain metrics on import
    from api.ratelimit import limiter

    app.state.limiter = limiter
    # Custom handler replaces slowapi's default plain-text 429 response so
    # rate-limit errors honour the application/problem+json contract.
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_exception_handler(APIError, api_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    # FastAPI's built-in 422 handler returns application/json; replace it.
    app.add_exception_handler(
        RequestValidationError,
        request_validation_error_handler,  # type: ignore[arg-type]
    )

    Instrumentator(
        should_group_status_codes=True,
        excluded_handlers=["/api/health", "/metrics"],
    ).instrument(app).expose(
        app,
        endpoint="/metrics",
        include_in_schema=False,
        dependencies=[Depends(_internal_only)],
    )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject security headers on every response.

    Headers applied:
    - X-Content-Type-Options: nosniff — prevent MIME-type sniffing
    - X-Frame-Options: DENY — block framing (clickjacking)
    - Strict-Transport-Security — enforce HTTPS for 1 year
    - X-XSS-Protection: 0 — disable legacy XSS filter (modern recommendation)
    - Referrer-Policy: strict-origin-when-cross-origin
    - Content-Security-Policy: default-src 'none' — API responses carry no
      browser-loadable resources
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Multi-tenant safety: API responses carry per-org data. Forbid storage in
        # any shared CDN/proxy cache so org A's response can never be replayed to
        # org B. Routes that need their own caching (e.g. signed export downloads)
        # set Cache-Control explicitly on their own Response and that value wins
        # because setdefault-style assignment below only fills when unset.
        if "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        # Exempt interactive docs — they load Swagger UI/ReDoc from external CDN.
        # Use an exact-set + single prefix to avoid over-matching (e.g. /api/docs-evil).
        # In prod, docs_url/redoc_url are None so these paths never exist and the
        # exemption is unreachable.
        _path = request.url.path
        _docs_exempt = _path in ("/api/docs", "/api/redoc") or _path.startswith("/api/docs/")
        if not _docs_exempt:
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
            )
        return response


def configure_middleware(app: FastAPI, *, settings) -> None:
    """Register request tracing and CORS middleware."""
    # CORS wildcard with credentials is a security violation (browser ignores it,
    # but some clients don't).  Config already blocks this in prod; belt-and-braces.
    if "*" in settings.cors_origins:
        raise RuntimeError(
            "CORS allow_origins='*' is incompatible with allow_credentials=True. "
            "Set explicit origins in CORS_ORIGINS."
        )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitHeaderMiddleware)
    # InputValidationMiddleware must be registered before RequestLoggingMiddleware so
    # RequestLogging (outer) sets request.state.request_id before InputValidation
    # short-circuits on 413/415, ensuring request_id is populated in those error bodies.
    app.add_middleware(InputValidationMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "X-Request-ID",
            "Idempotency-Key",
        ],
        expose_headers=[
            "Retry-After",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "X-Request-ID",
        ],
    )


def include_routes(app: FastAPI, *, prefix: str) -> None:
    """Mount all application routers."""
    from api.middleware.rate_limit import rate_limit_api
    from api.routes import (
        admin,
        admin_analytics,
        analyses,
        apikeys,
        batch,
        billing,
        chat,
        checkpoint_decisions,
        claimed_use_receipts,
        comments,
        compounds,
        configs,
        external_sharing_policy,
        feedback,
        internal,
        markush_evidence,
        monitors,
        notifications,
        patents,
        pipeline,
        principal,
        public,
        reports,
        reviewer_decisions,
        setup_readiness,
        sso,
        webhooks,
        webhooks_stripe,
    )

    authenticated_rate_limit = [Depends(rate_limit_api)]
    authenticated_routers = [
        (analyses.router, "analyses"),
        (reports.router, "reports"),
        (compounds.router, "compounds"),
        (patents.router, "patents"),
        (pipeline.router, "pipeline"),
        (configs.router, "configs"),
        (comments.router, "comments"),
        (feedback.router, "feedback"),
        (external_sharing_policy.router, "external-sharing-policy"),
        (chat.router, "chat"),
        (checkpoint_decisions.router, "checkpoint-decisions"),
        (claimed_use_receipts.router, "claimed-use-receipts"),
        (billing.router, "billing"),
        (notifications.router, "notifications"),
        (admin_analytics.router, "admin-analytics"),
        (admin.router, "admin"),
        (monitors.router, "monitors"),
        (batch.router, "batch"),
        (apikeys.router, "api-keys"),
        (reviewer_decisions.router, "reviewer-decisions"),
        (markush_evidence.router, "markush-evidence"),
        (principal.router, "principal"),
        (setup_readiness.router, "setup-readiness"),
        (sso.router, "sso"),
    ]
    for router, tag in authenticated_routers:
        app.include_router(
            router,
            prefix=prefix,
            tags=[tag],
            dependencies=authenticated_rate_limit,
        )

    app.include_router(webhooks.router, prefix="/api", tags=["webhooks"])
    app.include_router(webhooks_stripe.router, prefix="/api", tags=["webhooks"])
    app.include_router(public.router, tags=["public"])
    app.include_router(
        notifications.public_router,
        prefix=prefix,
        tags=["notifications"],
    )
    # Internal routes — invoked by Cloud Tasks via OIDC, not by end users.
    # No `prefix` so the path is /internal/* (workers Cloud Run service has
    # ingress=INTERNAL_ONLY per Terraform; only authenticated Cloud Tasks can hit it).
    app.include_router(internal.router, tags=["internal"])
