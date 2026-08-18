"""Pure helper logic for OCSR text validation."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import DataStructs, rdFingerprintGenerator, rdMolDescriptors
from rdkit.Chem.inchi import InchiToInchiKey, MolToInchi

# Vendored superatom dictionary used to filter candidate abbreviation tokens out
# of patent text. The same JSON is read by
# ``praviar_pipeline.ocsr.abbreviations`` for placeholder expansion; here we only
# need the set of known labels.
_SUPERATOM_DICT_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "abbreviations" / "patent_superatoms.json"
)

# Tokens of length < 2 are ambiguous (e.g. single letters, digits) and tokens
# of length > 10 are almost certainly not abbreviation labels in practice.
_ABBREV_MIN_LEN = 2
_ABBREV_MAX_LEN = 10

# Tokenizer for abbreviation candidates: split on whitespace and a wide set of
# common patent-text separators including hyphens (so ``Boc-protected`` yields
# the candidate token ``Boc``). The vendored dictionary contains no
# hyphenated keys today, so this split is safe; if hyphenated entries are
# added in future the tokenizer will need a second pass to recombine them.
_ABBREV_TOKEN_RE = re.compile(r"[\s,;:()\[\]{}\"'/\\\-]+")

# Molecular formula: C12H22O11, C6H12O6, etc.
_FORMULA_RE = re.compile(
    r"\b(C\d{1,3}H\d{1,3}"
    r"(?:Br\d{0,2})?"
    r"(?:Cl\d{0,2})?"
    r"(?:F\d{0,2})?"
    r"(?:I\d{0,2})?"
    r"(?:N\d{0,3})?"
    r"(?:O\d{0,3})?"
    r"(?:P\d{0,2})?"
    r"(?:S\d{0,2})?"
    r")\b"
)

# CAS Registry Number: 50-78-2, 69-72-7, 123456-78-9
_CAS_RE = re.compile(r"\b(\d{2,7}-\d{2}-\d)\b")

# IUPAC-like chemical names (simplified — catches common patterns)
_IUPAC_PATTERNS = [
    re.compile(
        r"\b(\d[,\d]*-(?:di|tri|tetra|penta|hexa)?"
        r"(?:amino|bromo|chloro|fluoro|hydroxy|methyl|ethyl|propyl|butyl|"
        r"phenyl|nitro|oxo|carboxy|sulfo|mercapto|cyano)"
        r"[a-z]*(?:ane|ene|yne|ol|al|one|oic acid|amine|amide|ester|ether|"
        r"benzene|pyridine|furan|thiophene|pyrrole|indole|naphthalene))"
        r"\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b([A-Z][a-z]{2,}(?:ib|mab|nib|zumab|tinib|ciclib|rafenib|"
        r"prazole|sartan|statin|olol|dipine|mycin|cillin|floxacin|"
        r"azole|avir|udine))\b"
    ),
]


@lru_cache(maxsize=1)
def _load_superatom_labels() -> frozenset[str]:
    """Load the set of known superatom labels from the vendored JSON dict.

    Cached at module level — the dictionary is small (~80 entries) and read
    only once per process. Errors propagate (no silent fallback) per the
    Praviar Pipeline "no silent degradation" contract.
    """
    if not _SUPERATOM_DICT_PATH.exists():
        raise RuntimeError(
            f"Patent abbreviation dictionary missing: {_SUPERATOM_DICT_PATH}. "
            "The OCSR abbreviation text filter requires the JSON dictionary under "
            "praviar_pipeline/data/abbreviations/."
        )
    payload = json.loads(_SUPERATOM_DICT_PATH.read_text())
    return frozenset(payload["abbreviations"].keys())


def extract_molecular_formulas(text: str) -> list[str]:
    """Extract molecular formulas from patent text."""
    return list(set(_FORMULA_RE.findall(text)))


def extract_cas_numbers(text: str) -> list[str]:
    """Extract CAS Registry Numbers from patent text."""
    candidates = _CAS_RE.findall(text)
    validated = []
    for cas in candidates:
        parts = cas.split("-")
        if len(parts) != 3:
            continue
        digits = parts[0] + parts[1]
        check = int(parts[2])
        total = sum(int(d) * (i + 1) for i, d in enumerate(reversed(digits)))
        if total % 10 == check:
            validated.append(cas)
    return validated


def extract_chemical_names(text: str) -> list[str]:
    """Extract IUPAC-like chemical names from patent text."""
    names: list[str] = []
    for pattern in _IUPAC_PATTERNS:
        names.extend(pattern.findall(text))
    return list(set(names))


def extract_abbreviation_labels(patent_text: str) -> list[str]:
    """Extract candidate abbreviation tokens from patent text for OCR-label matching.

    Looks for tokens that appear in the merged superatom dictionary
    (``praviar_pipeline/data/abbreviations/patent_superatoms.json``). Used as an
    OCR-label hint for ``ensemble.fuse(ocr_labels=...)`` to expand placeholder
    atoms (``*``, ``[U]``, ``[*]``) in voter SMILES output.

    Matching is case-sensitive (``Boc`` != ``boc``) — patent abbreviations
    have specific casing conventions and case-folding would create false
    positives. Tokens shorter than 2 chars or longer than 10 chars are
    filtered out as noise.

    Args:
        patent_text: Raw patent text (e.g. claim/spec excerpt near a drawing).

    Returns:
        Unique list of abbreviation labels found, preserving first-seen order.
    """
    if not patent_text:
        return []

    known = _load_superatom_labels()
    seen: set[str] = set()
    out: list[str] = []
    for raw in _ABBREV_TOKEN_RE.split(patent_text):
        # Strip trailing punctuation that the tokenizer leaves attached
        # (e.g. trailing periods at end of sentences).
        token = raw.strip(".")
        if not token:
            continue
        if not (_ABBREV_MIN_LEN <= len(token) <= _ABBREV_MAX_LEN):
            continue
        if token in known and token not in seen:
            seen.add(token)
            out.append(token)
    return out


def smiles_to_formula(smiles: str) -> str:
    """Convert SMILES to molecular formula string."""
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return ""
        return rdMolDescriptors.CalcMolFormula(mol)
    except Exception:
        return ""


def smiles_to_inchi_key(smiles: str) -> str:
    """Convert SMILES to InChI key."""
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return ""
        inchi = MolToInchi(mol)
        if inchi is None:
            return ""
        return str(InchiToInchiKey(inchi))
    except Exception:
        return ""


def tanimoto(smi1: str, smi2: str) -> float:
    """Compute Tanimoto similarity between two SMILES."""
    try:
        m1 = Chem.MolFromSmiles(smi1)
        m2 = Chem.MolFromSmiles(smi2)
        if not m1 or not m2:
            return 0.0
        generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
        fp1 = generator.GetFingerprint(m1)
        fp2 = generator.GetFingerprint(m2)
        return DataStructs.TanimotoSimilarity(fp1, fp2)
    except Exception:
        return 0.0
