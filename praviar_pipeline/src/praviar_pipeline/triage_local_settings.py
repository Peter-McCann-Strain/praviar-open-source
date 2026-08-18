"""Settings subset for triage flows that do not require external credentials."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from praviar_pipeline.errors import ConfigurationError
from praviar_pipeline.model_supply_chain import (
    DEFAULT_ML_BOM_PATH,
    require_resolved_drawing_model_supply_chain,
)


class TriageLocalSettings(BaseSettings):
    """Settings for triage paths that can run without LLM credentials."""

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        extra="forbid",
    )

    triage_max_abstract_chars: int = Field(
        default=5000,
        ge=100,
    )
    triage_max_claims_chars: int = Field(
        default=30000,
        ge=100,
    )
    drawing_segmentation_tool: Literal["decimer", "moldet", "chemsam"] = Field(
        default="decimer",
    )
    drawing_analysis_rollout_state: Literal["internal", "shadow", "beta", "production"] = Field(
        default="shadow",
    )
    drawing_analysis_evidence_gate_passed: bool = Field(
        default=False,
    )
    drawing_analysis_ml_bom_path: str = Field(
        default=DEFAULT_ML_BOM_PATH,
    )
    drawing_analysis_jurisdictions: list[str] = Field(
        default_factory=list,
    )
    drawing_ensemble_tools: list[str] = Field(
        default_factory=lambda: ["molscribe", "molsight"],
    )
    drawing_cascade_min_resolved_conf: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
    )
    drawing_analysis_vision_roster_path: str = Field(
        default="",
    )
    drawing_analysis_calibration_artifact_path: str = Field(
        default="",
    )
    drawing_analysis_calibration_artifact_sha256: str = Field(
        default="",
    )
    drawing_analysis_calibration_min_revision: int = Field(
        default=1,
        ge=1,
    )
    drawing_analysis_calibration_revocation_epoch: int = Field(
        default=0,
        ge=0,
    )
    drawing_analysis_revoked_calibration_artifact_ids: tuple[str, ...] = Field(
        default=(),
    )
    drawing_analysis_calibration_public_key: SecretStr = Field(
        default_factory=lambda: SecretStr(""),
    )
    drawing_analysis_calibration_key_id: str = Field(
        default="",
    )
    drawing_analysis_calibration_corpus_sha256: str = Field(
        default="",
    )
    drawing_analysis_container_image_digests: dict[str, str] = Field(
        default_factory=dict,
    )
    triage_drawing_auto_relevant_tanimoto: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
    )
    triage_drawing_auto_relevant_require_substructure: bool = Field(
        default=True,
    )
    triage_drawing_auto_not_relevant_tanimoto: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
    )
    triage_drawing_auto_not_relevant_min_structures: int = Field(
        default=3,
        ge=1,
    )
    triage_drawing_auto_not_relevant_min_confidence: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
    )

    @property
    def drawing_analysis_shadow_mode(self) -> bool:
        return self.drawing_analysis_rollout_state in {"internal", "shadow"}

    @field_validator(
        "drawing_analysis_jurisdictions",
        "drawing_ensemble_tools",
        mode="before",
    )
    @classmethod
    def _parse_drawing_lists(cls, value):
        if value in (None, ""):
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @model_validator(mode="after")
    def _validate_drawing_evidence_gate(self) -> TriageLocalSettings:
        if (
            self.drawing_analysis_rollout_state in {"beta", "production"}
            and not self.drawing_analysis_evidence_gate_passed
        ):
            raise ValueError(
                "drawing_analysis_evidence_gate_passed must be true before "
                "drawing_analysis_rollout_state can be beta or production"
            )
        if (
            self.drawing_analysis_rollout_state in {"beta", "production"}
            and self.drawing_analysis_evidence_gate_passed
        ):
            try:
                require_resolved_drawing_model_supply_chain(
                    self.drawing_analysis_ml_bom_path,
                    segmentation_tool=self.drawing_segmentation_tool,
                )
            except ConfigurationError:
                raise ValueError("Drawing model supply-chain validation failed") from None
        return self


@lru_cache
def get_triage_local_settings() -> TriageLocalSettings:
    """Cached settings for triage logic that can run without the LLM."""
    return TriageLocalSettings()
