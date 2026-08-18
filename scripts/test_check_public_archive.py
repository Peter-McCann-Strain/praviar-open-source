from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import check_public_archive as archive


def _manifest(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": "praviar.public-archive.v1",
        "publication_posture": "research_archive",
        "default_policy": "deny",
        "maximum_file_size_bytes": 1024,
        "include_globs": ["LICENSE", "README.md", "src/**"],
        "exclude_globs": ["commercial/**", ".github/workflows/**"],
        "forbidden_public_suffixes": [".pt", ".tfstate"],
        "large_file_allowlist": [],
        "sha256_pins": {},
        "required_included_files": ["LICENSE"],
    }
    value.update(overrides)
    return value


def _write(root: Path, relative: str, value: str = "safe\n") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def test_archive_boundary_partitions_public_and_private_files(tmp_path: Path) -> None:
    _write(tmp_path, "LICENSE")
    _write(tmp_path, "src/app.py")
    _write(tmp_path, "commercial/prospects.csv")

    report = archive.validate_archive(
        _manifest(),
        ["LICENSE", "src/app.py", "commercial/prospects.csv"],
        tmp_path,
    )

    assert report.included == ("LICENSE", "src/app.py")
    assert report.excluded == ("commercial/prospects.csv",)
    assert report.errors == ()


def test_archive_boundary_fails_closed_for_unclassified_file(tmp_path: Path) -> None:
    _write(tmp_path, "LICENSE")
    _write(tmp_path, "notes.txt")

    report = archive.validate_archive(_manifest(), ["LICENSE", "notes.txt"], tmp_path)

    assert report.errors == ("unclassified candidate (default deny): notes.txt",)


def test_exclusion_wins_over_a_broad_include(tmp_path: Path) -> None:
    _write(tmp_path, "LICENSE")
    _write(tmp_path, "commercial/private.md")
    manifest = _manifest(include_globs=["**"], exclude_globs=["commercial/**"])

    report = archive.validate_archive(
        manifest, ["LICENSE", "commercial/private.md"], tmp_path
    )

    assert report.included == ("LICENSE",)
    assert report.excluded == ("commercial/private.md",)
    assert report.errors == ()


def test_hard_forbidden_workflow_cannot_be_approved_by_manifest(tmp_path: Path) -> None:
    _write(tmp_path, "LICENSE")
    _write(tmp_path, ".github/workflows/ci.yml")
    manifest = _manifest(
        include_globs=["**"],
        exclude_globs=["commercial/**"],
    )

    report = archive.validate_archive(
        manifest, ["LICENSE", ".github/workflows/ci.yml"], tmp_path
    )

    assert report.errors == (
        "public archive contains forbidden path: .github/workflows/ci.yml",
    )


def test_archive_rejects_unpinned_opaque_asset(tmp_path: Path) -> None:
    _write(tmp_path, "LICENSE")
    (tmp_path / "src/module.wasm").parent.mkdir(parents=True)
    (tmp_path / "src/module.wasm").write_bytes(b"opaque")

    report = archive.validate_archive(
        _manifest(), ["LICENSE", "src/module.wasm"], tmp_path
    )

    assert report.errors == (
        "opaque executable asset is not SHA-256 pinned: src/module.wasm",
    )


def test_archive_accepts_exact_sha256_pin(tmp_path: Path) -> None:
    _write(tmp_path, "LICENSE")
    (tmp_path / "src/module.wasm").parent.mkdir(parents=True)
    (tmp_path / "src/module.wasm").write_bytes(b"opaque")
    digest = hashlib.sha256(b"opaque").hexdigest()
    manifest = _manifest(sha256_pins={"src/module.wasm": digest})

    report = archive.validate_archive(
        manifest, ["LICENSE", "src/module.wasm"], tmp_path
    )

    assert report.errors == ()


def test_manifest_loader_rejects_release_only_keys(tmp_path: Path) -> None:
    manifest = _manifest(public_workflows=[])
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match=r"unknown=\['public_workflows'\]"):
        archive.load_manifest(path)


def test_filesystem_candidate_fallback_lists_symlinks_without_following(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, "LICENSE")
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    _write(outside, "private.txt")
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(archive, "_git_candidates", lambda _root: None)

    assert archive.candidate_files(tmp_path) == ["LICENSE", "linked"]


def test_filesystem_candidate_fallback_ignores_generated_install_and_test_trees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, "LICENSE")
    _write(tmp_path, "node_modules/dependency/index.js")
    _write(tmp_path, "packages/fixture/.test-dist/generated.js")
    _write(tmp_path, "web/next-env.d.ts")
    monkeypatch.setattr(archive, "_git_candidates", lambda _root: None)

    assert archive.candidate_files(tmp_path) == ["LICENSE"]


def test_repository_archive_manifest_passes_current_boundary() -> None:
    manifest = archive.load_manifest(archive.DEFAULT_MANIFEST)
    report = archive.validate_archive(
        manifest, archive.candidate_files(archive.ROOT), archive.ROOT
    )

    assert report.errors == ()
