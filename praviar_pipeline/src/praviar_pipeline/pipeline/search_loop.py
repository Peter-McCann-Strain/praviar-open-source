"""Agentic search loop -- wraps Steps 2 and 3 in an iterative refinement loop.

When search_loop_enabled=False: single iteration (current behaviour).
When search_loop_enabled=True: up to N iterations with coverage assessment
between iterations. Each iteration searches with refined queries, triages
only new patents, and assesses whether coverage is sufficient. Public analysis
depths no longer exist; adaptive runtime signals can fold search_loop_enabled
on during run bootstrap.

This module consolidates what was previously spread across six files:
  search_loop.py, search_loop_assessment.py, search_loop_context.py,
  search_loop_directives.py, search_loop_gap_plan.py, search_loop_state.py.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.config import get_settings
from praviar_pipeline.models.report import SourceHealth
from praviar_pipeline.models.report_common import SourceStatus
from praviar_pipeline.models.report_evidence import (
    EvidenceCollectionDirective,
    EvidenceDirectivePriority,
)
from praviar_pipeline.models.search import (
    ExpandedSearchQueries,
    QueryExpansionProvenance,
)
from praviar_pipeline.models.search_loop import (
    CoverageAssessment,
    CoverageGap,
    SearchIterationLog,
    SearchLoopResult,
)
from praviar_pipeline.models.triage import Relevance
from praviar_pipeline.pipeline.runtime.evidence_policy import resolve_required_record_components
from praviar_pipeline.pipeline.runtime.live_collectors import execute_live_evidence_collectors
from praviar_pipeline.pipeline.search.loop_helpers import (
    compute_search_stats,
    compute_triage_stats,
    merge_queries,
)
from praviar_pipeline.pipeline.step2_search import search_patents
from praviar_pipeline.pipeline.step3_triage import triage_patents
from praviar_pipeline.sanitize import sanitize_untrusted_text
from praviar_pipeline.utils.formatting import format_compound_context
from praviar_pipeline.utils.patent_ids import normalize_patent_id
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from collections.abc import Callable

    from praviar_pipeline.models.audit import SearchFunnelEntry
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.patent import PatentHit
    from praviar_pipeline.models.triage import TriageResult

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# search_loop_gap_plan -- deterministic gap-planning helpers
# ---------------------------------------------------------------------------

_AUTHORITATIVE_SEARCH_SOURCES = frozenset({"patentsview", "epo_search"})


@dataclass(slots=True)
class SearchGapPlan:
    """Policy-aware record gaps known at search-loop time."""

    required_components: list[str]
    known_record_gaps: list[str]
    scoped_hits: list[PatentHit] = field(default_factory=list)
    patents_missing_claims: list[str] = field(default_factory=list)
    patents_missing_family_context: list[str] = field(default_factory=list)
    patents_missing_authoritative_records: list[str] = field(default_factory=list)
    failed_authoritative_sources: list[str] = field(default_factory=list)
    us_patents_missing_prosecution_context: list[str] = field(default_factory=list)
    us_patents_missing_file_wrapper_dossier: list[str] = field(default_factory=list)
    ep_patents_missing_register_context: list[str] = field(default_factory=list)
    us_patents_missing_ptab_record: list[str] = field(default_factory=list)
    us_patents_missing_orange_book_record: list[str] = field(default_factory=list)


def unique_strings(values: list[str]) -> list[str]:
    """Return stable unique non-empty strings."""
    return list(dict.fromkeys(value for value in values if value))


def material_hits(
    patent_hits: list[PatentHit],
    all_triage: list[TriageResult],
) -> list[PatentHit]:
    """Scope record-gap planning to material patents when triage data exists."""
    material_ids = {
        triage.patent_id
        for triage in all_triage
        if triage.relevance in (Relevance.RELEVANT, Relevance.POSSIBLY_RELEVANT)
    }
    scoped_hits = [hit for hit in patent_hits if hit.patent_id in material_ids]
    return scoped_hits or list(patent_hits)


def build_search_gap_plan(
    patent_hits: list[PatentHit],
    all_triage: list[TriageResult],
    source_health: SourceHealth,
    *,
    settings,
) -> SearchGapPlan:
    """Build a typed policy-aware gap snapshot for the current search iteration."""
    scoped_hits = material_hits(patent_hits, all_triage)

    us_patents = [
        hit for hit in scoped_hits if (hit.jurisdiction or hit.patent_id[:2]).upper() == "US"
    ]
    ep_patents = [
        hit for hit in scoped_hits if (hit.jurisdiction or hit.patent_id[:2]).upper() == "EP"
    ]
    required_components = resolve_required_record_components(
        settings,
        SimpleNamespace(us_patents=len(us_patents), ep_patents=len(ep_patents)),
    )

    if not scoped_hits:
        return SearchGapPlan(
            required_components=required_components,
            known_record_gaps=[
                "No material patents have been retained yet; continue broadening "
                "search before treating coverage as adequate."
            ],
            scoped_hits=[],
        )

    missing_claims_patent_ids = [
        hit.patent_id for hit in scoped_hits if not (hit.claims_text or "").strip()
    ]
    missing_family_patent_ids = [
        hit.patent_id for hit in scoped_hits if getattr(hit, "family", None) is None
    ]
    missing_authoritative_patent_ids = [
        hit.patent_id
        for hit in scoped_hits
        if not any(source.value in _AUTHORITATIVE_SEARCH_SOURCES for source in hit.sources)
    ]
    failed_authoritative_sources = sorted(
        entry.source
        for entry in source_health.entries
        if entry.source in _AUTHORITATIVE_SEARCH_SOURCES and entry.status == SourceStatus.FAILED
    )
    missing_us_prosecution_ids = [
        hit.patent_id for hit in us_patents if not hit.application_number or not hit.transactions
    ]
    missing_us_dossier_ids = [hit.patent_id for hit in us_patents if not hit.transactions]
    missing_ep_register_ids = [
        hit.patent_id
        for hit in ep_patents
        if not (
            hit.designated_states
            or hit.priority_claims
            or hit.opposition_events
            or hit.legal_events
        )
    ]
    missing_ptab_ids = [hit.patent_id for hit in us_patents if not hit.ptab_proceedings]
    missing_orange_book_ids = [
        hit.patent_id for hit in us_patents if not (hit.orange_book_listed or hit.orange_book_info)
    ]

    total_material = len(scoped_hits)
    gaps: list[str] = []
    if "claims_text" in required_components and missing_claims_patent_ids:
        gaps.append(
            f"{len(missing_claims_patent_ids)}/{total_material} material patents "
            "are missing full claims text."
        )
    if "family_context" in required_components and missing_family_patent_ids:
        gaps.append(
            f"{len(missing_family_patent_ids)}/{total_material} material patents "
            "are missing patent-family context."
        )
    if "authoritative_records" in required_components:
        if missing_authoritative_patent_ids:
            gaps.append(
                f"{len(missing_authoritative_patent_ids)}/{total_material} "
                "material patents lack authoritative-source support from "
                "PatentsView or EPO search."
            )
        if failed_authoritative_sources:
            gaps.append(
                "Authoritative sources failed this iteration: "
                + ", ".join(failed_authoritative_sources)
                + "."
            )
    if "us_prosecution_context" in required_components and missing_us_prosecution_ids:
        gaps.append(
            f"{len(missing_us_prosecution_ids)}/{len(us_patents)} material US "
            "patents are missing application or prosecution context."
        )
    if "us_file_wrapper_dossier" in required_components and missing_us_dossier_ids:
        gaps.append(
            f"{len(missing_us_dossier_ids)}/{len(us_patents)} material US patents "
            "are missing dossier-grade file-wrapper history."
        )
    if "ep_register_context" in required_components and missing_ep_register_ids:
        gaps.append(
            f"{len(missing_ep_register_ids)}/{len(ep_patents)} material EP "
            "patents are missing EPO register or opposition context."
        )
    if "ptab_record" in required_components and missing_ptab_ids:
        gaps.append(
            f"{len(missing_ptab_ids)}/{len(us_patents)} material US patents "
            "are missing PTAB posture."
        )
    if "orange_book_record" in required_components and missing_orange_book_ids:
        gaps.append(
            f"{len(missing_orange_book_ids)}/{len(us_patents)} material US "
            "patents are missing Orange Book context."
        )

    return SearchGapPlan(
        required_components=required_components,
        known_record_gaps=unique_strings(gaps),
        scoped_hits=scoped_hits,
        patents_missing_claims=missing_claims_patent_ids,
        patents_missing_family_context=missing_family_patent_ids,
        patents_missing_authoritative_records=missing_authoritative_patent_ids,
        failed_authoritative_sources=failed_authoritative_sources,
        us_patents_missing_prosecution_context=missing_us_prosecution_ids,
        us_patents_missing_file_wrapper_dossier=missing_us_dossier_ids,
        ep_patents_missing_register_context=missing_ep_register_ids,
        us_patents_missing_ptab_record=missing_ptab_ids,
        us_patents_missing_orange_book_record=missing_orange_book_ids,
    )


def derive_known_record_gaps(
    patent_hits: list[PatentHit],
    all_triage: list[TriageResult],
    source_health: SourceHealth,
    *,
    settings,
) -> tuple[list[str], list[str]]:
    """Derive policy-aware evidence gaps for the search-loop coverage agent."""
    plan = build_search_gap_plan(
        patent_hits,
        all_triage,
        source_health,
        settings=settings,
    )
    return plan.required_components, plan.known_record_gaps


def apply_record_gap_guard(
    assessment: CoverageAssessment,
    known_record_gaps: list[str],
) -> CoverageAssessment:
    """Prevent the search loop from declaring adequacy while record gaps remain."""
    if not known_record_gaps:
        return assessment

    existing_descriptions = {gap.description for gap in assessment.gaps_identified}
    for gap_text in known_record_gaps:
        if gap_text in existing_descriptions:
            continue
        assessment.gaps_identified.append(
            CoverageGap(
                gap_type="record_gap",
                description=gap_text,
                suggested_action=(
                    "Expand search or authoritative record collection until this gap is closed."
                ),
            )
        )

    assessment.coverage_adequate = False
    return assessment


# ---------------------------------------------------------------------------
# search_loop_directives -- directive and fallback-query helpers
# ---------------------------------------------------------------------------

_SEARCHABLE_DIRECTIVE_TYPES = frozenset(
    {
        "collect_claims_text",
        "collect_authoritative_records",
        "expand_family_context",
        "retry_authoritative_adapters",
    }
)


def _directive(
    *,
    directive_type: str,
    priority: EvidenceDirectivePriority,
    required_before_clear: bool,
    target_patent_ids: list[str],
    recommended_adapters: list[str],
    summary: str,
    rationale: str,
) -> EvidenceCollectionDirective:
    patent_ids = unique_strings(target_patent_ids)
    return EvidenceCollectionDirective(
        directive_id=":".join([directive_type, ",".join(patent_ids)]),
        directive_type=directive_type,
        priority=priority,
        required_before_clear=required_before_clear,
        target_patent_ids=patent_ids,
        target_claim_ids=[],
        target_jurisdictions=unique_strings(
            [patent_id[:2].upper() for patent_id in patent_ids if len(patent_id) >= 2]
        ),
        recommended_adapters=unique_strings(recommended_adapters),
        summary=summary,
        rationale=rationale,
    )


def build_search_collection_directives(
    gap_plan: SearchGapPlan,
) -> list[EvidenceCollectionDirective]:
    """Convert deterministic search-loop record gaps into typed directives."""
    directives: list[EvidenceCollectionDirective] = []

    if "claims_text" in gap_plan.required_components and gap_plan.patents_missing_claims:
        directives.append(
            _directive(
                directive_type="collect_claims_text",
                priority=EvidenceDirectivePriority.HIGH,
                required_before_clear=True,
                target_patent_ids=gap_plan.patents_missing_claims,
                recommended_adapters=["patentsview", "bigquery", "epo_search"],
                summary=(
                    "Collect full claims text for material patents still missing claims coverage."
                ),
                rationale=(
                    "Positive clearance is not defensible while claims text remains incomplete."
                ),
            )
        )
    if (
        "authoritative_records" in gap_plan.required_components
        and gap_plan.patents_missing_authoritative_records
    ):
        directives.append(
            _directive(
                directive_type="collect_authoritative_records",
                priority=EvidenceDirectivePriority.CRITICAL,
                required_before_clear=True,
                target_patent_ids=gap_plan.patents_missing_authoritative_records,
                recommended_adapters=["patentsview", "epo_search", "uspto_odp", "epo_register"],
                summary=(
                    "Collect authoritative legal-record support for material "
                    "patents still backed only by discovery sources."
                ),
                rationale=(
                    "Official or equivalent authoritative record support is "
                    "required before the search can be treated as "
                    "clearance-grade."
                ),
            )
        )
    if "family_context" in gap_plan.required_components and gap_plan.patents_missing_family_context:
        directives.append(
            _directive(
                directive_type="expand_family_context",
                priority=EvidenceDirectivePriority.HIGH,
                required_before_clear=True,
                target_patent_ids=gap_plan.patents_missing_family_context,
                recommended_adapters=["family_record", "epo_register"],
                summary="Expand family coverage for material patents still missing family context.",
                rationale="Continuation and family scope can materially alter FTO posture.",
            )
        )
    if (
        "us_prosecution_context" in gap_plan.required_components
        and gap_plan.us_patents_missing_prosecution_context
    ):
        directives.append(
            _directive(
                directive_type="collect_us_prosecution_context",
                priority=EvidenceDirectivePriority.HIGH,
                required_before_clear=True,
                target_patent_ids=gap_plan.us_patents_missing_prosecution_context,
                recommended_adapters=["uspto_odp"],
                summary=(
                    "Collect U.S. prosecution context for material patents "
                    "missing application or transaction history."
                ),
                rationale="A clearance-grade U.S. record requires prosecution context.",
            )
        )
    if (
        "us_file_wrapper_dossier" in gap_plan.required_components
        and gap_plan.us_patents_missing_file_wrapper_dossier
    ):
        directives.append(
            _directive(
                directive_type="collect_us_file_wrapper_dossier",
                priority=EvidenceDirectivePriority.CRITICAL,
                required_before_clear=True,
                target_patent_ids=gap_plan.us_patents_missing_file_wrapper_dossier,
                recommended_adapters=["uspto_odp"],
                summary=(
                    "Collect dossier-grade U.S. file-wrapper history for "
                    "material patents still missing it."
                ),
                rationale=(
                    "A positive U.S. clearance conclusion requires "
                    "dossier-grade prosecution coverage."
                ),
            )
        )
    if (
        "ep_register_context" in gap_plan.required_components
        and gap_plan.ep_patents_missing_register_context
    ):
        directives.append(
            _directive(
                directive_type="collect_ep_register_context",
                priority=EvidenceDirectivePriority.CRITICAL,
                required_before_clear=True,
                target_patent_ids=gap_plan.ep_patents_missing_register_context,
                recommended_adapters=["epo_register"],
                summary=(
                    "Collect EP register and opposition context for material "
                    "EP patents still missing register coverage."
                ),
                rationale=(
                    "A positive EP clearance conclusion requires "
                    "register-grade status and opposition context."
                ),
            )
        )
    if gap_plan.failed_authoritative_sources:
        directives.append(
            _directive(
                directive_type="retry_authoritative_adapters",
                priority=EvidenceDirectivePriority.HIGH,
                required_before_clear=True,
                target_patent_ids=[hit.patent_id for hit in gap_plan.scoped_hits],
                recommended_adapters=gap_plan.failed_authoritative_sources,
                summary=(
                    "Retry failed authoritative search or record adapters "
                    "before treating coverage as adequate."
                ),
                rationale=(
                    "Failed official-source collection leaves blind spots in the matter record."
                ),
            )
        )

    deduped: dict[str, EvidenceCollectionDirective] = {}
    for directive in directives:
        deduped.setdefault(directive.directive_id, directive)
    return list(deduped.values())


def synthesize_search_queries_from_directives(
    directives: list[EvidenceCollectionDirective],
    patent_hits: list[PatentHit],
    accumulated_queries: ExpandedSearchQueries,
) -> ExpandedSearchQueries | None:
    """Derive deterministic follow-up assignee/CPC queries from unresolved directives."""
    searchable = [
        directive
        for directive in directives
        if directive.directive_type in _SEARCHABLE_DIRECTIVE_TYPES
    ]
    if not searchable:
        return None

    target_patent_ids = {
        patent_id for directive in searchable for patent_id in directive.target_patent_ids
    }
    target_hits = [hit for hit in patent_hits if hit.patent_id in target_patent_ids] or list(
        patent_hits
    )
    if not target_hits:
        return None

    existing_assignees = {
        assignee.strip().lower() for assignee in accumulated_queries.key_assignees
    }
    existing_cpcs = set(accumulated_queries.cpc_codes)

    assignee_counts: Counter[str] = Counter()
    cpc_counts: Counter[str] = Counter()
    for hit in target_hits:
        assignee_counts.update(assignee for assignee in hit.assignees if assignee)
        cpc_counts.update(code for code in hit.cpc_codes if code)

    new_assignees = [
        assignee
        for assignee, _ in assignee_counts.most_common(8)
        if assignee.strip().lower() not in existing_assignees
    ]
    new_cpcs = [code for code, _ in cpc_counts.most_common(10) if code not in existing_cpcs]

    if not new_assignees and not new_cpcs:
        return None

    return ExpandedSearchQueries(
        patent_synonyms=[],
        cpc_codes=new_cpcs[:8],
        key_assignees=new_assignees[:6],
        process_keywords=[],
        compound_class_terms=[],
        provenance=QueryExpansionProvenance(
            origin="evidence_directive",
            grounded=True,
        ),
    )


# ---------------------------------------------------------------------------
# search_loop_context -- context building, iteration logs, and final results
# ---------------------------------------------------------------------------


def format_source_health_text(source_health: SourceHealth) -> str:
    """Render source health entries for coverage assessment prompts."""
    return "\n".join(
        f"  {e.source}: {e.status} ({e.patent_count} patents)"
        + (f" ERROR: {e.error_message}" if e.error_message else "")
        for e in source_health.entries
    )


def format_queries_used_text(queries_used: ExpandedSearchQueries) -> str:
    """Render the active query set for coverage assessment prompts."""
    return (
        f"Synonyms: {', '.join(queries_used.patent_synonyms[:10])}\n"
        f"CPC codes: {', '.join(queries_used.cpc_codes[:10])}\n"
        f"Assignees: {', '.join(queries_used.key_assignees[:10])}\n"
        f"Process keywords: {', '.join(queries_used.process_keywords[:10])}\n"
        f"Class terms: {', '.join(queries_used.compound_class_terms[:10])}"
    )


def format_clearance_policy_text(clearance_policy: dict[str, object] | None) -> str:
    """Render the active clearance policy for coverage assessment prompts."""
    if not clearance_policy:
        return ""

    required_raw = clearance_policy.get("required_record_components") or []
    required = [str(x) for x in required_raw] if isinstance(required_raw, list) else []
    required_text = ", ".join(required) if required else "default policy"
    return (
        f"Matter type: {clearance_policy.get('matter_type', '')}\n"
        f"Jurisdiction policy: {clearance_policy.get('jurisdiction_policy', '')}\n"
        f"Threshold profile: {clearance_policy.get('clearance_threshold_profile', '')}\n"
        f"Source authority policy: {clearance_policy.get('source_authority_policy', '')}\n"
        f"Required record components: {required_text}"
    )


def format_collection_directives_text(
    directives: list[EvidenceCollectionDirective] | None,
) -> str:
    """Render typed evidence-collection directives for the coverage agent."""
    if not directives:
        return "  - none"

    lines: list[str] = []
    for directive in directives:
        targets = ", ".join(directive.target_patent_ids[:5]) or "matter-wide"
        adapters = ", ".join(directive.recommended_adapters[:5]) or "none"
        lines.append(
            f"  - [{directive.priority.value}] {directive.directive_type}: "
            f"{directive.summary} Targets: {targets}. Adapters: {adapters}."
        )
    return "\n".join(lines)


def _summary_value(summary, key: str, default):
    if summary is None:
        return default
    if isinstance(summary, dict):
        return summary.get(key, default)
    return getattr(summary, key, default)


def format_matter_graph_summary_text(summary) -> str:
    """Render a compact matter-graph summary for coverage assessment prompts."""
    if not summary:
        return ""

    node_counts = _summary_value(summary, "node_counts_by_type", {}) or {}
    edge_counts = _summary_value(summary, "edge_counts_by_type", {}) or {}
    top_nodes = (
        ", ".join(f"{node_type}={count}" for node_type, count in sorted(node_counts.items()))
        or "none"
    )
    top_edges = (
        ", ".join(f"{edge_type}={count}" for edge_type, count in sorted(edge_counts.items()))
        or "none"
    )
    return (
        f"Root compound: {_summary_value(summary, 'root_compound', '')}\n"
        f"Node count: {_summary_value(summary, 'node_count', 0)}\n"
        f"Edge count: {_summary_value(summary, 'edge_count', 0)}\n"
        f"Node types: {top_nodes}\n"
        f"Edge types: {top_edges}\n"
        "Patent nodes: "
        f"{', '.join(_summary_value(summary, 'patent_node_ids', [])[:10]) or 'none'}\n"
        f"Family nodes: {', '.join(_summary_value(summary, 'family_node_ids', [])[:10]) or 'none'}"
    )


def format_matter_store_summary_text(matter_store) -> str:
    """Render the live matter-store summary for coverage assessment prompts."""
    if not matter_store:
        return ""

    summary = _summary_value(matter_store, "matter_graph_summary", None)
    record_completeness = _summary_value(matter_store, "record_completeness", None)
    run_observability = _summary_value(matter_store, "run_observability", None)
    collector_runs = _summary_value(matter_store, "collector_runs", []) or []
    record_contradictions = _summary_value(matter_store, "record_contradictions", []) or []

    collector_lines: list[str] = []
    for run in collector_runs[:5]:
        collector_name = _summary_value(_summary_value(run, "definition", {}), "collector_name", "")
        collection_state = _summary_value(run, "collection_state", "")
        missing_patents = ", ".join(_summary_value(run, "missing_patent_ids", [])[:3]) or "none"
        collector_lines.append(
            f"{collector_name or 'collector'}={collection_state or 'unknown'} "
            f"(missing patents: {missing_patents})"
        )

    contradiction_lines: list[str] = []
    for contradiction in record_contradictions[:5]:
        contradiction_lines.append(_summary_value(contradiction, "summary", ""))

    required_components = (
        ", ".join(_summary_value(record_completeness, "required_components", [])[:10]) or "none"
    )
    missing_components = (
        ", ".join(_summary_value(record_completeness, "missing_components", [])[:10]) or "none"
    )
    false_clear_flags = (
        ", ".join(_summary_value(run_observability, "false_clear_risk_flags", [])[:10]) or "none"
    )
    contradictions = " | ".join(filter(None, contradiction_lines)) or "none"
    collectors = " | ".join(collector_lines) or "none"

    return (
        f"{format_matter_graph_summary_text(summary)}\n"
        f"Required components: {required_components}\n"
        f"Missing components: {missing_components}\n"
        f"Collector ledger: {collectors}\n"
        f"False-clear flags: {false_clear_flags}\n"
        f"Unresolved contradictions: {contradictions}"
    ).strip()


def build_coverage_context(
    compound: ResolvedCompound,
    queries_used: ExpandedSearchQueries,
    source_health: SourceHealth,
    iteration: int,
    *,
    search_stats: str,
    triage_stats: str,
    clearance_policy: dict[str, object] | None = None,
    known_record_gaps: list[str] | None = None,
    collection_directives: list[EvidenceCollectionDirective] | None = None,
    matter_graph_summary=None,
    matter_store=None,
) -> dict[str, object]:
    """Assemble the structured context used by the coverage assessment agent."""
    return {
        "compound_info": format_compound_context(
            compound,
            include_inchi=True,
            include_weight=True,
        ),
        "search_stats": search_stats,
        "triage_stats": triage_stats,
        "source_health": format_source_health_text(source_health),
        "queries_used": format_queries_used_text(queries_used),
        "iteration_number": iteration,
        "clearance_policy": format_clearance_policy_text(clearance_policy),
        "known_record_gaps": list(known_record_gaps or []),
        "evidence_collection_directives": format_collection_directives_text(collection_directives),
        "matter_graph_summary": format_matter_graph_summary_text(matter_graph_summary),
        "matter_store_summary": format_matter_store_summary_text(matter_store),
    }


def build_iteration_log(
    *,
    iteration_number: int,
    patents_found_new: int,
    patents_found_total: int,
    triage_relevant_new: int,
    queries_used: ExpandedSearchQueries,
    input_tokens: int,
    output_tokens: int,
) -> SearchIterationLog:
    """Construct a search loop iteration log."""
    return SearchIterationLog(
        iteration_number=iteration_number,
        patents_found_new=patents_found_new,
        patents_found_total=patents_found_total,
        triage_relevant_new=triage_relevant_new,
        queries_used=queries_used,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def build_loop_result(
    iteration_logs: list[SearchIterationLog],
    *,
    pending_collection_directives: list[EvidenceCollectionDirective] | None = None,
    termination_reason: str = "",
) -> SearchLoopResult:
    """Construct final search loop metadata from completed iteration logs."""
    return SearchLoopResult(
        iterations_completed=len(iteration_logs),
        iteration_logs=iteration_logs,
        final_assessment=iteration_logs[-1].assessment if iteration_logs else None,
        pending_collection_directives=list(pending_collection_directives or []),
        termination_reason=termination_reason,
        total_input_tokens=sum(il.input_tokens for il in iteration_logs),
        total_output_tokens=sum(il.output_tokens for il in iteration_logs),
    )


def fallback_source_health() -> SourceHealth:
    """Return an empty source health payload."""
    return SourceHealth(entries=[])


# ---------------------------------------------------------------------------
# search_loop_state -- state bookkeeping helpers
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SearchLoopState:
    all_patent_hits: list[PatentHit] = field(default_factory=list)
    seen_patent_ids: set[str] = field(default_factory=set)
    all_triage_relevant: list[TriageResult] = field(default_factory=list)
    all_triage_complete: list[TriageResult] = field(default_factory=list)
    all_search_funnel: list[SearchFunnelEntry] = field(default_factory=list)
    iteration_logs: list[SearchIterationLog] = field(default_factory=list)
    total_triage_in: int = 0
    total_triage_out: int = 0
    total_triage_failed: int = 0
    last_source_health: SourceHealth | None = None
    current_queries: ExpandedSearchQueries | None = None
    accumulated_queries: ExpandedSearchQueries | None = None
    prosecution_cache: dict[str, dict[str, object]] = field(default_factory=dict)
    collector_runs: list = field(default_factory=list)
    pending_collection_directives: list[EvidenceCollectionDirective] = field(default_factory=list)
    termination_reason: str = ""


def record_search_results(
    state: SearchLoopState,
    *,
    new_hits: list[PatentHit],
    source_health: SourceHealth,
    search_funnel: list[SearchFunnelEntry],
) -> list[PatentHit]:
    """Record Step 2 results and return only truly new patent hits."""
    state.last_source_health = source_health
    state.all_search_funnel.extend(search_funnel)

    truly_new: list[PatentHit] = []
    for hit in new_hits:
        # Normalise before dedup so that the same patent arriving in a later
        # iteration with a different kind code or formatting (e.g. "US10,123,456 B2"
        # vs "US10123456B1") is still recognised as already-seen.
        norm_id = normalize_patent_id(hit.patent_id)
        if norm_id in state.seen_patent_ids:
            continue
        state.seen_patent_ids.add(norm_id)
        truly_new.append(hit)
    state.all_patent_hits.extend(truly_new)
    return truly_new


def record_triage_results(
    state: SearchLoopState,
    *,
    triage_relevant: list[TriageResult],
    triage_all: list[TriageResult],
    input_tokens: int,
    output_tokens: int,
    failed_count: int,
) -> None:
    """Accumulate Step 3 results into the loop state."""
    state.all_triage_relevant.extend(triage_relevant)
    state.all_triage_complete.extend(triage_all)
    state.total_triage_in += input_tokens
    state.total_triage_out += output_tokens
    state.total_triage_failed += failed_count


def build_iteration_record(
    *,
    state: SearchLoopState,
    iteration_number: int,
    patents_found_new: int,
    triage_relevant_new: int,
    input_tokens: int,
    output_tokens: int,
) -> SearchIterationLog:
    """Build and return the iteration log entry for this pass."""
    assert state.current_queries is not None
    return build_iteration_log(
        iteration_number=iteration_number,
        patents_found_new=patents_found_new,
        patents_found_total=len(state.all_patent_hits),
        triage_relevant_new=triage_relevant_new,
        queries_used=state.current_queries,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def apply_coverage_assessment(
    state: SearchLoopState,
    *,
    iter_log: SearchIterationLog,
    assessment: CoverageAssessment,
    input_tokens: int,
    output_tokens: int,
    coverage_threshold: float,
    merge_queries_fn: Callable[
        [ExpandedSearchQueries, ExpandedSearchQueries],
        ExpandedSearchQueries,
    ],
    patent_hits: list[PatentHit] | None = None,
) -> bool:
    """Apply a coverage assessment to state and return whether to stop."""
    assert state.accumulated_queries is not None
    iter_log.assessment = assessment
    iter_log.input_tokens += input_tokens
    iter_log.output_tokens += output_tokens
    state.pending_collection_directives = list(assessment.evidence_collection_directives)

    if assessment.coverage_adequate and assessment.confidence >= coverage_threshold:
        state.termination_reason = "coverage_adequate"
        state.iteration_logs.append(iter_log)
        return True

    if assessment.suggested_queries:
        if assessment.suggested_queries.provenance.origin == "unknown":
            assessment.suggested_queries.provenance = QueryExpansionProvenance(
                origin="coverage_assessment_agent",
                grounded=False,
            )
        state.current_queries = assessment.suggested_queries
        state.accumulated_queries = merge_queries_fn(
            state.accumulated_queries,
            state.current_queries,
        )
        state.termination_reason = ""
        return False

    if patent_hits:
        fallback_queries = synthesize_search_queries_from_directives(
            assessment.evidence_collection_directives,
            patent_hits,
            state.accumulated_queries,
        )
        if fallback_queries:
            state.current_queries = fallback_queries
            state.accumulated_queries = merge_queries_fn(
                state.accumulated_queries,
                state.current_queries,
            )
            state.termination_reason = ""
            return False

    state.termination_reason = (
        "record_collection_required"
        if assessment.evidence_collection_directives
        else "no_additional_search_directions"
    )
    state.iteration_logs.append(iter_log)
    return True


# ---------------------------------------------------------------------------
# search_loop_assessment -- coverage assessment agent
# ---------------------------------------------------------------------------


async def assess_search_coverage(
    compound: ResolvedCompound,
    patent_hits: list[PatentHit],
    triage_results: list[TriageResult],
    all_triage: list[TriageResult],
    queries_used: ExpandedSearchQueries,
    source_health: SourceHealth,
    iteration: int,
    *,
    prosecution_cache: dict[str, dict[str, object]] | None = None,
    existing_collector_runs: list | None = None,
    model_name: str,
) -> tuple[CoverageAssessment, int, int]:
    """Run the coverage assessment agent and return the assessment plus token usage."""
    from praviar_pipeline.agents.coverage import CoverageAssessmentAgent
    from praviar_pipeline.clients.claude import ClaudeClient
    from praviar_pipeline.pipeline.runtime.matter_graph_state import (
        build_runtime_evidence_snapshot,
    )

    search_stats = compute_search_stats(patent_hits)
    triage_stats = compute_triage_stats(triage_results, all_triage)
    settings = get_settings()
    gap_plan = build_search_gap_plan(
        patent_hits,
        all_triage,
        source_health,
        settings=settings,
    )
    directives = build_search_collection_directives(gap_plan)
    evidence_snapshot = build_runtime_evidence_snapshot(
        compound=compound,
        analyses=[],
        doe_assessments=[],
        invalidity_assessments=[],
        analysis_failures=[],
        patent_hits=patent_hits,
        prosecution_cache=prosecution_cache,
        source_health=source_health,
        search_loop_result=None,
        settings=settings,
        existing_collector_runs=existing_collector_runs,
    )
    context = build_coverage_context(
        compound,
        queries_used,
        source_health,
        iteration,
        search_stats=search_stats,
        triage_stats=triage_stats,
        clearance_policy={
            "matter_type": settings.matter_type,
            "jurisdiction_policy": settings.jurisdiction_policy,
            "clearance_threshold_profile": settings.clearance_threshold_profile,
            "source_authority_policy": settings.source_authority_policy,
            "required_record_components": gap_plan.required_components,
        },
        known_record_gaps=gap_plan.known_record_gaps,
        collection_directives=directives,
        matter_graph_summary=evidence_snapshot.matter_graph_summary,
        matter_store=evidence_snapshot.matter_store,
    )

    async with ClaudeClient() as claude:
        agent = CoverageAssessmentAgent(claude)
        findings, trace = await agent.research(
            f"Assess search coverage for {compound.name} FTO analysis",
            context,
        )

        assessment, usage = await claude.complete(
            system=(
                "Extract a CoverageAssessment from the findings below. "
                "Output JSON with: coverage_adequate (bool), confidence (0-1), "
                "gaps_identified (list of objects with gap_type/description/suggested_action), "
                "suggested_queries (object with patent_synonyms/cpc_codes/key_assignees/"
                "process_keywords/compound_class_terms lists, or null), "
                "iteration_summary (str), assignee_distribution (dict), cpc_distribution (dict)."
            ),
            user=sanitize_untrusted_text(
                findings,
                max_len=6000,
                data_type="model_coverage_findings",
            ),
            response_model=CoverageAssessment,
            model=model_name,
            max_tokens=4096,
            cache_system=True,
            role="search_loop",
        )
        assessment = apply_record_gap_guard(assessment, gap_plan.known_record_gaps)
        assessment.evidence_collection_directives = directives

    total_in = trace.total_input_tokens + usage.get("input_tokens", 0)
    total_out = trace.total_output_tokens + usage.get("output_tokens", 0)

    return assessment, total_in, total_out


# ---------------------------------------------------------------------------
# search_loop -- the main loop driver
# ---------------------------------------------------------------------------


async def _assess_coverage(
    compound: ResolvedCompound,
    patent_hits: list[PatentHit],
    triage_results: list[TriageResult],
    all_triage: list[TriageResult],
    queries_used: ExpandedSearchQueries,
    source_health: SourceHealth,
    iteration: int,
    prosecution_cache: dict[str, dict[str, object]],
    collector_runs: list,
) -> tuple[CoverageAssessment, int, int]:
    """Run coverage assessment agent and return structured assessment with token counts."""
    settings = get_settings()
    collector_result = await execute_live_evidence_collectors(
        compound=compound,
        patent_hits=patent_hits,
        source_health=source_health,
        prosecution_cache=prosecution_cache,
        collector_runs=collector_runs,
        settings=settings,
    )
    prosecution_cache.clear()
    prosecution_cache.update(collector_result.prosecution_cache)
    collector_runs.clear()
    collector_runs.extend(collector_result.collector_runs)
    source_health.entries = list(collector_result.source_health.entries)
    return await assess_search_coverage(
        compound,
        patent_hits,
        triage_results,
        all_triage,
        queries_used,
        collector_result.source_health,
        iteration,
        prosecution_cache=prosecution_cache,
        existing_collector_runs=collector_runs,
        model_name=settings.claude_triage_model,
    )


def _merge_queries(
    base: ExpandedSearchQueries,
    new: ExpandedSearchQueries,
) -> ExpandedSearchQueries:
    """Merge two ExpandedSearchQueries, deduplicating terms while preserving order."""
    return merge_queries(base, new)


async def run_search_loop(
    compound: ResolvedCompound,
    initial_queries: ExpandedSearchQueries,
    *,
    force_iterations: bool = False,
) -> tuple[
    list[PatentHit],  # all patent hits (deduplicated)
    SourceHealth,  # source health from last iteration
    list[SearchFunnelEntry],  # search funnel entries
    list[TriageResult],  # filtered triage results (relevant + possibly)
    int,  # triage_in tokens
    int,  # triage_out tokens
    int,  # triage_failed count
    list[TriageResult],  # all triage results (for audit)
    SearchLoopResult,  # loop metadata
]:
    """Execute the agentic search loop.

    When search_loop_enabled=False: single iteration (current behaviour).
    When search_loop_enabled=True: up to N iterations with coverage
    assessment between iterations.

    Returns:
        A 9-tuple of (patent_hits, source_health, search_funnel, triage_relevant,
        triage_in_tokens, triage_out_tokens, triage_failed, all_triage, loop_result).
    """
    settings = get_settings()

    state = SearchLoopState(
        current_queries=initial_queries,
        accumulated_queries=initial_queries,
    )

    loop_enabled = settings.search_loop_enabled or force_iterations
    max_iterations = settings.search_loop_max_iterations if loop_enabled else 1

    for iteration in range(max_iterations):
        assert state.current_queries is not None
        assert state.accumulated_queries is not None
        logger.info(
            "search_loop_iteration_start",
            iteration=iteration + 1,
            max_iterations=max_iterations,
            total_patents_so_far=len(state.all_patent_hits),
            queries_cpc=len(state.current_queries.cpc_codes),
            queries_assignees=len(state.current_queries.key_assignees),
        )

        # Step 2: Search
        new_hits, source_health, search_funnel = await search_patents(
            compound,
            expanded_queries=state.current_queries,
        )
        truly_new = record_search_results(
            state,
            new_hits=new_hits,
            source_health=source_health,
            search_funnel=search_funnel,
        )

        logger.info(
            "search_loop_iteration_search",
            iteration=iteration + 1,
            raw_hits=len(new_hits),
            truly_new=len(truly_new),
            total_unique=len(state.all_patent_hits),
        )

        # Step 3: Triage only new patents
        iter_triage_relevant: list[TriageResult] = []
        iter_triage_all: list[TriageResult] = []
        iter_triage_in = iter_triage_out = iter_triage_failed = 0

        if truly_new:
            (
                iter_triage_relevant,
                iter_triage_in,
                iter_triage_out,
                iter_triage_failed,
                iter_triage_all,
            ) = await triage_patents(truly_new, compound)
            record_triage_results(
                state,
                triage_relevant=iter_triage_relevant,
                triage_all=iter_triage_all,
                input_tokens=iter_triage_in,
                output_tokens=iter_triage_out,
                failed_count=iter_triage_failed,
            )

        # Build iteration log
        iter_log = build_iteration_record(
            state=state,
            iteration_number=iteration + 1,
            patents_found_new=len(truly_new),
            triage_relevant_new=len(iter_triage_relevant),
            input_tokens=iter_triage_in,
            output_tokens=iter_triage_out,
        )

        # Coverage assessment (only if more iterations are possible and loop is enabled)
        if iteration < max_iterations - 1 and loop_enabled:
            assert state.accumulated_queries is not None
            try:
                assessment, assess_in, assess_out = await _assess_coverage(
                    compound,
                    state.all_patent_hits,
                    state.all_triage_relevant,
                    state.all_triage_complete,
                    state.accumulated_queries,
                    source_health,
                    iteration + 1,
                    state.prosecution_cache,
                    state.collector_runs,
                )

                logger.info(
                    "search_loop_coverage_assessment",
                    iteration=iteration + 1,
                    coverage_adequate=assessment.coverage_adequate,
                    confidence=assessment.confidence,
                    gaps=len(assessment.gaps_identified),
                )

                if apply_coverage_assessment(
                    state,
                    iter_log=iter_log,
                    assessment=assessment,
                    input_tokens=assess_in,
                    output_tokens=assess_out,
                    coverage_threshold=settings.search_loop_coverage_threshold,
                    merge_queries_fn=_merge_queries,
                    patent_hits=state.all_patent_hits,
                ):
                    break

            except Exception as exc:
                logger.warning(
                    "coverage_assessment_failed",
                    iteration=iteration + 1,
                    error_type=safe_exception_type(exc),
                )
                state.termination_reason = "coverage_assessment_failed"
                state.iteration_logs.append(iter_log)
                break

        state.iteration_logs.append(iter_log)

    if not state.termination_reason:
        if loop_enabled and len(state.iteration_logs) >= max_iterations:
            state.termination_reason = "max_iterations_reached"
        else:
            state.termination_reason = "single_pass_completed"

    # Build final loop result
    loop_result = build_loop_result(
        state.iteration_logs,
        pending_collection_directives=state.pending_collection_directives,
        termination_reason=state.termination_reason,
    )

    logger.info(
        "search_loop_complete",
        iterations=loop_result.iterations_completed,
        total_patents=len(state.all_patent_hits),
        total_relevant=len(state.all_triage_relevant),
        total_tokens=loop_result.total_input_tokens + loop_result.total_output_tokens,
    )

    return (
        state.all_patent_hits,
        state.last_source_health or fallback_source_health(),
        state.all_search_funnel,
        state.all_triage_relevant,
        state.total_triage_in,
        state.total_triage_out,
        state.total_triage_failed,
        state.all_triage_complete,
        loop_result,
    )
