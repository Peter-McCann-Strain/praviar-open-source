from __future__ import annotations

from types import SimpleNamespace

import pytest

from praviar_pipeline.config_models import ClaudeModels, build_claude_models
from praviar_pipeline.config_paths import resolve_checkpoint_dir, resolve_output_dir
from praviar_pipeline.config_validators import (
    normalize_policy_string,
    normalize_required_record_components,
    validate_log_level,
)


def test_pipeline_mode_validator_removed_from_public_config_contract() -> None:
    import praviar_pipeline.config_validators as validators

    assert not hasattr(validators, "validate_pipeline_mode")


def test_normalize_required_record_components_deduplicates() -> None:
    assert normalize_required_record_components("claims_text, family_context, claims_text") == [
        "claims_text",
        "family_context",
    ]


def test_normalize_policy_string_lowercases() -> None:
    assert normalize_policy_string(" Official_Plus_Licensed ") == "official_plus_licensed"


def test_validate_log_level_normalizes() -> None:
    assert validate_log_level("debug") == "DEBUG"


def test_validate_log_level_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="Invalid log_level"):
        validate_log_level("verbose")


def test_build_claude_models_uses_settings_fields() -> None:
    models = build_claude_models(
        SimpleNamespace(
            claude_triage_model="triage-model",
            claude_analysis_model="analysis-model",
            claude_deep_model="deep-model",
        )
    )

    assert isinstance(models, ClaudeModels)
    assert models.triage == "triage-model"
    assert models.analysis == "analysis-model"
    assert models.deep == "deep-model"


def test_resolve_output_and_checkpoint_dir_create_directories(tmp_path) -> None:
    output_settings = SimpleNamespace(output_dir=str(tmp_path / "out"))
    checkpoint_settings = SimpleNamespace(checkpoint_dir=str(tmp_path / "ckpt"))

    output_dir = resolve_output_dir(output_settings)
    checkpoint_dir = resolve_checkpoint_dir(checkpoint_settings)

    assert output_dir.exists()
    assert checkpoint_dir.exists()
    assert output_dir == tmp_path / "out"
    assert checkpoint_dir == tmp_path / "ckpt"
