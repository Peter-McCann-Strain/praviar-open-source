"""Matter-graph models for the evidence fabric."""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field


class MatterNodeType(enum.StrEnum):
    """Canonical node types for the matter graph."""

    COMPOUND_VARIANT = "compound_variant"
    PATENT = "patent"
    APPLICATION = "application"
    FAMILY = "family"
    CLAIM = "claim"
    AMENDMENT = "amendment"
    OFFICE_ACTION = "office_action"
    PTAB_MATTER = "ptab_matter"
    EP_REGISTER_EVENT = "ep_register_event"
    ORANGE_BOOK_ENTRY = "orange_book_entry"
    PURPLE_BOOK_ENTRY = "purple_book_entry"
    PRIOR_ART_REFERENCE = "prior_art_reference"
    COMMERCIAL_PRODUCT = "commercial_product"


class MatterEdgeType(enum.StrEnum):
    """Canonical edge types for the matter graph."""

    ROOTS = "roots"
    BELONGS_TO_FAMILY = "belongs_to_family"
    PROSECUTED_AS = "prosecuted_as"
    CONTAINS_CLAIM = "contains_claim"
    AMENDED_BY = "amended_by"
    CHALLENGED_BY = "challenged_by"
    LISTED_IN = "listed_in"
    TRACKED_BY = "tracked_by"


class MatterNode(BaseModel):
    """A node in the per-run matter graph."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    node_type: MatterNodeType
    label: str
    jurisdiction: str = ""
    patent_id: str = ""
    family_id: str = ""
    application_number: str = ""


class MatterEdge(BaseModel):
    """A directional link in the per-run matter graph."""

    model_config = ConfigDict(extra="forbid")

    edge_type: MatterEdgeType
    from_node_id: str
    to_node_id: str
    summary: str = ""


class MatterGraph(BaseModel):
    """Canonical graph of patents, families, claims, and record links."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[MatterNode] = Field(default_factory=list)
    edges: list[MatterEdge] = Field(default_factory=list)


class MatterGraphSummary(BaseModel):
    """Compact summary of the runtime matter graph."""

    model_config = ConfigDict(extra="forbid")

    root_compound: str = ""
    node_count: int = 0
    edge_count: int = 0
    node_counts_by_type: dict[str, int] = Field(default_factory=dict)
    edge_counts_by_type: dict[str, int] = Field(default_factory=dict)
    patent_node_ids: list[str] = Field(default_factory=list)
    family_node_ids: list[str] = Field(default_factory=list)
