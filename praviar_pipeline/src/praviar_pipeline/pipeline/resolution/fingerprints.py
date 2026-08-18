"""Fingerprint and functional-group helpers for Step 1 compound resolution."""

from __future__ import annotations

from praviar_pipeline.config import get_settings


def compute_scaffold_smiles(smiles: str) -> str:
    """Return the Murcko scaffold SMILES for a compound, or empty string on failure.

    The Murcko scaffold strips side chains and retains the ring system with
    connecting linkers. Searching both the full structure and the scaffold
    expands structural matching for genus/Markush claims that use the core
    ring system as a key feature; no recall improvement is assumed.

    Returns an empty string if RDKit cannot parse the input or if the
    molecule has no rings (acyclic compounds have no meaningful scaffold).
    """
    try:
        from rdkit import Chem
        from rdkit.Chem.Scaffolds.MurckoScaffold import GetScaffoldForMol

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return ""
        scaffold = GetScaffoldForMol(mol)
        if scaffold is None or scaffold.GetNumAtoms() == 0:
            return ""
        return Chem.MolToSmiles(scaffold)
    except Exception:
        return ""


def strip_salts_and_stereo(smiles: str) -> tuple[str, str]:
    """Return (free_base_smiles, stereo_stripped_smiles) for a compound SMILES.

    free_base_smiles:
        Largest organic fragment after salt removal (e.g. HCl, Na, K counter-
        ions are discarded).  Empty string if the input cannot be parsed.

    stereo_stripped_smiles:
        Canonical SMILES with all stereocentres and double-bond geometry
        annotations removed.  Useful for searching patents on the racemate or
        achiral scaffold when the input is a single enantiomer.  Empty string
        if the input cannot be parsed.

    Pharmaceutical salts handled:
        RDKit's SaltRemover uses its built-in salt list which covers HCl, HBr,
        Na+, K+, Ca2+, Mg2+, sulfate, phosphate, acetate, and many more common
        pharmaceutical counter-ions and solvates.
    """
    free_base = ""
    stereo_stripped = ""
    try:
        from rdkit import Chem
        from rdkit.Chem.SaltRemover import SaltRemover

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return free_base, stereo_stripped

        remover = SaltRemover()
        stripped_mol = remover.StripMol(mol, dontRemoveEverything=True)
        if stripped_mol is not None and stripped_mol.GetNumAtoms() > 0:
            free_base = Chem.MolToSmiles(stripped_mol)

        # Remove stereo annotations from the original (not salt-stripped) mol
        mol_no_stereo = Chem.RWMol(mol)
        Chem.RemoveStereochemistry(mol_no_stereo)
        stereo_stripped = Chem.MolToSmiles(mol_no_stereo)
    except Exception:
        pass
    return free_base, stereo_stripped


def detect_prodrug_pattern(smiles: str) -> str | None:
    """Return a short description if the SMILES matches a common prodrug pattern.

    Checks for the most prevalent simple prodrug motifs:
      - Ester prodrug: alkyl or aryl ester that may be hydrolysed in vivo to
        release a carboxylic acid drug.
      - Phosphate prodrug: phosphate ester (fosamprenavir, tenofovir prodrugs).
      - Carbamate prodrug: N-linked carbamate that releases an amine drug.

    Returns None when no prodrug pattern is matched, or a short human-readable
    description string when a pattern is found.  This is advisory only — the
    pipeline uses the note to widen searches to the activated form.
    """
    try:
        from rdkit import Chem

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None

        prodrug_patterns: list[tuple[str, str]] = [
            # ester of carboxylic acid (R-C(=O)-O-R') where R' is non-H alkyl/aryl
            ("[CX3](=O)[OX2][CX4,cX3]", "ester_prodrug"),
            # phosphate ester
            ("[PX4](=O)([OX2H,OX1-])([OX2])[OX2][#6]", "phosphate_prodrug"),
            # carbamate (N-C(=O)-O)
            ("[NX3][CX3](=O)[OX2][#6]", "carbamate_prodrug"),
            # amide that could be an N-acyl prodrug (less common, flag only)
            ("[NX3][CX3](=O)[CX4][OX2H]", "acyloxyamide_prodrug"),
        ]

        for smarts, label in prodrug_patterns:
            pattern = Chem.MolFromSmarts(smarts)
            if pattern and mol.HasSubstructMatch(pattern):
                return label
    except Exception:
        pass
    return None


def compute_fingerprints(smiles: str) -> tuple[str, str, list[str]]:
    """Compute Morgan and MACCS fingerprints, detect functional groups."""
    from rdkit import Chem
    from rdkit.Chem import rdFingerprintGenerator, rdMolDescriptors

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"RDKit could not parse SMILES: {smiles[:50]}")

    settings = get_settings()
    generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=settings.fingerprint_radius,
        fpSize=settings.fingerprint_nbits,
    )
    morgan = generator.GetFingerprint(mol)
    morgan_hex = morgan.ToBitString()

    maccs = rdMolDescriptors.GetMACCSKeysFingerprint(mol)
    maccs_hex = maccs.ToBitString()

    fg_patterns = {
        "carboxylic_acid": "[CX3](=O)[OX2H1]",
        "amine": "[NX3;H2,H1;!$(NC=O)]",
        "alcohol": "[OX2H]",
        "ester": "[CX3](=O)[OX2H0]",
        "amide": "[NX3][CX3](=[OX1])",
        "ketone": "[CX3](=[OX1])([#6])[#6]",
        "aldehyde": "[CX3H1](=O)[#6]",
        "ether": "[OD2]([#6])[#6]",
        "phenol": "[OX2H][cX3]:[c]",
        "nitrile": "[NX1]#[CX2]",
        "phosphate": "[PX4](=O)([OX2])",
        "sulfonate": "[SX4](=O)(=O)[OX2]",
        "epoxide": "[OX2r3]",
        "lactone": "[CX3](=O)[OX2][CX4]",
        "thiol": "[SX2H]",
    }

    found_groups = []
    for name, smarts in fg_patterns.items():
        pattern = Chem.MolFromSmarts(smarts)
        if pattern and mol.HasSubstructMatch(pattern):
            found_groups.append(name)

    return morgan_hex, maccs_hex, found_groups
