from __future__ import annotations

import hashlib
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from praviar_pipeline.clients.pubchem import PubChemClient
from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.models.patent import PatentHit, PatentSource
from praviar_pipeline.models.report import SourceHealth, SourceHealthEntry, SourceStatus
from praviar_pipeline.pipeline.search import primary_sources
from praviar_pipeline.pipeline.search.models import SearchExecutionSummary
from praviar_pipeline.pipeline.search.normalizers import _merge_supplementary_rows
from praviar_pipeline.pipeline.search.orchestration import _required_failures_for_policy


@pytest.mark.asyncio
async def test_pubchem_client_executes_bounded_substructure_and_batch_xref() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "fastsubstructure" in request.url.path:
            assert request.url.params["MaxRecords"] == "3"
            assert request.url.params["RingsNotEmbedded"] == "false"
            return httpx.Response(
                200,
                json={"IdentifierList": {"CID": [11, 22]}},
            )
        assert request.url.path.endswith("/compound/cid/11,22/xrefs/PatentID/JSON")
        return httpx.Response(
            200,
            json={
                "InformationList": {
                    "Information": [
                        {
                            "CID": 11,
                            "PatentID": ["US20250001234A1", "EP1234567A1"],
                        },
                        {"CID": 22, "PatentID": ["US7654321B2"]},
                    ]
                }
            },
        )

    http = httpx.AsyncClient(
        base_url="https://pubchem.ncbi.nlm.nih.gov/rest/pug",
        transport=httpx.MockTransport(handler),
    )
    async with PubChemClient(client=http) as client:
        cids = await client.substructure_search_cids(
            "c1ccccc1",
            max_records=3,
        )
        mappings = await client.get_patent_links_for_cids(cids)
    await http.aclose()

    assert cids == [11, 22]
    assert mappings == [
        {
            "cid": 11,
            "patent_ids": ["US20250001234A1", "EP1234567A1"],
        },
        {"cid": 22, "patent_ids": ["US7654321B2"]},
    ]
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_pubchem_genus_rejects_malformed_cid_rows() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"IdentifierList": {"CID": ["not-an-integer"]}},
        )

    http = httpx.AsyncClient(
        base_url="https://pubchem.ncbi.nlm.nih.gov/rest/pug",
        transport=httpx.MockTransport(handler),
    )
    async with PubChemClient(client=http) as client:
        with pytest.raises(SourceUnavailableError):
            await client.substructure_search_cids("c1ccccc1")
    await http.aclose()


@pytest.mark.asyncio
async def test_genus_lane_retains_hash_only_evidence_and_jurisdiction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def substructure_search_cids(self, *_args, **_kwargs):
            return [11]

        async def get_patent_links_for_cids(self, _cids):
            return [
                {
                    "cid": 11,
                    "patent_ids": [
                        "US 2025 0001234 A1",
                        "EP1234567A1",
                        "CN123456789A",
                    ],
                }
            ]

    monkeypatch.setattr(
        primary_sources,
        "get_settings",
        lambda: SimpleNamespace(
            pubchem_genus_max_compounds=100,
            pubchem_genus_max_patents=100,
            pubchem_genus_max_seconds=60,
            search_allowed_jurisdictions=["US", "EP"],
        ),
    )
    compound = SimpleNamespace(
        compound_type="small_molecule",
        scaffold_smiles="c1ccccc1",
        canonical_smiles="CCc1ccccc1",
    )

    rows = await primary_sources.search_pubchem_genus(
        compound,
        client_factory=FakeClient,
    )

    assert [row["publication_number"] for row in rows] == [
        "EP1234567A1",
        "US20250001234A1",
    ]
    evidence = rows[0]["genus_matches"][0]
    assert evidence["query_sha256"] == hashlib.sha256(b"c1ccccc1").hexdigest()
    assert "c1ccccc1" not in repr(rows)
    assert evidence["artifact_locator"].endswith(evidence["result_sha256"])


@pytest.mark.asyncio
async def test_genus_lane_fails_closed_when_compound_cap_is_saturated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SaturatedClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def substructure_search_cids(self, *_args, **_kwargs):
            return [11, 22]

        async def get_patent_links_for_cids(self, _cids):
            raise AssertionError("truncated compound set must not be mapped")

    monkeypatch.setattr(
        primary_sources,
        "get_settings",
        lambda: SimpleNamespace(
            pubchem_genus_max_compounds=2,
            pubchem_genus_max_patents=100,
            pubchem_genus_max_seconds=60,
            search_allowed_jurisdictions=["US"],
        ),
    )

    with pytest.raises(SourceUnavailableError, match="compound cap"):
        await primary_sources.search_pubchem_genus(
            SimpleNamespace(
                compound_type="small_molecule",
                scaffold_smiles="c1ccccc1",
                canonical_smiles="CCc1ccccc1",
            ),
            client_factory=SaturatedClient,
        )


@pytest.mark.asyncio
async def test_genus_lane_refines_saturated_scaffold_with_canonical_structure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class RefiningClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def substructure_search_cids(self, smiles, *_args, **_kwargs):
            calls.append(smiles)
            return [11, 22] if smiles == "c1ccccc1" else [33]

        async def get_patent_links_for_cids(self, cids):
            assert cids == [33]
            return [{"cid": 33, "patent_ids": ["US20250001234A1"]}]

    monkeypatch.setattr(
        primary_sources,
        "get_settings",
        lambda: SimpleNamespace(
            pubchem_genus_max_compounds=2,
            pubchem_genus_max_patents=100,
            pubchem_genus_max_seconds=60,
            search_allowed_jurisdictions=["US"],
        ),
    )

    rows = await primary_sources.search_pubchem_genus(
        SimpleNamespace(
            compound_type="small_molecule",
            scaffold_smiles="c1ccccc1",
            canonical_smiles="CCc1ccccc1",
        ),
        client_factory=RefiningClient,
    )

    assert calls == ["c1ccccc1", "CCc1ccccc1"]
    assert rows[0]["genus_matches"][0]["query_role"] == ("canonical_refinement_after_scaffold_cap")
    assert rows[0]["genus_matches"][0]["query_sha256"] == hashlib.sha256(b"CCc1ccccc1").hexdigest()
    PatentHit(
        patent_id=rows[0]["publication_number"],
        sources=[PatentSource.PUBCHEM_GENUS],
        genus_matches=rows[0]["genus_matches"],
    )


def test_genus_evidence_merges_into_existing_hit() -> None:
    hit = PatentHit(
        patent_id="US123A1",
        sources=[PatentSource.PUBCHEM],
    )
    digest = "a" * 64
    row = {
        "publication_number": "US123A1",
        "genus_matches": [
            {
                "query_sha256": "b" * 64,
                "query_role": "murcko_scaffold",
                "matched_pubchem_cid": 11,
                "result_sha256": digest,
                "retrieved_at": "2026-07-26T12:00:00Z",
                "artifact_locator": (
                    "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/"
                    f"cid/11/xrefs/PatentID/JSON#sha256={digest}"
                ),
            }
        ],
    }

    _merge_supplementary_rows(
        [row],
        PatentSource.PUBCHEM_GENUS,
        [hit],
        {"US123A"},
        {"US123A": {PatentSource.PUBCHEM_GENUS}},
    )

    assert PatentSource.PUBCHEM_GENUS in hit.sources
    assert hit.match_type == "substructure"
    assert [match.matched_pubchem_cid for match in hit.genus_matches] == [11]

    with pytest.raises(ValidationError):
        hit.genus_matches[0].model_copy(
            update={"artifact_locator": "https://example.com/unbound"}
        ).__class__.model_validate(
            {
                **hit.genus_matches[0].model_dump(),
                "artifact_locator": "https://example.com/unbound",
            }
        )


def test_genus_coverage_fails_closed_even_under_best_effort() -> None:
    summary = SearchExecutionSummary(
        health=SourceHealth(
            entries=[
                SourceHealthEntry(
                    source="pubchem_sdq",
                    status=SourceStatus.OK,
                    patent_count=10,
                ),
                SourceHealthEntry(
                    source="bigquery",
                    status=SourceStatus.OK,
                    patent_count=10,
                ),
                SourceHealthEntry(
                    source="pubchem_genus",
                    status=SourceStatus.FAILED,
                    error_message="source search failed: SourceUnavailableError",
                ),
            ]
        ),
        failures={"pubchem_genus": "source search failed: SourceUnavailableError"},
    )

    required = _required_failures_for_policy(
        summary=summary,
        settings=SimpleNamespace(
            source_failure_policy="best_effort",
            search_enable_pubchem_genus=True,
        ),
        compound_type="small_molecule",
    )

    assert required == {
        "coverage:genus_expansion": ("pubchem_genus: source search failed: SourceUnavailableError")
    }
