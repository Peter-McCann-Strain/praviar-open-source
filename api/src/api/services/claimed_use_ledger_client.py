"""Authenticated client for the isolated claimed-use ledger service."""

from __future__ import annotations

from importlib import import_module
from typing import Any, Literal

import httpx
from starlette.concurrency import run_in_threadpool

from api.config import get_settings
from api.errors import APIError


def _fetch_worker_identity_token(audience: str) -> str:
    id_token_module = import_module("google.oauth2.id_token")
    requests_module = import_module("google.auth.transport.requests")
    return str(
        id_token_module.fetch_id_token(
            requests_module.Request(),
            audience,
        )
    )


async def call_claimed_use_ledger(
    *,
    operation: Literal["list", "issue", "revoke", "erase-org"],
    payload: dict[str, Any],
    http_client_cls: type[httpx.AsyncClient] = httpx.AsyncClient,
) -> dict[str, Any]:
    """Call one worker-only ledger operation with the API workload identity."""
    settings = get_settings()
    if settings.app_env != "prod" or settings.service_role != "api":
        raise RuntimeError("the remote claimed-use ledger is production API-only")
    audience = settings.workers_service_url.rstrip("/")
    if not audience.startswith("https://"):
        raise RuntimeError("WORKERS_SERVICE_URL must be an HTTPS origin")
    token = await run_in_threadpool(_fetch_worker_identity_token, audience)
    try:
        async with http_client_cls(
            timeout=httpx.Timeout(30.0, connect=5.0),
            follow_redirects=False,
        ) as client:
            response = await client.post(
                f"{audience}/internal/claimed-use/{operation}",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.RequestError as exc:
        raise APIError(
            503,
            "Service Unavailable",
            "The claimed-use ledger service is temporarily unavailable.",
        ) from exc
    if response.status_code >= 400:
        try:
            problem = response.json()
        except ValueError:
            problem = {}
        detail = str(problem.get("detail") or "The claimed-use ledger rejected the request.")
        title = str(problem.get("title") or "Claimed-use ledger error")
        raise APIError(response.status_code, title, detail)
    try:
        body = response.json()
    except ValueError as exc:
        raise APIError(
            502,
            "Bad Gateway",
            "The claimed-use ledger returned an invalid response.",
        ) from exc
    if not isinstance(body, dict):
        raise APIError(
            502,
            "Bad Gateway",
            "The claimed-use ledger returned an invalid response.",
        )
    return body
