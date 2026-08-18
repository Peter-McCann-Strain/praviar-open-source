"""Rendering package — Markdown, PDF, XLSX, CSV, DOCX, and PPTX output for FTO reports."""

from praviar_pipeline.rendering.csv import render_csv
from praviar_pipeline.rendering.markdown import render_markdown
from praviar_pipeline.rendering.pdf import render_pdf
from praviar_pipeline.rendering.xlsx import render_xlsx

# DOCX and PPTX require optional dependencies (python-docx, python-pptx).
# Import lazily to avoid ImportError in environments without them.
try:
    from praviar_pipeline.rendering.docx_report import render_docx
except ImportError:

    def render_docx(*args, **kwargs):  # type: ignore[misc]
        raise ImportError(
            "Install python-docx to use DOCX export: pip install 'praviar_pipeline[export]'"
        )


try:
    from praviar_pipeline.rendering.pptx_report import render_pptx
except ImportError:

    def render_pptx(*args, **kwargs):  # type: ignore[misc]
        raise ImportError(
            "Install python-pptx to use PPTX export: pip install 'praviar_pipeline[export]'"
        )


__all__ = [
    "render_csv",
    "render_docx",
    "render_markdown",
    "render_pdf",
    "render_pptx",
    "render_xlsx",
]
