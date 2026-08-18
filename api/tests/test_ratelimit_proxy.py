"""Targeted tests for api.ratelimit — trusted proxy detection and key function."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from api.ratelimit import _is_trusted_proxy, _key_func

# ---------------------------------------------------------------------------
# _is_trusted_proxy
# ---------------------------------------------------------------------------


class TestIsTrustedProxy:
    """Tests for ratelimit._is_trusted_proxy."""

    def test_loopback_is_trusted(self) -> None:
        """127.0.0.1 falls in 127.0.0.0/8 (loopback) and must be trusted."""
        assert _is_trusted_proxy("127.0.0.1") is True

    def test_arbitrary_public_ip_is_not_trusted(self) -> None:
        """An address outside all trusted CIDRs must return False."""
        assert _is_trusted_proxy("1.2.3.4") is False

    def test_cloudflare_ipv4_is_trusted(self) -> None:
        """104.16.1.1 falls inside 104.16.0.0/13 (Cloudflare IPv4) — must be trusted."""
        assert _is_trusted_proxy("104.16.1.1") is True

    def test_private_rfc1918_10_is_trusted(self) -> None:
        """10.0.0.1 is within 10.0.0.0/8 — trusted as local proxy."""
        assert _is_trusted_proxy("10.0.0.1") is True

    def test_private_rfc1918_192_168_is_trusted(self) -> None:
        """192.168.1.1 is within 192.168.0.0/16 — trusted as local proxy."""
        assert _is_trusted_proxy("192.168.1.1") is True

    def test_another_cloudflare_range(self) -> None:
        """162.158.0.1 is inside 162.158.0.0/15 (Cloudflare) — must be trusted."""
        assert _is_trusted_proxy("162.158.0.1") is True

    def test_invalid_host_returns_false(self) -> None:
        """A non-IP hostname must not raise — returns False instead."""
        assert _is_trusted_proxy("invalid-host") is False

    def test_empty_string_returns_false(self) -> None:
        """Empty string is not a valid IP — must return False."""
        assert _is_trusted_proxy("") is False

    def test_non_cloudflare_public_ip_returns_false(self) -> None:
        """8.8.8.8 (Google DNS) is not in any trusted CIDR."""
        assert _is_trusted_proxy("8.8.8.8") is False

    def test_cloudflare_ipv6_is_trusted(self) -> None:
        """2606:4700::1 falls inside 2606:4700::/32 (Cloudflare IPv6)."""
        assert _is_trusted_proxy("2606:4700::1") is True

    def test_ipv6_loopback_is_trusted(self) -> None:
        """::1 is the IPv6 loopback — trusted."""
        assert _is_trusted_proxy("::1") is True


# ---------------------------------------------------------------------------
# _key_func
# ---------------------------------------------------------------------------


class TestKeyFunc:
    """Tests for ratelimit._key_func."""

    def _make_request(
        self,
        *,
        client_host: str | None = "1.2.3.4",
        x_forwarded_for: str | None = None,
    ) -> MagicMock:
        """Build a minimal mock Request object."""
        request = MagicMock()
        if client_host is None:
            request.client = None
        else:
            request.client = MagicMock()
            request.client.host = client_host

        headers: dict[str, str] = {}
        if x_forwarded_for is not None:
            headers["X-Forwarded-For"] = x_forwarded_for
        request.headers = headers
        return request

    def test_trusted_proxy_with_xff_returns_forwarded_ip(self) -> None:
        """When connecting from a trusted proxy with X-Forwarded-For, return the forwarded IP."""
        request = self._make_request(
            client_host="127.0.0.1",
            x_forwarded_for="203.0.113.42, 10.0.0.1",
        )
        with patch(
            "api.client_ip.get_settings",
            return_value=SimpleNamespace(trusted_proxy_cidrs=["127.0.0.0/8"]),
        ):
            key = _key_func(request)
        assert key == "10.0.0.1"

    def test_untrusted_proxy_xff_is_ignored(self) -> None:
        """When the direct connection is from an untrusted host, X-Forwarded-For is ignored."""
        request = self._make_request(
            client_host="1.2.3.4",
            x_forwarded_for="203.0.113.99",
        )
        key = _key_func(request)
        assert key == "1.2.3.4"

    def test_no_xff_returns_direct_host(self) -> None:
        """No X-Forwarded-For header — direct socket address is used."""
        request = self._make_request(client_host="5.6.7.8")
        key = _key_func(request)
        assert key == "5.6.7.8"

    def test_client_none_returns_unknown(self) -> None:
        """When request.client is None, return the string 'unknown'."""
        request = self._make_request(client_host=None)
        key = _key_func(request)
        assert key == "unknown"

    def test_xff_with_cloudflare_proxy_returns_first_ip(self) -> None:
        """Cloudflare proxy (104.16.x.x) + XFF header — first IP in list returned."""
        request = self._make_request(
            client_host="104.16.1.1",
            x_forwarded_for="  198.51.100.7 , 10.0.0.2",
        )
        with patch(
            "api.client_ip.get_settings",
            return_value=SimpleNamespace(trusted_proxy_cidrs=["104.16.0.0/13"]),
        ):
            key = _key_func(request)
        assert key == "10.0.0.2"

    def test_empty_xff_header_falls_back_to_direct(self) -> None:
        """An empty X-Forwarded-For header is treated as absent — use direct host."""
        request = self._make_request(
            client_host="127.0.0.1",
            x_forwarded_for="",
        )
        key = _key_func(request)
        # empty XFF is falsy, so direct host is returned
        assert key == "127.0.0.1"
