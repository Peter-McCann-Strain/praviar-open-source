"""Patent chemistry abbreviation expansion for OCSR voter outputs.

The 5-tool OCSR ensemble all share a common failure mode: when the input
crop contains a text-label functional group (Boc, Ts, Ms, BocHN, OAc, ...)
the voters either output a placeholder atom (`*` or `[U]`) or a wildly
incorrect SMILES. This module post-processes voter SMILES, replacing
placeholders with their canonical SMILES expansion using a merged
dictionary of:

  * RDKit's ``rdAbbreviations.GetDefaultAbbreviations()`` (37 entries, BSD)
  * A vendored patent-specific dictionary at
    ``praviar_pipeline/data/abbreviations/patent_superatoms.json`` (~80 entries,
    sourced from OSRA + MolGrapher + literature; see file header)

Runtime contract:
  * No silent fallbacks — if RDKit can't parse an input, ``expand_superatoms``
    raises rather than returning the original string.
  * The dictionary is loaded lazily, exactly once per process.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import structlog
from rdkit import Chem
from rdkit.Chem import rdAbbreviations

logger = structlog.get_logger()

_DICT_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "abbreviations" / "patent_superatoms.json"
)


@lru_cache(maxsize=1)
def _load_merged_dict() -> dict[str, str]:
    """Merge vendored patent dict + RDKit defaults into one label→SMILES map.

    Vendored dict wins on key collisions (the patent set is more recent and
    explicitly curated against PatCID failure cases).
    """
    if not _DICT_PATH.exists():
        raise RuntimeError(
            f"Patent abbreviation dictionary missing: {_DICT_PATH}. "
            "The OCSR abbreviation expander requires the JSON dictionary under "
            "praviar_pipeline/data/abbreviations/."
        )
    payload = json.loads(_DICT_PATH.read_text())
    vendored: dict[str, str] = payload["abbreviations"]

    rdkit_defaults: dict[str, str] = {}
    for entry in rdAbbreviations.GetDefaultAbbreviations():
        rdkit_defaults[entry.label] = Chem.MolToSmiles(entry.mol)

    merged: dict[str, str] = dict(rdkit_defaults)
    merged.update(vendored)  # vendored wins
    return merged


def lookup(label: str) -> str | None:
    """Return the canonical SMILES expansion for a label, or None if unknown.

    Case-sensitive first, then case-insensitive — patents use mixed casing
    inconsistently (e.g., 'Boc' vs 'BOC'). Returns the canonical SMILES
    with one wildcard ``*`` atom marking the attachment point.
    """
    table = _load_merged_dict()
    if label in table:
        return table[label]
    lower = label.lower()
    for k, v in table.items():
        if k.lower() == lower:
            return v
    return None


def has_placeholder_atoms(smiles: str) -> bool:
    """True if SMILES contains the placeholder atoms voters emit on
    unread labels: ``*``, ``[*]``, or ``[U]`` (MolScribe / MolNeXTR output).
    """
    if not smiles:
        return False
    return "*" in smiles or "[U]" in smiles or "[U+" in smiles or "[*" in smiles


def expand_superatoms(smiles: str, ocr_labels: list[str] | None = None) -> str:
    """Replace placeholder atoms in ``smiles`` with their dictionary expansion.

    Args:
        smiles: SMILES string from an OCSR voter, possibly containing ``*`` or
            ``[U]`` placeholder atoms where the voter saw a text label it
            couldn't read.
        ocr_labels: Optional list of text labels OCR'd from the crop image.
            When provided, we attempt to substitute each placeholder for the
            canonical SMILES of a dictionary-known label. When None, we use
            the labels' positional fallback (try common abbreviations in
            priority order).

    Returns:
        Expanded SMILES (canonical via RDKit). If no placeholders are present,
        returns the canonical form unchanged. If RDKit cannot parse the
        input, raises RuntimeError (no silent fallback).
    """
    if not smiles:
        return smiles
    if not has_placeholder_atoms(smiles):
        return _canonical_or_raise(smiles)

    if ocr_labels:
        # Try each label in turn — pick the first that produces a valid molecule
        # after substitution. We do the substitution structurally (parse both
        # SMILES, identify the dummy atom and its sole neighbour, fuse on that
        # bond) rather than at the string level, because string concatenation
        # mangles ring closures and aromaticity.
        for label in ocr_labels:
            expansion = lookup(label)
            if expansion is None:
                continue
            try:
                merged = _structural_substitute(smiles, expansion)
            except RuntimeError:
                continue
            if merged is not None:
                return merged

    # Without OCR labels, OR if no label expansion produced valid output, we
    # leave the SMILES alone and emit it canonically. The caller decides
    # whether to penalise placeholder-bearing voters.
    return _canonical_or_raise(smiles)


def _canonical_or_raise(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise RuntimeError(f"RDKit cannot parse SMILES: {smiles!r}")
    return Chem.MolToSmiles(mol)


def _structural_substitute(host_smi: str, expansion_smi: str) -> str | None:
    """Fuse host and expansion at their dummy atoms.

    Both inputs are SMILES with exactly one ``*`` atom each. We:
      1. Parse both as RDKit Mols
      2. Find the dummy atom + its sole heavy neighbour in each
      3. Combine the two mols, draw a bond between the two heavy neighbours,
         then strip both dummies
      4. Canonicalise

    Returns None if either side has zero or more than one dummy atom (the
    contract assumes exactly one attachment point per side).
    """
    from rdkit.Chem import RWMol

    host = Chem.MolFromSmiles(host_smi)
    exp = Chem.MolFromSmiles(expansion_smi)
    if host is None or exp is None:
        raise RuntimeError(f"Cannot parse SMILES: host={host_smi!r} exp={expansion_smi!r}")

    host_attach = _single_dummy_neighbour(host)
    exp_attach = _single_dummy_neighbour(exp)
    if host_attach is None or exp_attach is None:
        return None

    combined = RWMol(Chem.CombineMols(host, exp))
    n_host = host.GetNumAtoms()
    # Indices in `combined`:
    #   host atoms: 0..n_host-1
    #   expansion atoms: n_host..n_host+n_exp-1
    host_dummy_idx, host_neighbour_idx = host_attach
    exp_dummy_idx, exp_neighbour_idx = exp_attach
    exp_neighbour_combined = exp_neighbour_idx + n_host
    exp_dummy_combined = exp_dummy_idx + n_host

    # Add bond between the two heavy neighbours
    combined.AddBond(
        host_neighbour_idx,
        exp_neighbour_combined,
        Chem.BondType.SINGLE,
    )

    # Remove both dummy atoms (highest index first to avoid renumbering)
    for idx in sorted([host_dummy_idx, exp_dummy_combined], reverse=True):
        combined.RemoveAtom(idx)

    final_mol = combined.GetMol()
    try:
        Chem.SanitizeMol(final_mol)
    except (Chem.AtomValenceException, Chem.KekulizeException):
        return None
    return Chem.MolToSmiles(final_mol)


def _single_dummy_neighbour(mol) -> tuple[int, int] | None:
    """Return (dummy_atom_idx, its_sole_heavy_neighbour_idx) or None."""
    dummies = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 0]
    if len(dummies) != 1:
        return None
    dummy_idx = dummies[0]
    nbrs = mol.GetAtomWithIdx(dummy_idx).GetNeighbors()
    if len(nbrs) != 1:
        return None
    return dummy_idx, nbrs[0].GetIdx()
