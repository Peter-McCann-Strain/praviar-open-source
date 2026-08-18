"""RDKit-backed OCSR postprocessing transforms."""

from __future__ import annotations

from praviar_pipeline.ocsr.postprocessing_helpers import largest_fragment_smiles


def canonicalise(smiles: str) -> str:
    """Canonicalise SMILES via RDKit round-trip."""
    try:
        from rdkit import Chem

        mol = Chem.MolFromSmiles(smiles)
        if mol is not None:
            return Chem.MolToSmiles(mol)
    except Exception:
        pass
    return smiles


def to_inchi_key(smiles: str) -> str:
    """Convert SMILES to InChI key for database cross-reference."""
    try:
        from rdkit import Chem
        from rdkit.Chem.inchi import InchiToInchiKey, MolToInchi

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return ""
        inchi = MolToInchi(mol)
        if inchi is None:
            return ""
        return str(InchiToInchiKey(inchi))
    except Exception:
        return ""


def inchi_round_trip(smiles: str) -> str:
    """Normalise SMILES via InChI round-trip."""
    try:
        from rdkit import Chem
        from rdkit.Chem.inchi import MolFromInchi, MolToInchi

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return smiles
        inchi = MolToInchi(mol)
        if inchi is None:
            return smiles
        mol2 = MolFromInchi(inchi)
        if mol2 is None:
            return smiles
        return Chem.MolToSmiles(mol2)
    except Exception:
        return smiles


def remove_salts(smiles: str) -> str:
    """Remove salts and small fragments, keeping the largest fragment."""
    try:
        from rdkit import Chem
        from rdkit.Chem.SaltRemover import SaltRemover

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return smiles

        remover = SaltRemover()
        stripped = remover.StripMol(mol)
        if stripped.GetNumAtoms() > 0:
            return Chem.MolToSmiles(stripped)

        largest = largest_fragment_smiles(smiles)
        if largest is None:
            return smiles
        return largest
    except Exception:
        return smiles


def repair_valence(smiles: str) -> str:
    """Attempt to fix valence errors by sanitizing with RDKit."""
    try:
        from rdkit import Chem

        mol = Chem.MolFromSmiles(smiles, sanitize=False)
        if mol is None:
            return smiles

        try:
            Chem.SanitizeMol(mol)
            return Chem.MolToSmiles(mol)
        except Exception:
            try:
                Chem.SanitizeMol(
                    mol,
                    Chem.SanitizeFlags.SANITIZE_ALL ^ Chem.SanitizeFlags.SANITIZE_PROPERTIES,
                )
                return Chem.MolToSmiles(mol)
            except Exception:
                return smiles
    except Exception:
        return smiles


def normalise_aromaticity(smiles: str) -> str:
    """Normalise aromatic representation via Kekulize/aromatize round-trip."""
    try:
        from rdkit import Chem

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return smiles
        Chem.Kekulize(mol, clearAromaticFlags=True)
        Chem.SetAromaticity(mol)
        return Chem.MolToSmiles(mol)
    except Exception:
        return smiles
