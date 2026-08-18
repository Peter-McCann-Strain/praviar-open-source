"""Early pipeline-step helpers for the Praviar Pipeline runtime coordinator."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from praviar_pipeline.errors import SearchSourceFailedError
from praviar_pipeline.logging_config import StepTimer, bind_compound_context
from praviar_pipeline.pipeline.search.literature_sources import search_literature
from praviar_pipeline.pipeline.search_loop import run_search_loop
from praviar_pipeline.pipeline.step1_resolve import resolve_compound
from praviar_pipeline.pipeline.step1b_expand import expand_search_queries
from praviar_pipeline.pipeline.step2_search import search_patents
from praviar_pipeline.pipeline.step3_triage import triage_patents
from praviar_pipeline.pipeline.step4_analyze import analyze_patents_with_context
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from collections.abc import Callable


logger = structlog.get_logger()

_run_literature_search = search_literature


@dataclass(slots=True)
class SearchStepResult:
    patent_hits: list
    source_health: Any
    search_funnel: Any
    search_loop_result: Any
    literature_refs: list = field(default_factory=list)


@dataclass(slots=True)
class TriageStepResult:
    triage_results: list
    triage_input_tokens: int
    triage_output_tokens: int
    triage_failed: int
    all_triage: list


@dataclass(slots=True)
class AnalysisStepResult:
    analyses: list
    analysis_failures: list
    reasoning_traces: list
    prosecution_cache: dict


async def run_resolution_step(
    *,
    user_input: str,
    timing_data: list,
    notify: Callable[[int, str, str, dict], None],
    make_timing: Callable[[str, float, int, int], Any],
    resolve_compound_fn=resolve_compound,
    bind_compound_context_fn=bind_compound_context,
) -> Any:
    notify(1, "resolve", "started", {"description": "Resolving compound identity"})
    step_start = time.time()
    with StepTimer("step1_resolve", input=user_input):
        compound = await resolve_compound_fn(user_input)
    timing_data.append(make_timing("step1_resolve", step_start, 1, 1))
    bind_compound_context_fn(name=compound.name, cid=compound.pubchem_cid)
    logger.info(
        "step1_result",
        mw=compound.molecular_weight,
        synonyms=len(compound.synonyms or []),
    )
    notify(1, "resolve", "completed", {"compound_name": compound.name})
    return compound


async def run_query_expansion_step(
    *,
    compound,
    timing_data: list,
    notify: Callable[[int, str, str, dict], None],
    make_timing: Callable[[str, float, int, int], Any],
    expand_search_queries_fn=expand_search_queries,
) -> Any:
    notify(1, "expand", "started", {"description": "Expanding search queries"})
    step_start = time.time()
    with StepTimer("step1b_expand"):
        expanded_queries = await expand_search_queries_fn(compound)
    timing_data.append(make_timing("step1b_expand", step_start, 1, 1))
    logger.info(
        "step1b_result",
        process_keywords=len(expanded_queries.process_keywords),
    )
    notify(
        1,
        "expand",
        "completed",
        {
            "cpc_codes": len(expanded_queries.cpc_codes),
            "key_assignees": len(expanded_queries.key_assignees),
        },
    )
    return expanded_queries


async def run_search_step(
    *,
    compound,
    expanded_queries,
    settings,
    timing_data: list,
    notify: Callable[[int, str, str, dict], None],
    make_timing: Callable[[str, float, int, int], Any],
    run_search_loop_fn=run_search_loop,
    search_patents_fn=search_patents,
    search_literature_fn=_run_literature_search,
) -> SearchStepResult:
    """Run patent search and (concurrently) non-patent literature search.

    The literature branch (OpenAlex + Semantic Scholar) is a sibling to the
    patent search: its results do not feed the blocking-risk triage, they are
    threaded into step 6 invalidity analysis as §102/§103 prior-art candidates.
    """
    notify(2, "search", "started", {"description": "Searching patent databases"})
    step_start = time.time()
    logger.info(
        "step2_search_start",
        search_loop_enabled=settings.search_loop_enabled,
        hybrid_retrieval=getattr(settings, "hybrid_retrieval_enabled", False),
    )

    async def _patent_branch():
        # The search loop is now driven solely by its own flag. Deep-depth
        # runs are folded into ``search_loop_enabled`` during run bootstrap.
        if settings.search_loop_enabled:
            return await run_search_loop_fn(
                compound,
                expanded_queries,
                force_iterations=True,
            )
        hits, health, funnel = await search_patents_fn(
            compound,
            expanded_queries=expanded_queries,
        )
        return hits, health, funnel, [], 0, 0, 0, [], None

    async def _literature_branch():
        if not getattr(settings, "literature_search_enabled", False):
            return [], []
        failure_type: str | None = None
        try:
            return await search_literature_fn(
                compound,
                max_per_source=getattr(settings, "literature_max_per_source", 25),
            )
        except Exception as exc:
            failure_type = safe_exception_type(exc)
            logger.error(
                "literature_branch_failed",
                error_type=failure_type,
            )
        if failure_type is not None:
            raise SearchSourceFailedError(
                {"literature_branch": failure_type},
            ) from None
        raise AssertionError("literature branch reached an unreachable state")

    with StepTimer("step2_search"):
        patent_result, literature_result = await asyncio.gather(
            _patent_branch(),
            _literature_branch(),
        )

    (
        patent_hits,
        source_health,
        search_funnel,
        _loop_triage_results,
        _loop_triage_in,
        _loop_triage_out,
        _loop_triage_failed,
        _loop_all_triage,
        search_loop_result,
    ) = patent_result

    literature_refs, literature_health_entries = literature_result
    if literature_health_entries:
        source_health.entries.extend(literature_health_entries)

    timing_data.append(make_timing("step2_search", step_start, 0, len(patent_hits)))
    logger.info(
        "step2_result",
        hits=len(patent_hits),
        sources_ok=[entry.source for entry in source_health.entries if entry.status == "ok"],
        sources_failed=[entry.source for entry in source_health.entries if entry.status != "ok"],
        search_iterations=(search_loop_result.iterations_completed if search_loop_result else 0),
        literature_refs=len(literature_refs),
    )
    notify(
        2,
        "search",
        "completed",
        {
            "patents_found": len(patent_hits),
            "literature_refs": len(literature_refs),
        },
    )
    return SearchStepResult(
        patent_hits=patent_hits,
        source_health=source_health,
        search_funnel=search_funnel,
        search_loop_result=search_loop_result,
        literature_refs=literature_refs,
    )


async def run_triage_step(
    *,
    patent_hits: list,
    compound,
    drawing_evidence,
    timing_data: list,
    notify: Callable[[int, str, str, dict], None],
    make_timing: Callable[[str, float, int, int], Any],
    triage_patents_fn=triage_patents,
) -> TriageStepResult:
    notify(
        3,
        "triage",
        "started",
        {
            "description": "Triaging patents with AI",
            "total": len(patent_hits),
        },
    )
    step_start = time.time()
    with StepTimer("step3_triage", patents_in=len(patent_hits)):
        triage_results, triage_in, triage_out, triage_failed, all_triage = await triage_patents_fn(
            patent_hits,
            compound,
            drawing_evidence=drawing_evidence,
        )
    timing_data.append(
        make_timing("step3_triage", step_start, len(patent_hits), len(triage_results))
    )
    logger.info(
        "step3_result",
        relevant=len(triage_results),
        patents_failed=triage_failed,
        input_tokens=triage_in,
        output_tokens=triage_out,
    )
    notify(
        3,
        "triage",
        "completed",
        {"relevant": len(triage_results), "total": len(patent_hits)},
    )
    return TriageStepResult(
        triage_results=triage_results,
        triage_input_tokens=triage_in,
        triage_output_tokens=triage_out,
        triage_failed=triage_failed,
        all_triage=all_triage,
    )


async def run_analysis_step(
    *,
    relevant_patents: list,
    compound,
    triage_results: list,
    global_escalation_reasons: list[str],
    drawing_evidence,
    timing_data: list,
    notify: Callable[[int, str, str, dict], None],
    make_timing: Callable[[str, float, int, int], Any],
    analyze_patents_with_context_fn=analyze_patents_with_context,
) -> AnalysisStepResult:
    notify(
        4,
        "analyze",
        "started",
        {
            "description": "Deep claim analysis",
            "total": len(relevant_patents),
        },
    )
    step_start = time.time()
    with StepTimer("step4_analyze", patents_in=len(relevant_patents)):
        (
            analyses,
            analysis_failures,
            reasoning_traces,
            prosecution_cache,
        ) = await analyze_patents_with_context_fn(
            relevant_patents,
            compound,
            triage_results,
            drawing_evidence=drawing_evidence,
            global_escalation_reasons=global_escalation_reasons,
        )
    timing_data.append(
        make_timing("step4_analyze", step_start, len(relevant_patents), len(analyses))
    )
    logger.info(
        "step4_result",
        analyzed=len(analyses),
        failed=len(analysis_failures),
        total_input_tokens=sum(analysis.input_tokens for analysis in analyses),
        total_output_tokens=sum(analysis.output_tokens for analysis in analyses),
    )
    notify(
        4,
        "analyze",
        "completed",
        {"analyzed": len(analyses), "total": len(relevant_patents)},
    )
    return AnalysisStepResult(
        analyses=analyses,
        analysis_failures=analysis_failures,
        reasoning_traces=reasoning_traces,
        prosecution_cache=prosecution_cache,
    )
