"""PubChem-backed OCSR postprocessing helpers."""

from __future__ import annotations

import json
import urllib.request

from praviar_pipeline.ocsr.postprocessing_helpers import (
    fragment_records,
    has_suspicious_counterions,
)


def recover_stereo_from_pubchem(smiles: str) -> str:
    """Attempt to recover stereochemistry by matching InChI connectivity in PubChem."""
    try:
        from rdkit import Chem
        from rdkit.Chem.inchi import InchiToInchiKey, MolToInchi

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return smiles

        inchi = MolToInchi(mol)
        if not inchi:
            return smiles

        inchi_key = InchiToInchiKey(inchi)
        if not inchi_key:
            return smiles

        conn_key = inchi_key[:14]
        for key in [inchi_key, conn_key]:
            url = (
                f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound"
                f"/inchikey/{key}/property/CanonicalSMILES,IsomericSMILES/JSON"
            )
            try:
                # URL origin is hard-coded HTTPS; the path key is RDKit-normalized.
                with urllib.request.urlopen(url, timeout=10) as resp:  # nosec B310
                    data = json.loads(resp.read())
                    props = data.get("PropertyTable", {}).get("Properties", [])
                    if props:
                        iso = props[0].get("IsomericSMILES", "")
                        if isinstance(iso, str) and iso and iso != smiles:
                            return iso
                        can = props[0].get("CanonicalSMILES", "")
                        if isinstance(can, str) and can and can != smiles:
                            return can
            except Exception:
                continue

        return smiles
    except Exception:
        return smiles


def recover_salt_form(smiles: str) -> str:
    """Look up PubChem for the correct salt form when counterions are suspicious."""
    if "." not in smiles:
        return smiles

    try:
        from rdkit import Chem
        from rdkit.Chem.inchi import InchiToInchiKey, MolToInchi

        frag_mols = fragment_records(smiles)
        if not frag_mols:
            return smiles

        frag_mols.sort(key=lambda x: x[2], reverse=True)
        _, main_mol, _ = frag_mols[0]

        if not has_suspicious_counterions(frag_mols):
            return smiles

        inchi = MolToInchi(main_mol)
        if not inchi:
            return smiles
        inchi_key = InchiToInchiKey(inchi)
        if not inchi_key:
            return smiles

        url = (
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound"
            f"/inchikey/{inchi_key}/property/IsomericSMILES/JSON"
        )
        try:
            # URL origin is hard-coded HTTPS; the path key is RDKit-normalized.
            with urllib.request.urlopen(url, timeout=10) as resp:  # nosec B310
                data = json.loads(resp.read())
                props = data.get("PropertyTable", {}).get("Properties", [])
                if props:
                    pubchem_smi = props[0].get("IsomericSMILES", "")
                    if isinstance(pubchem_smi, str) and "." in pubchem_smi:
                        return pubchem_smi
        except Exception:
            pass

        return Chem.MolToSmiles(main_mol)
    except Exception:
        return smiles
