"""Unified entrypoint for research API verification tooling."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.tools.validation import certify_remdesivir_preflight, test_apis, verify_apis  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline-verification")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("verify-apis", help="Quick connectivity checks for configured APIs.")
    subparsers.add_parser("test-apis", help="Compound-based smoke tests for configured APIs.")
    certify = subparsers.add_parser(
        "certify-remdesivir",
        help="Strict live-source preflight for the Remdesivir certification run.",
    )
    certify.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "verify-apis":
        asyncio.run(verify_apis.main())
        return 0

    if args.command == "test-apis":
        asyncio.run(test_apis.main())
        return 0

    if args.command == "certify-remdesivir":
        return asyncio.run(
            certify_remdesivir_preflight.run_certification(json_output=args.json)
        )

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
