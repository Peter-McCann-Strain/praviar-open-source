"""Human-in-the-loop checkpoint models."""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CheckpointType(enum.StrEnum):
    """Types of HITL checkpoints in the pipeline."""

    IDENTITY_REVIEW = "identity_review"  # CP0: After resolution, before any search expansion
    SEARCH_REVIEW = "search_review"  # CP1: After search, before triage
    TRIAGE_REVIEW = "triage_review"  # CP2: After triage, before analysis
    ANALYSIS_REVIEW = "analysis_review"  # CP2.5: After analysis, before DoE
    REPORT_REVIEW = "report_review"  # CP3: After report draft, before finalization


class CheckpointDecision(BaseModel):
    """Decision made by a human reviewer at a checkpoint."""

    model_config = ConfigDict(extra="forbid")

    checkpoint_type: CheckpointType
    action: str = Field(
        description="Decision: 'approve', 'reject', or 'modify'",
    )
    modifications: dict = Field(
        default_factory=dict,
        description="Modifications to apply (patent additions, triage overrides, etc.)",
    )
    reviewer_id: str = ""
    reviewed_at: datetime | None = None
    notes: str = ""


class HITLConfig(BaseModel):
    """Configuration for human-in-the-loop checkpoints."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    checkpoints: list[CheckpointType] = Field(
        default_factory=list,
        description="Which checkpoints are active in this pipeline run",
    )
    auto_skip_timeout_minutes: int = Field(
        default=60,
        ge=1,
        description="Auto-proceed after this many minutes without human response",
    )
    confidence_gate_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="CP2 confidence gate: only pause if avg confidence below this",
    )
