"""Fail-closed production preflight for the versioned vision/OCSR runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from praviar_pipeline.config_paths import PROJECT_ROOT
from praviar_pipeline.ocsr.workers.model_integrity import (
    ModelChecksumError,
    verify_model_checksum_from_ml_bom,
    verify_model_directory_from_ml_bom,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

SHA256_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]*$")
IMPORT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PRODUCTION_JURISDICTIONS = frozenset({"US", "EP", "WO", "JP", "CN", "KR"})
REQUIRED_ROLES = frozenset({"segmentation", "classification", "primary_ocsr", "markush_ocsr"})
DEFAULT_ROSTER_PATH = Path(__file__).with_name("data") / "vision-production-roster.v2.json"


class VisionPreflightError(RuntimeError):
    """Raised when the production vision runtime is incomplete or mutable."""


class VisionModelArtifact(BaseModel):
    """A single model artifact bound to an ML-BOM entry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str
    artifact_kind: Literal["file", "directory_tree_v1"]
    runtime_path: str

    @model_validator(mode="after")
    def validate_values(self) -> VisionModelArtifact:
        if not IDENTIFIER_RE.fullmatch(self.model_id):
            raise ValueError("model_id contains unsupported characters")
        _validate_relative_path(self.runtime_path, field_name="runtime_path")
        return self


class VisionComponent(BaseModel):
    """One isolated subprocess worker and all artifacts it needs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    component_id: str
    role: Literal[
        "segmentation",
        "classification",
        "primary_ocsr",
        "markush_ocsr",
        "sar_table",
    ]
    venv_path: str
    worker_path: str
    required_imports: tuple[str, ...] = Field(min_length=1)
    models: tuple[VisionModelArtifact, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_values(self) -> VisionComponent:
        if not IDENTIFIER_RE.fullmatch(self.component_id):
            raise ValueError("component_id contains unsupported characters")
        _validate_relative_path(self.venv_path, field_name="venv_path")
        _validate_relative_path(self.worker_path, field_name="worker_path")
        if len(set(self.required_imports)) != len(self.required_imports):
            raise ValueError("required_imports must be unique")
        if any(not IMPORT_RE.fullmatch(value) for value in self.required_imports):
            raise ValueError("required_imports must be top-level Python module names")
        model_ids = [model.model_id for model in self.models]
        if len(set(model_ids)) != len(model_ids):
            raise ValueError("component model_id values must be unique")
        return self


class VisionRuntimeContract(BaseModel):
    """Exact tool selection permitted for the first production roster."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    segmentation_tool: Literal["decimer"]
    classifier_required: Literal[True]
    primary_ocsr_tools: tuple[str, ...] = Field(min_length=1)
    markush_ocsr_tools: tuple[str, ...] = Field(min_length=1)
    sar_table_tools: tuple[str, ...] = ()
    prohibited_production_tools: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_tool_sets(self) -> VisionRuntimeContract:
        active_groups = (
            self.primary_ocsr_tools,
            self.markush_ocsr_tools,
            self.sar_table_tools,
        )
        active_tools = [
            self.segmentation_tool,
            *(tool for group in active_groups for tool in group),
        ]
        all_tools = [*active_tools, *self.prohibited_production_tools]
        if any(not IDENTIFIER_RE.fullmatch(tool) for tool in all_tools):
            raise ValueError("vision runtime tool IDs contain unsupported characters")
        if len(active_tools) != len(set(active_tools)):
            raise ValueError("active vision runtime tool IDs must be unique")
        if len(self.prohibited_production_tools) != len(set(self.prohibited_production_tools)):
            raise ValueError("prohibited production tool IDs must be unique")
        if set(active_tools) & set(self.prohibited_production_tools):
            raise ValueError("active and prohibited vision runtime tools must be disjoint")
        return self


class VisionProductionRoster(BaseModel):
    """Immutable, versioned declaration of the production vision runtime."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2]
    roster_id: str
    architecture: Literal["subprocess_venv_workers"]
    worker_protocol_version: Literal[1]
    runtime_downloads_allowed: Literal[False]
    jurisdictions: tuple[str, ...]
    runtime_contract: VisionRuntimeContract
    components: tuple[VisionComponent, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_roster(self) -> VisionProductionRoster:
        if not IDENTIFIER_RE.fullmatch(self.roster_id):
            raise ValueError("roster_id contains unsupported characters")
        if set(self.jurisdictions) != PRODUCTION_JURISDICTIONS:
            raise ValueError("jurisdictions must contain exactly US, EP, WO, JP, CN, and KR")
        if len(set(self.jurisdictions)) != len(self.jurisdictions):
            raise ValueError("jurisdictions must be unique")
        component_ids = [component.component_id for component in self.components]
        if len(set(component_ids)) != len(component_ids):
            raise ValueError("component_id values must be unique")
        model_ids = [model.model_id for component in self.components for model in component.models]
        if len(set(model_ids)) != len(model_ids):
            raise ValueError("model_id values must be unique across the roster")
        roles = {component.role for component in self.components}
        if not REQUIRED_ROLES.issubset(roles):
            raise ValueError("roster is missing one or more required production roles")
        role_component_ids = {
            role: {
                component.component_id for component in self.components if component.role == role
            }
            for role in {
                "segmentation",
                "classification",
                "primary_ocsr",
                "markush_ocsr",
                "sar_table",
            }
        }
        expected_component_ids = {
            "segmentation": {f"segmentation.{self.runtime_contract.segmentation_tool}"},
            "primary_ocsr": {f"ocsr.{tool}" for tool in self.runtime_contract.primary_ocsr_tools},
            "markush_ocsr": {f"ocsr.{tool}" for tool in self.runtime_contract.markush_ocsr_tools},
            "sar_table": {f"ocsr.{tool}" for tool in self.runtime_contract.sar_table_tools},
        }
        for role, expected_ids in expected_component_ids.items():
            if role_component_ids[role] != expected_ids:
                raise ValueError(f"{role} components must exactly match the runtime tool contract")
        if len(role_component_ids["classification"]) != 1:
            raise ValueError(
                "classifier_required=true requires exactly one classification component"
            )
        return self


class PreflightCheck(BaseModel):
    """Machine-readable result for a single production invariant."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    check: str
    passed: bool
    detail: str


class VisionPreflightReport(BaseModel):
    """Complete preflight report, suitable for a deployment gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    roster_id: str
    roster_sha256: str
    ml_bom_sha256: str
    passed: bool
    checks: tuple[PreflightCheck, ...]


def _validate_relative_path(value: str, *, field_name: str) -> None:
    path = Path(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or "\x00" in value
        or value != path.as_posix()
    ):
        raise ValueError(f"{field_name} must be a normalized relative path")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_expected_sha256(value: str, *, label: str) -> str:
    normalized = value.strip().lower()
    if not SHA256_RE.fullmatch(normalized):
        raise VisionPreflightError(f"{label} must be a lowercase SHA-256 digest")
    return normalized.removeprefix("sha256:")


def _resolve_runtime_path(
    runtime_root: Path,
    relative_path: str,
    *,
    allow_final_symlink_escape: bool = False,
) -> Path:
    _validate_relative_path(relative_path, field_name="runtime path")
    root = runtime_root.resolve(strict=True)
    candidate = root / relative_path
    containment_target = candidate.parent if allow_final_symlink_escape else candidate
    try:
        containment_target.resolve(strict=False).relative_to(root)
    except (OSError, ValueError):
        raise VisionPreflightError("runtime path escapes the configured runtime root") from None
    return candidate


def load_roster(path: str | Path = DEFAULT_ROSTER_PATH) -> tuple[VisionProductionRoster, str]:
    """Load and hash the exact roster bytes that will be release-bound."""
    roster_path = Path(path)
    try:
        raw = roster_path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise VisionPreflightError("cannot read production vision roster") from exc
    roster = VisionProductionRoster.model_validate(payload)
    return roster, hashlib.sha256(raw).hexdigest()


def _probe_component_imports(
    python_path: Path,
    required_imports: Sequence[str],
    *,
    timeout_seconds: float,
) -> None:
    probe = (
        "import importlib.util,json,sys;"
        "mods=json.loads(sys.argv[1]);"
        "missing=[m for m in mods if importlib.util.find_spec(m) is None];"
        "print(json.dumps(missing));"
        "raise SystemExit(bool(missing))"
    )
    env = os.environ.copy()
    env.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PIP_NO_INDEX": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PYTHONNOUSERSITE": "1",
        }
    )
    try:
        completed = subprocess.run(
            [str(python_path), "-c", probe, json.dumps(list(required_imports))],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VisionPreflightError("worker dependency probe could not complete") from exc
    if completed.returncode != 0:
        raise VisionPreflightError("one or more required worker dependencies are unavailable")


def run_production_preflight(
    *,
    roster_path: str | Path = DEFAULT_ROSTER_PATH,
    runtime_root: str | Path = PROJECT_ROOT,
    ml_bom_path: str | Path,
    expected_roster_sha256: str | None,
    expected_ml_bom_sha256: str | None,
    production: bool = True,
    probe_imports: bool = True,
    import_probe_timeout_seconds: float = 20.0,
) -> VisionPreflightReport:
    """Verify roster identity, runtime availability, licensing, and model bytes.

    Production mode requires independently supplied digests for both control
    documents. Every component and model is checked; failures are aggregated
    into one machine-readable report and never downgraded to warnings.
    """
    roster, roster_sha256 = load_roster(roster_path)
    root = Path(runtime_root)
    # Normalize without dereferencing the final path: production must detect
    # and reject a mutable symlink rather than silently binding its target.
    manifest_path = Path(ml_bom_path).absolute()
    checks: list[PreflightCheck] = []

    def record(check: str, operation) -> None:
        try:
            detail = operation()
        except (ModelChecksumError, OSError, ValueError, VisionPreflightError) as exc:
            checks.append(PreflightCheck(check=check, passed=False, detail=str(exc)))
        else:
            checks.append(PreflightCheck(check=check, passed=True, detail=detail or "verified"))

    def verify_roster_identity() -> str:
        if production and not expected_roster_sha256:
            raise VisionPreflightError("production requires PRAVIAR_VISION_ROSTER_SHA256")
        if expected_roster_sha256:
            expected = _normalize_expected_sha256(
                expected_roster_sha256,
                label="expected roster digest",
            )
            if roster_sha256 != expected:
                raise VisionPreflightError("production vision roster checksum mismatch")
        return roster_sha256

    record("control.roster_identity", verify_roster_identity)

    ml_bom_sha256 = ""

    def verify_ml_bom_identity() -> str:
        nonlocal ml_bom_sha256
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise VisionPreflightError("ML-BOM manifest is unavailable or is a symlink")
        ml_bom_sha256 = _sha256_file(manifest_path)
        if production and not expected_ml_bom_sha256:
            raise VisionPreflightError("production requires PRAVIAR_ML_BOM_SHA256")
        if expected_ml_bom_sha256:
            expected = _normalize_expected_sha256(
                expected_ml_bom_sha256,
                label="expected ML-BOM digest",
            )
            if ml_bom_sha256 != expected:
                raise VisionPreflightError("ML-BOM checksum mismatch")
        return ml_bom_sha256

    record("control.ml_bom_identity", verify_ml_bom_identity)

    def verify_runtime_policy() -> str:
        if roster.runtime_downloads_allowed:
            raise VisionPreflightError("runtime model downloads must be disabled")
        return "runtime model downloads prohibited"

    record("control.offline_runtime", verify_runtime_policy)

    for component in roster.components:
        component_prefix = f"component.{component.component_id}"

        def verify_worker(component: VisionComponent = component) -> str:
            worker = _resolve_runtime_path(root, component.worker_path)
            if not worker.is_file() or worker.is_symlink():
                raise VisionPreflightError("worker source is unavailable or is a symlink")
            return "worker source available"

        record(f"{component_prefix}.worker", verify_worker)

        python_path = _resolve_runtime_path(
            root,
            f"{component.venv_path}/bin/python",
            allow_final_symlink_escape=True,
        )

        def verify_python(python_path: Path = python_path) -> str:
            if not python_path.is_file() or not os.access(python_path, os.X_OK):
                raise VisionPreflightError("isolated worker Python is unavailable")
            return "isolated worker Python executable available"

        record(f"{component_prefix}.python", verify_python)

        if probe_imports:

            def verify_imports(
                python_path: Path = python_path,
                component: VisionComponent = component,
            ) -> str:
                _probe_component_imports(
                    python_path,
                    component.required_imports,
                    timeout_seconds=import_probe_timeout_seconds,
                )
                return "required worker dependencies available offline"

            record(f"{component_prefix}.imports", verify_imports)

        for artifact in component.models:

            def verify_artifact(
                artifact: VisionModelArtifact = artifact,
            ) -> str:
                artifact_path = _resolve_runtime_path(root, artifact.runtime_path)
                if artifact.artifact_kind == "directory_tree_v1":
                    return verify_model_directory_from_ml_bom(
                        artifact_path,
                        model_id=artifact.model_id,
                        manifest_path=manifest_path,
                    )
                return verify_model_checksum_from_ml_bom(
                    artifact_path,
                    model_id=artifact.model_id,
                    manifest_path=manifest_path,
                )

            record(f"model.{artifact.model_id}", verify_artifact)

    def verify_ml_bom_stability() -> str:
        if not ml_bom_sha256:
            raise VisionPreflightError("ML-BOM identity was not established")
        if manifest_path.is_symlink() or _sha256_file(manifest_path) != ml_bom_sha256:
            raise VisionPreflightError("ML-BOM changed during production preflight")
        return ml_bom_sha256

    record("control.ml_bom_stability", verify_ml_bom_stability)

    return VisionPreflightReport(
        roster_id=roster.roster_id,
        roster_sha256=roster_sha256,
        ml_bom_sha256=ml_bom_sha256,
        passed=all(check.passed for check in checks),
        checks=tuple(checks),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight", help="verify the production runtime")
    preflight.add_argument(
        "--roster",
        default=os.environ.get("PRAVIAR_VISION_ROSTER_PATH", str(DEFAULT_ROSTER_PATH)),
    )
    preflight.add_argument(
        "--runtime-root",
        default=os.environ.get("PRAVIAR_VISION_RUNTIME_ROOT", str(PROJECT_ROOT)),
    )
    preflight.add_argument(
        "--ml-bom",
        default=os.environ.get("PRAVIAR_ML_BOM_PATH"),
        required=os.environ.get("PRAVIAR_ML_BOM_PATH") is None,
    )
    preflight.add_argument(
        "--expected-roster-sha256",
        default=os.environ.get("PRAVIAR_VISION_ROSTER_SHA256"),
    )
    preflight.add_argument(
        "--expected-ml-bom-sha256",
        default=os.environ.get("PRAVIAR_ML_BOM_SHA256"),
    )
    preflight.add_argument("--production", action="store_true")
    preflight.add_argument("--skip-import-probes", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the production preflight CLI."""
    args = _build_parser().parse_args(argv)
    try:
        report = run_production_preflight(
            roster_path=args.roster,
            runtime_root=args.runtime_root,
            ml_bom_path=args.ml_bom,
            expected_roster_sha256=args.expected_roster_sha256,
            expected_ml_bom_sha256=args.expected_ml_bom_sha256,
            production=args.production,
            probe_imports=not args.skip_import_probes,
        )
    except Exception as exc:
        failure = {
            "schema_version": 1,
            "passed": False,
            "error": type(exc).__name__,
        }
        print(json.dumps(failure, sort_keys=True))
        return 2
    print(report.model_dump_json())
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
