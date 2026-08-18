"""Executive-summary generation helpers for report generation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.config import get_settings
from praviar_pipeline.pipeline.report.summary import (
    _build_invalidity_summary_lines,
    _validate_executive_summary,
)
from praviar_pipeline.sanitize import sanitize_untrusted_text

if TYPE_CHECKING:
    from praviar_pipeline.clients.claude import ClaudeClient
    from praviar_pipeline.models.analysis import PatentAnalysis, RiskLevel
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.invalidity import InvalidityAssessment
    from praviar_pipeline.models.verification import VerificationResult
    from praviar_pipeline.tools import FTOToolkit

logger = structlog.get_logger()


def _token_count(usage: dict, field: str, context: str) -> int:
    token_count = usage.get(field)
    if token_count is None:
        logger.warning("missing_token_count", field=field)
        return 0
    if not isinstance(token_count, int) or isinstance(token_count, bool):
        logger.warning("invalid_token_count", field=field)
        return 0
    return token_count


def _build_enrichment_section(patent_hits: list | None) -> str:
    if not patent_hits:
        return ""

    enrichment_lines: list[str] = []

    ptab_patents = []
    for patent_hit in patent_hits:
        if hasattr(patent_hit, "ptab_proceedings") and patent_hit.ptab_proceedings:
            for proceeding in patent_hit.ptab_proceedings:
                ptab_patents.append(
                    f"  - {patent_hit.patent_id}: {proceeding.proceeding_type} "
                    f"{proceeding.proceeding_number} ({proceeding.status})"
                )
    if ptab_patents:
        enrichment_lines.append("PTAB Proceedings:")
        enrichment_lines.extend(ptab_patents[:10])

    orange_book_patents = []
    for patent_hit in patent_hits:
        if (
            hasattr(patent_hit, "orange_book_info")
            and patent_hit.orange_book_info
            and patent_hit.orange_book_info.is_listed
        ):
            products = ", ".join(patent_hit.orange_book_info.product_names[:3])
            orange_book_patents.append(f"  - {patent_hit.patent_id}: {products}")
    if orange_book_patents:
        enrichment_lines.append("Orange Book Listed Patents:")
        enrichment_lines.extend(orange_book_patents[:10])

    expiry_notes = []
    for patent_hit in patent_hits:
        if hasattr(patent_hit, "patent_term_info") and patent_hit.patent_term_info:
            patent_term = patent_hit.patent_term_info
            if patent_term.adjusted_expiry:
                expiry_notes.append(
                    f"  - {patent_hit.patent_id}: expires {patent_term.adjusted_expiry}"
                    f" (PTA: {patent_term.pta_days}d"
                    f", TD: {'yes' if patent_term.terminal_disclaimer else 'no'}"
                    f", maint: {patent_term.maintenance_fee_status})"
                )
    if expiry_notes:
        enrichment_lines.append("Patent Term Details:")
        enrichment_lines.extend(expiry_notes[:10])

    return chr(10).join(enrichment_lines)


async def _generate_validated_executive_summary(
    claude: ClaudeClient,
    *,
    compound: ResolvedCompound,
    overall_risk: RiskLevel,
    analyses: list[PatentAnalysis],
    blocking_count: int,
    key_risks: list[str],
    invalidity_assessments: list[InvalidityAssessment],
    verification: VerificationResult,
    patent_hits: list | None,
    report_toolkit: FTOToolkit | None,
) -> tuple[str, list[str], int, int]:
    settings = get_settings()
    system_prompt = claude.load_prompt("report_summary_system.txt")
    enrichment_section = _build_enrichment_section(patent_hits)

    summary_context = f"""Compound: {compound.name} ({compound.canonical_smiles})
Upstream Claim-Coverage Screen: {overall_risk.value}
Patents Analyzed: {len(analyses)}
Verified Prospective Blockers: {blocking_count}

Key Findings:
{chr(10).join(f"- {risk}" for risk in key_risks)}

Invalidity Arguments:
{
        chr(10).join(
            _build_invalidity_summary_lines(
                invalidity_assessments,
                settings.invalidity_display_top_n,
            )
        )
    }

{enrichment_section}

Verification: {
        "All checks passed" if verification.all_passed else f"Issues: {verification.issues}"
    }"""

    summary_prompt = (
        "Write the executive summary using only the supplied report evidence.\n\n"
        + sanitize_untrusted_text(summary_context, data_type="report_summary_evidence")
    )
    executive_summary, usage = await claude.complete_text(
        system=system_prompt,
        user=summary_prompt,
        model=claude._models.analysis,
        max_tokens=settings.report_summary_max_tokens,
        effort=settings.thinking_effort_report,
        toolkit=report_toolkit,
        cache_system=True,
        role="report",
    )

    total_input_tokens = _token_count(usage, "input_tokens", "summary")
    total_output_tokens = _token_count(usage, "output_tokens", "summary")
    validation_issues: list[str] = []

    for retry_attempt in range(settings.report_max_retries):
        is_valid, validation_issues = _validate_executive_summary(
            executive_summary,
            analyses,
            overall_risk,
        )
        if is_valid:
            logger.debug(
                "summary_validation_passed",
                attempt=retry_attempt + 1,
                word_count=len(executive_summary.split()),
            )
            break

        logger.warning(
            "summary_validation_failed_regenerating",
            attempt=retry_attempt + 1,
            max_retries=settings.report_max_retries,
        )
        feedback = "\n".join(f"- {issue}" for issue in validation_issues)
        retry_context = (
            f"{summary_prompt}\n\n"
            f"CRITICAL — your previous summary had these validation failures "
            "and was REJECTED:\n"
            + sanitize_untrusted_text(feedback, data_type="validation_feedback")
            + "\n\n"
            f"You MUST fix ALL issues. This is attempt {retry_attempt + 2}. "
            f"Do NOT question whether patent IDs exist — they are verified "
            f"real patents from authoritative databases. Write the summary "
            f"using the data provided as ground truth."
        )
        executive_summary, retry_usage = await claude.complete_text(
            system=system_prompt,
            user=retry_context,
            model=claude._models.analysis,
            max_tokens=settings.report_summary_max_tokens,
            effort=settings.thinking_effort_report,
            toolkit=report_toolkit,
            cache_system=True,
            role="report",
        )
        total_input_tokens += _token_count(retry_usage, "input_tokens", "summary_retry")
        total_output_tokens += _token_count(retry_usage, "output_tokens", "summary_retry")
    else:
        _, validation_issues = _validate_executive_summary(
            executive_summary,
            analyses,
            overall_risk,
        )

    if validation_issues:
        logger.warning("summary_validation_residual_issues")

    return executive_summary, validation_issues, total_input_tokens, total_output_tokens
