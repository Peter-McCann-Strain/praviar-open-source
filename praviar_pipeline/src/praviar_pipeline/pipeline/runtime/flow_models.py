"""Shared dataclasses for pipeline runtime flow orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(slots=True)
class RunBootstrapResult:
    settings: Any
    checkpoint_integrity_keys: Any
    execution_profile: str
    analysis_escalation_reasons: list[str]
    user_input: str
    run_id: str
    checkpoint_dir: Path
    started_at_epoch: float
    deadline_epoch: float | None
    completed_step: int = 0
    timing_data: list = field(default_factory=list)
    reasoning_traces: list = field(default_factory=list)
    compound: Any = None
    expanded_queries: Any = None
    patent_hits: list = field(default_factory=list)
    source_health: Any = None
    search_funnel: list = field(default_factory=list)
    matter_graph: Any = None
    matter_graph_summary: Any = None
    matter_store: Any = None
    evidence_artifacts: list = field(default_factory=list)
    evidence_adapter_results: list = field(default_factory=list)
    collector_runs: list = field(default_factory=list)
    triage_results: list = field(default_factory=list)
    all_triage: list = field(default_factory=list)
    triage_in: int = 0
    triage_out: int = 0
    triage_failed: int = 0
    analyses: list = field(default_factory=list)
    analysis_failures: list = field(default_factory=list)
    prosecution_cache: dict[str, dict[str, object]] = field(default_factory=dict)
    critic_report: Any = None
    critic_in: int = 0
    critic_out: int = 0
    search_loop_result: Any = None
    doe_assessments: list = field(default_factory=list)
    doe_in: int = 0
    doe_out: int = 0
    invalidity_assessments: list = field(default_factory=list)
    inv_in: int = 0
    inv_out: int = 0
    verification: Any = None
    regulatory_exclusivity: Any = None
    drawing_evidence: Any = None


@dataclass(slots=True)
class RuntimeTerminationInfo:
    reason: str
    step: str
    description: str
    impact: str
    action_description: str
    action_reasoning: str
