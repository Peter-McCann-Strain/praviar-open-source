"""Design-around feasibility validation using RDKit.

Given a proposed design-around SMILES and the original compound SMILES, this
module:

 - parses the proposed SMILES with RDKit and records ``rdkit_valid``,
 - computes Tanimoto similarity using Morgan fingerprints (radius 2, 2048 bits)
   and records ``tanimoto_to_original``,
 - sets a heuristic ``pharmacophore_preserved`` flag based on the Tanimoto band.

Tanimoto band rationale
-----------------------
The pharmacophore-preserved heuristic uses a mid-range Tanimoto window:

  Lower bound (0.35): below this value the core scaffold has been substantially
  destroyed. A Tanimoto under 0.35 between Morgan-r2 fingerprints typically
  indicates loss of the ring systems or key functional groups that define the
  pharmacophore. Reference: Willett, P. et al., J. Chem. Inf. Comput. Sci., 1998,
  https://doi.org/10.1021/ci9800211 reports that pairs with Tanimoto < 0.35 are
  reliably dissimilar at a scaffold level.

  Upper bound (0.85): above this value the modification is so minor that it may
  not constitute a real structural change, and could still infringe under the
  Doctrine of Equivalents. Chembl activity-cliff literature (Stumpfe & Bajorath,
  J. Med. Chem. 2012, https://doi.org/10.1021/jm300706s) puts pairs at Tanimoto
  > 0.85 in the "highly similar" bracket where biological equivalence is likely.

  The band [0.35, 0.85] therefore represents structures that share recognisable
  chemical ancestry (pharmacophore intact) while being sufficiently distinct to
  constitute a genuine design-around. This is deliberately conservative: the
  values are thresholds for a heuristic flag, not a legal opinion.

A chemically invalid SMILES (``rdkit_valid=False``) always yields
``pharmacophore_preserved=False`` because no structural comparison is possible.

This module follows the repo's no-fallback principle with one explicit exception:
an unparseable SMILES is DATA (the LLM produced a bad string), not a system
error. ``rdkit_valid`` is set to ``False`` and the function returns normally.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis_claims import DesignAroundSuggestion

logger = structlog.get_logger()

# Tanimoto band for heuristic pharmacophore-preservation check.
# See module docstring for the derivation and literature references.
_TANIMOTO_LOW = 0.35
_TANIMOTO_HIGH = 0.85


def validate_design_around(
    suggestion: DesignAroundSuggestion,
    original_smiles: str,
) -> DesignAroundSuggestion:
    """Validate a design-around suggestion against the original compound SMILES.

    Populates ``rdkit_valid``, ``tanimoto_to_original``, and
    ``pharmacophore_preserved`` on the suggestion and returns a new
    ``DesignAroundSuggestion`` instance (Pydantic models are immutable by
    default; we use ``model_copy`` to produce the updated record).

    If ``suggestion.smiles`` is None, the function returns the suggestion
    unchanged with all three fields still None.  Only call this function when
    you have a SMILES to validate.

    Parameters
    ----------
    suggestion:
        The design-around suggestion to validate.  Must have ``smiles`` set.
    original_smiles:
        Canonical SMILES of the original (target) compound, used as the
        reference for Tanimoto similarity.

    Returns
    -------
    DesignAroundSuggestion
        A new instance with the structured validation fields populated.
    """
    if suggestion.smiles is None:
        return suggestion

    # Import here so the module is importable even without RDKit installed
    # (tests gate on pytest.importorskip; the pipeline itself lists rdkit-pypi
    # as a hard dependency, so this is purely a safety measure).
    try:
        from rdkit import Chem
        from rdkit.Chem import DataStructs, rdFingerprintGenerator
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "RDKit is required for design-around validation but is not installed. "
            "Add rdkit-pypi to the project dependencies."
        ) from exc

    proposed_mol = Chem.MolFromSmiles(suggestion.smiles)

    if proposed_mol is None:
        logger.warning(
            "design_around_smiles_invalid",
            element_avoided=suggestion.element_avoided,
        )
        return suggestion.model_copy(
            update={
                "rdkit_valid": False,
                "tanimoto_to_original": None,
                "pharmacophore_preserved": False,
            }
        )

    # SMILES parsed successfully.
    original_mol = Chem.MolFromSmiles(original_smiles)
    if original_mol is None:
        # The original compound SMILES is invalid — this should not happen in
        # normal operation (ResolvedCompound validates its SMILES upstream), but
        # we fail loud here as it indicates a data-integrity problem upstream.
        raise ValueError(
            f"Original compound SMILES could not be parsed by RDKit: {original_smiles!r}"
        )

    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    fp_proposed = generator.GetFingerprint(proposed_mol)
    fp_original = generator.GetFingerprint(original_mol)
    tanimoto = DataStructs.TanimotoSimilarity(fp_proposed, fp_original)

    pharmacophore_preserved = _TANIMOTO_LOW <= tanimoto <= _TANIMOTO_HIGH

    logger.debug(
        "design_around_validated",
        element_avoided=suggestion.element_avoided,
        tanimoto=round(tanimoto, 4),
        pharmacophore_preserved=pharmacophore_preserved,
    )

    return suggestion.model_copy(
        update={
            "rdkit_valid": True,
            "tanimoto_to_original": round(tanimoto, 6),
            "pharmacophore_preserved": pharmacophore_preserved,
        }
    )
