"""Metadata and provenance helpers for patent-level evidence records."""

from __future__ import annotations

import re
from types import SimpleNamespace

from praviar_pipeline.models.patent import PatentSource
from praviar_pipeline.pipeline.report.evidence_index_shared import unique_strings
from praviar_pipeline.pipeline.report.prosecution_helpers import dossier_source_name

_PATENT_PREFIX_RE = re.compile(r"^([A-Z]{2})")
_AUTHORITATIVE_SOURCE_NAMES = {
    PatentSource.EPO_SEARCH.value,
    PatentSource.INPADOC.value,
    PatentSource.PATENTSVIEW.value,
    "epo_register",
    "orange_book",
    "ptab",
    "uspto_odp",
}


def normalize_dossier(dossier):
    if isinstance(dossier, dict):
        return SimpleNamespace(**dossier)
    return dossier


def derive_jurisdiction(patent_id: str, detail=None) -> str:
    jurisdiction = str(getattr(detail, "jurisdiction", "") or "").upper()
    if jurisdiction:
        return jurisdiction
    match = _PATENT_PREFIX_RE.match((patent_id or "").upper())
    return match.group(1) if match else ""


def classify_source_authority(source_names: list[str]) -> tuple[list[str], list[str]]:
    authoritative = [name for name in source_names if name in _AUTHORITATIVE_SOURCE_NAMES]
    supporting = [name for name in source_names if name not in _AUTHORITATIVE_SOURCE_NAMES]
    return unique_strings(authoritative), unique_strings(supporting)


def build_authoritative_record_categories(
    *,
    jurisdiction: str,
    authoritative_source_names: list[str],
    has_family_context: bool,
    has_us_prosecution_context: bool,
    has_us_file_wrapper_dossier: bool,
    has_ep_register_context: bool,
    has_assignments: bool,
    has_priority_claims: bool,
    has_ptab_proceedings: bool,
    has_orange_book_listing: bool,
) -> list[str]:
    categories: list[str] = []
    if authoritative_source_names:
        categories.append("authoritative_search_source")
    if has_family_context:
        categories.append("family_record")
    if jurisdiction == "US" and has_us_prosecution_context:
        categories.append("us_prosecution_record")
    if jurisdiction == "US" and has_us_file_wrapper_dossier:
        categories.append("us_file_wrapper_dossier")
    if jurisdiction == "EP" and has_ep_register_context:
        categories.append("ep_register_record")
    if has_assignments:
        categories.append("assignment_record")
    if has_priority_claims:
        categories.append("priority_record")
    if has_ptab_proceedings:
        categories.append("ptab_record")
    if has_orange_book_listing:
        categories.append("orange_book_record")
    return categories


def collect_source_names(
    *,
    detail,
    dossier,
    has_ptab_proceedings: bool,
    has_orange_book_listing: bool,
    has_ep_register_context: bool,
) -> list[str]:
    source_names = (
        sorted(
            {
                getattr(source, "value", str(source))
                for source in getattr(detail, "sources", []) or []
            }
        )
        if detail
        else []
    )
    if dossier:
        source_name = dossier_source_name(dossier)
        if source_name:
            source_names.append(source_name)
    if has_ptab_proceedings:
        source_names.append("ptab")
    if has_orange_book_listing:
        source_names.append("orange_book")
    if has_ep_register_context:
        source_names.append("epo_register")
    return unique_strings(source_names)
