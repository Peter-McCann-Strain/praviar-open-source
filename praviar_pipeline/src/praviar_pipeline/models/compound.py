"""Compound resolution models — output of Step 1."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StructureIntegrityCheck(BaseModel):
    """Machine-checkable properties attached to a derived structure."""

    model_config = ConfigDict(extra="forbid")

    molecular_formula: str
    exact_mass: float = Field(ge=0.0)
    heavy_atom_count: int = Field(ge=1)
    atom_count: int = Field(ge=1)
    formal_charge: int
    fragment_count: int = Field(ge=1)
    radical_electrons: int = Field(ge=0)
    retained_heavy_atom_fraction: float = Field(default=1.0, ge=0.0, le=1.0)
    passed: bool
    checks: list[str] = Field(default_factory=list)


class DerivedStructureCandidate(BaseModel):
    """A bounded, provenance-bearing structure search candidate."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=16, max_length=64)
    kind: Literal["tautomer", "prodrug_parent_hypothesis"]
    label: str
    source_smiles: str
    canonical_smiles: str
    rule_id: str
    rule_version: str
    engine: str
    engine_version: str
    transform_smarts: str = ""
    hypothesis: bool
    search_eligible: bool
    exclusion_reason: str = ""
    integrity: StructureIntegrityCheck
    evidence_references: list[str] = Field(default_factory=list)
    limitation: str


class TautomerEnumerationRecord(BaseModel):
    """Deterministic RDKit tautomer-enumeration receipt."""

    model_config = ConfigDict(extra="forbid")

    source_smiles: str
    source_form: Literal["canonical", "salt_stripped_largest_fragment"]
    engine: Literal["RDKit MolStandardize TautomerEnumerator"]
    engine_version: str
    score_version: str
    max_tautomers: int = Field(ge=1)
    max_transforms: int = Field(ge=1)
    status: Literal[
        "completed",
        "max_tautomers_reached",
        "max_transforms_reached",
        "parse_failed",
        "enumeration_failed",
        "not_applicable",
    ]
    enumerated_count: int = Field(ge=0)
    canonical_tautomer_smiles: str = ""
    candidates: list[DerivedStructureCandidate] = Field(default_factory=list)
    search_expansion_allowed: bool
    limitation: str


class RelatedCompound(BaseModel):
    """A structurally similar compound found via similarity search."""

    model_config = ConfigDict(extra="forbid")

    cid: int
    name: str = ""
    canonical_smiles: str
    tanimoto_similarity: float = Field(ge=0.0, le=1.0)


class ResolvedCompound(BaseModel):
    """Fully resolved compound identity — the foundation for all downstream steps."""

    model_config = ConfigDict(extra="forbid")

    # Core identifiers
    name: str
    canonical_smiles: str = Field(default="", min_length=0)
    inchi: str = ""
    inchi_key: str = ""
    pubchem_cid: int | None = Field(default=None, ge=1)

    # Synonyms and alternate IDs
    synonyms: list[str] = Field(default_factory=list)
    cas_numbers: list[str] = Field(default_factory=list)

    # Molecular properties
    molecular_formula: str = ""
    molecular_weight: float | None = None

    # Fingerprints (hex-encoded for serialization)
    morgan_fp: str = Field(default="", description="Morgan/ECFP4 fingerprint, hex-encoded")
    maccs_keys: str = Field(default="", description="MACCS keys fingerprint, hex-encoded")

    # Structural features
    functional_groups: list[str] = Field(default_factory=list)

    # Scaffold and salt coverage — populated by Step 1 to broaden patent searches
    scaffold_smiles: str = Field(
        default="",
        description=(
            "Murcko scaffold SMILES stripped of side chains. "
            "Used to broaden searches to Markush/genus claims covering the core ring system."
        ),
    )
    free_base_smiles: str = Field(
        default="",
        description=(
            "Canonical SMILES after salt/counter-ion removal (e.g. HCl, Na, K stripped). "
            "Used to search for patents on the pharmacologically active free base "
            "rather than a specific salt form."
        ),
    )
    stereo_stripped_smiles: str = Field(
        default="",
        description=(
            "Canonical SMILES with all stereocentres and geometric isomerism removed. "
            "Used to search for patents covering the racemate when the query compound "
            "is a single enantiomer/diastereomer."
        ),
    )
    prodrug_pattern: str | None = Field(
        default=None,
        description=(
            "Short label when the input SMILES matches a supported prodrug-candidate motif "
            "(e.g. 'ester_prodrug', 'phosphate_prodrug'). "
            "It does not establish prodrug status; only validated, reviewer-approved "
            "candidate structures can extend search."
        ),
    )
    tautomer_enumeration: TautomerEnumerationRecord | None = Field(
        default=None,
        description=(
            "Bounded RDKit tautomer-enumeration receipt. Alternate candidates never "
            "replace the resolved canonical identity."
        ),
    )
    prodrug_candidates: list[DerivedStructureCandidate] = Field(
        default_factory=list,
        description=(
            "Conservative deprotection/hydrolysis hypotheses approved only as additional "
            "structure-search lanes; never substituted for the resolved identity."
        ),
    )
    unsupported_prodrug_motifs: list[str] = Field(
        default_factory=list,
        description=(
            "Detected motifs for which no defensible one-step parent structure is generated."
        ),
    )

    # Related compounds from similarity search
    related_compounds: list[RelatedCompound] = Field(default_factory=list)

    # Input metadata
    original_input: str = Field(description="What the user originally typed")
    input_type: Literal["name", "smiles", "cas", "inchi", "inchikey"] = Field(
        description="Detected input type",
    )

    # Compound type classification
    compound_type: Literal["small_molecule", "biologic", "peptide"] = Field(
        default="small_molecule",
        description="Compound classification: small_molecule, biologic, or peptide",
    )

    # Biologic-specific fields (populated via Purple Book)
    bla_number: str = Field(default="", description="BLA number from FDA Purple Book")
    reference_product: str = Field(default="", description="Reference biologic product name")
    biosimilar_count: int = Field(default=0, ge=0, description="Number of approved biosimilars")
    unii: str = Field(default="", description="FDA GSRS Unique Ingredient Identifier")
    gsrs_uuid: str = Field(default="", description="FDA GSRS substance-record UUID")
    gsrs_substance_class: str = Field(default="", description="FDA GSRS substance class")
    gsrs_definition_type: str = Field(default="", description="FDA GSRS definition type")
    gsrs_definition_level: str = Field(default="", description="FDA GSRS definition level")
    gsrs_record_version: str = Field(default="", description="FDA GSRS record version")
    gsrs_names_last_updated: str = Field(
        default="",
        description="openFDA UNII name-index update date returned with the exact-name lookup",
    )
    gsrs_record_last_updated: str = Field(
        default="",
        description="openFDA substance-record dataset update date",
    )
    protein_subunit_sequences: list[str] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "Public, complete L-amino-acid subunit sequences bound to the exact FDA "
            "GSRS identity and eligible for patent-sequence retrieval."
        ),
    )

    @field_validator("protein_subunit_sequences")
    @classmethod
    def _validate_protein_subunit_sequences(cls, values: list[str]) -> list[str]:
        allowed = frozenset("ACDEFGHIKLMNPQRSTVWYBXZJUO")
        deduplicated = list(dict.fromkeys(values))
        if any(
            not value
            or len(value) > 10000
            or value != value.upper()
            or not set(value).issubset(allowed)
            for value in deduplicated
        ):
            raise ValueError("protein subunit sequence is not a supported L-amino-acid string")
        return deduplicated

    @field_validator("inchi_key", mode="before")
    @classmethod
    def _validate_inchi_key(cls, v: str) -> str:
        """Validate InChIKey format if non-empty."""
        import re

        if v and not re.match(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$", v):
            raise ValueError(f"Invalid InChIKey format: {v}")
        return v
