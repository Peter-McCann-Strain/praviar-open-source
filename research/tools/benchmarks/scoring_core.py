"""Shared scoring primitives for research benchmark tooling.

Houses the deterministic regex-based extractors and patent-ID normalization
that were previously duplicated between:
  - research/experiments/optimization/report_scorer.py
  - research/tools/benchmarks/enrich_ground_truth.py
  - (intent) research/tools/benchmarks/benchmark_scorer.py — kept dict-driven,
    so it does not need text extraction; it imports normalize_patent_id only.

This module is research-only. It must NOT be imported from praviar_pipeline runtime
code (api/, web/, praviar_pipeline/src). The opposite direction is fine: research
tooling may import praviar_pipeline, but praviar_pipeline runtime must not import research.

Public API:
    extract_patent_ids(text)        -> list[str]    (normalized, de-duplicated, ordered)
    extract_risk_level(text)        -> str | None   (lowercase: high|medium|low|clear)
    extract_claim_numbers(text)     -> list[int]    (sorted, de-duplicated)
    extract_section_headers(text)   -> list[str]    (lowercase, ordered)
    normalize_patent_id(pid)        -> str          (uppercase, no separators, no kind code)

These mirror the previous private `_extract_*` helpers but return list types
(stable iteration order is convenient for callers and tests). The previous
`set` callers can wrap with `set(...)` if they relied on hash-based membership.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Regex constants
# ---------------------------------------------------------------------------

# Country-prefixed patent IDs (US, EP, WO, CN, JP, KR, IN, CA, AU, DE, FR, GB)
# with optional separator and optional trailing kind code (e.g. "B2", "A1").
_PATENT_ID_RE = re.compile(
    r"\b(US|EP|WO|CN|JP|KR|IN|CA|AU|DE|FR|GB)"
    r"[-\s]?"
    r"(\d{4,})"
    r"(?:[-\s]?[A-Z]\d*)?"
    r"\b"
)

# Overall risk-level statements in narrative report text.
_RISK_LEVEL_RE = re.compile(
    r"(?:"
    r"overall\s+risk(?:\s+level)?\s*:?\s*(HIGH|MEDIUM|LOW|CLEAR)"
    r"|risk\s*:\s*(HIGH|MEDIUM|LOW|CLEAR)"
    r"|(?:presents?\s+a\s+)(HIGH|MEDIUM|LOW|CLEAR)\s+(?:freedom[- ]to[- ]operate\s+)?risk"
    r"|\b(HIGH|MEDIUM|LOW|CLEAR)\s+risk\s+(?:level\b|rating\b)"
    r")",
    re.IGNORECASE,
)

_CLAIM_NUMBER_RE = re.compile(r"\bclaim\s+(\d+)\b", re.IGNORECASE)

_SECTION_HEADER_RE = re.compile(
    r"^#+\s+\d*\.?\s*(.*?)$",
    re.MULTILINE,
)

# Trailing kind code (e.g. "B2", "A1") used by normalize_patent_id.
_KIND_CODE_RE = re.compile(r"(?<=\d)[A-Z]\d*$")


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def normalize_patent_id(pid: str) -> str:
    """Normalize a patent ID for comparison.

    Strips spaces / hyphens, uppercases, and removes a trailing kind code.
    Idempotent.
    """
    pid = pid.strip().upper().replace(" ", "").replace("-", "")
    return _KIND_CODE_RE.sub("", pid)


def extract_patent_ids(text: str) -> list[str]:
    """Extract normalized, de-duplicated patent IDs from free text.

    Order of first occurrence is preserved.
    """
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for m in _PATENT_ID_RE.finditer(text):
        raw = m.group(0).replace(" ", "").replace("-", "")
        nid = normalize_patent_id(raw)
        if nid not in seen:
            seen.add(nid)
            out.append(nid)
    return out


def extract_risk_level(text: str) -> str | None:
    """Extract the first overall risk level statement, lowercased.

    Returns one of {"high", "medium", "low", "clear"} or None if absent.
    """
    if not text:
        return None
    m = _RISK_LEVEL_RE.search(text)
    if not m:
        return None
    for g in m.groups():
        if g is not None:
            return g.lower()
    return None


def extract_claim_numbers(text: str) -> list[int]:
    """Extract sorted, de-duplicated claim numbers from "claim N" mentions."""
    if not text:
        return []
    return sorted({int(m.group(1)) for m in _CLAIM_NUMBER_RE.finditer(text)})


def extract_section_headers(text: str) -> list[str]:
    """Extract markdown section headers (lowercased, ordered)."""
    if not text:
        return []
    return [m.group(1).strip().lower() for m in _SECTION_HEADER_RE.finditer(text)]


__all__ = [
    "extract_claim_numbers",
    "extract_patent_ids",
    "extract_risk_level",
    "extract_section_headers",
    "normalize_patent_id",
]
