"""Regulatory exclusivity models for the FTO report.

Captures Purple Book (biologics), Patent Term Extension (PTE), and
Paragraph IV challenge data assembled during the regulatory enrichment step.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from praviar_pipeline.clients.paragraph_iv import ParagraphIVEntry
from praviar_pipeline.clients.purple_book import PurpleBookEntry
from praviar_pipeline.models.report_common import SourceHealthEntry


class PTEEntry(BaseModel):
    """A single USPTO Patent Term Extension certificate record."""

    model_config = ConfigDict(extra="forbid")

    patent_number: str
    product_name: str = ""
    nda_bla_number: str = ""
    extension_days: str = ""
    status: str = ""


class RegulatoryExclusivity(BaseModel):
    """Regulatory exclusivity data assembled from pharma regulatory sources."""

    model_config = ConfigDict(extra="forbid")

    purple_book_entry: PurpleBookEntry | None = Field(
        default=None,
        description="Matched Purple Book entry for biologic products",
    )
    bpcia_exclusivity_expiry: date | None = Field(
        default=None,
        description="BPCIA 12-year reference product exclusivity expiry derived from Purple Book",
    )
    pte_extensions: list[PTEEntry] = Field(
        default_factory=list,
        description="USPTO PTE certificates associated with this drug's patents",
    )
    pte_source_url: str = Field(
        default="",
        description="Authoritative USPTO issued-certificate workbook used for PTE coverage",
    )
    pte_source_scope: str = Field(
        default="",
        description="Explicit population covered by the queried PTE dataset",
    )
    pte_source_coverage_note: str = Field(
        default="",
        description="Publisher limitations on the PTE dataset's legal and temporal coverage",
    )
    pte_source_retrieved_at: datetime | None = Field(
        default=None,
        description="UTC instant at which the PTE dataset was retrieved",
    )
    pte_source_publisher_last_modified: str = Field(
        default="",
        description="Publisher Last-Modified response header when supplied",
    )
    paragraph_iv_challenges: list[ParagraphIVEntry] = Field(
        default_factory=list,
        description="Active Paragraph IV ANDA certifications for this product",
    )
    data_sources_queried: list[str] = Field(
        default_factory=list,
        description="Names of regulatory sources that were actually queried",
    )
    source_statuses: list[SourceHealthEntry] = Field(
        default_factory=list,
        description=(
            "Per-source regulatory enrichment status so empty result sets cannot "
            "hide source failures or non-configuration."
        ),
    )
