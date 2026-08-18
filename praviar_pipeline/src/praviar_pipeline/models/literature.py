"""Non-patent literature models — parallel prior-art branch for invalidity analysis.

Literature references do NOT block FTO (only patents do), but they can invalidate
a blocking patent under §102/§103. A ``LiteratureReference`` is a lightweight,
source-agnostic record that the invalidity step can fold into its prompt context.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LiteratureReference(BaseModel):
    """A single non-patent literature reference (journal article, preprint, etc.)."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["openalex", "semantic_scholar", "pubmed"]
    external_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    publication_year: int | None = None
    venue: str = ""
    doi: str = ""
    abstract: str = ""
    url: str = ""
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
