"""Exhaustive authentication-boundary inventory for every API route."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts

from api.app_setup import include_routes
from api.deps import get_authenticated_principal, get_current_user
from api.routes.internal import verify_ledger_oidc_token, verify_oidc_token

_PUBLIC_ROUTES = frozenset(
    {
        ("GET", "/api/health"),
        ("GET", "/api/health/ready"),
        ("GET", "/share/{token}"),
        ("POST", "/share/{token}/challenge"),
        ("POST", "/share/{token}/verify"),
        ("POST", "/api/webhooks/clerk"),
        ("POST", "/api/webhooks/stripe"),
        ("POST", "/api/v1/notifications/unsubscribe/digest/{token_locator}"),
    }
)


def _app_with_real_routes(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
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


def _dependency_calls(route: RouteContext) -> set[object]:
    calls: set[object] = set()

    def collect(dependant: object) -> None:
        for dependency in getattr(dependant, "dependencies", ()):
            if dependency.call is not None:
                calls.add(dependency.call)
            collect(dependency)

    collect(route.dependant)
    return calls


def _http_routes(app: FastAPI) -> list[RouteContext]:
    return [
        route
        for route in iter_route_contexts(app.routes)
        if isinstance(route.original_route, APIRoute)
    ]


def test_every_route_has_an_explicit_authentication_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_public: set[tuple[str, str]] = set()

    for route in _http_routes(_app_with_real_routes(monkeypatch)):
        dependency_calls = _dependency_calls(route)
        methods = route.methods or set()
        assert len(methods) == 1, f"{route.path} must expose one auditable HTTP method"
        method = next(iter(methods))
        route_key = (method, route.path)

        if route.path.startswith("/internal/"):
            assert {
                verify_oidc_token,
                verify_ledger_oidc_token,
            } & dependency_calls, f"{method} {route.path} lacks Cloud Tasks OIDC authentication"
            continue

        if route_key in _PUBLIC_ROUTES:
            observed_public.add(route_key)
            continue

        assert (
            get_current_user in dependency_calls or get_authenticated_principal in dependency_calls
        ), f"{method} {route.path} is neither authenticated nor explicitly public"

    assert observed_public == _PUBLIC_ROUTES
