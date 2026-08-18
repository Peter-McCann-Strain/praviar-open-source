"""Filesystem path helpers for Praviar Pipeline settings."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = PROJECT_ROOT.parent


def _resolve_dir(configured_dir: str, default_dir: Path) -> Path:
    directory = Path(configured_dir) if configured_dir else default_dir
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def resolve_checkpoint_dir(settings) -> Path:
    """Resolve and create the checkpoint directory for current settings."""
    return _resolve_dir(settings.checkpoint_dir, PROJECT_ROOT / "checkpoints")


def resolve_output_dir(settings) -> Path:
    """Resolve and create the output directory for current settings."""
    return _resolve_dir(settings.output_dir, PROJECT_ROOT / "output")
