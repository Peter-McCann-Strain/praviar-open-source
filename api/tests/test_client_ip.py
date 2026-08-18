"""Trusted client-IP extraction regressions."""

from __future__ import annotations

from types import SimpleNamespace

from api.client_ip import get_client_ip


def _request(peer_host: str, forwarded_for: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        client=SimpleNamespace(host=peer_host),
        headers={"X-Forwarded-For": forwarded_for} if forwarded_for else {},
    )


def test_get_client_ip_ignores_spoofed_forwarded_for_from_untrusted_peer() -> None:
    request = _request("198.51.100.10", "203.0.113.20, 198.51.100.10")

    assert get_client_ip(request, trusted_proxy_cidrs=["10.0.0.0/8"]) == "198.51.100.10"


def test_get_client_ip_honors_forwarded_for_from_trusted_proxy() -> None:
    request = _request("198.51.100.10", "203.0.113.20, 198.51.100.10")

    assert get_client_ip(request, trusted_proxy_cidrs=["198.51.100.0/24"]) == "203.0.113.20"


def test_get_client_ip_uses_rightmost_untrusted_forwarded_hop_from_trusted_proxy() -> None:
    request = _request("104.16.1.1", "6.6.6.6, 198.51.100.7")

    assert get_client_ip(request, trusted_proxy_cidrs=["104.16.0.0/13"]) == "198.51.100.7"


def test_get_client_ip_skips_invalid_forwarded_entries() -> None:
    request = _request("198.51.100.10", "bad-value, 203.0.113.21")

    assert get_client_ip(request, trusted_proxy_cidrs=["198.51.100.0/24"]) == "203.0.113.21"


def test_get_client_ip_handles_ipv4_peer_with_port() -> None:
    request = _request("198.51.100.10:443", "203.0.113.22")

    assert get_client_ip(request, trusted_proxy_cidrs=["198.51.100.10/32"]) == "203.0.113.22"


def test_get_client_ip_falls_back_to_peer_when_no_header() -> None:
    assert get_client_ip(_request("198.51.100.10"), trusted_proxy_cidrs=[]) == "198.51.100.10"


def test_ipv4_mapped_ipv6_peer_collapses_to_ipv4_key() -> None:
    # A dual-stack client connecting as ::ffff:198.51.100.10 must produce the
    # SAME rate-limit key as the plain IPv4 form, otherwise it gets two buckets.
    mapped = get_client_ip(_request("::ffff:198.51.100.10"), trusted_proxy_cidrs=[])
    plain = get_client_ip(_request("198.51.100.10"), trusted_proxy_cidrs=[])
    assert mapped == plain == "198.51.100.10"


def test_ipv4_mapped_ipv6_in_forwarded_for_collapses_to_ipv4_key() -> None:
    # Same identity via a trusted proxy that forwards an IPv4-mapped XFF entry.
    mapped = get_client_ip(
        _request("198.51.100.7", "::ffff:203.0.113.20"),
        trusted_proxy_cidrs=["198.51.100.0/24"],
    )
    plain = get_client_ip(
        _request("198.51.100.7", "203.0.113.20"),
        trusted_proxy_cidrs=["198.51.100.0/24"],
    )
    assert mapped == plain == "203.0.113.20"


def test_ipv4_mapped_ipv6_case_insensitive_key() -> None:
    # Upper- and lower-case IPv4-mapped forms must not yield distinct buckets.
    upper = get_client_ip(_request("::FFFF:198.51.100.10"), trusted_proxy_cidrs=[])
    lower = get_client_ip(_request("::ffff:198.51.100.10"), trusted_proxy_cidrs=[])
    assert upper == lower == "198.51.100.10"
