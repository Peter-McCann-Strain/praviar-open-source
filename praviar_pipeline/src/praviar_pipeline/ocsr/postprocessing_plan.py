"""Pure configuration helpers for OCSR SMILES postprocessing."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

ABBREVIATION_MAP: dict[str, str] = {
    "Boc": "C(=O)OC(C)(C)C",
    "Cbz": "C(=O)OCc1ccccc1",
    "Fmoc": "C(=O)OCC1c2ccccc2-c2ccccc21",
    "Ac": "C(=O)C",
    "Bn": "Cc1ccccc1",
    "Bz": "C(=O)c1ccccc1",
    "Ts": "S(=O)(=O)c1ccc(C)cc1",
    "Ms": "S(=O)(=O)C",
    "Tf": "S(=O)(=O)C(F)(F)F",
    "TBS": "[Si](C)(C)C(C)(C)C",
    "TBDMS": "[Si](C)(C)C(C)(C)C",
    "TMS": "[Si](C)(C)C",
    "TIPS": "[Si](C(C)C)(C(C)C)C(C)C",
    "PMB": "Cc1ccc(OC)cc1",
    "MOM": "COC",
    "SEM": "[Si](C)(C)CCOC",
    "Piv": "C(=O)C(C)(C)C",
    "Trt": "C(c1ccccc1)(c1ccccc1)c1ccccc1",
    "Ns": "S(=O)(=O)c1ccc([N+](=O)[O-])cc1",
    "Alloc": "C(=O)OCC=C",
    "Troc": "C(=O)OCC(Cl)(Cl)Cl",
}

DEFAULT_POSTPROCESSING_STEPS: tuple[str, ...] = (
    "strip_artifacts",
    "repair_valence",
    "remove_salts",
    "canonicalise",
)


def default_postprocessing_steps() -> list[str]:
    """Return the configured default postprocessing sequence."""
    return list(DEFAULT_POSTPROCESSING_STEPS)


def build_postprocessing_step_map(
    *,
    strip_ocsr_artifacts: Callable[[str], str],
    canonicalise: Callable[[str], str],
    inchi_round_trip: Callable[[str], str],
    remove_salts: Callable[[str], str],
    recover_salt_form: Callable[[str], str],
    repair_valence: Callable[[str], str],
    normalise_aromaticity: Callable[[str], str],
    recover_stereo_from_pubchem: Callable[[str], str],
) -> dict[str, Callable[[str], str]]:
    """Build the step dispatch table from live module-level callables."""
    return {
        "strip_artifacts": strip_ocsr_artifacts,
        "canonicalise": canonicalise,
        "inchi_round_trip": inchi_round_trip,
        "remove_salts": remove_salts,
        "recover_salt": recover_salt_form,
        "repair_valence": repair_valence,
        "normalise_aromaticity": normalise_aromaticity,
        "recover_stereo": recover_stereo_from_pubchem,
    }
