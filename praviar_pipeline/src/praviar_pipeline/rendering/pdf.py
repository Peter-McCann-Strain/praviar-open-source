"""PDF renderer — generates FTO reports via modular Typst template system.

Pre-renders charts (matplotlib PNG), chemical structures (RDKit SVG),
and branding config (JSON), then passes everything to the Typst compiler
via --input flags.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess as _stdlib_subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.config import get_settings
from praviar_pipeline.output_safety import sanitize_error_fields_for_output
from praviar_pipeline.rendering.governed_decision import (
    governed_blocking_count,
    governed_executive_summary,
    governed_risk_level,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.report import FTOReport
    from praviar_pipeline.rendering.branding import BrandingConfig
    from praviar_pipeline.rendering.export_options import ExportRenderOptions

logger = structlog.get_logger()


class _SubprocessFacade:
    run = staticmethod(_stdlib_subprocess.run)


subprocess = _SubprocessFacade


def _typst_available() -> bool:
    """Check if Typst is installed on the system."""
    return shutil.which("typst") is not None


def render_pdf(
    report: FTOReport,
    output_path: Path,
    branding: BrandingConfig | None = None,
    reviewer_decisions: list[dict] | None = None,
    options: ExportRenderOptions | None = None,
) -> Path:
    """Render an FTO report as PDF via the modular Typst template.

    Args:
        report: Complete FTOReport with all analysis data.
        output_path: Where to write the output PDF.
        branding: Optional white-label branding configuration.
        reviewer_decisions: Optional list of reviewer accept/reject/edit
            decisions (SG-reviewer / WS-3). Each dict carries at minimum
            ``finding_type``, ``finding_ref``, ``decision``, ``note``,
            ``edited_text``, ``reviewer_name``, ``reviewer_email`` and
            ``created_at``. When provided, they are rendered as the final
            appendix in the PDF.

    Returns:
        Path to the generated PDF file.

    Raises:
        RuntimeError: If Typst is not installed or compilation fails.
    """
    if not _typst_available():
        raise RuntimeError(
            "Typst is not installed. Install it: https://typst.app/docs/guides/install/"
        )
    if report.manifest is None:
        raise RuntimeError(
            "Report manifest is required before PDF rendering; export cannot "
            "synthesize historical run provenance from current settings."
        )
    rendered_path = _render_via_typst(
        report,
        output_path,
        branding,
        reviewer_decisions,
        options,
    )
    from praviar_pipeline.rendering.artifact_quality import validate_pdf_artifact

    validate_pdf_artifact(
        rendered_path,
        expected_text=(report.compound.name,),
    )
    return rendered_path


def _generate_charts(report: FTOReport, assets_dir: Path) -> None:
    """Generate all chart PNGs in parallel and write to assets directory."""
    from praviar_pipeline.rendering.charts import (
        render_funnel_chart,
        render_risk_distribution_chart,
    )

    def _write_chart(name: str, generator, *args) -> None:
        try:
            b64_png = generator(*args)
            (assets_dir / f"{name}.png").write_bytes(base64.b64decode(b64_png))
            logger.debug("chart_generated", chart=name)
        except Exception as exc:
            logger.error("chart_generation_failed", chart=name)
            raise RuntimeError(f"Required PDF chart generation failed: {name}") from exc

    with ThreadPoolExecutor(max_workers=1) as pool:
        futures = []
        # Always generate these two
        futures.append(
            pool.submit(_write_chart, "funnel_chart", render_funnel_chart, report.audit_trail)
        )
        futures.append(
            pool.submit(
                _write_chart,
                "risk_distribution",
                render_risk_distribution_chart,
                report.patent_analyses,
            )
        )

        # Additional charts
        from praviar_pipeline.rendering.charts import (
            render_assignee_chart,
            render_patent_timeline,
            render_risk_gauge,
            render_source_health_chart,
        )

        if report.patent_analyses:
            futures.append(
                pool.submit(
                    _write_chart,
                    "patent_timeline",
                    render_patent_timeline,
                    report.patent_analyses,
                    report.patent_details,
                )
            )

        futures.append(
            pool.submit(
                _write_chart,
                "risk_gauge",
                render_risk_gauge,
                governed_risk_level(report),
                governed_blocking_count(report),
                report.risk_summary.total_patents_analyzed,
            )
        )

        if report.patent_analyses:
            futures.append(
                pool.submit(
                    _write_chart,
                    "assignee_chart",
                    render_assignee_chart,
                    report.patent_analyses,
                )
            )

        if report.source_health.entries:
            futures.append(
                pool.submit(
                    _write_chart,
                    "source_health",
                    render_source_health_chart,
                    report.source_health.entries,
                )
            )

        for future in futures:
            future.result()


def _generate_structures(report: FTOReport, assets_dir: Path) -> None:
    """Generate chemical structure SVGs and write to assets directory."""
    try:
        from praviar_pipeline.rendering.structures import (
            render_comparison_svg,
            render_compound_svg,
        )
    except ImportError as exc:
        logger.error("structures_module_unavailable")
        raise RuntimeError("PDF structure rendering module is unavailable") from exc

    # Target compound structure
    try:
        svg = render_compound_svg(report.compound.canonical_smiles)
        if svg:
            (assets_dir / "target_structure.svg").write_text(svg, encoding="utf-8")
            logger.debug("structure_generated", type="target")
        else:
            raise RuntimeError("target structure renderer returned empty SVG")
    except Exception as exc:
        logger.error("target_structure_failed")
        raise RuntimeError("Required target structure generation failed") from exc

    # Comparison figures for each analyzed patent
    for a in report.patent_analyses:
        patent_data = report.patent_details.get(a.patent_id, {})
        # Try to find a SMILES for the patent compound
        patent_smiles = None
        if isinstance(patent_data, dict):
            patent_smiles = patent_data.get("match_smiles") or patent_data.get("canonical_smiles")

        if patent_smiles:
            try:
                svg = render_comparison_svg(report.compound.canonical_smiles, patent_smiles)
                if svg:
                    safe_id = a.patent_id.replace("/", "_").replace(" ", "_")
                    (assets_dir / f"comparison_{safe_id}.svg").write_text(svg, encoding="utf-8")
                else:
                    raise RuntimeError("comparison renderer returned empty SVG")
            except Exception as exc:
                logger.error("comparison_structure_failed")
                raise RuntimeError(
                    f"Required comparison structure generation failed for {a.patent_id}"
                ) from exc


def _render_via_typst(
    report: FTOReport,
    output_path: Path,
    branding: BrandingConfig | None = None,
    reviewer_decisions: list[dict] | None = None,
    options: ExportRenderOptions | None = None,
) -> Path:
    """Render PDF via the modular Typst template system."""
    from praviar_pipeline.rendering.branding import get_default_branding
    from praviar_pipeline.rendering.evidence_scope import build_evidence_scope_payload
    from praviar_pipeline.rendering.export_options import default_export_options

    if report.manifest is None:
        raise RuntimeError("Report manifest is required before PDF rendering.")

    options = options or default_export_options()
    if branding is None:
        branding = get_default_branding()

    template_path = Path(__file__).parent / "templates" / "report.typ"
    if not template_path.is_file():
        raise RuntimeError(f"Typst template not found: {template_path}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        typst_root = tmpdir_path / "templates"
        shutil.copytree(template_path.parent, typst_root)
        work_template_path = typst_root / "report.typ"
        assets_path = typst_root / "assets"
        assets_path.mkdir()

        # 1. Generate chart PNGs (parallel) and structure SVGs first
        _generate_charts(report, assets_path)
        _generate_structures(report, assets_path)

        # 2. Serialize report to JSON with asset-availability flags
        report_data = sanitize_error_fields_for_output(report.model_dump(mode="json"))
        report_data["_governed_risk_level"] = governed_risk_level(report).value
        report_data["risk_summary"]["blocking_patents_count"] = governed_blocking_count(report)
        report_data["risk_summary"]["executive_summary"] = governed_executive_summary(report)
        report_data["risk_summary"]["key_risks"] = []
        # Inject flags so Typst templates know which images exist
        report_data["_has_structure_image"] = (assets_path / "target_structure.svg").is_file()
        report_data["_has_funnel_chart"] = (assets_path / "funnel_chart.png").is_file()
        report_data["_has_risk_distribution"] = (assets_path / "risk_distribution.png").is_file()
        report_data["_has_risk_gauge"] = (assets_path / "risk_gauge.png").is_file()
        report_data["_has_patent_timeline"] = (assets_path / "patent_timeline.png").is_file()
        report_data["_has_assignee_chart"] = (assets_path / "assignee_chart.png").is_file()
        report_data["_has_source_health"] = (assets_path / "source_health.png").is_file()
        # Per-patent comparison image flags
        for a in report_data.get("patent_analyses", []):
            pid = a.get("patent_id", "")
            safe_id = pid.replace("/", "_").replace(" ", "_")
            comparison_png = assets_path / f"comparison_{safe_id}.png"
            comparison_svg = assets_path / f"comparison_{safe_id}.svg"
            a["_comparison_image_id"] = safe_id
            a["_comparison_image_ext"] = (
                "png" if comparison_png.is_file() else "svg" if comparison_svg.is_file() else None
            )
            a["_has_comparison_image"] = a["_comparison_image_ext"] is not None

        # Inject reviewer decisions (SG-reviewer / WS-3). Always include the
        # key so the Typst template can render a stable "no decisions" line
        # when the list is empty rather than silently eliding the appendix.
        report_data["reviewer_decisions"] = list(reviewer_decisions or [])
        report_data["export_options"] = options.model_dump()
        report_data["_evidence_scope"] = build_evidence_scope_payload(report_data)

        data_path = typst_root / "report.json"
        data_path.write_text(
            json.dumps(report_data, default=str, indent=2),
            encoding="utf-8",
        )

        export_options_path = typst_root / "export_options.json"
        export_options_path.write_text(
            json.dumps(options.model_dump(), default=str, indent=2),
            encoding="utf-8",
        )

        # 3. Serialize branding config with computed properties and local assets
        branding_data = _typst_branding_payload(branding, assets_path)
        branding_path = typst_root / "branding.json"
        branding_path.write_text(
            json.dumps(branding_data, default=str),
            encoding="utf-8",
        )

        # 4. Compile via Typst with --input flags
        cmd = [
            "typst",
            "compile",
            "--ignore-system-fonts",
            "--pdf-standard",
            "ua-1",
            "--input",
            "data-path=report.json",
            "--input",
            "assets-dir=../assets",
            "--input",
            "branding-path=branding.json",
            "--input",
            "export-options-path=export_options.json",
            str(work_template_path),
            str(output_path),
        ]

        # Pass environment with template directory for Typst imports
        env = os.environ.copy()
        env["TYPST_ROOT"] = str(typst_root)

        logger.info(
            "typst_compile_started",
            template=str(work_template_path),
            assets=str(assets_path),
        )

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=get_settings().pdf_typst_timeout,
            env=env,
            cwd=typst_root,
        )

        if result.returncode != 0:
            stderr_excerpt = result.stderr
            if len(stderr_excerpt) > 4000:
                stderr_excerpt = f"{result.stderr[:2000]}\n...\n{result.stderr[-2000:]}"
            logger.error("typst_compile_failed")
            raise RuntimeError(f"Typst compile failed: {stderr_excerpt}")

        if "unknown font family" in result.stderr.lower():
            logger.error("typst_font_resolution_failed")
            raise RuntimeError(f"Typst font resolution failed: {result.stderr}")

        logger.info("typst_compile_succeeded")
        return output_path


def _typst_branding_payload(branding: BrandingConfig, assets_path: Path) -> dict:
    """Return Typst-safe branding JSON with any custom logo copied locally."""
    from praviar_pipeline.rendering.branding import resolve_branding_logo_path

    branding_data = branding.model_dump()
    logo_source = resolve_branding_logo_path(branding, renderer_name="PDF")
    if logo_source is not None:
        suffix = logo_source.suffix.lower()
        logo_target = assets_path / f"branding_logo{suffix}"
        shutil.copyfile(logo_source, logo_target)
        branding_data["logo_path"] = f"../assets/{logo_target.name}"

    branding_data["header_text"] = branding.header_text
    branding_data["footer_text"] = branding.footer_text
    branding_data["display_name"] = branding.display_name
    branding_data["suppresses_praviar_branding"] = branding.suppresses_praviar_branding
    branding_data["disclaimer_text"] = branding.effective_disclaimer_text
    branding_data["legal_marking"] = branding.legal_marking
    branding_data["privilege_header"] = None
    return branding_data
