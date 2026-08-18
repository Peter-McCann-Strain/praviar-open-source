"""Route wiring regressions for analysis creation guards."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts

from api.app_setup import include_routes
from api.deps import get_authenticated_principal
from api.middleware.input_validation import validate_analysis_input
from api.middleware.rate_limit import rate_limit_analysis, rate_limit_api


def _app_with_real_routes(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """Build route metadata without patching runtime settings into imported routers."""
    for key in (
        "R2_ACCOUNT_ID",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET_NAME",
    ):
        monkeypatch.delenv(key, raising=False)

    app = FastAPI()
    include_routes(app, prefix="/api/v1")
    return app


def _find_route(app: FastAPI, *, path: str, method: str) -> RouteContext:
    for route in iter_route_contexts(app.routes):
        if (
            isinstance(route.original_route, APIRoute)
            and route.path == path
            and route.methods is not None
            and method in route.methods
        ):
            return route
    raise AssertionError(f"Route {method} {path} not found")


def _route_dependency_functions(route: RouteContext) -> set:
    return {dependency.dependency for dependency in route.dependencies}


def _nested_dependency_calls(route: RouteContext, parent: object) -> set[object]:
    for dependency in route.dependant.dependencies:
        if dependency.call is parent:
            return {child.call for child in dependency.dependencies}
    raise AssertionError(f"Dependency {parent!r} not found on {route.path}")


def test_real_api_v1_analyses_create_route_has_validation_and_plan_limit_guards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route = _find_route(
        _app_with_real_routes(monkeypatch),
        path="/api/v1/analyses",
        method="POST",
    )

    dependencies = _route_dependency_functions(route)

    assert validate_analysis_input in dependencies
    assert rate_limit_analysis in dependencies
    assert get_authenticated_principal in _nested_dependency_calls(route, rate_limit_analysis)
    assert get_authenticated_principal in _nested_dependency_calls(route, rate_limit_api)


def test_org_api_rate_limit_is_wired_to_authenticated_api_v1_routers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_with_real_routes(monkeypatch)

    for path, method in (
        ("/api/v1/analyses", "GET"),
        ("/api/v1/analyses", "POST"),
        ("/api/v1/analyses/{analysis_id}/chat", "POST"),
        ("/api/v1/billing/checkout", "POST"),
        ("/api/v1/api-keys", "POST"),
        ("/api/v1/admin/invite", "POST"),
        ("/api/v1/batch", "POST"),
    ):
        route = _find_route(app, path=path, method=method)
        assert rate_limit_api in _route_dependency_functions(route)


def test_org_api_rate_limit_excludes_public_and_webhook_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app_with_real_routes(monkeypatch)

    for path, method in (
        ("/share/{token}", "GET"),
        ("/api/webhooks/stripe", "POST"),
        ("/api/webhooks/clerk", "POST"),
        ("/internal/run-pipeline", "POST"),
    ):
        route = _find_route(app, path=path, method=method)
        assert rate_limit_api not in _route_dependency_functions(route)
