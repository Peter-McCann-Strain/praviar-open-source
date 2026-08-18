"""Deterministic runtime bundle identities used by release certification."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

PACKAGE_ROOT = Path(__file__).resolve().parent
_GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")


def _matching_files(patterns: tuple[str, ...]) -> list[Path]:
    files = {
        path
        for pattern in patterns
        for path in PACKAGE_ROOT.glob(pattern)
        if path.is_file() and "__pycache__" not in path.parts
    }
    return sorted(files, key=lambda path: path.relative_to(PACKAGE_ROOT).as_posix())


def _bundle_sha256(patterns: tuple[str, ...]) -> str:
    files = _matching_files(patterns)
    if not files:
        raise RuntimeError("certification subject bundle is empty")
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(PACKAGE_ROOT).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def compute_certification_bundle_digests() -> dict[str, str]:
    """Hash the exact runtime inputs represented by the certification receipt."""
    return {
        "runtime_policy_sha256": _bundle_sha256(
            (
                "certification_policy.py",
                "certification_receipt.py",
                "certification_subject.py",
                "pipeline/runtime/decisioning.py",
                "pipeline/runtime/decisioning_metrics.py",
            )
        ),
        "evidence_policy_sha256": _bundle_sha256(
            (
                "pipeline/runtime/evidence_policy.py",
                "pipeline/report/deterministic_checks.py",
                "pipeline/report/policy.py",
                "pipeline/report_validation/*.py",
            )
        ),
        "prompt_bundle_sha256": _bundle_sha256(
            (
                "prompts/*.txt",
                "agents/*.py",
                "agents/**/*.py",
                "pipeline/**/*prompt*.py",
                "clients/claude_prompting.py",
            )
        ),
        "model_bundle_sha256": _bundle_sha256(
            (
                "model_supply_chain.py",
                "config.py",
                "config_models.py",
                "config_search_sections.py",
                "config_sections.py",
                "config_execution_sections.py",
            )
        ),
        "tool_definition_bundle_sha256": _bundle_sha256(
            ("tools_definitions.py", "agents/tools/*.py")
        ),
        "collector_bundle_sha256": _bundle_sha256(
            (
                "clients/*.py",
                "pipeline/search/source_registry.py",
                "pipeline/runtime/evidence_collectors.py",
                "pipeline/runtime/live_collector*.py",
            )
        ),
    }


def build_runtime_certification_bundle(git_sha: str) -> dict[str, str]:
    """Build the subject fragment from files inside the final runtime image."""
    if _GIT_SHA_RE.fullmatch(git_sha) is None:
        raise ValueError("git_sha must be exactly 40 lowercase hexadecimal characters")
    return {
        "schema_version": "praviar.runtime-certification-bundle.v1",
        "git_sha": git_sha,
        **compute_certification_bundle_digests(),
    }


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _write_new_file(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o444)
    try:
        written = 0
        while written < len(payload):
            written += os.write(descriptor, payload[written:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit the canonical certification bundle embedded in this image."
    )
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload = _canonical_json_bytes(build_runtime_certification_bundle(args.git_sha))
    if args.output is None:
        sys.stdout.buffer.write(payload)
    else:
        _write_new_file(args.output, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
