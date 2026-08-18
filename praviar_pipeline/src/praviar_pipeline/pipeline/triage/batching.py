"""LLM batch orchestration helpers for Step 3 triage."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.models.triage import Relevance, TriageBatch, TriageResult
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from praviar_pipeline.clients.claude import ClaudeClient
    from praviar_pipeline.config import Settings
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.drawing import DrawingEvidenceStore
    from praviar_pipeline.models.patent import PatentHit

logger = structlog.get_logger()


@dataclass(slots=True)
class LlmTriageRunResult:
    filtered: list[TriageResult]
    all_results: list[TriageResult]
    total_input: int
    total_output: int
    failed_patent_count: int
    batch_count: int
    failed_batch_count: int


async def run_llm_triage_batches(
    claude: ClaudeClient,
    llm_patents: list[PatentHit],
    known_patent_ids: set[str],
    compound: ResolvedCompound,
    system_prompt: str,
    settings: Settings,
    *,
    auto_results: list[TriageResult],
    drawing_evidence: DrawingEvidenceStore | None,
    triage_batch_fn: Callable[..., Awaitable[TriageBatch]],
) -> LlmTriageRunResult:
    """Run Claude triage over patent batches and merge the results with auto-triage."""
    batch_size = settings.triage_batch_size
    batches = [llm_patents[i : i + batch_size] for i in range(0, len(llm_patents), batch_size)]

    semaphore = asyncio.Semaphore(settings.triage_concurrency)

    async def _limited_triage(batch: list[PatentHit]) -> TriageBatch:
        async with semaphore:
            return await triage_batch_fn(
                claude,
                batch,
                compound,
                system_prompt,
                settings.triage_max_tokens,
                drawing_evidence=drawing_evidence,
            )

    batch_results = await asyncio.gather(
        *[_limited_triage(batch) for batch in batches],
        return_exceptions=True,
    )

    llm_results: list[TriageResult] = []
    total_input = 0
    total_output = 0
    failed_batch_count = 0

    for index, batch_result in enumerate(batch_results):
        if isinstance(batch_result, BaseException):
            batch_patent_count = len(batches[index])
            failed_batch_count += 1
            logger.error(
                "triage_batch_failed",
                error_type=safe_exception_type(batch_result),
                batch_index=index,
                patents_lost=batch_patent_count,
            )
            continue

        llm_results.extend(batch_result.results)
        total_input += batch_result.input_tokens
        total_output += batch_result.output_tokens

    validated_by_id: dict[str, TriageResult] = {}
    duplicate_ids: set[str] = set()
    for result in llm_results:
        if result.patent_id in known_patent_ids:
            if result.patent_id in validated_by_id:
                duplicate_ids.add(result.patent_id)
            else:
                validated_by_id[result.patent_id] = result
            continue
        logger.warning(
            "triage_unknown_patent_id",
        )

    expected_llm_ids = [patent.patent_id for patent in llm_patents]
    for patent_id in duplicate_ids:
        validated_by_id.pop(patent_id, None)
        logger.warning("triage_duplicate_patent_result")

    missing_ids = [patent_id for patent_id in expected_llm_ids if patent_id not in validated_by_id]
    failed_patent_count = len(missing_ids)
    for patent_id in missing_ids:
        validated_by_id[patent_id] = TriageResult(
            patent_id=patent_id,
            relevance=Relevance.UNKNOWN,
            reason="Triage unavailable; mandatory downstream analysis required.",
            blocking_potential="Unknown until downstream analysis completes.",
            confidence=0.0,
        )

    validated_results = [validated_by_id[patent_id] for patent_id in expected_llm_ids]

    all_results = auto_results + validated_results
    filtered = [
        result
        for result in all_results
        if result.relevance in (Relevance.RELEVANT, Relevance.POSSIBLY_RELEVANT, Relevance.UNKNOWN)
    ]

    return LlmTriageRunResult(
        filtered=filtered,
        all_results=all_results,
        total_input=total_input,
        total_output=total_output,
        failed_patent_count=failed_patent_count,
        batch_count=len(batches),
        failed_batch_count=failed_batch_count,
    )
