"""Shared helpers for deterministic report validators."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

# Strips trailing document-kind code (A1, B2, A, B, A2, etc.) from a
# normalized patent ID so "US2011178396" matches "US2011178396A1".
_KIND_CODE_RE = re.compile(r"[A-Z]\d?$")

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.pipeline.report_data_store import ReportDataStore

# Country-code prefix shared by all multi-jurisdiction patterns.
_CC = r"(?:US|EP|WO|CN|JP|KR|CA|AU|MX|BR|IN|GB|DE|FR)"

# Generic multi-jurisdiction patent ID
# US7964580B2, WO2024112312A1, EP1234567B1, CN120187720A, etc.
# Handles dashes/spaces as separators and US comma-thousands notation.
_ANY_PATENT = (
    r"(?:"
    # US with optional comma-thousands: US7,964,580B2
    r"US[-\s]?(?:\d[\d,\s]{5,})(?:\s?[A-Z]\d?)?"
    r"|"
    # WO: WO2024112312A1 or WO2024/112312
    r"WO[-\s]?\d{4}[-/\s]?\d{5,8}(?:[-\s]?[A-Z]\d?)?"
    r"|"
    # EP/CN/JP/KR/…: 6+ digits, optional kind code
    rf"{_CC}[-\s]?\d{{6,}}(?:[-\s]?[A-Z]\d?)?"
    r")"
)

# Compiled bare matcher — used for extract_patent_ids
_ANY_PATENT_RE = re.compile(_ANY_PATENT, re.IGNORECASE)

# Legacy alias kept for PTAB/date/assignee patterns that only appear near US IDs
US_PATENT_RE = re.compile(r"US[-\s]?(?:\d[\d,\s]{5,})(?:\s?[A-Z]\d?)?")

# PTAB proceeding format
PTAB_RE = re.compile(r"(IPR|PGR|CBM)\d{4}-\d{4,5}")

# Regex: patent ID near a risk word within ~100 chars (any jurisdiction)
PATENT_RISK_RE = re.compile(
    rf"({_ANY_PATENT})"
    r"[^.]{0,100}?"
    r"\b(HIGH|MEDIUM|LOW|CLEAR)\b"
    r"[\s\-]*risk",
    re.IGNORECASE,
)

# Also catch "HIGH risk ... <patent>" (any jurisdiction)
RISK_PATENT_RE = re.compile(
    r"\b(HIGH|MEDIUM|LOW|CLEAR)\b"
    r"[\s\-]*risk"
    r"[^.]{0,100}?"
    rf"({_ANY_PATENT})",
    re.IGNORECASE,
)

# Date near patent ID (US only — date validators only run on US-originated data)
PATENT_DATE_RE = re.compile(
    r"(US[-\s]?(?:\d[\d,\s]{5,})(?:\s?[A-Z]\d?)?)"
    r"[^.]{0,120}?"
    r"(?:expir(?:es|y|ation)|expires?\s+(?:on\s+)?|expiry[:\s]+)"
    r"(\d{4}[-/]\d{2}[-/]\d{2})",
    re.IGNORECASE,
)

# Assignee near patent ID (US only — parenthetical pattern)
PATENT_ASSIGNEE_RE = re.compile(
    r"(US[-\s]?(?:\d[\d,\s]{5,})(?:\s?[A-Z]\d?)?)"
    r"\s*\(([^)]{2,80})\)",
)


def normalize_patent_id(pid: str) -> str:
    """Normalize a patent ID for comparison (strips dashes, spaces, commas, slashes)."""
    return pid.replace("-", "").replace(" ", "").replace(",", "").replace("/", "").strip()


def strip_kind_code(normalized_pid: str) -> str:
    """Remove trailing document-kind code (A1, B2, A, B, etc.) from a normalized patent ID.

    Allows matching 'US2011178396' against 'US2011178396A1' from the pipeline data.
    Input must already be normalized (no dashes/spaces).
    """
    return _KIND_CODE_RE.sub("", normalized_pid)


def extract_patent_ids(text: str) -> set[str]:
    """Extract patent IDs (any jurisdiction) from text and normalize."""
    raw = _ANY_PATENT_RE.findall(text)
    return {normalize_patent_id(pid) for pid in raw if len(normalize_patent_id(pid)) >= 8}


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


def find_analysis_by_normalized_patent_id(
    data_store: ReportDataStore,
    normalized_patent_id: str,
) -> PatentAnalysis | None:
    for patent_id in data_store.all_patent_ids():
        if normalize_patent_id(patent_id) == normalized_patent_id:
            return data_store.get_analysis(patent_id)
    return None


def extract_patent_risk_pairs(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for match in PATENT_RISK_RE.finditer(text):
        # Guard: skip if another patent appears between the initial patent and the risk word.
        # The risk word likely belongs to the intervening patent, not the leading one.
        span_between = text[match.end(1) : match.start(2)]
        if _ANY_PATENT_RE.search(span_between):
            continue
        pairs.append((match.group(1), match.group(2).upper()))
    for match in RISK_PATENT_RE.finditer(text):
        # Guard A: skip if another patent appears between the risk word and the target patent.
        span_between = text[match.end(1) : match.start(2)]
        if _ANY_PATENT_RE.search(span_between):
            continue
        # Guard B: skip if another patent precedes the risk word in the same sentence
        # (from the previous period to the risk word position) — the risk word belongs
        # to that earlier patent, not the one that follows.
        risk_pos = match.start()
        prev_dot = text.rfind(".", 0, risk_pos)
        preceding_in_sentence = text[prev_dot + 1 : risk_pos]
        if _ANY_PATENT_RE.search(preceding_in_sentence):
            continue
        pairs.append((match.group(2), match.group(1).upper()))
    return pairs
