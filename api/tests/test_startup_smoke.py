"""Smoke tests for importability and app startup in test mode."""

from __future__ import annotations

import importlib

ROUTER_MODULES = [
    "api.routes.admin",
    "api.routes.admin_analytics",
    "api.routes.analyses",
    "api.routes.apikeys",
    "api.routes.batch",
    "api.routes.billing",
    "api.routes.chat",
    "api.routes.comments",
    "api.routes.compounds",
    "api.routes.configs",
    "api.routes.monitors",
    "api.routes.notifications",
    "api.routes.patents",
    "api.routes.pipeline",
    "api.routes.reports",
    "api.routes.feedback",
    "api.routes.webhooks",
    "api.routes.webhooks_stripe",
]


def test_router_modules_import() -> None:
    for module_name in ROUTER_MODULES:
        module = importlib.import_module(module_name)
        assert module is not None


def test_create_app_in_test_mode() -> None:
    from api.main import create_app

    app = create_app()

    assert app.title == "Praviar API"
