"""Tests for the persistent-worker mode of ``OCSRRunner``.

These tests mock the ``asyncio.subprocess`` machinery so no real
subprocesses are spawned. They verify:

1. The start/predict_persistent/stop protocol writes the image path +
   newline to the worker's stdin and reads a single JSON line from stdout.
2. Backward compatibility: when ``start()`` is not called, ``predict``
   still takes the original one-shot ``create_subprocess_exec`` path.
3. Error handling: if the persistent worker dies mid-call, ``predict``
   falls back to one-shot rather than silently returning bad data, and
   ``predict_persistent`` itself raises a clear ``RuntimeError``.
4. Context-manager cleanup: ``async with runner:`` starts and stops the
   worker; ``stop()`` sends an empty line then waits, and falls back to
   ``terminate()`` if the worker doesn't exit.
5. ``start()`` is idempotent.

The tests use an in-process fake ``asyncio.subprocess.Process`` that
exposes ``stdin``, ``stdout``, and ``stderr`` stream-like attributes and
records what was written so assertions can inspect the protocol.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest

from praviar_pipeline.models.drawing import OCSRResult
from praviar_pipeline.ocsr.runner import (
    OCSROutputError,
    OCSRRunner,
    OCSRSpawnError,
    OCSRTimeoutError,
    OCSRWorkerExitError,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Fakes
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
        # Each readline() pops the next entry. ``b""`` represents EOF.
        self._queue: list[bytes] = list(lines)

    async def readline(self) -> bytes:
        if not self._queue:
            return b""
        return self._queue.pop(0)

    def feed(self, line: bytes) -> None:
        self._queue.append(line)


class _FakeStderr:
    def __init__(self, content: bytes = b"") -> None:
        self._content = content

    async def read(self) -> bytes:
        data = self._content
        self._content = b""
        return data


class _FakeProcess:
    """Mimics the subset of ``asyncio.subprocess.Process`` we rely on."""

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
        self.terminated = False
        self.killed = False
        self._wait_event = asyncio.Event()
        if returncode is not None:
            self._wait_event.set()

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15
        self._wait_event.set()

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self._wait_event.set()

    async def wait(self) -> int:
        await self._wait_event.wait()
        return self.returncode if self.returncode is not None else 0

    def mark_exited(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self._wait_event.set()


class _NeverExitingProcess(_FakeProcess):
    """Simulates a worker that ignores the empty-line shutdown signal."""

    async def wait(self) -> int:
        # Only resolves after terminate() or kill().
        await self._wait_event.wait()
        return self.returncode if self.returncode is not None else 0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_venv(tmp_path: Path) -> Path:
    """Create a fake venv layout so ``OCSRRunner`` ctor checks pass."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    python = bin_dir / "python"
    python.write_text("#!/bin/sh\nexit 0\n")
    python.chmod(0o755)
    return tmp_path


@pytest.fixture()
def fake_worker(tmp_path: Path) -> Path:
    worker = tmp_path / "worker.py"
    worker.write_text("# fake worker\n")
    return worker


@pytest.fixture()
def runner(fake_venv: Path, fake_worker: Path) -> OCSRRunner:
    return OCSRRunner(
        venv_path=fake_venv,
        worker_script=fake_worker,
        tool_name="fake",
        timeout_s=5.0,
    )


def _ok_payload(smiles: str = "CCO", tool: str = "fake") -> bytes:
    return (
        json.dumps(
            {
                "smiles": smiles,
                "confidence": 0.9,
                "valid": True,
                "tool": tool,
                "error": "",
            }
        ).encode()
        + b"\n"
    )


# ---------------------------------------------------------------------------
# Tests: persistent protocol
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_spawns_worker_with_persistent_flag(
    runner: OCSRRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    async def fake_create(*args: Any, **kwargs: Any) -> _FakeProcess:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    await runner.start()

    assert runner._persistent_process is not None
    # argv: python, worker, "predict", "--persistent"
    assert captured["args"][0] == str(runner.python)
    assert captured["args"][1] == str(runner.worker)
    assert captured["args"][2] == "predict"
    assert captured["args"][3] == "--persistent"
    assert kwargs_has_pipe(captured["kwargs"], "stdin")
    assert kwargs_has_pipe(captured["kwargs"], "stdout")

    # Cleanup — avoid leaving state across tests
    runner._persistent_process = None


def kwargs_has_pipe(kwargs: dict[str, Any], name: str) -> bool:
    return kwargs.get(name) == asyncio.subprocess.PIPE


@pytest.mark.asyncio
async def test_predict_persistent_round_trip(
    runner: OCSRRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify the persistent-mode protocol: write path+newline, read JSON line."""
    image = tmp_path / "img.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    proc = _FakeProcess(stdout_lines=[_ok_payload("CCO")])

    async def fake_create(*args: Any, **kwargs: Any) -> _FakeProcess:
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    await runner.start()
    result = await runner.predict_persistent(image)

    assert isinstance(result, OCSRResult)
    assert result.smiles == "CCO"
    assert result.valid is True
    # The runner overwrites ``tool`` on the result for consistency.
    assert result.tool == "fake"
    assert result.latency_ms >= 0
    # And the worker's stdin received exactly "path\n".
    assert proc.stdin.writes == [str(image).encode() + b"\n"]

    # Cleanup
    runner._persistent_process = None


@pytest.mark.asyncio
async def test_predict_uses_persistent_when_started(
    runner: OCSRRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """After ``start()``, ``predict`` should use the persistent worker."""
    image = tmp_path / "img.png"
    image.write_bytes(b"fake")

    proc = _FakeProcess(stdout_lines=[_ok_payload("CCO"), _ok_payload("CCC")])

    call_counter = {"n": 0}

    async def fake_create(*args: Any, **kwargs: Any) -> _FakeProcess:
        call_counter["n"] += 1
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    await runner.start()
    r1 = await runner.predict(image)
    r2 = await runner.predict(image)

    assert r1.smiles == "CCO"
    assert r2.smiles == "CCC"
    # Only one subprocess spawn across two predicts.
    assert call_counter["n"] == 1
    assert len(proc.stdin.writes) == 2

    runner._persistent_process = None


# ---------------------------------------------------------------------------
# Tests: backward compatibility
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_predict_one_shot_when_not_started(
    runner: OCSRRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without ``start()``, each ``predict`` spawns a fresh subprocess."""
    image = tmp_path / "img.png"
    image.write_bytes(b"fake")

    captured: dict[str, Any] = {"argv": []}

    class _OneShotProc:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return _ok_payload("CCO"), b""

    async def fake_create(*args: Any, **kwargs: Any) -> _OneShotProc:
        captured["argv"].append(args)
        # The one-shot path must NOT pass stdin=PIPE — it uses
        # .communicate() without stdin.
        assert "stdin" not in kwargs
        return _OneShotProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    result = await runner.predict(image)

    assert result.smiles == "CCO"
    # argv ends with "predict <image>" — not "--persistent".
    last_args = captured["argv"][-1]
    assert last_args[-2] == "predict"
    assert last_args[-1] == str(image)
    assert "--persistent" not in last_args


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_predict_persistent_raises_if_not_started(runner: OCSRRunner, tmp_path: Path) -> None:
    image = tmp_path / "img.png"
    image.write_bytes(b"fake")
    with pytest.raises(RuntimeError, match="not running"):
        await runner.predict_persistent(image)


@pytest.mark.asyncio
async def test_predict_persistent_raises_if_worker_dead(
    runner: OCSRRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    image = tmp_path / "img.png"
    image.write_bytes(b"fake")

    proc = _FakeProcess(stdout_lines=[], stderr=b"traceback\n", returncode=1)

    async def fake_create(*args: Any, **kwargs: Any) -> _FakeProcess:
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    await runner.start()
    # Worker already exited with returncode=1 — predict_persistent must
    # raise rather than hang on stdout.
    with pytest.raises(RuntimeError, match="has exited"):
        await runner.predict_persistent(image)


@pytest.mark.asyncio
async def test_predict_persistent_raises_on_eof(
    runner: OCSRRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Worker dies mid-call: stdout returns b"" (EOF) → clear error."""
    image = tmp_path / "img.png"
    image.write_bytes(b"fake")

    # stdout_lines empty → readline() returns b"" immediately.
    proc = _FakeProcess(stdout_lines=[], stderr=b"crash\n", returncode=None)

    async def fake_create(*args: Any, **kwargs: Any) -> _FakeProcess:
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    await runner.start()
    with pytest.raises(RuntimeError, match="closed stdout"):
        await runner.predict_persistent(image)


@pytest.mark.asyncio
async def test_predict_falls_back_to_one_shot_if_persistent_dies(
    runner: OCSRRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If persistent worker has died, ``predict`` must not silently return bad data —
    it falls back to the one-shot path."""
    image = tmp_path / "img.png"
    image.write_bytes(b"fake")

    dead_proc = _FakeProcess(stdout_lines=[], stderr=b"", returncode=1)

    class _OneShotProc:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return _ok_payload("FALLBACK"), b""

    call_log: list[str] = []

    async def fake_create(*args: Any, **kwargs: Any):
        # First call: start() returns the dead persistent proc.
        # Second call: predict() one-shot fallback.
        if "--persistent" in args:
            call_log.append("persistent")
            return dead_proc
        call_log.append("one_shot")
        return _OneShotProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    await runner.start()
    result = await runner.predict(image)

    assert result.smiles == "FALLBACK"
    assert call_log == ["persistent", "one_shot"]
    # Runner dropped the dead worker.
    assert runner._persistent_process is None


@pytest.mark.asyncio
async def test_predict_persistent_missing_image_returns_error_result(
    runner: OCSRRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    proc = _FakeProcess(stdout_lines=[_ok_payload("CCO")])

    async def fake_create(*args: Any, **kwargs: Any) -> _FakeProcess:
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    await runner.start()
    missing = tmp_path / "nope.png"

    result = await runner.predict_persistent(missing)

    assert result.error == "Image not found"
    assert str(missing) not in result.error
    # No write should have happened — worker never saw the bad path.
    assert proc.stdin.writes == []

    runner._persistent_process = None


@pytest.mark.asyncio
async def test_predict_persistent_bad_json(
    runner: OCSRRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    image = tmp_path / "img.png"
    image.write_bytes(b"fake")
    proc = _FakeProcess(stdout_lines=[b"not-json\n"])

    async def fake_create(*args: Any, **kwargs: Any) -> _FakeProcess:
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    await runner.start()

    result = await runner.predict_persistent(image)
    assert result.error.startswith("Bad JSON output from persistent worker")

    runner._persistent_process = None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure_mode", "error_type"),
    [
        ("timeout", OCSRTimeoutError),
        ("spawn", OCSRSpawnError),
        ("nonzero", OCSRWorkerExitError),
        ("bad_json", OCSROutputError),
    ],
)
async def test_live_one_shot_infrastructure_failures_raise_typed_errors(
    fake_venv: Path,
    fake_worker: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure_mode: str,
    error_type: type[RuntimeError],
) -> None:
    image = tmp_path / "img.png"
    image.write_bytes(b"fake")
    live_runner = OCSRRunner(
        venv_path=fake_venv,
        worker_script=fake_worker,
        tool_name="fake",
        timeout_s=5.0,
        fail_closed=True,
    )

    class _OneShotFailureProcess:
        returncode = 7 if failure_mode == "nonzero" else 0

        async def communicate(self) -> tuple[bytes, bytes]:
            if failure_mode == "timeout":
                raise TimeoutError
            if failure_mode == "bad_json":
                return b"not-json", b""
            return b"", b"worker failed"

    async def fake_create(*_args: Any, **_kwargs: Any) -> _OneShotFailureProcess:
        if failure_mode == "spawn":
            raise OSError("worker unavailable")
        return _OneShotFailureProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    with pytest.raises(error_type):
        await live_runner.predict(image)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure_mode", "error_fragment"),
    [
        ("timeout", "timed out"),
        ("spawn", "spawn failed"),
        ("nonzero", "Worker exited"),
        ("bad_json", "Bad JSON"),
    ],
)
async def test_shadow_one_shot_infrastructure_failures_remain_abstentions(
    runner: OCSRRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure_mode: str,
    error_fragment: str,
) -> None:
    image = tmp_path / "img.png"
    image.write_bytes(b"fake")

    class _OneShotFailureProcess:
        returncode = 7 if failure_mode == "nonzero" else 0

        async def communicate(self) -> tuple[bytes, bytes]:
            if failure_mode == "timeout":
                raise TimeoutError
            if failure_mode == "bad_json":
                return b"not-json", b""
            return b"", b"worker failed"

    async def fake_create(*_args: Any, **_kwargs: Any) -> _OneShotFailureProcess:
        if failure_mode == "spawn":
            raise OSError("worker unavailable")
        return _OneShotFailureProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    result = await runner.predict(image)

    assert result.valid is False
    assert error_fragment in result.error


@pytest.mark.asyncio
async def test_live_persistent_bad_json_raises_typed_output_error(
    fake_venv: Path,
    fake_worker: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image = tmp_path / "img.png"
    image.write_bytes(b"fake")
    proc = _FakeProcess(stdout_lines=[b"not-json\n"])
    live_runner = OCSRRunner(
        venv_path=fake_venv,
        worker_script=fake_worker,
        tool_name="fake",
        fail_closed=True,
    )

    async def fake_create(*_args: Any, **_kwargs: Any) -> _FakeProcess:
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    await live_runner.start()

    with pytest.raises(OCSROutputError):
        await live_runner.predict_persistent(image)

    live_runner._persistent_process = None


# ---------------------------------------------------------------------------
# Tests: stop / context manager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_sends_empty_line_and_awaits(
    runner: OCSRRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = _FakeProcess()
    # Simulate worker exiting cleanly when stdin closes.
    proc.mark_exited(0)

    async def fake_create(*args: Any, **kwargs: Any) -> _FakeProcess:
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    await runner.start()
    await runner.stop()

    # Empty newline was written before close.
    assert proc.stdin.writes == [b"\n"]
    assert proc.stdin.is_closing()
    assert runner._persistent_process is None
    # Clean shutdown path — terminate() not needed.
    assert proc.terminated is False
    assert proc.killed is False


@pytest.mark.asyncio
async def test_stop_falls_back_to_terminate_on_timeout(
    runner: OCSRRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = _NeverExitingProcess()

    async def fake_create(*args: Any, **kwargs: Any) -> _NeverExitingProcess:
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    # Patch asyncio.wait_for to short-circuit the graceful-wait timeout
    # so the test doesn't sit for 5 seconds.
    real_wait_for = asyncio.wait_for

    async def fast_wait_for(aw: Any, timeout: float) -> Any:
        # For the graceful-shutdown wait, fail immediately. Keep the
        # short terminate/kill waits real so the process state updates
        # after terminate() fires the event.
        return await real_wait_for(aw, timeout=0.05)

    monkeypatch.setattr(asyncio, "wait_for", fast_wait_for)

    await runner.start()
    await runner.stop()

    assert proc.terminated is True
    assert runner._persistent_process is None


@pytest.mark.asyncio
async def test_context_manager_starts_and_stops(
    runner: OCSRRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    image = tmp_path / "img.png"
    image.write_bytes(b"fake")

    class _StdinClosingProc(_FakeProcess):
        """Exits cleanly as soon as its stdin is closed — mimics a real
        worker that breaks out of its read loop on empty line / EOF."""

    proc = _StdinClosingProc(stdout_lines=[_ok_payload("CCO")])

    # Wire stdin.close → process exits cleanly.
    original_close = proc.stdin.close

    def _close_and_exit() -> None:
        original_close()
        proc.mark_exited(0)

    proc.stdin.close = _close_and_exit  # type: ignore[method-assign]

    async def fake_create(*args: Any, **kwargs: Any) -> _FakeProcess:
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    async with runner as r:
        assert r is runner
        assert r._persistent_process is proc
        result = await r.predict(image)
        assert result.smiles == "CCO"

    # Context exit must have stopped the worker.
    assert runner._persistent_process is None
    # Empty line sent before close; stdin is closed.
    assert b"\n" in proc.stdin.writes
    assert proc.stdin.is_closing()


@pytest.mark.asyncio
async def test_start_is_idempotent(runner: OCSRRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    spawns: list[int] = []

    async def fake_create(*args: Any, **kwargs: Any) -> _FakeProcess:
        spawns.append(1)
        return _FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    await runner.start()
    await runner.start()  # Second call should be a no-op.
    assert len(spawns) == 1

    runner._persistent_process = None


@pytest.mark.asyncio
async def test_stop_when_not_started_is_noop(runner: OCSRRunner) -> None:
    # Should not raise — just returns.
    await runner.stop()
    assert runner._persistent_process is None
