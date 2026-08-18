"""Pure result normalization helpers for the Lens.org client."""

from __future__ import annotations


def normalize_patent_results(
    *,
    hits: list[dict],
    max_results: int,
) -> list[dict]:
    normalized: list[dict] = []
    for hit in hits[:max_results]:
        jurisdiction = hit.get("jurisdiction", "")
        doc_number = hit.get("doc_number", "")
        publication_number = f"{jurisdiction}{doc_number}" if jurisdiction else doc_number
        cpc_raw = hit.get("classification_cpc", []) or []
        applicants_raw = hit.get("applicant", []) or []
        normalized.append(
            {
                "publication_number": publication_number,
                "title": hit.get("title", ""),
                "abstract": hit.get("abstract", ""),
                "filing_date": hit.get("date_published", ""),
                "assignees": [
                    applicant.get("name", "")
                    for applicant in applicants_raw
                    if isinstance(applicant, dict)
                ],
                "cpc_codes": [
                    entry.get("symbol", "") for entry in cpc_raw if isinstance(entry, dict)
                ],
            }
        )
    return normalized
