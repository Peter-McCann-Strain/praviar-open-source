"""Runner-construction helpers for drawing analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from pathlib import Path

    from praviar_pipeline.config import Settings


# Canonical set of segmentation backends supported by the pipeline. Mirrors
# the Literal in ``Settings.drawing_segmentation_tool``. Used to distinguish
# "the user picked something the pipeline doesn't know about" (raise loudly,
# user error) from "the dispatch table is missing this backend"
# (configuration drift — also loud, but a different message).
_SUPPORTED_SEGMENTATION_BACKENDS: frozenset[str] = frozenset({"decimer", "moldet", "chemsam"})


def get_runners(
    tool_names: list[str],
    settings: Settings,
    *,
    tool_configs: dict[str, dict[str, Any]],
    logger,
    runner_cls,
    fail_closed: bool = False,
) -> dict[str, Any]:
    """Create OCSR runners for the specified tools."""
    runners: dict[str, Any] = {}
    for tool in tool_names:
        config = tool_configs.get(tool)
        if not config:
            if fail_closed:
                raise RuntimeError(f"Drawing OCSR tool has no registered config: {tool}")
            logger.warning("drawing_unknown_tool", tool=tool)
            continue

        venv = config["venv"]
        if not (venv / "bin" / "python").exists():
            if fail_closed:
                raise RuntimeError(f"Drawing OCSR tool venv missing for {tool}: {venv}")
            logger.warning("drawing_tool_venv_missing", tool=tool)
            continue

        setup_failed = False
        try:
            runners[tool] = runner_cls(
                venv_path=venv,
                worker_script=config["worker"],
                timeout_s=settings.drawing_timeout_per_patent_s,
                tool_name=tool,
                env_vars=config.get("env", {}),
                fail_closed=fail_closed,
            )
        except FileNotFoundError as exc:
            setup_failed = True
            logger.warning(
                "drawing_tool_setup_failed",
                tool=tool,
                error_type=safe_exception_type(exc),
            )
        if setup_failed and fail_closed:
            raise RuntimeError(f"Drawing OCSR tool setup failed for {tool}") from None

    return runners


def get_segmentation_runner(
    *,
    backend: str,
    backends: dict[str, dict[str, Path]],
    logger,
    runner_cls,
    fail_closed: bool = False,
):
    """Create the segmentation runner for the requested backend.

    Multi-backend segmentation dispatch:
        - ``backend`` must be one of the values declared by
          ``Settings.drawing_segmentation_tool`` (``decimer`` / ``moldet`` /
          ``chemsam``). Anything else is a user-config error and we raise
          ``ValueError`` with an "Unsupported" message.
        - ``backends`` is the registered dispatch table (typically
          ``SEGMENTATION_BACKENDS`` from ``tooling.py``). If the canonical
          backend isn't in it, that's configuration drift — also a
          ``ValueError`` but with a different "No configuration registered"
          message so the failure mode is unambiguous.
        - If the backend's venv isn't installed, shadow/internal runs log and
          return ``None``. Live drawing-evidence runs fail closed.
    """
    if backend not in _SUPPORTED_SEGMENTATION_BACKENDS:
        raise ValueError(f"Unsupported segmentation backend: {backend}")

    cfg = backends.get(backend)
    if cfg is None:
        raise ValueError(f"No configuration registered for backend: {backend}")

    venv = cfg["venv"]
    worker = cfg["worker"]

    if not (venv / "bin" / "python").exists():
        if fail_closed:
            raise RuntimeError(f"Segmentation venv missing for {backend}: {venv}")
        logger.warning("segmentation_venv_missing", backend=backend)
        return None

    setup_failed = False
    try:
        runner = runner_cls(venv_path=venv, worker_script=worker)
    except FileNotFoundError as exc:
        setup_failed = True
        logger.warning(
            "segmentation_setup_failed",
            backend=backend,
            error_type=safe_exception_type(exc),
        )
        runner = None
    if setup_failed and fail_closed:
        raise RuntimeError(f"Segmentation setup failed for {backend}") from None
    return runner
