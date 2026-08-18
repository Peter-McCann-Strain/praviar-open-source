"""Serialization helpers for pipeline checkpoints."""

from __future__ import annotations

from typing import Any


def serialize_checkpoint_value(obj: Any) -> Any:
    """Serialize a Pydantic model or list of models to JSON-safe dicts."""
    if obj is None:
        return None
    if isinstance(obj, list):
        return [serialize_checkpoint_value(item) for item in obj]
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return obj


def serialize_drawing_results(drawing_results: Any) -> Any:
    """Serialize drawing evidence stores while preserving plain values."""
    if hasattr(drawing_results, "to_dict"):
        return drawing_results.to_dict()
    return serialize_checkpoint_value(drawing_results)
