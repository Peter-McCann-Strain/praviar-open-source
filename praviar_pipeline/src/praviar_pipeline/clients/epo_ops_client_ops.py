"""Endpoint-level orchestration helpers for the EPO OPS client."""

from __future__ import annotations

from typing import Protocol

import structlog

from praviar_pipeline.clients.epo_ops_helpers import (
    build_drawing_page_path,
    build_drawing_range_header,
    collect_drawings,
    to_docdb_format,
    to_epodoc_publication_format,
)
from praviar_pipeline.clients.epo_ops_parsing import (
    extract_drawing_page_count,
    parse_biblio,
    parse_claims_text,
    parse_family,
    parse_legal_status,
    parse_register,
)
from praviar_pipeline.errors import EPOCredentialsMissingError

logger = structlog.get_logger()

EPO_HARD_MAX_DRAWING_PAGES = 100


class _EPOOPSClientLike(Protocol):
    _consumer_key: str
    _consumer_secret: str

    async def _get(self, path: str, *, ok_on_404: bool = False) -> dict: ...

    async def _get_binary(
        self,
        path: str,
        accept: str = "image/png",
        headers: dict[str, str] | None = None,
        max_bytes: int | None = None,
    ) -> bytes | None: ...

    async def get_drawing_page_count(self, patent_id: str) -> int: ...

    async def fetch_drawing_page(
        self,
        patent_id: str,
        page: int = 1,
        image_format: str = "image/png",
    ) -> bytes | None: ...


async def _get_docdb_json(client: _EPOOPSClientLike, patent_id: str, suffix: str) -> dict:
    """Semantic-empty-on-404 DOCDB fetch (legal/biblio/claims/images).

    OPS returns 404 for patents without the requested facet; that's an empty
    result, not a source failure, so we pass ``ok_on_404=True``.
    """
    docdb = to_docdb_format(patent_id)
    data = await client._get(
        f"/published-data/publication/docdb/{docdb}/{suffix}",
        ok_on_404=True,
    )
    return data or {}


async def get_legal_status(client: _EPOOPSClientLike, patent_id: str) -> list[dict]:
    """Fetch and parse INPADOC legal events."""
    docdb = to_docdb_format(patent_id)
    data = await client._get(
        f"/legal/publication/docdb/{docdb}",
        ok_on_404=True,
    )
    return parse_legal_status(data or {})


async def get_family(client: _EPOOPSClientLike, patent_id: str) -> dict:
    """Fetch and parse the DOCDB patent family.

    404 here means the patent has no family relatives on file — a semantic
    empty, not a source failure.
    """
    docdb = to_docdb_format(patent_id)
    data = await client._get(
        f"/family/publication/docdb/{docdb}",
        ok_on_404=True,
    )
    if not data:
        return {}
    return parse_family(data)


async def get_biblio(client: _EPOOPSClientLike, patent_id: str) -> dict:
    """Fetch and parse bibliographic metadata."""
    data = await _get_docdb_json(client, patent_id, "biblio")
    if not data:
        return {}
    return parse_biblio(data)


async def get_claims_text(client: _EPOOPSClientLike, patent_id: str) -> str:
    """Fetch and parse the English claims text."""
    return parse_claims_text(await _get_docdb_json(client, patent_id, "claims"))


async def get_register(client: _EPOOPSClientLike, patent_id: str) -> dict:
    """Fetch and parse central EP Register data from the documented endpoint.

    404 here means no register entry for this publication — semantic empty.
    National post-grant status is not supplied by this endpoint.
    """
    epodoc = to_epodoc_publication_format(patent_id)
    core_data = await client._get(
        (f"/register/publication/epodoc/{epodoc}/biblio,events,procedural-steps"),
        ok_on_404=True,
    )
    if not core_data:
        return {}
    unitary_data = await client._get(
        f"/register/publication/epodoc/{epodoc}/upp",
        ok_on_404=True,
    )
    return parse_register(core_data, unitary_data=unitary_data or {})


async def get_drawing_page_count(client: _EPOOPSClientLike, patent_id: str) -> int:
    """Fetch the image inquiry response and derive the available page count."""
    return extract_drawing_page_count(
        await _get_docdb_json(client, patent_id, "images"),
    )


async def fetch_drawing_page(
    client: _EPOOPSClientLike,
    patent_id: str,
    page: int = 1,
    image_format: str = "image/png",
) -> bytes | None:
    """Fetch a single drawing page image."""
    docdb = to_docdb_format(patent_id)
    path = build_drawing_page_path(docdb, page, image_format)
    range_header = build_drawing_range_header(page)
    return await client._get_binary(path, accept=image_format, headers={"Range": range_header})


async def fetch_all_drawings(
    client: _EPOOPSClientLike,
    patent_id: str,
    max_pages: int = 0,
    image_format: str = "image/png",
    *,
    fail_closed: bool = False,
) -> list[tuple[int, bytes]]:
    """Fetch all available drawing pages for a patent.

    Raises:
        EPOCredentialsMissingError: OPS consumer key/secret not configured.
            The orchestrator should treat this as a SKIPPED source (a config
            choice), not a FAILED one. Subclass of ``AuthenticationError`` so
            existing auth handlers still cover it.
    """
    if not client._consumer_key or not client._consumer_secret:
        logger.warning(
            "epo_drawings_skipped",
        )
        raise EPOCredentialsMissingError(
            "EPO OPS drawings unavailable: consumer key/secret not configured",
        )

    n_pages = await client.get_drawing_page_count(patent_id)
    if n_pages == 0:
        # Legitimate semantic empty: patent genuinely has no drawings on file.
        logger.debug(
            "epo_no_drawings",
        )
        return []

    configured_cap = max_pages or EPO_HARD_MAX_DRAWING_PAGES
    pages_to_fetch = min(n_pages, configured_cap, EPO_HARD_MAX_DRAWING_PAGES)
    logger.info(
        "epo_fetching_drawings",
        total_pages=n_pages,
        fetching=pages_to_fetch,
    )
    return await collect_drawings(
        patent_id=patent_id,
        pages_to_fetch=pages_to_fetch,
        image_format=image_format,
        fetch_drawing_page=client.fetch_drawing_page,
        logger=logger,
        fail_closed=fail_closed,
    )
