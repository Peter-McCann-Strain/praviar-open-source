"""CLI surface for runtime Praviar Pipeline commands."""

from __future__ import annotations

import argparse
import sys
from typing import cast

from praviar_pipeline.cli_bigquery import main as check_bigquery_main
from praviar_pipeline.cli_models import main as models_main
from praviar_pipeline.cli_patcid import main as index_patcid_main
from praviar_pipeline.cli_replay import main as replay_main
from praviar_pipeline.cli_validate import main as validate_main
from praviar_pipeline.run import main as run_main


def _print_run_usage() -> None:
    print(
        "usage: praviar-pipeline run <compound> [--format json|markdown|pdf] "
        "[--dry-run] [--output-dir <dir>]"
    )
    print('example: praviar-pipeline run "succinic acid" --format json')
    print(
        'example: praviar-pipeline run "PVX-FICTIONAL-0042" --dry-run --output-dir /tmp/dryrun-test'
    )


def _print_validate_usage() -> None:
    print("usage: praviar-pipeline validate")


def _print_bigquery_usage() -> None:
    print("usage: praviar-pipeline check-bigquery")


def _print_patcid_usage() -> None:
    print("usage: praviar-pipeline index-patcid <patcid_dump.jsonl>")


def _print_replay_usage() -> None:
    print(
        "usage: praviar-pipeline replay <manifest.json> "
        "[--allow-drift] [--run] [--original <report.json>] [--output-dir <dir>]"
    )
    print("example: praviar-pipeline replay ./fto_report_abc.manifest.json")


def _print_models_usage() -> None:
    print("usage: praviar-pipeline models list [--json]")
    print("usage: praviar-pipeline models fetch <model-id> [--accept-license]")
    print("usage: praviar-pipeline models register-local <model-id> <path> [--accept-license]")
    print("usage: praviar-pipeline models verify [<model-id>] [--json]")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="praviar-pipeline")
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "validate", "check-bigquery", "index-patcid", "replay", "models"],
        help="Runtime command to execute.",
    )
    parser.add_argument("args", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if raw_args and raw_args[0].startswith("-"):
        build_parser().parse_args(raw_args)
        return 0

    if raw_args[:2] in (["run", "--help"], ["run", "-h"]):
        _print_run_usage()
        return 0
    if raw_args[:2] in (["validate", "--help"], ["validate", "-h"]):
        _print_validate_usage()
        return 0
    if raw_args[:2] in (["check-bigquery", "--help"], ["check-bigquery", "-h"]):
        _print_bigquery_usage()
        return 0
    if raw_args[:2] in (["index-patcid", "--help"], ["index-patcid", "-h"]):
        _print_patcid_usage()
        return 0
    if raw_args[:2] in (["replay", "--help"], ["replay", "-h"]):
        _print_replay_usage()
        return 0
    if raw_args[:2] in (["models", "--help"], ["models", "-h"]):
        _print_models_usage()
        return 0

    if raw_args and raw_args[0] not in {
        "run",
        "validate",
        "check-bigquery",
        "index-patcid",
        "replay",
        "models",
    }:
        raw_args = ["run", *raw_args]

    args = build_parser().parse_args(raw_args)
    if args.command == "run":
        sys.argv = ["praviar_pipeline.run", *args.args]
        run_main()
        return 0
    if args.command == "validate":
        return cast("int", validate_main(args.args))
    if args.command == "check-bigquery":
        return cast("int", check_bigquery_main(args.args))
    if args.command == "index-patcid":
        return index_patcid_main(args.args) or 0
    if args.command == "replay":
        return replay_main(args.args) or 0
    if args.command == "models":
        return models_main(args.args) or 0

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
