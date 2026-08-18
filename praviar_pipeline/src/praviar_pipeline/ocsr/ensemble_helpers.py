"""Pure helper logic for OCSR ensemble fusion."""

from __future__ import annotations

import math
import re
from collections import Counter

import structlog
from rdkit import Chem
from rdkit.Chem import DataStructs, rdFingerprintGenerator, rdMolDescriptors

from praviar_pipeline.models.drawing import OCSRResult
from praviar_pipeline.ocsr.reranking import rerank_candidates, score_plausibility

logger = structlog.get_logger()


CALIBRATION_PARAMS: dict[str, tuple[float, float]] = {
    "molscribe": (2.499, -0.806),
    "molsight": (0.985, 0.488),
    "decimer": (3.534, -2.477),
    "molnextr": (4.220, 2.089),
    "molgrapher": (2.957, 1.576),
}
DEFAULT_WEIGHTS = {
    "molscribe": 0.732,
    "molsight": 0.918,
    "molnextr": 0.698,
    "molgrapher": 0.798,
    "decimer": 0.650,
}


def calibrate_confidence(
    raw: float,
    model: str,
    *,
    parameters: dict[str, tuple[float, float]] | None = None,
    strict: bool = False,
) -> float:
    params = CALIBRATION_PARAMS if parameters is None else parameters
    if not params or any(
        not math.isfinite(a) or not math.isfinite(b) or a <= 0 for a, b in params.values()
    ):
        raise RuntimeError("Invalid live OCSR calibration parameters")
    if model not in params:
        if strict:
            raise RuntimeError(f"OCSR tool has no verified calibration binding: {model}")
        return raw
    a, b = params[model]
    if a == 1.0 and b == 0.0:
        return raw
    return 1.0 / (1.0 + math.exp(-(a * raw + b)))


def canonical(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    return Chem.MolToSmiles(mol) if mol else ""


def canonical_flat(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return ""
    return Chem.MolToSmiles(mol, isomericSmiles=False)


def main_fragment(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return smiles
    frags = Chem.GetMolFrags(mol, asMols=True)
    if len(frags) <= 1:
        return Chem.MolToSmiles(mol)
    largest = max(frags, key=lambda m: m.GetNumHeavyAtoms())
    return Chem.MolToSmiles(largest)


def vote_key(smiles: str) -> str:
    flat = canonical_flat(smiles)
    if not flat:
        return smiles
    return main_fragment(flat)


def has_ez(smiles: str) -> bool:
    return "/" in smiles or "\\" in smiles


def recover_rgroup_numbers(smiles: str, valid: dict[str, tuple[str, float]]) -> str:
    if not smiles or "*" not in smiles:
        return smiles
    if re.search(r"\[\d+\*\]", smiles):
        return smiles

    flat = canonical_flat(smiles)
    if not flat:
        return smiles

    for tool in ["molsight", "decimer", "molnextr", "molscribe", "molgrapher"]:
        t_data = valid.get(tool)
        if not t_data:
            continue
        t_smi = t_data[0]
        if not re.search(r"\[\d+\*\]", t_smi):
            continue
        if canonical_flat(t_smi) == flat:
            return t_smi

    return smiles


def pick_best_stereo(
    candidates: list[tuple[str, str, float]],
    weights: dict[str, float],
) -> str:
    """Pick the best stereo-annotated SMILES from a vote-equivalent group.

    Vote groups are formed on flat (stereo-stripped) canonical SMILES, so a
    single group can contain candidates whose E/Z bond directions disagree
    (e.g. ``C/C=C/C`` vs ``C/C=C\\C``). The original implementation only
    considered the *presence* of E/Z markers, falling through to weight
    tie-breaking — which let a minority-direction high-weight voter override
    a clear modal direction (Fix B in the MolDet post-mortem).

    Behaviour:
    - Tier 1: prefer candidates with E/Z markers over @-only stereo, both
      over no stereo at all (unchanged).
    - Tier 2 (modal-stereo selection): when the top tier contains multiple
      E/Z candidates, group them by their fully-canonical *isomeric* SMILES
      (RDKit ``MolToSmiles(mol, isomericSmiles=True)``, which distinguishes
      ``/`` from ``\\``). Pick the modal isomeric group; tie-break on summed
      voter weight inside each group.
    - Tier 3: within the chosen subgroup, pick the highest-weight tool
      (unchanged).
    """
    if not candidates:
        return ""

    def _stereo_tier(smi: str) -> int:
        if has_ez(smi):
            return 2
        if "@" in smi:
            return 1
        return 0

    top_tier = max(_stereo_tier(smi) for _, smi, _ in candidates)
    top_group = [c for c in candidates if _stereo_tier(c[1]) == top_tier]

    if top_tier == 2 and len(top_group) > 1:
        # Modal-stereo selection: group by fully-canonical isomeric SMILES so
        # that opposing E/Z directions land in distinct buckets.
        bucket_count: Counter[str] = Counter()
        bucket_weight: dict[str, float] = {}
        bucket_members: dict[str, list[tuple[str, str, float]]] = {}
        for tool, smi, conf in top_group:
            mol = Chem.MolFromSmiles(smi)
            iso_key = Chem.MolToSmiles(mol, isomericSmiles=True) if mol else smi
            bucket_count[iso_key] += 1
            bucket_weight[iso_key] = bucket_weight.get(iso_key, 0.0) + weights.get(tool, 0.5)
            bucket_members.setdefault(iso_key, []).append((tool, smi, conf))

        # Mode by count, tie-break on summed voter weight.
        best_key = max(
            bucket_count,
            key=lambda k: (bucket_count[k], bucket_weight[k]),
        )
        chosen = bucket_members[best_key]
    else:
        chosen = top_group

    chosen.sort(key=lambda item: weights.get(item[0], 0.5), reverse=True)
    return chosen[0][1]


def tanimoto(smiles_a: str, smiles_b: str) -> float:
    m1 = Chem.MolFromSmiles(smiles_a)
    m2 = Chem.MolFromSmiles(smiles_b)
    if not m1 or not m2:
        return 0.0
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    fp1 = generator.GetFingerprint(m1)
    fp2 = generator.GetFingerprint(m2)
    return DataStructs.TanimotoSimilarity(fp1, fp2)


def copy_weights(weights: dict[str, float] | None) -> dict[str, float]:
    return dict(DEFAULT_WEIGHTS if weights is None else weights)


def collect_valid_predictions(
    results: dict[str, OCSRResult],
    *,
    calibration_parameters: dict[str, tuple[float, float]] | None = None,
    calibration_strict: bool = False,
) -> tuple[dict[str, tuple[str, float]], dict[str, str]]:
    valid: dict[str, tuple[str, float]] = {}
    vote_keys: dict[str, str] = {}
    for tool, result in results.items():
        if result.valid and result.smiles and result.confidence_available:
            can = canonical(result.smiles)
            if can:
                valid[tool] = (
                    can,
                    calibrate_confidence(
                        result.confidence,
                        tool,
                        parameters=calibration_parameters,
                        strict=calibration_strict,
                    ),
                )
                vote_keys[tool] = vote_key(can)
    return valid, vote_keys


def boost_weights_by_formula(
    valid: dict[str, tuple[str, float]],
    weights: dict[str, float],
    text_formula: str,
    *,
    boost: float,
) -> dict[str, float]:
    """Boost weights of voters whose RDKit formula matches the patent-text formula.

    The boost magnitude comes from Settings via
    ``DRAWING_ENSEMBLE_FORMULA_BOOST``. Failures in formula computation raise
    instead of being swallowed.
    """
    boosted = dict(weights)
    for tool, (can, _conf) in valid.items():
        mol = Chem.MolFromSmiles(can)
        if not mol:
            raise RuntimeError(
                f"Voter {tool!r} produced canonical SMILES that RDKit cannot parse: {can!r} — "
                "this should never happen because collect_valid_predictions canonicalised it."
            )
        if rdMolDescriptors.CalcMolFormula(mol) == text_formula:
            boosted[tool] = boosted.get(tool, 0.5) + boost
    return boosted


def best_single(valid: dict[str, tuple[str, float]]) -> OCSRResult:
    for tool in ["molscribe", "molsight", "decimer", "molnextr", "molgrapher"]:
        if tool in valid:
            return OCSRResult(
                smiles=valid[tool][0],
                confidence=valid[tool][1],
                valid=True,
                tool=f"ensemble:{tool}",
            )
    return OCSRResult(tool="ensemble", error="No valid predictions from any model")


def confidence_cascade(
    valid: dict[str, tuple[str, float]],
    vote_keys: dict[str, str],
    weights: dict[str, float],
    confidence_threshold: float,
    plausibility_threshold: float,
    beam_candidates: list[dict] | None,
    *,
    molscribe_high_conf: float,
) -> OCSRResult | None:
    ms = valid.get("molscribe")
    ms_key = vote_keys.get("molscribe", "")
    if not ms or ms[1] < confidence_threshold:
        return None

    plaus = score_plausibility(ms[0])
    if plaus >= plausibility_threshold:
        msight = valid.get("molsight")
        msight_key = vote_keys.get("molsight", "")
        if msight and msight_key == ms_key:
            best = pick_best_stereo(
                [("molscribe", ms[0], ms[1]), ("molsight", msight[0], msight[1])],
                weights,
            )
            return OCSRResult(
                smiles=best,
                confidence=max(ms[1], msight[1]),
                valid=True,
                tool="ensemble:molscribe_molsight_agree",
            )
        if ms[1] >= molscribe_high_conf:
            return OCSRResult(
                smiles=ms[0],
                confidence=ms[1],
                valid=True,
                tool="ensemble:molscribe_primary",
            )
        return None

    if beam_candidates:
        ranked = rerank_candidates(beam_candidates)
        if ranked and ranked[0].get("plausibility", 0) >= plausibility_threshold:
            return OCSRResult(
                smiles=ranked[0]["smiles"],
                confidence=ms[1] * ranked[0]["plausibility"],
                valid=True,
                tool="ensemble:beam_reranked",
            )

    for fallback_tool in ["decimer", "molsight", "molnextr", "molgrapher"]:
        fb = valid.get(fallback_tool)
        fb_key = vote_keys.get(fallback_tool, "")
        if fb and fb_key != ms_key:
            fb_plaus = score_plausibility(fb[0])
            if fb_plaus > plaus:
                return OCSRResult(
                    smiles=fb[0],
                    confidence=fb[1] * fb_plaus,
                    valid=True,
                    tool=f"ensemble:{fallback_tool}_plausibility_fallback",
                )

    msight = valid.get("molsight")
    msight_key = vote_keys.get("molsight", "")
    if msight and ms and msight_key != ms_key:
        ms_plaus = score_plausibility(ms[0])
        msight_plaus = score_plausibility(msight[0])
        if msight_plaus > ms_plaus:
            return OCSRResult(
                smiles=msight[0],
                confidence=msight[1],
                valid=True,
                tool="ensemble:molsight_preferred",
            )

    return None


def majority_vote(
    valid: dict[str, tuple[str, float]],
    vote_keys: dict[str, str],
    weights: dict[str, float],
    total_results: int,
    *,
    agreement_ratio_min: float,
    low_agreement_penalty: float,
) -> OCSRResult:
    key_counts = Counter(vote_keys.values())
    best_key, best_count = key_counts.most_common(1)[0]
    group = [(t, can, conf) for t, (can, conf) in valid.items() if vote_keys[t] == best_key]
    best_smi = pick_best_stereo(group, weights)
    best_smi = recover_rgroup_numbers(best_smi, valid)
    best_conf = max(conf for _, _, conf in group)

    n_total = max(total_results, 5)
    agreement_ratio = best_count / n_total
    if agreement_ratio < agreement_ratio_min:
        best_conf *= low_agreement_penalty

    return OCSRResult(
        smiles=best_smi,
        confidence=best_conf,
        valid=True,
        tool=f"ensemble:majority_{best_count}_of_{len(valid)}",
    )


def weighted_majority(
    valid: dict[str, tuple[str, float]],
    vote_keys: dict[str, str],
    weights: dict[str, float],
) -> OCSRResult:
    weighted_votes: dict[str, float] = {}
    for tool in valid:
        key = vote_keys[tool]
        weighted_votes[key] = weighted_votes.get(key, 0) + weights.get(tool, 0.5)

    best_key = max(weighted_votes, key=lambda key: weighted_votes[key])
    group = [(t, can, conf) for t, (can, conf) in valid.items() if vote_keys[t] == best_key]
    best_smi = pick_best_stereo(group, weights)
    best_smi = recover_rgroup_numbers(best_smi, valid)
    best_conf = max(conf for _, _, conf in group)

    return OCSRResult(
        smiles=best_smi,
        confidence=best_conf,
        valid=True,
        tool="ensemble:weighted_majority",
    )
