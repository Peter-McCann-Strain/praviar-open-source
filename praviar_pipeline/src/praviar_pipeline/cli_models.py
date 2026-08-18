"""Command-line interface for explicit, fail-closed model acquisition."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

from praviar_pipeline.model_acquisition import (
    ModelAcquisitionError,
    ModelEntry,
    ModelReceipt,
    fetch_model,
    load_registry,
    register_local_model,
    verify_model,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="praviar-pipeline models",
        description=(
            "Inspect or explicitly acquire optional third-party models. "
            "Normal pipeline runs never invoke these operations."
        ),
    )
    parser.add_argument(
        "--model-root",
        type=Path,
        default=None,
        help="Installation root (default: PRAVIAR_MODEL_HOME or user cache).",
    )
    subparsers = parser.add_subparsers(dest="models_command", required=True)

    list_parser = subparsers.add_parser("list", help="List registry policy and upstream links.")
    list_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    fetch_parser = subparsers.add_parser(
        "fetch", help="Download only when the registry explicitly permits it."
    )
    fetch_parser.add_argument("model_id")
    fetch_parser.add_argument(
        "--accept-license",
        action="store_true",
        help="Acknowledge that you reviewed and accept the upstream terms.",
    )

    register_parser = subparsers.add_parser(
        "register-local", help="Verify and install a model obtained from its upstream publisher."
    )
    register_parser.add_argument("model_id")
    register_parser.add_argument("path", type=Path)
    register_parser.add_argument(
        "--accept-license",
        action="store_true",
        help="Acknowledge that you reviewed and accept the upstream terms.",
    )

    verify_parser = subparsers.add_parser("verify", help="Verify one or all installed models.")
    verify_parser.add_argument("model_id", nargs="?")
    verify_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser


def _entry_summary(entry: ModelEntry) -> dict[str, object]:
    local_activation_allowed = (
        entry.license_status == "approved"
        and entry.permitted_use == "approved"
        and entry.sha256 is not None
        and entry.expected_size_bytes is not None
    )
    return {
        "model_id": entry.model_id,
        "component": entry.component,
        "license_status": entry.license_status,
        "permitted_use": entry.permitted_use,
        "automated_download_allowed": entry.automated_download_allowed,
        "local_activation_allowed": local_activation_allowed,
        "checksum_available": entry.sha256 is not None,
        "serialization_format": entry.serialization_format,
        "upstream_page_url": entry.upstream_page_url,
    }


def _print_receipt(receipt: ModelReceipt) -> None:
    print(json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True))


def _list_models(*, as_json: bool) -> int:
    registry = load_registry()
    summaries = [_entry_summary(entry) for entry in registry.entries]
    if as_json:
        print(json.dumps(summaries, indent=2, sort_keys=True))
        return 0
    for summary in summaries:
        if summary["automated_download_allowed"]:
            acquisition = "fetch-approved"
        elif summary["local_activation_allowed"]:
            acquisition = "manual-register-approved"
        else:
            acquisition = "link-only/activation-blocked"
        print(
            f"{summary['model_id']}: {summary['license_status']}; {acquisition}; "
            f"{summary['upstream_page_url']}"
        )
    return 0


def _verify_models(model_id: str | None, *, root: Path | None, as_json: bool) -> int:
    registry = load_registry()
    identifiers = [model_id] if model_id else [entry.model_id for entry in registry.entries]
    results: list[dict[str, object]] = []
    failed = False
    for identifier in identifiers:
        try:
            receipt = verify_model(identifier, registry=registry, root=root)
        except ModelAcquisitionError as exc:
            failed = True
            results.append({"model_id": identifier, "verified": False, "error": str(exc)})
        else:
            results.append(
                {
                    "model_id": identifier,
                    "verified": True,
                    "sha256": receipt.sha256,
                    "size_bytes": receipt.size_bytes,
                }
            )
    if as_json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        for result in results:
            status = "verified" if result["verified"] else f"not verified: {result['error']}"
            print(f"{result['model_id']}: {status}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    """Run the model-management subcommand without touching models implicitly."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.models_command == "list":
            return _list_models(as_json=args.json)
        if args.models_command == "fetch":
            receipt = fetch_model(
                args.model_id,
                acknowledge_license=args.accept_license,
                root=args.model_root,
            )
            _print_receipt(receipt)
            return 0
        if args.models_command == "register-local":
            receipt = register_local_model(
                args.model_id,
                args.path,
                acknowledge_license=args.accept_license,
                root=args.model_root,
            )
            _print_receipt(receipt)
            return 0
        if args.models_command == "verify":
            return _verify_models(args.model_id, root=args.model_root, as_json=args.json)
    except (ModelAcquisitionError, httpx.HTTPError) as exc:
        parser.exit(1, f"model operation failed: {exc}\n")
    parser.error(f"unsupported models command: {args.models_command}")
    return 2
