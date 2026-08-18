"""Tests for ``praviar_pipeline.ocsr.workers.molparser_worker``.

The worker normally runs inside the ``venvs/molparser/`` subprocess
with torch + transformers + the MolParser-Base weights available.
These tests execute inside the main praviar_pipeline venv — torch is not
importable from here, transformers is not installed, and the
weights do not exist. So we:

1. Import the worker module directly.
2. Mock ``PIL.Image.open``, ``get_model``, and the model's
   ``.generate(...)`` to return a deterministic fake E-SMILES
   string. The adapter (``esmiles_adapter``) runs for real so the
   parse → RDKit / CXSMILES round-trip is exercised end-to-end.
3. For the persistent-mode test, replicate the ``_FakeProcess``
   pattern from ``test_runner_persistent.py`` and drive the
   ``OCSRRunner`` against a fake subprocess that emits JSON lines
   matching the worker's output shape.

No real subprocess is ever spawned.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from praviar_pipeline.models.drawing import OCSRResult
from praviar_pipeline.ocsr.runner import OCSRRunner
from praviar_pipeline.ocsr.workers import molparser_worker

# ---------------------------------------------------------------------------
# In-process mocks for the worker's torch / transformers stack
# ---------------------------------------------------------------------------


class _FakeImage:
    def __init__(self) -> None:
        self.size = (256, 256)

    def convert(self, mode: str) -> _FakeImage:
        return self


class _FakeImageModule:
    @staticmethod
    def open(path: str) -> _FakeImage:
        return _FakeImage()


class _FakeTensor:
    """Stand-in for a torch tensor that supports ``.to(device)``."""

    def to(self, device: Any) -> _FakeTensor:
        return self


class _FakeProcessor:
    def __call__(self, images: Any = None, return_tensors: str = "pt") -> dict:
        return {"pixel_values": _FakeTensor()}


class _FakeTokenizer:
    def __init__(self, decoded: list[str]) -> None:
        self._decoded = decoded

    def batch_decode(self, _ids: Any, skip_special_tokens: bool = True) -> list[str]:
        return list(self._decoded)


class _FakeDevice:
    def __init__(self, t: str = "cpu") -> None:
        self.type = t


class _FakeModel:
    """Mock MolParser model — returns a fake generated-ids tensor.

    The decoded output is controlled by the tokenizer, so ``generate``
    only needs to return *something*.
    """

    def generate(self, **kwargs: Any) -> _FakeTensor:
        return _FakeTensor()


class _FakeTorchModule(types.ModuleType):
    """Enough of a torch stand-in for the worker's ``with torch.no_grad():``
    context manager."""

    class backends:  # noqa: N801 - mimic torch.backends namespace
        class mps:  # noqa: N801
            @staticmethod
            def is_available() -> bool:
                return False

    class cuda:  # noqa: N801
        @staticmethod
        def is_available() -> bool:
            return False

    @staticmethod
    def no_grad() -> _NoGradCtx:
        return _NoGradCtx()


class _NoGradCtx:
    def __enter__(self) -> _NoGradCtx:
        return self

    def __exit__(self, *args: Any) -> None:
        return None


@pytest.fixture()
def patched_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire the worker against fake PIL / torch / model stack."""
    # Reset model cache between tests so each test picks up its own
    # monkeypatched get_model().
    molparser_worker._MODEL_CACHE.clear()

    # Provide fake PIL.Image — ``from PIL import Image`` inside predict
    # finds ``sys.modules["PIL.Image"]`` first.
    fake_pil = types.ModuleType("PIL")
    fake_pil.Image = _FakeImageModule  # type: ignore[attr-defined]
    fake_pil_image = types.ModuleType("PIL.Image")
    fake_pil_image.open = _FakeImageModule.open  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", fake_pil_image)

    # Provide a fake torch so ``import torch`` inside predict succeeds.
    fake_torch = _FakeTorchModule("torch")
    monkeypatch.setitem(sys.modules, "torch", fake_torch)


def _install_fake_model(
    monkeypatch: pytest.MonkeyPatch,
    decoded_esmiles: str,
) -> None:
    """Patch get_model() to return the fake stack with a fixed decode."""

    def fake_get_model() -> tuple:
        return (
            _FakeModel(),
            _FakeProcessor(),
            _FakeTokenizer([decoded_esmiles]),
            _FakeDevice("cpu"),
        )

    monkeypatch.setattr(molparser_worker, "get_model", fake_get_model)


# ---------------------------------------------------------------------------
# Output shape tests (one-shot in-process)
# ---------------------------------------------------------------------------


def test_predict_plain_smiles_shape(patched_worker: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_model(monkeypatch, "CCO")
    out = molparser_worker.predict("/tmp/anything.png")

    assert out["tool"] == "molparser"
    assert out["smiles"] == "CCO"
    assert out["valid"] is True
    assert out["is_markush"] is False
    assert out["cxsmiles"] == ""
    assert out["error"] == ""
    assert out["confidence"] > 0.0  # default 0.85 on valid
    assert "latency_ms" in out


def test_predict_markush_populates_cxsmiles(
    patched_worker: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # MolParser emits Markush E-SMILES → worker must:
    #   - set is_markush=True
    #   - set cxsmiles to the adapter's CXSMILES output
    #   - set smiles="" and valid=False (RDKit can't canonicalise)
    _install_fake_model(monkeypatch, "c1ccc(<r>R1</r>)cc1")
    out = molparser_worker.predict("/tmp/anything.png")

    assert out["tool"] == "molparser"
    assert out["is_markush"] is True
    assert out["smiles"] == ""
    assert out["valid"] is False
    assert out["cxsmiles"] != ""
    assert "R1" in out["cxsmiles"]
    assert out["error"] == ""


def test_predict_invalid_esmiles_no_crash(
    patched_worker: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Decoder emits garbage; worker must return valid=False, no crash.
    _install_fake_model(monkeypatch, "not-a-smiles[[[")
    out = molparser_worker.predict("/tmp/anything.png")

    assert out["tool"] == "molparser"
    assert out["valid"] is False
    assert out["smiles"] == ""
    assert out["is_markush"] is False
    assert out["error"].startswith("Conversion failed (")


def test_predict_empty_decoder_output(
    patched_worker: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_model(monkeypatch, "")
    out = molparser_worker.predict("/tmp/anything.png")

    assert out["tool"] == "molparser"
    assert out["valid"] is False
    assert out["smiles"] == ""
    assert out["confidence"] == 0.0


def test_predict_image_load_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    # Point the worker at a PIL that raises on open().
    molparser_worker._MODEL_CACHE.clear()

    class _RaisingImageModule:
        @staticmethod
        def open(path: str) -> None:
            raise OSError(f"cannot open {path}")

    fake_pil = types.ModuleType("PIL")
    fake_pil.Image = _RaisingImageModule  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)

    out = molparser_worker.predict("/tmp/does-not-exist.png")
    assert out["valid"] is False
    assert out["smiles"] == ""
    assert "Image load failed" in out["error"]
    assert out["tool"] == "molparser"


def test_predict_model_load_failure(patched_worker: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_on_load() -> tuple:
        raise ImportError("molparser venv not set up — install torch, ...")

    monkeypatch.setattr(molparser_worker, "get_model", raise_on_load)

    out = molparser_worker.predict("/tmp/anything.png")
    assert out["valid"] is False
    assert "Model load failed" in out["error"]
    assert out["error"] == "Model load failed (ImportError)"
    assert out["tool"] == "molparser"


def test_predict_inference_failure(patched_worker: None, monkeypatch: pytest.MonkeyPatch) -> None:
    class _RaisingModel:
        def generate(self, **kwargs: Any) -> Any:
            raise RuntimeError("CUDA OOM")

    def fake_get_model() -> tuple:
        return _RaisingModel(), _FakeProcessor(), _FakeTokenizer(["CCO"]), _FakeDevice()

    monkeypatch.setattr(molparser_worker, "get_model", fake_get_model)

    out = molparser_worker.predict("/tmp/anything.png")
    assert out["valid"] is False
    assert "Inference failed" in out["error"]


# ---------------------------------------------------------------------------
# Persistent-mode runner integration (subprocess is mocked end-to-end)
# ---------------------------------------------------------------------------


class _FakeStdin:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self._closing = False

    def write(self, data: bytes) -> None:
        if self._closing:
            raise BrokenPipeError("stdin closed")
        self.writes.append(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self._closing = True

    def is_closing(self) -> bool:
        return self._closing


class _FakeStdout:
    def __init__(self, lines: list[bytes]) -> None:
        self._queue: list[bytes] = list(lines)

    async def readline(self) -> bytes:
        if not self._queue:
            return b""
        return self._queue.pop(0)


class _FakeStderr:
    def __init__(self) -> None:
        self._data = b""

    async def read(self) -> bytes:
        return self._data


class _FakeProcess:
    def __init__(self, stdout_lines: list[bytes]) -> None:
        self.stdin = _FakeStdin()
        self.stdout = _FakeStdout(stdout_lines)
        self.stderr = _FakeStderr()
        self.returncode: int | None = None
        self._wait_event = asyncio.Event()

    def terminate(self) -> None:
        self.returncode = -15
        self._wait_event.set()

    def kill(self) -> None:
        self.returncode = -9
        self._wait_event.set()

    async def wait(self) -> int:
        await self._wait_event.wait()
        return self.returncode or 0

    def mark_exited(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self._wait_event.set()


def _payload(
    smiles: str = "CCO",
    *,
    is_markush: bool = False,
    cxsmiles: str = "",
    valid: bool = True,
) -> bytes:
    return (
        json.dumps(
            {
                "smiles": smiles,
                "confidence": 0.85 if valid else 0.0,
                "valid": valid,
                "tool": "molparser",
                "latency_ms": 100,
                "error": "",
                "is_markush": is_markush,
                "cxsmiles": cxsmiles,
            }
        ).encode()
        + b"\n"
    )


@pytest.fixture()
def fake_venv(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    python = bin_dir / "python"
    python.write_text("#!/bin/sh\nexit 0\n")
    python.chmod(0o755)
    return tmp_path


@pytest.fixture()
def fake_worker_file(tmp_path: Path) -> Path:
    worker = tmp_path / "molparser_worker.py"
    worker.write_text("# fake\n")
    return worker


@pytest.mark.asyncio
async def test_persistent_mode_stdin_loop(
    fake_venv: Path,
    fake_worker_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Runner in persistent mode: writes path+newline, reads JSON line."""
    image = tmp_path / "img.png"
    image.write_bytes(b"fake-png")

    proc = _FakeProcess(stdout_lines=[_payload("CCO")])

    async def fake_create(*args: Any, **kwargs: Any) -> _FakeProcess:
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    runner = OCSRRunner(
        venv_path=fake_venv,
        worker_script=fake_worker_file,
        tool_name="molparser",
    )
    await runner.start()
    result = await runner.predict_persistent(image)

    assert isinstance(result, OCSRResult)
    assert result.smiles == "CCO"
    assert result.valid is True
    assert result.tool == "molparser"
    # Worker stdin received exactly ``"<path>\n"``.
    assert proc.stdin.writes == [str(image).encode() + b"\n"]

    runner._persistent_process = None  # cleanup


@pytest.mark.asyncio
async def test_persistent_mode_markush_payload(
    fake_venv: Path,
    fake_worker_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Markush payload round-trips through OCSRResult model_validate.

    OCSRResult.model_config has ``extra="ignore"`` so the extra
    ``is_markush`` / ``cxsmiles`` fields are silently dropped at the
    Pydantic layer — but the runner should still accept and tag the
    result. Downstream Markush routing reads the raw JSON directly.
    """
    image = tmp_path / "img.png"
    image.write_bytes(b"fake-png")

    proc = _FakeProcess(
        stdout_lines=[
            _payload(
                smiles="",
                is_markush=True,
                cxsmiles="c1ccc([*:1])cc1 |$;;;;R1;;$|",
                valid=False,
            )
        ]
    )

    async def fake_create(*args: Any, **kwargs: Any) -> _FakeProcess:
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    runner = OCSRRunner(
        venv_path=fake_venv,
        worker_script=fake_worker_file,
        tool_name="molparser",
    )
    await runner.start()
    result = await runner.predict_persistent(image)

    assert result.smiles == ""
    assert result.valid is False
    assert result.tool == "molparser"
    assert result.is_markush is True
    assert result.cxsmiles == "c1ccc([*:1])cc1 |$;;;;R1;;$|"

    runner._persistent_process = None


@pytest.mark.asyncio
async def test_persistent_mode_invalid_esmiles_no_crash(
    fake_venv: Path,
    fake_worker_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Worker emits valid=False for unparseable output → runner passes through."""
    image = tmp_path / "img.png"
    image.write_bytes(b"fake-png")

    proc = _FakeProcess(stdout_lines=[_payload("", valid=False)])

    async def fake_create(*args: Any, **kwargs: Any) -> _FakeProcess:
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    runner = OCSRRunner(
        venv_path=fake_venv,
        worker_script=fake_worker_file,
        tool_name="molparser",
    )
    await runner.start()
    result = await runner.predict_persistent(image)

    assert result.valid is False
    assert result.smiles == ""
    assert result.tool == "molparser"
    assert result.error == ""

    runner._persistent_process = None


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def test_molparser_registered_in_tool_configs() -> None:
    from praviar_pipeline.pipeline.drawings.tooling import TOOL_CONFIGS

    assert "molparser" in TOOL_CONFIGS
    cfg = TOOL_CONFIGS["molparser"]
    assert cfg["venv"].name == "molparser"
    assert cfg["worker"].name == "molparser_worker.py"
    # Env contract must supply both ROOT and CKPT env vars.
    assert "MOLPARSER_ROOT" in cfg["env"]
    assert "MOLPARSER_CKPT" in cfg["env"]


def test_molparser_not_in_default_ensemble() -> None:
    """Phase B2 constraint: molparser is opt-in until Phase D re-tunes."""
    from praviar_pipeline.config import Settings

    # Read the default via model_fields so we don't need API-key env
    # vars to instantiate Settings.
    field = Settings.model_fields["drawing_ensemble_tools"]
    assert field.default_factory is not None
    defaults = field.default_factory()
    assert "molparser" not in defaults
    assert defaults == ["molscribe", "molsight"]


def test_molparser_verifies_complete_snapshot_before_model_load() -> None:
    source = Path(molparser_worker.__file__).read_text(encoding="utf-8")
    verify_offset = source.index(
        "verified_model_directory_from_ml_bom(", source.index("def get_model")
    )
    load_offset = source.index(
        "VisionEncoderDecoderModel.from_pretrained(", source.index("def get_model")
    )

    assert molparser_worker._MOLPARSER_MODEL_ID == "molparser/molparser-base"
    assert verify_offset < load_offset
