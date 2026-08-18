"""Base classes and mixins for API clients.

Provides:

* :class:`AsyncClientMixin` — async context-manager support. Concrete
  clients **must** implement :meth:`close`. The mixin declares ``close`` as
  an abstract async method so static type-checkers (pyright/mypy) know
  ``self.close()`` is callable from ``__aexit__``.
* :func:`cached_request` — helper that consolidates the
  cache-wrap-with-fallback pattern used by every HTTP client. Concrete
  clients call this from their ``_get``/``_post`` methods to avoid
  re-implementing the same six-line cache-mode dance.

The "no fallbacks" project rule is preserved: if no cache is installed (or
the cache is in ``DISABLED`` mode) the live call is invoked directly. If a
cache is installed, exceptions from the underlying call propagate
unrecorded — :meth:`ResponseCache.wrap` does not swallow errors.
"""

from __future__ import annotations

import base64
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, TypeVar, cast

# Re-exported for downstream client modules so they can import the canonical
# HTTP/rate-limit/retry stack from a single place. Listed in ``__all__`` so
# pyright/mypy treat the imports as a public re-export surface and do not
# flag them as unused.
import httpx
from aiolimiter import AsyncLimiter
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from praviar_pipeline.response_cache import CacheMode, get_current_cache

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

T = TypeVar("T")

__all__ = [
    "AsyncClientMixin",
    "AsyncLimiter",
    "cached_bytes_request",
    "cached_request",
    "httpx",
    "retry",
    "stop_after_attempt",
    "wait_exponential_jitter",
]


class AsyncClientMixin:
    """Mixin that adds async-context-manager support to API clients.

    Concrete clients must implement an async ``close()`` method. The mixin
    delegates ``__aexit__`` to ``self.close()`` so callers can write::

        async with PubChemClient() as client:
            await client.resolve_by_name("aspirin")
    """

    @abstractmethod
    async def close(self) -> None:  # pragma: no cover - abstract
        """Release any resources held by this client (httpx, sqlite, ...)."""
        raise NotImplementedError

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc: Any) -> None:
        del exc
        await self.close()


async def cached_request(
    *,
    source: str,
    method: str,
    url: str,
    body: str | None,
    call: Callable[[], Awaitable[T]],
) -> T:
    """Run ``call`` through the active :class:`ResponseCache`, if any.

    Mirrors the inlined pattern in pubchem/lens/uspto_odp/epo_ops/surechembl
    — when no cache is installed (or the cache is in ``DISABLED`` mode) the
    live call is invoked directly. Otherwise the cache wraps the call so the
    response is recorded/replayed. Cache hits bypass tenacity (we only retry
    live calls). Exceptions propagate unrecorded.

    Provided as a free function rather than a mixin method so it can be
    called from clients that already inherit from :class:`AsyncClientMixin`
    without touching their ``self`` typing.
    """
    cache = get_current_cache()
    if cache is None or cache.mode == CacheMode.DISABLED:
        return await call()
    return cast(
        "T",
        await cache.wrap(
            source=source,
            method=method,
            url=url,
            body=body,
            call=call,
        ),
    )


async def cached_bytes_request(
    *,
    source: str,
    method: str,
    url: str,
    body: str | None,
    call: Callable[[], Awaitable[bytes]],
) -> bytes:
    """Cache a bounded binary response through a JSON-safe base64 envelope."""

    async def _encoded_call() -> str:
        return base64.b64encode(await call()).decode("ascii")

    encoded = await cached_request(
        source=source,
        method=method,
        url=url,
        body=body,
        call=_encoded_call,
    )
    if not isinstance(encoded, str):
        raise ValueError("Cached binary response has an invalid envelope")
    try:
        return base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        raise ValueError("Cached binary response is malformed") from None
