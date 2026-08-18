"""Supply-chain tests for the isolated DECIMER segmentation worker."""

from __future__ import annotations

import hashlib

import pytest

from praviar_pipeline.ocsr.workers.decimer_seg_worker import _verify_model_artifact


def test_model_artifact_accepts_the_expected_digest(tmp_path) -> None:
    model = tmp_path / "mask_rcnn_molecule.h5"
    model.write_bytes(b"verified-model")

    _verify_model_artifact(
        model,
        expected_sha256=hashlib.sha256(b"verified-model").hexdigest(),
    )


def test_model_artifact_rejects_missing_weights(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="not pre-baked"):
        _verify_model_artifact(
            tmp_path / "missing.h5",
            expected_sha256="0" * 64,
        )


def test_model_artifact_rejects_substituted_weights(tmp_path) -> None:
    model = tmp_path / "mask_rcnn_molecule.h5"
    model.write_bytes(b"substituted")

    with pytest.raises(RuntimeError, match="checksum mismatch"):
        _verify_model_artifact(model, expected_sha256="0" * 64)
