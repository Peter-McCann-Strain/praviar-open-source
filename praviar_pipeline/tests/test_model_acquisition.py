from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

import praviar_pipeline.model_acquisition as model_acquisition
from praviar_pipeline.model_acquisition import (
    ModelAcquisitionError,
    ModelEntry,
    ModelRegistry,
    _strict_registry_json,
    fetch_model,
    load_registry,
    model_path,
    register_local_model,
    verify_model,
)
from praviar_pipeline.ocsr.workers import model_policy, molnextr_worker, superres_worker


def _approved_registry(content: bytes) -> ModelRegistry:
    digest = hashlib.sha256(content).hexdigest()
    entry = ModelEntry.model_validate(
        {
            "model_id": "test/approved-model",
            "component": "Test model",
            "purpose": "exercise the acquisition boundary",
            "source_kind": "upstream_project",
            "upstream_page_url": "https://models.example.test/approved-model",
            "upstream_revision": "0123456789abcdef0123456789abcdef01234567",
            "acquisition_url": "https://models.example.test/approved-model/model.bin",
            "allowed_filenames": ["model.bin"],
            "expected_size_bytes": len(content),
            "sha256": digest,
            "serialization_format": "opaque-test-bytes",
            "license_identifier": "Apache-2.0",
            "license_status": "approved",
            "redistribution_allowed": False,
            "automated_download_allowed": True,
            "permitted_use": "approved",
            "acknowledgement_required": True,
            "runtime_destination": "test/model.bin",
        }
    )
    return ModelRegistry(
        schema_version="praviar.model-registry.v1",
        as_of_date="2030-01-01",
        default_policy="fail_closed",
        entries=(entry,),
    )


def test_shipped_registry_is_link_only_and_uses_authoritative_https_pages() -> None:
    registry = load_registry()

    assert registry.entries
    assert all(entry.upstream_page_url.startswith("https://") for entry in registry.entries)
    assert all(not entry.automated_download_allowed for entry in registry.entries)
    assert all(not entry.redistribution_allowed for entry in registry.entries)
    assert registry.get("moldet/yolo11l_960_doc").license_status == "noncommercial"
    assert registry.get("molnextr/molnextr_best").sha256 is None

    molsight = registry.get("molsight/pubchem_uspto_smiles_edges_30")
    assert molsight.source_kind == "huggingface"
    assert molsight.upstream_revision == "befac2077e41f644c25b97a740c3c779c1ed34cf"
    assert molsight.upstream_page_url == (
        "https://huggingface.co/Robert-zwr/MolSight/blob/"
        "befac2077e41f644c25b97a740c3c779c1ed34cf/"
        "pubchem_uspto_smiles_edges_30.pth"
    )
    assert molsight.license_status == "pending_review"
    assert molsight.permitted_use == "unapproved"
    assert molsight.acquisition_url is None
    assert not molsight.automated_download_allowed
    assert not molsight.redistribution_allowed


def test_registry_parser_rejects_duplicate_keys_and_non_json_numbers() -> None:
    with pytest.raises(ModelAcquisitionError, match="duplicate object key"):
        _strict_registry_json('{"schema_version":"one","schema_version":"two"}')
    with pytest.raises(ModelAcquisitionError, match="non-JSON number"):
        _strict_registry_json('{"expected_size_bytes":NaN}')


def test_isolated_worker_registry_parser_is_equally_strict() -> None:
    with pytest.raises(RuntimeError, match="repeats key"):
        model_policy._strict_json_object('{"license_status":"unknown","license_status":"approved"}')
    with pytest.raises(RuntimeError, match="non-JSON number"):
        model_policy._strict_json_object('{"expected_size_bytes":Infinity}')


def test_registry_rejects_unsafe_destination() -> None:
    registry = load_registry()
    raw = registry.entries[0].model_dump(mode="json")
    raw["runtime_destination"] = "../escape/model.bin"
    raw["allowed_filenames"] = ["model.bin"]

    with pytest.raises(ValueError, match="safe relative path"):
        ModelEntry.model_validate(raw)


@pytest.mark.parametrize(
    "destination",
    [r"..\escape\model.bin", r"C:\models\model.bin", "safe/model.bin\x00"],
)
def test_registry_rejects_cross_platform_unsafe_destination(destination: str) -> None:
    registry = load_registry()
    raw = registry.entries[0].model_dump(mode="json")
    raw["runtime_destination"] = destination
    raw["allowed_filenames"] = ["model.bin"]

    with pytest.raises(ValueError, match="safe relative path"):
        ModelEntry.model_validate(raw)


@pytest.mark.parametrize("filename", [r"..\model.bin", "C:model.bin", "nested/model.bin"])
def test_registry_rejects_non_basename_filename(filename: str) -> None:
    registry = load_registry()
    raw = registry.entries[0].model_dump(mode="json")
    raw["runtime_destination"] = "safe/model.bin"
    raw["allowed_filenames"] = [filename, "model.bin"]

    with pytest.raises(ValueError, match="plain basenames"):
        ModelEntry.model_validate(raw)


def test_registry_rejects_malformed_or_credentialed_url() -> None:
    registry = load_registry()
    raw = registry.entries[0].model_dump(mode="json")

    raw["upstream_page_url"] = "https://"
    with pytest.raises(ValueError, match="absolute HTTPS"):
        ModelEntry.model_validate(raw)

    raw["upstream_page_url"] = "https://publisher.example"
    raw["acquisition_url"] = "https://user:not-a-credential@publisher.example/model.bin"
    with pytest.raises(ValueError, match="embedded credentials"):
        ModelEntry.model_validate(raw)

    raw["acquisition_url"] = "https://publisher.example/model.bin?variant=example"
    with pytest.raises(ValueError, match="queries"):
        ModelEntry.model_validate(raw)


def test_register_local_requires_acknowledgement_and_verifies_bytes(tmp_path: Path) -> None:
    content = b"approved deterministic model bytes"
    registry = _approved_registry(content)
    source = tmp_path / "operator-download.bin"
    source.write_bytes(content)
    root = tmp_path / "models"

    with pytest.raises(ModelAcquisitionError, match="accept-license"):
        register_local_model(
            "test/approved-model",
            source,
            acknowledge_license=False,
            registry=registry,
            root=root,
        )

    receipt = register_local_model(
        "test/approved-model",
        source,
        acknowledge_license=True,
        registry=registry,
        root=root,
    )

    destination = root / "test" / "model.bin"
    assert destination.read_bytes() == content
    assert receipt.sha256 == hashlib.sha256(content).hexdigest()
    saved_receipt = json.loads((root / "test" / "model.bin.receipt.json").read_text())
    assert saved_receipt["model_id"] == "test/approved-model"
    assert saved_receipt["acquisition_kind"] == "register-local"
    assert (
        verify_model("test/approved-model", registry=registry, root=root).sha256 == receipt.sha256
    )


def test_register_local_rejects_tampering_without_activating_file(tmp_path: Path) -> None:
    registry = _approved_registry(b"expected")
    source = tmp_path / "wrong.bin"
    source.write_bytes(b"tampered")
    root = tmp_path / "models"

    with pytest.raises(ModelAcquisitionError, match="SHA-256 mismatch"):
        register_local_model(
            "test/approved-model",
            source,
            acknowledge_license=True,
            registry=registry,
            root=root,
        )

    assert not model_path(registry.entries[0], root=root).exists()
    assert list(root.rglob("*.part")) == []


def test_register_local_rejects_symlink_source(tmp_path: Path) -> None:
    content = b"approved"
    registry = _approved_registry(content)
    real_source = tmp_path / "real.bin"
    real_source.write_bytes(content)
    linked_source = tmp_path / "linked.bin"
    linked_source.symlink_to(real_source)

    with pytest.raises(ModelAcquisitionError, match="must not be a symlink"):
        register_local_model(
            "test/approved-model",
            linked_source,
            acknowledge_license=True,
            registry=registry,
            root=tmp_path / "models",
        )


def test_register_local_refuses_unapproved_use_even_with_known_digest(tmp_path: Path) -> None:
    content = b"known but not approved"
    approved = _approved_registry(content)
    raw = approved.entries[0].model_dump(mode="json")
    raw.update(
        {
            "license_status": "pending_review",
            "permitted_use": "unapproved",
            "automated_download_allowed": False,
            "acquisition_url": None,
        }
    )
    registry = ModelRegistry(
        schema_version="praviar.model-registry.v1",
        as_of_date="2030-01-01",
        default_policy="fail_closed",
        entries=(ModelEntry.model_validate(raw),),
    )
    source = tmp_path / "model.bin"
    source.write_bytes(content)

    with pytest.raises(ModelAcquisitionError, match="local activation is disabled"):
        register_local_model(
            "test/approved-model",
            source,
            acknowledge_license=True,
            registry=registry,
            root=tmp_path / "models",
        )


def test_register_local_rejects_receipt_symlink(tmp_path: Path) -> None:
    content = b"approved"
    registry = _approved_registry(content)
    source = tmp_path / "model.bin"
    source.write_bytes(content)
    root = tmp_path / "models"
    receipt_path = root / "test" / "model.bin.receipt.json"
    receipt_path.parent.mkdir(parents=True)
    victim = tmp_path / "victim.txt"
    victim.write_text("do not replace")
    receipt_path.symlink_to(victim)

    with pytest.raises(ModelAcquisitionError, match="receipt must not be a symlink"):
        register_local_model(
            "test/approved-model",
            source,
            acknowledge_license=True,
            registry=registry,
            root=root,
        )

    assert victim.read_text() == "do not replace"
    assert not (root / "test" / "model.bin").exists()


def test_register_local_rejects_receipt_directory_before_activation(tmp_path: Path) -> None:
    content = b"approved"
    registry = _approved_registry(content)
    source = tmp_path / "model.bin"
    source.write_bytes(content)
    root = tmp_path / "models"
    receipt_path = root / "test" / "model.bin.receipt.json"
    receipt_path.mkdir(parents=True)

    with pytest.raises(ModelAcquisitionError, match="receipt must be a regular file"):
        register_local_model(
            "test/approved-model",
            source,
            acknowledge_license=True,
            registry=registry,
            root=root,
        )

    assert not (root / "test" / "model.bin").exists()


def test_register_local_rejects_shared_writable_model_root(tmp_path: Path) -> None:
    content = b"approved"
    registry = _approved_registry(content)
    source = tmp_path / "model.bin"
    source.write_bytes(content)
    root = tmp_path / "models"
    root.mkdir()
    root.chmod(0o777)

    with pytest.raises(ModelAcquisitionError, match="group- or world-writable"):
        register_local_model(
            "test/approved-model",
            source,
            acknowledge_license=True,
            registry=registry,
            root=root,
        )

    assert not (root / "test" / "model.bin").exists()


def test_receipt_write_failure_removes_activated_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"approved"
    registry = _approved_registry(content)
    source = tmp_path / "model.bin"
    source.write_bytes(content)
    root = tmp_path / "models"

    def fail_receipt(*_args, **_kwargs):
        raise OSError("simulated receipt failure")

    monkeypatch.setattr(model_acquisition, "_write_receipt", fail_receipt)

    with pytest.raises(OSError, match="simulated receipt failure"):
        register_local_model(
            "test/approved-model",
            source,
            acknowledge_license=True,
            registry=registry,
            root=root,
        )

    assert not (root / "test" / "model.bin").exists()


def test_worker_requires_matching_receipt_and_private_model_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"approved"
    registry = _approved_registry(content)
    package_root = tmp_path / "package"
    package_root.mkdir()
    (package_root / "model_registry.json").write_text(registry.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(
        model_policy,
        "__file__",
        str(package_root / "ocsr/workers/model_policy.py"),
    )
    source = tmp_path / "model.bin"
    source.write_bytes(content)
    root = tmp_path / "models"
    monkeypatch.setenv("PRAVIAR_MODEL_HOME", str(root))

    register_local_model(
        "test/approved-model",
        source,
        acknowledge_license=True,
        registry=registry,
        root=root,
    )
    destination = root / "test/model.bin"
    assert model_policy.verified_model_path("test/approved-model") == destination

    destination.with_suffix(".bin.receipt.json").unlink()
    with pytest.raises(RuntimeError, match="receipt does not exist"):
        model_policy.verified_model_path("test/approved-model")

    register_local_model(
        "test/approved-model",
        source,
        acknowledge_license=True,
        registry=registry,
        root=root,
    )
    root.chmod(0o777)
    with pytest.raises(RuntimeError, match="model root must not be group- or world-writable"):
        model_policy.verified_model_path("test/approved-model")


def test_fetch_uses_https_and_activates_only_verified_bytes(tmp_path: Path) -> None:
    content = b"downloaded and verified"
    registry = _approved_registry(content)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://models.example.test/approved-model/model.bin"
        return httpx.Response(200, content=content, headers={"content-length": str(len(content))})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        receipt = fetch_model(
            "test/approved-model",
            acknowledge_license=True,
            registry=registry,
            root=tmp_path / "models",
            client=client,
        )

    assert receipt.acquisition_kind == "download"
    assert (tmp_path / "models" / "test" / "model.bin").read_bytes() == content


def test_fetch_rejects_malformed_content_length_as_policy_error(tmp_path: Path) -> None:
    content = b"downloaded and verified"
    registry = _approved_registry(content)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content, headers={"content-length": "not-an-integer"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ModelAcquisitionError, match="invalid Content-Length"):
            fetch_model(
                "test/approved-model",
                acknowledge_license=True,
                registry=registry,
                root=tmp_path / "models",
                client=client,
            )

    assert not (tmp_path / "models" / "test" / "model.bin").exists()


def test_fetch_rejects_cross_origin_redirect_before_activation(tmp_path: Path) -> None:
    content = b"downloaded and verified"
    registry = _approved_registry(content)
    contacted_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted_hosts.append(request.url.host)
        if request.url.host == "models.example.test":
            return httpx.Response(
                302,
                headers={"location": "https://cdn.example.test/model.bin"},
            )
        return httpx.Response(200, content=content)

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        with pytest.raises(ModelAcquisitionError, match="unapproved origin"):
            fetch_model(
                "test/approved-model",
                acknowledge_license=True,
                registry=registry,
                root=tmp_path / "models",
                client=client,
            )

    assert not (tmp_path / "models" / "test" / "model.bin").exists()
    assert contacted_hosts == ["models.example.test"]


def test_fetch_allows_bounded_same_origin_redirect(tmp_path: Path) -> None:
    content = b"downloaded and verified"
    registry = _approved_registry(content)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/approved-model/model.bin":
            return httpx.Response(302, headers={"location": "/immutable/model.bin"})
        return httpx.Response(200, content=content)

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        receipt = fetch_model(
            "test/approved-model",
            acknowledge_license=True,
            registry=registry,
            root=tmp_path / "models",
            client=client,
        )

    assert receipt.sha256 == hashlib.sha256(content).hexdigest()


def test_fetch_refuses_shipped_link_only_entry_before_network(monkeypatch) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: pytest.fail("network used"))
    )
    try:
        with pytest.raises(ModelAcquisitionError, match="automatic download is disabled"):
            fetch_model(
                "moldet/yolo11l_960_doc",
                acknowledge_license=True,
                client=client,
            )
    finally:
        client.close()


def test_known_workers_contain_no_implicit_weight_downloads() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    superres = (
        repo_root / "praviar_pipeline/src/praviar_pipeline/ocsr/workers/superres_worker.py"
    ).read_text()
    molnextr = (
        repo_root / "praviar_pipeline/src/praviar_pipeline/ocsr/workers/molnextr_worker.py"
    ).read_text()

    assert 'model_path=f"https://' not in superres
    assert "_verified_model_path" in molnextr
    assert "_block_runtime_download" in molnextr
    assert "resolve/main/molnextr_best.pth" not in molnextr


def test_molnextr_worker_fails_before_import_when_checkpoint_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    molnextr_worker._MODEL_CACHE.clear()
    monkeypatch.setenv("PRAVIAR_MODEL_HOME", str(tmp_path / "models"))

    with pytest.raises(RuntimeError, match="activation is disabled by registry policy"):
        molnextr_worker.get_model()


def test_superres_worker_fails_before_optional_imports_for_unapproved_model() -> None:
    result = superres_worker.upscale("unused.png", "unused-output.png", scale=2)

    assert result["output_path"] == ""
    assert result["error"] == "Super-resolution model policy failed (RuntimeError)"


def test_superres_worker_rejects_unsupported_scale_before_model_lookup() -> None:
    result = superres_worker.upscale("unused.png", "unused-output.png", scale=8)

    assert result == {
        "output_path": "",
        "scale": 8,
        "error": "super-resolution scale must be 2 or 4",
    }
