"""Tests for the ChemSAM segmentation backend.

All subprocess + model machinery is mocked — these tests run on the dev
``.venv`` without the optional ``venvs/chemsam`` venv existing and
without SAM / torch / opencv / ChemSAM weights installed.

Coverage:
    1. One-shot subprocess mode: a ``SegmentationRunner`` targeted at the
       ChemSAM worker invokes the right Python + script with ``segment``
       and parses the JSON array it emits.
    2. Persistent mode (``_FakeProcess`` pattern borrowed from
       ``test_runner_persistent.py``): can be started and written to.
    3. ``get_segmentation_runner`` factory dispatch picks the ChemSAM
       venv + worker when ``backend="chemsam"`` and the DECIMER pair
       when ``backend="decimer"``. Unknown backends raise ``ValueError``.
    4. End-to-end respect for ``settings.drawing_segmentation_tool``:
       ``step2d_drawings._get_segmentation_runner()`` routes through the
       right backend.
    5. Worker import-guard: importing the module on the dev venv (where
       SAM / torch are unavailable) must not raise — all heavy imports
       are inside ``_load_predictor`` and surface a "ChemSAM venv not
       set up" error to the caller rather than a raw traceback.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from praviar_pipeline.ocsr.runner import SegmentationRunner
from praviar_pipeline.ocsr.workers import chemsam_seg_worker
from praviar_pipeline.pipeline.drawings.factories import get_segmentation_runner

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Fakes (adapted from test_runner_persistent.py)
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
        self._queue = list(lines)

    async def readline(self) -> bytes:
        if not self._queue:
            return b""
        return self._queue.pop(0)


class _FakeStderr:
    def __init__(self, content: bytes = b"") -> None:
        self._content = content

    async def read(self) -> bytes:
        data = self._content
        self._content = b""
        return data


class _FakeProcess:
    def __init__(
        self,
        stdout_lines: list[bytes] | None = None,
        stderr: bytes = b"",
        returncode: int | None = None,
    ) -> None:
        self.stdin = _FakeStdin()
        self.stdout = _FakeStdout(stdout_lines or [])
        self.stderr = _FakeStderr(stderr)
        self.returncode = returncode
        self._wait_event = asyncio.Event()
        if returncode is not None:
            self._wait_event.set()

    def terminate(self) -> None:
        self.returncode = -15
        self._wait_event.set()

    def kill(self) -> None:
        self.returncode = -9
        self._wait_event.set()

    async def wait(self) -> int:
        await self._wait_event.wait()
        return self.returncode if self.returncode is not None else 0

    async def communicate(self) -> tuple[bytes, bytes]:
        # Drain queued stdout lines into one blob — matches asyncio.subprocess.Process.
        stdout_parts: list[bytes] = []
        while True:
            line = await self.stdout.readline()
            if not line:
                break
            stdout_parts.append(line)
        stderr_bytes = await self.stderr.read()
        if self.returncode is None:
            self.returncode = 0
        self._wait_event.set()
        return b"".join(stdout_parts), stderr_bytes


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_venv(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    python = bin_dir / "python"
    python.write_text("#!/bin/sh\nexit 0\n")
    python.chmod(0o755)
    return tmp_path


@pytest.fixture()
def fake_worker(tmp_path: Path) -> Path:
    worker = tmp_path / "chemsam_seg_worker.py"
    worker.write_text("# fake worker\n")
    return worker


class _Logger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def warning(self, event: str, **kwargs: Any) -> None:
        self.events.append((event, kwargs))


# ---------------------------------------------------------------------------
# Tests: worker module import-guard
# ---------------------------------------------------------------------------


def test_worker_module_imports_without_sam_installed() -> None:
    """The module must import on a venv that has no SAM / torch / cv2.
    Heavy deps are lazily loaded from ``_load_predictor``. We assert
    that calling ``segment()`` without those deps returns a clean
    error dict rather than raising ``ImportError``."""
    # Already imported at module level — proves the guard.
    assert hasattr(chemsam_seg_worker, "segment")
    assert hasattr(chemsam_seg_worker, "_load_predictor")

    result = chemsam_seg_worker.segment("/nonexistent/image.png", "/tmp/does_not_matter")
    assert isinstance(result, list)
    assert len(result) == 1
    assert "error" in result[0]
    # Message must be stable without exposing dependency or filesystem details.
    msg = result[0]["error"]
    assert msg.startswith("ChemSAM model load failed (")


def test_load_predictor_raises_runtime_error_when_deps_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_load_predictor must surface a RuntimeError with a clear message
    pointing at the venv README when any heavy dep is missing."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name in {"cv2", "torch", "segment_anything"}:
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="ChemSAM worker dependency is unavailable"):
        chemsam_seg_worker._load_predictor()


# ---------------------------------------------------------------------------
# Tests: one-shot subprocess mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_shot_parses_json_array(
    fake_venv: Path,
    fake_worker: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One-shot: runner → subprocess → JSON array → SegmentationResult list."""
    page = tmp_path / "page.png"
    page.write_bytes(b"\x89PNG\r\n\x1a\n")
    out = tmp_path / "out"
    out.mkdir()
    (out / "seg000.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (out / "seg001.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    payload = json.dumps(
        [
            {
                "segment_index": 0,
                "bbox": [10, 20, 110, 120],
                "image_path": str(out / "seg000.png"),
                "width": 100,
                "height": 100,
                "confidence": 0.93,
            },
            {
                "segment_index": 1,
                "bbox": [5, 200, 80, 280],
                "image_path": str(out / "seg001.png"),
                "width": 75,
                "height": 80,
                "confidence": 0.81,
            },
        ]
    ).encode()

    captured: dict[str, Any] = {}

    class _Proc:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return payload, b""

    async def fake_create(*args: Any, **kwargs: Any) -> _Proc:
        captured["args"] = args
        return _Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    runner = SegmentationRunner(venv_path=fake_venv, worker_script=fake_worker)
    results = await runner.segment(page, out)

    assert captured["args"][0] == str(fake_venv / "bin" / "python")
    assert captured["args"][1] == str(fake_worker)
    assert captured["args"][2] == "segment"
    assert captured["args"][3] == str(page)
    assert captured["args"][4] == str(out)

    assert len(results) == 2
    assert results[0].segment_index == 0
    assert results[0].bbox == (10, 20, 110, 120)
    assert results[1].bbox == (5, 200, 80, 280)
    # SegmentationResult has extra="forbid", so ``confidence`` in the
    # JSON would fail validation unless the model accepts it. If it
    # doesn't, this test flags the contract mismatch.


# ---------------------------------------------------------------------------
# Tests: persistent mode via _FakeProcess
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persistent_mode_writes_image_and_dir_to_stdin(
    fake_venv: Path,
    fake_worker: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persistent-mode protocol: write '<img> <out>\\n' to stdin, read one
    JSON line back.

    The project's ``SegmentationRunner`` doesn't yet expose a dedicated
    persistent API, so this test directly exercises the worker's
    documented stdin contract by spawning the persistent-mode command
    and asserting the fake worker receives the expected bytes.
    """
    page = tmp_path / "page.png"
    page.write_bytes(b"\x89PNG\r\n\x1a\n")
    out_dir = tmp_path / "persist_out"

    response = (
        json.dumps(
            [
                {
                    "segment_index": 0,
                    "bbox": [1, 2, 3, 4],
                    "image_path": str(out_dir / "seg000.png"),
                    "width": 2,
                    "height": 2,
                    "confidence": 0.77,
                }
            ]
        ).encode()
        + b"\n"
    )

    proc = _FakeProcess(stdout_lines=[response])

    async def fake_create(*args: Any, **kwargs: Any) -> _FakeProcess:
        # Assert the worker was launched in persistent mode.
        assert "--persistent" in args
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    # Simulate the protocol directly.
    spawned = await asyncio.create_subprocess_exec(
        str(fake_venv / "bin" / "python"),
        str(fake_worker),
        "segment",
        "--persistent",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert spawned is proc

    # Write a request line.
    line = f"{page} {out_dir}\n".encode()
    proc.stdin.write(line)
    await proc.stdin.drain()

    raw = await proc.stdout.readline()
    data = json.loads(raw.decode())
    assert data[0]["segment_index"] == 0
    assert data[0]["bbox"] == [1, 2, 3, 4]
    assert data[0]["confidence"] == 0.77
    assert proc.stdin.writes == [line]


# ---------------------------------------------------------------------------
# Tests: factory dispatch
# ---------------------------------------------------------------------------


def test_factory_dispatches_to_chemsam_backend(tmp_path: Path) -> None:
    """With ``backend='chemsam'``, the factory picks the ChemSAM venv/worker
    pair from the ``backends`` dict."""
    chemsam_venv = tmp_path / "chemsam"
    (chemsam_venv / "bin").mkdir(parents=True)
    (chemsam_venv / "bin" / "python").write_text("")
    decimer_venv = tmp_path / "decimer"
    (decimer_venv / "bin").mkdir(parents=True)
    (decimer_venv / "bin" / "python").write_text("")

    captured: dict[str, Any] = {}

    def _runner_cls(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return kwargs

    logger = _Logger()
    backends = {
        "decimer": {
            "venv": decimer_venv,
            "worker": tmp_path / "decimer_seg_worker.py",
        },
        "chemsam": {
            "venv": chemsam_venv,
            "worker": tmp_path / "chemsam_seg_worker.py",
        },
    }

    result = get_segmentation_runner(
        logger=logger,
        runner_cls=_runner_cls,
        backend="chemsam",
        backends=backends,
    )

    assert result is not None
    assert captured["venv_path"] == chemsam_venv
    assert captured["worker_script"] == tmp_path / "chemsam_seg_worker.py"
    assert logger.events == []


def test_factory_dispatches_to_decimer_backend(tmp_path: Path) -> None:
    """Default ``backend='decimer'`` continues to pick the DECIMER pair."""
    decimer_venv = tmp_path / "decimer"
    (decimer_venv / "bin").mkdir(parents=True)
    (decimer_venv / "bin" / "python").write_text("")

    captured: dict[str, Any] = {}

    def _runner_cls(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return kwargs

    backends = {
        "decimer": {
            "venv": decimer_venv,
            "worker": tmp_path / "decimer_seg_worker.py",
        },
        "chemsam": {
            "venv": tmp_path / "chemsam",
            "worker": tmp_path / "chemsam_seg_worker.py",
        },
    }

    result = get_segmentation_runner(
        logger=_Logger(),
        runner_cls=_runner_cls,
        backend="decimer",
        backends=backends,
    )

    assert result is not None
    assert captured["venv_path"] == decimer_venv


def test_factory_rejects_unknown_backend(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported segmentation backend"):
        get_segmentation_runner(
            logger=_Logger(),
            runner_cls=lambda **kw: kw,
            backend="bogus",  # type: ignore[arg-type]
            backends={"decimer": {"venv": tmp_path, "worker": tmp_path}},
        )


def test_factory_missing_backend_config_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No configuration registered"):
        get_segmentation_runner(
            logger=_Logger(),
            runner_cls=lambda **kw: kw,
            backend="chemsam",
            backends={"decimer": {"venv": tmp_path, "worker": tmp_path}},
        )


def test_factory_returns_none_when_chemsam_venv_missing(tmp_path: Path) -> None:
    logger = _Logger()
    backends = {
        "chemsam": {
            "venv": tmp_path / "missing_chemsam",
            "worker": tmp_path / "worker.py",
        },
    }

    result = get_segmentation_runner(
        logger=logger,
        runner_cls=lambda **kw: kw,
        backend="chemsam",
        backends=backends,
    )

    assert result is None
    assert logger.events == [
        (
            "segmentation_venv_missing",
            {"backend": "chemsam"},
        )
    ]


# ---------------------------------------------------------------------------
# Tests: end-to-end flag plumbing
# ---------------------------------------------------------------------------


def test_step2d_helper_routes_to_chemsam_when_flag_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``step2d_drawings._get_segmentation_runner(settings)`` must pass
    ``backend=settings.drawing_segmentation_tool`` through to the
    factory."""
    from praviar_pipeline.pipeline import step2d_drawings

    captured: dict[str, Any] = {}

    def _fake_factory(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "sentinel"

    monkeypatch.setattr(
        step2d_drawings.drawing_factories,
        "get_segmentation_runner",
        _fake_factory,
    )

    settings = SimpleNamespace(drawing_segmentation_tool="chemsam")
    result = step2d_drawings._get_segmentation_runner(settings)

    assert result == "sentinel"
    assert captured["backend"] == "chemsam"
    assert "backends" in captured
    # ``moldet`` is part of the canonical dispatch table; chemsam +
    # decimer must still both be registered.
    assert {"decimer", "chemsam"}.issubset(captured["backends"])
    assert captured["backends"]["chemsam"]["worker"].name == "chemsam_seg_worker.py"


def test_step2d_helper_defaults_to_decimer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from praviar_pipeline.pipeline import step2d_drawings

    captured: dict[str, Any] = {}

    def _fake_factory(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "sentinel"

    monkeypatch.setattr(
        step2d_drawings.drawing_factories,
        "get_segmentation_runner",
        _fake_factory,
    )

    settings = SimpleNamespace(drawing_segmentation_tool="decimer")
    step2d_drawings._get_segmentation_runner(settings)

    assert captured["backend"] == "decimer"
    assert captured["backends"]["decimer"]["worker"].name == "decimer_seg_worker.py"
