from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from export_public_archive import (
    ArchiveExportError,
    export_archive,
    select_archive_files,
)


def _manifest(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": "praviar.public-archive.v1",
        "publication_posture": "research_archive",
        "default_policy": "deny",
        "maximum_file_size_bytes": 1024,
        "include_globs": ["LICENSE", "README.md", "tool.sh"],
        "exclude_globs": ["private/**"],
        "forbidden_public_suffixes": [".pt"],
        "large_file_allowlist": [],
        "sha256_pins": {},
        "required_included_files": ["LICENSE"],
    }
    value.update(overrides)
    return value


def test_export_copies_only_selected_files_and_revalidates(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "LICENSE").write_text("licence\n", encoding="utf-8")
    (source / "README.md").write_text("archive\n", encoding="utf-8")
    private = source / "private/notes.md"
    private.parent.mkdir()
    private.write_text("private\n", encoding="utf-8")
    manifest = _manifest()

    included, excluded_count = select_archive_files(manifest, source)
    destination = tmp_path / "archive"
    digest = export_archive(source, destination, included, manifest)

    assert included == ("LICENSE", "README.md")
    assert excluded_count == 1
    assert (destination / "README.md").read_text(encoding="utf-8") == "archive\n"
    assert not (destination / "private").exists()
    assert len(digest) == 64
    assert not list(tmp_path.glob(".archive.tmp-*"))


def test_export_refuses_existing_destination(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "LICENSE").write_text("safe\n", encoding="utf-8")
    destination = tmp_path / "archive"
    destination.mkdir()

    with pytest.raises(ArchiveExportError, match="destination already exists"):
        export_archive(source, destination, ("LICENSE",), _manifest())


def test_export_refuses_destination_inside_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "LICENSE").write_text("safe\n", encoding="utf-8")

    with pytest.raises(ArchiveExportError, match="outside the source repository"):
        export_archive(source, source / "archive", ("LICENSE",), _manifest())


def test_export_rejects_symlinked_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("private\n", encoding="utf-8")
    (source / "LICENSE").symlink_to(outside)

    with pytest.raises(ArchiveExportError, match="contains a symlink"):
        export_archive(source, tmp_path / "archive", ("LICENSE",), _manifest())

    assert not (tmp_path / "archive").exists()


def test_export_rechecks_pin_and_leaves_no_partial_destination(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "LICENSE").write_text("changed\n", encoding="utf-8")
    manifest = _manifest(sha256_pins={"LICENSE": "0" * 64})

    with pytest.raises(ArchiveExportError, match="pin changed during export"):
        export_archive(source, tmp_path / "archive", ("LICENSE",), manifest)

    assert not (tmp_path / "archive").exists()


def test_export_normalizes_permissions_and_digest_binds_mode(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "LICENSE").write_text("safe\n", encoding="utf-8")
    script = source / "tool.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o4777)

    first = tmp_path / "first"
    executable_digest = export_archive(
        source, first, ("LICENSE", "tool.sh"), _manifest()
    )
    assert os.stat(first / "tool.sh").st_mode & 0o7777 == 0o755

    script.chmod(0o644)
    regular_digest = export_archive(
        source, tmp_path / "second", ("LICENSE", "tool.sh"), _manifest()
    )
    assert executable_digest != regular_digest
    assert hashlib.sha256(b"#!/bin/sh\n").hexdigest()
