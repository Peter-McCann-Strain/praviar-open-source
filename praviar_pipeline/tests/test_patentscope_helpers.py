from __future__ import annotations

from praviar_pipeline.clients.patentscope_helpers import (
    build_applicant_query,
    build_clir_params,
    build_clir_query,
    build_keyword_query,
    parse_results,
)


def test_build_applicant_query_with_jurisdictions() -> None:
    query = build_applicant_query("BASF SE", ["US", "EP"])

    assert query == 'pa:"BASF SE" AND (dp:US OR dp:EP)'


def test_build_clir_params_with_target_langs() -> None:
    params = build_clir_params(
        '("succinic acid")',
        25,
        source_lang="EN",
        target_langs=["JA", "KO"],
    )

    assert params["q"] == '("succinic acid")'
    assert params["rows"] == 25
    assert params["clir"] == "true"
    assert params["clirSourceLang"] == "EN"
    assert params["clirTargetLangs"] == "JA,KO"


def test_build_keyword_query_empty_keywords() -> None:
    assert build_keyword_query([]) == ""


def test_build_clir_query_joins_keywords() -> None:
    query = build_clir_query(["succinic acid", "amber acid"])

    assert query == '("succinic acid" OR "amber acid")'


def test_parse_results_normalizes_string_and_list_fields() -> None:
    results = parse_results(
        {
            "response": {
                "docs": [
                    {
                        "publicationNumber": "WO2020123456",
                        "title": "Method for producing succinic acid",
                        "applicants": "BASF SE;Evonik Industries",
                        "cpcCodes": ["C12P7/46"],
                    }
                ]
            }
        }
    )

    assert results == [
        {
            "publication_number": "WO2020123456",
            "title": "Method for producing succinic acid",
            "abstract": "",
            "filing_date": "",
            "priority_date": "",
            "assignees": ["BASF SE", "Evonik Industries"],
            "cpc_codes": ["C12P7/46"],
        }
    ]
