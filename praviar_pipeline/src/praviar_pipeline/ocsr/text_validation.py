"""Text-based cross-validation for OCSR outputs.

Validates OCSR-extracted SMILES against chemical information found in
patent text. Provides an independent validation signal by comparing
image-derived structures against text-derived structures.

Validation layers:
1. Molecular formula cross-check — extract formula from text, compare to OCSR
2. IUPAC name → SMILES via OPSIN — convert names found in text to SMILES
3. CAS number → PubChem lookup — resolve CAS to canonical SMILES
4. InChI key cross-reference — match OCSR output against PubChem

This module runs in the primary Praviar Pipeline venv and uses:
- RDKit for SMILES/InChI manipulation
- httpx for PubChem API calls (reuses existing client pattern)
- Regex for chemical entity extraction (lightweight NER)
"""

from __future__ import annotations

from typing import NamedTuple

import structlog

from praviar_pipeline.ocsr.text_validation_clients import (
    _pubchem_cas_lookup,
    _pubchem_inchi_lookup,
    _pubchem_name_lookup,
)
from praviar_pipeline.ocsr.text_validation_clients import (
    opsin_resolve as _opsin_resolve,
)
from praviar_pipeline.ocsr.text_validation_helpers import (
    extract_cas_numbers as _extract_cas_numbers,
)
from praviar_pipeline.ocsr.text_validation_helpers import (
    extract_chemical_names as _extract_chemical_names,
)
from praviar_pipeline.ocsr.text_validation_helpers import (
    extract_molecular_formulas as _extract_molecular_formulas,
)
from praviar_pipeline.ocsr.text_validation_helpers import (
    smiles_to_formula as _smiles_to_formula_impl,
)
from praviar_pipeline.ocsr.text_validation_helpers import (
    smiles_to_inchi_key as _smiles_to_inchi_key_impl,
)
from praviar_pipeline.ocsr.text_validation_helpers import (
    tanimoto as _tanimoto_impl,
)

logger = structlog.get_logger()


class TextValidationResult(NamedTuple):
    """Result of text-based cross-validation."""

    validated: bool  # True if text evidence supports the OCSR output
    confidence: float  # 0-1, how confident the text validation is
    method: str  # Which method validated (formula, iupac, cas, pubchem)
    text_smiles: str  # SMILES derived from text (if available)
    text_formula: str  # Formula found in text (if available)
    details: str  # Human-readable explanation


def extract_molecular_formulas(text: str) -> list[str]:
    """Extract molecular formulas from patent text."""
    return _extract_molecular_formulas(text)


def extract_cas_numbers(text: str) -> list[str]:
    """Extract CAS Registry Numbers from patent text.

    Basic validation: checksum digit must match.
    """
    return _extract_cas_numbers(text)


def extract_chemical_names(text: str) -> list[str]:
    """Extract IUPAC-like chemical names from patent text.

    Uses pattern matching — not a full NER model. Catches common
    systematic names and drug name suffixes.
    """
    return _extract_chemical_names(text)


async def opsin_resolve(name: str, timeout: float = 10.0) -> str | None:
    """Resolve an IUPAC chemical name to SMILES via OPSIN REST API."""
    return await _opsin_resolve(name, timeout=timeout)


def _smiles_to_formula(smiles: str) -> str:
    """Convert SMILES to molecular formula string."""
    return _smiles_to_formula_impl(smiles)


def _smiles_to_inchi_key(smiles: str) -> str:
    """Convert SMILES to InChI key."""
    return _smiles_to_inchi_key_impl(smiles)


def _tanimoto(smi1: str, smi2: str) -> float:
    """Compute Tanimoto similarity between two SMILES."""
    return _tanimoto_impl(smi1, smi2)


def validate_formula(ocsr_smiles: str, text_formulas: list[str]) -> TextValidationResult | None:
    """Check if OCSR output formula matches any formula found in text."""
    ocsr_formula = _smiles_to_formula(ocsr_smiles)
    if not ocsr_formula:
        return None

    for text_formula in text_formulas:
        if ocsr_formula == text_formula:
            return TextValidationResult(
                validated=True,
                confidence=0.85,
                method="formula_match",
                text_smiles="",
                text_formula=text_formula,
                details=f"OCSR formula {ocsr_formula} matches text formula {text_formula}",
            )

    return TextValidationResult(
        validated=False,
        confidence=0.30,
        method="formula_mismatch",
        text_smiles="",
        text_formula=ocsr_formula,
        details=f"OCSR formula {ocsr_formula} not found in text formulas {text_formulas}",
    )


async def validate_against_text(
    ocsr_smiles: str,
    patent_text: str,
    *,
    tanimoto_threshold: float,
    skip_pubchem: bool = False,
) -> TextValidationResult:
    """Cross-validate an OCSR-extracted SMILES against patent text.

    Runs all validation layers and returns the strongest signal.

    Args:
        ocsr_smiles: SMILES string from OCSR extraction.
        patent_text: Full patent text (claims + description).
        tanimoto_threshold: Cutoff for accepting CAS/name PubChem matches.
            Pass `settings.drawing_text_validation_tanimoto_threshold` from the
            caller; the threshold is not baked in here.
        skip_pubchem: Skip PubChem API calls (for testing).

    Returns:
        TextValidationResult with the validation outcome.
    """
    if not ocsr_smiles or not patent_text:
        return TextValidationResult(
            validated=False,
            confidence=0.0,
            method="no_input",
            text_smiles="",
            text_formula="",
            details="Missing OCSR SMILES or patent text",
        )

    # Layer 1: Molecular formula cross-check
    text_formulas = extract_molecular_formulas(patent_text)
    if text_formulas:
        formula_result = validate_formula(ocsr_smiles, text_formulas)
        if formula_result and formula_result.validated:
            logger.debug(
                "text_validation_formula_match",
            )
            return formula_result

    # Layer 2: CAS number → PubChem lookup → Tanimoto comparison
    if not skip_pubchem:
        cas_numbers = extract_cas_numbers(patent_text)
        for cas in cas_numbers[:5]:  # Limit API calls
            cas_smiles = await _pubchem_cas_lookup(cas)
            if cas_smiles:
                sim = _tanimoto(ocsr_smiles, cas_smiles)
                if sim > tanimoto_threshold:
                    return TextValidationResult(
                        validated=True,
                        confidence=0.90,
                        method="cas_pubchem_match",
                        text_smiles=cas_smiles,
                        text_formula="",
                        details=f"CAS {cas} → PubChem SMILES matches OCSR (Tanimoto={sim:.3f})",
                    )

    # Layer 3: Chemical name → PubChem lookup
    if not skip_pubchem:
        chem_names = extract_chemical_names(patent_text)
        for name in chem_names[:3]:  # Limit API calls
            name_smiles = await _pubchem_name_lookup(name)
            if name_smiles:
                sim = _tanimoto(ocsr_smiles, name_smiles)
                if sim > tanimoto_threshold:
                    return TextValidationResult(
                        validated=True,
                        confidence=0.85,
                        method="name_pubchem_match",
                        text_smiles=name_smiles,
                        text_formula="",
                        details=f"Name '{name}' → PubChem matches OCSR (Tanimoto={sim:.3f})",
                    )

    # Layer 4: InChI key cross-reference in PubChem
    if not skip_pubchem:
        inchi_key = _smiles_to_inchi_key(ocsr_smiles)
        if inchi_key:
            pubchem_smiles = await _pubchem_inchi_lookup(inchi_key)
            if pubchem_smiles:
                return TextValidationResult(
                    validated=True,
                    confidence=0.80,
                    method="inchi_pubchem_confirmed",
                    text_smiles=pubchem_smiles,
                    text_formula="",
                    details=f"OCSR InChI key {inchi_key} found in PubChem (known compound)",
                )

    # No validation signal found
    return TextValidationResult(
        validated=False,
        confidence=0.0,
        method="no_match",
        text_smiles="",
        text_formula="",
        details="No text-based validation signal found",
    )
