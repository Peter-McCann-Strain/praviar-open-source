"""PDF fallback rendering helpers for patent drawing analysis."""

from __future__ import annotations

import importlib
import io
import math
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.clients.epo_ops import _to_docdb_format
from praviar_pipeline.errors import ConfigurationError, SourceUnavailableError
from praviar_pipeline.utils.private_artifacts import atomic_write_bytes

if TYPE_CHECKING:
    from pathlib import Path

    from praviar_pipeline.clients.epo_ops import EPOOPSClient

logger = structlog.get_logger()

DRAWING_PDF_HARD_MAX_PAGES = 100
DRAWING_PDF_HARD_MAX_BYTES = 100 * 1024 * 1024
DRAWING_PDF_HARD_MAX_PIXELS_PER_PAGE = 40_000_000
DRAWING_PDF_HARD_MAX_TOTAL_PIXELS = 250_000_000


async def fetch_pdf_fallback(
    patent_id: str,
    epo_client: EPOOPSClient,
    work_dir: Path,
    *,
    max_pages: int = 30,
    max_pdf_bytes: int = 100 * 1024 * 1024,
    max_pixels_per_page: int = 40_000_000,
    max_total_pixels: int = 250_000_000,
) -> list[tuple[int, bytes]]:
    """Download the full patent PDF and render pages as PNG bytes."""
    effective_pdf_bytes = min(max_pdf_bytes, DRAWING_PDF_HARD_MAX_BYTES)
    effective_pixels_per_page = min(
        max_pixels_per_page,
        DRAWING_PDF_HARD_MAX_PIXELS_PER_PAGE,
    )
    effective_total_pixels = min(max_total_pixels, DRAWING_PDF_HARD_MAX_TOTAL_PIXELS)
    if min(effective_pdf_bytes, effective_pixels_per_page, effective_total_pixels) < 1:
        raise ValueError("drawing PDF resource limits must be positive")

    try:
        pdfium = importlib.import_module("pypdfium2")
    except ImportError:
        raise ConfigurationError(
            "pypdfium2 is required for configured drawing PDF fallback",
            source="pypdfium2",
            step="drawing_pdf_fallback",
        ) from None

    docdb = _to_docdb_format(patent_id)
    pdf_bytes = await epo_client._get_binary(
        f"/published-data/publication/docdb/{docdb}/fulltext.pdf",
        accept="application/pdf",
        max_bytes=effective_pdf_bytes,
    )
    if not pdf_bytes:
        return []
    if len(pdf_bytes) > effective_pdf_bytes:
        raise SourceUnavailableError("epo_ops", "drawing PDF exceeded byte limit")

    effective_max_pages = min(max_pages or DRAWING_PDF_HARD_MAX_PAGES, DRAWING_PDF_HARD_MAX_PAGES)
    if effective_max_pages < 1:
        raise ValueError("max_pages must not be negative")

    pdf_path = work_dir / f"{patent_id.replace('/', '_')}_full.pdf"
    atomic_write_bytes(pdf_path, pdf_bytes)

    pages: list[tuple[int, bytes]] = []
    total_pixels = 0
    document = pdfium.PdfDocument(str(pdf_path))
    try:
        for page_number in range(min(len(document), effective_max_pages)):
            page = document[page_number]
            try:
                width_points, height_points = page.get_size()
                render_scale = 300 / 72
                pixel_count = math.ceil(width_points * render_scale) * math.ceil(
                    height_points * render_scale
                )
                if pixel_count > effective_pixels_per_page:
                    raise SourceUnavailableError("epo_ops", "drawing PDF page exceeded pixel limit")
                if total_pixels + pixel_count > effective_total_pixels:
                    raise SourceUnavailableError(
                        "epo_ops", "drawing PDF exceeded total pixel limit"
                    )
                total_pixels += pixel_count

                bitmap = page.render(scale=render_scale)
                try:
                    rendered = bitmap.to_pil()
                    output = io.BytesIO()
                    rendered.save(output, format="PNG")
                    pages.append((page_number + 1, output.getvalue()))
                finally:
                    bitmap.close()
            finally:
                page.close()
    finally:
        document.close()

    logger.info("pdf_fallback_rendered", pages_rendered=len(pages))
    return pages
