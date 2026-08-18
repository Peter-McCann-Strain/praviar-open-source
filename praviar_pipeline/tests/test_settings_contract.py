"""Settings contract regressions for Praviar Pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from praviar_pipeline.config import Settings

if TYPE_CHECKING:
    from pathlib import Path


def test_settings_reject_unknown_env_keys(tmp_path: Path):
    env_file = tmp_path / "praviar_pipeline.env"
    env_file.write_text(
        "ANTHROPIC_API_KEY=test-key\nUNKNOWN_SETTING=true\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        Settings(_env_file=env_file)
