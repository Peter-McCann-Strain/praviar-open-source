"""PubChem-backed resolution helpers for Step 1 compound resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast, get_args

import structlog

from praviar_pipeline.models.compound import RelatedCompound, ResolvedCompound
from praviar_pipeline.pipeline.resolution.fingerprints import (
    compute_scaffold_smiles,
    strip_salts_and_stereo,
)
from praviar_pipeline.pipeline.resolution.identity_derivations import (
    derive_prodrug_candidates,
    enumerate_tautomer_candidates,
)

if TYPE_CHECKING:
    from praviar_pipeline.config import Settings

_log = structlog.get_logger()


async def resolve_pubchem_props(
    pubchem,
    *,
    user_input: str,
    input_type: str,
    logger,
) -> dict[str, Any]:
    if input_type == "name" or input_type == "cas":
        return cast("dict[str, Any]", await pubchem.resolve_by_name(user_input))
    if input_type == "smiles":
        return cast("dict[str, Any]", await pubchem.resolve_by_smiles(user_input))
    if input_type == "inchikey":
        return cast("dict[str, Any]", await pubchem.resolve_by_inchikey(user_input))
    if input_type == "inchi":
        return await _resolve_inchi_props(user_input, pubchem, logger)
    return cast("dict[str, Any]", await pubchem.resolve_by_name(user_input))


async def _resolve_inchi_props(user_input: str, pubchem, logger) -> dict[str, Any]:
    from rdkit import Chem
    from rdkit.Chem.inchi import InchiToInchiKey

    mol = Chem.MolFromInchi(user_input)
    if not mol:
        logger.error(
            "rdkit_inchi_parse_failed",
        )
        return {}

    inchikey = InchiToInchiKey(user_input)
    return cast("dict[str, Any]", await pubchem.resolve_by_inchikey(inchikey))


def build_related_compounds(
    *,
    sim_results: list[dict],
    cid: int,
    settings: Settings,
    logger,
) -> list[RelatedCompound]:
    related: list[RelatedCompound] = []
    for index, result in enumerate(sim_results[: settings.resolve_max_related_compounds]):
        result_cid = result.get("CID")
        if not result_cid:
            logger.warning("similarity_result_missing_cid", index=index)
            continue
        if result_cid == cid:
            continue
        estimated_tanimoto = max(
            settings.resolve_similarity_threshold,
            1.0 - (index * settings.resolve_tanimoto_step),
        )
        related.append(
            RelatedCompound(
                cid=result_cid,
                name=result.get("IUPACName", ""),
                canonical_smiles=result.get("CanonicalSMILES", ""),
                tanimoto_similarity=round(estimated_tanimoto, 3),
            )
        )
    return related


def build_resolved_compound(
    *,
    props: dict,
    input_type: str,
    user_input: str,
    synonyms: list[str],
    cas_numbers: list[str],
    molecular_weight: float | None,
    morgan_fp: str,
    maccs_keys: str,
    functional_groups: list[str],
    related_compounds: list[RelatedCompound],
    settings: Settings,
) -> ResolvedCompound:
    valid_input_types = get_args(ResolvedCompound.model_fields["input_type"].annotation)
    resolved_input_type = input_type if input_type in valid_input_types else "name"

    canonical_smiles = props.get("CanonicalSMILES", "")

    # Derive scaffold, salt-stripped, and stereo-stripped SMILES for broad searching.
    scaffold = compute_scaffold_smiles(canonical_smiles) if canonical_smiles else ""
    free_base, stereo_stripped = (
        strip_salts_and_stereo(canonical_smiles) if canonical_smiles else ("", "")
    )
    derivation_source = free_base or canonical_smiles
    derivation_source_form = (
        "salt_stripped_largest_fragment"
        if free_base and free_base != canonical_smiles
        else "canonical"
    )
    tautomer_enumeration = (
        enumerate_tautomer_candidates(
            derivation_source,
            source_form=derivation_source_form,
            max_tautomers=settings.identity_tautomer_max_enumerated,
            max_transforms=settings.identity_tautomer_max_transforms,
            max_search_candidates=settings.identity_tautomer_max_search_candidates,
        )
        if derivation_source
        else None
    )
    prodrug_derivation = (
        derive_prodrug_candidates(
            derivation_source,
            max_search_candidates=settings.identity_prodrug_max_search_candidates,
            min_parent_heavy_atom_fraction=(
                settings.identity_prodrug_min_parent_heavy_atom_fraction
            ),
        )
        if derivation_source
        else None
    )
    prodrug = (
        prodrug_derivation.detected_motifs[0]
        if prodrug_derivation and prodrug_derivation.detected_motifs
        else None
    )

    _log.debug(
        "step1_structural_coverage",
        has_scaffold=bool(scaffold),
        has_free_base=bool(free_base),
        has_stereo_stripped=bool(stereo_stripped),
        prodrug_pattern=prodrug,
        free_base_differs_from_canonical=bool(free_base and free_base != canonical_smiles),
        stereo_stripped_differs=bool(stereo_stripped and stereo_stripped != canonical_smiles),
        tautomer_status=(
            tautomer_enumeration.status if tautomer_enumeration is not None else "not_applicable"
        ),
        tautomer_search_candidate_count=sum(
            candidate.search_eligible
            for candidate in (
                tautomer_enumeration.candidates if tautomer_enumeration is not None else []
            )
        ),
        prodrug_search_candidate_count=len(
            prodrug_derivation.candidates if prodrug_derivation is not None else []
        ),
        unsupported_prodrug_motif_count=len(
            prodrug_derivation.unsupported_motifs if prodrug_derivation is not None else []
        ),
    )

    if prodrug:
        _log.info(
            "prodrug_pattern_detected",
            prodrug_pattern=prodrug,
        )

    return ResolvedCompound(
        name=props.get("IUPACName", user_input),
        canonical_smiles=canonical_smiles,
        inchi=props.get("InChI", ""),
        inchi_key=props.get("InChIKey", ""),
        pubchem_cid=props["CID"],
        synonyms=synonyms[: settings.resolve_max_synonyms],
        cas_numbers=cas_numbers,
        molecular_formula=props.get("MolecularFormula", ""),
        molecular_weight=molecular_weight,
        morgan_fp=morgan_fp,
        maccs_keys=maccs_keys,
        functional_groups=functional_groups,
        related_compounds=related_compounds,
        original_input=user_input,
        input_type=resolved_input_type,  # type: ignore[arg-type]
        scaffold_smiles=scaffold,
        free_base_smiles=free_base,
        stereo_stripped_smiles=stereo_stripped,
        prodrug_pattern=prodrug,
        tautomer_enumeration=tautomer_enumeration,
        prodrug_candidates=(
            prodrug_derivation.candidates if prodrug_derivation is not None else []
        ),
        unsupported_prodrug_motifs=(
            prodrug_derivation.unsupported_motifs if prodrug_derivation is not None else []
        ),
    )
