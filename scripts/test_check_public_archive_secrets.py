from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_public_archive_secrets as checker  # noqa: E402


def _fake_gitleaks(
    tmp_path: Path,
    *,
    version: str = "8.22.1",
    detect_canary: bool = True,
) -> Path:
    binary = tmp_path / "gitleaks"
    binary.write_text(
        """#!/usr/bin/env python3
import hashlib
import json
import pathlib
import sys

if sys.argv[1:] == ["version"]:
    print("__VERSION__")
    raise SystemExit(0)

source = pathlib.Path(sys.argv[sys.argv.index("--source") + 1])
report = pathlib.Path(sys.argv[sys.argv.index("--report-path") + 1])
detector_keyword = "_".join(("api", "key"))
canary_value = hashlib.sha256(
    b"praviar-public-archive-gitleaks-detection-canary"
).hexdigest()
findings = []
for path in source.rglob("*"):
    if (
        __DETECT_CANARY__
        and path.is_file()
        and f'{detector_keyword} = "{canary_value}"' in path.read_text()
    ):
        findings.append({"RuleID": "generic-api-key", "File": path.name})
report.write_text(json.dumps(findings))
raise SystemExit(1 if findings else 0)
""".replace("__VERSION__", version).replace("__DETECT_CANARY__", repr(detect_canary)),
        encoding="utf-8",
    )
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


def test_check_archive_proves_canary_then_accepts_clean_tree(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "README.md").write_text("research archive\n", encoding="utf-8")

    checker.check_archive(
        archive,
        gitleaks_binary=os.fspath(_fake_gitleaks(tmp_path)),
    )


def test_check_archive_refuses_an_unpinned_scanner(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()

    with pytest.raises(checker.ArchiveSecretCheckError, match="unpinned"):
        checker.check_archive(
            archive,
            gitleaks_binary=os.fspath(_fake_gitleaks(tmp_path, version="8.30.1")),
        )


def test_check_archive_refuses_a_false_negative_scanner(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()

    with pytest.raises(checker.ArchiveSecretCheckError, match="detection canary"):
        checker.check_archive(
            archive,
            gitleaks_binary=os.fspath(_fake_gitleaks(tmp_path, detect_canary=False)),
        )


def test_check_archive_rejects_a_secret_finding(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    checker._write_runtime_canary(archive)

    with pytest.raises(checker.ArchiveSecretCheckError, match="1 finding"):
        checker.check_archive(
            archive,
            gitleaks_binary=os.fspath(_fake_gitleaks(tmp_path)),
        )


def test_check_archive_rejects_a_symlinked_root(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    linked_archive = tmp_path / "linked-archive"
    linked_archive.symlink_to(archive, target_is_directory=True)

    with pytest.raises(checker.ArchiveSecretCheckError, match="symbolic link"):
        checker.check_archive(
            linked_archive,
            gitleaks_binary=os.fspath(_fake_gitleaks(tmp_path)),
        )
