"""PatCID local index client — InChIKey to patent mappings from static dataset."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import structlog

from praviar_pipeline.clients.base import AsyncClientMixin
from praviar_pipeline.config import PROJECT_ROOT
from praviar_pipeline.errors import PatCIDDatabaseNotFoundError

logger = structlog.get_logger()

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "patcid" / "patcid.db"


class PatCIDClient(AsyncClientMixin):
    """Client for the local PatCID SQLite index.

    PatCID is a static 5.7GB JSONL dataset mapping 14M chemical structures
    to patent IDs. We pre-index it into SQLite keyed by InChIKey for fast
    lookups.

    The index is created by `praviar-pipeline index-patcid`.
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def _ensure_connection(self) -> sqlite3.Connection:
        """Lazy-load SQLite connection. Raises if database not found."""
        if self._conn is not None:
            return self._conn
        if not self._db_path.exists():
            raise PatCIDDatabaseNotFoundError("configured database")
        connection = sqlite3.connect(str(self._db_path))
        connection.row_factory = sqlite3.Row
        self._conn = connection
        return connection

    async def lookup_by_inchikey(self, inchikey: str) -> list[str]:
        """Look up patent IDs for an InChIKey.

        Returns a list of patent ID strings. When a
        :class:`~praviar_pipeline.response_cache.ResponseCache` is installed, the
        SQLite query is wrapped so deterministic replays don't depend on the
        local PatCID database being present. ``method="QUERY"`` and the
        InChIKey-as-URL together form the cache key.
        """
        # Inline import — survives the aggressive format hook.
        from praviar_pipeline.response_cache import CacheMode, get_current_cache

        cache = get_current_cache()
        if cache is None or cache.mode == CacheMode.DISABLED:
            return await self._lookup_by_inchikey_uncached(inchikey)
        return await cache.wrap(
            source="patcid",
            method="QUERY",
            url=f"inchikey={inchikey}",
            body=None,
            call=lambda: self._lookup_by_inchikey_uncached(inchikey),
        )

    async def _lookup_by_inchikey_uncached(self, inchikey: str) -> list[str]:
        """Underlying live SQLite query — never cached here."""
        conn = self._ensure_connection()

        def _query():
            try:
                cursor = conn.execute(
                    "SELECT patent_id FROM compound_patents WHERE inchikey = ?",
                    (inchikey,),
                )
                return [row["patent_id"] for row in cursor.fetchall()]
            except sqlite3.OperationalError:
                raise PatCIDDatabaseNotFoundError("configured database") from None

        return await asyncio.to_thread(_query)

    async def lookup_by_inchikey_prefix(self, prefix: str) -> list[dict]:
        """Look up patents by InChIKey first layer (connectivity).

        Useful for finding patents covering stereoisomers and salts.
        The first 14 characters of InChIKey encode the molecular skeleton.

        When a :class:`~praviar_pipeline.response_cache.ResponseCache` is installed
        the SQLite LIKE query is wrapped so replays don't need the local DB.
        """
        # Inline import — survives the aggressive format hook.
        from praviar_pipeline.response_cache import CacheMode, get_current_cache

        cache = get_current_cache()
        if cache is None or cache.mode == CacheMode.DISABLED:
            return await self._lookup_by_inchikey_prefix_uncached(prefix)
        return await cache.wrap(
            source="patcid",
            method="QUERY",
            url=f"inchikey_prefix={prefix}",
            body=None,
            call=lambda: self._lookup_by_inchikey_prefix_uncached(prefix),
        )

    async def _lookup_by_inchikey_prefix_uncached(self, prefix: str) -> list[dict]:
        """Underlying live SQLite query — never cached here."""
        import sqlite3

        conn = self._ensure_connection()

        def _query():
            try:
                cursor = conn.execute(
                    "SELECT inchikey, patent_id FROM compound_patents WHERE inchikey LIKE ?",
                    (f"{prefix}%",),
                )
                return [dict(row) for row in cursor.fetchall()]
            except sqlite3.OperationalError:
                raise PatCIDDatabaseNotFoundError("configured database") from None

        return await asyncio.to_thread(_query)

    async def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
