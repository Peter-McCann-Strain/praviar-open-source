"""Data models for patent drawing analysis (Step 2.75)."""

from __future__ import annotations

import enum
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from praviar_pipeline.models._base import PatentBase


class DrawingRiskLevel(enum.StrEnum):
    """Risk signal from drawing structure comparison to target compound."""

    HIGH = "high"  # Tanimoto > 0.7 or substructure match
    MEDIUM = "medium"  # Tanimoto 0.3-0.7
    LOW = "low"  # Tanimoto < 0.3
    NONE = "none"  # No valid structure extracted


class OCSRResult(BaseModel):
    """Standardised output from any OCSR subprocess worker."""

    model_config = ConfigDict(extra="forbid")

    smiles: str = ""
    confidence: float = 0.0
    # A numeric zero is the transport sentinel for workers whose upstream
    # model does not emit a calibrated score.  Consumers must never interpret
    # that sentinel as a calibrated low probability.
    confidence_available: bool = True
    valid: bool = False
    tool: str = ""
    latency_ms: int = 0
    error: str = ""
    is_markush: bool = False
    cxsmiles: str = ""
    ocr_words: int = 0
    ocr_time_ms: int = 0
    avg_logprob: float = 0.0
    markush_validation: Literal[
        "not_applicable",
        "passed",
        "failed",
        "reference_required",
    ] = "not_applicable"

    @model_validator(mode="after")
    def _unavailable_confidence_uses_zero_sentinel(self) -> OCSRResult:
        if not self.confidence_available and self.confidence != 0.0:
            raise ValueError("unavailable confidence must use the 0.0 transport sentinel")
        return self


class SegmentationResult(BaseModel):
    """One chemical structure region found by DECIMER Segmentation."""

    model_config = ConfigDict(extra="forbid")

    segment_index: int
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    image_path: str = ""  # Path to cropped segment image
    width: int = 0
    height: int = 0
    confidence: float = 0.0  # Mask R-CNN per-detection score
    latency_ms: int = 0  # First detection on a page carries the page-level timing
    error: str = ""
    # Set when this segment was produced by ``_maybe_split_oversized_segments``;
    # carries the segment_index of the original detector output that was split.
    parent_segment_index: int | None = None


class SubstituentTableRow(BaseModel):
    """One resolved R-group row extracted from a Doc2SAR table."""

    model_config = ConfigDict(extra="forbid")

    row_index: int
    rgroup_labels: dict[str, str] = Field(default_factory=dict)
    resolved_smiles: str = ""
    confidence: float = 0.0


class Doc2SARResult(BaseModel):
    """Strict Doc2SAR worker result for Markush table extraction."""

    model_config = ConfigDict(extra="forbid")

    scaffold_smiles: str
    substituent_table: list[SubstituentTableRow] = Field(default_factory=list)
    enumerated_species: list[str] = Field(default_factory=list)
    confidence: float
    tool: str = "doc2sar"
    latency_ms: int = 0
    error: str = ""
    overflowed: bool = False
    valid: bool = False


class MarkushScopeVerdict(BaseModel):
    """Agent verdict for whether a target falls inside a Markush structure."""

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["in_scope", "out_of_scope", "ambiguous"] = "ambiguous"
    reasoning: str = ""
    enumerated_hits: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    abstained_reason: str = ""
    tool_calls: int = 0
    agent_model: str = ""


class DrawingGovernanceProvenance(BaseModel):
    """Release identities governing customer-visible drawing evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["praviar.drawing-governance.v1"] = "praviar.drawing-governance.v1"
    rollout_state: Literal["internal", "shadow", "beta", "production"]
    influence_permitted: bool
    evidence_gate_passed: bool
    runtime_roster_sha256: str = ""
    ml_bom_sha256: str = ""
    calibration_artifact_id: str = ""
    calibration_artifact_revision: int = 0
    calibration_artifact_sha256: str = ""
    worker_image_digest: str = ""
    jurisdictions: tuple[str, ...] = ()
    verified_at: datetime | None = None

    @model_validator(mode="after")
    def validate_live_provenance(self) -> DrawingGovernanceProvenance:
        if self.influence_permitted:
            if self.rollout_state not in {"beta", "production"}:
                raise ValueError("influential drawing evidence requires a live rollout state")
            if not self.evidence_gate_passed or self.verified_at is None:
                raise ValueError("influential drawing evidence requires a verified gate")
            if self.verified_at.tzinfo is None or self.verified_at.utcoffset() is None:
                raise ValueError("drawing provenance verified_at must be timezone-aware")
            for value in (
                self.runtime_roster_sha256,
                self.ml_bom_sha256,
                self.calibration_artifact_sha256,
            ):
                if re.fullmatch(r"[0-9a-f]{64}", value) is None:
                    raise ValueError("live drawing provenance requires SHA-256 bindings")
            if re.fullmatch(r"sha256:[0-9a-f]{64}", self.worker_image_digest) is None:
                raise ValueError("live drawing provenance requires an immutable worker image")
            if (
                not self.calibration_artifact_id
                or self.calibration_artifact_revision < 1
                or not self.jurisdictions
            ):
                raise ValueError("live drawing calibration provenance is incomplete")
        elif self.rollout_state in {"beta", "production"}:
            raise ValueError("live rollout state cannot claim non-influential evidence")
        return self


class DrawingStructure(BaseModel):
    """A chemical structure extracted from a patent drawing page."""

    model_config = ConfigDict(extra="forbid")

    patent_id: str
    page_number: int
    structure_index: int  # Which structure on the page

    # OCSR extraction
    raw_smiles: str = ""  # Direct OCSR output
    canonical_smiles: str = ""  # After canonicalisation + postprocessing
    inchi_key: str = ""
    confidence: float = 0.0
    extraction_tool: str = ""  # "molscribe", "decimer", "ensemble", "markushgrapher"
    input_image_sha256: str = ""
    source_page_image_sha256: str = ""
    preprocessing_applied: list[str] = Field(default_factory=list)
    postprocessing_applied: list[str] = Field(default_factory=list)

    # Verification layers
    rdkit_valid: bool = False
    pubchem_match: bool = False
    pubchem_cid: int | None = None
    llm_verified: bool | None = None  # None = not yet checked
    llm_verification_model: str = ""
    llm_match_confidence: float = 0.0

    # Comparison to target compound
    tanimoto_to_target: float = 0.0
    is_substructure_of_target: bool = False
    target_is_substructure: bool = False

    # Risk signal
    drawing_risk_signal: DrawingRiskLevel = DrawingRiskLevel.NONE

    # Markush structure info
    is_markush: bool = False
    markush_cxsmiles: str = ""  # CXSMILES from MarkushGrapher
    markush_r_groups: list[str] = Field(default_factory=list)
    markush_target_in_scope: bool | None = None  # None = unknown
    markush_scope_verdict: MarkushScopeVerdict | None = None
    stereo_flag: str = ""
    stereo_cip_count: int = 0
    stereo_ez_count: int = 0
    stereo_target_cip_count: int = 0
    stereo_target_ez_count: int = 0
    stereo_claim_mentions: bool = False
    stereo_details: str = ""

    # Bounding box on original page
    bbox: tuple[int, int, int, int] | None = None  # x1, y1, x2, y2

    # Image paths (relative to output dir)
    original_page_image: str = ""
    cropped_structure_image: str = ""
    rendered_comparison_image: str = ""


class PatentDrawingAnalysis(PatentBase):
    """Complete drawing analysis for a single patent.

    External-boundary model written by Step 2.75 (drawing pipeline).
    Uses ``extra="forbid"`` (inherited from :class:`PatentBase`).
    ``patent_id`` is inherited.
    """

    model_config = ConfigDict(extra="forbid")

    pages_fetched: int = 0
    pages_with_structures: int = 0
    structures_found: int = 0
    structures_valid: int = 0
    structures_pubchem_confirmed: int = 0
    structures_llm_verified: int = 0
    structures_flagged_for_review: int = 0
    structures: list[DrawingStructure] = Field(default_factory=list)
    governance_provenance: DrawingGovernanceProvenance | None = None

    # Aggregate risk
    highest_risk_signal: DrawingRiskLevel = DrawingRiskLevel.NONE
    highest_tanimoto: float = 0.0
    drawing_summary: str = ""  # One-paragraph summary for triage enrichment

    # Figure reference gaps (figures referenced in claims but not fetched)
    figure_reference_gaps: list[str] = Field(default_factory=list)

    # Timing
    fetch_time_s: float = 0.0
    segmentation_time_s: float = 0.0
    ocsr_time_s: float = 0.0
    verification_time_s: float = 0.0
    total_time_s: float = 0.0

    # Cost
    llm_verification_cost_usd: float = 0.0


class DrawingAnalysisResults(BaseModel):
    """Aggregate results across all patents in a pipeline run."""

    model_config = ConfigDict(extra="forbid")

    patent_analyses: list[PatentDrawingAnalysis] = Field(default_factory=list)
    total_patents_with_images: int = 0
    total_structures_extracted: int = 0
    total_high_risk_structures: int = 0
    total_cost_usd: float = 0.0
    total_time_s: float = 0.0


class DrawingEvidenceStore:
    """O(1) lookup for drawing analysis results, keyed by patent_id.

    Built from DrawingAnalysisResults after Step 2.75 completes.
    Consumed by steps 3 (triage), 4 (analysis), 5 (DoE), 6 (invalidity),
    and 8 (report) to inject structural evidence into LLM prompts and reports.
    """

    def __init__(self, results: DrawingAnalysisResults | None = None) -> None:
        self._by_patent: dict[str, PatentDrawingAnalysis] = {}
        if results:
            for pa in results.patent_analyses:
                self._by_patent[pa.patent_id] = pa

    def get(self, patent_id: str) -> PatentDrawingAnalysis | None:
        return self._by_patent.get(patent_id)

    def has_structures(self, patent_id: str) -> bool:
        pa = self._by_patent.get(patent_id)
        return pa is not None and pa.structures_found > 0

    def get_structures(
        self, patent_id: str, *, min_tanimoto: float = 0.0
    ) -> list[DrawingStructure]:
        pa = self._by_patent.get(patent_id)
        if not pa:
            return []
        return [s for s in pa.structures if s.tanimoto_to_target >= min_tanimoto and s.rdkit_valid]

    def get_highest_tanimoto(self, patent_id: str) -> float:
        pa = self._by_patent.get(patent_id)
        return pa.highest_tanimoto if pa else 0.0

    def get_risk_signal(self, patent_id: str) -> DrawingRiskLevel:
        pa = self._by_patent.get(patent_id)
        return pa.highest_risk_signal if pa else DrawingRiskLevel.NONE

    def has_substructure_match(self, patent_id: str) -> bool:
        return any(
            s.is_substructure_of_target or s.target_is_substructure
            for s in self.get_structures(patent_id)
        )

    def brief_summary(self, patent_id: str) -> str:
        """One-line summary for triage prompts."""
        pa = self._by_patent.get(patent_id)
        if not pa or pa.structures_found == 0:
            return ""
        sub = " (substructure match)" if self.has_substructure_match(patent_id) else ""
        return (
            f"DRAWING EVIDENCE: {pa.structures_found} structures extracted, "
            f"highest Tanimoto {pa.highest_tanimoto:.2f} "
            f"({pa.highest_risk_signal.value.upper()} risk){sub}"
        )

    def summary_for_prompt(
        self,
        patent_id: str,
        *,
        max_structures: int = 10,
        min_tanimoto: float = 0.3,
    ) -> str:
        """Formatted text block for claim analysis / DoE / invalidity prompts."""
        pa = self._by_patent.get(patent_id)
        if not pa or pa.structures_found == 0:
            return ""

        relevant = self.get_structures(patent_id, min_tanimoto=min_tanimoto)
        if not relevant:
            return (
                f"DRAWING EVIDENCE: {pa.structures_found} structures extracted "
                f"from patent drawings. None above Tanimoto {min_tanimoto:.1f} "
                f"to target (max: {pa.highest_tanimoto:.2f})."
            )

        lines = [
            "--- CHEMICAL STRUCTURES FROM PATENT DRAWINGS ---",
            f"{pa.structures_found} total structures extracted. "
            f"Showing {min(len(relevant), max_structures)} most relevant:",
            "",
        ]
        for i, s in enumerate(relevant[:max_structures], 1):
            sub_info = ""
            if s.is_substructure_of_target:
                sub_info = " | target is substructure of this compound"
            elif s.target_is_substructure:
                sub_info = " | this compound is substructure of target"

            lines.append(
                f"{i}. Page {s.page_number}: {s.canonical_smiles}\n"
                f"   Tanimoto: {s.tanimoto_to_target:.3f} | "
                f"Confidence: {s.confidence:.2f} | "
                f"Tool: {s.extraction_tool} | "
                f"Risk: {s.drawing_risk_signal.value.upper()}{sub_info}"
            )
            lines.append("")

        remaining = pa.structures_found - len(relevant)
        if remaining > 0:
            lines.append(
                f"({remaining} additional structures below "
                f"Tanimoto {min_tanimoto:.1f} threshold omitted)"
            )

        lines.append("--- END DRAWING STRUCTURES ---")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize for checkpoint storage."""
        return {pid: pa.model_dump() for pid, pa in self._by_patent.items()}

    @classmethod
    def from_dict(cls, data: dict) -> DrawingEvidenceStore:
        """Restore from checkpoint data."""
        store = cls()
        for pid, pa_dict in data.items():
            store._by_patent[pid] = PatentDrawingAnalysis.model_validate(pa_dict)
        return store

    @property
    def patent_ids(self) -> list[str]:
        return list(self._by_patent.keys())

    def __len__(self) -> int:
        return len(self._by_patent)

    def __contains__(self, patent_id: str) -> bool:
        return patent_id in self._by_patent
