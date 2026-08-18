"""Bootstrap helpers for pipeline runtime flow orchestration."""

from __future__ import annotations

import time
from pathlib import Path

from praviar_pipeline.cost_tracker import CostTracker, set_current_tracker
from praviar_pipeline.manifest import start_provenance_context
from praviar_pipeline.pipeline.analysis.adaptive_decision import (
    WORLD_CLASS_EXECUTION_PROFILE,
    dedupe_reasons,
)
from praviar_pipeline.pipeline.runtime.flow_helpers import (
    restore_run_context_from_checkpoint,
)
from praviar_pipeline.pipeline.runtime.flow_models import RunBootstrapResult
from praviar_pipeline.response_cache import (
    CacheMode,
    ResponseCache,
    get_current_cache,
    set_current_cache,
)
from praviar_pipeline.utils.determinism import seed_pipeline_rng


def bootstrap_run_context(
    *,
    user_input: str,
    resume_from: str | None,
    config_overrides: dict | None,
    get_settings_fn,
    apply_analysis_config_overrides_fn,
    bind_pipeline_context_fn,
    bind_compound_context_fn,
    restore_runtime_state_fn,
    logger,
) -> RunBootstrapResult:
    """Create the mutable run context, optionally restoring from checkpoint."""
    settings = get_settings_fn()
    settings = apply_analysis_config_overrides_fn(settings, config_overrides)
    # Pin Python/NumPy RNG before any pipeline work so any tie-breaking,
    # sampling, or future randomized ranking inherits a reproducible seed.
    # LLM sampling is pinned separately via temperature=0 on every analysis
    # and verification call. Tests that hand-build a SimpleNamespace settings
    # may omit ``deterministic_seed`` — fall back to the helper's default.
    seed_pipeline_rng(getattr(settings, "deterministic_seed", 42))
    # Install a fresh per-run cost tracker so every subsequent Claude call is
    # recorded against its role. The tracker is torn down in
    # ``finalize_report_output`` after the snapshot has been stamped into the
    # manifest. Any prior tracker (from a crashed/aborted run) is replaced.
    set_current_tracker(
        CostTracker(
            hard_budget_usd=float(getattr(settings, "pipeline_llm_hard_budget_usd", 50.0)),
        )
    )
    # Prompt/tool provenance is per run. Reset here so a long-lived worker
    # cannot leak collector state from a previous analysis into this manifest.
    start_provenance_context(
        tool_trace_key=settings.checkpoint_integrity_keys.active_key(),
        tool_trace_key_id=settings.checkpoint_integrity_keys.active_key_id,
    )
    initial_escalation_reasons = _initial_adaptive_escalation_reasons(settings)
    if initial_escalation_reasons:
        settings.search_loop_enabled = True
    run_id = bind_pipeline_context_fn(compound_input=user_input)
    started_at_epoch = time.time()
    deadline_epoch = started_at_epoch + (float(settings.max_run_duration_hours) * 3600.0)

    context = RunBootstrapResult(
        settings=settings,
        checkpoint_integrity_keys=settings.checkpoint_integrity_keys,
        execution_profile=WORLD_CLASS_EXECUTION_PROFILE,
        analysis_escalation_reasons=initial_escalation_reasons,
        user_input=user_input,
        run_id=run_id,
        checkpoint_dir=settings.resolved_checkpoint_dir / run_id,
        started_at_epoch=started_at_epoch,
        deadline_epoch=deadline_epoch,
    )

    resume_state = restore_runtime_state_fn(
        resume_from,
        integrity_keys=context.checkpoint_integrity_keys,
    )
    if resume_state:
        context = restore_run_context_from_checkpoint(
            context,
            resume_state=resume_state,
            resolved_checkpoint_dir=settings.resolved_checkpoint_dir,
            bind_compound_context_fn=bind_compound_context_fn,
            logger=logger,
        )

    context.execution_profile = WORLD_CLASS_EXECUTION_PROFILE
    context.analysis_escalation_reasons = dedupe_reasons(
        list(getattr(context, "analysis_escalation_reasons", []) or [])
        + _initial_adaptive_escalation_reasons(settings)
    )
    if context.analysis_escalation_reasons:
        settings.search_loop_enabled = True
    _install_response_cache(
        context=context,
        settings=settings,
        resume_from=resume_from,
    )
    return context


def _install_response_cache(*, context, settings, resume_from: str | None) -> None:
    """Install a private, run-local exact-response record/replay cache."""
    active_cache = get_current_cache()
    if active_cache is not None and active_cache.mode == CacheMode.DRY_RUN:
        # The explicit zero-spend harness is the authority for this run. Never
        # replace it with the ordinary configured cache and accidentally open
        # live network boundaries during bootstrap.
        return
    output_dir = getattr(settings, "resolved_output_dir", None)
    if not isinstance(output_dir, Path):
        # Minimal unit-test doubles do not represent a runnable Settings contract.
        set_current_cache(None)
        return

    configured_mode = CacheMode(settings.response_cache_mode)
    mode = (
        CacheMode.REPLAY_THEN_RECORD
        if resume_from and configured_mode == CacheMode.RECORD
        else configured_mode
    )
    if settings.response_cache_dir:
        cache_dir = Path(settings.response_cache_dir)
        reference = ""
    else:
        relative_dir = Path(".replay-cache") / context.run_id
        cache_dir = output_dir / relative_dir
        reference = str(relative_dir / ResponseCache.JSONL_FILENAME)

    cache = ResponseCache(
        cache_dir=cache_dir,
        mode=mode,
        manifest_reference=reference,
    )
    if resume_from and mode == CacheMode.REPLAY_THEN_RECORD and not cache.cache_path.is_file():
        raise RuntimeError("Retained response cache is required to resume this run")
    if mode == CacheMode.REPLAY:
        if not cache.cache_path.is_file():
            raise RuntimeError("Retained response cache is unavailable for exact replay")
        expected_key_id = settings.response_cache_expected_key_id
        if expected_key_id != context.checkpoint_integrity_keys.active_key_id:
            raise RuntimeError("Response cache audit key ID does not match active key")
        if not settings.response_cache_expected_digest:
            raise RuntimeError("Response cache digest is required for exact replay")
        if cache.digest() != settings.response_cache_expected_digest:
            raise RuntimeError("Response cache digest verification failed")
        expected_hmac = settings.response_cache_expected_hmac
        actual_hmac = cache.authenticated_digest(key=context.checkpoint_integrity_keys.active_key())
        if not expected_hmac or actual_hmac != expected_hmac:
            raise RuntimeError("Response cache authentication failed")
    set_current_cache(cache)


def _initial_adaptive_escalation_reasons(settings) -> list[str]:
    """Return matter-level reasons for agentic escalation before triage runs."""
    reasons: list[str] = []
    matter_type = str(getattr(settings, "matter_type", "") or "").strip().lower()
    asset_type_hint = str(getattr(settings, "asset_type_hint", "") or "").strip().lower()
    threshold_profile = (
        str(getattr(settings, "clearance_threshold_profile", "") or "").strip().lower()
    )
    trust_mode = str(getattr(settings, "trust_mode", "") or "").strip().lower()
    intended_actions = {
        str(action).strip().lower()
        for action in getattr(settings, "intended_actions", []) or []
        if str(action).strip()
    }
    target_jurisdictions = [
        str(code).strip().upper()
        for code in getattr(settings, "target_jurisdictions", []) or []
        if str(code).strip()
    ]
    required_components = {
        str(component).strip().lower()
        for component in getattr(settings, "required_record_components", []) or []
    }

    complex_matter_types = {
        "markush_candidate",
        "biologic",
        "biologic_or_sequence",
        "formulation",
        "process",
        "process_or_synthesis",
        "combination",
    }
    counsel_actions = {
        "commercial_action",
        "commercial_launch",
        "commercialization",
        "commercialisation",
        "design_around",
        "formulation_review",
        "manufacture_import",
        "method_of_use_review",
        "launch",
        "license",
        "licence",
        "invest",
        "partner",
        "file",
    }
    needs_counsel_grade_record = bool(
        required_components
        & {
            "claim_level_analysis",
            "authoritative_records",
            "family_context",
            "verification",
        }
    )
    if trust_mode == "counsel":
        reasons.append("counsel_trust_mode")
    if threshold_profile == "world_class_us_ep":
        reasons.append("clearance_grade_threshold")
    if matter_type in complex_matter_types or asset_type_hint in complex_matter_types:
        reasons.append("complex_matter_type")
    if len(target_jurisdictions) > 3:
        reasons.append("multi_jurisdiction_matter")
    if needs_counsel_grade_record:
        reasons.append("counsel_grade_record_required")
    if intended_actions & counsel_actions:
        reasons.append("commercial_or_filing_action")
    if getattr(settings, "search_citation_traversal_enabled", False):
        reasons.append("citation_traversal_enabled")
    return dedupe_reasons(reasons)
