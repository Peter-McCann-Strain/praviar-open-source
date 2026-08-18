"""Biologic detection and Purple Book resolution helpers for Step 1."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, get_args

import structlog

from praviar_pipeline.models.compound import ResolvedCompound

if TYPE_CHECKING:
    from praviar_pipeline.clients.openfda_gsrs import GSRSBiologicIdentity

BIOLOGIC_SUFFIXES = (
    "-mab",
    "-cept",
    "-zumab",
    "-ximab",
    "-umab",
    "-ase",
    "-stim",
    "-poetin",
    "-plasm",
    "-pressin",
    "-tide",
    "-relin",
)

SMALL_MOLECULE_OVERRIDE_SUFFIXES = (
    "-tinib",
    "-ciclib",
    "-lisib",
    "-rafenib",
    "-metinib",
    "-parib",
)


def is_biologic_name(name: str) -> bool:
    """Return True when a name matches known biologic naming patterns."""
    name_lower = name.lower().strip()
    for sm_suffix in SMALL_MOLECULE_OVERRIDE_SUFFIXES:
        if name_lower.endswith(sm_suffix) or name_lower.endswith(sm_suffix.lstrip("-")):
            return False
    for suffix in BIOLOGIC_SUFFIXES:
        if name_lower.endswith(suffix) or name_lower.endswith(suffix.lstrip("-")):
            return True
    return False


def classify_compound(
    name: str,
    canonical_smiles: str,
    molecular_weight: float | None,
) -> str:
    """Classify a compound as small_molecule, biologic, or peptide."""
    if is_biologic_name(name):
        return "biologic"

    if molecular_weight is not None and molecular_weight > 5000:
        if molecular_weight > 10000:
            return "biologic"
        return "peptide"

    if not canonical_smiles or len(canonical_smiles) < 3:
        return "biologic"

    return "small_molecule"


async def resolve_biologic(
    user_input: str,
    input_type: str,
    pubchem_props: dict | None = None,
    *,
    load_purple_book_fn: Any,
    resolve_gsrs_fn: Any | None = None,
    is_biologic_name_fn: Any = is_biologic_name,
    classify_compound_fn: Any = classify_compound,
    logger: Any | None = None,
) -> ResolvedCompound:
    """Resolve a biologic against Purple Book or one exact FDA GSRS protein record."""
    bound_logger = logger or structlog.get_logger()
    purple_book = await load_purple_book_fn()
    pb_data = purple_book.lookup_biologic(user_input)
    if pb_data and not _is_exact_purple_book_identity(user_input, pb_data):
        bound_logger.warning("biologic_purple_book_non_exact_match_rejected")
        pb_data = None
    gsrs_data: GSRSBiologicIdentity | None = None
    if resolve_gsrs_fn is not None:
        gsrs_lookup_name = str(pb_data.get("proper_name") or user_input) if pb_data else user_input
        gsrs_data = await resolve_gsrs_fn(gsrs_lookup_name)
    if not pb_data and gsrs_data is None:
        raise ValueError(
            "Could not bind the biologic to an exact FDA Purple Book or primary, "
            "complete FDA GSRS protein record"
        )

    name = user_input
    synonyms: list[str] = []
    mol_weight: float | None = None
    mol_formula = ""
    canonical_smiles = ""
    inchi = ""
    inchi_key = ""
    pubchem_cid: int | None = None

    if pubchem_props and "CID" in pubchem_props:
        pubchem_cid = pubchem_props["CID"]
        name = pubchem_props.get("IUPACName", user_input)
        canonical_smiles = pubchem_props.get("CanonicalSMILES", "")
        inchi = pubchem_props.get("InChI", "")
        inchi_key = pubchem_props.get("InChIKey", "")
        mol_formula = pubchem_props.get("MolecularFormula", "")
        raw_weight = pubchem_props.get("MolecularWeight")
        mol_weight = float(raw_weight) if raw_weight else None

    compound_type = classify_compound_fn(name, canonical_smiles, mol_weight)
    if compound_type == "small_molecule" and is_biologic_name_fn(user_input):
        compound_type = "biologic"

    bla_number = ""
    reference_product = ""
    biosimilar_count = 0

    if pb_data:
        bla_number = pb_data["bla_number"]
        reference_product = pb_data.get("reference_product", "")
        biosimilar_count = pb_data.get("biosimilar_count", 0)
        if name == user_input and pb_data.get("proper_name"):
            name = pb_data["proper_name"]
        pb_product_name = pb_data.get("product_name", "")
        if pb_product_name and pb_product_name.lower() != name.lower():
            synonyms.append(pb_product_name)

        bound_logger.info(
            "biologic_purple_book_match",
            biosimilar_count=biosimilar_count,
        )
    else:
        assert gsrs_data is not None
        name = gsrs_data.preferred_name
        synonyms.extend(gsrs_data.aliases)
        bound_logger.info(
            "biologic_gsrs_match",
            gsrs_substance_class=gsrs_data.substance_class,
            gsrs_definition_type=gsrs_data.definition_type,
            gsrs_definition_level=gsrs_data.definition_level,
        )

    valid_types = get_args(ResolvedCompound.model_fields["input_type"].annotation)
    resolved_input_type = input_type if input_type in valid_types else "name"

    compound = ResolvedCompound(
        name=name,
        canonical_smiles=canonical_smiles,
        inchi=inchi,
        inchi_key=inchi_key,
        pubchem_cid=pubchem_cid,
        synonyms=synonyms,
        cas_numbers=[],
        molecular_formula=mol_formula,
        molecular_weight=mol_weight,
        morgan_fp="",
        maccs_keys="",
        functional_groups=[],
        related_compounds=[],
        scaffold_smiles="",
        free_base_smiles="",
        stereo_stripped_smiles="",
        prodrug_pattern=None,
        original_input=user_input,
        input_type=resolved_input_type,  # type: ignore[arg-type]
        compound_type=compound_type,
        bla_number=bla_number,
        reference_product=reference_product,
        biosimilar_count=biosimilar_count,
        unii=gsrs_data.unii if gsrs_data is not None else "",
        gsrs_uuid=gsrs_data.uuid if gsrs_data is not None else "",
        gsrs_substance_class=gsrs_data.substance_class if gsrs_data is not None else "",
        gsrs_definition_type=gsrs_data.definition_type if gsrs_data is not None else "",
        gsrs_definition_level=gsrs_data.definition_level if gsrs_data is not None else "",
        gsrs_record_version=gsrs_data.record_version if gsrs_data is not None else "",
        gsrs_names_last_updated=(gsrs_data.names_last_updated if gsrs_data is not None else ""),
        gsrs_record_last_updated=(gsrs_data.record_last_updated if gsrs_data is not None else ""),
        protein_subunit_sequences=(
            gsrs_data.protein_subunit_sequences if gsrs_data is not None else []
        ),
    )

    bound_logger.info(
        "biologic_resolved",
        compound_type=compound.compound_type,
        biosimilar_count=compound.biosimilar_count,
    )
    return compound


def _is_exact_purple_book_identity(user_input: str, pb_data: dict[str, Any]) -> bool:
    query = " ".join(user_input.casefold().split())
    exact_values = {
        " ".join(str(pb_data.get(key, "")).casefold().split())
        for key in ("proper_name", "product_name", "bla_number")
        if str(pb_data.get(key, "")).strip()
    }
    return query in exact_values
