"""Full PPTX renderer for FTO reports.

Produces a 17-25 slide structured review presentation with charts, risk matrix,
chemical structure images, and speaker notes.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.rendering.pptx_report_deck import build_pptx_presentation

if TYPE_CHECKING:
    from praviar_pipeline.models.report import FTOReport
    from praviar_pipeline.rendering.branding import BrandingConfig
    from praviar_pipeline.rendering.export_options import ExportRenderOptions

log = structlog.get_logger()

__all__ = ["render_pptx"]


def render_pptx(
    report: FTOReport,
    branding: BrandingConfig | None = None,
    options: ExportRenderOptions | None = None,
) -> bytes:
    """Render a structured PPTX review artifact.

    Returns the PPTX file as bytes.
    """
    from praviar_pipeline.rendering.branding import get_default_branding

    if branding is None:
        branding = get_default_branding()

    log.info("pptx_render_started")
    try:
        prs = build_pptx_presentation(report, branding, options=options)

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        log.info("pptx_render_completed", slides=len(prs.slides))
        return buf.read()
    except Exception:
        log.error("pptx_render_failed")
        raise
