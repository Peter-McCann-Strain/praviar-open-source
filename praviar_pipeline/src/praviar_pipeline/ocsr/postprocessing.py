"""Configured SMILES normalization and repair steps for OCSR output.

Each function takes a SMILES string and returns a corrected version.
Functions are designed to be composable — chain them in any order.
"""

from __future__ import annotations

import structlog

from praviar_pipeline.ocsr.postprocessing_helpers import clean_fragments
from praviar_pipeline.ocsr.postprocessing_plan import (
    ABBREVIATION_MAP as _ABBREVIATION_MAP,
)
from praviar_pipeline.ocsr.postprocessing_plan import (
    build_postprocessing_step_map,
    default_postprocessing_steps,
)
from praviar_pipeline.ocsr.postprocessing_pubchem import (
    recover_salt_form,
    recover_stereo_from_pubchem,
)
from praviar_pipeline.ocsr.postprocessing_rdkit import (
    canonicalise,
    inchi_round_trip,
    normalise_aromaticity,
    remove_salts,
    repair_valence,
    to_inchi_key,
)
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

logger = structlog.get_logger()
ABBREVIATION_MAP = _ABBREVIATION_MAP


def strip_ocsr_artifacts(smiles: str) -> str:
    """Remove OCSR-specific artifacts before further processing.

    Common OCSR artifacts:
    - Wildcard fragments: *, *.*.*.*
    - Invalid atom labels from OCR: [HH], [Chiral], [Compound]
    - Empty fragments from disconnected dot notation
    """
    if "." not in smiles:
        return smiles

    try:
        cleaned = clean_fragments(smiles)
        if not cleaned:
            return smiles  # Don't return empty
        return ".".join(cleaned)
    except Exception:
        return smiles


def postprocess(
    smiles: str,
    steps: list[str] | None = None,
) -> tuple[str, list[str]]:
    """Run the configured postprocessing pipeline.

    Args:
        smiles: Raw SMILES from OCSR tool.
        steps: List of step names to apply, in order.
               Valid: "canonicalise", "inchi_round_trip", "remove_salts",
               "repair_valence", "normalise_aromaticity".
               If None, applies default: ["repair_valence", "remove_salts", "canonicalise"].

    Returns:
        Tuple of (processed SMILES, list of steps actually applied).
    """
    if steps is None:
        steps = default_postprocessing_steps()

    applied: list[str] = []
    step_fn = build_postprocessing_step_map(
        strip_ocsr_artifacts=strip_ocsr_artifacts,
        canonicalise=canonicalise,
        inchi_round_trip=inchi_round_trip,
        remove_salts=remove_salts,
        recover_salt_form=recover_salt_form,
        repair_valence=repair_valence,
        normalise_aromaticity=normalise_aromaticity,
        recover_stereo_from_pubchem=recover_stereo_from_pubchem,
    )

    for step_name in steps:
        fn = step_fn.get(step_name)
        if fn is None:
            logger.warning("postprocessing_unknown_step", step=step_name)
            continue
        try:
            new_smiles = fn(smiles)
            if new_smiles and new_smiles != smiles:
                logger.debug(
                    "postprocessing_changed",
                    step=step_name,
                )
            smiles = new_smiles
            applied.append(step_name)
        except Exception as exc:
            logger.error(
                "postprocessing_step_failed",
                step=step_name,
                error_type=safe_exception_type(exc),
            )

    return smiles, applied


__all__ = [
    "ABBREVIATION_MAP",
    "canonicalise",
    "inchi_round_trip",
    "normalise_aromaticity",
    "postprocess",
    "recover_salt_form",
    "recover_stereo_from_pubchem",
    "remove_salts",
    "repair_valence",
    "strip_ocsr_artifacts",
    "to_inchi_key",
]
