"""Common report metadata and summary models."""

from __future__ import annotations

import enum
import importlib.metadata

from pydantic import BaseModel, ConfigDict, Field

from praviar_pipeline.models.analysis import RiskLevel

REPORT_DISCLAIMER = (
    "IMPORTANT: This report is an AI-assisted screening tool and does NOT constitute "
    "legal advice or a formal Freedom-to-Operate opinion. Patent claim interpretation "
    "requires human judgment that AI cannot replicate. Key limitations:\n"
    "- Markush structure coverage may be incomplete\n"
    "- Claim construction has not been performed by a patent attorney\n"
    "- Prosecution history estoppel analysis is preliminary\n"
    "- Prior art search is not exhaustive\n"
    "- Patent term calculations may not reflect all PTA/PTE/TD adjustments\n"
    "- Confidence bands reflect evidence availability, not legal outcome probability\n\n"
    "A qualified patent attorney should review all findings before making "
    "commercial decisions. This tool is designed to accelerate the initial "
    "screening phase, not replace professional patent analysis."
)


def _get_version() -> str:
    try:
        return importlib.metadata.version("praviar_pipeline")
    except importlib.metadata.PackageNotFoundError:
        return "0.1.0-dev"


class SourceStatus(enum.StrEnum):
    """Outcome of querying a single data source."""

    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_CONFIGURED = "not_configured"


class SourceHealthEntry(BaseModel):
    """Health record for one data source."""

    model_config = ConfigDict(extra="forbid")

    source: str
    status: SourceStatus
    patent_count: int = 0
    attempted_count: int = 0
    covered_count: int = 0
    error_message: str = ""


class SourceHealth(BaseModel):
    """Aggregated health of all search sources used in a pipeline run."""

    model_config = ConfigDict(extra="forbid")

    entries: list[SourceHealthEntry] = Field(default_factory=list)

    @property
    def any_failed(self) -> bool:
        return any(
            entry.status in {SourceStatus.FAILED, SourceStatus.NOT_CONFIGURED}
            for entry in self.entries
        )

    @property
    def all_failed(self) -> bool:
        queried = [entry for entry in self.entries if entry.status != SourceStatus.SKIPPED]
        return len(queried) > 0 and all(
            entry.status in {SourceStatus.FAILED, SourceStatus.NOT_CONFIGURED} for entry in queried
        )

    @property
    def primary_succeeded(self) -> bool:
        for entry in self.entries:
            if entry.source == "pubchem_sdq":
                return entry.status == SourceStatus.OK
        return False

    @property
    def failed_sources(self) -> list[str]:
        return [
            entry.source
            for entry in self.entries
            if entry.status in {SourceStatus.FAILED, SourceStatus.NOT_CONFIGURED}
        ]


class AnalysisFailure(BaseModel):
    """Record of a patent that failed during analysis (Step 4/5/6)."""

    model_config = ConfigDict(extra="forbid")

    patent_id: str
    step: str = Field(description="Pipeline step where failure occurred")
    error_type: str = Field(description="Exception class name")
    error_message: str
    recoverable: bool = Field(
        default=False,
        description="Whether the failure was due to a transient error",
    )


class DataLimitation(BaseModel):
    """A known limitation in the pipeline's data coverage."""

    model_config = ConfigDict(extra="forbid")

    category: str = Field(description="e.g. source_unavailable, enrichment_gap")
    description: str
    impact: str = Field(description="How this affects the report's reliability")


class ActionType(enum.StrEnum):
    """Types of recommended next steps."""

    LICENSE = "license"
    DESIGN_AROUND = "design_around"
    CHALLENGE_IPR = "challenge_ipr"
    MONITOR = "monitor"
    ACCEPT_RISK = "accept_risk"
    HALT = "halt"


class ActionPriority(enum.StrEnum):
    """Priority level for action items."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ActionItem(BaseModel):
    """A recommended next step derived from analysis results."""

    model_config = ConfigDict(extra="forbid")

    action_type: ActionType
    priority: ActionPriority
    description: str
    patent_ids: list[str] = Field(default_factory=list)
    reasoning: str = ""
    estimated_timeline: str = ""


class RiskSummary(BaseModel):
    """Executive risk summary for the compound."""

    model_config = ConfigDict(extra="forbid")

    overall_risk: RiskLevel
    blocking_patents_count: int = 0
    total_patents_analyzed: int = 0
    key_risks: list[str] = Field(default_factory=list)
    executive_summary: str = Field(description="2-3 paragraph summary for attorneys")
    summary_validation_issues: list[str] = Field(default_factory=list)
