from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from praviar_pipeline.pipeline.drawings.factories import get_runners, get_segmentation_runner

if TYPE_CHECKING:
    from pathlib import Path


class _Logger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def warning(self, event: str, **kwargs) -> None:
        self.events.append((event, kwargs))


def _prepare_venv(tmp_path: Path, name: str) -> Path:
    venv = tmp_path / name
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").write_text("", encoding="utf-8")
    return venv


def test_get_runners_skips_unknown_and_missing_venvs(tmp_path: Path) -> None:
    logger = _Logger()
    settings = SimpleNamespace(drawing_timeout_per_patent_s=12)
    ready_venv = _prepare_venv(tmp_path, "ready")
    missing_venv = tmp_path / "missing"

    tool_configs = {
        "ready": {"venv": ready_venv, "worker": tmp_path / "ready.py", "env": {"X": "1"}},
        "missing": {"venv": missing_venv, "worker": tmp_path / "missing.py", "env": {}},
    }
    created: list[dict] = []

    def _runner_cls(**kwargs):
        created.append(kwargs)
        return kwargs["tool_name"]

    result = get_runners(
        ["ready", "missing", "unknown"],
        settings,
        tool_configs=tool_configs,
        logger=logger,
        runner_cls=_runner_cls,
    )

    assert result == {"ready": "ready"}
    assert created == [
        {
            "venv_path": ready_venv,
            "worker_script": tmp_path / "ready.py",
            "timeout_s": 12,
            "tool_name": "ready",
            "env_vars": {"X": "1"},
            "fail_closed": False,
        }
    ]
    assert [event for event, _ in logger.events] == [
        "drawing_tool_venv_missing",
        "drawing_unknown_tool",
    ]


def test_get_runners_threads_live_failure_policy_into_workers(tmp_path: Path) -> None:
    ready_venv = _prepare_venv(tmp_path, "ready")
    created: list[dict] = []

    get_runners(
        ["ready"],
        SimpleNamespace(drawing_timeout_per_patent_s=12),
        tool_configs={
            "ready": {
                "venv": ready_venv,
                "worker": tmp_path / "ready.py",
                "env": {},
            }
        },
        logger=_Logger(),
        runner_cls=lambda **kwargs: created.append(kwargs) or object(),
        fail_closed=True,
    )

    assert created[0]["fail_closed"] is True


def test_get_runners_swallows_runner_setup_errors(tmp_path: Path) -> None:
    logger = _Logger()
    settings = SimpleNamespace(drawing_timeout_per_patent_s=12)
    ready_venv = _prepare_venv(tmp_path, "ready")
    tool_configs = {"ready": {"venv": ready_venv, "worker": tmp_path / "ready.py", "env": {}}}

    sentinel = "drawing-worker-path-sentinel"

    def _runner_cls(**kwargs):
        raise FileNotFoundError(f"{kwargs['tool_name']}:{sentinel}")

    result = get_runners(
        ["ready"],
        settings,
        tool_configs=tool_configs,
        logger=logger,
        runner_cls=_runner_cls,
    )

    assert result == {}
    assert logger.events == [
        (
            "drawing_tool_setup_failed",
            {"tool": "ready", "error_type": "FileNotFoundError"},
        )
    ]
    assert sentinel not in repr(logger.events)


def test_get_segmentation_runner_returns_none_for_missing_venv(tmp_path: Path) -> None:
    logger = _Logger()
    backends = {
        "decimer": {
            "venv": tmp_path / "missing",
            "worker": tmp_path / "worker.py",
        },
    }
    result = get_segmentation_runner(
        backend="decimer",
        backends=backends,
        logger=logger,
        runner_cls=lambda **kwargs: kwargs,
    )
    assert result is None
    assert logger.events == [
        (
            "segmentation_venv_missing",
            {"backend": "decimer"},
        ),
    ]


def test_get_segmentation_runner_swallows_runner_setup_errors(tmp_path: Path) -> None:
    logger = _Logger()
    ready_venv = _prepare_venv(tmp_path, "ready")

    sentinel = "segmentation-worker-path-sentinel"

    def _runner_cls(**kwargs):
        raise FileNotFoundError(f"segmentation:{sentinel}")

    backends = {
        "decimer": {
            "venv": ready_venv,
            "worker": tmp_path / "worker.py",
        },
    }
    result = get_segmentation_runner(
        backend="decimer",
        backends=backends,
        logger=logger,
        runner_cls=_runner_cls,
    )
    assert result is None
    assert logger.events == [
        (
            "segmentation_setup_failed",
            {"backend": "decimer", "error_type": "FileNotFoundError"},
        ),
    ]
    assert sentinel not in repr(logger.events)


def test_factory_dispatches_decimer(tmp_path: Path) -> None:
    """Multi-backend dispatch: ``backend='decimer'`` selects the
    DECIMER venv/worker pair and returns a constructed runner."""
    decimer_venv = _prepare_venv(tmp_path, "decimer")
    moldet_venv = _prepare_venv(tmp_path, "moldet")
    captured: dict = {}

    def _runner_cls(**kwargs):
        captured.update(kwargs)
        return kwargs

    backends = {
        "decimer": {
            "venv": decimer_venv,
            "worker": tmp_path / "decimer_seg_worker.py",
        },
        "moldet": {
            "venv": moldet_venv,
            "worker": tmp_path / "moldet_seg_worker.py",
        },
    }

    result = get_segmentation_runner(
        backend="decimer",
        backends=backends,
        logger=_Logger(),
        runner_cls=_runner_cls,
    )

    assert result is not None
    assert captured["venv_path"] == decimer_venv
    assert captured["worker_script"] == tmp_path / "decimer_seg_worker.py"


def test_factory_dispatches_moldet(tmp_path: Path) -> None:
    """Multi-backend dispatch: ``backend='moldet'`` selects the
    MolDet venv/worker pair (opt-in YOLO11l detector)."""
    decimer_venv = _prepare_venv(tmp_path, "decimer")
    moldet_venv = _prepare_venv(tmp_path, "moldet")
    captured: dict = {}

    def _runner_cls(**kwargs):
        captured.update(kwargs)
        return kwargs

    backends = {
        "decimer": {
            "venv": decimer_venv,
            "worker": tmp_path / "decimer_seg_worker.py",
        },
        "moldet": {
            "venv": moldet_venv,
            "worker": tmp_path / "moldet_seg_worker.py",
        },
    }

    result = get_segmentation_runner(
        backend="moldet",
        backends=backends,
        logger=_Logger(),
        runner_cls=_runner_cls,
    )

    assert result is not None
    assert captured["venv_path"] == moldet_venv
    assert captured["worker_script"] == tmp_path / "moldet_seg_worker.py"
