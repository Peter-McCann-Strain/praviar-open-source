"""USPTO ODP response extraction helpers.

Parses patentFileWrapperDataBag records from the USPTO Open Data Portal
applications/search endpoint. Maps the ODP schema to the canonical internal
field names used by the downstream pipeline.
"""

from __future__ import annotations

import re
from typing import cast


def extract_patents(data: dict | None) -> list[dict]:
    """Extract and normalise patent records from an ODP search response."""
    if not data:
        return []
    bag = data.get("patentFileWrapperDataBag", [])
    if not isinstance(bag, list):
        return []
    return [_normalize_record(rec) for rec in bag if rec]


def extract_first_patent(patents: list[dict] | None) -> dict:
    return patents[0] if patents else {}


def extract_patent_citations(_patents: list[dict] | None) -> list[dict]:
    # The ODP applications search endpoint does not expose citation networks.
    return []


def format_claims_text(claims: list[dict]) -> str:
    if not claims:
        return ""
    sorted_claims = sorted(claims, key=lambda c: c.get("claim_number", 0))
    return "\n\n".join(
        f"{c.get('claim_number', '?')}. {c.get('claim_text', '')}" for c in sorted_claims
    )


def _normalize_record(rec: dict) -> dict:
    """Map a patentFileWrapperDataBag record to the canonical patent dict."""
    meta = rec.get("applicationMetaData") or {}
    patent_number = meta.get("patentNumber") or ""

    if patent_number:
        patent_id = f"US{patent_number}B2"
        kind = "B2"
    else:
        # Use pre-grant publication number while application is pending
        pub = meta.get("earliestPublicationNumber") or rec.get("applicationNumberText") or ""
        patent_id = pub
        kind = "A1"

    cpcs = [_normalise_cpc(c) for c in (meta.get("cpcClassificationBag") or []) if c]

    return {
        "patent_id": patent_id,
        "patent_kind": kind,
        "patent_title": meta.get("inventionTitle"),
        "patent_abstract": None,
        "patent_date": meta.get("grantDate") or meta.get("effectiveFilingDate"),
        "assignee_organization": _extract_assignee(rec),
        "cpc_subgroup_ids": cpcs,
    }


def _extract_assignee(rec: dict) -> str | None:
    """Extract the primary assignee name from an ODP record."""
    for assignment in rec.get("assignmentBag") or []:
        for assignee in assignment.get("assigneeBag") or []:
            name = assignee.get("assigneeNameText")
            if name:
                return cast("str", name.title())
    for applicant in (rec.get("applicationMetaData") or {}).get("applicantBag") or []:
        name = applicant.get("applicantNameText")
        if name:
            return cast("str", name)
    return None


def _normalise_cpc(code: str) -> str:
    """Collapse internal whitespace in a CPC code (e.g. 'A61K   8/0216' → 'A61K 8/0216')."""
    return re.sub(r"\s+", " ", code).strip()
