from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from praviar_pipeline import vision_production
from praviar_pipeline.pipeline.runtime import run_execution
from praviar_pipeline.vision_production import (
    DEFAULT_ROSTER_PATH,
    VisionPreflightError,
    load_roster,
    run_production_preflight,
)


def _minimal_roster() -> dict:
    roles = (
        "segmentation",
        "classification",
        "primary_ocsr",
        "markush_ocsr",
    )
    component_ids = (
        "segmentation.decimer",
        "classification.test",
        "ocsr.primary",
        "ocsr.markush",
    )
    components = []
    for index, (role, component_id) in enumerate(zip(roles, component_ids, strict=True)):
        components.append(
            {
                "component_id": component_id,
                "role": role,
                "venv_path": f"venvs/component-{index}",
                "worker_path": f"workers/component-{index}.py",
                "required_imports": ["json"],
                "models": [
                    {
                        "model_id": f"model/component-{index}",
                        "artifact_kind": "file",
                        "runtime_path": f"models/component-{index}.bin",
                    }
                ],
            }
        )
    return {
        "schema_version": 2,
        "roster_id": "test-vision-roster",
        "architecture": "subprocess_venv_workers",
        "worker_protocol_version": 1,
        "runtime_downloads_allowed": False,
        "jurisdictions": ["US", "EP", "WO", "JP", "CN", "KR"],
        "runtime_contract": {
            "segmentation_tool": "decimer",
            "classifier_required": True,
            "primary_ocsr_tools": ["primary"],
            "markush_ocsr_tools": ["markush"],
            "sar_table_tools": [],
            "prohibited_production_tools": ["unsafe"],
        },
        "components": components,
    }


def test_packaged_production_roster_is_strict_and_complete() -> None:
    roster, digest = load_roster()

    assert DEFAULT_ROSTER_PATH.is_file()
    assert roster.runtime_downloads_allowed is False
    assert set(roster.jurisdictions) == {"US", "EP", "WO", "JP", "CN", "KR"}
    assert {component.role for component in roster.components} == {
        "segmentation",
        "classification",
        "primary_ocsr",
        "markush_ocsr",
    }
    assert len(digest) == 64


def test_production_preflight_verifies_every_declared_runtime_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    roster_path = tmp_path / "roster.json"
    roster_path.write_text(json.dumps(_minimal_roster()), encoding="utf-8")
    manifest_path = tmp_path / "ml-bom.json"
    manifest_path.write_text('{"entries":[]}', encoding="utf-8")

    for index in range(4):
        worker = root / f"workers/component-{index}.py"
        worker.parent.mkdir(exist_ok=True)
        worker.write_text("pass\n", encoding="utf-8")
        python_path = root / f"venvs/component-{index}/bin/python"
        python_path.parent.mkdir(parents=True)
        python_path.symlink_to(sys.executable)
        model = root / f"models/component-{index}.bin"
        model.parent.mkdir(exist_ok=True)
        model.write_bytes(f"model-{index}".encode())

    verified: list[str] = []

    def fake_verify(_path, *, model_id, manifest_path):
        assert Path(manifest_path) == manifest_path_fixture
        verified.append(model_id)
        return "a" * 64

    manifest_path_fixture = manifest_path
    monkeypatch.setattr(vision_production, "verify_model_checksum_from_ml_bom", fake_verify)
    monkeypatch.chdir(tmp_path)

    roster_sha = hashlib.sha256(roster_path.read_bytes()).hexdigest()
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    report = run_production_preflight(
        roster_path=roster_path,
        runtime_root=root,
        ml_bom_path=Path("ml-bom.json"),
        expected_roster_sha256=roster_sha,
        expected_ml_bom_sha256=manifest_sha,
        production=True,
        probe_imports=False,
    )

    assert report.passed is True
    assert verified == [f"model/component-{index}" for index in range(4)]
    assert all(check.passed for check in report.checks)


def test_production_preflight_requires_independent_control_digests(tmp_path: Path) -> None:
    roster_path = tmp_path / "roster.json"
    roster_path.write_text(json.dumps(_minimal_roster()), encoding="utf-8")
    manifest_path = tmp_path / "ml-bom.json"
    manifest_path.write_text('{"entries":[]}', encoding="utf-8")
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()

    report = run_production_preflight(
        roster_path=roster_path,
        runtime_root=runtime_root,
        ml_bom_path=manifest_path,
        expected_roster_sha256=None,
        expected_ml_bom_sha256=None,
        production=True,
        probe_imports=False,
    )

    failures = {check.check: check.detail for check in report.checks if not check.passed}
    assert "control.roster_identity" in failures
    assert "control.ml_bom_identity" in failures
    assert report.passed is False


def test_production_preflight_rejects_ml_bom_symlink(
    tmp_path: Path,
) -> None:
    roster_path = tmp_path / "roster.json"
    roster_path.write_text(json.dumps(_minimal_roster()), encoding="utf-8")
    real_manifest_path = tmp_path / "real-ml-bom.json"
    real_manifest_path.write_text('{"entries":[]}', encoding="utf-8")
    manifest_path = tmp_path / "ml-bom.json"
    manifest_path.symlink_to(real_manifest_path)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()

    report = run_production_preflight(
        roster_path=roster_path,
        runtime_root=runtime_root,
        ml_bom_path=manifest_path,
        expected_roster_sha256=hashlib.sha256(roster_path.read_bytes()).hexdigest(),
        expected_ml_bom_sha256=hashlib.sha256(real_manifest_path.read_bytes()).hexdigest(),
        production=True,
        probe_imports=False,
    )

    failures = {check.check: check.detail for check in report.checks if not check.passed}
    assert "control.ml_bom_identity" in failures
    assert "control.ml_bom_stability" in failures
    assert report.passed is False


def test_production_preflight_detects_ml_bom_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    roster_path = tmp_path / "roster.json"
    roster_path.write_text(json.dumps(_minimal_roster()), encoding="utf-8")
    manifest_path = tmp_path / "ml-bom.json"
    manifest_path.write_text('{"entries":[]}', encoding="utf-8")

    for index in range(4):
        worker = root / f"workers/component-{index}.py"
        worker.parent.mkdir(exist_ok=True)
        worker.write_text("pass\n", encoding="utf-8")
        python_path = root / f"venvs/component-{index}/bin/python"
        python_path.parent.mkdir(parents=True)
        python_path.symlink_to(sys.executable)
        model = root / f"models/component-{index}.bin"
        model.parent.mkdir(exist_ok=True)
        model.write_bytes(f"model-{index}".encode())

    mutation_done = False

    def mutate_manifest(_path, *, model_id, manifest_path):
        nonlocal mutation_done
        if not mutation_done:
            Path(manifest_path).write_text(
                '{"entries":[],"tampered":true}',
                encoding="utf-8",
            )
            mutation_done = True
        return "a" * 64

    monkeypatch.setattr(
        vision_production,
        "verify_model_checksum_from_ml_bom",
        mutate_manifest,
    )
    report = run_production_preflight(
        roster_path=roster_path,
        runtime_root=root,
        ml_bom_path=manifest_path,
        expected_roster_sha256=hashlib.sha256(roster_path.read_bytes()).hexdigest(),
        expected_ml_bom_sha256=hashlib.sha256(b'{"entries":[]}').hexdigest(),
        production=True,
        probe_imports=False,
    )

    failures = {check.check: check.detail for check in report.checks if not check.passed}
    assert failures["control.ml_bom_stability"] == ("ML-BOM changed during production preflight")
    assert report.passed is False


def test_load_roster_rejects_unknown_contract_keys(tmp_path: Path) -> None:
    roster = _minimal_roster()
    roster["unexpected"] = True
    path = tmp_path / "roster.json"
    path.write_text(json.dumps(roster), encoding="utf-8")

    with pytest.raises(ValueError):
        load_roster(path)


def test_load_roster_rejects_runtime_tools_without_matching_components(
    tmp_path: Path,
) -> None:
    roster = _minimal_roster()
    roster["runtime_contract"]["primary_ocsr_tools"] = ["unbound-tool"]
    path = tmp_path / "roster.json"
    path.write_text(json.dumps(roster), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="primary_ocsr components must exactly match",
    ):
        load_roster(path)


def test_load_roster_rejects_active_tool_on_prohibited_list(tmp_path: Path) -> None:
    roster = _minimal_roster()
    roster["runtime_contract"]["prohibited_production_tools"] = [
        "unsafe",
        "primary",
    ]
    path = tmp_path / "roster.json"
    path.write_text(json.dumps(roster), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="active and prohibited vision runtime tools must be disjoint",
    ):
        load_roster(path)


@pytest.mark.asyncio
async def test_live_drawing_failure_propagates_after_evidence_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("vision worker unavailable")

    async def fail_drawing_enrichment(**_kwargs):
        raise failure

    monkeypatch.setattr(
        run_execution,
        "run_post_triage_drawing_enrichment",
        fail_drawing_enrichment,
    )
    monkeypatch.setattr(
        run_execution,
        "map_relevant_patents",
        lambda patent_hits, _triage_results: patent_hits,
    )

    state = SimpleNamespace(
        completed_step=6,
        patent_hits=[SimpleNamespace(patent_id="US1")],
        triage_results=[],
        all_triage=[],
        settings=SimpleNamespace(
            drawing_analysis_enabled=True,
            drawing_analysis_evidence_gate_passed=True,
            drawing_analysis_rollout_state="production",
        ),
        compound=SimpleNamespace(name="compound"),
        drawing_evidence=None,
        timing_data=[],
        analysis_escalation_reasons=[],
        source_health=None,
    )
    callbacks = SimpleNamespace(
        raise_if_cancelled=lambda *_args: None,
        notify=lambda *_args: None,
        save_checkpoint=lambda *_args: None,
        make_timing=lambda *_args: SimpleNamespace(),
    )

    with pytest.raises(RuntimeError, match="vision worker unavailable"):
        await run_execution.execute_analysis_to_verification_flow(
            state=state,
            callbacks=callbacks,
        )


def test_sha256_parser_rejects_mutable_or_placeholder_values() -> None:
    with pytest.raises(VisionPreflightError):
        vision_production._normalize_expected_sha256("latest", label="test digest")
