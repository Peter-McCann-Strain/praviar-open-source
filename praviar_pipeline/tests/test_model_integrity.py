from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from praviar_pipeline.ocsr.workers.model_integrity import (
    ModelChecksumError,
    expected_model_sha256,
    model_directory_tree_sha256,
    verified_model_directory_from_ml_bom,
    verify_model_checksum,
    verify_model_checksum_from_ml_bom,
    verify_model_directory_from_ml_bom,
)


def write_approved_license_evidence(
    tmp_path,
    *,
    model_id="test/model",
    model_sha256: str,
    approved_model_id: str | None = None,
    approved_model_sha256: str | None = None,
    approval_artifact_sha256: str | None = None,
) -> str:
    approval_artifact = (
        tmp_path / "docs/trust/evidence/supply-chain/licenses/test-model-approval.json"
    )
    approval_artifact.parent.mkdir(parents=True, exist_ok=True)
    approval_artifact.write_bytes(b"security lead model evidence approval")
    approval_sha = (
        approval_artifact_sha256 or hashlib.sha256(approval_artifact.read_bytes()).hexdigest()
    )
    evidence_path = tmp_path / "docs/trust/evidence/supply-chain/licenses/test-model-license.md"
    evidence_path.write_text(
        "\n".join(
            [
                f"model_id: {model_id}",
                "license_status: approved_for_commercial_use",
                "primary_source_url: https://vendor.example.test/license",
                "source_kind: vendor_contract",
                "retrieved_at: 2026-05-25T12:00:00Z",
                f"retrieved_sha256: {hashlib.sha256(b'license').hexdigest()}",
                "approved_use: commercial FTO analysis in Praviar",
                "review_authority: security_lead",
                "approval_artifact_path: "
                "docs/trust/evidence/supply-chain/licenses/test-model-approval.json",
                f"approval_artifact_sha256: {approval_sha}",
                f"approved_model_id: {approved_model_id or model_id}",
                f"approved_model_sha256: {approved_model_sha256 or model_sha256}",
            ]
        ),
        encoding="utf-8",
    )
    return "docs/trust/evidence/supply-chain/licenses/test-model-license.md"


def test_verify_model_checksum_accepts_matching_digest(tmp_path):
    model_path = tmp_path / "model.pt"
    model_path.write_bytes(b"trusted model bytes")
    expected = hashlib.sha256(model_path.read_bytes()).hexdigest()

    actual = verify_model_checksum(
        model_path,
        expected_sha256=f"sha256:{expected}",
        model_id="test/model",
    )

    assert actual == expected


def test_verify_model_checksum_rejects_mismatch(tmp_path):
    model_path = tmp_path / "model.pt"
    model_path.write_bytes(b"tampered model bytes")

    with pytest.raises(ModelChecksumError, match="checksum mismatch"):
        verify_model_checksum(
            model_path,
            expected_sha256="0" * 64,
            model_id="test/model",
        )


def test_verify_model_checksum_rejects_invalid_expected_digest(tmp_path):
    model_path = tmp_path / "model.pt"
    model_path.write_bytes(b"model bytes")

    with pytest.raises(ModelChecksumError, match="64-character hex digest"):
        verify_model_checksum(
            model_path,
            expected_sha256="not-a-sha",
            model_id="test/model",
        )


def test_verify_model_checksum_from_ml_bom_uses_registered_digest(tmp_path):
    model_path = tmp_path / "model.pt"
    model_path.write_bytes(b"ml-bom model bytes")
    expected = hashlib.sha256(model_path.read_bytes()).hexdigest()
    manifest_path = tmp_path / "ml-bom.json"
    license_evidence_path = write_approved_license_evidence(
        tmp_path,
        model_sha256=expected,
    )
    manifest_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "model_id": "test/model",
                        "sha256": expected,
                        "license_status": "approved_for_commercial_use",
                        "license_evidence_path": license_evidence_path,
                        "release_blocker": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    actual = verify_model_checksum_from_ml_bom(
        model_path,
        model_id="test/model",
        manifest_path=manifest_path,
    )

    assert actual == expected
    assert expected_model_sha256("test/model", manifest_path=manifest_path) == expected


def test_verify_model_checksum_from_ml_bom_rejects_unregistered_model(tmp_path):
    model_path = tmp_path / "model.pt"
    model_path.write_bytes(b"ml-bom model bytes")
    manifest_path = tmp_path / "ml-bom.json"
    manifest_path.write_text(json.dumps({"entries": []}), encoding="utf-8")

    with pytest.raises(ModelChecksumError, match="not registered"):
        verify_model_checksum_from_ml_bom(
            model_path,
            model_id="test/model",
            manifest_path=manifest_path,
        )


def test_verify_model_checksum_from_ml_bom_rejects_unapproved_license_state(tmp_path):
    model_path = tmp_path / "model.pt"
    model_path.write_bytes(b"licensed bytes")
    manifest_path = tmp_path / "ml-bom.json"
    manifest_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "model_id": "test/model",
                        "sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
                        "license_status": "missing_license_evidence",
                        "release_blocker": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ModelChecksumError, match="license_status"):
        verify_model_checksum_from_ml_bom(
            model_path,
            model_id="test/model",
            manifest_path=manifest_path,
        )


def test_verify_model_checksum_from_ml_bom_rejects_missing_license_evidence_path(
    tmp_path,
):
    model_path = tmp_path / "model.pt"
    model_path.write_bytes(b"licensed bytes")
    manifest_path = tmp_path / "ml-bom.json"
    manifest_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "model_id": "test/model",
                        "sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
                        "license_status": "approved_for_commercial_use",
                        "release_blocker": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ModelChecksumError, match="missing license_evidence_path"):
        verify_model_checksum_from_ml_bom(
            model_path,
            model_id="test/model",
            manifest_path=manifest_path,
        )


def test_verify_model_checksum_from_ml_bom_rejects_placeholder_license_evidence(
    tmp_path,
):
    model_path = tmp_path / "model.pt"
    model_path.write_bytes(b"licensed bytes")
    manifest_path = tmp_path / "ml-bom.json"
    evidence_path = tmp_path / "docs/trust/evidence/supply-chain/licenses/test-model-license.md"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        "\n".join(
            [
                "model_id: test/model",
                "license_status: approved_for_commercial_use",
                "primary_source_url: todo",
                "source_kind: placeholder",
                "retrieved_at: pending",
                "retrieved_sha256: local-only",
                "approved_use: not release evidence",
                "review_authority: security_lead",
            ]
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "model_id": "test/model",
                        "sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
                        "license_status": "approved_for_commercial_use",
                        "license_evidence_path": (
                            "docs/trust/evidence/supply-chain/licenses/test-model-license.md"
                        ),
                        "release_blocker": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ModelChecksumError,
        match="approved license evidence must not contain",
    ):
        verify_model_checksum_from_ml_bom(
            model_path,
            model_id="test/model",
            manifest_path=manifest_path,
        )


def test_verify_model_checksum_from_ml_bom_rejects_unbound_approved_license_evidence(
    tmp_path,
):
    model_path = tmp_path / "model.pt"
    model_path.write_bytes(b"licensed bytes")
    manifest_path = tmp_path / "ml-bom.json"
    evidence_path = tmp_path / "docs/trust/evidence/supply-chain/licenses/test-model-license.md"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        "\n".join(
            [
                "model_id: test/model",
                "license_status: approved_for_commercial_use",
                "primary_source_url: https://vendor.example.test/license",
                "source_kind: vendor_contract",
                "retrieved_at: 2026-05-25T12:00:00Z",
                f"retrieved_sha256: {hashlib.sha256(b'license').hexdigest()}",
                "approved_use: commercial FTO analysis in Praviar",
                "review_authority: security_lead",
            ]
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "model_id": "test/model",
                        "sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
                        "license_status": "approved_for_commercial_use",
                        "license_evidence_path": (
                            "docs/trust/evidence/supply-chain/licenses/test-model-license.md"
                        ),
                        "release_blocker": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ModelChecksumError, match="missing structured fields"):
        verify_model_checksum_from_ml_bom(
            model_path,
            model_id="test/model",
            manifest_path=manifest_path,
        )


def test_verify_model_checksum_from_ml_bom_rejects_approval_artifact_hash_mismatch(
    tmp_path,
):
    model_path = tmp_path / "model.pt"
    model_path.write_bytes(b"licensed bytes")
    expected = hashlib.sha256(model_path.read_bytes()).hexdigest()
    manifest_path = tmp_path / "ml-bom.json"
    license_evidence_path = write_approved_license_evidence(
        tmp_path,
        model_sha256=expected,
        approval_artifact_sha256="0" * 64,
    )
    manifest_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "model_id": "test/model",
                        "sha256": expected,
                        "license_status": "approved_for_commercial_use",
                        "license_evidence_path": license_evidence_path,
                        "release_blocker": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ModelChecksumError, match="approval_artifact_sha256 must match"):
        verify_model_checksum_from_ml_bom(
            model_path,
            model_id="test/model",
            manifest_path=manifest_path,
        )


def test_verify_model_checksum_from_ml_bom_rejects_license_approval_for_wrong_model_or_digest(
    tmp_path,
):
    model_path = tmp_path / "model.pt"
    model_path.write_bytes(b"licensed bytes")
    expected = hashlib.sha256(model_path.read_bytes()).hexdigest()
    manifest_path = tmp_path / "ml-bom.json"
    license_evidence_path = write_approved_license_evidence(
        tmp_path,
        model_sha256=expected,
        approved_model_id="test/other-model",
        approved_model_sha256="1" * 64,
    )
    manifest_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "model_id": "test/model",
                        "sha256": expected,
                        "license_status": "approved_for_commercial_use",
                        "license_evidence_path": license_evidence_path,
                        "release_blocker": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ModelChecksumError, match="approved_model_id must match model_id"):
        verify_model_checksum_from_ml_bom(
            model_path,
            model_id="test/model",
            manifest_path=manifest_path,
        )


def test_verify_model_checksum_from_ml_bom_rejects_release_blocker(tmp_path):
    model_path = tmp_path / "model.pt"
    model_path.write_bytes(b"blocked bytes")
    manifest_path = tmp_path / "ml-bom.json"
    manifest_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "model_id": "test/model",
                        "sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
                        "license_status": "approved_for_commercial_use",
                        "release_blocker": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ModelChecksumError, match="release blocker"):
        verify_model_checksum_from_ml_bom(
            model_path,
            model_id="test/model",
            manifest_path=manifest_path,
        )


def test_verify_model_checksum_from_ml_bom_rejects_tampered_file(tmp_path):
    model_path = tmp_path / "model.pt"
    model_path.write_bytes(b"tampered")
    manifest_path = tmp_path / "ml-bom.json"
    license_evidence_path = write_approved_license_evidence(
        tmp_path,
        model_sha256=hashlib.sha256(b"trusted").hexdigest(),
    )
    manifest_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "model_id": "test/model",
                        "sha256": hashlib.sha256(b"trusted").hexdigest(),
                        "license_status": "approved_for_commercial_use",
                        "license_evidence_path": license_evidence_path,
                        "release_blocker": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ModelChecksumError, match="checksum mismatch"):
        verify_model_checksum_from_ml_bom(
            model_path,
            model_id="test/model",
            manifest_path=manifest_path,
        )


def _write_transformer_snapshot(tmp_path):
    snapshot = tmp_path / "checkpoint"
    snapshot.mkdir()
    files = {
        "config.json": b'{"model_type":"vision-encoder-decoder"}',
        "preprocessor_config.json": b'{"size":224}',
        "tokenizer_config.json": b'{"model_max_length":512}',
        "tokenizer.json": b'{"version":"1.0"}',
        "model-00001-of-00002.safetensors": b"trusted shard one",
        "model-00002-of-00002.safetensors": b"trusted shard two",
        "model.safetensors.index.json": json.dumps(
            {
                "weight_map": {
                    "encoder.weight": "model-00001-of-00002.safetensors",
                    "decoder.weight": "model-00002-of-00002.safetensors",
                }
            },
            sort_keys=True,
        ).encode(),
    }
    for name, contents in files.items():
        (snapshot / name).write_bytes(contents)
    return snapshot, sorted(files)


def _write_directory_manifest(tmp_path, snapshot, required_files, *, model_id="test/model"):
    digest, size_bytes, _files = model_directory_tree_sha256(
        snapshot,
        model_id=model_id,
    )
    evidence_path = write_approved_license_evidence(
        tmp_path,
        model_id=model_id,
        model_sha256=digest,
    )
    manifest_path = tmp_path / "ml-bom-directory.json"
    manifest_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "model_id": model_id,
                        "artifact_kind": "directory_tree_v1",
                        "path": "checkpoint",
                        "required_files": required_files,
                        "size_bytes": size_bytes,
                        "sha256": digest,
                        "license_status": "approved_for_commercial_use",
                        "license_evidence_path": evidence_path,
                        "release_blocker": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return manifest_path, digest


def test_verify_model_directory_accepts_complete_integrity_bound_snapshot(tmp_path):
    snapshot, required_files = _write_transformer_snapshot(tmp_path)
    manifest_path, expected = _write_directory_manifest(
        tmp_path,
        snapshot,
        required_files,
    )

    actual = verify_model_directory_from_ml_bom(
        snapshot,
        model_id="test/model",
        manifest_path=manifest_path,
    )

    assert actual == expected


def test_verified_model_directory_accepts_unchanged_load_boundary(tmp_path):
    snapshot, required_files = _write_transformer_snapshot(tmp_path)
    manifest_path, _expected = _write_directory_manifest(
        tmp_path,
        snapshot,
        required_files,
    )

    with verified_model_directory_from_ml_bom(
        snapshot,
        model_id="test/model",
        manifest_path=manifest_path,
    ) as verified_root:
        assert verified_root == snapshot.resolve()


def test_verify_model_directory_rejects_missing_indexed_shard(tmp_path):
    snapshot, required_files = _write_transformer_snapshot(tmp_path)
    manifest_path, _expected = _write_directory_manifest(
        tmp_path,
        snapshot,
        required_files,
    )
    (snapshot / "model-00002-of-00002.safetensors").unlink()

    with pytest.raises(ModelChecksumError, match="missing required files"):
        verify_model_directory_from_ml_bom(
            snapshot,
            model_id="test/model",
            manifest_path=manifest_path,
        )


def test_verify_model_directory_rejects_extra_critical_file(tmp_path):
    snapshot, required_files = _write_transformer_snapshot(tmp_path)
    manifest_path, _expected = _write_directory_manifest(
        tmp_path,
        snapshot,
        required_files,
    )
    (snapshot / "unapproved_config.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ModelChecksumError, match="unlisted critical files"):
        verify_model_directory_from_ml_bom(
            snapshot,
            model_id="test/model",
            manifest_path=manifest_path,
        )


def test_verify_model_directory_rejects_pickle_capable_weights(tmp_path):
    snapshot, required_files = _write_transformer_snapshot(tmp_path)
    unsafe_weight = "pytorch_model.bin"
    (snapshot / unsafe_weight).write_bytes(b"pickle-capable payload")
    required_files.append(unsafe_weight)
    manifest_path, _expected = _write_directory_manifest(
        tmp_path,
        snapshot,
        required_files,
    )

    with pytest.raises(ModelChecksumError, match="unsafe serialized weights"):
        verify_model_directory_from_ml_bom(
            snapshot,
            model_id="test/model",
            manifest_path=manifest_path,
        )


def test_verify_model_directory_rejects_symlink(tmp_path):
    snapshot, required_files = _write_transformer_snapshot(tmp_path)
    manifest_path, _expected = _write_directory_manifest(
        tmp_path,
        snapshot,
        required_files,
    )
    (snapshot / "linked.bin").symlink_to(snapshot / "model-00001-of-00002.safetensors")

    with pytest.raises(ModelChecksumError, match="contains a symlink"):
        verify_model_directory_from_ml_bom(
            snapshot,
            model_id="test/model",
            manifest_path=manifest_path,
        )


def test_verify_model_directory_rejects_symlink_snapshot_root(tmp_path):
    snapshot, required_files = _write_transformer_snapshot(tmp_path)
    manifest_path, _expected = _write_directory_manifest(
        tmp_path,
        snapshot,
        required_files,
    )
    linked_root = tmp_path / "linked-checkpoint"
    linked_root.symlink_to(snapshot, target_is_directory=True)

    with pytest.raises(ModelChecksumError, match="root must not be a symlink"):
        verify_model_directory_from_ml_bom(
            linked_root,
            model_id="test/model",
            manifest_path=manifest_path,
        )


def test_verified_model_directory_detects_restore_after_load_boundary_mutation(tmp_path):
    snapshot, required_files = _write_transformer_snapshot(tmp_path)
    manifest_path, _expected = _write_directory_manifest(
        tmp_path,
        snapshot,
        required_files,
    )
    config = snapshot / "config.json"
    approved_contents = config.read_bytes()

    with pytest.raises(ModelChecksumError, match="changed across the model load boundary"):
        with verified_model_directory_from_ml_bom(
            snapshot,
            model_id="test/model",
            manifest_path=manifest_path,
        ):
            config.write_bytes(b'{"model_type":"attacker-controlled"}')
            config.write_bytes(approved_contents)


def test_verified_model_directory_detects_root_replacement_during_load(tmp_path):
    snapshot, required_files = _write_transformer_snapshot(tmp_path)
    manifest_path, _expected = _write_directory_manifest(
        tmp_path,
        snapshot,
        required_files,
    )
    original_snapshot = tmp_path / "original-checkpoint"

    with pytest.raises(ModelChecksumError, match="changed across the model load boundary"):
        with verified_model_directory_from_ml_bom(
            snapshot,
            model_id="test/model",
            manifest_path=manifest_path,
        ) as verified_root:
            assert verified_root == snapshot.resolve()
            snapshot.rename(original_snapshot)
            shutil.copytree(original_snapshot, snapshot)


def test_verify_model_directory_rejects_file_style_ml_bom_entry(tmp_path):
    snapshot, required_files = _write_transformer_snapshot(tmp_path)
    manifest_path, _expected = _write_directory_manifest(
        tmp_path,
        snapshot,
        required_files,
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["entries"][0].pop("artifact_kind")
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ModelChecksumError, match="artifact_kind"):
        verify_model_directory_from_ml_bom(
            snapshot,
            model_id="test/model",
            manifest_path=manifest_path,
        )
