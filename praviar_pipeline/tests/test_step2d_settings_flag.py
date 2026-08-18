"""Verify ``settings.drawing_segmentation_tool`` reaches the segmentation factory.

These tests do *not* run YOLO or any subprocess; they assert the wiring
between ``step2d_drawings._get_segmentation_runner(settings)`` and
``factories.get_segmentation_runner(...)`` by mocking the factory and
inspecting the kwargs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from praviar_pipeline.model_supply_chain import (
    REQUIRED_DOC2SAR_MODEL_IDS,
    REQUIRED_DRAWING_MODEL_IDS,
)


@pytest.fixture()
def captured_factory_kwargs(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace ``drawing_factories.get_segmentation_runner`` with a spy
    that records the kwargs it was called with and returns a sentinel.
    """
    from praviar_pipeline.pipeline import step2d_drawings

    captured: dict[str, Any] = {}

    def _spy(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "sentinel-runner"

    monkeypatch.setattr(
        step2d_drawings.drawing_factories,
        "get_segmentation_runner",
        _spy,
    )
    return captured


def _approved_entry(model_id: str, *, sha256: str = "a" * 64) -> dict[str, object]:
    return {
        "model_id": model_id,
        "path": f"models/{model_id.replace('/', '_')}.bin",
        "size_bytes": len(_model_payload(model_id)),
        "sha256": sha256,
        "license_evidence_path": (
            f"docs/trust/evidence/supply-chain/licenses/{model_id.replace('/', '_')}.md"
        ),
        "license_status": "approved_for_commercial_use",
        "release_blocker": False,
    }


def _model_payload(model_id: str) -> bytes:
    return f"approved test model bytes: {model_id}\n".encode()


def _write_approved_ml_bom(tmp_path, *, model_ids=None, write_model_files: bool = True) -> str:
    manifest_path = tmp_path / "ml-bom-approved.json"
    model_ids = sorted(model_ids or REQUIRED_DRAWING_MODEL_IDS)
    entries: list[dict[str, object]] = []
    for model_id in model_ids:
        model_payload = _model_payload(model_id)
        if write_model_files:
            model_path = tmp_path / "models" / f"{model_id.replace('/', '_')}.bin"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_bytes(model_payload)
        license_path = (
            tmp_path
            / "docs/trust/evidence/supply-chain/licenses"
            / f"{model_id.replace('/', '_')}.md"
        )
        license_path.parent.mkdir(parents=True, exist_ok=True)
        license_path.write_text(
            f"# Approved License Evidence For {model_id}\n\n"
            "license_status: approved_for_commercial_use\n"
            "primary_source_url: https://example.test/model-license\n"
            "source_kind: vendor_permission_artifact\n"
            "retrieved_at: 2026-06-03T00:00:00Z\n"
            f"retrieved_sha256: {hashlib.sha256(model_payload).hexdigest()}\n"
            "approved_use: beta/production OCSR model execution\n"
            "review_authority: security_lead\n",
            encoding="utf-8",
        )
        entries.append(
            _approved_entry(
                model_id,
                sha256=hashlib.sha256(model_payload).hexdigest(),
            )
        )
    manifest_path.write_text(
        json.dumps({"entries": entries}),
        encoding="utf-8",
    )
    return str(manifest_path)


def _write_blocked_ml_bom(tmp_path) -> str:
    """Write a BOM covering all required models but with release_blocker=True.

    Model files and sha256 hashes are valid so validation reaches the
    release_blocker check and raises 'ML-BOM has unresolved model evidence'.
    """
    manifest_path_str = _write_approved_ml_bom(tmp_path)
    manifest_path = Path(manifest_path_str)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in payload["entries"]:
        entry["release_blocker"] = True
        entry["license_status"] = "pending_commercial_review"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    return manifest_path_str


def _write_approved_ml_bom_with_placeholder_license(tmp_path) -> str:
    manifest_path = Path(_write_approved_ml_bom(tmp_path))
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    first_entry = payload["entries"][0]
    first_license = tmp_path / first_entry["license_evidence_path"]
    first_license.write_text(
        f"# Approved License Evidence For {first_entry['model_id']}\n\n"
        "license_status: approved_for_commercial_use\n"
        "primary_source_url: https://example.test/model-license\n"
        "source_kind: vendor_permission_artifact\n"
        "retrieved_at: 2026-06-03T00:00:00Z\n"
        "retrieved_sha256: 0000000000000000000000000000000000000000000000000000000000000000\n"
        "approved_use: beta/production OCSR model execution\n"
        "review_authority: security_lead\n"
        "placeholder approval text\n",
        encoding="utf-8",
    )
    return str(manifest_path)


def test_default_settings_flag_is_decimer(captured_factory_kwargs: dict[str, Any]) -> None:
    """Default ``drawing_segmentation_tool='decimer'`` must reach the
    factory unchanged. Confirms the rollout default preserves prior
    behavior."""
    from praviar_pipeline.pipeline import step2d_drawings

    settings = SimpleNamespace(drawing_segmentation_tool="decimer")
    result = step2d_drawings._get_segmentation_runner(settings)

    assert result == "sentinel-runner"
    assert captured_factory_kwargs["backend"] == "decimer"
    assert "decimer" in captured_factory_kwargs["backends"]
    assert captured_factory_kwargs["backends"]["decimer"]["worker"].name == "decimer_seg_worker.py"


def test_moldet_flag_routes_to_moldet_worker(
    captured_factory_kwargs: dict[str, Any],
) -> None:
    """Setting ``drawing_segmentation_tool='moldet'`` must select the
    MolDet venv/worker pair via the canonical ``SEGMENTATION_BACKENDS``
    dispatch table."""
    from praviar_pipeline.pipeline import step2d_drawings

    settings = SimpleNamespace(drawing_segmentation_tool="moldet")
    step2d_drawings._get_segmentation_runner(settings)

    assert captured_factory_kwargs["backend"] == "moldet"
    backends = captured_factory_kwargs["backends"]
    assert set(backends) == {"decimer", "moldet", "chemsam"}
    assert backends["moldet"]["worker"].name == "moldet_seg_worker.py"
    assert backends["moldet"]["venv"].name == "moldet"


def test_chemsam_flag_routes_to_chemsam_worker(
    captured_factory_kwargs: dict[str, Any],
) -> None:
    """Setting ``drawing_segmentation_tool='chemsam'`` reaches the SAM
    backend. Tests the third branch of the Literal."""
    from praviar_pipeline.pipeline import step2d_drawings

    settings = SimpleNamespace(drawing_segmentation_tool="chemsam")
    step2d_drawings._get_segmentation_runner(settings)

    assert captured_factory_kwargs["backend"] == "chemsam"
    backends = captured_factory_kwargs["backends"]
    assert backends["chemsam"]["worker"].name == "chemsam_seg_worker.py"


def test_settings_class_defaults_to_decimer(monkeypatch: pytest.MonkeyPatch) -> None:
    """``Settings.drawing_segmentation_tool`` defaults to ``decimer`` (MIT license).
    MolDet weights are CC-BY-NC-SA-4.0 and are blocked from beta/production use.
    DECIMER is the default for all commercial deployments."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    from praviar_pipeline.config import Settings

    settings = Settings()  # type: ignore[call-arg]
    assert settings.drawing_segmentation_tool == "decimer"
    assert settings.drawing_analysis_rollout_state == "shadow"
    assert settings.drawing_analysis_evidence_gate_passed is False
    assert settings.drawing_markush_rollout_state == "shadow"
    assert settings.drawing_markushgrapher_enabled is False
    assert settings.drawing_analysis_shadow_mode is True


def test_settings_class_accepts_moldet_literal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``Settings.drawing_segmentation_tool='moldet'`` is a valid Literal
    value (proves the field rejects unknown strings via Pydantic)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    from praviar_pipeline.config import Settings

    settings = Settings(drawing_segmentation_tool="moldet")  # type: ignore[call-arg]
    assert settings.drawing_segmentation_tool == "moldet"


def test_settings_rejects_live_drawing_rollout_without_evidence_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live drawing decisions require the reviewed evidence gate to pass first."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import pydantic

    from praviar_pipeline.config import Settings

    with pytest.raises(pydantic.ValidationError, match="drawing_analysis_evidence_gate_passed"):
        Settings(drawing_analysis_rollout_state="beta")  # type: ignore[call-arg]


def test_settings_rejects_live_drawing_rollout_with_unresolved_ml_bom(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """An ML-BOM where every entry has release_blocker=True must not allow live rollout."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import pydantic

    from praviar_pipeline.config import Settings

    with pytest.raises(
        pydantic.ValidationError,
        match="Drawing model supply-chain validation failed",
    ):
        Settings(  # type: ignore[call-arg]
            drawing_analysis_rollout_state="beta",
            drawing_analysis_evidence_gate_passed=True,
            drawing_analysis_ml_bom_path=_write_blocked_ml_bom(tmp_path),
        )


def test_settings_rejects_moldet_in_production_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """MolDet (CC-BY-NC-SA-4.0) must be blocked in beta/production mode."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import pydantic

    from praviar_pipeline.config import Settings

    with pytest.raises(
        pydantic.ValidationError,
        match="Drawing model supply-chain validation failed",
    ):
        Settings(  # type: ignore[call-arg]
            drawing_analysis_rollout_state="beta",
            drawing_analysis_evidence_gate_passed=True,
            drawing_analysis_ml_bom_path=_write_approved_ml_bom(tmp_path),
            drawing_segmentation_tool="moldet",
        )


def test_settings_accepts_live_drawing_rollout_with_clean_ml_bom(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    from praviar_pipeline.config import Settings

    settings = Settings(  # type: ignore[call-arg]
        drawing_analysis_rollout_state="beta",
        drawing_analysis_evidence_gate_passed=True,
        drawing_analysis_ml_bom_path=_write_approved_ml_bom(tmp_path),
    )
    assert settings.drawing_analysis_rollout_state == "beta"
    assert settings.drawing_analysis_evidence_gate_passed is True


def test_settings_rejects_live_drawing_rollout_with_placeholder_license_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import pydantic

    from praviar_pipeline.config import Settings

    with pytest.raises(
        pydantic.ValidationError,
        match="Drawing model supply-chain validation failed",
    ):
        Settings(  # type: ignore[call-arg]
            drawing_analysis_rollout_state="beta",
            drawing_analysis_evidence_gate_passed=True,
            drawing_analysis_ml_bom_path=_write_approved_ml_bom_with_placeholder_license(tmp_path),
        )


def test_settings_rejects_live_drawing_rollout_with_shadow_markush_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import pydantic

    from praviar_pipeline.config import Settings

    with pytest.raises(pydantic.ValidationError, match="drawing_markush_rollout_state"):
        Settings(  # type: ignore[call-arg]
            drawing_analysis_rollout_state="beta",
            drawing_analysis_evidence_gate_passed=True,
            drawing_analysis_ml_bom_path=_write_approved_ml_bom(tmp_path),
            drawing_markushgrapher_enabled=True,
            drawing_markush_rollout_state="shadow",
        )


def test_settings_accepts_live_drawing_rollout_with_live_markush_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    from praviar_pipeline.config import Settings

    settings = Settings(  # type: ignore[call-arg]
        drawing_analysis_rollout_state="beta",
        drawing_analysis_evidence_gate_passed=True,
        drawing_analysis_ml_bom_path=_write_approved_ml_bom(tmp_path),
        drawing_markushgrapher_enabled=True,
        drawing_markush_rollout_state="beta",
    )

    assert settings.drawing_markushgrapher_enabled is True
    assert settings.drawing_markush_rollout_state == "beta"


def test_settings_rejects_markush_scope_agent_in_live_drawing_rollout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import pydantic

    from praviar_pipeline.config import Settings

    with pytest.raises(
        pydantic.ValidationError,
        match="experimental scope agent is shadow-only",
    ):
        Settings(  # type: ignore[call-arg]
            drawing_analysis_rollout_state="production",
            drawing_analysis_evidence_gate_passed=True,
            drawing_analysis_ml_bom_path=_write_approved_ml_bom(tmp_path),
            drawing_markush_scope_agent_enabled=True,
        )


def test_settings_rejects_live_drawing_rollout_with_shadow_doc2sar_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import pydantic

    from praviar_pipeline.config import Settings

    with pytest.raises(pydantic.ValidationError, match="drawing_doc2sar_enabled must be false"):
        Settings(  # type: ignore[call-arg]
            drawing_analysis_rollout_state="production",
            drawing_analysis_evidence_gate_passed=True,
            drawing_analysis_ml_bom_path=_write_approved_ml_bom(tmp_path),
            drawing_doc2sar_enabled=True,
            drawing_doc2sar_rollout_state="internal",
        )


def test_settings_rejects_live_doc2sar_before_supply_chain_evaluation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import pydantic

    from praviar_pipeline.config import Settings

    with pytest.raises(pydantic.ValidationError, match="drawing_doc2sar_enabled must be false"):
        Settings(  # type: ignore[call-arg]
            drawing_analysis_rollout_state="production",
            drawing_analysis_evidence_gate_passed=True,
            drawing_analysis_ml_bom_path=_write_approved_ml_bom(tmp_path),
            drawing_doc2sar_enabled=True,
            drawing_doc2sar_rollout_state="production",
        )


def test_settings_rejects_live_doc2sar_even_with_a_complete_ml_bom(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    import pydantic

    from praviar_pipeline.config import Settings

    with pytest.raises(pydantic.ValidationError, match="drawing_doc2sar_enabled must be false"):
        Settings(  # type: ignore[call-arg]
            drawing_analysis_rollout_state="production",
            drawing_analysis_evidence_gate_passed=True,
            drawing_analysis_ml_bom_path=_write_approved_ml_bom(
                tmp_path,
                model_ids=REQUIRED_DRAWING_MODEL_IDS | REQUIRED_DOC2SAR_MODEL_IDS,
            ),
            drawing_doc2sar_enabled=True,
            drawing_doc2sar_rollout_state="production",
        )


def test_settings_rejects_live_specialist_state_before_global_live_rollout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import pydantic

    from praviar_pipeline.config import Settings

    with pytest.raises(pydantic.ValidationError, match="drawing_markush_rollout_state"):
        Settings(drawing_markush_rollout_state="beta")  # type: ignore[call-arg]


def test_settings_rejects_live_drawing_rollout_with_incomplete_clean_ml_bom(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import pydantic

    from praviar_pipeline.config import Settings

    incomplete_model_ids = {"moldet/yolo11l_960_doc"}
    with pytest.raises(
        pydantic.ValidationError,
        match="Drawing model supply-chain validation failed",
    ):
        Settings(  # type: ignore[call-arg]
            drawing_analysis_rollout_state="beta",
            drawing_analysis_evidence_gate_passed=True,
            drawing_analysis_ml_bom_path=_write_approved_ml_bom(
                tmp_path,
                model_ids=incomplete_model_ids,
            ),
        )


def test_settings_rejects_live_drawing_rollout_with_fake_model_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import pydantic

    from praviar_pipeline.config import Settings

    with pytest.raises(
        pydantic.ValidationError,
        match="Drawing model supply-chain validation failed",
    ):
        Settings(  # type: ignore[call-arg]
            drawing_analysis_rollout_state="production",
            drawing_analysis_evidence_gate_passed=True,
            drawing_analysis_ml_bom_path=_write_approved_ml_bom(
                tmp_path,
                write_model_files=False,
            ),
        )


def test_settings_rejects_live_drawing_rollout_with_model_sha_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import pydantic

    from praviar_pipeline.config import Settings

    manifest_path = _write_approved_ml_bom(tmp_path)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    manifest["entries"][0]["sha256"] = "b" * 64
    Path(manifest_path).write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        pydantic.ValidationError,
        match="Drawing model supply-chain validation failed",
    ):
        Settings(  # type: ignore[call-arg]
            drawing_analysis_rollout_state="production",
            drawing_analysis_evidence_gate_passed=True,
            drawing_analysis_ml_bom_path=manifest_path,
        )


def test_triage_local_settings_rejects_live_drawing_rollout_without_evidence_gate() -> None:
    import pydantic

    from praviar_pipeline.triage_local_settings import TriageLocalSettings

    with pytest.raises(pydantic.ValidationError, match="drawing_analysis_evidence_gate_passed"):
        TriageLocalSettings(drawing_analysis_rollout_state="production")  # type: ignore[call-arg]


def test_triage_local_settings_rejects_live_drawing_rollout_with_unresolved_ml_bom(
    tmp_path,
) -> None:
    import pydantic

    from praviar_pipeline.triage_local_settings import TriageLocalSettings

    with pytest.raises(
        pydantic.ValidationError,
        match="Drawing model supply-chain validation failed",
    ):
        TriageLocalSettings(  # type: ignore[call-arg]
            drawing_analysis_rollout_state="production",
            drawing_analysis_evidence_gate_passed=True,
            drawing_analysis_ml_bom_path=_write_blocked_ml_bom(tmp_path),
        )


def test_triage_local_settings_accepts_live_drawing_rollout_with_clean_ml_bom(
    tmp_path,
) -> None:
    from praviar_pipeline.triage_local_settings import TriageLocalSettings

    settings = TriageLocalSettings(  # type: ignore[call-arg]
        drawing_analysis_rollout_state="production",
        drawing_analysis_evidence_gate_passed=True,
        drawing_analysis_ml_bom_path=_write_approved_ml_bom(tmp_path),
    )

    assert settings.drawing_analysis_rollout_state == "production"
    assert settings.drawing_analysis_evidence_gate_passed is True


def test_settings_class_rejects_unknown_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown backends are rejected at config-validation time. NO
    fallbacks: the user gets a Pydantic ValidationError, not a silent
    default."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import pydantic

    from praviar_pipeline.config import Settings

    with pytest.raises(pydantic.ValidationError):
        Settings(drawing_segmentation_tool="bogus")  # type: ignore[call-arg]


def test_settings_normalizes_drawing_jurisdiction_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    from praviar_pipeline.config import Settings

    settings = Settings(drawing_analysis_jurisdictions=["us", "EP", "us"])  # type: ignore[call-arg]
    assert settings.drawing_analysis_jurisdictions == ["US", "EP"]


def test_settings_rejects_unknown_drawing_jurisdiction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import pydantic

    from praviar_pipeline.config import Settings

    with pytest.raises(pydantic.ValidationError):
        Settings(drawing_analysis_jurisdictions=["BR"])  # type: ignore[call-arg]
