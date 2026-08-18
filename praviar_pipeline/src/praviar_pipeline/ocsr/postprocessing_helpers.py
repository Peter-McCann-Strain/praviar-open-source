"""Pure helper logic for OCSR SMILES postprocessing."""

from __future__ import annotations

from typing import Any

SUSPICIOUS_COUNTERIONS = frozenset({"[HH]", "[H][H]", "*", "[Chiral]", "[Compound]"})


def split_fragments(smiles: str) -> list[str]:
    """Split a disconnected SMILES string into trimmed fragments."""
    return [fragment.strip() for fragment in smiles.split(".") if fragment.strip()]


def is_trivial_fragment(fragment: str) -> bool:
    """Return True for fragments that are clearly non-chemical artifacts."""
    fragment = fragment.strip()
    if not fragment or fragment in {"*", "[HH]"}:
        return True
    return all(char in "*.()" for char in fragment)


def clean_fragments(smiles: str) -> list[str]:
    """Return canonical SMILES fragments after filtering obvious artifacts."""
    from rdkit import Chem

    cleaned: list[str] = []
    for fragment in split_fragments(smiles):
        if is_trivial_fragment(fragment):
            continue
        mol = Chem.MolFromSmiles(fragment)
        if mol is not None and mol.GetNumAtoms() > 0:
            cleaned.append(Chem.MolToSmiles(mol))
    return cleaned


def fragment_records(smiles: str) -> list[tuple[str, Any, int]]:
    """Return valid fragments with their RDKit molecule and heavy-atom count."""
    from rdkit import Chem

    records: list[tuple[str, Any, int]] = []
    for fragment in split_fragments(smiles):
        mol = Chem.MolFromSmiles(fragment)
        if mol is not None:
            records.append((fragment, mol, mol.GetNumHeavyAtoms()))
    return records


def has_suspicious_counterions(records: list[tuple[str, Any, int]]) -> bool:
    """Return True when any non-primary fragment looks like an OCR artifact."""
    return any(fragment in SUSPICIOUS_COUNTERIONS for fragment, _, _ in records[1:])


def largest_fragment_smiles(smiles: str) -> str | None:
    """Return the canonical SMILES for the largest fragment, if any."""
    from rdkit import Chem

    records = fragment_records(smiles)
    if not records:
        return None
    records.sort(key=lambda record: record[2], reverse=True)
    _, mol, _ = records[0]
    return Chem.MolToSmiles(mol)
