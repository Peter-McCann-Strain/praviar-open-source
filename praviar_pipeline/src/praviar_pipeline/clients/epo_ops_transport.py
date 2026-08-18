"""Authenticated EPO OPS transport helpers."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import httpx
import structlog

from praviar_pipeline.errors import AuthenticationError, RateLimitError, SourceUnavailableError
from praviar_pipeline.utils.http_bodies import read_bounded_response_body

if TYPE_CHECKING:
    from aiolimiter import AsyncLimiter

logger = structlog.get_logger()

EPO_BINARY_MAX_BYTES = 100 * 1024 * 1024


def _decode_json_response(resp: httpx.Response, *, detail: str) -> dict:
    parse_failed = False
    try:
        payload = resp.json()
    except (TypeError, ValueError):
        parse_failed = True
        payload = None
    if parse_failed or not isinstance(payload, dict):
        raise SourceUnavailableError("epo_ops", detail) from None
    return payload


def _parse_retry_after(resp: httpx.Response) -> float:
    for header in ("Retry-After", "X-Throttle-Control"):
        value = resp.headers.get(header)
        if value:
            try:
                return max(0.0, float(value))
            except ValueError:
                pass
    return 60.0


async def request_access_token(
    *,
    auth_client: httpx.AsyncClient,
    auth_url: str,
    consumer_key: str,
    consumer_secret: str,
) -> dict:
    """Request a new OAuth2 access token from OPS.

    The OAuth token endpoint must always respond — a 404/5xx/timeout here is
    a real source outage, not a semantic empty. Raise ``SourceUnavailableError``
    so the orchestrator can mark EPO OPS FAILED for this run.
    """
    transport_failed = False
    try:
        resp = await auth_client.post(
            auth_url,
            data={"grant_type": "client_credentials"},
            auth=(consumer_key, consumer_secret),
        )
    except (httpx.TimeoutException, httpx.TransportError):
        transport_failed = True
    if transport_failed:
        raise SourceUnavailableError("epo_ops", "OAuth token request failed") from None
    if resp.status_code in (401, 403):
        raise AuthenticationError("EPO OPS consumer key/secret invalid", source="epo_ops")
    if resp.status_code >= 500 or resp.status_code == 404:
        raise SourceUnavailableError(
            "epo_ops",
            f"OAuth token endpoint returned {resp.status_code}",
            status_code=resp.status_code,
        )
    if resp.status_code >= 400:
        raise SourceUnavailableError(
            "epo_ops",
            "OAuth token endpoint rejected request",
            status_code=resp.status_code,
        )
    return _decode_json_response(resp, detail="OAuth token response parsing failed")


async def authenticated_json_get(
    *,
    client: httpx.AsyncClient,
    limiter: AsyncLimiter,
    path: str,
    token: str,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    ok_on_404: bool = False,
) -> dict:
    """Perform an authenticated JSON GET with EPO-specific status handling.

    When a :class:`~praviar_pipeline.response_cache.ResponseCache` is installed,
    the live call is wrapped so the response is recorded/replayed. The cache
    key folds the sorted ``params`` into the body so distinct queries key
    distinctly. The per-request bearer ``token`` is NOT folded into the key
    (tokens rotate between runs and are not a semantic input). Exceptions
    propagate unrecorded.

    Args:
        ok_on_404: When True, 404 responses return ``{}`` (semantic empty, e.g.
            a patent with no family/biblio entry). When False (default), 404 is
            treated as a source failure and raises ``SourceUnavailableError``.
    """
    import json

    from praviar_pipeline.response_cache import CacheMode, get_current_cache

    cache = get_current_cache()
    if cache is None or cache.mode == CacheMode.DISABLED:
        return await _authenticated_json_get_uncached(
            client=client,
            limiter=limiter,
            path=path,
            token=token,
            headers=headers,
            params=params,
            ok_on_404=ok_on_404,
        )
    body = json.dumps({"params": params, "ok_on_404": ok_on_404}, sort_keys=True)
    return await cache.wrap(
        source="epo_ops",
        method="GET",
        url=path,
        body=body,
        call=lambda: _authenticated_json_get_uncached(
            client=client,
            limiter=limiter,
            path=path,
            token=token,
            headers=headers,
            params=params,
            ok_on_404=ok_on_404,
        ),
    )


async def _authenticated_json_get_uncached(
    *,
    client: httpx.AsyncClient,
    limiter: AsyncLimiter,
    path: str,
    token: str,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    ok_on_404: bool = False,
) -> dict:
    """Underlying live JSON GET — not wrapped by the response cache."""
    request_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if headers:
        request_headers.update(headers)

    transport_failed = False
    try:
        async with limiter:
            resp = await client.get(path, params=params, headers=request_headers)
    except (httpx.TimeoutException, httpx.TransportError):
        transport_failed = True
    if transport_failed:
        raise SourceUnavailableError("epo_ops", "authenticated GET failed") from None

    if resp.status_code in (401, 403):
        raise AuthenticationError("EPO OPS access token rejected", source="epo_ops")
    if resp.status_code == 429:
        retry_after = _parse_retry_after(resp)
        logger.warning("epo_ops_rate_limited", retry_after=retry_after)
        await asyncio.sleep(retry_after)
        raise RateLimitError(
            f"EPO OPS request throttled; retry after {retry_after}s",
            source="epo_ops",
        )
    if resp.status_code == 404:
        if ok_on_404:
            return {}
        raise SourceUnavailableError(
            "epo_ops",
            "authenticated GET returned 404",
            status_code=404,
        )
    if resp.status_code >= 500:
        raise SourceUnavailableError(
            "epo_ops",
            "authenticated GET failed",
            status_code=resp.status_code,
        )

    if resp.status_code >= 400:
        raise SourceUnavailableError(
            "epo_ops",
            "authenticated GET rejected request",
            status_code=resp.status_code,
        )
    return _decode_json_response(resp, detail="authenticated GET response parsing failed")


async def authenticated_binary_get(
    *,
    client: httpx.AsyncClient,
    limiter: AsyncLimiter,
    path: str,
    token: str,
    accept: str = "image/png",
    ok_on_404: bool = True,
    headers: dict[str, str] | None = None,
    max_bytes: int = EPO_BINARY_MAX_BYTES,
) -> bytes | None:
    """Perform an authenticated binary GET with EPO-specific status handling.

    When a :class:`~praviar_pipeline.response_cache.ResponseCache` is installed,
    the live call is wrapped so the response is recorded/replayed. Binary
    bodies are base64-encoded into a JSON envelope for cache serialisation;
    a ``None`` (semantic empty on 404) is recorded as a JSON null.

    Args:
        ok_on_404: When True (default), 404 returns ``None`` — drawings pages
            genuinely may not exist for a given patent. When False, 404 becomes
            a ``SourceUnavailableError``.
    """
    import base64
    import json

    from praviar_pipeline.response_cache import CacheMode, get_current_cache

    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    effective_max_bytes = min(max_bytes, EPO_BINARY_MAX_BYTES)

    cache = get_current_cache()
    if cache is None or cache.mode == CacheMode.DISABLED:
        return await _authenticated_binary_get_uncached(
            client=client,
            limiter=limiter,
            path=path,
            token=token,
            accept=accept,
            ok_on_404=ok_on_404,
            headers=headers,
            max_bytes=effective_max_bytes,
        )

    body = json.dumps(
        {
            "accept": accept,
            "max_bytes": effective_max_bytes,
            "ok_on_404": ok_on_404,
        },
        sort_keys=True,
    )

    async def _call_and_encode() -> str | None:
        raw = await _authenticated_binary_get_uncached(
            client=client,
            limiter=limiter,
            path=path,
            token=token,
            accept=accept,
            ok_on_404=ok_on_404,
            headers=headers,
            max_bytes=effective_max_bytes,
        )
        if raw is None:
            return None
        return base64.b64encode(raw).decode("ascii")

    encoded = await cache.wrap(
        source="epo_ops",
        method="GET_BINARY",
        url=path,
        body=body,
        call=_call_and_encode,
    )
    if encoded is None:
        return None
    if not isinstance(encoded, str) or len(encoded) > ((effective_max_bytes + 2) // 3) * 4:
        raise SourceUnavailableError("epo_ops", "cached binary body exceeded byte limit")
    try:
        decoded = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError):
        raise SourceUnavailableError("epo_ops", "cached binary body was invalid") from None
    if len(decoded) > effective_max_bytes:
        raise SourceUnavailableError("epo_ops", "cached binary body exceeded byte limit")
    return decoded


async def _authenticated_binary_get_uncached(
    *,
    client: httpx.AsyncClient,
    limiter: AsyncLimiter,
    path: str,
    token: str,
    accept: str = "image/png",
    ok_on_404: bool = True,
    headers: dict[str, str] | None = None,
    max_bytes: int = EPO_BINARY_MAX_BYTES,
) -> bytes | None:
    """Underlying live binary GET — not wrapped by the response cache."""
    request_headers: dict[str, str] = {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
    }
    if headers:
        request_headers.update(headers)
    try:
        async with limiter, client.stream("GET", path, headers=request_headers) as resp:
            if resp.status_code in (401, 403):
                raise AuthenticationError("EPO OPS access token rejected", source="epo_ops")
            if resp.status_code == 429:
                retry_after = _parse_retry_after(resp)
                logger.warning("epo_ops_rate_limited_binary", retry_after=retry_after)
                await asyncio.sleep(retry_after)
                raise RateLimitError(
                    f"EPO OPS binary request throttled; retry after {retry_after}s",
                    source="epo_ops",
                )
            if resp.status_code == 404:
                if ok_on_404:
                    return None
                raise SourceUnavailableError(
                    "epo_ops",
                    "authenticated binary GET returned 404",
                    status_code=404,
                )
            if resp.status_code >= 500:
                raise SourceUnavailableError(
                    "epo_ops",
                    "authenticated binary GET failed",
                    status_code=resp.status_code,
                )
            if resp.status_code >= 400:
                raise SourceUnavailableError(
                    "epo_ops",
                    "authenticated binary GET rejected request",
                    status_code=resp.status_code,
                )
            return await read_bounded_response_body(
                resp,
                max_bytes=max_bytes,
                source="epo_ops",
                detail="binary body exceeded byte limit",
            )
    except (httpx.TimeoutException, httpx.TransportError):
        raise SourceUnavailableError("epo_ops", "authenticated binary GET failed") from None
