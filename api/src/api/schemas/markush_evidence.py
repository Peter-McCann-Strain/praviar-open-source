"""Request models for the supervised PATENTSCOPE Markush receipt workflow."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from praviar_pipeline.models.markush_evidence import MarkushEvidenceReceipt
from pydantic import BaseModel, ConfigDict, Field


class MarkushEvidenceImportRequest(BaseModel):
    """Analyst import; actor identity is derived from authentication."""

    model_config = ConfigDict(extra="forbid")

    query_structure: str = Field(min_length=1, max_length=10000)
    target_structure: str = Field(min_length=1, max_length=10000)
    query_role: Literal["target_compound", "murcko_scaffold"]
    chemical_search_mode: Literal["exact", "substructure", "scaffold"]
    markush_method: Literal["enumeration", "formula_matching"]
    markush_match_mode: Literal["exact", "substructure", "fuzzy"]
    wipo_query_field: Literal["ENUM"] | None = None
    family_grouping_enabled: bool
    executed_at: datetime
    artifact_base64: str = Field(min_length=1, max_length=35_000_000)
    artifact_filename: str = Field(min_length=1, max_length=255)
    artifact_media_type: Literal[
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ]
    controls_artifact_base64: str = Field(min_length=1, max_length=35_000_000)
    controls_artifact_filename: str = Field(min_length=1, max_length=255)
    controls_artifact_media_type: Literal["image/png"]
    result_count: int = Field(ge=0, le=1_000_000)
    selected_publication_ids: list[str] = Field(default_factory=list, max_length=10000)
    limitations: list[str] = Field(min_length=1, max_length=50)


class MarkushEvidenceVerifyRequest(BaseModel):
    """Independent reviewer verification of an analyst's draft receipt."""

    model_config = ConfigDict(extra="forbid")

    draft_receipt: MarkushEvidenceReceipt
    query_structure: str = Field(min_length=1, max_length=10000)
    target_structure: str = Field(min_length=1, max_length=10000)
    query_role: Literal["target_compound", "murcko_scaffold"]
    chemical_search_mode: Literal["exact", "substructure", "scaffold"]
    markush_method: Literal["enumeration", "formula_matching"]
    markush_match_mode: Literal["exact", "substructure", "fuzzy"]
    wipo_query_field: Literal["ENUM"] | None = None
    family_grouping_enabled: bool
    executed_at: datetime
    artifact_base64: str = Field(min_length=1, max_length=35_000_000)
    artifact_filename: str = Field(min_length=1, max_length=255)
    artifact_media_type: Literal[
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ]
    controls_artifact_base64: str = Field(min_length=1, max_length=35_000_000)
    controls_artifact_filename: str = Field(min_length=1, max_length=255)
    controls_artifact_media_type: Literal["image/png"]
    result_count: int = Field(ge=0, le=1_000_000)
    selected_publication_ids: list[str] = Field(default_factory=list, max_length=10000)
