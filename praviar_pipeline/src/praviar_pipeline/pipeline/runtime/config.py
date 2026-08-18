"""Runtime configuration helpers for Praviar Pipeline pipeline execution."""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, create_model

from praviar_pipeline.config import Settings

ANALYSIS_CONFIG_OVERRIDE_MAP = {
    "claude_triage_model": "claude_triage_model",
    "claude_analysis_model": "claude_analysis_model",
    "claude_deep_model": "claude_deep_model",
    "output_dir": "output_dir",
    "search_jurisdictions": "search_allowed_jurisdictions",
    "search_max_ranked_results": "search_max_ranked_results",
    "search_tanimoto_threshold": "search_tanimoto_threshold",
    "include_expired": "search_include_expired",
    "enable_pubchem": "search_enable_pubchem",
    "enable_bigquery": "search_enable_bigquery",
    "enable_surechembl": "search_enable_surechembl",
    "enable_patcid": "search_enable_patcid",
    "search_expired_grace_years": "search_expired_grace_years",
    "citation_traversal_enabled": "search_citation_traversal_enabled",
    "citation_max_depth": "search_citation_max_depth",
    "analysis_thinking_budget_tokens": "analysis_thinking_budget_tokens",
    "thinking_effort_analysis": "thinking_effort_analysis",
    "thinking_effort_triage": "thinking_effort_triage",
    "thinking_effort_report": "thinking_effort_report",
    "search_loop_enabled": "search_loop_enabled",
    "hitl_enabled": "hitl_enabled",
    "hitl_checkpoints": "hitl_checkpoints",
    "hitl_auto_skip_minutes": "hitl_auto_skip_minutes",
    "identity_review_required": "identity_review_required",
    "max_analysis_patents": "max_analysis_patents",
    "max_doe_candidates": "max_doe_candidates",
    "triage_batch_size": "triage_batch_size",
    "matter_type": "matter_type",
    "trust_mode": "trust_mode",
    "intended_actions": "intended_actions",
    "product_context": "product_context",
    "target_jurisdictions": "target_jurisdictions",
    "jurisdiction_bundle": "jurisdiction_bundle",
    "development_stage": "development_stage",
    "asset_type_hint": "asset_type_hint",
    "jurisdiction_policy": "jurisdiction_policy",
    "clearance_threshold_profile": "clearance_threshold_profile",
    "max_run_duration_hours": "max_run_duration_hours",
    "source_authority_policy": "source_authority_policy",
    "required_record_components": "required_record_components",
    "require_verified_manual_markush": "require_verified_manual_markush",
    "markush_evidence_max_age_days": "markush_evidence_max_age_days",
    "markush_evidence_receipt": "markush_evidence_receipt",
    "response_cache_mode": "response_cache_mode",
    "response_cache_dir": "response_cache_dir",
    "response_cache_expected_digest": "response_cache_expected_digest",
    "response_cache_expected_hmac": "response_cache_expected_hmac",
    "response_cache_expected_key_id": "response_cache_expected_key_id",
}


_ANALYSIS_CONFIG_FIELDS: dict[str, Any] = {
    api_key: (Settings.model_fields[settings_key].annotation, None)
    for api_key, settings_key in ANALYSIS_CONFIG_OVERRIDE_MAP.items()
}

AnalysisConfigOverrides = create_model(
    "AnalysisConfigOverrides",
    __config__=ConfigDict(extra="forbid", strict=True),
    **_ANALYSIS_CONFIG_FIELDS,
)


def apply_analysis_config_overrides(
    settings: Settings,
    config_overrides: dict | None,
) -> Settings:
    """Return a new, atomically validated settings instance with overrides."""
    if not config_overrides:
        return settings

    validated = AnalysisConfigOverrides.model_validate(config_overrides)
    updates = {
        ANALYSIS_CONFIG_OVERRIDE_MAP[api_key]: value
        for api_key, value in validated.model_dump(exclude_unset=True).items()
    }
    complete_payload = settings.model_dump()
    complete_payload.update(updates)
    return settings.__class__.model_validate(complete_payload)
