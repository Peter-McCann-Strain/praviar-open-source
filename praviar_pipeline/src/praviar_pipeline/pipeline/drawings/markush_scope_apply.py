"""Post-pass: run MarkushScopeAgent on every Markush-flagged structure.

Called AFTER `prepare_structure_ocsr` / `finalize_structure_analysis` complete
so the verdict run has access to all the context the agent needs (target
SMILES, claim text, MG2-derived CXSMILES). Keeps `prepare_structure_ocsr`
simple — the agent call is a separate concern layered on top of the
drawing analysis.

Gated by `settings.drawing_markush_scope_agent_enabled`. When disabled, this
module is a no-op and safe to always invoke.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.agents.markush_scope import MarkushScopeAgent, MarkushScopeInput
from praviar_pipeline.pipeline.drawing_rollout import markush_scope_agent_can_run
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from praviar_pipeline.clients.claude import ClaudeClient
    from praviar_pipeline.config import Settings
    from praviar_pipeline.models.drawing import (
        DrawingAnalysisResults,
        PatentDrawingAnalysis,
    )

logger = structlog.get_logger()


async def apply_markush_scope_verdicts(
    results: DrawingAnalysisResults,
    *,
    target_smiles: str,
    claim_text_by_patent: dict[str, str],
    claude: ClaudeClient | None,
    settings: Settings,
    rgroup_definitions_by_patent: dict[str, dict[str, list[str]]] | None = None,
) -> int:
    """Fill in `markush_scope_verdict` on every Markush structure in `results`.

    Returns the number of verdicts produced. Runs serially per patent to keep
    Anthropic token costs predictable; per-patent tool-call budget is capped
    inside MarkushScopeAgent.

    No-op when:
      - `settings.drawing_markush_scope_agent_enabled` is False
      - `claude` is None (no LLM client plumbed through)
      - target_smiles is empty (no reference compound to compare against)
    """
    if not settings.drawing_markush_scope_agent_enabled:
        return 0
    if not markush_scope_agent_can_run(settings):
        raise RuntimeError(
            "Experimental Markush scope verdicts are shadow-only and cannot "
            "be attached to beta or production drawing evidence"
        )
    if claude is None:
        logger.debug("markush_scope_skipped_no_claude_client")
        return 0
    if not target_smiles:
        logger.debug("markush_scope_skipped_no_target")
        return 0

    # Resolve model here so the agent never has to call get_settings() —
    # that path requires anthropic_api_key to be set, which breaks tests
    # and any dry-run that uses a mocked ClaudeClient.
    agent_model_id = (
        getattr(settings, "drawing_markush_scope_agent_model", "")
        or getattr(settings, "claude_deep_model", "")
        or None
    )
    agent = MarkushScopeAgent(
        claude=claude,
        model_id=agent_model_id,
        max_turns=getattr(settings, "drawing_markush_scope_agent_max_turns", 8),
        max_output_tokens=getattr(settings, "drawing_markush_scope_agent_max_output_tokens", 6000),
    )

    rgroup_definitions_by_patent = rgroup_definitions_by_patent or {}

    produced = 0
    analyses: list[PatentDrawingAnalysis] = list(results.patent_analyses or [])
    for analysis in analyses:
        claim_text = claim_text_by_patent.get(analysis.patent_id, "")
        rgroups = rgroup_definitions_by_patent.get(analysis.patent_id, {})
        for structure in analysis.structures:
            if not structure.is_markush:
                continue
            if structure.markush_scope_verdict is not None:
                continue  # already decided (idempotent re-runs)
            scaffold = structure.markush_cxsmiles or structure.canonical_smiles
            if not scaffold:
                continue

            try:
                verdict = await agent.run(
                    MarkushScopeInput(
                        scaffold_cxsmiles=scaffold,
                        target_smiles=target_smiles,
                        claim_text=claim_text,
                        rgroup_definitions=rgroups,
                        patent_id=analysis.patent_id,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "markush_scope_agent_failed",
                    error_type=safe_exception_type(exc),
                )
                continue

            structure.markush_scope_verdict = verdict
            produced += 1

    logger.info(
        "markush_scope_apply_complete",
        total_patents=len(analyses),
        verdicts_produced=produced,
    )
    return produced
