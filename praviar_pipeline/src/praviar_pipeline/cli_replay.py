"""CLI subcommand: ``praviar-pipeline replay <manifest.json>``.

Verifies that a past run's manifest can be reproduced against the
current working tree, optionally re-runs the pipeline with the
manifest's pinned configuration, and diffs the result against the
original report (if supplied).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from praviar_pipeline.replay import (
    diff_reports,
    load_manifest,
    verify_preconditions,
)
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

EXIT_OK = 0
EXIT_DRIFT = 2
EXIT_MANIFEST_ERROR = 3
EXIT_REPLAY_FAILURE = 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="praviar-pipeline replay",
        description=(
            "Verify and optionally re-run a Praviar Pipeline pipeline from a "
            "previously-emitted manifest.json sidecar."
        ),
    )
    parser.add_argument(
        "manifest_path",
        type=Path,
        help="Path to the manifest JSON file to replay.",
    )
    parser.add_argument(
        "--allow-drift",
        action="store_true",
        help=(
            "Continue even if the current working tree has drifted from the "
            "manifest's pinned pipeline version or prompt hashes. A warning "
            "is printed for each drift point."
        ),
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help=(
            "After verification, actually re-run the pipeline on the "
            "compound recorded in the manifest. Without this flag, the "
            "command only verifies preconditions and exits."
        ),
    )
    parser.add_argument(
        "--original",
        type=Path,
        default=None,
        help=(
            "Path to the original FTOReport JSON. When provided along with "
            "--run, the replay result is diffed against the original."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directory to write the replay's report output. Defaults to "
            "the pipeline's standard output directory."
        ),
    )
    return parser


def _format_preconditions(result) -> str:  # PreconditionResult
    lines: list[str] = []
    if result.version_matches:
        lines.append("  pipeline_version: MATCH")
    else:
        mf, curr = result.version_diff or ("?", "?")
        lines.append(f"  pipeline_version: DRIFT  (manifest {mf[:12]} -> current {curr[:12]})")

    if result.missing_prompts:
        for p in result.missing_prompts:
            lines.append(f"  prompt missing on disk: {p}")
    if result.prompt_drift:
        for name, (mh, ch) in sorted(result.prompt_drift.items()):
            lines.append(f"  prompt drift: {name}  (manifest {mh[:12]} -> current {ch[:12]})")

    if result.missing_tool_definitions:
        for tool_name in result.missing_tool_definitions:
            lines.append(f"  tool definition missing in runtime: {tool_name}")
    if result.tool_definition_drift:
        for name, (mh, ch) in sorted(result.tool_definition_drift.items()):
            lines.append(
                f"  tool definition drift: {name}  (manifest {mh[:12]} -> current {ch[:12]})"
            )

    hashed_ok = not result.missing_prompts and not result.prompt_drift
    if hashed_ok:
        lines.append("  prompt_hashes: ALL MATCH")
    tool_hashes_ok = not result.missing_tool_definitions and not result.tool_definition_drift
    if tool_hashes_ok:
        lines.append("  tool_definition_hashes: ALL MATCH")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest_path)
    except (FileNotFoundError, ValueError) as exc:
        print(
            f"error: replay manifest unavailable ({safe_exception_type(exc)})",
            file=sys.stderr,
        )
        return EXIT_MANIFEST_ERROR

    print("Loaded replay manifest")
    print("  compound_query: protected")
    print(f"  pipeline_version: {manifest.pipeline_version}")
    print(f"  generated_at: {manifest.generated_at.isoformat()}")
    print(f"  prompts recorded: {len(manifest.prompt_hashes)}")
    print(f"  tool definitions recorded: {len(manifest.tool_definition_hashes)}")
    print()

    result = verify_preconditions(manifest, allow_drift=args.allow_drift)
    print("Preconditions:")
    print(_format_preconditions(result))
    print()

    if not result.ok:
        print(
            "DRIFT detected. Re-run with --allow-drift to proceed anyway "
            "(results may not match the original).",
            file=sys.stderr,
        )
        return EXIT_DRIFT

    if not args.run:
        print("Verification-only mode (no --run). Exiting.")
        return EXIT_OK

    # Re-run the pipeline. Import lazily so a simple "verify manifest"
    # invocation doesn't pull the world.
    try:
        replay_report = _rerun_pipeline(
            manifest,
            manifest_path=args.manifest_path,
            output_dir=args.output_dir,
        )
    except Exception as exc:
        print(
            f"replay failed during pipeline execution ({safe_exception_type(exc)})",
            file=sys.stderr,
        )
        return EXIT_REPLAY_FAILURE

    if args.original:
        try:
            original = json.loads(Path(args.original).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            print(
                f"error reading --original ({safe_exception_type(exc)})",
                file=sys.stderr,
            )
            return EXIT_MANIFEST_ERROR
        diff = diff_reports(original, replay_report)
        print("Diff vs original:")
        if diff.identical:
            print("  IDENTICAL (structural match: same verdict, same patent set)")
        else:
            for msg in diff.messages:
                print(f"  {msg}")
            if not diff.messages:
                print("  (structural differences detected but no high-level messages)")

    return EXIT_OK


def _resolve_response_cache_dir(manifest, *, manifest_path: Path) -> Path:
    """Resolve the authenticated retained-response cache without path escape."""
    if not (
        manifest.response_cache_reference
        and manifest.response_cache_digest
        and manifest.response_cache_hmac_sha256
        and manifest.response_cache_key_id
    ):
        raise RuntimeError("Manifest does not contain an exact response-cache contract")
    manifest_dir = manifest_path.resolve().parent
    cache_path = (manifest_dir / cast("str", manifest.response_cache_reference)).resolve()
    try:
        cache_path.relative_to(manifest_dir)
    except ValueError:
        raise RuntimeError("Response cache reference escapes manifest directory") from None
    if cache_path.name != "responses.jsonl" or not cache_path.is_file():
        raise RuntimeError("Retained response cache is unavailable")
    return cache_path.parent


def _rerun_pipeline(
    manifest,
    *,
    manifest_path: Path,
    output_dir: Path | None,
) -> dict:
    """Invoke the canonical async ``run_pipeline`` with the manifest's inputs.

    Returns the report payload as a dict. Kept out of module-level
    imports so ``praviar-pipeline replay --help`` and verification-only mode
    don't pull the pipeline's heavy import graph.
    """
    import asyncio

    from praviar_pipeline.replay import reset_prompt_hasher
    from praviar_pipeline.run import run_pipeline

    cache_dir = _resolve_response_cache_dir(manifest, manifest_path=manifest_path)
    overrides: dict[str, object] = {}
    for role in ("triage", "analysis", "deep"):
        model_id = manifest.model_versions.get(role, "")
        if model_id:
            overrides[f"claude_{role}_model"] = model_id
    if output_dir is not None:
        overrides["output_dir"] = str(output_dir)
    overrides.update(
        {
            "response_cache_mode": "replay",
            "response_cache_dir": str(cache_dir),
            "response_cache_expected_digest": manifest.response_cache_digest,
            "response_cache_expected_hmac": manifest.response_cache_hmac_sha256,
            "response_cache_expected_key_id": manifest.response_cache_key_id,
        }
    )

    reset_prompt_hasher()
    coro = run_pipeline(
        user_input=manifest.compound_query,
        config_overrides=overrides or None,
    )
    return asyncio.run(coro)


if __name__ == "__main__":
    raise SystemExit(main())
