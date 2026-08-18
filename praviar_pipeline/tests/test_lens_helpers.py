from __future__ import annotations

from praviar_pipeline.clients.lens_queries import (
    build_patent_search_payload,
    build_patent_search_query,
    build_scholarly_search_payload,
)
from praviar_pipeline.clients.lens_results import normalize_patent_results


def test_build_scholarly_search_payload_includes_patent_filter() -> None:
    payload = build_scholarly_search_payload(
        patent_id="US7851188B2",
        page_size=20,
        offset=40,
    )

    assert payload["query"]["bool"]["must"][0]["match"] == {
        "referenced_by_patent.lens_id": "US7851188B2"
    }
    assert payload["size"] == 20
    assert payload["from"] == 40


def test_build_patent_search_query_wraps_jurisdiction_terms() -> None:
    query = build_patent_search_query(
        keywords=["succinic acid", "fermentation"],
        jurisdictions=["US", "EP"],
    )

    must_clauses = query["bool"]["must"]
    assert must_clauses[1] == {"terms": {"jurisdiction": ["US", "EP"]}}
    assert len(must_clauses[0]["bool"]["should"]) == 6


def test_build_patent_search_payload_preserves_page_controls() -> None:
    payload = build_patent_search_payload(
        keywords=["alpha"],
        jurisdictions=None,
        page_size=50,
        offset=100,
    )

    assert payload["size"] == 50
    assert payload["from"] == 100
    assert payload["query"]["bool"]["minimum_should_match"] == 1


def test_normalize_patent_results_filters_non_dict_entries() -> None:
    normalized = normalize_patent_results(
        hits=[
            {
                "jurisdiction": "US",
                "doc_number": "123",
                "title": "Example",
                "abstract": "Abstract",
                "date_published": "2020-01-01",
                "classification_cpc": [{"symbol": "C07C"}, "bad"],
                "applicant": [{"name": "Acme"}, "bad"],
            }
        ],
        max_results=5,
    )

    assert normalized == [
        {
            "publication_number": "US123",
            "title": "Example",
            "abstract": "Abstract",
            "filing_date": "2020-01-01",
            "assignees": ["Acme"],
            "cpc_codes": ["C07C"],
        }
    ]
