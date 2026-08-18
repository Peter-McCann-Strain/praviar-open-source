"""Trusted client-IP extraction for rate limits and audit metadata."""

from __future__ import annotations

from ipaddress import (
    IPv4Address,
    IPv4Network,
    IPv6Address,
    IPv6Network,
    ip_address,
    ip_network,
)
from typing import Any

from fastapi import Request

from api.config import get_settings

IPAddress = IPv4Address | IPv6Address
IPNetwork = IPv4Network | IPv6Network


def _canonical_ip(addr: IPAddress) -> IPAddress:
    """Collapse IPv4-mapped IPv6 addresses to their IPv4 form.

    ``::ffff:1.2.3.4`` and ``1.2.3.4`` identify the same client, but
    ``str()`` renders them differently (``::ffff:102:304`` vs ``1.2.3.4``).
    A dual-stack client (directly, or via a trusted proxy that forwards an
    IPv4-mapped X-Forwarded-For) could otherwise alternate representations to
    get two independent rate-limit buckets for one identity. Canonicalising
    here yields a single, stable key per client across both stacks.
    """
    if isinstance(addr, IPv6Address) and addr.ipv4_mapped is not None:
        return addr.ipv4_mapped
    return addr


def _parse_ip_literal(raw_value: str) -> IPAddress | None:
    value = raw_value.strip().strip('"')
    if not value:
        return None
    if value.startswith("[") and "]" in value:
        value = value[1 : value.index("]")]
    elif value.count(":") == 1 and "." in value:
        value = value.rsplit(":", maxsplit=1)[0]
    try:
        return _canonical_ip(ip_address(value))
    except ValueError:
        return None


def _trusted_networks(raw_cidrs: list[str]) -> tuple[IPNetwork, ...]:
    networks = []
    for raw_cidr in raw_cidrs:
        cidr = str(raw_cidr or "").strip()
        if not cidr:
            continue
        networks.append(ip_network(cidr, strict=False))
    return tuple(networks)


def _is_trusted_proxy(peer_ip: IPAddress, trusted_cidrs: list[str]) -> bool:
    return any(peer_ip in network for network in _trusted_networks(trusted_cidrs))


def _trusted_forwarded_client_ip(header_value: str, trusted_cidrs: list[str]) -> str | None:
    parsed_chain: list[IPAddress] = []
    for candidate in header_value.split(","):
        parsed = _parse_ip_literal(candidate)
        if parsed is not None:
            parsed_chain.append(parsed)
    if not parsed_chain:
        return None

    # Walk from the proxy closest to us back toward the client. The first
    # untrusted hop from the right is the client identity we can safely use;
    # entries further left may have been supplied by that untrusted client.
    for parsed_ip in reversed(parsed_chain):
        if not _is_trusted_proxy(parsed_ip, trusted_cidrs):
            return str(parsed_ip)
    return str(parsed_chain[0])


def get_client_ip(
    request: Request | Any,
    *,
    trusted_proxy_cidrs: list[str] | None = None,
) -> str:
    """Return the trusted client IP for a request.

    ``X-Forwarded-For`` is honored only when the immediate peer is in the
    configured trusted proxy CIDRs. Spoofed forwarding headers from direct
    clients therefore cannot change rate-limit or audit identity.
    """

    peer_host = ""
    if getattr(request, "client", None) is not None:
        peer_host = str(getattr(request.client, "host", "") or "").strip()
    if not peer_host:
        return "unknown"

    peer_ip = _parse_ip_literal(peer_host)
    cidrs = (
        trusted_proxy_cidrs
        if trusted_proxy_cidrs is not None
        else list(getattr(get_settings(), "trusted_proxy_cidrs", []) or [])
    )
    forwarded_for = str(getattr(request, "headers", {}).get("X-Forwarded-For", "") or "")
    if peer_ip is not None and forwarded_for and _is_trusted_proxy(peer_ip, cidrs):
        forwarded_ip = _trusted_forwarded_client_ip(forwarded_for, cidrs)
        if forwarded_ip:
            return forwarded_ip

    return str(peer_ip) if peer_ip is not None else peer_host[:255]
