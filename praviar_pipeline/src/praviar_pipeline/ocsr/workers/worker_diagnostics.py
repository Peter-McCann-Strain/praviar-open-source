"""Stable secret-safe diagnostics for isolated OCSR worker protocols."""

from __future__ import annotations

import re

_SAFE_TYPE_PATTERN = re.compile(r"[^A-Za-z0-9_.-]")
_MAX_TYPE_LENGTH = 80


def safe_exception_type(error: BaseException) -> str:
    """Return a bounded exception class without inspecting exception text."""
    raw_name = type(error).__name__
    safe_name = _SAFE_TYPE_PATTERN.sub("_", raw_name)[:_MAX_TYPE_LENGTH]
    return safe_name or "Exception"


def safe_worker_error(operation: str, error: BaseException) -> str:
    """Return a fixed worker failure message containing only the error type."""
    return f"{operation} failed ({safe_exception_type(error)})"


SUPPRESSED_DEPENDENCY_OUTPUT = "Dependency output suppressed by worker boundary"
