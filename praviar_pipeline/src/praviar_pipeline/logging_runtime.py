"""Runtime logging primitives for pipeline steps and concurrent progress."""

from __future__ import annotations

import time
from typing import Any

import structlog

_SAFE_EXTRA_FIELDS = frozenset(
    {
        "analyses_in",
        "error_type",
        "items",
        "patents_in",
        "risk_level",
        "total_duration_s",
    }
)


def _safe_extra(extra: dict[str, Any]) -> dict[str, Any]:
    """Allow only explicitly non-confidential progress/timing metadata."""
    return {key: value for key, value in extra.items() if key in _SAFE_EXTRA_FIELDS}


class StepTimer:
    """Context manager that logs step start/complete with duration."""

    def __init__(self, step_name: str, **extra: Any) -> None:
        self.step_name = step_name
        self.extra = _safe_extra(extra)
        self.start_time = 0.0
        self.duration_s = 0.0
        self._logger = structlog.get_logger()

    def __enter__(self) -> StepTimer:
        structlog.contextvars.bind_contextvars(step=self.step_name)
        self.start_time = time.monotonic()
        self._logger.info(f"{self.step_name}_start", **self.extra)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.duration_s = round(time.monotonic() - self.start_time, 2)
        if exc_type:
            self._logger.error(
                f"{self.step_name}_failed",
                duration_s=self.duration_s,
                error_type=exc_type.__name__,
                **self.extra,
            )
        else:
            self._logger.info(
                f"{self.step_name}_complete",
                duration_s=self.duration_s,
                **self.extra,
            )


class ProgressTracker:
    """Track progress of concurrent operations with ETA."""

    def __init__(self, total: int, operation: str) -> None:
        self.total = total
        self.completed = 0
        self.failed = 0
        self.operation = operation
        self._start = time.monotonic()
        self._logger = structlog.get_logger()

    def mark_complete(self, *, success: bool = True, **extra: Any) -> None:
        """Mark one item complete. Thread-safe for asyncio under the GIL."""
        if success:
            self.completed += 1
        else:
            self.failed += 1

        done = self.completed + self.failed
        elapsed = time.monotonic() - self._start
        rate = done / elapsed if elapsed > 0 else 0
        remaining = self.total - done
        eta_s = remaining / rate if rate > 0 else None

        self._logger.info(
            f"{self.operation}_progress",
            done=done,
            total=self.total,
            completed=self.completed,
            failed=self.failed,
            pct=round(100 * done / self.total, 1) if self.total > 0 else 0,
            elapsed_s=round(elapsed, 1),
            eta_s=round(eta_s, 1) if eta_s else None,
            **_safe_extra(extra),
        )
