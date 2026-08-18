"""Report output helpers for the Praviar Pipeline runtime."""

from __future__ import annotations

import asyncio
import json

import structlog

from praviar_pipeline.config import get_settings
from praviar_pipeline.utils.private_artifacts import (
    atomic_write_text,
    enforce_private_file,
    ensure_private_directory,
    prepare_private_output_path,
)

logger = structlog.get_logger()


async def write_pipeline_outputs(report, output_format: str) -> dict:
    """Persist the canonical JSON report and any requested alternate format."""
    report_dict: dict[str, object] = report.model_dump(mode="json")

    settings = get_settings()
    output_dir = settings.resolved_output_dir
    ensure_private_directory(output_dir)
    report_slug = f"fto_report_{report.report_id[:8]}"
    logger.info("output_directory")

    json_path = output_dir / f"{report_slug}.json"
    json_content = json.dumps(report_dict, indent=2, default=str)

    def _write_json() -> None:
        atomic_write_text(json_path, json_content)

    await asyncio.to_thread(_write_json)
    logger.info("json_report_written")

    if report.manifest is not None:
        manifest_path = output_dir / f"{report_slug}.manifest.json"
        manifest_content = report.manifest.model_dump_json(indent=2)

        def _write_manifest() -> None:
            atomic_write_text(manifest_path, manifest_content)

        await asyncio.to_thread(_write_manifest)
        logger.info("manifest_written")

    if output_format == "markdown":
        from praviar_pipeline.rendering import render_markdown

        md = render_markdown(report)
        md_path = output_dir / f"{report_slug}.md"

        def _write_md() -> None:
            atomic_write_text(md_path, md)

        await asyncio.to_thread(_write_md)
        logger.info("markdown_report_written")
    elif output_format == "pdf":
        from praviar_pipeline.rendering import render_pdf

        pdf_path = output_dir / f"{report_slug}.pdf"
        prepare_private_output_path(pdf_path)
        await asyncio.to_thread(render_pdf, report, pdf_path)
        enforce_private_file(pdf_path)
        logger.info("pdf_report_written")

    return report_dict
