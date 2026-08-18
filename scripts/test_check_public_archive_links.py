from __future__ import annotations

from pathlib import Path

from check_public_archive_links import find_broken_links


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_link_checker_accepts_files_directories_anchors_and_app_routes(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "README.md",
        "[guide](docs/guide.md) [docs](docs/) [section](#section) [app](/reports)\n",
    )
    _write(tmp_path, "docs/guide.md", "[home](../README.md)\n")
    included = {"README.md", "docs/guide.md"}

    assert find_broken_links(included, tmp_path) == []


def test_link_checker_reports_missing_markdown_and_html_images(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "README.md",
        "![missing](docs/missing.png)\n<img src='images/also-missing.png'>\n",
    )

    assert find_broken_links({"README.md"}, tmp_path) == [
        "README.md: 'docs/missing.png' is absent from the public archive",
        "README.md: 'images/also-missing.png' is absent from the public archive",
    ]


def test_link_checker_rejects_escape_and_unsafe_scheme(tmp_path: Path) -> None:
    _write(
        tmp_path, "docs/guide.md", "[escape](../../private.md) [bad](file:///tmp/x)\n"
    )

    assert find_broken_links({"docs/guide.md"}, tmp_path) == [
        "docs/guide.md: '../../private.md' escapes the repository root",
        "docs/guide.md: 'file:///tmp/x' uses forbidden URL scheme 'file'",
    ]


def test_link_checker_ignores_test_fixture_markdown(tmp_path: Path) -> None:
    _write(tmp_path, "tests/fixture.md", "[intentionally missing](missing.md)\n")

    assert find_broken_links({"tests/fixture.md"}, tmp_path) == []
