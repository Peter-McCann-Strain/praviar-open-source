"""Single-compound structure rendering helpers."""

from __future__ import annotations

import structlog

from praviar_pipeline.rendering.structures_helpers import (
    _configure_drawer,
    _mol_from_smiles,
    _prepare_mol_2d,
    _svg_to_png,
)
from praviar_pipeline.rendering.structures_renderers import (
    _try_cairo_drawer,
    _try_mol_to_image,
)

logger = structlog.get_logger()


def render_compound_svg(
    smiles: str,
    width: int = 500,
    height: int = 400,
) -> str | None:
    """Render a single compound as a B&W patent-style SVG image."""
    mol = _mol_from_smiles(smiles)
    if mol is None:
        return None

    try:
        from rdkit.Chem.Draw import rdMolDraw2D

        _prepare_mol_2d(mol)
        drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
        _configure_drawer(drawer)
        drawer.DrawMolecule(mol)
        drawer.FinishDrawing()
        return drawer.GetDrawingText()
    except Exception:
        logger.warning("render_compound_svg_failed")
        return None


def render_compound_png(
    smiles: str,
    width: int = 500,
    height: int = 400,
    dpi: int = 300,
) -> bytes | None:
    """Render a single compound as a PNG image."""
    mol = _mol_from_smiles(smiles)
    if mol is None:
        return None

    _prepare_mol_2d(mol)

    png_bytes = _try_cairo_drawer(mol, width, height)
    if png_bytes is not None:
        return png_bytes

    svg_text = render_compound_svg(smiles, width, height)
    if svg_text is not None:
        png_bytes = _svg_to_png(svg_text, width, dpi)
        if png_bytes is not None:
            return png_bytes

    return _try_mol_to_image(mol, width, height)
