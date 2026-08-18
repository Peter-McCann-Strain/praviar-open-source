"""Validate machine-readable quarantine boundaries on non-release evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = (
    REPO_ROOT / "research" / "validation" / "evidence-quarantine-manifest.json"
)


def validate_manifest(manifest_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read quarantine manifest {manifest_path}: {exc}"]

    if manifest.get("schema_version") != "evidence-quarantine-manifest/v1":
        errors.append("quarantine manifest has an unsupported schema_version")
    policy = manifest.get("policy") or {}
    if policy.get("not_release_evidence") is not True:
        errors.append("quarantine manifest policy must set not_release_evidence=true")
    required_boundary_schema = str(policy.get("required_boundary_schema") or "")
    required_prohibited_use = str(policy.get("required_prohibited_use") or "")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return errors + ["quarantine manifest artifacts must be a non-empty list"]

    seen_paths: set[str] = set()
    for index, entry in enumerate(artifacts):
        if not isinstance(entry, dict):
            errors.append(f"artifact[{index}] must be an object")
            continue
        relative_path = str(entry.get("path") or "")
        if not relative_path:
            errors.append(f"artifact[{index}] is missing path")
            continue
        if relative_path in seen_paths:
            errors.append(f"duplicate quarantined artifact: {relative_path}")
            continue
        seen_paths.add(relative_path)

        artifact_path = (REPO_ROOT / relative_path).resolve()
        try:
            artifact_path.relative_to(REPO_ROOT.resolve())
        except ValueError:
            errors.append(f"quarantined artifact escapes repository: {relative_path}")
            continue
        try:
            payload: Any = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"cannot read quarantined artifact {relative_path}: {exc}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"quarantined artifact must be an object: {relative_path}")
            continue
        boundary = payload.get("_evidence_boundary")
        if not isinstance(boundary, dict):
            errors.append(f"missing _evidence_boundary: {relative_path}")
            continue
        if boundary.get("schema_version") != required_boundary_schema:
            errors.append(f"wrong boundary schema: {relative_path}")
        if boundary.get("not_release_evidence") is not True:
            errors.append(f"artifact is not fail-closed for release: {relative_path}")
        if boundary.get("evidence_status") != entry.get("evidence_status"):
            errors.append(f"manifest/status mismatch: {relative_path}")
        prohibited_uses = boundary.get("prohibited_uses") or []
        if required_prohibited_use not in prohibited_uses:
            errors.append(
                f"artifact does not prohibit {required_prohibited_use}: {relative_path}"
            )
        reviewer = str((payload.get("_metadata") or {}).get("reviewer") or "").lower()
        if "simulated" in reviewer and boundary.get("human_reviewer") is not False:
            errors.append(f"simulated reviewer is not explicitly non-human: {relative_path}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    errors = validate_manifest(args.manifest)
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 1
    print(f"evidence quarantine passed: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
