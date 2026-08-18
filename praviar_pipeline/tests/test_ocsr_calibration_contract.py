from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import SecretStr

from praviar_pipeline.ocsr.calibration_contract import (
    CALIBRATION_DOMAIN,
    EXACTNESS_DEFINITION,
    CalibrationContractError,
    require_verified_calibration,
    sign_calibration_artifact,
)
from praviar_pipeline.ocsr.ensemble import calibrate_confidence, set_thresholds_from_settings
from praviar_pipeline.pipeline.drawing_rollout import drawing_evidence_can_influence
from praviar_pipeline.vision_production import DEFAULT_ROSTER_PATH, load_roster

if TYPE_CHECKING:
    from pathlib import Path

_KEY_ID = "test-calibration-key"
_PRIVATE_KEY = Ed25519PrivateKey.generate()
_PUBLIC_KEY_B64 = base64.b64encode(
    _PRIVATE_KEY.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
).decode()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _artifact_settings(
    tmp_path: Path,
    *,
    include_markush: bool = False,
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> tuple[SimpleNamespace, Path]:
    roster, roster_sha256 = load_roster(DEFAULT_ROSTER_PATH)
    tools = (
        ("molscribe", "molsight", "markushgrapher")
        if include_markush
        else ("molscribe", "molsight")
    )
    components = {
        component.component_id.removeprefix("ocsr."): component
        for component in roster.components
        if component.role in {"primary_ocsr", "markush_ocsr"}
    }
    entries = []
    tool_bindings = []
    container_digests = {}
    worker_image_digest = f"sha256:{_digest('worker-container')}"
    for index, tool_id in enumerate(tools):
        models = []
        for model in components[tool_id].models:
            model_sha = _digest(model.model_id)
            entries.append({"model_id": model.model_id, "sha256": model_sha})
            models.append({"model_id": model.model_id, "sha256": model_sha})
        container_digest = worker_image_digest
        container_digests[tool_id] = container_digest
        tool_bindings.append(
            {
                "tool_id": tool_id,
                "models": models,
                "container_image_digest": container_digest,
                "calibration_method": "platt",
                "platt_a": 1.1 + index,
                "platt_b": -0.2 + index,
            }
        )

    ml_bom_path = tmp_path / "ml-bom.json"
    ml_bom_path.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    ml_bom_sha256 = hashlib.sha256(ml_bom_path.read_bytes()).hexdigest()
    now = datetime.now(UTC)
    payload = {
        "schema_version": "praviar-ocsr-calibration/v1",
        "artifact_id": "test-calibration-v1",
        "artifact_revision": 1,
        "revocation_epoch": 0,
        "issued_at": (issued_at or now - timedelta(hours=1)).isoformat(),
        "expires_at": (expires_at or now + timedelta(days=30)).isoformat(),
        "calibration_corpus_sha256": _digest("calibration-corpus"),
        "runtime_roster_sha256": roster_sha256,
        "ml_bom_sha256": ml_bom_sha256,
        "exactness_definition": EXACTNESS_DEFINITION,
        "domain": CALIBRATION_DOMAIN,
        "jurisdictions": ["US", "EP"],
        "minimum_resolved_confidence": 0.65,
        "tools": tool_bindings,
    }
    artifact_path = tmp_path / "calibration.json"
    artifact_path.write_text(
        json.dumps(
            sign_calibration_artifact(
                payload,
                private_key=_PRIVATE_KEY,
                key_id=_KEY_ID,
            )
        ),
        encoding="utf-8",
    )
    settings = SimpleNamespace(
        drawing_analysis_rollout_state="production",
        drawing_analysis_evidence_gate_passed=True,
        drawing_analysis_jurisdictions=["US"],
        drawing_analysis_calibration_artifact_path=str(artifact_path),
        drawing_analysis_calibration_artifact_sha256=hashlib.sha256(
            artifact_path.read_bytes()
        ).hexdigest(),
        drawing_analysis_calibration_min_revision=1,
        drawing_analysis_calibration_revocation_epoch=0,
        drawing_analysis_revoked_calibration_artifact_ids=(),
        drawing_analysis_calibration_public_key=SecretStr(_PUBLIC_KEY_B64),
        drawing_analysis_calibration_key_id=_KEY_ID,
        drawing_analysis_calibration_corpus_sha256=_digest("calibration-corpus"),
        drawing_analysis_vision_roster_path=str(DEFAULT_ROSTER_PATH),
        drawing_analysis_ml_bom_path=str(ml_bom_path),
        drawing_analysis_container_image_digests=container_digests,
        certification_worker_oci_image_digest=worker_image_digest,
        drawing_ensemble_tools=list(tools),
        drawing_segmentation_tool="decimer",
        drawing_classifier_enabled=True,
        drawing_markushgrapher_enabled=include_markush,
        drawing_markush_rollout_state="production" if include_markush else "shadow",
        drawing_cascade_min_resolved_conf=0.65,
    )
    return settings, artifact_path


def test_verified_calibration_binds_runtime_scope_and_can_influence(
    tmp_path: Path,
) -> None:
    settings, _ = _artifact_settings(tmp_path)

    verified = require_verified_calibration(settings)

    assert verified.artifact_id == "test-calibration-v1"
    assert set(verified.parameters) == {"molscribe", "molsight"}
    assert drawing_evidence_can_influence(settings) is True


def test_verified_calibration_binds_live_markush_models(
    tmp_path: Path,
) -> None:
    settings, _ = _artifact_settings(tmp_path, include_markush=True)

    verified = require_verified_calibration(settings)

    assert set(verified.parameters) == {
        "molscribe",
        "molsight",
        "markushgrapher",
    }


def test_missing_or_stale_calibration_fails_closed(tmp_path: Path) -> None:
    settings, _ = _artifact_settings(
        tmp_path,
        issued_at=datetime(2025, 1, 1, tzinfo=UTC),
        expires_at=datetime(2025, 2, 1, tzinfo=UTC),
    )

    with pytest.raises(CalibrationContractError, match="stale"):
        require_verified_calibration(settings)
    assert drawing_evidence_can_influence(settings) is False

    settings.drawing_analysis_calibration_artifact_path = ""
    with pytest.raises(CalibrationContractError, match="requires a calibration artifact"):
        require_verified_calibration(settings)


def test_signed_artifact_rejects_tampering_and_unknown_tools(tmp_path: Path) -> None:
    settings, artifact_path = _artifact_settings(tmp_path)
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["tools"][0]["platt_a"] = 99
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    settings.drawing_analysis_calibration_artifact_sha256 = hashlib.sha256(
        artifact_path.read_bytes()
    ).hexdigest()

    with pytest.raises(CalibrationContractError, match="signature mismatch"):
        require_verified_calibration(settings)

    settings, _ = _artifact_settings(tmp_path)
    settings.drawing_ensemble_tools.append("unknown-tool")
    settings.drawing_analysis_container_image_digests["unknown-tool"] = (
        f"sha256:{_digest('unknown-container')}"
    )
    with pytest.raises(CalibrationContractError, match="unknown or prohibited"):
        require_verified_calibration(settings)


def test_calibration_rejects_runtime_roster_drift(tmp_path: Path) -> None:
    settings, _ = _artifact_settings(tmp_path)
    settings.drawing_segmentation_tool = "chemsam"
    with pytest.raises(CalibrationContractError, match="segmentation tool"):
        require_verified_calibration(settings)

    settings, _ = _artifact_settings(tmp_path)
    settings.drawing_classifier_enabled = False
    with pytest.raises(CalibrationContractError, match=r"requires.*classifier"):
        require_verified_calibration(settings)


def test_calibration_anti_replay_pins_revision_epoch_and_revocation(
    tmp_path: Path,
) -> None:
    settings, artifact_path = _artifact_settings(tmp_path)
    settings.drawing_analysis_calibration_artifact_sha256 = "0" * 64
    with pytest.raises(CalibrationContractError, match="SHA-256 pin mismatch"):
        require_verified_calibration(settings)

    settings.drawing_analysis_calibration_artifact_sha256 = hashlib.sha256(
        artifact_path.read_bytes()
    ).hexdigest()
    settings.drawing_analysis_calibration_min_revision = 2
    with pytest.raises(CalibrationContractError, match="revision is below"):
        require_verified_calibration(settings)

    settings.drawing_analysis_calibration_min_revision = 1
    settings.drawing_analysis_calibration_revocation_epoch = 1
    with pytest.raises(CalibrationContractError, match="revocation epoch is stale"):
        require_verified_calibration(settings)

    settings.drawing_analysis_calibration_revocation_epoch = 0
    settings.drawing_analysis_revoked_calibration_artifact_ids = ("test-calibration-v1",)
    with pytest.raises(CalibrationContractError, match="artifact is revoked"):
        require_verified_calibration(settings)


def test_live_threshold_bridge_requires_artifact_and_unknown_calibration_fails(
    tmp_path: Path,
) -> None:
    settings, _ = _artifact_settings(tmp_path)
    settings.drawing_ensemble_molscribe_high_conf = 0.8
    settings.drawing_ensemble_agreement_ratio_min = 1.5
    settings.drawing_ensemble_low_agreement_penalty = 0.8
    settings.drawing_ensemble_formula_boost = 1.2
    settings.drawing_text_confirm_conf_bump = 0.1
    settings.drawing_cascade_plausibility_threshold = 0.4
    settings.drawing_max_resolved_atoms = 100

    set_thresholds_from_settings(settings)

    with pytest.raises(RuntimeError, match="no verified calibration binding"):
        calibrate_confidence(0.5, "unknown-tool")

    settings.drawing_analysis_calibration_artifact_path = ""
    with pytest.raises(CalibrationContractError):
        set_thresholds_from_settings(settings)
