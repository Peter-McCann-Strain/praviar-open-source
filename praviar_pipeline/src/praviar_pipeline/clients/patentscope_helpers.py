"""Pure helpers for PatentScope query and result normalization."""

from __future__ import annotations

DEFAULT_FIELDS = "publicationNumber,title,abstract,filingDate,priorityDate,applicants,cpcCodes"


def build_keyword_query(
    keywords: list[str],
    jurisdictions: list[str] | None = None,
) -> str:
    """Build a PatentScope keyword query with optional jurisdiction filters."""
    if not keywords:
        return ""

    keyword_clause = " OR ".join(f'"{kw}"' for kw in keywords)
    query = f"({keyword_clause})"

    if jurisdictions:
        dp_clause = " OR ".join(f"dp:{jurisdiction}" for jurisdiction in jurisdictions)
        query = f"{query} AND ({dp_clause})"

    return query


def build_applicant_query(
    applicant: str,
    jurisdictions: list[str] | None = None,
) -> str:
    """Build a PatentScope applicant query with optional jurisdiction filters."""
    query = f'pa:"{applicant}"'
    if not jurisdictions:
        return query

    dp_clause = " OR ".join(f"dp:{jurisdiction}" for jurisdiction in jurisdictions)
    return f"{query} AND ({dp_clause})"


def build_clir_query(keywords: list[str]) -> str:
    """Build a CLIR PatentScope query from keyword clauses only."""
    if not keywords:
        return ""

    keyword_clause = " OR ".join(f'"{kw}"' for kw in keywords)
    return f"({keyword_clause})"


def build_search_params(query: str, rows: int) -> dict[str, str | int]:
    """Build common PatentScope search request parameters."""
    return {
        "q": query,
        "rows": rows,
        "start": 0,
        "fl": DEFAULT_FIELDS,
        "wt": "json",
    }


def build_clir_params(
    query: str,
    rows: int,
    *,
    source_lang: str,
    target_langs: list[str] | None,
) -> dict[str, str | int]:
    """Build PatentScope CLIR request parameters."""
    params = build_search_params(query, rows)
    params["clir"] = "true"
    params["clirSourceLang"] = source_lang
    if target_langs:
        params["clirTargetLangs"] = ",".join(target_langs)
    return params


def _normalize_multi_value(raw_value) -> list[str]:
    if isinstance(raw_value, str):
        return [item.strip() for item in raw_value.split(";") if item.strip()]
    if isinstance(raw_value, list):
        return raw_value
    return []


def parse_results(data: dict) -> list[dict]:
    """Parse PatentScope search responses into normalized patent records."""
    results: list[dict] = []
    docs = data.get("results", data.get("response", {}).get("docs", []))
    if not isinstance(docs, list):
        return results

    for doc in docs:
        pub_number = doc.get("publicationNumber", doc.get("publication_number", ""))
        if not pub_number:
            continue

        assignees = _normalize_multi_value(doc.get("applicants", doc.get("assignees", [])))
        cpc_codes = _normalize_multi_value(doc.get("cpcCodes", doc.get("cpc_codes", [])))

        results.append(
            {
                "publication_number": pub_number,
                "title": doc.get("title", ""),
                "abstract": doc.get("abstract", ""),
                "filing_date": doc.get("filingDate", doc.get("filing_date", "")),
                "priority_date": doc.get("priorityDate", doc.get("priority_date", "")),
                "assignees": assignees,
                "cpc_codes": cpc_codes,
            }
        )

    return results
