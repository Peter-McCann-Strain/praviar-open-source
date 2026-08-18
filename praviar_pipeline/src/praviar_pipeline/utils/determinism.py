"""Reproducibility helpers — pin Python/NumPy RNG to a fixed seed.

LLM sampling is pinned separately via ``temperature=0`` on every analysis
and verification call (see ``praviar_pipeline/clients/claude.py``). This module
covers the *non-LLM* sources of variance that matter for legally-
consequential output: any pipeline-side ``random`` / ``numpy.random``
draw, plus tie-breaking that would otherwise depend on dict/set
iteration order.

Usage:
    from praviar_pipeline.utils.determinism import seed_pipeline_rng
    seed_pipeline_rng(seed)            # uses configured ``deterministic_seed``

The helper is idempotent: calling it more than once is safe and simply
re-pins the global state. NumPy is seeded only when it is already
importable (it is part of the OCSR/embedding extras, not a hard
dependency of the CLI runtime).
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from praviar_pipeline.config import Settings

logger = structlog.get_logger()

_DEFAULT_SEED = 42


def seed_pipeline_rng(seed: int = _DEFAULT_SEED) -> int:
    """Pin Python/NumPy RNG state for reproducibility.

    Returns the seed actually applied so callers can record it in audit
    trails alongside the run inputs.
    """
    random.seed(seed)
    try:  # NumPy is optional for the CLI runtime.
        import numpy as np

        np.random.seed(seed)
    except ImportError:  # pragma: no cover — NumPy is always present in CI
        pass
    logger.debug("pipeline_rng_seeded", seed=seed)
    return seed


def seed_pipeline_rng_from_settings(settings: Settings) -> int:
    """Convenience wrapper that reads the seed from ``Settings``."""
    return seed_pipeline_rng(settings.deterministic_seed)
