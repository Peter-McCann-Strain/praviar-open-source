"""Contract tests for the public NCBI patent-protein BLAST adapter."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from praviar_pipeline.clients import ncbi_patent_sequence
from praviar_pipeline.clients.ncbi_patent_sequence import NCBIPatentSequenceClient
from praviar_pipeline.errors import ConfigurationError, SourceUnavailableError
from praviar_pipeline.models.patent import PatentHit, PatentSource
from praviar_pipeline.pipeline.search.normalizers import _merge_supplementary_rows
from praviar_pipeline.pipeline.search.wiring import _search_ncbi_patent_sequence
from praviar_pipeline.utils.patent_ids import normalize_patent_id


@pytest.mark.asyncio
async def test_blast_adapter_returns_content_addressed_patent_match(
    mock_settings,
    monkeypatch,
) -> None:
    requests: list[httpx.Request] = []
    sequence = "ACDEFGHIKLMNPQRSTVWY"

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(ncbi_patent_sequence.asyncio, "sleep", no_sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            body = request.content.decode()
            assert "DATABASE=pat" in body
            assert "PROGRAM=blastp" in body
            assert "subunit_1" in body
            assert "email=" not in body
            return httpx.Response(
                200,
                text="QBlastInfoBegin\nRID = TEST-RID-123\nRTOE = 0\nQBlastInfoEnd\n",
            )
        return httpx.Response(
            200,
            json={
                "BlastOutput2": [
                    {
                        "report": {
                            "results": {
                                "search": {
                                    "query_id": "Query_1 subunit_1",
                                    "query_title": "subunit_1",
                                    "query_len": len(sequence),
                                    "hits": [
                                        {
                                            "description": [
                                                {
                                                    "id": "gb|AEN35515.1|",
                                                    "accession": "AEN35515.1",
                                                    "title": (
                                                        "Sequence 1443 from patent US 7998689"
                                                    ),
                                                }
                                            ],
                                            "hsps": [
                                                {
                                                    "bit_score": 82.5,
                                                    "evalue": 1e-20,
                                                    "identity": 19,
                                                    "align_len": 20,
                                                    "query_from": 1,
                                                    "query_to": 20,
                                                }
                                            ],
                                        }
                                    ],
                                }
                            }
                        }
                    }
                ]
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://blast.ncbi.nlm.nih.gov",
    ) as http_client:
        rows = await NCBIPatentSequenceClient(client=http_client).search_protein_patents(
            [sequence],
            allowed_jurisdictions=["US", "EP"],
            max_hits=100,
            min_identity=0.75,
            min_query_coverage=0.75,
            max_polls=1,
            poll_interval_seconds=60.0,
        )

    assert len(requests) == 2
    assert rows[0]["publication_number"] == "US7998689"
    match = rows[0]["sequence_matches"][0]
    assert match["query_sha256"] == hashlib.sha256(sequence.encode()).hexdigest()
    assert match["subject_accession"] == "AEN35515.1"
    assert len(match["result_sha256"]) == 64
    assert match["identity"] == pytest.approx(0.95)
    assert match["query_coverage"] == pytest.approx(1.0)
    assert sequence not in json.dumps(rows)


@pytest.mark.asyncio
async def test_blast_adapter_sends_only_explicit_operator_contact(
    mock_settings,
    monkeypatch,
) -> None:
    requests: list[httpx.Request] = []

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(ncbi_patent_sequence.asyncio, "sleep", no_sleep)
    monkeypatch.setenv("SOURCE_CONTACT_EMAIL", "operator@example.org")
    from praviar_pipeline.config import clear_settings_cache

    clear_settings_cache()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(
                200,
                text="QBlastInfoBegin\nRID = CONTACT-RID\nRTOE = 0\nQBlastInfoEnd\n",
            )
        return httpx.Response(200, json={"BlastOutput2": []})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://blast.ncbi.nlm.nih.gov",
    ) as http_client:
        await NCBIPatentSequenceClient(client=http_client).search_protein_patents(
            ["ACDEFGHIKLMNPQRSTVWY"],
            allowed_jurisdictions=["US"],
            max_hits=10,
            min_identity=0.75,
            min_query_coverage=0.75,
            max_polls=1,
            poll_interval_seconds=60.0,
        )

    assert len(requests) == 2
    assert "email=operator%40example.org" in requests[0].content.decode()
    assert requests[1].url.params["email"] == "operator@example.org"


@pytest.mark.asyncio
async def test_blast_adapter_fails_closed_when_job_does_not_complete(
    mock_settings,
    monkeypatch,
) -> None:
    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(ncbi_patent_sequence.asyncio, "sleep", no_sleep)
    responses = iter(
        [
            httpx.Response(
                200,
                text="QBlastInfoBegin\nRID = TEST-RID-456\nRTOE = 0\nQBlastInfoEnd\n",
            ),
            httpx.Response(200, text="Status=WAITING\n"),
        ]
    )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: next(responses)),
        base_url="https://blast.ncbi.nlm.nih.gov",
    ) as http_client:
        with pytest.raises(SourceUnavailableError, match="bounded polling window"):
            await NCBIPatentSequenceClient(client=http_client).search_protein_patents(
                ["ACDEFGHIKLMNPQRSTVWY"],
                allowed_jurisdictions=["US"],
                max_hits=10,
                min_identity=0.75,
                min_query_coverage=0.75,
                max_polls=1,
                poll_interval_seconds=60.0,
            )


@pytest.mark.asyncio
async def test_biologic_without_exact_public_sequence_fails_before_network(
    mock_settings,
) -> None:
    with pytest.raises(ConfigurationError, match="no supported public protein"):
        await _search_ncbi_patent_sequence(
            SimpleNamespace(
                compound_type="biologic",
                protein_subunit_sequences=[],
            )
        )


@pytest.mark.asyncio
async def test_blast_adapter_filters_unrequested_jurisdictions(
    mock_settings,
    monkeypatch,
) -> None:
    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(ncbi_patent_sequence.asyncio, "sleep", no_sleep)
    payload = {
        "BlastOutput2": [
            {
                "report": {
                    "results": {
                        "search": {
                            "query_title": "subunit_1",
                            "query_len": 20,
                            "hits": [
                                {
                                    "description": [
                                        {
                                            "accession": "EXAMPLE.1",
                                            "title": "Sequence 1 from patent JP 1234567",
                                        }
                                    ],
                                    "hsps": [
                                        {
                                            "bit_score": 50,
                                            "evalue": 1e-10,
                                            "identity": 20,
                                            "align_len": 20,
                                            "query_from": 1,
                                            "query_to": 20,
                                        }
                                    ],
                                }
                            ],
                        }
                    }
                }
            }
        ]
    }
    responses = iter(
        [
            httpx.Response(
                200,
                text="QBlastInfoBegin\nRID = TEST-RID-789\nRTOE = 0\nQBlastInfoEnd\n",
            ),
            httpx.Response(200, json=payload),
        ]
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: next(responses)),
        base_url="https://blast.ncbi.nlm.nih.gov",
    ) as http_client:
        rows = await NCBIPatentSequenceClient(client=http_client).search_protein_patents(
            ["ACDEFGHIKLMNPQRSTVWY"],
            allowed_jurisdictions=["US"],
            max_hits=10,
            min_identity=0.75,
            min_query_coverage=0.75,
            max_polls=1,
            poll_interval_seconds=60.0,
        )

    assert rows == []


def test_sequence_evidence_merges_into_an_existing_patent_hit(mock_settings) -> None:
    hit = PatentHit(
        patent_id="US7998689",
        sources=[PatentSource.PUBCHEM],
    )
    evidence = {
        "schema_version": "ncbi-patent-sequence-match-v1",
        "program": "blastp",
        "database": "pat",
        "request_id": "TEST-RID-123",
        "result_sha256": "b" * 64,
        "query_subunit_index": 1,
        "query_sha256": "a" * 64,
        "query_length": 20,
        "subject_accession": "AEN35515.1",
        "subject_title": "Sequence 1443 from patent US 7998689",
        "identity": 0.95,
        "query_coverage": 1.0,
        "evalue": 1e-20,
        "bit_score": 82.5,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "artifact_locator": ("https://blast.ncbi.nlm.nih.gov/Blast.cgi?CMD=Get&RID=TEST-RID-123"),
    }

    _merge_supplementary_rows(
        [{"publication_number": "US7998689", "sequence_matches": [evidence]}],
        PatentSource.NCBI_PATENT_SEQUENCE,
        [hit],
        {normalize_patent_id("US7998689")},
        {},
    )

    assert PatentSource.NCBI_PATENT_SEQUENCE in hit.sources
    assert hit.match_type == "sequence"
    assert hit.sequence_matches[0].subject_accession == "AEN35515.1"
    assert hit.sequence_matches[0].query_sha256 == "a" * 64
