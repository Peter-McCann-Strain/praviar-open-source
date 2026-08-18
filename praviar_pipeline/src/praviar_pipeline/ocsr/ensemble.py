"""Ensemble fusion for multi-model OCSR."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal

import structlog

from praviar_pipeline.models.drawing import OCSRResult
from praviar_pipeline.ocsr.ensemble_helpers import (
    CALIBRATION_PARAMS as _CALIBRATION_PARAMS,
)
from praviar_pipeline.ocsr.ensemble_helpers import (
    DEFAULT_WEIGHTS as _DEFAULT_WEIGHTS,
)
from praviar_pipeline.ocsr.ensemble_helpers import (
    best_single as _best_single_impl,
)
from praviar_pipeline.ocsr.ensemble_helpers import (
    boost_weights_by_formula as _boost_weights_by_formula_impl,
)
from praviar_pipeline.ocsr.ensemble_helpers import (
    calibrate_confidence as _calibrate_confidence_impl,
)
from praviar_pipeline.ocsr.ensemble_helpers import (
    canonical as _canonical_impl,
)
from praviar_pipeline.ocsr.ensemble_helpers import (
    collect_valid_predictions as _collect_valid_predictions_impl,
)
from praviar_pipeline.ocsr.ensemble_helpers import (
    confidence_cascade as _confidence_cascade_impl,
)
from praviar_pipeline.ocsr.ensemble_helpers import (
    copy_weights as _copy_weights_impl,
)
from praviar_pipeline.ocsr.ensemble_helpers import (
    majority_vote as _majority_vote_impl,
)
from praviar_pipeline.ocsr.ensemble_helpers import (
    tanimoto as _tanimoto_impl,
)
from praviar_pipeline.ocsr.ensemble_helpers import (
    vote_key as _vote_key_impl,
)
from praviar_pipeline.ocsr.ensemble_helpers import (
    weighted_majority as _weighted_majority_impl,
)

CALIBRATION_PARAMS = _CALIBRATION_PARAMS
DEFAULT_WEIGHTS = _DEFAULT_WEIGHTS

Strategy = Literal[
    "confidence_cascade",
    "majority_vote",
    "weighted_majority",
    "best_single",
]


@dataclass(frozen=True, slots=True)
class EnsembleRunConfig:
    """Immutable per-analysis fusion and calibration configuration."""

    molscribe_high_conf: float
    agreement_ratio_min: float
    low_agreement_penalty: float
    formula_boost: float
    text_confirm_conf_bump: float
    plausibility_threshold: float
    min_resolved_conf: float
    max_resolved_atoms: int
    calibration_parameters: dict[str, tuple[float, float]]
    calibration_strict: bool


_RUN_CONFIG: ContextVar[EnsembleRunConfig | None] = ContextVar(
    "praviar_ocsr_ensemble_run_config",
    default=None,
)


def _current_run_config() -> EnsembleRunConfig:
    config = _RUN_CONFIG.get()
    if config is None:
        raise RuntimeError(
            "OCSR ensemble run configuration is missing. "
            "Call set_thresholds_from_settings(settings) at the analysis boundary."
        )
    return config


def calibrate_confidence(raw: float, model: str) -> float:
    config = _current_run_config()
    return _calibrate_confidence_impl(
        raw,
        model,
        parameters=config.calibration_parameters,
        strict=config.calibration_strict,
    )


def _canonical(smiles: str) -> str:
    return _canonical_impl(smiles)


def _vote_key(smiles: str) -> str:
    return _vote_key_impl(smiles)


def _tanimoto(s1: str, s2: str) -> float:
    return _tanimoto_impl(s1, s2)


def _required_setting(settings: object, name: str) -> float:
    value = getattr(settings, name, None)
    if value is None:
        raise RuntimeError(f"settings.{name} missing; config_sections.py is out of sync.")
    return float(value)


def set_thresholds_from_settings(settings: object) -> EnsembleRunConfig:
    """Install immutable, task-local thresholds and calibration for one run."""

    from praviar_pipeline.ocsr.calibration_contract import (
        require_verified_calibration,
    )
    from praviar_pipeline.pipeline.drawing_rollout import drawing_rollout_state

    live = drawing_rollout_state(settings) in {"beta", "production"}
    calibration_parameters = dict(CALIBRATION_PARAMS)
    if live:
        verified = require_verified_calibration(settings)
        calibration_parameters = {
            tool: (float(values[0]), float(values[1]))
            for tool, values in verified.parameters.items()
        }
    config = EnsembleRunConfig(
        molscribe_high_conf=_required_setting(settings, "drawing_ensemble_molscribe_high_conf"),
        agreement_ratio_min=_required_setting(settings, "drawing_ensemble_agreement_ratio_min"),
        low_agreement_penalty=_required_setting(settings, "drawing_ensemble_low_agreement_penalty"),
        formula_boost=_required_setting(settings, "drawing_ensemble_formula_boost"),
        text_confirm_conf_bump=_required_setting(settings, "drawing_text_confirm_conf_bump"),
        plausibility_threshold=_required_setting(
            settings, "drawing_cascade_plausibility_threshold"
        ),
        min_resolved_conf=_required_setting(settings, "drawing_cascade_min_resolved_conf"),
        max_resolved_atoms=int(_required_setting(settings, "drawing_max_resolved_atoms")),
        calibration_parameters=calibration_parameters,
        calibration_strict=live,
    )
    _RUN_CONFIG.set(config)
    return config


_gate_log = structlog.get_logger("praviar_pipeline.ocsr.ensemble.gates")


def apply_resolution_gates(
    result: OCSRResult,
    *,
    min_resolved_conf: float,
    max_resolved_atoms: int,
) -> OCSRResult:
    """Apply the shared resolved-structure safety gates.

    This public helper exists so shortcut and specialist paths cannot bypass
    the same confidence and atom-count policy enforced after ensemble fusion.
    Callers must pass values from their task-local validated settings rather
    than reading process-global environment state.
    """
    if not result.smiles or not result.valid:
        return result
    if not result.confidence_available:
        return result.model_copy(
            update={"smiles": "", "valid": False, "error": "confidence_unavailable"}
        )
    if result.confidence < min_resolved_conf:
        _gate_log.info(
            "gate_fired_below_min_conf",
            tool=result.tool,
            confidence=round(result.confidence, 4),
            min_conf=min_resolved_conf,
        )
        return result.model_copy(update={"smiles": "", "valid": False, "error": "below_min_conf"})
    from rdkit import Chem

    mol = Chem.MolFromSmiles(result.smiles)
    if mol is None:
        # The upstream validity flag is not authoritative: a malformed value
        # must never survive as resolved evidence.
        return result.model_copy(update={"smiles": "", "valid": False, "error": "invalid_smiles"})
    if mol.GetNumHeavyAtoms() > max_resolved_atoms:
        _gate_log.info(
            "gate_fired_exceeds_max_atoms",
            tool=result.tool,
            confidence=round(result.confidence, 4),
            heavy_atoms=mol.GetNumHeavyAtoms(),
            max_atoms=max_resolved_atoms,
        )
        return result.model_copy(
            update={"smiles": "", "valid": False, "error": "exceeds_max_atoms"}
        )
    return result


def _apply_post_fuse_gates(
    result: OCSRResult,
    config: EnsembleRunConfig | None = None,
) -> OCSRResult:
    """Apply post-fusion safety gates to a fused OCSRResult.

    * Confidence floor — if fused confidence is below
      ``DRAWING_CASCADE_MIN_RESOLVED_CONF``, downgrade the result to
      unresolved with ``error="below_min_conf"``. Catches catastrophic
      miscalls at low ensemble agreement (e.g. wrong skeleton at conf=0.38).
    * Atom-count triage — if the SMILES heavy-atom count exceeds
      ``DRAWING_MAX_RESOLVED_ATOMS``, downgrade to unresolved with
      ``error="exceeds_max_atoms"``. Catches out-of-distribution
      macromolecule hallucinations (e.g. 189-atom polysaccharide).

    No-ops on results that are already invalid or carry an existing error.
    """
    run_config = config or _current_run_config()
    return apply_resolution_gates(
        result,
        min_resolved_conf=run_config.min_resolved_conf,
        max_resolved_atoms=run_config.max_resolved_atoms,
    )


def fuse(
    results: dict[str, OCSRResult],
    strategy: Strategy = "confidence_cascade",
    confidence_threshold: float = 0.8,
    plausibility_threshold: float | None = None,
    weights: dict[str, float] | None = None,
    beam_candidates: list[dict] | None = None,
    text_smiles: str | None = None,
    text_formula: str | None = None,
    ocr_labels: list[str] | None = None,
    run_config: EnsembleRunConfig | None = None,
) -> OCSRResult:
    """Fuse multiple OCSR results into a single best prediction.

    ``plausibility_threshold`` defaults to None and is then read from the
    Settings env var ``DRAWING_CASCADE_PLAUSIBILITY``. Pass an explicit float
    only in tests where you want to override.
    The text-confirm confidence bump is also Settings-driven.

    When ``ocr_labels`` is provided, voter SMILES with placeholder atoms
    (``*``/``[U]``) get expanded against the merged abbreviation dictionary
    before vote_key computation. This addresses the Boc/Ts/Ms/BocHN-driven
    abbreviation failure class.
    """
    if not results:
        return OCSRResult(tool="ensemble", error="No results to fuse")

    config = run_config or _current_run_config()
    if plausibility_threshold is None:
        plausibility_threshold = config.plausibility_threshold

    if ocr_labels:
        # Expand placeholders in each voter's SMILES before fusion.
        from praviar_pipeline.ocsr.abbreviations import (
            expand_superatoms,
            has_placeholder_atoms,
        )

        expanded: dict[str, OCSRResult] = {}
        for tool, r in results.items():
            if r.valid and r.smiles and has_placeholder_atoms(r.smiles):
                try:
                    new_smi = expand_superatoms(r.smiles, ocr_labels=ocr_labels)
                except RuntimeError:
                    new_smi = r.smiles
                if new_smi != r.smiles:
                    r = r.model_copy(update={"smiles": new_smi})
            expanded[tool] = r
        results = expanded

    w = _copy_weights_impl(weights)
    valid, vote_keys = _collect_valid_predictions_impl(
        results,
        calibration_parameters=config.calibration_parameters,
        calibration_strict=config.calibration_strict,
    )

    if not valid:
        return OCSRResult(tool="ensemble", error="No valid predictions from any model")

    if text_smiles:
        text_can = _canonical(text_smiles)
        if text_can:
            text_key = _vote_key(text_can)
            text_bump = config.text_confirm_conf_bump
            for tool, (can, conf) in valid.items():
                if vote_keys[tool] == text_key:
                    return _apply_post_fuse_gates(
                        OCSRResult(
                            smiles=can,
                            confidence=min(conf + text_bump, 1.0),
                            valid=True,
                            tool=f"ensemble:text_confirmed_{tool}",
                        ),
                        config,
                    )

    if text_formula:
        w = _boost_weights_by_formula_impl(
            valid,
            w,
            text_formula,
            boost=config.formula_boost,
        )

    if strategy == "best_single":
        return _apply_post_fuse_gates(_best_single_impl(valid), config)

    if strategy == "confidence_cascade":
        cascaded = _confidence_cascade_impl(
            valid,
            vote_keys,
            w,
            confidence_threshold,
            plausibility_threshold,
            beam_candidates,
            molscribe_high_conf=config.molscribe_high_conf,
        )
        if cascaded is not None:
            return _apply_post_fuse_gates(cascaded, config)
        strategy = "majority_vote"

    if strategy == "majority_vote":
        return _apply_post_fuse_gates(
            _majority_vote_impl(
                valid,
                vote_keys,
                w,
                len(results),
                agreement_ratio_min=config.agreement_ratio_min,
                low_agreement_penalty=config.low_agreement_penalty,
            ),
            config,
        )

    if strategy == "weighted_majority":
        return _apply_post_fuse_gates(
            _weighted_majority_impl(valid, vote_keys, w),
            config,
        )

    return _apply_post_fuse_gates(
        OCSRResult(
            smiles=next(iter(valid.values()))[0],
            confidence=next(iter(valid.values()))[1],
            valid=True,
            tool="ensemble:fallback",
        ),
        config,
    )
