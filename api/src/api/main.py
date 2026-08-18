"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from api.app_lifecycle import build_lifespan
from api.app_setup import (
    configure_extensions,
    configure_middleware,
    configure_observability,
    configure_openapi_schema,
    configure_sentry,
    include_routes,
)
from api.config import get_settings
from api.db.session import engine


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    # Disable interactive docs in production — they serve external CDN scripts that
    # conflict with the strict Content-Security-Policy set by SecurityHeadersMiddleware.
    # Also null the raw OpenAPI schema URL in production: disabling docs_url/redoc_url
    # alone still leaves FastAPI's default /openapi.json publicly served, which exposes
    # every path, schema, and parameter to unauthenticated callers (recon surface).
    # NB: app_env=="prod" is also true for staging deployments (deployment_env=="staging"),
    # so both staging and prod are covered.
    _is_prod = settings.app_env == "prod"
    app = FastAPI(
        title="Praviar API",
        description="Freedom-to-Operate analysis platform backend",
        version=settings.release_version,
        lifespan=build_lifespan(engine=engine),
        docs_url=None if _is_prod else "/api/docs",
        redoc_url=None if _is_prod else "/api/redoc",
        openapi_url=None if _is_prod else "/openapi.json",
    )

    configure_sentry(settings=settings)
    configure_extensions(app)
    configure_middleware(app, settings=settings)
    configure_observability(app, settings=settings)
    include_routes(app, prefix=settings.api_prefix)
    configure_openapi_schema(app)

    return app


app = create_app()
