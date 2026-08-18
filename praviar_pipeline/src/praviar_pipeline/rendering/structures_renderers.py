"""Rendering strategies for chemical structures."""

from __future__ import annotations

from typing import Any

import structlog

from praviar_pipeline.rendering.structures_helpers import (
    _configure_drawer,
    _find_mcs_diff_atoms,
)

logger = structlog.get_logger()


def _try_cairo_drawer(mol: Any, width: int, height: int) -> bytes | None:
    """Attempt to render PNG via RDKit's Cairo-backed drawer."""
    try:
        from rdkit.Chem.Draw import rdMolDraw2D

        drawer = rdMolDraw2D.MolDraw2DCairo(width, height)
        _configure_drawer(drawer)
        drawer.DrawMolecule(mol)
        drawer.FinishDrawing()
        return bytes(drawer.GetDrawingText())
    except (ImportError, AttributeError, RuntimeError):
        return None
    except Exception:
        logger.warning("cairo_drawer_failed")
        return None


def _try_mol_to_image(mol: Any, width: int, height: int) -> bytes | None:
    """PIL-based fallback for PNG generation."""
    try:
        import io

        from rdkit.Chem.Draw import MolToImage

        img = MolToImage(mol, size=(width, height))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        logger.warning("pil_not_available")
        return None
    except Exception:
        logger.warning("mol_to_image_failed")
        return None


def _try_comparison_cairo(
    target_mol: Any,
    patent_mol: Any,
    width: int,
    height: int,
) -> bytes | None:
    """Attempt comparison PNG via RDKit Cairo drawer."""
    try:
        from rdkit.Chem.Draw import rdMolDraw2D

        highlight_target: list[int] = []
        highlight_patent: list[int] = []
        diff = _find_mcs_diff_atoms(target_mol, patent_mol)
        if diff is not None:
            highlight_target, highlight_patent = diff

        drawer = rdMolDraw2D.MolDraw2DCairo(width, height, width // 2, height)
        _configure_drawer(drawer)
        opts = drawer.drawOptions()
        opts.setHighlightColour((0.84, 0.37, 0.0, 0.3))

        drawer.DrawMolecules(
            [target_mol, patent_mol],
            legends=["Target Compound", "Patented Compound"],
            highlightAtoms=[highlight_target, highlight_patent],
        )
        drawer.FinishDrawing()
        return bytes(drawer.GetDrawingText())
    except (ImportError, AttributeError, RuntimeError):
        return None
    except Exception:
        logger.warning("cairo_comparison_failed")
        return None


def _try_comparison_pil(
    target_mol: Any,
    patent_mol: Any,
    width: int,
    height: int,
) -> bytes | None:
    """PIL-based fallback for comparison PNG."""
    try:
        import io

        from rdkit.Chem.Draw import MolsToGridImage

        diff = _find_mcs_diff_atoms(target_mol, patent_mol)
        highlight_atoms: list[list[int]] = [[], []]
        if diff is not None:
            highlight_atoms = [diff[0], diff[1]]

        img = MolsToGridImage(
            [target_mol, patent_mol],
            molsPerRow=2,
            subImgSize=(width // 2, height),
            legends=["Target Compound", "Patented Compound"],
            highlightAtomLists=highlight_atoms,
        )
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        logger.warning("pil_grid_not_available")
        return None
    except Exception:
        logger.warning("comparison_pil_failed")
        return None
