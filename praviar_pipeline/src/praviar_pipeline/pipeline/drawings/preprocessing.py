"""Deterministic preprocessing helpers for drawing analysis."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from praviar_pipeline.config import Settings


def image_hash(image_bytes: bytes) -> str:
    """Return a stable content hash for image bytes."""
    return hashlib.sha256(image_bytes).hexdigest()[:16]


def jurisdiction_from_patent_id(patent_id: str) -> str:
    """Extract a jurisdiction code from a patent identifier."""
    cleaned = patent_id.strip().upper()
    for prefix in ("US", "EP", "JP", "CN", "KR", "WO", "AU", "CA", "IN"):
        if cleaned.startswith(prefix):
            return prefix
    return "UNKNOWN"


def get_preprocessing_steps(jurisdiction: str, settings: Settings) -> list[str]:
    """Return jurisdiction-aware preprocessing steps."""
    base_steps = [str(step) for step in settings.drawing_preprocessing]

    if not settings.drawing_jurisdiction_aware:
        return base_steps

    if jurisdiction == "JP":
        if "denoise" not in base_steps:
            base_steps.insert(0, "denoise")
        if "sharpen" not in base_steps:
            base_steps.append("sharpen")
    elif jurisdiction == "CN" and "denoise" not in base_steps:
        base_steps.insert(0, "denoise")

    return base_steps
