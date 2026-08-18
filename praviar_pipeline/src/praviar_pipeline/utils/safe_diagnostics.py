"""Secret-safe diagnostics for external and asynchronous failure boundaries."""

from __future__ import annotations

import re

_SAFE_TYPE_PATTERN = re.compile(r"[^A-Za-z0-9_.-]")
_MAX_TYPE_LENGTH = 80


def safe_exception_type(error: BaseException) -> str:
    """Return a bounded class-name diagnostic without inspecting exception text."""
    raw_name = type(error).__name__
    safe_name = _SAFE_TYPE_PATTERN.sub("_", raw_name)[:_MAX_TYPE_LENGTH]
    return safe_name or "Exception"


def safe_failure_message(operation: str, error: BaseException) -> str:
    """Build a fixed-operation diagnostic containing only the exception class."""
    return f"{operation} failed ({safe_exception_type(error)})"
