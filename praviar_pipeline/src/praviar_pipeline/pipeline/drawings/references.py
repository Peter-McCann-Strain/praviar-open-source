"""Figure and formula reference parsing helpers for drawing analysis."""

from __future__ import annotations

import re
from contextlib import suppress

FIGURE_REF_PATTERNS = [
    re.compile(r"(?:FIG(?:URE)?\.?\s*(\d+[A-Za-z]?))", re.IGNORECASE),
    re.compile(r"(?:Formula\s+([IVXLCDM]+|\d+[A-Za-z]?))", re.IGNORECASE),
    re.compile(
        r"(?:Compound\s+(?:of\s+)?(?:the\s+)?(?:general\s+)?[Ff]ormula\s+([IVXLCDM]+|\d+))",
        re.IGNORECASE,
    ),
    re.compile(r"(?:Structure\s+([IVXLCDM]+|\d+[A-Za-z]?))", re.IGNORECASE),
    re.compile(r"(?:Scheme\s+(\d+[A-Za-z]?))", re.IGNORECASE),
]


def cross_check_figure_references(patent_text: str, pages_fetched: int) -> list[str]:
    """Parse patent text for figure references and flag gaps."""
    if not patent_text:
        return []

    referenced_figures: set[str] = set()
    for pattern in FIGURE_REF_PATTERNS:
        for match in pattern.finditer(patent_text):
            referenced_figures.add(match.group(1))

    if not referenced_figures:
        return []

    numeric_refs = set()
    for reference in referenced_figures:
        with suppress(ValueError):
            numeric_refs.add(int(reference))

    gaps = []
    for figure_number in sorted(numeric_refs):
        if figure_number > pages_fetched:
            gaps.append(
                f"Figure {figure_number} referenced in claims but only "
                f"{pages_fetched} drawing pages were fetched"
            )

    return gaps
