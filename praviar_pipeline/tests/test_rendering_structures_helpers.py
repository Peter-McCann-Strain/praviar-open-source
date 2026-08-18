"""Focused tests for praviar_pipeline.rendering.structures helper modules."""

from __future__ import annotations

import pytest

pytest.importorskip("rdkit")

from praviar_pipeline.rendering.structures_helpers import _find_mcs_diff_atoms


def test_find_mcs_diff_atoms_returns_different_atom_lists() -> None:
    from rdkit import Chem

    target = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
    patent = Chem.MolFromSmiles("c1ccccc1")

    assert target is not None
    assert patent is not None

    diff = _find_mcs_diff_atoms(target, patent)
    assert diff is not None

    target_diff, patent_diff = diff
    assert target_diff
    assert patent_diff == []


def test_find_mcs_diff_atoms_same_molecule_returns_no_differences() -> None:
    from rdkit import Chem

    mol = Chem.MolFromSmiles("CCO")
    assert mol is not None

    diff = _find_mcs_diff_atoms(mol, mol)
    assert diff == ([], [])
