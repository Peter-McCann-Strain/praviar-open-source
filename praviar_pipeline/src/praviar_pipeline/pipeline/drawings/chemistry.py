"""Chemistry similarity helpers for drawing analysis."""

from __future__ import annotations

from praviar_pipeline.errors import ConfigurationError, SourceUnavailableError


def compute_tanimoto(smi1: str, smi2: str) -> float:
    """Compute Morgan fingerprint Tanimoto similarity between two SMILES."""
    try:
        from rdkit import Chem
        from rdkit.Chem import DataStructs, rdFingerprintGenerator

        mol1 = Chem.MolFromSmiles(smi1)
        mol2 = Chem.MolFromSmiles(smi2)
        if not mol1 or not mol2:
            raise SourceUnavailableError("rdkit", "chemical similarity input is invalid")
        generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
        fp1 = generator.GetFingerprint(mol1)
        fp2 = generator.GetFingerprint(mol2)
        return DataStructs.TanimotoSimilarity(fp1, fp2)
    except ImportError:
        raise ConfigurationError(
            "RDKit is required for drawing similarity",
            source="rdkit",
            step="drawing_chemistry",
        ) from None
    except SourceUnavailableError:
        raise
    except (ValueError, RuntimeError):
        raise SourceUnavailableError("rdkit", "chemical similarity failed") from None


def check_substructure(query_smi: str, target_smi: str) -> bool:
    """Check whether the query molecule is a substructure of the target."""
    try:
        from rdkit import Chem

        query = Chem.MolFromSmiles(query_smi)
        target = Chem.MolFromSmiles(target_smi)
        if not query or not target:
            raise SourceUnavailableError("rdkit", "substructure input is invalid")
        return target.HasSubstructMatch(query)
    except ImportError:
        raise ConfigurationError(
            "RDKit is required for drawing substructure checks",
            source="rdkit",
            step="drawing_chemistry",
        ) from None
    except SourceUnavailableError:
        raise
    except (ValueError, RuntimeError):
        raise SourceUnavailableError("rdkit", "substructure check failed") from None
