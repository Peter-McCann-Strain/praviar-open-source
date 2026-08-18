"""Pure helpers for chemical structure rendering."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()


def _mol_from_smiles(smiles: str) -> Any | None:
    """Safely parse a SMILES string into an RDKit Mol object."""
    if not smiles or not smiles.strip():
        return None

    try:
        from rdkit import Chem
    except ImportError:
        logger.warning("rdkit_not_available")
        return None

    mol = Chem.MolFromSmiles(smiles.strip())
    if mol is None:
        logger.warning("invalid_smiles")
        return None
    return mol


def _prepare_mol_2d(mol: Any) -> Any:
    """Compute 2D coordinates for a molecule in place and return it."""
    try:
        from rdkit.Chem import rdDepictor

        rdDepictor.Compute2DCoords(mol)
    except Exception:
        logger.warning("mol_2d_coords_failed")
    return mol


def _configure_drawer(drawer: Any) -> None:
    """Apply patent-style B&W drawing options to an MolDraw2D instance."""
    opts = drawer.drawOptions()
    opts.bondLineWidth = 1.5
    opts.minFontSize = 12
    opts.addStereoAnnotation = True
    opts.useBWAtomPalette()


def _svg_to_png(svg_string: str, width: int, dpi: int = 300) -> bytes | None:
    """Convert an SVG string to PNG bytes using cairosvg when available."""
    try:
        import cairosvg
    except ImportError:
        logger.debug("cairosvg_not_available")
        return None

    try:
        scale = dpi / 96.0
        output_width = int(width * scale)
        return bytes(
            cairosvg.svg2png(
                bytestring=svg_string.encode("utf-8"),
                output_width=output_width,
            )
        )
    except Exception:
        logger.warning("svg_to_png_failed")
        return None


def _find_mcs_diff_atoms(
    target_mol: Any,
    patent_mol: Any,
) -> tuple[list[int], list[int]] | None:
    """Find atoms that differ between two molecules using MCS."""
    try:
        from rdkit import Chem
        from rdkit.Chem import rdFMCS
    except ImportError:
        return None

    try:
        mcs_result = rdFMCS.FindMCS(
            [target_mol, patent_mol],
            ringMatchesRingOnly=True,
            completeRingsOnly=True,
            timeout=10,
        )

        if mcs_result.canceled or not mcs_result.smartsString:
            target_diff = list(range(target_mol.GetNumAtoms()))
            patent_diff = list(range(patent_mol.GetNumAtoms()))
            return target_diff, patent_diff

        mcs_mol = Chem.MolFromSmarts(mcs_result.smartsString)
        if mcs_mol is None:
            return None

        target_match = target_mol.GetSubstructMatch(mcs_mol)
        patent_match = patent_mol.GetSubstructMatch(mcs_mol)

        target_match_set = set(target_match)
        patent_match_set = set(patent_match)

        target_diff = [i for i in range(target_mol.GetNumAtoms()) if i not in target_match_set]
        patent_diff = [i for i in range(patent_mol.GetNumAtoms()) if i not in patent_match_set]

        return target_diff, patent_diff
    except Exception:
        logger.warning("mcs_computation_failed")
        return None
