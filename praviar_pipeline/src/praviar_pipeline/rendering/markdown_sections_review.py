"""Review section renderers for Markdown FTO reports."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.output_safety import safe_processing_error_detail

if TYPE_CHECKING:
    from praviar_pipeline.models.report import FTOReport


def render_action_items(lines: list[str], report: FTOReport) -> None:
    """Render recommended next steps — critical for actionable FTO reports."""
    if not report.action_items:
        return

    lines.append("## Recommended Actions")
    lines.append("")
    lines.append(
        "The following actions are recommended based on the analysis results, sorted by priority."
    )
    lines.append("")
    lines.append("| Priority | Action | Patents | Description | Timeline |")
    lines.append("|----------|--------|---------|-------------|----------|")
    for item in report.action_items:
        priority = item.priority.value.upper()
        action = item.action_type.value.replace("_", " ").title()
        patents = ", ".join(item.patent_ids[:5])
        if len(item.patent_ids) > 5:
            patents += f" (+{len(item.patent_ids) - 5} more)"
        desc = item.description[:120] + ("..." if len(item.description) > 120 else "")
        timeline = item.estimated_timeline or "-"
        lines.append(f"| **{priority}** | {action} | {patents} | {desc} | {timeline} |")
    lines.append("")


def render_data_limitations(lines: list[str], report: FTOReport) -> None:
    """Render known data gaps — transparency is critical for attorney reliance."""
    if not report.data_limitations and not report.analysis_failures:
        return

    lines.append("## Data Limitations & Coverage Gaps")
    lines.append("")

    if report.data_limitations:
        lines.append("### Known Limitations")
        lines.append("")
        for limitation in report.data_limitations:
            lines.append(
                f"- **{limitation.category}**: {limitation.description} "
                f"— *Impact: {limitation.impact}*"
            )
        lines.append("")

    if report.analysis_failures:
        lines.append("### Analysis Failures")
        lines.append("")
        lines.append(
            "The following patents could not be fully analyzed. These should be reviewed manually."
        )
        lines.append("")
        lines.append("| Patent | Step | Error |")
        lines.append("|--------|------|-------|")
        for failure in report.analysis_failures:
            err = safe_processing_error_detail(failure.error_message)
            lines.append(f"| {failure.patent_id} | {failure.step} | {err} |")
        lines.append("")


def render_verification(lines: list[str], report: FTOReport) -> None:
    lines.append("## Verification Results")
    lines.append("")
    lines.append(f"**All checks passed:** {'Yes' if report.verification.all_passed else 'No'}")
    lines.append("")
    if report.verification.checks:
        lines.append("| Check | Passed | Details |")
        lines.append("|-------|--------|---------|")
        for check in report.verification.checks:
            status = "PASS" if check.passed else "FAIL"
            details_short = check.details[:80] + ("..." if len(check.details) > 80 else "")
            lines.append(f"| {check.check_name} | {status} | {details_short} |")
        lines.append("")


def render_appendices(lines: list[str], report: FTOReport) -> None:
    lines.append("## Appendices")
    lines.append("")

    if report.audit_trail.search_funnel:
        lines.append("### Appendix A: Patent Disposition Summary")
        lines.append("")
        included = sum(1 for s in report.audit_trail.search_funnel if s.included_in_triage)
        excluded = len(report.audit_trail.search_funnel) - included
        lines.append(f"Total patents tracked: {len(report.audit_trail.search_funnel)}")
        lines.append(f"Included in triage: {included}")
        lines.append(f"Excluded by filters: {excluded}")
        lines.append("")

    lines.append("### Appendix B: Search Parameters")
    lines.append("")
    lines.append(f"- Compound: {report.compound.name}")
    lines.append(f"- SMILES: `{report.compound.canonical_smiles}`")
    lines.append(f"- Sources: {', '.join(report.search_sources_used)}")
    lines.append("")

    if report.llm_models_used:
        lines.append("### Appendix C: LLM Model Versions")
        lines.append("")
        for role, model in report.llm_models_used.items():
            lines.append(f"- **{role}:** {model}")
        lines.append("")

    details = report.patent_details or {}
    patents_with_term = [
        (pid, d)
        for pid, d in details.items()
        if d.get("patent_term_info") and d["patent_term_info"].get("adjusted_expiry")
    ]
    if patents_with_term:
        lines.append("### Appendix D: Patent Term Calculations")
        lines.append("")
        lines.append(
            "| Patent | Filing | Grant | PTA | PTE | TD | Maintenance | Expiry | Confidence |"
        )
        lines.append(
            "|--------|--------|-------|-----|-----|----|-------------|--------|------------|"
        )
        for pid, d in patents_with_term:
            ti = d["patent_term_info"]
            filing = ti.get("effective_filing_date", "-")
            grant = ti.get("grant_date", "-")
            pta = f"{ti.get('pta_days', 0)}d" if ti.get("pta_days", 0) > 0 else "-"
            pte = f"{ti.get('pte_days', 0)}d" if ti.get("pte_days", 0) > 0 else "-"
            td = "Yes" if ti.get("terminal_disclaimer") else "-"
            mf = ti.get("maintenance_fee_status", "unknown")
            expiry = ti.get("adjusted_expiry", "-")
            conf = f"{ti.get('calculation_confidence', 0):.0%}"
            lines.append(
                f"| {pid} | {filing} | {grant} | {pta} | {pte} | {td} | {mf} | {expiry} | {conf} |"
            )
        lines.append("")

    if report.invalidity_assessments:
        all_prior_art = []
        for inv in report.invalidity_assessments:
            if inv.prior_art:
                for ref in inv.prior_art:
                    all_prior_art.append((inv.patent_id, ref))
        if all_prior_art:
            lines.append("### Appendix E: Prior Art References")
            lines.append("")
            lines.append("| Against Patent | Reference | Title | Date | Type |")
            lines.append("|---------------|-----------|-------|------|------|")
            for pat_id, ref in all_prior_art[:50]:
                ref_id = getattr(ref, "reference_id", getattr(ref, "id", str(ref)))
                title = getattr(ref, "title", "")[:60]
                pub_date = getattr(ref, "publication_date", "-")
                ref_type = getattr(ref, "reference_type", "unknown")
                lines.append(f"| {pat_id} | {ref_id} | {title} | {pub_date} | {ref_type} |")
            lines.append("")

    lines.append("### Appendix F: Methodology")
    lines.append("")
    lines.append(report.disclaimer)
    lines.append("")
