"""Subprocess runner for isolated OCSR tool invocation.

Each OCSR tool lives in its own virtual environment with potentially
incompatible dependencies (different torch, numpy, tensorflow versions).
This module provides a uniform async interface that spawns the tool's
Python interpreter as a subprocess, passes image paths, and parses
structured JSON output.

Usage:
    runner = OCSRRunner(
        venv_path=Path("praviar_pipeline/venvs/molscribe"),
        worker_script=Path("praviar_pipeline/src/praviar_pipeline/ocsr/workers/molscribe_worker.py"),
    )
    result = await runner.predict(Path("/tmp/structure.png"))
    print(result.smiles, result.confidence)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import cast

import structlog

from praviar_pipeline.models.drawing import Doc2SARResult, OCSRResult, SegmentationResult
from praviar_pipeline.utils.private_artifacts import enforce_private_file, ensure_private_directory
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

logger = structlog.get_logger()

_WORKER_ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "HOME",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "PYTHONPATH",
        "CUDA_VISIBLE_DEVICES",
        "PYTORCH_ENABLE_MPS_FALLBACK",
        "HF_HOME",
        "TRANSFORMERS_CACHE",
        "TORCH_HOME",
        "XDG_CACHE_HOME",
        "PRAVIAR_ML_BOM_PATH",
        "PRAVIAR_MARKUSHGRAPHER_ALLOW_NO_OCR",
        "MOLSCRIBE_ROOT",
        "MOLSCRIBE_CKPT",
        "MOLSIGHT_ROOT",
        "MOLSIGHT_CKPT",
        "MOLSIGHT_LORA",
        "MOLSIGHT_FORMATS",
        "MOLPARSER_ROOT",
        "MOLPARSER_CKPT",
        "DOC2SAR_ROOT",
        "DOC2SAR_CKPT",
        "DOC2SAR_MAX_ENUMERATIONS",
        "MOLCLASSIFIER_CKPT",
        "MOLCLASSIFIER_DEVICE",
        "MOLCLASSIFIER_BOX_THRESH",
        "MOLCLASSIFIER_NC_MIN_CONF",
        "CHEMSAM_CKPT",
        "CHEMSAM_MODEL_TYPE",
        "CHEMSAM_DEVICE",
        "MOLDET_CKPT",
        "MOLDET_BOX_THRESH",
        "MOLDET_MAX_DETECTIONS",
    }
)


def _safe_worker_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Return the minimal documented environment OCSR workers may inherit."""
    import os

    env = {key: value for key, value in os.environ.items() if key in _WORKER_ENV_ALLOWLIST}
    for key, value in (overrides or {}).items():
        if key in _WORKER_ENV_ALLOWLIST:
            env[key] = value
    return env


def _output_digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class SegmentationError(RuntimeError):
    """Raised by SegmentationRunner.segment when segmentation cannot complete.

    Segmentation failures raise explicit exceptions so the cascade reports
    honest "this page failed detection" outcomes rather than masquerading as
    "0 chemical structures found."
    """


class SegmentationTimeoutError(SegmentationError):
    """The DECIMER subprocess took longer than the configured timeout."""


class SegmentationSpawnError(SegmentationError):
    """OS failed to spawn the subprocess (missing venv, permissions, etc)."""


class SegmentationOutputError(SegmentationError):
    """Worker exited or produced output that isn't valid SegmentationResult JSON."""


class OCSRExecutionError(RuntimeError):
    """Base class for OCSR infrastructure failures in live influence mode."""


class OCSRTimeoutError(OCSRExecutionError):
    """The OCSR worker exceeded the configured prediction timeout."""


class OCSRSpawnError(OCSRExecutionError):
    """The operating system could not start an OCSR worker."""


class OCSRWorkerExitError(OCSRExecutionError):
    """An OCSR worker exited or closed its transport before returning output."""


class OCSROutputError(OCSRExecutionError):
    """An OCSR worker returned output that violates its JSON contract."""


class OCSRRunner:
    """Run any OCSR tool in its isolated venv via subprocess."""

    def __init__(
        self,
        venv_path: Path,
        worker_script: Path,
        timeout_s: float = 120.0,
        tool_name: str = "",
        env_vars: dict[str, str] | None = None,
        fail_closed: bool = False,
    ) -> None:
        self.python = venv_path / "bin" / "python"
        self.worker = worker_script
        self.timeout = timeout_s
        self.tool_name = tool_name or venv_path.name
        self.env_vars = env_vars or {}
        self.fail_closed = fail_closed
        self._persistent_process: asyncio.subprocess.Process | None = None

        if not self.python.exists():
            raise FileNotFoundError(
                f"Python interpreter not found at {self.python}. "
                f"Create the venv first: python3 -m venv {venv_path}"
            )
        if not self.worker.exists():
            raise FileNotFoundError(f"Worker script not found at {self.worker}")

    def _subprocess_env(self) -> dict[str, str]:
        return _safe_worker_env(self.env_vars)

    def _validate_worker_result(self, data: object) -> OCSRResult | Doc2SARResult:
        """Validate against the registered worker's exact output contract."""
        if self.tool_name == "doc2sar":
            return Doc2SARResult.model_validate(data)
        return OCSRResult.model_validate(data)

    async def __aenter__(self) -> OCSRRunner:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()

    async def start(self) -> None:
        """Start a persistent worker process for tools that support stdin mode."""
        if self._persistent_process is not None:
            return

        spawn_failure_type: str | None = None
        try:
            self._persistent_process = await asyncio.create_subprocess_exec(
                str(self.python),
                str(self.worker),
                "predict",
                "--persistent",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._subprocess_env(),
            )
        except OSError as exc:
            spawn_failure_type = safe_exception_type(exc)
            logger.error(
                "ocsr_persistent_spawn_failed",
                tool=self.tool_name,
                error_type=spawn_failure_type,
            )
        if spawn_failure_type is not None:
            raise OCSRSpawnError("Persistent OCSR worker spawn failed") from None

    async def stop(self) -> None:
        """Terminate a persistent worker process if one is running."""
        proc = self._persistent_process
        self._persistent_process = None
        if proc is None:
            return

        stdin = getattr(proc, "stdin", None)
        if stdin is not None and not getattr(stdin, "is_closing", lambda: False)():
            try:
                stdin.write(b"\n")
                await stdin.drain()
            except (BrokenPipeError, OSError):
                pass
            finally:
                stdin.close()

        if getattr(proc, "returncode", None) is None:
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except TimeoutError:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except TimeoutError:
                    proc.kill()
                    await proc.wait()

    async def predict_persistent(self, image_path: Path) -> OCSRResult | Doc2SARResult:
        """Run prediction through a started persistent worker process."""
        if not image_path.exists():
            return OCSRResult(
                tool=self.tool_name,
                error="Image not found",
            )
        if self._persistent_process is None:
            raise RuntimeError("Persistent OCSR worker is not running")

        proc = self._persistent_process
        returncode = getattr(proc, "returncode", None)
        if returncode is not None:
            stderr = b""
            stderr_pipe = getattr(proc, "stderr", None)
            if stderr_pipe is not None:
                try:
                    stderr = await stderr_pipe.read()
                except (OSError, AttributeError):
                    stderr = b""
            raise OCSRWorkerExitError(
                "Persistent OCSR worker has exited "
                f"(code={returncode}, stderr_sha256={_output_digest(stderr)})"
            )

        stdin = getattr(proc, "stdin", None)
        stdout = getattr(proc, "stdout", None)
        if stdin is None or stdout is None:
            raise OCSRWorkerExitError("Persistent OCSR worker pipes are unavailable")

        t0 = time.monotonic()
        try:
            stdin.write(str(image_path).encode() + b"\n")
            await stdin.drain()
            line = await asyncio.wait_for(stdout.readline(), timeout=self.timeout)
        except TimeoutError as exc:
            logger.error(
                "ocsr_persistent_prediction_failed",
                tool=self.tool_name,
                error_type=safe_exception_type(exc),
            )
            raise OCSRTimeoutError("Persistent OCSR prediction timed out") from None
        except (BrokenPipeError, OSError) as exc:
            logger.error(
                "ocsr_persistent_prediction_failed",
                tool=self.tool_name,
                error_type=safe_exception_type(exc),
            )
            raise OCSRWorkerExitError("Persistent OCSR prediction failed") from None

        if not line:
            stderr = b""
            stderr_pipe = getattr(proc, "stderr", None)
            if stderr_pipe is not None:
                try:
                    stderr = await stderr_pipe.read()
                except (OSError, AttributeError):
                    stderr = b""
            raise OCSRWorkerExitError(
                f"Persistent OCSR worker closed stdout (stderr_sha256={_output_digest(stderr)})"
            )

        try:
            result = self._validate_worker_result(json.loads(line.decode()))
            result.tool = self.tool_name
            result.latency_ms = int((time.monotonic() - t0) * 1000)
            if result.error:
                result.error = "Worker prediction failed"
            return result
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error(
                "ocsr_persistent_bad_output",
                tool=self.tool_name,
                output_sha256=_output_digest(line),
                error_type=safe_exception_type(exc),
            )
            if self.fail_closed:
                raise OCSROutputError("Persistent OCSR worker returned invalid output") from None
            return OCSRResult(
                tool=self.tool_name,
                error="Bad JSON output from persistent worker",
                latency_ms=int((time.monotonic() - t0) * 1000),
            )

    async def predict(self, image_path: Path) -> OCSRResult:
        """Run OCSR prediction on a single image.

        Args:
            image_path: Path to a PNG/TIFF image of a chemical structure.

        Returns:
            OCSRResult with SMILES, confidence, validity, timing.
        """
        if not image_path.exists():
            return OCSRResult(
                tool=self.tool_name,
                error="Image not found",
            )

        if self._persistent_process is not None:
            if getattr(self._persistent_process, "returncode", None) is None:
                try:
                    return cast("OCSRResult", await self.predict_persistent(image_path))
                except RuntimeError as exc:
                    logger.warning(
                        "ocsr_persistent_failed_falling_back",
                        tool=self.tool_name,
                        error_type=safe_exception_type(exc),
                    )
                    self._persistent_process = None
            else:
                self._persistent_process = None

        t0 = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                str(self.python),
                str(self.worker),
                "predict",
                str(image_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._subprocess_env(),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        except TimeoutError:
            logger.error(
                "ocsr_subprocess_timeout",
                tool=self.tool_name,
                image=str(image_path),
                timeout_s=self.timeout,
            )
            if self.fail_closed:
                raise OCSRTimeoutError("OCSR subprocess timed out") from None
            return OCSRResult(
                tool=self.tool_name,
                error=f"Subprocess timed out after {self.timeout}s",
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
        except OSError as exc:
            logger.error(
                "ocsr_subprocess_spawn_failed",
                tool=self.tool_name,
                error_type=safe_exception_type(exc),
            )
            if self.fail_closed:
                raise OCSRSpawnError("OCSR subprocess spawn failed") from None
            return OCSRResult(tool=self.tool_name, error="Subprocess spawn failed")

        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if proc.returncode != 0:
            stderr_digest = _output_digest(stderr)
            logger.error(
                "ocsr_subprocess_failed",
                tool=self.tool_name,
                returncode=proc.returncode,
                stderr_sha256=stderr_digest,
            )
            if self.fail_closed:
                raise OCSRWorkerExitError("OCSR worker exited unsuccessfully") from None
            return OCSRResult(
                tool=self.tool_name,
                error=(f"Worker exited (code={proc.returncode}, stderr_sha256={stderr_digest})"),
                latency_ms=elapsed_ms,
            )

        try:
            # Parse last JSON line — some workers print debug lines before JSON
            raw_out = stdout.decode().strip()
            data = None
            for line in reversed(raw_out.split("\n")):
                line = line.strip()
                if line.startswith("{"):
                    data = json.loads(line)
                    break
            if data is None:
                data = json.loads(raw_out)
            result = self._validate_worker_result(data)
            result.latency_ms = elapsed_ms
            result.tool = self.tool_name
            if result.error:
                result.error = "Worker prediction failed"
            return cast("OCSRResult", result)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error(
                "ocsr_subprocess_bad_output",
                tool=self.tool_name,
                output_sha256=_output_digest(stdout),
                error_type=safe_exception_type(exc),
            )
            if self.fail_closed:
                raise OCSROutputError("OCSR worker returned invalid output") from None
            return OCSRResult(
                tool=self.tool_name,
                error="Bad JSON output",
                latency_ms=elapsed_ms,
            )

    async def predict_batch(self, image_paths: list[Path]) -> list[OCSRResult]:
        """Run predictions on multiple images sequentially.

        Subprocess cold-start is per-call, so batching doesn't help
        unless the worker supports batch mode (future optimisation).
        """
        return [await self.predict(p) for p in image_paths]


class SegmentationRunner:
    """Run DECIMER Segmentation in its isolated venv via subprocess."""

    def __init__(
        self,
        venv_path: Path,
        worker_script: Path,
        timeout_s: float = 180.0,
    ) -> None:
        self.python = venv_path / "bin" / "python"
        self.worker = worker_script
        self.timeout = timeout_s

        if not self.python.exists():
            raise FileNotFoundError(
                f"Python interpreter not found at {self.python}. "
                f"Create the venv first: python3 -m venv {venv_path}"
            )

    async def segment(self, page_image_path: Path, output_dir: Path) -> list[SegmentationResult]:
        """Find and crop chemical structures from a patent page image.

        Args:
            page_image_path: Full patent page image.
            output_dir: Directory to save cropped segment images.

        Returns:
            List of SegmentationResult with bounding boxes and paths.
        """
        ensure_private_directory(output_dir)

        failure_kind: str | None = None
        failure_type: str | None = None
        try:
            proc = await asyncio.create_subprocess_exec(
                str(self.python),
                str(self.worker),
                "segment",
                str(page_image_path),
                str(output_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=_safe_worker_env(),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        except TimeoutError as exc:
            failure_kind = "timeout"
            failure_type = safe_exception_type(exc)
            logger.error(
                "segmentation_timeout",
                timeout_s=self.timeout,
                error_type=failure_type,
            )
        except OSError as exc:
            failure_kind = "spawn"
            failure_type = safe_exception_type(exc)
            logger.error(
                "segmentation_spawn_failed",
                error_type=failure_type,
            )
        if failure_kind == "timeout":
            raise SegmentationTimeoutError(
                f"Segmentation timed out after {self.timeout}s"
            ) from None
        if failure_kind == "spawn":
            raise SegmentationSpawnError("Could not spawn segmentation subprocess") from None

        if proc.returncode != 0:
            stderr_digest = _output_digest(stderr)
            logger.error(
                "segmentation_failed",
                returncode=proc.returncode,
                stderr_sha256=stderr_digest,
            )
            raise SegmentationOutputError(
                f"Segmentation worker exited (code={proc.returncode}, "
                f"stderr_sha256={stderr_digest})"
            )

        parse_failure_type: str | None = None
        try:
            data = json.loads(stdout.decode())
            results = [SegmentationResult.model_validate(item) for item in data]
            for result in results:
                if result.error:
                    result.error = "Segmentation worker failed"
                if result.image_path:
                    segment_path = Path(result.image_path).resolve(strict=True)
                    if not segment_path.is_relative_to(output_dir.resolve(strict=True)):
                        raise ValueError("Segmentation worker output escaped private directory")
                    enforce_private_file(segment_path)
            return results
        except (json.JSONDecodeError, ValueError) as exc:
            parse_failure_type = safe_exception_type(exc)
            logger.error(
                "segmentation_bad_output",
                output_sha256=_output_digest(stdout),
                error_type=parse_failure_type,
            )
        if parse_failure_type is not None:
            raise SegmentationOutputError(
                "Segmentation worker produced unparseable output"
            ) from None
        raise AssertionError("segmentation result parsing reached an unreachable state")
