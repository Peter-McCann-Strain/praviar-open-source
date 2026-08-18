"""Step 4.5: Portfolio-Level Critic Review — cross-validate all patent analyses."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.clients.claude import ClaudeClient
from praviar_pipeline.config import get_settings
from praviar_pipeline.models.critic import CriticReport
from praviar_pipeline.sanitize import sanitize_prompt_value, sanitize_untrusted_text

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.compound import ResolvedCompound

logger = structlog.get_logger()


def _format_portfolio_summary(analyses: list[PatentAnalysis]) -> str:
    """Format all analyses into a portfolio summary for the critic."""
    lines: list[str] = []
    # Group by assignee for cross-patent consistency checks
    by_assignee: dict[str, list[PatentAnalysis]] = {}
    for a in analyses:
        assignee = a.assignee or "Unknown"
        by_assignee.setdefault(assignee, []).append(a)

    for assignee, patents in sorted(by_assignee.items()):
        lines.append(f"\n## Assignee: {assignee} ({len(patents)} patents)\n")
        for a in patents:
            lines.append(f"### {a.patent_id}: {a.title}")
            lines.append(f"Risk: {a.risk_level.value.upper()}")
            lines.append(f"Expiry: {a.expiry_date}")
            lines.append(f"Risk Summary: {a.risk_summary}")
            for claim in a.claims_analyzed[:20]:
                statuses = ", ".join(
                    f"E{e.element_number}={e.status.value}" for e in claim.elements[:20]
                )
                lines.append(
                    f"  Claim {claim.claim_number} ({claim.claim_type}): "
                    f"{claim.overall_status.value} [{statuses}]"
                )
            if a.design_around_suggestions:
                lines.append("  Design-arounds:")
                for das in a.design_around_suggestions:
                    lines.append(f"    - E{das.element_avoided}: {das.suggestion}")
            lines.append("")

    return "\n".join(lines)


def _portfolio_needs_agentic_review(analyses: list[PatentAnalysis]) -> bool:
    """Return whether the portfolio critic should use agentic review."""
    if any(getattr(analysis, "analysis_escalated", False) for analysis in analyses):
        return True
    high_or_medium = sum(
        1 for analysis in analyses if analysis.risk_level.value in {"high", "medium"}
    )
    return high_or_medium >= 3 or len(analyses) >= 10


async def _review_compact_portfolio(
    claude: ClaudeClient,
    analyses: list[PatentAnalysis],
    compound: ResolvedCompound,
) -> tuple[CriticReport, int, int]:
    """Run a compact single-call portfolio review."""
    settings = get_settings()
    system_prompt = claude.load_prompt("critic_system.txt")
    portfolio_summary = _format_portfolio_summary(analyses)

    user_prompt = (
        f"Review the following portfolio of {len(analyses)} patent analyses "
        f"for the compound {sanitize_prompt_value(compound.name)} "
        f"({sanitize_prompt_value(compound.canonical_smiles, max_len=2000)}).\n\n"
        + sanitize_untrusted_text(
            portfolio_summary,
            data_type="prior_model_portfolio_analyses",
        )
        + "\n\n"
        "Identify issues, inconsistencies, and quality concerns. "
        "Rate the overall portfolio quality from 0.0 to 1.0."
    )

    report, usage = await claude.complete(
        system=system_prompt,
        user=user_prompt,
        response_model=CriticReport,
        model=settings.claude_analysis_model,
        max_tokens=settings.critic_max_tokens,
        effort=settings.thinking_effort_analysis,
        cache_system=True,
        role="critic",
    )

    report.patents_reviewed = len(analyses)
    report.input_tokens = usage.get("input_tokens", 0)
    report.output_tokens = usage.get("output_tokens", 0)

    return report, report.input_tokens, report.output_tokens


async def _review_agentic_portfolio(
    claude: ClaudeClient,
    analyses: list[PatentAnalysis],
    compound: ResolvedCompound,
) -> tuple[CriticReport, int, int]:
    """Run CriticAgent multi-turn portfolio review."""
    from praviar_pipeline.agents.critic import CriticAgent
    from praviar_pipeline.utils.formatting import format_compound_context

    portfolio_summary = _format_portfolio_summary(analyses)
    compound_ctx = format_compound_context(compound, include_inchi=True, include_weight=True)

    # Build patent data cache for toolkit
    patent_data: dict[str, dict] = {}
    for a in analyses:
        patent_data[a.patent_id] = {
            "title": a.title,
            "assignee": a.assignee,
            "risk_level": a.risk_level.value,
            "claims_count": len(a.claims_analyzed),
            "expiry_date": str(a.expiry_date) if a.expiry_date else None,
        }

    context = {
        "compound_context": compound_ctx,
        "portfolio_summary": portfolio_summary,
        "patent_data": patent_data,
    }

    agent = CriticAgent(claude)
    task = f"Critically review all {len(analyses)} supplied patent analyses for FTO assessment"

    findings_text, trace = await agent.research(task, context)

    # Extract structured report from agent output
    settings = get_settings()
    report, usage = await claude.complete(
        system=(
            "Extract the critic report from the review findings below. "
            "Output structured JSON matching the CriticReport schema."
        ),
        user=sanitize_untrusted_text(
            findings_text,
            max_len=30000,
            data_type="model_critic_findings",
        ),
        response_model=CriticReport,
        model=settings.claude_triage_model,
        max_tokens=settings.critic_max_tokens,
        effort=settings.thinking_effort_analysis,
        cache_system=True,
        role="critic",
    )

    report.patents_reviewed = len(analyses)
    total_in = trace.total_input_tokens + usage.get("input_tokens", 0)
    total_out = trace.total_output_tokens + usage.get("output_tokens", 0)
    report.input_tokens = total_in
    report.output_tokens = total_out

    return report, total_in, total_out


async def review_analyses(
    analyses: list[PatentAnalysis],
    compound: ResolvedCompound,
) -> tuple[CriticReport, int, int]:
    """Review all analyses for consistency, completeness, and quality.

    The unified adaptive path uses compact review for clear/simple portfolios
    and agentic review for high-risk, uncertain, or dense portfolios.

    Returns: (critic_report, input_tokens, output_tokens)
    """
    if not analyses:
        return CriticReport(patents_reviewed=0, overall_quality_score=1.0), 0, 0

    agentic_review = _portfolio_needs_agentic_review(analyses)
    logger.info(
        "critic_review_start",
        execution_profile="world_class_adaptive",
        agentic_review=agentic_review,
        patents=len(analyses),
    )

    async with ClaudeClient() as claude:
        if agentic_review:
            report, in_tok, out_tok = await _review_agentic_portfolio(claude, analyses, compound)
        else:
            report, in_tok, out_tok = await _review_compact_portfolio(claude, analyses, compound)

    logger.info(
        "critic_review_complete",
        execution_profile="world_class_adaptive",
        agentic_review=agentic_review,
        findings=len(report.findings),
        flagged=len(report.patents_flagged_for_revision),
        quality_score=report.overall_quality_score,
        critical_findings=sum(1 for f in report.findings if f.severity.value == "critical"),
        input_tokens=in_tok,
        output_tokens=out_tok,
    )

    return report, in_tok, out_tok
