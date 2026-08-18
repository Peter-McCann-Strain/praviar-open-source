"""Owner-only confidential artifact filesystem contract."""

from __future__ import annotations

import os
import stat
from typing import TYPE_CHECKING

import pytest

from praviar_pipeline.utils.private_artifacts import (
    atomic_write_text,
    ensure_private_directory,
    private_file_for_read,
    read_private_bytes,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_private_directory_and_atomic_file_modes(tmp_path: Path) -> None:
    directory = tmp_path / "matter" / "artifacts"
    directory.mkdir(parents=True, mode=0o755)
    output = directory / "report.json"
    output.write_text("old", encoding="utf-8")
    output.chmod(0o644)

    ensure_private_directory(directory)
    atomic_write_text(output, "confidential")

    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert output.read_text(encoding="utf-8") == "confidential"


def test_private_file_symlink_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("protected", encoding="utf-8")
    alias = tmp_path / "alias"
    alias.symlink_to(target)

    with pytest.raises(OSError, match="symlink"):
        atomic_write_text(alias, "replacement")

    assert target.read_text(encoding="utf-8") == "protected"


def test_nested_directory_symlink_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)

    with pytest.raises(OSError, match="symlink"):
        ensure_private_directory(alias / "nested")


def test_private_read_rejects_symlink_and_preserves_target(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"protected")
    alias = tmp_path / "alias"
    alias.symlink_to(target)

    with pytest.raises(OSError, match="symlink"):
        read_private_bytes(alias, max_bytes=1024)

    assert target.read_bytes() == b"protected"


def test_private_read_enforces_exact_byte_cap(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact"
    artifact.write_bytes(b"12345")

    assert read_private_bytes(artifact, max_bytes=5) == b"12345"
    with pytest.raises(OSError, match="byte limit"):
        read_private_bytes(artifact, max_bytes=4)


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="owner IDs unavailable on this platform")
def test_non_owner_file_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "artifact"
    output.write_text("confidential", encoding="utf-8")
    real_uid = os.getuid()
    monkeypatch.setattr(os, "getuid", lambda: real_uid + 1)

    with pytest.raises(PermissionError, match="not owned"):
        private_file_for_read(output)
