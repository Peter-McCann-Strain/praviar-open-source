"""Substructure highlighting renderers."""

from __future__ import annotations

import structlog

from praviar_pipeline.rendering.structures_helpers import (
    _configure_drawer,
    _mol_from_smiles,
    _prepare_mol_2d,
)

logger = structlog.get_logger()


def render_substructure_svg(
    mol_smi: str,
    query_smarts: str,
    width: int = 500,
    height: int = 400,
) -> str | None:
    """Highlight a substructure match within a molecule."""
    mol = _mol_from_smiles(mol_smi)
    if mol is None:
        return None

    if not query_smarts or not query_smarts.strip():
        logger.warning("empty_query_smarts")
        return None

    try:
        from rdkit import Chem
        from rdkit.Chem.Draw import rdMolDraw2D

        query = Chem.MolFromSmarts(query_smarts.strip())
        if query is None:
            logger.warning("invalid_smarts")
            return None

        match = mol.GetSubstructMatch(query)
        if not match:
            logger.debug(
                "no_substructure_match",
            )
            return None

        highlight_atoms = list(match)
        atom_set = set(highlight_atoms)
        highlight_bonds: list[int] = []
        for bond in mol.GetBonds():
            if bond.GetBeginAtomIdx() in atom_set and bond.GetEndAtomIdx() in atom_set:
                highlight_bonds.append(bond.GetIdx())

        _prepare_mol_2d(mol)
        drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
        _configure_drawer(drawer)

        opts = drawer.drawOptions()
        opts.setHighlightColour((0.84, 0.37, 0.0, 0.3))

        drawer.DrawMolecule(
            mol,
            highlightAtoms=highlight_atoms,
            highlightBonds=highlight_bonds,
        )
        drawer.FinishDrawing()
        return drawer.GetDrawingText()
    except Exception:
        logger.warning(
            "render_substructure_svg_failed",
        )
        return None
