"""Stereochemistry validation for OCSR outputs.

Stereochemical descriptors can be material to human claim review, while OCSR
outputs may omit or alter them. This module compares structure-level signals so
the report can flag missing stereochemical information; it makes no legal
conclusion and no comparative model-performance claim.

Three signals produced per structure:

1. Stereocenter counts (CIP + E/Z) on OCSR output and on the target SMILES
2. Stereo-keyword detection in the claim text (R/S/E/Z/(+)/(-)/alpha/beta/enantiomer/
   racemate/chiral/stereo-specific/diastereomer)
3. A flag combining them: "ok" | "target_mismatch" | "claim_demands_stereo_but_ocsr_blind" |
   "stereo_blind" | ""

The flag is strictly informational - attorneys make the final call. Surfaced
in DrawingStructure so the report layer can highlight stereo-risk structures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from rdkit import Chem

GREEK_ALPHA = "\u03b1"
GREEK_BETA = "\u03b2"
MINUS_SIGN = "\u2212"

StereoFlag = Literal[
    "",
    "ok",
    "target_mismatch",
    "claim_demands_stereo_but_ocsr_blind",
    "stereo_blind",
]


@dataclass(slots=True, frozen=True)
class StereoValidation:
    ocsr_cip_count: int
    ocsr_ez_count: int
    target_cip_count: int
    target_ez_count: int
    claim_mentions_stereo: bool
    flag: StereoFlag
    details: str


# Keywords that indicate a stereo-aware claim. We match case-insensitively on
# word boundaries so "chiral" doesn't false-match "spirocyclic". The parenthesised
# (+)/(-) descriptors are matched verbatim.
_STEREO_KEYWORDS = [
    r"\b[RS]\s*-\s*enantiomer\b",
    r"\b[RS]-configuration\b",
    rf"\(\s*[+\-{MINUS_SIGN}]\s*\)",  # (+), (-), Unicode minus
    r"\benantiomer(?:ic)?\b",
    r"\bdiastereomer(?:s|ic)?\b",
    r"\bracemate\b",
    r"\bracemic\b",
    r"\bchiral\b",
    r"\bachiral\b",
    r"\bstereo-?specific\b",
    r"\bstereo-?selective\b",
    r"\bstereoisomer\b",
    r"\bstereocenter\b",
    r"\bchiral\s+center\b",
    rf"\b{GREEK_ALPHA}-\s?anomer\b",
    rf"\b{GREEK_BETA}-\s?anomer\b",
    r"\balpha\s+anomer\b",
    r"\bbeta\s+anomer\b",
    r"\bcis-?trans\b",
    r"\([RS]\)\s*-",  # (R)- or (S)-
    r"\([EZ]\)\s*-",  # (E)- or (Z)-
]
_STEREO_RE = re.compile("|".join(_STEREO_KEYWORDS), re.IGNORECASE)


def count_stereocenters(smiles: str) -> tuple[int, int]:
    """Return (cip_stereocenters, ez_double_bonds) for a SMILES string.

    CIP stereocenters: atoms with @/@@ in the canonical form, or atoms whose
    stereochemistry is specified via CIP descriptor. Uses RDKit's
    FindMolChiralCenters with includeUnassigned=False — we only count
    explicitly-assigned centers since OCSR either sets stereo or does not.

    E/Z count: double bonds with explicit /\\ stereo bonds in SMILES. Counted
    via RDKit BondStereo enumeration.

    Invalid SMILES → (0, 0).
    """
    if not smiles:
        return 0, 0
    try:
        mol = Chem.MolFromSmiles(smiles)
    except Exception:
        return 0, 0
    if mol is None:
        return 0, 0

    try:
        cip = Chem.FindMolChiralCenters(mol, includeUnassigned=False)
        cip_count = len(cip)
    except Exception:
        cip_count = 0

    ez_count = 0
    try:
        for bond in mol.GetBonds():
            stereo = bond.GetStereo()
            if stereo in (
                Chem.BondStereo.STEREOE,
                Chem.BondStereo.STEREOZ,
                Chem.BondStereo.STEREOCIS,
                Chem.BondStereo.STEREOTRANS,
            ):
                ez_count += 1
    except Exception:
        pass

    return cip_count, ez_count


def claim_mentions_stereo(text: str) -> bool:
    """True if the patent claim text (or any passed text) includes any stereo
    descriptor our regex catches."""
    if not text:
        return False
    return bool(_STEREO_RE.search(text))


def validate_stereo(
    ocsr_smiles: str,
    target_smiles: str = "",
    claim_text: str = "",
) -> StereoValidation:
    """Compute stereo signals and a combined flag.

    Flag semantics (most severe first):
        "claim_demands_stereo_but_ocsr_blind":
            Claim text explicitly mentions stereo AND OCSR produced zero
            stereocenters. Likely a stereo-stripping model (e.g. MG2) on a
            stereospecific claim.
        "target_mismatch":
            Target has N stereocenters; OCSR has 0. A stereospecific target
            cannot match a stereo-blind OCSR prediction.
        "stereo_blind":
            OCSR produced zero stereocenters (information for the user).
            No target / claim context to escalate.
        "ok":
            OCSR produced >=1 stereocenter (informational positive).
        "":
            No OCSR SMILES to evaluate.
    """
    if not ocsr_smiles:
        return StereoValidation(
            ocsr_cip_count=0,
            ocsr_ez_count=0,
            target_cip_count=0,
            target_ez_count=0,
            claim_mentions_stereo=False,
            flag="",
            details="no OCSR SMILES provided",
        )

    ocsr_cip, ocsr_ez = count_stereocenters(ocsr_smiles)
    tgt_cip, tgt_ez = count_stereocenters(target_smiles) if target_smiles else (0, 0)
    claim_stereo = claim_mentions_stereo(claim_text)

    ocsr_total = ocsr_cip + ocsr_ez
    tgt_total = tgt_cip + tgt_ez

    flag: StereoFlag
    if claim_stereo and ocsr_total == 0:
        flag = "claim_demands_stereo_but_ocsr_blind"
        details = (
            "Claim text indicates stereospecificity but OCSR produced no "
            "stereocenters; verify manually before relying on similarity score."
        )
    elif tgt_total > 0 and ocsr_total == 0:
        flag = "target_mismatch"
        details = (
            f"Target has {tgt_cip} CIP + {tgt_ez} E/Z stereocenters; OCSR has 0. "
            "Stereospecific match cannot be determined."
        )
    elif ocsr_total == 0:
        flag = "stereo_blind"
        details = "OCSR produced no stereocenters (no target or claim context)"
    else:
        flag = "ok"
        details = f"OCSR stereo: {ocsr_cip} CIP + {ocsr_ez} E/Z centers"

    return StereoValidation(
        ocsr_cip_count=ocsr_cip,
        ocsr_ez_count=ocsr_ez,
        target_cip_count=tgt_cip,
        target_ez_count=tgt_ez,
        claim_mentions_stereo=claim_stereo,
        flag=flag,
        details=details,
    )
