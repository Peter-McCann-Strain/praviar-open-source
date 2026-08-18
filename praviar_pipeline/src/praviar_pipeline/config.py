"""Application settings loaded from environment variables and .env file."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from typing import TYPE_CHECKING, Literal, cast  # noqa: F401

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from praviar_pipeline.checkpoint import (
    DEV_CHECKPOINT_HMAC_KEYRING_SECRET,
    CheckpointIntegrityKeyRing,
)
from praviar_pipeline.config_models import ClaudeModels, build_claude_models
from praviar_pipeline.config_paths import (
    PROJECT_ROOT,
    REPO_ROOT,
    resolve_checkpoint_dir,
    resolve_output_dir,
)
from praviar_pipeline.config_runtime_sections import (
    PipelineExecutionSettingsMixin,
    QualityAndDisplaySettingsMixin,
    SearchSourceSettingsMixin,
)
from praviar_pipeline.config_sections import (
    DrawingPipelineSettingsMixin,
    OutputAndStorageSettingsMixin,
    TransportAndClientSettingsMixin,
)
from praviar_pipeline.config_validators import (
    check_api_keys,
    normalize_policy_string,
    normalize_required_record_components,
    validate_hybrid_retrieval_settings,
    validate_log_level,
)
from praviar_pipeline.triage_local_settings import TriageLocalSettings, get_triage_local_settings

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

__all__ = [
    "PROJECT_ROOT",
    "REPO_ROOT",
    "ClaudeModels",
    "Settings",
    "TriageLocalSettings",
    "clear_settings_cache",
    "get_settings",
    "get_triage_local_settings",
    "runtime_settings_context",
]


class Settings(
    DrawingPipelineSettingsMixin,
    OutputAndStorageSettingsMixin,
    PipelineExecutionSettingsMixin,
    QualityAndDisplaySettingsMixin,
    SearchSourceSettingsMixin,
    TransportAndClientSettingsMixin,
    BaseSettings,
):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="forbid",
    )

    # API Keys
    anthropic_api_key: str = ""
    google_application_credentials: str = ""
    bigquery_project_id: str = ""
    patentsview_api_key: str = ""
    uspto_odp_api_key: str = ""
    lens_api_key: str = ""
    tavily_api_key: str = ""
    hf_token: str = ""
    pipeline_checkpoint_hmac_secret: SecretStr = SecretStr(DEV_CHECKPOINT_HMAC_KEYRING_SECRET)
    certification_release_receipt_json: str = ""
    certification_release_public_key: SecretStr = SecretStr("")
    certification_release_key_id: str = ""
    certification_release_verifier_id: str = ""
    certification_api_oci_image_digest: str = ""
    certification_worker_oci_image_digest: str = ""
    certification_runtime_policy_sha256: str = ""
    certification_evidence_policy_sha256: str = ""
    certification_prompt_bundle_sha256: str = ""
    certification_model_bundle_sha256: str = ""
    certification_tool_definition_bundle_sha256: str = ""
    certification_collector_bundle_sha256: str = ""
    certification_revoked_receipt_ids: tuple[str, ...] = ()

    # LLM Models
    claude_triage_model: str = "claude-haiku-4-5-20251001"
    claude_analysis_model: str = "claude-sonnet-4-6"
    claude_deep_model: str = "claude-sonnet-4-6"

    @property
    def resolved_checkpoint_dir(self) -> Path:
        """Resolve checkpoint directory, creating it if needed."""
        return resolve_checkpoint_dir(self)

    @property
    def checkpoint_integrity_keys(self) -> CheckpointIntegrityKeyRing:
        """Return the dedicated runtime-only checkpoint signing key ring."""
        return CheckpointIntegrityKeyRing.from_secret(
            self.pipeline_checkpoint_hmac_secret.get_secret_value()
        )

    @field_validator(
        "matter_type",
        "jurisdiction_policy",
        "clearance_threshold_profile",
        "source_authority_policy",
        mode="before",
    )
    @classmethod
    def _normalize_policy_strings(cls, v: str) -> str:
        return normalize_policy_string(v)

    @field_validator("required_record_components", mode="before")
    @classmethod
    def _normalize_required_record_components(cls, v: list[str] | str | None) -> list[str]:
        return normalize_required_record_components(v)

    @field_validator("log_level", mode="before")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        return validate_log_level(v)

    @model_validator(mode="after")
    def _check_api_keys(self) -> Settings:
        return cast("Settings", check_api_keys(self))

    @model_validator(mode="after")
    def _check_hybrid_retrieval_settings(self) -> Settings:
        return cast("Settings", validate_hybrid_retrieval_settings(self))

    @property
    def resolved_output_dir(self) -> Path:
        """Return the resolved output directory, creating it if needed."""
        return resolve_output_dir(self)

    @property
    def claude_models(self) -> ClaudeModels:
        return build_claude_models(self)


@lru_cache
def _get_base_settings() -> Settings:
    """Return the cached environment-backed settings singleton."""
    return Settings()


_RUNTIME_SETTINGS: ContextVar[Settings | None] = ContextVar(
    "praviar_pipeline_runtime_settings",
    default=None,
)


def get_settings() -> Settings:
    """Return task-local analysis settings, or the cached environment settings.

    Per-analysis overrides must be visible to clients and pipeline stages that
    resolve configuration below the runtime coordinator.  A ``ContextVar``
    keeps concurrent analysis tasks isolated while retaining the historical
    cached-settings behaviour outside a pipeline run.
    """
    runtime_settings = _RUNTIME_SETTINGS.get()
    return runtime_settings if runtime_settings is not None else _get_base_settings()


def clear_settings_cache() -> None:
    """Clear the process-level environment settings cache."""
    _get_base_settings.cache_clear()


@contextmanager
def runtime_settings_context(settings: Settings) -> Iterator[None]:
    """Install validated per-analysis settings for the current async context."""
    token = _RUNTIME_SETTINGS.set(settings)
    try:
        yield
    finally:
        _RUNTIME_SETTINGS.reset(token)
