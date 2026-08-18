#!/usr/bin/env python3
"""Validate Praviar's deny-by-default public source-archive boundary.

This checker is deliberately independent of private publication machinery. It
uses only the Python standard library and is
copied into the history-free archive so a reader can re-run the same boundary
check from a clone.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "public-archive" / "manifest.json"
ARCHIVE_SCHEMA = "praviar.public-archive.v1"
ARCHIVE_POSTURE = "research_archive"

REQUIRED_MANIFEST_KEYS = {
    "schema_version",
    "publication_posture",
    "default_policy",
    "maximum_file_size_bytes",
    "include_globs",
    "exclude_globs",
    "forbidden_public_suffixes",
    "large_file_allowlist",
    "sha256_pins",
    "required_included_files",
}

FORBIDDEN_PUBLIC_FILENAMES = {
    ".netrc",
    ".npmrc",
    ".pypirc",
    "credentials",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
}
PIN_REQUIRED_SUFFIXES = (".wasm",)
ARCHIVE_FORBIDDEN_PATHS = {
    "AGENTS.md",
    "CLAUDE.md",
    "CODEOWNERS",
    "Praviar-Backend-Technical-Report.pdf",
    "RELEASE.md",
    "REVIEW.md",
    "scripts/check_public_markdown_links.py",
    "scripts/check_public_release.py",
    "scripts/export_public_snapshot.py",
    "scripts/test_check_public_markdown_links.py",
    "scripts/test_check_public_release.py",
    "scripts/test_export_public_snapshot.py",
}
ARCHIVE_FORBIDDEN_PREFIXES = (
    ".github/workflows/",
    ".agents/",
    ".claude/",
    ".codex/",
    "benchmark_results/",
    "commercial/",
    "docs/_archive/",
    "docs/gallery/",
    "docs/showcase/",
    "docs/trust/",
    "output/",
    "outputs/",
    "public-release/",
    "publication/",
    "research/tools/trust/",
    "research/validation/",
    "scripts/release/",
    "tmp/",
)
TERRAFORM_BOOTSTRAP_FORBIDDEN = (
    "roles/owner",
    "service-accounts keys create",
    "iam.serviceAccounts.keys.create",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "BEGIN KEY",
)
FILESYSTEM_ONLY_IGNORED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".next",
    ".pnpm-store",
    ".pytest_cache",
    ".ruff_cache",
    ".test-dist",
    ".terraform",
    ".turbo",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
    "out",
    "playwright-report",
    "test-results",
    "venv",
}
FILESYSTEM_ONLY_IGNORED_FILES = {
    ".coverage",
    ".DS_Store",
    "Thumbs.db",
    "next-env.d.ts",
}


@dataclass(frozen=True)
class ArchiveReport:
    """Deterministic classification and validation result."""

    included: tuple[str, ...]
    excluded: tuple[str, ...]
    errors: tuple[str, ...]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def safe_relative_path(path: str) -> bool:
    """Return whether ``path`` has one canonical repository-relative spelling."""

    pure = PurePosixPath(path)
    return (
        bool(path)
        and "\\" not in path
        and not pure.is_absolute()
        and pure.as_posix() == path
        and all(part not in {"", ".", ".."} for part in pure.parts)
        and all(part == part.strip() for part in pure.parts)
        and unicodedata.normalize("NFC", path) == path
        and all(
            unicodedata.category(character) not in {"Cc", "Cf", "Cs", "Zl", "Zp"}
            for character in path
        )
    )


def load_manifest(path: Path) -> dict[str, Any]:
    """Load and strictly validate the archive manifest schema."""

    raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(raw, dict):
        raise ValueError("manifest root must be an object")
    unknown = set(raw) - REQUIRED_MANIFEST_KEYS
    missing = REQUIRED_MANIFEST_KEYS - set(raw)
    if unknown or missing:
        raise ValueError(
            f"manifest keys differ: missing={sorted(missing)}, unknown={sorted(unknown)}"
        )
    if raw["schema_version"] != ARCHIVE_SCHEMA:
        raise ValueError(f"schema_version must be {ARCHIVE_SCHEMA}")
    if raw["publication_posture"] != ARCHIVE_POSTURE:
        raise ValueError(f"publication_posture must be {ARCHIVE_POSTURE}")
    if raw["default_policy"] != "deny":
        raise ValueError("default_policy must be deny")
    if (
        not isinstance(raw["maximum_file_size_bytes"], int)
        or isinstance(raw["maximum_file_size_bytes"], bool)
        or raw["maximum_file_size_bytes"] < 1
    ):
        raise ValueError("maximum_file_size_bytes must be a positive integer")

    list_keys = (
        "include_globs",
        "exclude_globs",
        "forbidden_public_suffixes",
        "large_file_allowlist",
        "required_included_files",
    )
    for key in list_keys:
        values = raw[key]
        if not isinstance(values, list) or any(
            not isinstance(item, str) or not item for item in values
        ):
            raise ValueError(f"{key} must be a list of non-empty strings")
        if len(values) != len(set(values)):
            raise ValueError(f"{key} contains duplicates")
    if not raw["include_globs"] or not raw["exclude_globs"]:
        raise ValueError("include_globs and exclude_globs must not be empty")

    for key in ("large_file_allowlist", "required_included_files"):
        if any(not safe_relative_path(item) for item in raw[key]):
            raise ValueError(f"{key} contains an unsafe path")

    pins = raw["sha256_pins"]
    if not isinstance(pins, dict) or any(
        not isinstance(public_path, str)
        or not safe_relative_path(public_path)
        or not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        for public_path, digest in pins.items()
    ):
        raise ValueError(
            "sha256_pins must map safe relative paths to lowercase SHA-256 digests"
        )
    return raw


def _git_candidates(root: Path) -> list[str] | None:
    git = shutil.which("git")
    if git is None:
        return None
    environment = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
    }
    top_level = subprocess.run(
        [git, "rev-parse", "--show-toplevel"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if top_level.returncode != 0:
        return None
    try:
        discovered_root = Path(top_level.stdout.strip()).resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if discovered_root != root.resolve(strict=True):
        return None

    present = subprocess.run(
        [git, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
        env=environment,
    )
    deleted = subprocess.run(
        [git, "ls-files", "--deleted", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
        env=environment,
    )
    candidates = {
        entry.decode("utf-8", errors="surrogateescape")
        for entry in present.stdout.split(b"\0")
        if entry
    }
    missing = {
        entry.decode("utf-8", errors="surrogateescape")
        for entry in deleted.stdout.split(b"\0")
        if entry
    }
    return sorted(candidates - missing)


def _filesystem_candidates(root: Path) -> list[str]:
    """Walk an exported, not-yet-initialised archive without following links."""

    candidates: list[str] = []

    def visit(directory: Path, prefix: PurePosixPath) -> None:
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                if entry.name in FILESYSTEM_ONLY_IGNORED_FILES:
                    continue
                relative = prefix / entry.name
                relative_text = relative.as_posix()
                if entry.is_dir(follow_symlinks=False):
                    if entry.name in FILESYSTEM_ONLY_IGNORED_DIRECTORIES:
                        continue
                    visit(Path(entry.path), relative)
                elif entry.name.endswith((".pyc", ".pyo")):
                    continue
                else:
                    candidates.append(relative_text)

    visit(root, PurePosixPath())
    return candidates


def candidate_files(root: Path) -> list[str]:
    """List tracked and non-ignored files, with a no-Git export-tree fallback."""

    root = root.resolve(strict=True)
    git_files = _git_candidates(root)
    return git_files if git_files is not None else _filesystem_candidates(root)


def _matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_archive(
    manifest: dict[str, Any], files: list[str], root: Path
) -> ArchiveReport:
    """Classify every candidate and validate every selected public file."""

    errors: list[str] = []
    included: list[str] = []
    excluded: list[str] = []
    root = root.resolve(strict=True)

    for path in sorted(set(files)):
        if not safe_relative_path(path):
            errors.append(f"unsafe candidate path: {path!r}")
        elif _matches(path, manifest["exclude_globs"]):
            excluded.append(path)
        elif _matches(path, manifest["include_globs"]):
            included.append(path)
        else:
            errors.append(f"unclassified candidate (default deny): {path}")

    included_set = set(included)
    for required in manifest["required_included_files"]:
        if required not in included_set:
            errors.append(f"required public file is absent or excluded: {required}")

    suffixes = tuple(item.casefold() for item in manifest["forbidden_public_suffixes"])
    large_allowlist = set(manifest["large_file_allowlist"])
    pins = manifest["sha256_pins"]
    size_limit = manifest["maximum_file_size_bytes"]

    for path in sorted(large_allowlist - set(pins)):
        errors.append(f"large-file allowlist entry is not SHA-256 pinned: {path}")
    for path in sorted(large_allowlist | set(pins)):
        if path not in included_set:
            errors.append(f"pinned or large public file is absent or excluded: {path}")

    for path in included:
        if path in ARCHIVE_FORBIDDEN_PATHS or path.startswith(
            ARCHIVE_FORBIDDEN_PREFIXES
        ):
            errors.append(f"public archive contains forbidden path: {path}")
        absolute = root / path
        if absolute.is_symlink():
            errors.append(f"public symlink is forbidden: {path}")
            continue
        if not absolute.is_file():
            errors.append(f"public path is not a regular file: {path}")
            continue
        name = PurePosixPath(path).name.casefold()
        if (name == ".env" or name.startswith(".env.")) and not name.endswith(
            ".example"
        ):
            errors.append(f"environment file is forbidden: {path}")
        if name in FORBIDDEN_PUBLIC_FILENAMES:
            errors.append(f"credential filename is forbidden: {path}")
        if suffixes and name.endswith(suffixes):
            errors.append(f"forbidden binary/sensitive suffix: {path}")
        if name.endswith(PIN_REQUIRED_SUFFIXES) and path not in pins:
            errors.append(f"opaque executable asset is not SHA-256 pinned: {path}")
        if (name.endswith(".tfvars") or ".tfvars." in name) and not name.endswith(
            (".example", ".template")
        ):
            errors.append(f"Terraform variable file is forbidden: {path}")
        if (
            name == "tfplan"
            or name.startswith(("tfplan-", "tfplan."))
            or ".tfstate." in name
        ):
            errors.append(f"forbidden Terraform plan/state artifact: {path}")
        size = absolute.stat().st_size
        if size > size_limit and path not in large_allowlist:
            errors.append(f"public file exceeds {size_limit} bytes ({size}): {path}")
        expected = pins.get(path)
        if expected is not None:
            observed = _sha256(absolute)
            if observed != expected:
                errors.append(
                    f"SHA-256 mismatch for {path}: expected {expected}, got {observed}"
                )

    bootstrap = "infra/terraform/bootstrap.sh"
    if bootstrap in included_set:
        text = (root / bootstrap).read_text(encoding="utf-8")
        for fragment in TERRAFORM_BOOTSTRAP_FORBIDDEN:
            if fragment.casefold() in text.casefold():
                errors.append(
                    f"Terraform bootstrap contains forbidden credential pattern {fragment!r}"
                )
        if re.search(r"\b[0-9A-F]{6}-[0-9A-F]{6}-[0-9A-F]{6}\b", text, re.IGNORECASE):
            errors.append(
                "Terraform bootstrap contains a concrete billing account identifier"
            )

    return ArchiveReport(
        included=tuple(included),
        excluded=tuple(excluded),
        errors=tuple(sorted(set(errors))),
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="repository or exported archive root (defaults to this checkout)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="archive manifest (defaults to ROOT/public-archive/manifest.json)",
    )
    parser.add_argument(
        "--require-no-excluded",
        action="store_true",
        help="also fail if the checked tree still contains excluded source files",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        root = args.root.expanduser().resolve(strict=True)
        manifest_path = (
            args.manifest.expanduser().resolve(strict=True)
            if args.manifest is not None
            else root / "public-archive" / "manifest.json"
        )
        manifest = load_manifest(manifest_path)
        report = validate_archive(manifest, candidate_files(root), root)
    except (
        OSError,
        UnicodeError,
        ValueError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"Public archive check failed: {exc}", file=sys.stderr)
        return 2

    errors = list(report.errors)
    if args.require_no_excluded and report.excluded:
        preview = ", ".join(report.excluded[:10])
        suffix = "" if len(report.excluded) <= 10 else ", ..."
        errors.append(f"archive tree still contains excluded files: {preview}{suffix}")
    if errors:
        print("Public archive boundary failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "Public archive boundary passed: "
        f"{len(report.included)} included, {len(report.excluded)} excluded, "
        "0 unclassified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
