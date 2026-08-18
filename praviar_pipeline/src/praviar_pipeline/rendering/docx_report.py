"""Full DOCX renderer for FTO reports.

Produces a structured reviewer Word document with styled tables, claim charts,
risk coloring, chemical structure images, and all FTOReport fields. Rendering
quality does not establish legal accuracy or fitness for legal use.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.rendering.docx_report_layout import configure_document
from praviar_pipeline.rendering.docx_report_sections import build_report_sections

if TYPE_CHECKING:
    from praviar_pipeline.models.report import FTOReport
    from praviar_pipeline.rendering.branding import BrandingConfig
    from praviar_pipeline.rendering.export_options import ExportRenderOptions

log = structlog.get_logger()

__all__ = ["render_docx"]


def render_docx(
    report: FTOReport,
    branding: BrandingConfig | None = None,
    options: ExportRenderOptions | None = None,
) -> bytes:
    """Render a structured DOCX review artifact.

    Returns the DOCX file as bytes.
    """
    from docx import Document

    from praviar_pipeline.rendering.branding import get_default_branding

    if branding is None:
        branding = get_default_branding()

    log.info("docx_render_started")
    try:
        doc = Document()
        configure_document(doc, branding)
        build_report_sections(doc, report, branding, options=options)
        from praviar_pipeline.rendering.artifact_quality import validate_docx_document

        validate_docx_document(doc, expected_text=(report.compound.name,))

        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        log.info("docx_render_completed")
        return buf.read()
    except Exception:
        log.error("docx_render_failed")
        raise
