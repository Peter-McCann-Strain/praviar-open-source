"""Drawing analysis response models for the FTO report API surface.

These mirror :class:`praviar_pipeline.models.drawing.DrawingStructure` and
:class:`praviar_pipeline.models.drawing.PatentDrawingAnalysis` so that the
``GET /reports/{analysis_id}`` endpoint can surface chemical structures
extracted from patent drawings — including Markush placeholders and the
CXSMILES emitted by MarkushGrapher — to the web UI without silent
field stripping at the response_model boundary.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DrawingRiskLevelLiteral = Literal["high", "medium", "low", "none"]


class DrawingGovernanceProvenanceResponse(BaseModel):
    """Verified control-plane identities for drawing-derived evidence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["praviar.drawing-governance.v1"]
    rollout_state: Literal["internal", "shadow", "beta", "production"]
    influence_permitted: bool
    evidence_gate_passed: bool
    runtime_roster_sha256: str = ""
    ml_bom_sha256: str = ""
    calibration_artifact_id: str = ""
    calibration_artifact_revision: int = 0
    calibration_artifact_sha256: str = ""
    worker_image_digest: str = ""
    jurisdictions: list[str] = Field(default_factory=list)
    verified_at: datetime | None = None


class DrawingStructureResponse(BaseModel):
    """A chemical structure extracted from a patent drawing page.

    Mirrors :class:`praviar_pipeline.models.drawing.DrawingStructure`. Only the
    user-facing fields needed for report rendering and the Markush UX
    (badge, R-group display, CXSMILES code block) are explicitly typed.
    Unknown drawing payload fields are deliberately preserved at this
    response boundary so newer pipeline metadata is not silently stripped
    before the web client can render or inspect it.
    """

    model_config = ConfigDict(extra="allow")

    patent_id: str = Field(description="Patent ID this structure was extracted from.")
    page_number: int = Field(default=0, description="Page number on the patent PDF.")
    structure_index: int = Field(
        default=0, description="Zero-based index of the structure on the page."
    )

    # OCSR extraction
    canonical_smiles: str = Field(
        default="",
        description="Canonicalised SMILES after RDKit + post-processing. Empty for Markush.",
    )
    inchi_key: str = Field(default="", description="InChI key, when computable.")
    confidence: float = Field(
        default=0.0, description="OCSR tool confidence in the extracted structure."
    )
    extraction_tool: str = Field(
        default="",
        description=(
            "OCSR tool that produced the structure: molscribe, decimer, ensemble, "
            "or markushgrapher."
        ),
    )
    input_image_sha256: str = Field(
        default="",
        description="SHA-256 of the exact cropped image supplied to OCSR.",
    )
    source_page_image_sha256: str = Field(
        default="",
        description="SHA-256 of the rendered source patent page image.",
    )

    # Verification
    rdkit_valid: bool = Field(default=False, description="Whether RDKit parsed the SMILES.")
    pubchem_match: bool = Field(default=False, description="Whether PubChem returned a CID match.")
    pubchem_cid: int | None = Field(default=None, description="PubChem CID if matched.")

    # Comparison to target compound
    tanimoto_to_target: float = Field(
        default=0.0, description="Tanimoto similarity to the target compound (0–1)."
    )
    is_substructure_of_target: bool = Field(
        default=False, description="Drawing structure is a substructure of the target."
    )
    target_is_substructure: bool = Field(
        default=False, description="Target is a substructure of the drawing structure."
    )

    # Risk signal
    drawing_risk_signal: DrawingRiskLevelLiteral = Field(
        default="none",
        description="Risk signal derived from Tanimoto / substructure comparison.",
    )

    # Markush structure info — the fields this whole module exists to surface
    is_markush: bool = Field(
        default=False,
        description=(
            "True when the extracted structure is a Markush template containing "
            "R-group placeholders rather than a fully specified molecule."
        ),
    )
    markush_cxsmiles: str | None = Field(
        default=None,
        description=(
            "Extended-SMILES (CXSMILES) emitted by MarkushGrapher for Markush "
            "structures. Carries the variable R-group annotations that "
            "canonical_smiles cannot represent. Null/empty for non-Markush."
        ),
    )
    markush_r_groups: list[str] = Field(
        default_factory=list,
        description="Names of R-groups defined in the Markush structure (e.g. ['R1', 'R2']).",
    )
    markush_target_in_scope: bool | None = Field(
        default=None,
        description=(
            "Whether the target compound falls within the Markush scope. Null when undetermined."
        ),
    )

    # Image paths (relative to the report output directory)
    cropped_structure_image: str = Field(
        default="", description="Relative path to the cropped structure image."
    )
    rendered_comparison_image: str = Field(
        default="",
        description="Relative path to the side-by-side rendered comparison image.",
    )


class PatentDrawingAnalysisResponse(BaseModel):
    """Per-patent drawing analysis aggregate.

    Mirrors :class:`praviar_pipeline.models.drawing.PatentDrawingAnalysis`.
    """

    model_config = ConfigDict(extra="allow")

    patent_id: str = Field(description="Patent ID covered by this drawing analysis.")
    pages_fetched: int = Field(default=0, description="Number of drawing pages fetched.")
    pages_with_structures: int = Field(
        default=0, description="Number of pages containing chemical structures."
    )
    structures_found: int = Field(default=0, description="Total structures extracted.")
    structures_valid: int = Field(default=0, description="Structures with valid RDKit parses.")
    structures: list[DrawingStructureResponse] = Field(
        default_factory=list,
        description="Per-structure extraction details, including Markush metadata.",
    )
    governance_provenance: DrawingGovernanceProvenanceResponse | None = Field(
        default=None,
        description="Runtime governance bound to this drawing analysis.",
    )

    highest_risk_signal: DrawingRiskLevelLiteral = Field(
        default="none",
        description="Highest risk signal across all structures on this patent.",
    )
    highest_tanimoto: float = Field(
        default=0.0, description="Highest Tanimoto similarity observed for this patent."
    )
    drawing_summary: str = Field(
        default="",
        description="One-paragraph triage summary describing the structures found.",
    )


__all__ = [
    "DrawingRiskLevelLiteral",
    "DrawingGovernanceProvenanceResponse",
    "DrawingStructureResponse",
    "PatentDrawingAnalysisResponse",
]
