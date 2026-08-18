"""Pure parsing, filtering, and scoring helpers for Step 2b ranking."""

from __future__ import annotations

import contextlib
import re
from contextvars import ContextVar
from datetime import date
from typing import TYPE_CHECKING

from praviar_pipeline.config import get_settings
from praviar_pipeline.utils.dates import parse_date as _parse_date
from praviar_pipeline.utils.patent_term import _safe_add_years

if TYPE_CHECKING:
    from collections.abc import Iterator

    from praviar_pipeline.models.compound import ResolvedCompound

_CPC_HIGH_RELEVANCE = {
    "C07C",
    "C07D",
    "C07K",
    "C12P",
    "C12N",
    "A61K",
    "A61P",
}
_CPC_MEDIUM_RELEVANCE = {"C08", "C09", "C12", "A61"}
_ALLOWED_KIND_CODES = re.compile(r"[ABE]\d?$", re.IGNORECASE)
_REFERENCE_DATE: ContextVar[date | None] = ContextVar(
    "praviar_ranking_reference_date", default=None
)


@contextlib.contextmanager
def use_ranking_reference_date(value: date) -> Iterator[None]:
    """Temporarily freeze date-sensitive ranking for a governed replay.

    Normal production ranking continues to use the current date. Synthetic
    dry-runs and other explicitly governed replays may bind one reference date
    so expiry filtering and recency scoring remain reproducible across days.
    """

    token = _REFERENCE_DATE.set(value)
    try:
        yield
    finally:
        _REFERENCE_DATE.reset(token)


def _ranking_today() -> date:
    return _REFERENCE_DATE.get() or date.today()


def extract_kind_code(patent_id: str) -> str:
    """Extract kind code from a publication number."""
    match = re.search(r"([A-Z]\d?)$", patent_id.strip())
    return match.group(1) if match else ""


def count_cids(cids_field: str | list | None) -> int:
    """Count how many compounds are listed in a CID field."""
    if not cids_field:
        return 0
    if isinstance(cids_field, list):
        return len(cids_field)
    text = str(cids_field)
    separator = "|" if "|" in text else ","
    return len([cid for cid in text.split(separator) if cid.strip()])


def parse_cpc_codes(classification: str | list | None) -> list[str]:
    """Parse CPC/IPC codes from SDQ-style classification data."""
    if not classification:
        return []
    if isinstance(classification, list):
        return classification
    text = str(classification)
    separator = "|" if "|" in text else ";"
    return [code.strip() for code in text.split(separator) if code.strip()]


def apply_hard_filters(
    patents: list[dict],
    include_expired: bool = True,
    expired_grace_years: int = 5,
    allowed_jurisdictions: list[str] | None = None,
    collect_audit: bool = False,
) -> tuple[list[dict], dict[str, str]]:
    """Remove patents that are clearly irrelevant."""
    if allowed_jurisdictions is None:
        settings = get_settings()
        allowed_jurisdictions = settings.search_allowed_jurisdictions

    today = _ranking_today()
    filtered: list[dict] = []
    rejection_reasons: dict[str, str] = {}

    for patent in patents:
        pub_num = str(patent.get("publicationnumber", ""))

        if not any(pub_num.startswith(code) for code in allowed_jurisdictions):
            if collect_audit:
                rejection_reasons[pub_num] = "non_allowed_jurisdiction"
            continue

        kind = extract_kind_code(pub_num)
        if kind and not _ALLOWED_KIND_CODES.match(kind):
            if collect_audit:
                rejection_reasons[pub_num] = f"invalid_kind_code_{kind}"
            continue

        filing_date = _parse_date(patent.get("filingdate")) or _parse_date(
            patent.get("prioritydate")
        )
        if filing_date:
            estimated_expiry = _safe_add_years(filing_date, 20)
            if not include_expired and estimated_expiry < today:
                if collect_audit:
                    rejection_reasons[pub_num] = "expired"
                continue
            if include_expired:
                grace_cutoff = _safe_add_years(today, -expired_grace_years)
                if estimated_expiry < grace_cutoff:
                    if collect_audit:
                        rejection_reasons[pub_num] = "expired_beyond_grace"
                    continue

        filtered.append(patent)

    return filtered, rejection_reasons


def score_cpc_relevance(cpc_codes: list[str]) -> float:
    """Score 0.0-1.0 based on CPC code relevance to chemistry/pharma claims."""
    if not cpc_codes:
        return 0.0

    for code in cpc_codes:
        if code[:4].rstrip("/") in _CPC_HIGH_RELEVANCE:
            return 1.0

    for code in cpc_codes:
        if code[:3].rstrip("/") in _CPC_MEDIUM_RELEVANCE:
            return 0.5

    return 0.0


def score_compound_count(cid_count: int) -> float:
    """Score 0.0-1.0 based on how many compounds the patent lists."""
    settings = get_settings()
    if cid_count <= settings.rank_compound_count_low:
        return 1.0
    if cid_count <= settings.rank_compound_count_medium:
        return 0.7
    if cid_count <= settings.rank_compound_count_high:
        return 0.3
    return 0.0


def score_recency(priority_date: date | None) -> float:
    """Score 0.0-1.0 with linear decay so recent patents score higher."""
    if not priority_date:
        return 0.0

    today = _ranking_today()
    age_years = (today - priority_date).days / 365.25

    settings = get_settings()
    if age_years <= 0:
        return 1.0
    if age_years >= settings.rank_recency_max_age_years:
        return 0.0

    return 1.0 - (age_years / settings.rank_recency_max_age_years)


def score_title_keyword(title: str, compound: ResolvedCompound) -> float:
    """Score 1.0 if a compound identifier appears in the patent title."""
    if not title:
        return 0.0

    title_lower = title.lower()
    if compound.name.lower() in title_lower:
        return 1.0

    settings = get_settings()
    for synonym in compound.synonyms[: settings.rank_title_synonyms]:
        if len(synonym) >= settings.rank_min_synonym_length and synonym.lower() in title_lower:
            return 1.0

    for cas in compound.cas_numbers:
        if cas in title:
            return 1.0

    return 0.0


def score_multi_source(patent_id: str, multi_source_ids: set[str]) -> float:
    """Score 1.0 if a patent was also found by another source."""
    from praviar_pipeline.utils.patent_ids import normalize_patent_id

    normalized = normalize_patent_id(patent_id)
    return 1.0 if normalized in multi_source_ids else 0.0


def compute_composite_score(
    cpc_score: float,
    compound_count_score: float,
    recency_score: float,
    title_score: float,
    multi_source_score: float,
) -> float:
    """Weighted composite of all ranking signals."""
    settings = get_settings()
    return (
        settings.rank_weight_cpc * cpc_score
        + settings.rank_weight_compound_count * compound_count_score
        + settings.rank_weight_recency * recency_score
        + settings.rank_weight_title * title_score
        + settings.rank_weight_multi_source * multi_source_score
    )
