"""Typed contract for the post-resolution compound identity checkpoint."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from praviar_pipeline.models.compound import (
    DerivedStructureCandidate,
    TautomerEnumerationRecord,
)

IdentitySource = Literal[
    "pubchem",
    "fda_purple_book",
    "pubchem_and_fda_purple_book",
    "fda_gsrs",
    "pubchem_and_fda_gsrs",
]
IdentityVariant = Literal[
    "salt_or_product_form",
    "stereochemistry",
    "tautomer",
    "prodrug",
]
IdentityVariantStatus = Literal[
    "declared",
    "derived_search_form",
    "no_distinct_form",
    "candidate_detected",
    "not_detected",
    "not_modeled",
    "not_applicable",
    "unavailable",
]


class IdentityComparison(BaseModel):
    """How the submitted identifier relates to the resolved identity."""

    model_config = ConfigDict(extra="forbid")

    outcome: Literal[
        "exact_match",
        "normalized_match",
        "resolved_from_identifier",
        "different",
        "not_comparable",
    ]
    submitted_value: str
    resolved_value: str
    detail: str
    requires_attention: bool = False


class ResolvedIdentityRecord(BaseModel):
    """Authoritative identifiers returned by the configured resolution source."""

    model_config = ConfigDict(extra="forbid")

    name: str
    compound_type: str
    identity_source: IdentitySource
    source_authority: str
    source_record_id: str
    canonical_smiles: str = ""
    inchi: str = ""
    inchi_key: str = ""
    molecular_formula: str = ""
    molecular_weight: float | None = None
    cas_numbers: list[str] = Field(default_factory=list)
    bla_number: str = ""
    reference_product: str = ""
    unii: str = ""
    gsrs_uuid: str = ""
    gsrs_substance_class: str = ""
    gsrs_definition_type: str = ""
    gsrs_definition_level: str = ""
    gsrs_record_version: str = ""
    gsrs_names_last_updated: str = ""
    gsrs_record_last_updated: str = ""
    authoritative_record_present: bool


class IdentitySearchLane(BaseModel):
    """One exact identifier or structure lane in the downstream search envelope."""

    model_config = ConfigDict(extra="forbid")

    lane_id: str
    label: str
    values: list[str] = Field(default_factory=list)
    total_value_count: int = Field(default=0, ge=0)
    sources: list[str] = Field(default_factory=list)
    enabled: bool
    derived: bool = False
    differs_from_canonical: bool = False
    purpose: str


class IdentityVariantAssessment(BaseModel):
    """The explicit treatment and limitation for one identity-variant family."""

    model_config = ConfigDict(extra="forbid")

    variant: IdentityVariant
    label: str
    status: IdentityVariantStatus
    declared_value: str = ""
    derived_value: str = ""
    search_effect: str
    limitation: str
    requires_attention: bool = False


class IdentityDerivationEvidence(BaseModel):
    """Full derivation receipt fingerprinted into the review decision."""

    model_config = ConfigDict(extra="forbid")

    tautomer_enumeration: TautomerEnumerationRecord | None = None
    prodrug_candidates: list[DerivedStructureCandidate] = Field(default_factory=list)
    unsupported_prodrug_motifs: list[str] = Field(default_factory=list)


class IdentityReviewContext(BaseModel):
    """Complete review packet shown before any query expansion or patent search."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["identity-review/v2"] = "identity-review/v2"
    checkpoint_id: str
    identity_fingerprint: str
    original_input: str
    input_type: str
    comparison: IdentityComparison
    resolved_identity: ResolvedIdentityRecord
    search_envelope: list[IdentitySearchLane]
    variant_assessments: list[IdentityVariantAssessment]
    derivation_evidence: IdentityDerivationEvidence
    enabled_search_sources: list[str]
    product_form_declaration: str = ""
    approval_attestation: str
    downstream_state: Literal["search_blocked_pending_identity_approval"] = (
        "search_blocked_pending_identity_approval"
    )
