"""Contract tests for the fail-closed openFDA GSRS biologic resolver."""

from __future__ import annotations

import json

import httpx
import pytest

from praviar_pipeline.clients import openfda_gsrs
from praviar_pipeline.clients.openfda_gsrs import OpenFDAGSRSClient
from praviar_pipeline.errors import SourceUnavailableError


def _response(payload: dict, *, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        content=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
    )


@pytest.mark.asyncio
async def test_exact_name_binds_one_primary_complete_protein_record(mock_settings) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/other/unii.json":
            assert 'substance_name.exact:"ADALIMUMAB"' in request.url.params["search"]
            return _response(
                {
                    "meta": {"last_updated": "2026-07-25"},
                    "results": [{"substance_name": "ADALIMUMAB", "unii": "FYS6T7F842"}],
                }
            )
        return _response(
            {
                "meta": {"last_updated": "2025-09-19"},
                "results": [
                    {
                        "uuid": "49c070a0-3b9f-4617-86ad-d5551a84fbab",
                        "unii": "FYS6T7F842",
                        "substance_class": "protein",
                        "definition_type": "PRIMARY",
                        "definition_level": "COMPLETE",
                        "version": "119",
                        "names": [
                            {
                                "name": "ADALIMUMAB",
                                "display_name": True,
                                "type": "of",
                            },
                            {"name": "D2E7", "display_name": False, "type": "cd"},
                        ],
                        "protein": {
                            "protein_type": "MONOCLONAL ANTIBODY",
                            "protein_sub_type": "IGG1|KAPPA",
                            "sequence_origin": "HUMAN",
                            "sequence_type": "COMPLETE",
                            "subunits": [
                                {
                                    "subunit_index": 2,
                                    "sequence": "ACDEFGHIK",
                                },
                                {
                                    "subunit_index": 1,
                                    "sequence": "LMNPQRSTV",
                                },
                            ],
                        },
                    }
                ],
            }
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://api.fda.gov",
    ) as http_client:
        client = OpenFDAGSRSClient(client=http_client)
        identity = await client.resolve_exact_biologic("adalimumab")

    assert len(requests) == 2
    assert identity is not None
    assert identity.unii == "FYS6T7F842"
    assert identity.substance_class == "protein"
    assert identity.definition_type == "PRIMARY"
    assert identity.definition_level == "COMPLETE"
    assert identity.names_last_updated == "2026-07-25"
    assert identity.record_last_updated == "2025-09-19"
    assert identity.protein_subunit_sequences == ["LMNPQRSTV", "ACDEFGHIK"]


@pytest.mark.asyncio
async def test_ambiguous_exact_name_fails_closed_before_record_lookup(mock_settings) -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return _response(
            {
                "meta": {"last_updated": "2026-07-25"},
                "results": [
                    {"substance_name": "EXAMPLEMAB", "unii": "AAAAAAAAAA"},
                    {"substance_name": "EXAMPLEMAB", "unii": "BBBBBBBBBB"},
                ],
            }
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.fda.gov",
    ) as http_client:
        identity = await OpenFDAGSRSClient(client=http_client).resolve_exact_biologic("examplemab")

    assert identity is None
    assert request_count == 1


@pytest.mark.asyncio
async def test_nonprotein_or_incomplete_gsrs_record_is_rejected(mock_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/other/unii.json":
            return _response(
                {
                    "meta": {"last_updated": "2026-07-25"},
                    "results": [{"substance_name": "EXAMPLEMAB", "unii": "AAAAAAAAAA"}],
                }
            )
        return _response(
            {
                "meta": {"last_updated": "2026-07-25"},
                "results": [
                    {
                        "uuid": "uuid-1",
                        "unii": "AAAAAAAAAA",
                        "substance_class": "chemical",
                        "definition_type": "PRIMARY",
                        "definition_level": "COMPLETE",
                        "names": [{"name": "EXAMPLEMAB", "display_name": True}],
                    }
                ],
            }
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.fda.gov",
    ) as http_client:
        identity = await OpenFDAGSRSClient(client=http_client).resolve_exact_biologic("examplemab")

    assert identity is None


@pytest.mark.asyncio
async def test_nonsemantic_http_error_is_source_failure(mock_settings) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: _response({}, status_code=400)),
        base_url="https://api.fda.gov",
    ) as http_client:
        with pytest.raises(SourceUnavailableError) as exc_info:
            await OpenFDAGSRSClient(client=http_client).resolve_exact_biologic("adalimumab")

    assert exc_info.value.source == "openfda_gsrs"
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_cached_response_with_invalid_envelope_fails_closed(
    mock_settings,
    monkeypatch,
) -> None:
    async def malformed_cached_request(**_kwargs):
        return []

    monkeypatch.setattr(openfda_gsrs, "cached_request", malformed_cached_request)
    async with httpx.AsyncClient(base_url="https://api.fda.gov") as http_client:
        client = OpenFDAGSRSClient(client=http_client)
        with pytest.raises(SourceUnavailableError, match="cached response"):
            await client._get(
                "/other/unii.json",
                params={"search": 'substance_name.exact:"ADALIMUMAB"'},
                semantic_not_found=True,
            )


@pytest.mark.asyncio
async def test_malformed_gsrs_protein_subunit_fails_closed(mock_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/other/unii.json":
            return _response({"results": [{"substance_name": "EXAMPLEMAB", "unii": "AAAAAAAAAA"}]})
        return _response(
            {
                "results": [
                    {
                        "uuid": "uuid-1",
                        "unii": "AAAAAAAAAA",
                        "substance_class": "protein",
                        "definition_type": "PRIMARY",
                        "definition_level": "COMPLETE",
                        "names": [{"name": "EXAMPLEMAB", "display_name": True}],
                        "protein": {
                            "sequence_type": "COMPLETE",
                            "subunits": [{"subunit_index": 1, "sequence": "ACD*INVALID"}],
                        },
                    }
                ]
            }
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.fda.gov",
    ) as http_client:
        with pytest.raises(SourceUnavailableError, match="unsupported or malformed"):
            await OpenFDAGSRSClient(client=http_client).resolve_exact_biologic("examplemab")
