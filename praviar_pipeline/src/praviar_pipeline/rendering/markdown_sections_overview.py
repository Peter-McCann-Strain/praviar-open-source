"""Overview section renderers for Markdown FTO reports."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.rendering.design import risk_display as _risk_display
from praviar_pipeline.rendering.evidence_scope import (
    source_status_detail,
    source_status_label,
    summarize_evidence_scope,
)
from praviar_pipeline.rendering.governed_decision import (
    governed_decision_label,
    governed_executive_summary,
    governed_risk_level,
)
from praviar_pipeline.rendering.markdown_support import (
    format_claim_numbers,
    format_orange_book_status,
    format_ptab_status,
    risk_sort_key,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.report import FTOReport


def render_header(lines: list[str], report: FTOReport) -> None:
    lines.append("# Freedom-to-Operate Analysis Report")
    lines.append("")
    lines.append(f"**Report ID:** {report.report_id}")
    lines.append(f"**Generated:** {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Praviar Version:** {report.praviar_pipeline_version}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("> **DISCLAIMER**")
    for line in report.disclaimer.split("\n"):
        lines.append(f"> {line}")
    lines.append("")


def render_executive_summary(lines: list[str], report: FTOReport) -> None:
    lines.append("## Executive Summary")
    lines.append("")
    overall = _risk_display(governed_risk_level(report))
    lines.append(f"**Clearance Decision: {governed_decision_label(report)}**")
    lines.append("")
    lines.append(f"**Overall Risk Level: {overall}**")
    lines.append("")
    lines.append(governed_executive_summary(report))
    lines.append("")

    lines.append("## Compound Profile")
    lines.append("")
    c = report.compound
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append(f"| **Name** | {c.name} |")
    lines.append(f"| **SMILES** | `{c.canonical_smiles}` |")
    lines.append(f"| **InChIKey** | `{c.inchi_key}` |")
    lines.append(f"| **Molecular Formula** | {c.molecular_formula} |")
    lines.append(f"| **Molecular Weight** | {c.molecular_weight} |")
    if c.cas_numbers:
        lines.append(f"| **CAS Number(s)** | {', '.join(c.cas_numbers)} |")
    if c.functional_groups:
        lines.append(f"| **Functional Groups** | {', '.join(c.functional_groups)} |")
    lines.append("")

    lines.append("## Search Coverage & Methodology")
    lines.append("")
    lines.append(f"**Total patents discovered:** {report.total_patents_found}")
    lines.append(f"**Patents after triage:** {report.patents_after_triage}")
    lines.append(f"**Patents analyzed:** {len(report.patent_analyses)}")
    scope = summarize_evidence_scope(report)
    lines.append(f"**Source status:** {scope.headline}")
    lines.append(f"**Reader scope note:** {scope.review_note}")
    if report.source_health.entries:
        configured_sources = ", ".join(entry.source for entry in report.source_health.entries)
        lines.append(f"**Configured source requests:** {configured_sources}")
    else:
        sources = ", ".join(report.search_sources_used) or "Not recorded"
        lines.append(f"**Recorded source names:** {sources}")
    lines.append("")

    if report.source_health.entries:
        lines.append("### Source Health")
        lines.append("")
        lines.append("| Source | Status | Patents Found | Detail |")
        lines.append("|--------|--------|---------------|--------|")
        for entry in report.source_health.entries:
            lines.append(
                f"| {entry.source} | {source_status_label(entry)} | "
                f"{entry.patent_count} | {source_status_detail(entry)} |"
            )
        lines.append("")


def render_pipeline_summary(lines: list[str], report: FTOReport) -> None:
    if not report.audit_trail.timing_data:
        return
    lines.append("## Pipeline Summary")
    lines.append("")
    lines.append("| Stage | Patents In | Patents Out | Duration |")
    lines.append("|-------|-----------|-------------|----------|")
    for step in report.audit_trail.timing_data:
        lines.append(
            f"| {step.step_name} | {step.items_processed} | "
            f"{step.items_output} | {step.duration_seconds:.1f}s |"
        )
    lines.append("")


def render_risk_matrix(lines: list[str], report: FTOReport) -> None:
    if not report.patent_analyses:
        return
    lines.append("## Risk Matrix")
    lines.append("")
    lines.append("| Patent | Assignee | Risk | Expiry | Key Claims | PTAB | Orange Book |")
    lines.append("|--------|----------|------|--------|------------|------|-------------|")

    details = report.patent_details or {}

    for a in sorted(report.patent_analyses, key=lambda x: risk_sort_key(x.risk_level)):
        risk = _risk_display(a.risk_level)
        expiry = a.expiry_date.isoformat() if a.expiry_date else "Unknown"
        claims = format_claim_numbers(a.claims_analyzed)
        ptab_str = format_ptab_status(details.get(a.patent_id, {}))
        ob_str = format_orange_book_status(details.get(a.patent_id, {}), a.orange_book_info)

        lines.append(
            f"| {a.patent_id} | {a.assignee} | {risk} | {expiry} | "
            f"{claims} | {ptab_str} | {ob_str} |"
        )
    lines.append("")
