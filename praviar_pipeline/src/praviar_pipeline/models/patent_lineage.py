"""Support models for patent lineage, family, and event records."""

from __future__ import annotations

import enum
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PatentSource(enum.StrEnum):
    """Which API found this patent."""

    BIGQUERY = "bigquery"
    BIGQUERY_TRANSLATED = "bigquery_translated"
    SURECHEMBL = "surechembl"
    PUBCHEM = "pubchem"
    PUBCHEM_GENUS = "pubchem_genus"
    PATCID = "patcid"
    INPADOC = "inpadoc"
    CPC_SEARCH = "cpc_search"
    ASSIGNEE_SEARCH = "assignee_search"
    EPO_SEARCH = "epo_search"
    LENS = "lens"
    KIPRIS = "kipris"
    PATENTSCOPE = "patentscope"
    PATENTSVIEW = "patentsview"
    NCBI_PATENT_SEQUENCE = "ncbi_patent_sequence"
    SYNTHETIC_FIXTURE = "synthetic_fixture"


class LegalStatus(enum.StrEnum):
    """Simplified patent legal status."""

    ACTIVE = "active"
    EXPIRED = "expired"
    LAPSED = "lapsed"
    REVOKED = "revoked"
    PENDING = "pending"
    UNKNOWN = "unknown"


class LegalEvent(BaseModel):
    """A single legal status event from INPADOC."""

    model_config = ConfigDict(extra="forbid")

    event_date: date | None = None
    event_code: str = ""
    event_description: str = ""
    country: str = ""


class PatentFamilyMember(BaseModel):
    """A member of a DOCDB patent family."""

    model_config = ConfigDict(extra="forbid")

    country: str = ""
    doc_number: str
    kind: str = ""
    application_number: str = ""
    application_identity_verified: bool = False
    application_identity_source: str = ""

    @model_validator(mode="after")
    def _validate_application_identity(self) -> PatentFamilyMember:
        if self.application_identity_verified and (
            not self.application_number or not self.application_identity_source
        ):
            raise ValueError("verified family application identity requires a number and source")
        return self


class PatentFamily(BaseModel):
    """DOCDB patent family grouping related patents across jurisdictions."""

    model_config = ConfigDict(extra="forbid")

    family_id: str = ""
    members: list[PatentFamilyMember] = Field(default_factory=list)

    @property
    def jurisdictions(self) -> list[str]:
        """Unique country codes in the family."""
        return sorted({member.country for member in self.members if member.country})


class AssignmentRecord(BaseModel):
    """A patent ownership assignment/transfer."""

    model_config = ConfigDict(extra="forbid")

    assignor: str = ""
    assignee: str = ""
    conveyance: str = ""
    recorded_date: date | None = None
    reel_frame: str = ""


class ForeignPriorityClaim(BaseModel):
    """A foreign priority claim under the Paris Convention."""

    model_config = ConfigDict(extra="forbid")

    country: str = ""
    application_number: str = ""
    priority_date: date | None = None


class TransactionEvent(BaseModel):
    """A prosecution transaction/event from the USPTO event log."""

    model_config = ConfigDict(extra="forbid")

    event_code: str = ""
    event_description: str = ""
    event_date: date | None = None


class PTABProceeding(BaseModel):
    """A PTAB post-grant proceeding (IPR/PGR/CBM) for a patent."""

    model_config = ConfigDict(extra="forbid")

    proceeding_number: str = ""
    proceeding_type: str = Field(default="", description="IPR, PGR, or CBM")
    filing_date: date | None = None
    institution_date: date | None = None
    status: str = Field(
        default="", description="e.g. Instituted, FWD Coverage, Settled, Terminated"
    )
    petitioner: str = ""
    outcome: str = Field(default="", description="e.g. claims_cancelled, claims_survived, settled")
    claims_challenged: list[int] = Field(default_factory=list)
    claims_cancelled: list[int] = Field(default_factory=list)
