"""Pure request-payload builders for the Lens.org client."""

from __future__ import annotations


def build_scholarly_search_payload(
    *,
    patent_id: str,
    page_size: int,
    offset: int,
) -> dict:
    return {
        "query": {
            "bool": {
                "must": [
                    {
                        "match": {
                            "referenced_by_patent.lens_id": patent_id,
                        }
                    }
                ]
            }
        },
        "size": page_size,
        "from": offset,
        "include": [
            "lens_id",
            "title",
            "abstract",
            "date_published",
            "year_published",
            "authors",
            "external_ids",
            "source",
            "scholarly_citations_count",
        ],
    }


def build_patent_search_query(
    *,
    keywords: list[str],
    jurisdictions: list[str] | None,
) -> dict:
    should_clauses = [
        {"match": {field: keyword}}
        for keyword in keywords
        for field in ("title", "abstract", "claims")
    ]
    bool_query: dict = {
        "bool": {
            "should": should_clauses,
            "minimum_should_match": 1,
        }
    }
    if not jurisdictions:
        return bool_query
    return {
        "bool": {
            "must": [
                bool_query,
                {"terms": {"jurisdiction": jurisdictions}},
            ]
        }
    }


def build_patent_search_payload(
    *,
    keywords: list[str],
    jurisdictions: list[str] | None,
    page_size: int,
    offset: int,
) -> dict:
    return {
        "query": build_patent_search_query(
            keywords=keywords,
            jurisdictions=jurisdictions,
        ),
        "size": page_size,
        "from": offset,
        "include": [
            "lens_id",
            "doc_number",
            "jurisdiction",
            "title",
            "abstract",
            "date_published",
            "applicant",
            "classification_cpc",
        ],
    }
