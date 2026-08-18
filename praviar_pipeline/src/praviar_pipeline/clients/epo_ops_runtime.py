"""Runtime helpers for the EPO OPS client."""

from __future__ import annotations

import time
from typing import cast

from praviar_pipeline.clients.epo_ops_helpers import build_cql_query
from praviar_pipeline.clients.epo_ops_search import search_published_data
from praviar_pipeline.clients.epo_ops_transport import (
    authenticated_binary_get,
    authenticated_json_get,
    request_access_token,
)
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import AuthenticationError


async def ensure_access_token(
    client,
    *,
    auth_url: str,
    build_ops_auth_client_fn,
    refresh_access_token_fn,
    logger,
) -> str:
    """Obtain or refresh the OAuth2 access token for OPS."""
    if client._access_token and time.monotonic() < client._token_expires_at:
        return cast("str", client._access_token)

    if not client._consumer_key or not client._consumer_secret:
        raise AuthenticationError(
            "EPO OPS consumer key/secret not configured",
            source="epo_ops",
        )

    settings = get_settings()
    auth_client = build_ops_auth_client_fn(settings=settings)
    try:
        access_token, expires_at = await refresh_access_token_fn(
            auth_client=auth_client,
            auth_url=auth_url,
            consumer_key=client._consumer_key,
            consumer_secret=client._consumer_secret,
            request_access_token_fn=request_access_token,
            logger=logger,
        )
        client._access_token = access_token
        client._token_expires_at = expires_at
        return cast("str", client._access_token)
    finally:
        await auth_client.aclose()


async def authenticated_ops_json_get(
    client,
    *,
    path: str,
    logger,
    ok_on_404: bool = False,
) -> dict:
    """Rate-limited authenticated JSON GET for OPS.

    Args:
        ok_on_404: Forwarded to the transport. Set True for endpoints where
            404 is a semantic empty (e.g., family/biblio/register of a patent
            with no matching record). Default False treats 404 as a source
            failure (``SourceUnavailableError``).
    """
    token = await client._ensure_token()
    logger.debug("epo_ops_request", method="GET")
    try:
        return await authenticated_json_get(
            client=client._client,
            limiter=client._limiter,
            path=path,
            token=token,
            ok_on_404=ok_on_404,
        )
    except AuthenticationError:
        # Clear cached token and retry once — covers transient token expiry and
        # quota resets (EPO OPS returns 403 for both expired tokens and quota).
        client._access_token = ""
        client._token_expires_at = 0.0
        logger.warning("epo_ops_token_refresh_retry")
        fresh_token = await client._ensure_token()
        return await authenticated_json_get(
            client=client._client,
            limiter=client._limiter,
            path=path,
            token=fresh_token,
            ok_on_404=ok_on_404,
        )


async def authenticated_ops_binary_get_impl(
    client,
    *,
    path: str,
    accept: str,
    headers: dict[str, str] | None = None,
    max_bytes: int | None = None,
    logger,
) -> bytes | None:
    """Rate-limited authenticated binary GET for OPS."""

    async def _request(active_token: str) -> bytes | None:
        if max_bytes is None:
            return await authenticated_binary_get(
                client=client._client,
                limiter=client._limiter,
                path=path,
                token=active_token,
                accept=accept,
                headers=headers,
            )
        return await authenticated_binary_get(
            client=client._client,
            limiter=client._limiter,
            path=path,
            token=active_token,
            accept=accept,
            headers=headers,
            max_bytes=max_bytes,
        )

    token = await client._ensure_token()
    logger.debug("epo_ops_binary_request", method="GET")
    try:
        return await _request(token)
    except AuthenticationError:
        client._access_token = ""
        client._token_expires_at = 0.0
        logger.warning("epo_ops_token_refresh_retry_binary")
        fresh_token = await client._ensure_token()
        return await _request(fresh_token)


async def search_published_data_impl(
    client,
    *,
    cpc_codes: list[str] | None,
    claim_keywords: list[str] | None,
    applicants: list[str] | None,
    max_results: int,
    logger,
) -> list[dict]:
    """Search published EPO data using the authenticated OPS transport."""
    if not client._consumer_key or not client._consumer_secret:
        logger.debug("epo_search_skipped")
        return []

    cql_query = build_cql_query(
        cpc_codes=cpc_codes,
        claim_keywords=claim_keywords,
        applicants=applicants,
    )
    if not cql_query:
        return []

    logger.debug("epo_search_query")
    token = await client._ensure_token()
    try:
        return await search_published_data(
            client=client._client,
            limiter=client._limiter,
            token=token,
            cql_query=cql_query,
            max_results=max_results,
            logger=logger,
        )
    except AuthenticationError:
        client._access_token = ""
        client._token_expires_at = 0.0
        raise
