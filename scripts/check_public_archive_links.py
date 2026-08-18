#!/usr/bin/env python3
"""Check local Markdown and HTML links inside the public source archive."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Sequence
from urllib.parse import unquote, urlsplit

from check_public_archive import (
    ROOT,
    candidate_files,
    load_manifest,
    validate_archive,
)

INLINE_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\n]+)\)")
REFERENCE_LINK = re.compile(r"^\s*\[[^\]]+\]:\s*(\S+)", re.MULTILINE)
HTML_LINK = re.compile(
    r"<(?:a|img)\b[^>]*?\b(?:href|src)\s*=\s*([\"'])(.*?)\1",
    re.IGNORECASE,
)


def _target_token(raw: str) -> str:
    value = raw.strip()
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    return value.split(maxsplit=1)[0]


def _local_target(
    source: str, raw_target: str, included: set[str]
) -> tuple[str | None, str | None]:
    target = _target_token(raw_target)
    if not target or target.startswith("#"):
        return None, None
    parsed = urlsplit(target)
    if parsed.scheme:
        if parsed.scheme.casefold() not in {"http", "https", "mailto"}:
            return target, f"uses forbidden URL scheme {parsed.scheme!r}"
        return None, None
    # Root-relative paths are application routes, not repository file links.
    if parsed.netloc or target.startswith("/"):
        return None, None
    decoded = unquote(parsed.path)
    if not decoded:
        return None, None

    candidate = PurePosixPath(source).parent / PurePosixPath(decoded)
    normalized_parts: list[str] = []
    for part in candidate.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not normalized_parts:
                return None, "escapes the repository root"
            normalized_parts.pop()
        else:
            normalized_parts.append(part)
    normalized = "/".join(normalized_parts)
    exists = normalized in included or any(
        path.startswith(f"{normalized}/") for path in included
    )
    if not exists:
        return normalized, "is absent from the public archive"
    return normalized, None


def find_broken_links(included: set[str], root: Path) -> list[str]:
    """Return deterministic diagnostics for absent or unsafe local links."""

    errors: list[str] = []
    for source in sorted(
        path
        for path in included
        if path.casefold().endswith((".md", ".markdown"))
        and "tests" not in PurePosixPath(path).parts
    ):
        text = (root / source).read_text(encoding="utf-8")
        targets = [match.group(1) for match in INLINE_LINK.finditer(text)]
        targets.extend(match.group(1) for match in REFERENCE_LINK.finditer(text))
        targets.extend(match.group(2) for match in HTML_LINK.finditer(text))
        for raw_target in targets:
            normalized, error = _local_target(source, raw_target, included)
            if error:
                display = normalized or _target_token(raw_target)
                errors.append(f"{source}: {display!r} {error}")
    return sorted(set(errors))


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
        if report.errors:
            print(
                "Public archive link check refused; archive boundary is invalid:",
                file=sys.stderr,
            )
            for error in report.errors:
                print(f"  - {error}", file=sys.stderr)
            return 2
        errors = find_broken_links(set(report.included), root)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Public archive link check failed: {exc}", file=sys.stderr)
        return 2

    if errors:
        print("Broken public archive links:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(
        f"Public archive link check passed: {len(report.included)} public files checked."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
