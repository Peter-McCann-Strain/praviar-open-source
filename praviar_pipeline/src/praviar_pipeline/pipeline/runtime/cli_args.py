"""CLI parsing helpers for the Praviar Pipeline runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(slots=True)
class RunCliArgs:
    user_input: str
    output_format: str = "json"
    resume_from: str | None = None
    reanalyze_dir: str | None = None
    dry_run: bool = False
    output_dir: str | None = None


def print_usage() -> None:
    print("Usage: praviar-pipeline run <compound> [--format json|markdown|pdf]")
    print('Example: praviar-pipeline run "succinic acid"')
    print('Example: praviar-pipeline run "succinic acid" --format markdown')


def parse_run_args(argv: list[str]) -> RunCliArgs:
    args = list(argv)
    output_format = "json"
    resume_from = None
    reanalyze_dir = None
    dry_run = False
    output_dir = None

    if "--format" in args:
        format_index = args.index("--format")
        if format_index + 1 < len(args):
            output_format = args[format_index + 1].lower()
            args = args[:format_index] + args[format_index + 2 :]
    if any(arg == "--mode" or arg.startswith("--mode=") for arg in args):
        raise ValueError("--mode was removed; the pipeline always uses world_class_adaptive.")
    if any(arg == "--depth" or arg.startswith("--depth=") for arg in args):
        raise ValueError("--depth was removed; the pipeline always uses world_class_adaptive.")
    if "--resume" in args:
        resume_index = args.index("--resume")
        if resume_index + 1 < len(args):
            resume_from = args[resume_index + 1]
            args = args[:resume_index] + args[resume_index + 2 :]
    if "--reanalyze" in args:
        reanalyze_index = args.index("--reanalyze")
        if reanalyze_index + 1 < len(args):
            reanalyze_dir = args[reanalyze_index + 1]
            args = args[:reanalyze_index] + args[reanalyze_index + 2 :]
    if "--output-dir" in args:
        out_index = args.index("--output-dir")
        if out_index + 1 < len(args):
            output_dir = args[out_index + 1]
            args = args[:out_index] + args[out_index + 2 :]
    if "--dry-run" in args:
        dry_run = True
        args = [a for a in args if a != "--dry-run"]

    return RunCliArgs(
        user_input=" ".join(args),
        output_format=output_format,
        resume_from=resume_from,
        reanalyze_dir=reanalyze_dir,
        dry_run=dry_run,
        output_dir=output_dir,
    )


def emit_json_report(report: dict, *, banner: bool) -> None:
    if banner:
        print("\n" + "=" * 80)
        print("FTO ANALYSIS REPORT")
        print("=" * 80)
    print(json.dumps(report, indent=2, default=str))
