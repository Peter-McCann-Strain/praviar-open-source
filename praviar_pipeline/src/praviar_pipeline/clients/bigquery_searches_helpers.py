"""Pure helpers for building BigQuery search query fragments."""

from __future__ import annotations

import re


def build_regex_pattern(values: list[str]) -> str | None:
    """Build a lowercased regex alternation pattern from search values."""
    escaped = [
        re.escape(normalized.lower()) for value in values if value and (normalized := value.strip())
    ]
    if not escaped:
        return None
    return "(" + "|".join(escaped) + ")"


def build_or_clause(conditions: list[str], *, prefix: str = "", suffix: str = "") -> str:
    """Format a list of OR conditions as a clause fragment."""
    if not conditions:
        return ""
    return f"{prefix}(" + " OR ".join(conditions) + f"){suffix}"
