"""Restoration helpers for pipeline checkpoints."""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)


def _restore_list(
    data: list[dict] | None,
    model_cls: type[ModelT],
    logger,
) -> list[ModelT]:
    if not data:
        return []
    try:
        restored = []
        for item in data:
            restored.append(model_cls.model_validate(item))
        return restored
    except (ValidationError, ValueError, TypeError):
        logger.warning("checkpoint_restore_list_failed", model=model_cls.__name__)
        raise ValueError(f"Checkpoint contains invalid {model_cls.__name__} records") from None


def _restore_one(
    data: dict | None,
    model_cls: type[ModelT],
    logger,
) -> ModelT | None:
    if not data:
        return None
    try:
        return model_cls.model_validate(data)
    except (ValidationError, ValueError, TypeError):
        logger.warning("checkpoint_restore_failed", model=model_cls.__name__)
        raise ValueError(f"Checkpoint contains invalid {model_cls.__name__} data") from None


def _restore_drawing_evidence(data: dict | None, logger) -> Any:
    if not data:
        return None
    from praviar_pipeline.models.drawing import DrawingEvidenceStore

    try:
        return DrawingEvidenceStore.from_dict(data)
    except (ValidationError, ValueError, TypeError):
        logger.warning("checkpoint_restore_drawing_failed")
        raise ValueError("Checkpoint contains invalid drawing evidence") from None


def _restore_patent_hits(
    data: list[dict] | None,
    *,
    checkpoint,
    checkpoint_restore_capability: object | None,
) -> list:
    """Restore patent hits and reattach trust only for a validated loader capability."""
    from praviar_pipeline.models.patent import (
        PatentHit,
        _restore_checkpoint_claim_text_attestation,
        _restore_checkpoint_legal_status_attestation,
    )

    try:
        restored: list[PatentHit] = []
        for item in data or []:
            hit = PatentHit.model_validate(item)
            if hit.claims_text_provenance is not None and checkpoint_restore_capability is not None:
                _restore_checkpoint_claim_text_attestation(
                    hit,
                    checkpoint=checkpoint,
                    checkpoint_restore_capability=checkpoint_restore_capability,
                )
            if hit.legal_status_provenance is not None or hit.legal_status_observations:
                if checkpoint_restore_capability is None:
                    # Manually constructed/deserialized checkpoints have no loader trust.
                    restored.append(hit)
                    continue
                _restore_checkpoint_legal_status_attestation(
                    hit,
                    checkpoint=checkpoint,
                    checkpoint_restore_capability=checkpoint_restore_capability,
                )
            restored.append(hit)
        return restored
    except ValidationError as exc:
        # Preserve only fixed provenance-policy outcomes; never replay
        # attacker-controlled validation prose from the checkpoint.
        messages = {str(error.get("msg", "")) for error in exc.errors()}
        for stable_message in (
            "legal-status retained artifact hash mismatch",
            "legal-status collector version is not trusted",
            "legal-status provenance is stale",
        ):
            if any(stable_message in message for message in messages):
                raise ValueError(stable_message) from None
        raise ValueError("Checkpoint contains invalid PatentHit records") from None
    except TypeError:
        raise ValueError("Checkpoint contains invalid PatentHit records") from None


def restore_checkpoint_state(
    ckpt,
    logger,
    *,
    checkpoint_restore_capability: object | None = None,
) -> dict[str, Any]:
    """Deserialize checkpoint data back to typed Pydantic objects."""
    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.audit import StepTiming
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.critic import CriticReport
    from praviar_pipeline.models.equivalents import DoEAssessment
    from praviar_pipeline.models.invalidity import InvalidityAssessment
    from praviar_pipeline.models.reasoning import ReasoningTrace
    from praviar_pipeline.models.report import AnalysisFailure, SourceHealth, VerificationResult
    from praviar_pipeline.models.report_evidence import (
        EvidenceAdapterResult,
        EvidenceArtifact,
        EvidenceCollectorRun,
        MatterGraph,
        MatterGraphSummary,
        MatterStore,
    )
    from praviar_pipeline.models.search import ExpandedSearchQueries
    from praviar_pipeline.models.search_loop import SearchLoopResult
    from praviar_pipeline.models.triage import TriageResult

    compound = None
    if ckpt.compound:
        compound = _restore_one(ckpt.compound, ResolvedCompound, logger)

    return {
        "compound": compound,
        "expanded_queries": _restore_one(ckpt.expanded_queries, ExpandedSearchQueries, logger),
        "patent_hits": _restore_patent_hits(
            ckpt.patent_hits,
            checkpoint=ckpt,
            checkpoint_restore_capability=checkpoint_restore_capability,
        ),
        "source_health": _restore_one(ckpt.source_health, SourceHealth, logger),
        "search_funnel": ckpt.search_funnel,
        "matter_graph": _restore_one(ckpt.matter_graph, MatterGraph, logger),
        "matter_graph_summary": _restore_one(ckpt.matter_graph_summary, MatterGraphSummary, logger),
        "matter_store": _restore_one(ckpt.matter_store, MatterStore, logger),
        "evidence_artifacts": _restore_list(ckpt.evidence_artifacts, EvidenceArtifact, logger),
        "evidence_adapter_results": _restore_list(
            ckpt.evidence_adapter_results,
            EvidenceAdapterResult,
            logger,
        ),
        "collector_runs": _restore_list(ckpt.collector_runs, EvidenceCollectorRun, logger),
        "drawing_results": _restore_drawing_evidence(ckpt.drawing_results, logger),
        "triage_results": _restore_list(ckpt.triage_results, TriageResult, logger),
        "all_triage_results": _restore_list(ckpt.all_triage_results, TriageResult, logger),
        "triage_input_tokens": ckpt.triage_input_tokens,
        "triage_output_tokens": ckpt.triage_output_tokens,
        "triage_failed": ckpt.triage_failed,
        "analyses": _restore_list(ckpt.analyses, PatentAnalysis, logger),
        "analysis_failures": _restore_list(ckpt.analysis_failures, AnalysisFailure, logger),
        "prosecution_cache": ckpt.prosecution_cache or {},
        "reasoning_traces": _restore_list(ckpt.reasoning_traces, ReasoningTrace, logger),
        "critic_report": _restore_one(ckpt.critic_report, CriticReport, logger),
        "critic_input_tokens": ckpt.critic_input_tokens,
        "critic_output_tokens": ckpt.critic_output_tokens,
        "search_loop_result": _restore_one(ckpt.search_loop_result, SearchLoopResult, logger),
        "doe_assessments": _restore_list(ckpt.doe_assessments, DoEAssessment, logger),
        "doe_input_tokens": ckpt.doe_input_tokens,
        "doe_output_tokens": ckpt.doe_output_tokens,
        "invalidity_assessments": _restore_list(
            ckpt.invalidity_assessments,
            InvalidityAssessment,
            logger,
        ),
        "inv_input_tokens": ckpt.inv_input_tokens,
        "inv_output_tokens": ckpt.inv_output_tokens,
        "verification": _restore_one(ckpt.verification, VerificationResult, logger),
        "regulatory_exclusivity": ckpt.regulatory_exclusivity,
        "timing_data": _restore_list(ckpt.timing_data, StepTiming, logger),
    }
