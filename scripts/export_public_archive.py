#!/usr/bin/env python3
"""Export the deny-by-default public file set to a history-free directory.

The destination must not exist.  Files are copied into a sibling temporary
directory, revalidated with ``check_public_archive.py``, and renamed into place
only after the completed tree passes. No Git history, private records, or
generated publication artefacts are copied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

from check_public_archive import (
    ROOT,
    candidate_files,
    load_manifest,
    safe_relative_path,
    validate_archive,
)


class ArchiveExportError(RuntimeError):
    """Raised when an archive cannot be exported without weakening its boundary."""


def select_archive_files(
    manifest: dict[str, Any], root: Path
) -> tuple[tuple[str, ...], int]:
    """Return the exact validated public set and the excluded-source count."""

    report = validate_archive(manifest, candidate_files(root), root)
    if report.errors:
        raise ArchiveExportError("; ".join(report.errors))
    return report.included, len(report.excluded)


def _safe_source(root: Path, relative_path: str) -> tuple[Path, os.stat_result]:
    if not safe_relative_path(relative_path):
        raise ArchiveExportError(f"unsafe source path: {relative_path!r}")
    current = root
    for part in PurePosixPath(relative_path).parts:
        current = current / part
        if current.is_symlink():
            raise ArchiveExportError(f"source path contains a symlink: {relative_path}")
    try:
        # ``Path.stat(follow_symlinks=...)`` is not available on the macOS
        # system Python 3.9 used by some fresh clones.  ``os.stat`` provides
        # the same no-follow guarantee without raising a compatibility error.
        metadata = os.stat(current, follow_symlinks=False)
    except OSError as exc:
        raise ArchiveExportError(
            f"could not stat public source: {relative_path}"
        ) from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise ArchiveExportError(
            f"source is not a single-link regular file: {relative_path}"
        )
    return current, metadata


def _copy_verified(
    root: Path, relative_path: str, destination: Path
) -> tuple[str, int, str]:
    source, initial = _safe_source(root, relative_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(source, flags)
        try:
            opened = os.fstat(descriptor)
            identity_fields = (
                "st_dev",
                "st_ino",
                "st_mode",
                "st_nlink",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
            )
            if any(
                getattr(initial, field) != getattr(opened, field)
                for field in identity_fields
            ):
                raise ArchiveExportError(
                    f"public source changed before copy: {relative_path}"
                )
            with (
                os.fdopen(descriptor, "rb", closefd=False) as source_stream,
                destination.open("xb") as output,
            ):
                while chunk := source_stream.read(1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
                    output.write(chunk)
                final = os.fstat(source_stream.fileno())
            if (
                any(
                    getattr(opened, field) != getattr(final, field)
                    for field in identity_fields
                )
                or size != final.st_size
            ):
                raise ArchiveExportError(
                    f"public source changed during copy: {relative_path}"
                )
        finally:
            os.close(descriptor)
        exported_mode = 0o755 if initial.st_mode & 0o111 else 0o644
        os.chmod(destination, exported_mode, follow_symlinks=False)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    normalized_mode = "100755" if exported_mode == 0o755 else "100644"
    return digest.hexdigest(), size, normalized_mode


def export_archive(
    root: Path,
    destination: Path,
    included: tuple[str, ...],
    manifest: dict[str, Any],
) -> str:
    """Atomically copy and revalidate ``included``; return its inventory digest."""

    supplied_root = root.expanduser().absolute()
    if (
        supplied_root.is_symlink()
        or supplied_root.resolve(strict=True) != supplied_root
    ):
        raise ArchiveExportError(
            "source root must be a canonical non-symlink directory"
        )
    root = supplied_root

    raw_destination = destination.expanduser().absolute()
    if raw_destination.exists() or raw_destination.is_symlink():
        raise ArchiveExportError(f"destination already exists: {raw_destination}")
    raw_destination.parent.mkdir(parents=True, exist_ok=True)
    resolved_parent = raw_destination.parent.resolve(strict=True)
    if resolved_parent != raw_destination.parent:
        raise ArchiveExportError("destination parent must not contain a symbolic link")
    destination = resolved_parent / raw_destination.name
    if destination == root or root in destination.parents:
        raise ArchiveExportError(
            "destination must remain outside the source repository"
        )

    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
    )
    inventory = hashlib.sha256()
    pins = manifest["sha256_pins"]
    large_files = set(manifest["large_file_allowlist"])
    size_limit = manifest["maximum_file_size_bytes"]
    try:
        for relative_path in included:
            file_digest, size, normalized_mode = _copy_verified(
                root, relative_path, staging / relative_path
            )
            expected = pins.get(relative_path)
            if expected is not None and file_digest != expected:
                raise ArchiveExportError(
                    f"public source pin changed during export: {relative_path}"
                )
            if size > size_limit and relative_path not in large_files:
                raise ArchiveExportError(
                    f"public source grew beyond the archive cap: {relative_path}"
                )
            inventory.update(relative_path.encode("utf-8"))
            inventory.update(b"\0")
            inventory.update(normalized_mode.encode("ascii"))
            inventory.update(b"\0")
            inventory.update(file_digest.encode("ascii"))
            inventory.update(b"\n")

        staged_report = validate_archive(manifest, candidate_files(staging), staging)
        if staged_report.errors or staged_report.excluded:
            details = list(staged_report.errors)
            details.extend(
                f"completed archive unexpectedly excluded: {path}"
                for path in staged_report.excluded
            )
            raise ArchiveExportError(
                "completed public archive failed revalidation: " + "; ".join(details)
            )
        if staged_report.included != included:
            raise ArchiveExportError(
                "completed public archive file set differs from the selected source set"
            )
        staging.rename(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return inventory.hexdigest()


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="new history-free directory")
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="source repository root (defaults to this checkout)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="archive manifest (defaults to ROOT/public-archive/manifest.json)",
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
        included, excluded_count = select_archive_files(manifest, root)
        digest = export_archive(root, args.destination, included, manifest)
    except (OSError, UnicodeError, ValueError, ArchiveExportError) as exc:
        print(f"Public archive export failed: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "destination": str(args.destination.expanduser().absolute()),
                "excluded_source_files": excluded_count,
                "files": len(included),
                "inventory_sha256": digest,
                "publication_posture": manifest["publication_posture"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
