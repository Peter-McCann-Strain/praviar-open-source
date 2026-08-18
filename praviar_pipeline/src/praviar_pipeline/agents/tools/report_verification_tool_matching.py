"""Normalization helpers for report verification tools."""

from __future__ import annotations


def normalize_assignee(name: str) -> str:
    """Normalize an assignee name for fuzzy comparison."""
    normalized = name.lower().strip()
    for suffix in [
        " inc.",
        " inc",
        " corp.",
        " corp",
        " ltd.",
        " ltd",
        " llc",
        " plc",
        " s.a.",
        " ag",
        " gmbh",
        " co.",
        " company",
        " corporation",
        " incorporated",
        " limited",
        ",",
        ".",
    ]:
        normalized = normalized.replace(suffix, "")
    return normalized.strip()
