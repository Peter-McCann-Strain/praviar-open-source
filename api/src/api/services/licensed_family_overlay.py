"""Vendor-agnostic runtime contract for a licensed family/legal-status overlay."""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlparse

import httpcore
import httpx

from api.config import (
    get_settings,
    is_licensed_family_overlay_search_url_safe,
    validate_licensed_family_overlay_search_url,
)

# Hard cap on the bytes buffered from the overlay response. The overlay is an
# operator-configured third party; a compromised, misconfigured, or simply
# buggy upstream returning an unbounded body would otherwise be buffered whole
# into worker memory by ``resp.json()``. 16 MiB comfortably exceeds a legitimate
# family/legal-status JSON payload while bounding the blast radius.
_MAX_OVERLAY_RESPONSE_BYTES = 16 * 1024 * 1024


def _text(value: object) -> str:
    return str(value or "").strip()


@dataclass(frozen=True)
class LicensedFamilyOverlayRuntimeConfig:
    provider_name: str
    search_url: str
    api_key: str
    allowed_org_ids: frozenset[str]
    timeout_seconds: float

    @property
    def search_url_safe(self) -> bool:
        return is_licensed_family_overlay_search_url_safe(self.search_url)

    @property
    def configured(self) -> bool:
        return bool(
            self.search_url and self.search_url_safe and self.api_key and self.allowed_org_ids
        )

    def allows_org(self, org_id: str | None) -> bool:
        return bool(org_id) and org_id in self.allowed_org_ids


def get_licensed_family_overlay_runtime_config() -> LicensedFamilyOverlayRuntimeConfig:
    settings = get_settings()
    return LicensedFamilyOverlayRuntimeConfig(
        provider_name=_text(settings.licensed_family_overlay_provider_name)
        or "licensed_family_overlay",
        search_url=_text(settings.licensed_family_overlay_search_url),
        api_key=_text(settings.licensed_family_overlay_api_key),
        allowed_org_ids=frozenset(settings.licensed_family_overlay_allowed_org_ids),
        timeout_seconds=max(float(settings.licensed_family_overlay_timeout_seconds), 0.1),
    )


def _validate_public_dns_resolution(search_url: str) -> None:
    host = (urlparse(search_url).hostname or "").strip().lower().rstrip(".")
    if not host:
        raise ValueError("LICENSED_FAMILY_OVERLAY_SEARCH_URL must include a hostname.")

    try:
        resolved = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError(
            "LICENSED_FAMILY_OVERLAY_SEARCH_URL hostname could not be resolved."
        ) from exc

    addresses = {str(item[4][0]) for item in resolved if item[4]}
    if not addresses:
        raise ValueError(
            "LICENSED_FAMILY_OVERLAY_SEARCH_URL hostname did not resolve to an address."
        )
    for address_value in addresses:
        _validate_public_ip_address(address_value)


def _validate_public_ip_address(address_value: str) -> None:
    address = ip_address(address_value)
    if not address.is_global:
        raise ValueError(
            "LICENSED_FAMILY_OVERLAY_SEARCH_URL must resolve only to public IP ranges."
        )


def _network_stream_peer_ip(stream: httpcore.AsyncNetworkStream) -> str | None:
    server_addr = stream.get_extra_info("server_addr")
    if isinstance(server_addr, tuple) and server_addr:
        return str(server_addr[0])

    sock = stream.get_extra_info("socket")
    if sock is None or not hasattr(sock, "getpeername"):
        return None
    peername = sock.getpeername()
    if isinstance(peername, tuple) and peername:
        return str(peername[0])
    return None


class _PublicEndpointNetworkBackend(httpcore.AsyncNetworkBackend):
    """Validate the concrete connected peer before HTTP bytes are sent."""

    def __init__(self, delegate: httpcore.AsyncNetworkBackend) -> None:
        self._delegate = delegate

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        stream = await self._delegate.connect_tcp(
            host,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )
        try:
            peer_ip = _network_stream_peer_ip(stream)
            if peer_ip is None:
                raise ValueError(
                    "LICENSED_FAMILY_OVERLAY_SEARCH_URL connection peer could not be verified."
                )
            _validate_public_ip_address(peer_ip)
        except Exception:
            await stream.aclose()
            raise
        return stream

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        raise ValueError("Licensed family overlay does not allow Unix socket transports.")

    async def sleep(self, seconds: float) -> None:
        await self._delegate.sleep(seconds)


def _public_endpoint_transport() -> httpx.AsyncHTTPTransport:
    transport = httpx.AsyncHTTPTransport(trust_env=False, retries=0)
    pool = getattr(transport, "_pool", None)
    if pool is None:
        raise RuntimeError("httpx transport connection pool is unavailable.")
    backend = getattr(pool, "_network_backend", None)
    if backend is None:
        raise RuntimeError("httpx transport network backend is unavailable.")
    pool._network_backend = _PublicEndpointNetworkBackend(backend)
    return transport


async def search_licensed_family_overlay(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Execute a vendor-agnostic family-overlay request.

    Expected response contract:
    {
        "results": [
            {
                "id": "...",
                "title": "...",
                "summary": "...",
                "patent_id": "...",
                "family_id": "...",
                "jurisdictions": [...],
                "assignees": [...],
                "legal_status": "...",
                "ownership_summary": "...",
                "freshness": "..."
            }
        ]
    }
    """

    config = get_licensed_family_overlay_runtime_config()
    if config.search_url and not config.search_url_safe:
        validate_licensed_family_overlay_search_url(config.search_url)
    if not config.configured:
        return []
    _validate_public_dns_resolution(config.search_url)

    timeout = httpx.Timeout(config.timeout_seconds, connect=min(config.timeout_seconds, 5.0))
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.api_key}",
        "X-Praviar-Pipeline-Provider-Contract": "licensed-family-overlay.v1",
    }

    from api.circuit_breaker import licensed_overlay_breaker

    async def _do_request() -> Any:
        async with httpx.AsyncClient(
            timeout=timeout,
            headers=headers,
            follow_redirects=False,
            transport=_public_endpoint_transport(),
        ) as client:
            # Stream the body so an unbounded (compromised/buggy) upstream
            # cannot exhaust worker memory: ``resp.json()`` would otherwise
            # buffer the whole response before any size check ran.
            async with client.stream("POST", config.search_url, json=payload) as resp:
                resp.raise_for_status()
                body = bytearray()
                async for chunk in resp.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > _MAX_OVERLAY_RESPONSE_BYTES:
                        raise ValueError(
                            "Licensed family overlay response exceeded the "
                            f"{_MAX_OVERLAY_RESPONSE_BYTES}-byte size limit."
                        )
            return json.loads(body) if body else None

    data = await licensed_overlay_breaker.call(_do_request)

    if not isinstance(data, dict):
        return []
    results = data.get("results")
    if not isinstance(results, list):
        return []
    return [item for item in results if isinstance(item, dict)]
