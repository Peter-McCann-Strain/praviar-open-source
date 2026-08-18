"""Tests for ``praviar_pipeline.ocsr.workers.doc2sar_worker``.

The worker normally runs inside ``venvs/doc2sar/`` with torch +
transformers + pandas + beautifulsoup4 + the Doc2SAR MLLM weights
available. These tests execute inside the main praviar_pipeline venv —
none of those deps are installed here and the weights do not
exist. So we:

1. Import the worker module directly — the module-level import
   contract forbids any heavy deps at module load; everything
   torch / transformers / pandas / bs4-related must be lazy.
2. Mock ``PIL.Image.open``, ``get_model``, and the model's
   ``.generate(...)`` to return a deterministic fake MLLM output
   (JSON object with ``scaffold`` + ``table``).
3. For the persistent-mode test, replicate the ``_FakeProcess``
   pattern from ``test_runner_persistent.py`` and drive the
   ``OCSRRunner`` against a fake subprocess that emits JSON lines
   matching the worker's output shape.
4. Verify ``SubstituentTableRow`` and ``Doc2SARResult`` round-trip
   through pydantic with ``extra="forbid"`` enforced.
5. Verify TOOL_CONFIGS registration.

No real subprocess is ever spawned; no doc2sar venv is required.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from praviar_pipeline.models.drawing import Doc2SARResult, SubstituentTableRow
from praviar_pipeline.ocsr.runner import OCSRRunner
from praviar_pipeline.ocsr.workers import doc2sar_worker

# ---------------------------------------------------------------------------
# In-process mocks for the worker's torch / transformers stack
# ---------------------------------------------------------------------------


class _FakeImage:
    def __init__(self) -> None:
        self.size = (512, 512)

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
    def generate(self, **kwargs: Any) -> _FakeTensor:
        return _FakeTensor()


class _FakeTorchModule(types.ModuleType):
    """Enough of a torch stand-in for ``with torch.no_grad():``."""

    class backends:  # noqa: N801 — mimic torch.backends
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
    """Wire the worker against fake PIL / torch stack."""
    doc2sar_worker._MODEL_CACHE.clear()

    fake_pil = types.ModuleType("PIL")
    fake_pil.Image = _FakeImageModule  # type: ignore[attr-defined]
    fake_pil_image = types.ModuleType("PIL.Image")
    fake_pil_image.open = _FakeImageModule.open  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", fake_pil_image)

    fake_torch = _FakeTorchModule("torch")
    monkeypatch.setitem(sys.modules, "torch", fake_torch)


def _install_fake_model(
    monkeypatch: pytest.MonkeyPatch,
    decoded_raw: str,
) -> None:
    """Patch get_model() to return the fake stack with a fixed decode."""

    def fake_get_model() -> tuple:
        return (
            _FakeModel(),
            _FakeProcessor(),
            _FakeTokenizer([decoded_raw]),
            _FakeDevice("cpu"),
        )

    monkeypatch.setattr(doc2sar_worker, "get_model", fake_get_model)


# ---------------------------------------------------------------------------
# Output shape tests (one-shot in-process)
# ---------------------------------------------------------------------------


def test_predict_returns_full_doc2sar_shape(
    patched_worker: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given a well-formed MLLM output, ``predict`` returns a dict with
    the exact Doc2SARResult contract keys."""
    mllm_out = json.dumps(
        {
            "scaffold": "c1ccc(R1)cc1",
            "table": [
                {
                    "row": 0,
                    "R1": "OCH3",
                    "R2": "Cl",
                    "smiles": "COc1ccc(Cl)cc1",
                    "confidence": 0.91,
                },
                {
                    "row": 1,
                    "R1": "F",
                    "R2": "H",
                    "smiles": "Fc1ccccc1",
                    "confidence": 0.86,
                },
            ],
        }
    )
    _install_fake_model(monkeypatch, mllm_out)

    out = doc2sar_worker.predict("/tmp/whatever.png")

    # Shape — every Doc2SARResult key present and typed correctly.
    assert out["tool"] == "doc2sar"
    assert out["scaffold_smiles"] == "c1ccc(R1)cc1"
    assert isinstance(out["substituent_table"], list)
    assert len(out["substituent_table"]) == 2
    assert isinstance(out["enumerated_species"], list)
    assert out["enumerated_species"] == ["COc1ccc(Cl)cc1", "Fc1ccccc1"]
    assert out["valid"] is True
    assert out["overflowed"] is False
    assert out["error"] == ""
    assert out["confidence"] > 0.0
    assert "latency_ms" in out

    row0 = out["substituent_table"][0]
    assert row0["row_index"] == 0
    assert row0["rgroup_labels"] == {"R1": "OCH3", "R2": "Cl"}
    assert row0["resolved_smiles"] == "COc1ccc(Cl)cc1"
    assert row0["confidence"] == pytest.approx(0.91)


def test_predict_missing_scaffold_marks_invalid(
    patched_worker: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MLLM emits a table but no scaffold → invalid with explicit error."""
    mllm_out = json.dumps(
        {
            "scaffold": "",
            "table": [{"row": 0, "R1": "OCH3", "smiles": "COc1ccccc1"}],
        }
    )
    _install_fake_model(monkeypatch, mllm_out)

    out = doc2sar_worker.predict("/tmp/whatever.png")

    assert out["valid"] is False
    assert out["scaffold_smiles"] == ""
    assert out["enumerated_species"] == []
    assert "Missing scaffold" in out["error"]
    assert out["tool"] == "doc2sar"


def test_predict_overflow_abstains(patched_worker: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Table with > max_enum rows → overflowed=True, empty species."""
    rows = [{"row": i, "R1": f"X{i}", "smiles": f"C{i}"} for i in range(10)]
    mllm_out = json.dumps({"scaffold": "c1ccc(R1)cc1", "table": rows})
    _install_fake_model(monkeypatch, mllm_out)

    # Cap below the row count forces overflow.
    out = doc2sar_worker.predict("/tmp/whatever.png", max_enum=5)

    assert out["overflowed"] is True
    assert out["enumerated_species"] == []
    assert out["valid"] is False
    assert out["confidence"] == 0.0
    assert out["scaffold_smiles"] == "c1ccc(R1)cc1"
    # Table itself is still returned — the caller may want to log it.
    assert len(out["substituent_table"]) == 10


def test_predict_garbage_output_no_crash(
    patched_worker: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decoder emits non-JSON garbage → valid=False, no raise."""
    _install_fake_model(monkeypatch, "not-a-json {{{")
    out = doc2sar_worker.predict("/tmp/whatever.png")

    assert out["valid"] is False
    assert out["scaffold_smiles"] == ""
    assert out["substituent_table"] == []
    assert out["enumerated_species"] == []
    # No JSON → no scaffold → explicit error, not a crash.
    assert "Missing scaffold" in out["error"]


def test_predict_markdown_fenced_output(
    patched_worker: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MLLM sometimes wraps JSON in ``` fences — parser must strip them."""
    mllm_out = (
        "```json\n"
        + json.dumps(
            {
                "scaffold": "c1ccncc1",
                "table": [
                    {"row": 0, "R1": "Me", "smiles": "Cc1ccncc1"},
                ],
            }
        )
        + "\n```"
    )
    _install_fake_model(monkeypatch, mllm_out)

    out = doc2sar_worker.predict("/tmp/whatever.png")

    assert out["scaffold_smiles"] == "c1ccncc1"
    assert out["enumerated_species"] == ["Cc1ccncc1"]
    assert out["valid"] is True


def test_predict_model_load_failure(patched_worker: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing venv → clean error surfaces with ``tool=doc2sar``."""

    def raise_on_load() -> tuple:
        raise ImportError("doc2sar venv not set up — missing dependency: torch")

    monkeypatch.setattr(doc2sar_worker, "get_model", raise_on_load)

    out = doc2sar_worker.predict("/tmp/whatever.png")
    assert out["valid"] is False
    assert "Model load failed" in out["error"]
    assert out["error"] == "Model load failed (ImportError)"
    assert out["tool"] == "doc2sar"


def test_predict_image_load_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """PIL.open raises → worker returns 'Image load failed' error dict."""
    doc2sar_worker._MODEL_CACHE.clear()

    class _RaisingImageModule:
        @staticmethod
        def open(path: str) -> None:
            raise OSError(f"cannot open {path}")

    fake_pil = types.ModuleType("PIL")
    fake_pil.Image = _RaisingImageModule  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)

    out = doc2sar_worker.predict("/tmp/does-not-exist.png")

    assert out["valid"] is False
    assert out["scaffold_smiles"] == ""
    assert "Image load failed" in out["error"]
    assert out["tool"] == "doc2sar"


def test_worker_module_imports_without_torch_installed() -> None:
    """Module must import on the dev venv (no torch / transformers /
    pandas / bs4). All heavy imports live inside ``get_model``."""
    assert hasattr(doc2sar_worker, "predict")
    assert hasattr(doc2sar_worker, "get_model")
    # Calling predict with no model stack returns an error dict rather
    # than raising ImportError from the module.
    doc2sar_worker._MODEL_CACHE.clear()
    # No patched_worker fixture here — this is the true cold-start case.
    out = doc2sar_worker.predict("/nonexistent/path.png")
    assert isinstance(out, dict)
    assert out["tool"] == "doc2sar"
    assert out["valid"] is False
    # Error could come from either PIL missing or the image load failing.
    assert out["error"]


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


def _payload(
    scaffold: str = "c1ccc(R1)cc1",
    *,
    species: list[str] | None = None,
    overflowed: bool = False,
    valid: bool = True,
    error: str = "",
) -> bytes:
    return (
        json.dumps(
            {
                "scaffold_smiles": scaffold,
                "substituent_table": [
                    {
                        "row_index": 0,
                        "rgroup_labels": {"R1": "OCH3"},
                        "resolved_smiles": (species or [""])[0],
                        "confidence": 0.9,
                    }
                ],
                "enumerated_species": species or [],
                "confidence": 0.8 if valid else 0.0,
                "tool": "doc2sar",
                "latency_ms": 123,
                "error": error,
                "overflowed": overflowed,
                "valid": valid,
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
    worker = tmp_path / "doc2sar_worker.py"
    worker.write_text("# fake\n")
    return worker


@pytest.mark.asyncio
async def test_persistent_mode_stdin_loop(
    fake_venv: Path,
    fake_worker_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Persistent runner: writes '<path>\\n', reads one JSON line per input.

    The runner selects Doc2SARResult for this registered specialist so
    scaffold/table/species data cannot be silently discarded.
    """
    image = tmp_path / "table.png"
    image.write_bytes(b"fake-png")

    proc = _FakeProcess(stdout_lines=[_payload(species=["COc1ccccc1"])])

    async def fake_create(*args: Any, **kwargs: Any) -> _FakeProcess:
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    runner = OCSRRunner(
        venv_path=fake_venv,
        worker_script=fake_worker_file,
        tool_name="doc2sar",
    )
    await runner.start()
    result = await runner.predict_persistent(image)

    assert isinstance(result, Doc2SARResult)
    assert result.tool == "doc2sar"
    assert result.scaffold_smiles == "c1ccc(R1)cc1"
    assert result.enumerated_species == ["COc1ccccc1"]
    # Worker stdin received exactly ``"<path>\n"``.
    assert proc.stdin.writes == [str(image).encode() + b"\n"]

    runner._persistent_process = None  # cleanup


@pytest.mark.asyncio
async def test_persistent_mode_overflow_payload(
    fake_venv: Path,
    fake_worker_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Overflow payload round-trips through runner without crashing.

    Downstream Doc2SAR consumers read the raw payload and validate
    against Doc2SARResult; we validate the structure here directly.
    """
    image = tmp_path / "big_table.png"
    image.write_bytes(b"fake-png")

    raw = _payload(species=[], overflowed=True, valid=False)
    proc = _FakeProcess(stdout_lines=[raw])

    async def fake_create(*args: Any, **kwargs: Any) -> _FakeProcess:
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    runner = OCSRRunner(
        venv_path=fake_venv,
        worker_script=fake_worker_file,
        tool_name="doc2sar",
    )
    await runner.start()
    result = await runner.predict_persistent(image)

    assert result.tool == "doc2sar"
    assert result.valid is False

    # Validate the raw JSON against the strict Doc2SARResult model.
    # The worker payload carries a runtime ``valid`` flag for the
    # OCSRRunner's convention; Doc2SARResult itself has
    # ``extra="forbid"`` so downstream consumers must drop that key
    # before validating — mirrors how the aggregation layer handles
    # the split between the wire format and the strict contract.
    decoded = json.loads(raw.decode())
    decoded.pop("valid", None)
    validated = Doc2SARResult.model_validate(decoded)
    assert validated.overflowed is True
    assert validated.enumerated_species == []
    assert validated.scaffold_smiles == "c1ccc(R1)cc1"

    runner._persistent_process = None


# ---------------------------------------------------------------------------
# Pydantic model contracts
# ---------------------------------------------------------------------------


def test_substituent_table_row_round_trips() -> None:
    """SubstituentTableRow round-trips and enforces extra='forbid'."""
    row = SubstituentTableRow(
        row_index=3,
        rgroup_labels={"R1": "OMe", "R2": "CF3"},
        resolved_smiles="COc1ccc(C(F)(F)F)cc1",
        confidence=0.88,
    )
    dumped = row.model_dump()
    restored = SubstituentTableRow.model_validate(dumped)
    assert restored == row

    with pytest.raises(ValidationError):
        SubstituentTableRow.model_validate(
            {
                "row_index": 0,
                "rgroup_labels": {},
                "rogue_field": "nope",
            }
        )


def test_doc2sar_result_round_trips() -> None:
    """Doc2SARResult round-trips and enforces extra='forbid'."""
    result = Doc2SARResult(
        scaffold_smiles="c1ccc(R1)cc1",
        substituent_table=[
            SubstituentTableRow(
                row_index=0,
                rgroup_labels={"R1": "OCH3"},
                resolved_smiles="COc1ccccc1",
                confidence=0.9,
            )
        ],
        enumerated_species=["COc1ccccc1"],
        confidence=0.8,
        latency_ms=420,
        error="",
        overflowed=False,
    )
    dumped = result.model_dump()
    restored = Doc2SARResult.model_validate(dumped)
    assert restored == result
    assert restored.tool == "doc2sar"

    with pytest.raises(ValidationError):
        Doc2SARResult.model_validate(
            {
                "scaffold_smiles": "",
                "confidence": 0.0,
                "unexpected_key": 42,
            }
        )


# ---------------------------------------------------------------------------
# TOOL_CONFIGS registration
# ---------------------------------------------------------------------------


def test_doc2sar_registered_in_tool_configs() -> None:
    from praviar_pipeline.pipeline.drawings.tooling import TOOL_CONFIGS

    assert "doc2sar" in TOOL_CONFIGS
    cfg = TOOL_CONFIGS["doc2sar"]
    assert cfg["venv"].name == "doc2sar"
    assert cfg["worker"].name == "doc2sar_worker.py"
    assert "DOC2SAR_ROOT" in cfg["env"]
    assert "DOC2SAR_CKPT" in cfg["env"]


def test_doc2sar_not_in_default_ensemble() -> None:
    """Doc2SAR is opt-in and must not be in drawing_ensemble_tools default."""
    from praviar_pipeline.config import Settings

    field = Settings.model_fields["drawing_ensemble_tools"]
    assert field.default_factory is not None
    defaults = field.default_factory()
    assert "doc2sar" not in defaults


def test_doc2sar_config_flags_default_off() -> None:
    """drawing_doc2sar_enabled must default False; max_enumerations=500."""
    from praviar_pipeline.config import Settings

    enabled_field = Settings.model_fields["drawing_doc2sar_enabled"]
    assert enabled_field.default is False

    max_field = Settings.model_fields["drawing_doc2sar_max_enumerations"]
    assert max_field.default == 500


def test_doc2sar_verifies_complete_snapshot_before_model_load() -> None:
    source = Path(doc2sar_worker.__file__).read_text(encoding="utf-8")
    verify_offset = source.index(
        "verified_model_directory_from_ml_bom(", source.index("def get_model")
    )
    load_offset = source.index(
        "VisionEncoderDecoderModel.from_pretrained(", source.index("def get_model")
    )

    assert doc2sar_worker._DOC2SAR_MODEL_ID == "doc2sar/doc2sar-mllm"
    assert verify_offset < load_offset
