from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from praviar_pipeline.clients.uspto_odp_client_ops import (
    get_adjustment,
    get_application_data,
    get_assignment,
    get_continuity_data,
    get_file_wrapper_documents,
    get_office_actions,
    resolve_app_number,
    search_patents,
)
from praviar_pipeline.utils.patent_ids import clean_patent_number_for_api


class _StubClient(SimpleNamespace):
    def _require_valid_key(self) -> None:
        if not getattr(self, "_key_valid", True):
            raise RuntimeError("invalid key")


@pytest.mark.asyncio
async def test_resolve_app_number_caches_exact_match() -> None:
    client = _StubClient(
        _key_valid=True,
        _app_number_cache={},
        _post=AsyncMock(
            return_value={
                "patentFileWrapperDataBag": [
                    {
                        "applicationNumberText": "22222222",
                        "applicationMetaData": {"patentNumber": "US1234567"},
                    }
                ]
            }
        ),
    )

    assert await resolve_app_number(client, "US1234567") == "22222222"
    assert client._app_number_cache[clean_patent_number_for_api("US1234567")] == "22222222"
    client._post.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_application_data_extracts_first_wrapper_record() -> None:
    client = _StubClient(
        _key_valid=True,
        _app_number_cache={clean_patent_number_for_api("US1234567"): "22222222"},
        _get=AsyncMock(
            return_value={
                "patentFileWrapperDataBag": [{"applicationNumberText": "22222222", "foo": "bar"}]
            }
        ),
        get_application_data=AsyncMock(
            return_value={"parentContinuityBag": [], "childContinuityBag": []}
        ),
        get_file_wrapper_documents=AsyncMock(return_value=[]),
    )

    result = await get_application_data(client, "US1234567")
    assert result == {"applicationNumberText": "22222222", "foo": "bar"}


@pytest.mark.asyncio
async def test_get_file_wrapper_documents_prefers_named_results() -> None:
    client = _StubClient(
        _key_valid=True,
        _app_number_cache={clean_patent_number_for_api("US1234567"): "22222222"},
        _get=AsyncMock(return_value={"results": [{"documentCode": "OA"}]}),
        get_application_data=AsyncMock(return_value={}),
        get_file_wrapper_documents=AsyncMock(return_value=[]),
    )

    docs = await get_file_wrapper_documents(client, "US1234567")
    assert docs == [{"documentCode": "OA"}]


@pytest.mark.asyncio
async def test_get_continuity_data_merges_entries() -> None:
    client = _StubClient(
        _key_valid=True,
        _app_number_cache={clean_patent_number_for_api("US1234567"): "22222222"},
        _get=AsyncMock(
            return_value={
                "parentContinuityBag": [{"parent": 1}],
                "childContinuityBag": [{"child": 2}],
            }
        ),
        get_file_wrapper_documents=AsyncMock(return_value=[]),
    )

    assert await get_continuity_data(client, "US1234567") == [{"parent": 1}, {"child": 2}]
    client._get.assert_awaited_once_with("/patent/applications/22222222/continuity")


@pytest.mark.asyncio
async def test_adjustment_and_assignment_use_current_dedicated_endpoints() -> None:
    client = _StubClient(
        _key_valid=True,
        _app_number_cache={clean_patent_number_for_api("US1234567"): "22222222"},
        _get=AsyncMock(
            side_effect=[
                {"patentTermAdjustmentData": {"adjustmentTotalQuantity": 12}},
                {"assignmentBag": [{"reelNumber": "1234"}]},
            ]
        ),
        get_application_data=AsyncMock(return_value={}),
        get_file_wrapper_documents=AsyncMock(return_value=[]),
    )

    adjustment = await get_adjustment(client, "US1234567")
    assignments = await get_assignment(client, "US1234567")

    assert adjustment["patentTermAdjustmentData"]["adjustmentTotalQuantity"] == 12
    assert assignments == [{"reelNumber": "1234"}]
    assert [call.args[0] for call in client._get.await_args_list] == [
        "/patent/applications/22222222/adjustment",
        "/patent/applications/22222222/assignment",
    ]


@pytest.mark.asyncio
async def test_get_office_actions_filters_codes() -> None:
    client = _StubClient(
        _key_valid=True,
        _app_number_cache={"US1234567": "22222222"},
        _get=AsyncMock(return_value={}),
        get_application_data=AsyncMock(return_value={}),
        get_file_wrapper_documents=AsyncMock(
            return_value=[
                {"documentCode": "OA"},
                {"documentCode": "COVER"},
                {"documentCode": "NFOA"},
            ]
        ),
    )

    docs = await get_office_actions(client, "US1234567")
    assert docs == [{"documentCode": "OA"}, {"documentCode": "NFOA"}]


@pytest.mark.asyncio
async def test_search_patents_returns_empty_for_non_dict_response() -> None:
    client = _StubClient(
        _key_valid=True,
        _app_number_cache={},
        _post=AsyncMock(return_value=[]),
        get_application_data=AsyncMock(return_value={}),
        get_file_wrapper_documents=AsyncMock(return_value=[]),
    )

    assert await search_patents(client, "compound") == {}
