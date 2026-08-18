"""Side-by-side structure comparison renderers."""

from __future__ import annotations

import structlog

from praviar_pipeline.rendering.structures_helpers import (
    _configure_drawer,
    _find_mcs_diff_atoms,
    _mol_from_smiles,
    _prepare_mol_2d,
    _svg_to_png,
)
from praviar_pipeline.rendering.structures_renderers import (
    _try_comparison_cairo,
    _try_comparison_pil,
)

logger = structlog.get_logger()


def render_comparison_svg(
    target_smi: str,
    patent_smi: str,
    width: int = 900,
    height: int = 350,
) -> str | None:
    """Render a side-by-side comparison of two molecules with MCS highlighting."""
    target_mol = _mol_from_smiles(target_smi)
    patent_mol = _mol_from_smiles(patent_smi)
    if target_mol is None or patent_mol is None:
        return None

    try:
        from rdkit.Chem.Draw import rdMolDraw2D

        _prepare_mol_2d(target_mol)
        _prepare_mol_2d(patent_mol)

        highlight_target: list[int] = []
        highlight_patent: list[int] = []
        diff = _find_mcs_diff_atoms(target_mol, patent_mol)
        if diff is not None:
            highlight_target, highlight_patent = diff

        drawer = rdMolDraw2D.MolDraw2DSVG(width, height, width // 2, height)
        _configure_drawer(drawer)

        opts = drawer.drawOptions()
        opts.setHighlightColour((0.84, 0.37, 0.0, 0.3))

        drawer.DrawMolecules(
            [target_mol, patent_mol],
            legends=["Target Compound", "Patented Compound"],
            highlightAtoms=[highlight_target, highlight_patent],
        )
        drawer.FinishDrawing()
        return drawer.GetDrawingText()
    except Exception:
        logger.warning(
            "render_comparison_svg_failed",
        )
        return None


def render_comparison_png(
    target_smi: str,
    patent_smi: str,
    width: int = 900,
    height: int = 350,
    dpi: int = 300,
) -> bytes | None:
    """Render a side-by-side comparison of two molecules as PNG."""
    target_mol = _mol_from_smiles(target_smi)
    patent_mol = _mol_from_smiles(patent_smi)
    if target_mol is None or patent_mol is None:
        return None

    _prepare_mol_2d(target_mol)
    _prepare_mol_2d(patent_mol)

    png_bytes = _try_comparison_cairo(target_mol, patent_mol, width, height)
    if png_bytes is not None:
        return png_bytes

    svg_text = render_comparison_svg(target_smi, patent_smi, width, height)
    if svg_text is not None:
        png_bytes = _svg_to_png(svg_text, width, dpi)
        if png_bytes is not None:
            return png_bytes

    return _try_comparison_pil(target_mol, patent_mol, width, height)
