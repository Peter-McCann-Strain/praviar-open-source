"""Step 1: Compound Resolution — user input → ResolvedCompound."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.clients.openfda_gsrs import OpenFDAGSRSClient
from praviar_pipeline.clients.pubchem import PubChemClient
from praviar_pipeline.clients.purple_book import load_purple_book
from praviar_pipeline.config import get_settings
from praviar_pipeline.pipeline.resolution.biologic import (
    classify_compound as _classify_compound,
)
from praviar_pipeline.pipeline.resolution.biologic import (
    is_biologic_name as _is_biologic_name,
)
from praviar_pipeline.pipeline.resolution.biologic import (
    resolve_biologic as _resolve_biologic_impl,
)
from praviar_pipeline.pipeline.resolution.fingerprints import (
    compute_fingerprints as _compute_fingerprints,
)
from praviar_pipeline.pipeline.resolution.pubchem_resolution import (
    build_related_compounds,
    build_resolved_compound,
    resolve_pubchem_props,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.compound import ResolvedCompound

logger = structlog.get_logger()

_ECMASCRIPT_TRIM_CHARACTERS = (
    "\u0009\u000a\u000b\u000c\u000d\u0020\u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000\ufeff"
)
_ECMASCRIPT_WHITESPACE_PATTERN = (
    r"[\u0009-\u000d\u0020\u00a0\u1680\u2000-\u200a"
    r"\u2028\u2029\u202f\u205f\u3000\ufeff]"
)

# Public aliases retained for downstream tests and modules that import
# the canonical underscore-prefixed names from this step module.
__all__ = [
    "_classify_compound",
    "_compute_fingerprints",
    "_is_biologic_name",
    "_resolve_biologic",
    "detect_input_type",
    "normalize_cas_input",
    "normalize_compound_identifier",
    "resolve_compound",
]

# Input type detection patterns
CAS_PATTERN = re.compile(
    rf"^(?:CAS(?:{_ECMASCRIPT_WHITESPACE_PATTERN}*(?:RN|No\.?|#|:))?"
    rf"{_ECMASCRIPT_WHITESPACE_PATTERN}*)?[0-9]{{2,7}}-[0-9]{{2}}-[0-9]$",
    re.ASCII | re.IGNORECASE,
)
CAS_PREFIX_PATTERN = re.compile(
    rf"^CAS(?:{_ECMASCRIPT_WHITESPACE_PATTERN}*(?:RN|No\.?|#|:))?"
    rf"{_ECMASCRIPT_WHITESPACE_PATTERN}*",
    re.ASCII | re.IGNORECASE,
)
INCHI_PATTERN = re.compile(r"^InChI=")
INCHIKEY_PATTERN = re.compile(
    r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$",
    re.ASCII | re.IGNORECASE,
)
SMILES_ORGANIC_ATOMS = frozenset("BCNOPSFI")
SMILES_AROMATIC_ATOMS = frozenset("bcnops")
SMILES_STRUCTURE_MARKERS = frozenset("-=#$:/\\.()")


def normalize_compound_identifier(value: str) -> str:
    """Apply the exact boundary trimming used by ECMAScript String.trim()."""
    return value.strip(_ECMASCRIPT_TRIM_CHARACTERS)


def normalize_cas_input(user_input: str) -> str | None:
    """Return the bare registry number for accepted CAS-prefixed syntax."""
    text = normalize_compound_identifier(user_input)
    if not CAS_PATTERN.fullmatch(text):
        return None
    return CAS_PREFIX_PATTERN.sub("", text)


def _is_likely_smiles(value: str) -> bool:
    """Mirror the launch UI's conservative token-by-token SMILES classifier."""
    if not value or any(character in _ECMASCRIPT_TRIM_CHARACTERS for character in value):
        return False

    atom_count = 0
    has_structure_marker = False
    index = 0
    while index < len(value):
        character = value[index]

        if character == "[":
            close_index = value.find("]", index + 1)
            if close_index == -1:
                return False
            atom_count += 1
            has_structure_marker = True
            index = close_index + 1
            continue

        token = value[index : index + 2]
        if token in {"Cl", "Br"}:
            atom_count += 1
            index += 2
            continue

        if character in SMILES_ORGANIC_ATOMS or character in SMILES_AROMATIC_ATOMS:
            atom_count += 1
            index += 1
            continue

        if character in SMILES_STRUCTURE_MARKERS:
            has_structure_marker = True
            index += 1
            continue

        if character == "%":
            ring_id = value[index + 1 : index + 3]
            if len(ring_id) != 2 or any(digit not in "0123456789" for digit in ring_id):
                return False
            has_structure_marker = True
            index += 3
            continue

        if character in "123456789":
            has_structure_marker = True
            index += 1
            continue

        if character == "*":
            atom_count += 1
            has_structure_marker = True
            index += 1
            continue

        return False

    return atom_count >= 2 or (atom_count == 1 and has_structure_marker)


def detect_input_type(user_input: str) -> str:
    """Detect whether input is a name, SMILES, CAS, InChI, or InChIKey."""
    text = normalize_compound_identifier(user_input)

    if CAS_PATTERN.fullmatch(text):
        return "cas"
    if INCHI_PATTERN.match(text):
        return "inchi"
    if INCHIKEY_PATTERN.match(text):
        return "inchikey"
    if _is_likely_smiles(text):
        return "smiles"
    return "name"


async def _resolve_biologic(
    user_input: str,
    input_type: str,
    pubchem_props: dict | None = None,
) -> ResolvedCompound:
    """Resolve a biologic via FDA Purple Book or exact FDA GSRS identity."""

    async def _resolve_exact_gsrs(name: str):
        async with OpenFDAGSRSClient() as client:
            return await client.resolve_exact_biologic(name)

    return await _resolve_biologic_impl(
        user_input,
        input_type,
        pubchem_props=pubchem_props,
        load_purple_book_fn=load_purple_book,
        resolve_gsrs_fn=_resolve_exact_gsrs,
        is_biologic_name_fn=_is_biologic_name,
        classify_compound_fn=_classify_compound,
        logger=logger,
    )


async def resolve_compound(user_input: str) -> ResolvedCompound:
    """Resolve arbitrary user input into a fully identified compound.

    Supports: compound names, SMILES, CAS numbers, InChI, InChIKey.
    Biologics (monoclonal antibodies, proteins, peptides) are routed
    through the Purple Book pathway instead of requiring SMILES.
    """
    if not isinstance(user_input, str):
        raise ValueError("Compound input must be text")
    user_input = normalize_compound_identifier(user_input)
    if not user_input:
        raise ValueError("Compound input cannot be empty")
    settings = get_settings()
    if len(user_input) > settings.input_max_length:
        raise ValueError(
            f"Compound input too long ({len(user_input)} chars, max {settings.input_max_length})"
        )

    input_type = detect_input_type(user_input)
    logger.info("compound_resolution_start", input_type=input_type)
    logger.debug(
        "step1_entry",
        input_type=input_type,
        input_length=len(user_input),
    )

    # Early biologic detection by name — skip PubChem entirely
    if input_type == "name" and _is_biologic_name(user_input):
        logger.info(
            "biologic_detected_by_name",
            pathway="fda_purple_book_or_gsrs",
        )
        return await _resolve_biologic(user_input, input_type)

    async with PubChemClient() as pubchem:
        if input_type == "cas":
            lookup_input = normalize_cas_input(user_input)
        elif input_type == "inchikey":
            lookup_input = user_input.upper()
        else:
            lookup_input = user_input
        if lookup_input is None:
            raise ValueError(f"Could not normalize CAS input: {user_input}")
        props = await resolve_pubchem_props(
            pubchem,
            user_input=lookup_input,
            input_type=input_type,
            logger=logger,
        )

        # If PubChem fails, check if this might be a biologic
        if not props or "CID" not in props:
            # Try Purple Book pathway before raising
            if input_type == "name":
                purple_book = await load_purple_book()
                pb_data = purple_book.lookup_biologic(user_input)
                if pb_data:
                    logger.info(
                        "biologic_detected_pubchem_fallback",
                        pathway="fda_purple_book_or_gsrs",
                    )
                    return await _resolve_biologic(user_input, input_type)
            raise ValueError(f"Could not resolve compound: {user_input}")

        cid = props["CID"]
        canonical_smiles = props.get("CanonicalSMILES", "")
        raw_weight = props.get("MolecularWeight")
        mol_weight = float(raw_weight) if raw_weight else None

        # Post-PubChem biologic detection
        compound_type = _classify_compound(
            props.get("IUPACName", user_input),
            canonical_smiles,
            mol_weight,
        )
        if compound_type in ("biologic", "peptide"):
            logger.info(
                "biologic_detected_post_pubchem",
                compound_type=compound_type,
                molecular_weight=mol_weight,
                has_smiles=bool(canonical_smiles),
                pathway="fda_purple_book_or_gsrs",
            )
            return await _resolve_biologic(user_input, input_type, pubchem_props=props)

        logger.debug(
            "step1_pubchem_resolved",
            has_smiles=bool(canonical_smiles),
            has_inchi=bool(props.get("InChI")),
        )

        # Step 2: Get synonyms
        synonyms = await pubchem.get_synonyms(cid)

        # Step 3: Extract CAS numbers from synonyms
        cas_numbers = [s for s in synonyms if CAS_PATTERN.match(s)]

        # Step 4: Compute fingerprints via RDKit
        morgan_hex, maccs_hex, functional_groups = _compute_fingerprints(canonical_smiles)

        sim_results = await pubchem.similarity_search(
            canonical_smiles,
            threshold=settings.resolve_similarity_threshold,
        )
        related = build_related_compounds(
            sim_results=sim_results,
            cid=cid,
            settings=settings,
            logger=logger,
        )

        compound = build_resolved_compound(
            props=props,
            input_type=input_type,
            user_input=user_input,
            synonyms=synonyms,
            cas_numbers=cas_numbers,
            molecular_weight=mol_weight,
            morgan_fp=morgan_hex,
            maccs_keys=maccs_hex,
            functional_groups=functional_groups,
            related_compounds=related,
            settings=settings,
        )

        logger.info(
            "compound_resolved",
            compound_type=compound.compound_type,
            synonyms_count=len(compound.synonyms),
            related_count=len(compound.related_compounds),
        )
        logger.debug(
            "step1_output_summary",
            smiles_length=len(compound.canonical_smiles),
            cas_count=len(compound.cas_numbers),
            molecular_weight=compound.molecular_weight,
            related_compounds_count=len(compound.related_compounds),
            synonyms_count=len(compound.synonyms),
        )
        return compound
