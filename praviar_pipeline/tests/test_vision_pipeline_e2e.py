"""End-to-end CI gate for the vision pipeline.

Runs the cascade harness
(`research/experiments/drawing_analysis/eval_pdf_to_smiles.py`) against a
small fixed sample of pre-rasterized USPTO patent pages and asserts the
stage-attributed thresholds.

Gating philosophy:
  - **Hard fail** on regression in stages we already know work
    (detection ≥ 80%, triage chemical-route ≥ 80%).
  - **Warn but don't fail** on the end-to-end OCSR number until the
    triage-strategy and crop-quality questions in `phase42_live_full`
    are resolved (see plan doc Phase 4.2 caveats).

Skipped automatically when:
  - The 50-page US sample under `research/benchmarks/patcid/page_pdfs/us/`
    is missing (CI hasn't pulled it).
  - Any of decimer/molclassifier venvs are missing (small-runner CI).
"""

from __future__ import annotations

import hashlib
import json
import os
import runpy
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS = REPO_ROOT / "research" / "experiments" / "drawing_analysis" / "eval_pdf_to_smiles.py"
PAGE_DIR = REPO_ROOT / "research" / "benchmarks" / "patcid" / "page_pdfs" / "us"
DECIMER_VENV = REPO_ROOT / "praviar_pipeline" / "venvs" / "decimer" / "bin" / "python"
MOLCLASSIFIER_VENV = REPO_ROOT / "praviar_pipeline" / "venvs" / "molclassifier" / "bin" / "python"
PRAVIAR_PIPELINE_PY = REPO_ROOT / "praviar_pipeline" / ".venv" / "bin" / "python"
DEFAULT_MOLCLASSIFIER_CKPT = (
    REPO_ROOT / "praviar_pipeline" / "models" / "molclassifier" / "molclassifier_model.chpt"
)
DEFAULT_ML_BOM_PATH = (
    REPO_ROOT / "docs" / "trust" / "evidence" / "supply-chain" / "ml-bom-local-2026-05-25.json"
)
MOLCLASSIFIER_MODEL_ID = "molclassifier/local"


def _resolve_repo_path(value: str | None, default: Path) -> Path:
    path = Path(value) if value else default
    return path if path.is_absolute() else REPO_ROOT / path


MOLCLASSIFIER_CKPT = _resolve_repo_path(
    os.environ.get("MOLCLASSIFIER_CKPT"),
    DEFAULT_MOLCLASSIFIER_CKPT,
)
ML_BOM_PATH = _resolve_repo_path(
    os.environ.get("PRAVIAR_ML_BOM_PATH"),
    DEFAULT_ML_BOM_PATH,
)

CI_SAMPLE_SIZE = int(os.environ.get("VISION_E2E_SAMPLE_SIZE", "5"))
OCSR_MODE = os.environ.get("VISION_E2E_OCSR_MODE", "replay")
if OCSR_MODE not in {"replay", "live"}:
    raise ValueError("VISION_E2E_OCSR_MODE must be 'replay' or 'live'")

# Thresholds — minimums we expect on the CI sample. Set well below the
# observed n=50 numbers (96% detection, 93% triage routing) so genuine CI
# variance doesn't flap, but tight enough to catch regressions.
MIN_DETECTION_RECALL = 0.50
MIN_TRIAGE_CHEMICAL_ROUTE = 0.80


@dataclass(frozen=True)
class _MolClassifierReadiness:
    expected_sha256: str | None = None
    actual_sha256: str | None = None
    missing_asset_reason: str | None = None
    approval_block_reason: str | None = None
    error: str | None = None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inspect_molclassifier_readiness(
    checkpoint_path: Path,
    manifest_path: Path,
) -> _MolClassifierReadiness:
    """Inspect test readiness without conflating trust failures with approval."""
    if not checkpoint_path.is_file():
        return _MolClassifierReadiness(
            missing_asset_reason="MolClassifier checkpoint is not available on this runner"
        )
    if not manifest_path.is_file():
        return _MolClassifierReadiness(
            error=f"MolClassifier ML-BOM manifest is missing: {manifest_path}"
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _MolClassifierReadiness(
            error=f"MolClassifier ML-BOM manifest is unreadable: {manifest_path}"
        )
    if not isinstance(manifest, dict) or not isinstance(manifest.get("entries"), list):
        return _MolClassifierReadiness(
            error="MolClassifier ML-BOM manifest must contain an entries list"
        )

    entry = next(
        (
            candidate
            for candidate in manifest["entries"]
            if isinstance(candidate, dict) and candidate.get("model_id") == MOLCLASSIFIER_MODEL_ID
        ),
        None,
    )
    if entry is None:
        return _MolClassifierReadiness(
            error=f"{MOLCLASSIFIER_MODEL_ID} is not registered in the ML-BOM"
        )

    expected_sha256 = str(entry.get("sha256") or "").lower()
    if expected_sha256.startswith("sha256:"):
        expected_sha256 = expected_sha256.removeprefix("sha256:")
    actual_sha256 = _sha256_file(checkpoint_path)
    digest_error: str | None = None
    if len(expected_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in expected_sha256
    ):
        digest_error = f"{MOLCLASSIFIER_MODEL_ID} has an invalid SHA-256 digest in the ML-BOM"
    elif actual_sha256 != expected_sha256:
        digest_error = (
            f"{MOLCLASSIFIER_MODEL_ID} checkpoint digest mismatch: "
            f"expected {expected_sha256}, observed {actual_sha256}"
        )

    license_status = str(entry.get("license_status") or "").strip()
    release_blocker = entry.get("release_blocker")
    approval_block_reason: str | None = None
    if license_status == "pending_commercial_review" or release_blocker is True:
        approval_block_reason = (
            "MolClassifier human commercial-use approval remains pending "
            f"(license_status={license_status or 'missing'}, "
            f"release_blocker={release_blocker!r})"
        )

    approval_state_error: str | None = None
    if approval_block_reason is None and (
        license_status != "approved_for_commercial_use" or release_blocker is not False
    ):
        approval_state_error = (
            "MolClassifier ML-BOM approval state is neither explicitly pending/blocked "
            "nor release-ready"
        )

    return _MolClassifierReadiness(
        expected_sha256=expected_sha256,
        actual_sha256=actual_sha256,
        approval_block_reason=approval_block_reason,
        error=digest_error or approval_state_error,
    )


def _interpreter_can_import(interpreter: Path, module: str) -> bool:
    if not interpreter.exists():
        return False
    proc = subprocess.run(
        [str(interpreter), "-c", f"import {module}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode == 0


_MOLCLASSIFIER_READINESS = _inspect_molclassifier_readiness(
    MOLCLASSIFIER_CKPT,
    ML_BOM_PATH,
)


def _ordinary_suite_skip_reason() -> str | None:
    if not HARNESS.exists():
        return "eval_pdf_to_smiles.py not available in this checkout"
    if not PAGE_DIR.exists() or not list(PAGE_DIR.glob("*.png")):
        return "USPTO page PNGs not present (run download_uspto_pages.py)"
    if not DECIMER_VENV.exists() or not MOLCLASSIFIER_VENV.exists():
        return "DECIMER or MolClassifier venv missing on this runner"
    if not PRAVIAR_PIPELINE_PY.exists():
        return "praviar_pipeline/.venv/bin/python missing"
    if not _interpreter_can_import(PRAVIAR_PIPELINE_PY, "cv2"):
        return "vision e2e harness subprocess requires optional OpenCV dependency"
    if _MOLCLASSIFIER_READINESS.missing_asset_reason is not None:
        return _MOLCLASSIFIER_READINESS.missing_asset_reason
    return _MOLCLASSIFIER_READINESS.approval_block_reason


_ORDINARY_SUITE_SKIP_REASON = _ordinary_suite_skip_reason()
_ordinary_vision_e2e = pytest.mark.skipif(
    _ORDINARY_SUITE_SKIP_REASON is not None,
    reason=_ORDINARY_SUITE_SKIP_REASON or "",
)


def test_molclassifier_checkpoint_matches_registered_digest() -> None:
    """A pending approval must never mask a corrupt or substituted checkpoint."""
    if _MOLCLASSIFIER_READINESS.missing_asset_reason is not None:
        pytest.skip(_MOLCLASSIFIER_READINESS.missing_asset_reason)
    assert _MOLCLASSIFIER_READINESS.error is None, _MOLCLASSIFIER_READINESS.error
    assert _MOLCLASSIFIER_READINESS.actual_sha256
    assert _MOLCLASSIFIER_READINESS.actual_sha256 == _MOLCLASSIFIER_READINESS.expected_sha256


def test_pending_approval_does_not_mask_checkpoint_digest_mismatch(
    tmp_path: Path,
) -> None:
    checkpoint_path = tmp_path / "molclassifier.chpt"
    checkpoint_path.write_bytes(b"present-but-substituted-checkpoint")
    manifest_path = tmp_path / "ml-bom.json"
    manifest_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "model_id": MOLCLASSIFIER_MODEL_ID,
                        "sha256": hashlib.sha256(b"registered-checkpoint").hexdigest(),
                        "license_status": "pending_commercial_review",
                        "release_blocker": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    readiness = _inspect_molclassifier_readiness(checkpoint_path, manifest_path)

    assert readiness.approval_block_reason is not None
    assert readiness.error is not None
    assert "checkpoint digest mismatch" in readiness.error


def test_harness_forwards_explicit_molclassifier_trust_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not HARNESS.exists():
        pytest.skip("eval_pdf_to_smiles.py not available in this checkout")
    checkpoint_path = "/tmp/praviar-test-molclassifier.chpt"
    manifest_path = "/tmp/praviar-test-ml-bom.json"
    monkeypatch.setenv("MOLCLASSIFIER_CKPT", checkpoint_path)
    monkeypatch.setenv("PRAVIAR_ML_BOM_PATH", manifest_path)

    harness_namespace = runpy.run_path(str(HARNESS))
    worker_env = harness_namespace["_molclassifier_worker_env"](
        box_thresh="0.800000",
        nc_min_conf="0.950000",
    )

    assert worker_env["MOLCLASSIFIER_CKPT"] == checkpoint_path
    assert worker_env["PRAVIAR_ML_BOM_PATH"] == manifest_path
    assert worker_env["MOLCLASSIFIER_BOX_THRESH"] == "0.800000"
    assert worker_env["MOLCLASSIFIER_NC_MIN_CONF"] == "0.950000"


@pytest.fixture(scope="module")
def harness_results(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Run the harness once and yield parsed results JSON."""
    out_dir = tmp_path_factory.mktemp("pdf_to_smiles_e2e")
    target_json = out_dir / f"results_us_n{CI_SAMPLE_SIZE}_{OCSR_MODE}_decimer.json"
    env = os.environ.copy()
    env["APP_ENV"] = "test"
    env["ANTHROPIC_API_KEY"] = "dummy"
    env.pop("MOLCLASSIFIER_BOX_THRESH", None)
    env.pop("MOLCLASSIFIER_NC_MIN_CONF", None)
    env["MOLCLASSIFIER_CKPT"] = str(MOLCLASSIFIER_CKPT)
    env["PRAVIAR_ML_BOM_PATH"] = str(ML_BOM_PATH)

    proc = subprocess.run(
        [
            str(PRAVIAR_PIPELINE_PY),
            str(HARNESS),
            "--jurisdiction",
            "us",
            "--limit",
            str(CI_SAMPLE_SIZE),
            "--iou-thresh",
            "0.5",
            "--ocsr-mode",
            OCSR_MODE,
            "--output-dir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(REPO_ROOT),
        env=env,
    )
    if proc.returncode != 0:
        pytest.fail(
            f"Harness exited {proc.returncode}\n"
            f"stdout: {proc.stdout[-1000:]}\n"
            f"stderr: {proc.stderr[-1000:]}"
        )
    if not target_json.exists():
        pytest.fail(f"Harness did not write results JSON at {target_json}")
    data = json.loads(target_json.read_text())
    return data


@_ordinary_vision_e2e
def test_summary_has_required_fields(harness_results: dict) -> None:
    assert harness_results["totals"]["n_pages"] == CI_SAMPLE_SIZE
    assert harness_results["ocsr_mode"] == OCSR_MODE
    sa = harness_results["stage_attribution"]
    for k in (
        "detection_recall",
        "triage_chemical_route_rate",
        "ocsr_resolved_rate",
        "end_to_end_correct_per_gt_box",
        "end_to_end_correct_per_labeled_gt",
    ):
        assert k in sa, f"missing stage_attribution key: {k}"


@_ordinary_vision_e2e
def test_detection_recall_above_floor(harness_results: dict) -> None:
    sa = harness_results["stage_attribution"]
    assert sa["detection_recall"] >= MIN_DETECTION_RECALL, (
        f"Detection recall {sa['detection_recall']:.3f} dropped below "
        f"{MIN_DETECTION_RECALL:.3f} — regression in DECIMER bbox output."
    )


@_ordinary_vision_e2e
def test_triage_chemical_route_above_floor(harness_results: dict) -> None:
    sa = harness_results["stage_attribution"]
    assert sa["triage_chemical_route_rate"] >= MIN_TRIAGE_CHEMICAL_ROUTE, (
        f"Triage chemical-route rate {sa['triage_chemical_route_rate']:.3f} "
        f"dropped below {MIN_TRIAGE_CHEMICAL_ROUTE:.3f} — MolClassifier "
        f"is over-firing on `non_chemical` for chemical structures."
    )


@_ordinary_vision_e2e
def test_per_page_records_are_complete(harness_results: dict) -> None:
    for p in harness_results["per_page"]:
        assert {"stem", "n_gt", "n_pred", "n_matched", "matches"} <= set(p.keys())
        assert p["n_matched"] <= min(p["n_gt"], p["n_pred"])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
