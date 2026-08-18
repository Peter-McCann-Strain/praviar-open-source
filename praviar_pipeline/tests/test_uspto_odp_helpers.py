from __future__ import annotations

from praviar_pipeline.clients.uspto_odp_helpers import (
    extract_first_wrapper_record,
    extract_named_results,
    is_key_valid,
    merge_continuity_entries,
    resolve_app_number_from_search,
)


def test_is_key_valid_trims_whitespace() -> None:
    assert is_key_valid(" key ")
    assert not is_key_valid("   ")


def test_resolve_app_number_from_search_prefers_exact_patent_number() -> None:
    app_num = resolve_app_number_from_search(
        {
            "patentFileWrapperDataBag": [
                {
                    "applicationNumberText": "11111111",
                    "applicationMetaData": {"patentNumber": "US0000001"},
                },
                {
                    "applicationNumberText": "22222222",
                    "applicationMetaData": {"patentNumber": "US1234567"},
                },
            ]
        },
        "US1234567",
    )

    assert app_num == "22222222"


def test_resolve_app_number_never_falls_back_to_a_fuzzy_first_result() -> None:
    assert (
        resolve_app_number_from_search(
            {
                "patentFileWrapperDataBag": [
                    {
                        "applicationNumberText": "11111111",
                        "applicationMetaData": {"patentNumber": "US0000001"},
                    }
                ]
            },
            "US1234567",
        )
        is None
    )


def test_extract_named_results_and_wrapper_helpers() -> None:
    assert extract_first_wrapper_record({"patentFileWrapperDataBag": [{"a": 1}]}) == {"a": 1}
    assert extract_named_results({"results": [{"b": 2}]}, "results", "documentBag") == [{"b": 2}]
    assert merge_continuity_entries(
        {"parentContinuityBag": [{"a": 1}], "childContinuityBag": [{"b": 2}]}
    ) == [{"a": 1}, {"b": 2}]
