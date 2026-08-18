"""Beam search reranking with chemical plausibility rules.

Given top-N SMILES candidates from MolScribe beam search,
rerank them using chemical rules (functional group frequency,
valence, charge balance) to prefer chemically plausible structures.

This catches the isocyanide → nitrile class of errors where
the model is confidently wrong but the correct answer is in the
beam search candidates.

The plausibility score also feeds into ensemble voting — when
multiple models disagree, predictions with higher plausibility
get more weight.
"""

from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors

# Functional groups that are rare in pharmaceutical/patent contexts.
# These represent common OCSR misrecognition patterns.
# SMARTS pattern → (name, penalty_multiplier)
RARE_GROUPS: dict[str, tuple[str, float]] = {
    # Original patterns
    "[C-]#[N+]": ("isocyanide", 0.3),  # should usually be C#N (nitrile)
    "[C-]": ("carbanion", 0.3),  # unusual outside organometallics
    "[C]=[C]=[C]": ("allene", 0.5),  # rare in drug molecules
    # Common OCSR misrecognition patterns
    "[O-][O-]": ("peroxide_dianion", 0.3),  # OCSR artifact — almost never real
    "[N-][N-]": ("diazide_dianion", 0.2),  # OCSR artifact
    "[#6]1~[#6]~[#6]1": ("cyclopropane", 0.7),  # rare in pharma, mild penalty
    "[O]~[O]~[O]": ("ozonide", 0.3),  # extremely rare
    "[N+]([O-])([O-])=O": ("over_oxidized_N", 0.4),  # pentavalent nitrogen artifact
}

# Pre-compile SMARTS patterns
_COMPILED_RARE: list = []


def _get_rare_patterns() -> list[tuple[Chem.rdchem.Mol, str, float]]:
    """Lazily compile SMARTS patterns."""
    global _COMPILED_RARE
    if not _COMPILED_RARE:
        for smarts, (name, penalty) in RARE_GROUPS.items():
            mol = Chem.MolFromSmarts(smarts)
            if mol:
                _COMPILED_RARE.append((mol, name, penalty))
    return _COMPILED_RARE


def score_plausibility(smiles: str) -> float:
    """Score a SMILES string for chemical plausibility (0-1, higher=better).

    Combines substructure-based penalties (rare functional groups) with
    molecular property checks (size, charge, radical count).  Designed to
    softly penalize common OCSR error modes without rejecting valid but
    unusual structures.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return 0.0

    score = 1.0

    # Check for rare functional groups
    for pattern, _name, penalty in _get_rare_patterns():
        if mol.HasSubstructMatch(pattern):
            score *= penalty

    # Charge balance — prefer neutral or singly charged molecules
    charge = Chem.GetFormalCharge(mol)
    if abs(charge) > 2:
        score *= 0.4
    elif abs(charge) == 2:
        score *= 0.7

    # Very small molecules (< 3 heavy atoms) are suspicious as standalone OCSR output
    n_heavy = mol.GetNumHeavyAtoms()
    if n_heavy < 3:
        score *= 0.5

    # Radical electrons — OCSR frequently produces accidental radicals
    n_radicals = Descriptors.NumRadicalElectrons(mol)
    if n_radicals > 0:
        score *= 0.5

    # Very high molecular weight suggests concatenated/hallucinated structure
    # ``Descriptors.MolWt`` is a dynamic alias for this same RDKit function.
    mw = rdMolDescriptors._CalcMolWt(mol)
    if mw > 1500:
        score *= 0.6

    # Floor: prevent near-zero scores from cascading penalties
    return max(score, 0.05)


def rerank_candidates(
    candidates: list[dict],
    plausibility_weight: float = 2.0,
) -> list[dict]:
    """Rerank beam search candidates by combined model score + plausibility.

    Args:
        candidates: List of dicts with 'smiles', 'score', 'valid' keys.
        plausibility_weight: Weight for plausibility score relative to model score.

    Returns:
        Sorted list of candidates (best first) with added 'combined_score' and
        'plausibility' fields.
    """
    # First pass: collect valid candidates with plausibility scores
    valid_entries = []
    invalid_entries = []
    for cand in candidates:
        smi = cand.get("smiles", "")
        model_score = cand.get("score", 0.0)
        valid = cand.get("valid", False)

        if not valid or not smi:
            invalid_entries.append(
                {
                    **cand,
                    "plausibility": 0.0,
                    "combined_score": -999.0,
                }
            )
            continue

        plausibility = score_plausibility(smi)
        valid_entries.append(
            {
                **cand,
                "plausibility": round(plausibility, 4),
                "raw_model_score": model_score,
            }
        )

    # Normalize model scores to [0, 1] so plausibility has equal influence
    if valid_entries:
        raw_scores = [e["raw_model_score"] for e in valid_entries]
        s_min, s_max = min(raw_scores), max(raw_scores)
        s_range = s_max - s_min if s_max > s_min else 1.0
        for entry in valid_entries:
            norm_score = (entry["raw_model_score"] - s_min) / s_range
            combined = norm_score + plausibility_weight * entry["plausibility"]
            entry["combined_score"] = round(combined, 4)

    scored = valid_entries + invalid_entries
    scored.sort(key=lambda x: x["combined_score"], reverse=True)
    return scored


def select_best(
    candidates: list[dict],
    plausibility_weight: float = 2.0,
) -> dict:
    """Select the best SMILES from beam candidates after reranking.

    Returns the top-ranked candidate dict.
    """
    ranked = rerank_candidates(candidates, plausibility_weight)
    if not ranked:
        return {"smiles": "", "confidence": 0.0, "valid": False}
    return ranked[0]
