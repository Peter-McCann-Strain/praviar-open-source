#!/usr/bin/env python3
"""Prove Gitleaks detection works before scanning a public archive tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

EXPECTED_GITLEAKS_VERSION = "8.22.1"
_SCAN_TIMEOUT_SECONDS = 300


class ArchiveSecretCheckError(RuntimeError):
    """Raised when the scanner or archive does not satisfy the safety contract."""


def _find_gitleaks(explicit_binary: str | None) -> Path:
    candidate = explicit_binary or os.environ.get("GITLEAKS_BIN")
    if candidate is None:
        candidate = shutil.which("gitleaks")
    if candidate is None:
        raise ArchiveSecretCheckError(
            "gitleaks was not found; install version "
            f"{EXPECTED_GITLEAKS_VERSION} or set GITLEAKS_BIN"
        )

    binary = Path(candidate).expanduser()
    if not binary.is_file():
        raise ArchiveSecretCheckError(f"gitleaks binary does not exist: {binary}")
    if not os.access(binary, os.X_OK):
        raise ArchiveSecretCheckError(f"gitleaks binary is not executable: {binary}")
    return binary.resolve()


def _run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=_SCAN_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ArchiveSecretCheckError(
            f"could not execute {Path(command[0]).name}: {exc}"
        ) from exc


def _assert_pinned_version(binary: Path) -> None:
    result = _run_command((str(binary), "version"))
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    match = re.search(r"(?<![0-9.])v?(\d+\.\d+\.\d+)(?![0-9.])", output)
    if result.returncode != 0 or match is None:
        raise ArchiveSecretCheckError("could not determine the gitleaks version")
    actual_version = match.group(1)
    if actual_version != EXPECTED_GITLEAKS_VERSION:
        raise ArchiveSecretCheckError(
            "refusing unpinned gitleaks version "
            f"{actual_version}; expected {EXPECTED_GITLEAKS_VERSION}"
        )


def _read_report(report_path: Path) -> list[object]:
    if not report_path.exists():
        return []
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArchiveSecretCheckError(
            f"gitleaks produced an unreadable JSON report: {report_path}"
        ) from exc
    if not isinstance(report, list):
        raise ArchiveSecretCheckError("gitleaks JSON report must contain a list")
    return report


def _scan(binary: Path, source: Path, report_path: Path) -> tuple[int, list[object]]:
    result = _run_command(
        (
            str(binary),
            "detect",
            "--source",
            str(source),
            "--no-git",
            "--redact=100",
            "--no-banner",
            "--no-color",
            "--report-format",
            "json",
            "--report-path",
            str(report_path),
        )
    )
    if result.returncode not in (0, 1):
        detail = (result.stderr or result.stdout).strip()
        if detail:
            detail = f": {detail}"
        raise ArchiveSecretCheckError(
            f"gitleaks scan failed with exit code {result.returncode}{detail}"
        )
    return result.returncode, _read_report(report_path)


def _write_runtime_canary(directory: Path) -> None:
    # Assemble both the detector keyword and high-entropy value at runtime so the
    # tracked checker does not itself contain a secret-shaped test credential.
    detector_keyword = "_".join(("api", "key"))
    canary_value = hashlib.sha256(
        b"praviar-public-archive-gitleaks-detection-canary"
    ).hexdigest()
    (directory / "canary.txt").write_text(
        f'{detector_keyword} = "{canary_value}"\n',
        encoding="utf-8",
    )


def _prove_scanner(binary: Path, workspace: Path) -> None:
    detection_source = workspace / "detection-canary"
    detection_source.mkdir()
    _write_runtime_canary(detection_source)
    detection_code, findings = _scan(
        binary,
        detection_source,
        workspace / "detection-report.json",
    )
    if detection_code != 1 or not findings:
        raise ArchiveSecretCheckError(
            "gitleaks detection canary failed; refusing to trust an archive scan"
        )

    clean_source = workspace / "clean-control"
    clean_source.mkdir()
    (clean_source / "fixture.txt").write_text(
        "fixture_name = low_entropy_public_fixture\n",
        encoding="utf-8",
    )
    clean_code, clean_findings = _scan(
        binary,
        clean_source,
        workspace / "clean-report.json",
    )
    if clean_code != 0 or clean_findings:
        raise ArchiveSecretCheckError(
            "gitleaks clean control failed; refusing to scan the archive"
        )


def check_archive(archive: Path, *, gitleaks_binary: str | None = None) -> None:
    if archive.is_symlink():
        raise ArchiveSecretCheckError("archive root must not be a symbolic link")
    if not archive.is_dir():
        raise ArchiveSecretCheckError(f"archive directory does not exist: {archive}")
    archive = archive.resolve()
    binary = _find_gitleaks(gitleaks_binary)
    _assert_pinned_version(binary)

    with tempfile.TemporaryDirectory(prefix="praviar-gitleaks-") as temporary:
        workspace = Path(temporary)
        _prove_scanner(binary, workspace)
        archive_code, archive_findings = _scan(
            binary,
            archive,
            workspace / "archive-report.json",
        )

    if archive_code != 0 or archive_findings:
        raise ArchiveSecretCheckError(
            f"public archive secret scan found {len(archive_findings)} finding(s)"
        )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a detection canary, clean control, and zero-finding Gitleaks "
            "scan against a public archive directory."
        )
    )
    parser.add_argument("archive", type=Path, help="final public archive directory")
    parser.add_argument(
        "--gitleaks-bin",
        help=("path to gitleaks 8.22.1 (defaults to GITLEAKS_BIN, then PATH)"),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        check_archive(args.archive, gitleaks_binary=args.gitleaks_bin)
    except ArchiveSecretCheckError as exc:
        print(f"Public archive secret check failed: {exc}", file=sys.stderr)
        return 1
    print(
        "Public archive secret check passed: gitleaks 8.22.1 canary detected, "
        "clean control passed, archive findings=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
