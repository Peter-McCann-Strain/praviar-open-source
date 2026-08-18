"""Response cache — manifest v2 foundation for byte-identical replays.

Manifest v1 (already shipped) pins every *input* we control: git SHA of the
pipeline, hashes of every prompt file, model IDs, sampling parameters.
Re-running with a v1 manifest gives a structurally-similar report but can
drift if external APIs have added/removed data since the original run (a
new PubChem synonym, a new patent family member, a revoked Lens record).

This module adds the v2 capability: **capture every external API response
during the original run**, save them to a directory, and on replay load
the saved responses instead of hitting the live network. The result is a
replay that cannot drift on external data — only on code changes.

Design:

* One cache directory per run. Files are JSONL; each line is one request
  / response pair. The key is a sha256 over ``(method, url, body_hash)``.
* Clients opt-in explicitly via ``ResponseCache.wrap(coro, key)``. We do
  NOT intercept httpx at the transport level in v1: too magical, too
  easy to mis-cache non-idempotent calls. The explicit wrap keeps the
  semantics obvious per call site.
* ``record`` and ``replay`` modes are explicit. A cache in replay mode
  with no hit for a key raises ``CacheMissError`` — no silent fallthrough
  to the live network, per the no-silent-fallbacks rule.

Production runs install a private record-mode cache at bootstrap. Cache-aware
clients use it explicitly; exact replay installs the retained cache in strict
``REPLAY`` mode, where any missing request aborts instead of reaching live data.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeVar, cast

from praviar_pipeline.utils.private_artifacts import (
    append_private_text,
    atomic_write_text,
    ensure_private_directory,
    private_file_for_read,
)

T = TypeVar("T")


class CacheMode(StrEnum):
    """What the cache should do for each call."""

    #: Pass through to the wrapped coroutine and save its result.
    RECORD = "record"
    #: Look up the result; raise ``CacheMissError`` on miss.
    REPLAY = "replay"
    #: Look up the result; fall through to the wrapped coroutine on miss
    #: (and record the new result). Useful for incremental re-runs that
    #: tolerate fresh data for newly-requested keys.
    REPLAY_THEN_RECORD = "replay_then_record"
    #: No-op: call the coroutine, do not record or look up.
    DISABLED = "disabled"
    #: Zero-spend dry-run mode: never call the wrapped coroutine. Instead
    #: dispatch to a registered ``DryRunProvider`` keyed by ``source``.
    #: Used by :mod:`praviar_pipeline.dryrun` to smoke-test pipeline orchestration
    #: without touching live external APIs. If no provider is registered or
    #: it returns ``None``, raises :class:`DryRunProviderMissingError`.
    DRY_RUN = "dry_run"


class DryRunProviderMissingError(Exception):
    """Raised in DRY_RUN cache mode when no provider can answer a request.

    The dry-run harness registers a provider via :func:`set_dry_run_provider`
    that maps ``(source, method, url)`` to a canned response. If the
    provider returns ``None``, this error fires so that the test surface
    knows a source was reached that the harness has not been taught to
    fake — exactly the kind of gap the dry-run is meant to surface.
    """

    def __init__(self, source: str, method: str, url: str) -> None:
        self.source = source
        self.method = method
        self.url = url
        super().__init__(
            f"DRY_RUN cache mode: no canned response provider returned a value "
            f"for source={source!r} method={method!r} url={url!r}. "
            "Register a provider via set_dry_run_provider() before invoking the pipeline."
        )


class CacheMissError(Exception):
    """Raised by :class:`ResponseCache` in REPLAY mode when a key is absent.

    The key and cache path are attached so the caller can surface a clear
    error message (``praviar-pipeline replay`` maps this to a user-visible message).
    """

    def __init__(self, key: str, cache_path: Path) -> None:
        self.key = key
        self.cache_path = cache_path
        super().__init__(
            f"Cache miss for key {key[:16]}... in {cache_path}. "
            "Either the original run didn't make this call, or the cache "
            "is for a different run. Re-record or use --allow-live-fallback."
        )


def compute_request_key(
    *,
    source: str,
    method: str,
    url: str,
    body: str | bytes | None = None,
) -> str:
    """Return a deterministic sha256 hex key for a request.

    ``source`` is a short client identifier (``"pubchem"`` etc.) to keep
    different clients' keys from colliding if they happen to hit the same
    URL. ``method`` is upper-cased, ``url`` is used verbatim, ``body`` is
    hashed separately so its content contributes without being replayed
    into the key itself.
    """
    body_hash = ""
    if body is not None:
        body_bytes = body.encode("utf-8") if isinstance(body, str) else body
        body_hash = hashlib.sha256(body_bytes).hexdigest()
    blob = f"{source}\n{method.upper()}\n{url}\n{body_hash}".encode()
    return hashlib.sha256(blob).hexdigest()


@dataclass(slots=True)
class CacheEntry:
    """One cached request/response pair."""

    key: str
    source: str
    method: str
    url: str
    #: JSON-serialisable response payload (what the client's ``_get``
    #: etc. would have returned after parsing).
    response: Any
    #: Optional metadata — status code, headers we care about, timing.
    meta: dict[str, Any] = field(default_factory=dict)


class ResponseCache:
    """Record or replay external API responses for a single pipeline run.

    Thread-safe (a :class:`threading.Lock` guards the in-memory map and
    the append to the JSONL file). Intended for use by one pipeline run
    at a time — a single ``ResponseCache`` instance per run, passed to
    any client that opts into caching.
    """

    JSONL_FILENAME = "responses.jsonl"

    def __init__(
        self,
        *,
        cache_dir: Path,
        mode: CacheMode = CacheMode.DISABLED,
        manifest_reference: str = "",
    ) -> None:
        self._dir = Path(cache_dir)
        self._mode = mode
        self._manifest_reference = manifest_reference
        self._entries: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        if mode not in (CacheMode.DISABLED, CacheMode.DRY_RUN):
            ensure_private_directory(self._dir)
        if mode == CacheMode.RECORD:
            if os.path.lexists(self.cache_path):
                raise FileExistsError("Response cache already exists for record mode")
            atomic_write_text(self.cache_path, "")
        if mode in (CacheMode.REPLAY, CacheMode.REPLAY_THEN_RECORD):
            self._load_from_disk()

    # -- properties --------------------------------------------------------

    @property
    def mode(self) -> CacheMode:
        return self._mode

    @property
    def cache_path(self) -> Path:
        return self._dir / self.JSONL_FILENAME

    @property
    def manifest_reference(self) -> str:
        """Return the owner-only path reference retained in the manifest."""
        return self._manifest_reference

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def __iter__(self):
        return iter(self.keys())

    # -- persistence -------------------------------------------------------

    def _load_from_disk(self) -> None:
        path = self.cache_path
        if not os.path.lexists(path):
            return
        path = private_file_for_read(path)
        with path.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                parse_failed = False
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    parse_failed = True
                if parse_failed:
                    raise ValueError(
                        f"Response cache contains invalid JSON at line {lineno}"
                    ) from None
                entry = CacheEntry(
                    key=raw["key"],
                    source=raw["source"],
                    method=raw["method"],
                    url=raw["url"],
                    response=raw["response"],
                    meta=raw.get("meta", {}),
                )
                self._entries[entry.key] = entry

    def _append_to_disk(self, entry: CacheEntry) -> None:
        ensure_private_directory(self._dir)
        line = json.dumps(
            {
                "key": entry.key,
                "source": entry.source,
                "method": entry.method,
                "url": entry.url,
                "response": entry.response,
                "meta": entry.meta,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        append_private_text(self.cache_path, line + "\n")

    # -- core API ----------------------------------------------------------

    async def wrap(
        self,
        *,
        source: str,
        method: str,
        url: str,
        body: str | bytes | None,
        call: Callable[[], Awaitable[T]],
        meta: dict[str, Any] | None = None,
    ) -> T:
        """Run ``call`` under the cache's mode.

        In REPLAY mode, returns the cached response (raises
        :class:`CacheMissError` on miss). In RECORD or
        REPLAY_THEN_RECORD mode, calls through and caches the result.
        In DISABLED mode, just calls through.
        """
        key = compute_request_key(source=source, method=method, url=url, body=body)

        if self._mode == CacheMode.DISABLED:
            return await call()

        if self._mode == CacheMode.DRY_RUN:
            provider = get_dry_run_provider()
            if provider is None:
                raise DryRunProviderMissingError(source=source, method=method, url=url)
            response = provider(source=source, method=method, url=url, body=body)
            if response is None:
                raise DryRunProviderMissingError(source=source, method=method, url=url)
            return cast("T", response)

        if self._mode in (CacheMode.REPLAY, CacheMode.REPLAY_THEN_RECORD):
            with self._lock:
                existing = self._entries.get(key)
            if existing is not None:
                return cast("T", existing.response)
            if self._mode == CacheMode.REPLAY:
                raise CacheMissError(key, self.cache_path)

        # Either RECORD, or REPLAY_THEN_RECORD with a miss.
        result = await call()
        entry = CacheEntry(
            key=key,
            source=source,
            method=method.upper(),
            url=url,
            response=result,
            meta=meta or {},
        )
        with self._lock:
            # Only persist the first observation — later RECORD calls
            # with the same key would overwrite, masking nondeterminism
            # we want to see surface during testing.
            if key not in self._entries:
                self._entries[key] = entry
                self._append_to_disk(entry)
        return result

    # -- introspection -----------------------------------------------------

    def keys(self) -> list[str]:
        """Return all recorded keys, sorted, for test assertions."""
        with self._lock:
            return sorted(self._entries)

    def digest(self) -> str:
        """Return an unkeyed change-detection digest of the complete cache.

        This detects response or metadata drift as well as request-set drift. It
        is not an authentication primitive; production replay still requires a
        separately authenticated manifest or signature.
        """
        with self._lock:
            entries = [
                {
                    "key": entry.key,
                    "source": entry.source,
                    "method": entry.method,
                    "url": entry.url,
                    "response": entry.response,
                    "meta": entry.meta,
                }
                for _, entry in sorted(self._entries.items())
            ]
        canonical = json.dumps(
            {"schema_version": 1, "entries": entries},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def authenticated_digest(self, *, key: bytes) -> str:
        """Authenticate the complete cache digest with a non-exported audit key."""
        return hmac.new(
            key,
            b"praviar-response-cache-v1\0" + self.digest().encode("ascii"),
            hashlib.sha256,
        ).hexdigest()


# -- module-level accessor pattern --------------------------------------------


_CURRENT_CACHE: ContextVar[ResponseCache | None] = ContextVar(
    "praviar_response_cache",
    default=None,
)


def set_current_cache(cache: ResponseCache | None) -> None:
    """Install (or clear) the pipeline-run's active cache.

    Context-local storage isolates concurrent pipeline runs while allowing
    child tasks within one run to share the same exact-response record.
    """
    _CURRENT_CACHE.set(cache)


def get_current_cache() -> ResponseCache | None:
    """Return the current run's cache, or ``None`` when caching is off."""
    return _CURRENT_CACHE.get()


# -- dry-run provider registry ------------------------------------------------

#: Signature: provider(source, method, url, body) -> response or None.
#: Returning ``None`` signals "I do not know how to fake this call" and
#: causes :class:`DryRunProviderMissingError` to fire.
DryRunProvider = Callable[..., Any]

_DRY_RUN_PROVIDER: DryRunProvider | None = None
_DRY_RUN_PROVIDER_LOCK = threading.Lock()


def set_dry_run_provider(provider: DryRunProvider | None) -> None:
    """Install (or clear) the global DRY_RUN provider.

    Only consulted when the active cache is in :attr:`CacheMode.DRY_RUN`.
    The harness in :mod:`praviar_pipeline.dryrun` sets this on enter and clears
    it on exit.
    """
    global _DRY_RUN_PROVIDER
    with _DRY_RUN_PROVIDER_LOCK:
        _DRY_RUN_PROVIDER = provider


def get_dry_run_provider() -> DryRunProvider | None:
    """Return the currently-installed DRY_RUN provider, or ``None``."""
    with _DRY_RUN_PROVIDER_LOCK:
        return _DRY_RUN_PROVIDER
