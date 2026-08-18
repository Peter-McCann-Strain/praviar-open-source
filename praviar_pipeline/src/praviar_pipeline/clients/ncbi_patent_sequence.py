"""NCBI BLAST adapter for protein sequences in the GenBank Patent division."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from praviar_pipeline.clients.base import AsyncClientMixin
from praviar_pipeline.clients.http_identity import (
    optional_contact_parameter,
    source_user_agent,
)
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.utils.http_bodies import read_bounded_response_body

BASE_URL = "https://blast.ncbi.nlm.nih.gov"
BLAST_PATH = "/Blast.cgi"
PATENT_PROTEIN_DATABASE = "pat"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_RID_PATTERN = re.compile(r"\bRID\s*=\s*([A-Z0-9-]+)")
_RTOE_PATTERN = re.compile(r"\bRTOE\s*=\s*(\d+)")
_PATENT_TITLE_PATTERN = re.compile(
    r"\bpatent\s+([A-Z]{2})\s*[/|,:;-]?\s*([0-9][0-9A-Z./-]*)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class _QuerySearchContext:
    query_number: int
    metadata: dict[str, Any]
    query_length: int
    raw_hits: list[Any]


@dataclass(frozen=True, slots=True)
class _HitContext:
    descriptions: list[Any]
    best_hsp: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _HSPMetrics:
    identity: float
    query_coverage: float


class NCBIPatentSequenceClient(AsyncClientMixin):
    """Search public GSRS protein subunits against NCBI patent proteins."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._external_client = client is not None
        settings = get_settings()
        self._source_contact_email = settings.source_contact_email
        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(
                max(settings.http_timeout_default, 60.0),
                connect=settings.http_connect_timeout,
            ),
            limits=httpx.Limits(
                max_connections=2,
                max_keepalive_connections=2,
            ),
            headers={"User-Agent": source_user_agent(settings.source_contact_email)},
        )

    async def close(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    async def search_protein_patents(
        self,
        sequences: list[str],
        *,
        allowed_jurisdictions: list[str],
        max_hits: int,
        min_identity: float,
        min_query_coverage: float,
        max_polls: int,
        poll_interval_seconds: float,
    ) -> list[dict[str, Any]]:
        """Return patent rows with content-addressed BLAST match evidence."""
        distinct_sequences = list(dict.fromkeys(sequences))
        if not distinct_sequences:
            raise SourceUnavailableError(
                "ncbi_patent_sequence",
                "no public FDA GSRS protein subunit sequence is available",
            )
        if len(distinct_sequences) > 20:
            raise SourceUnavailableError(
                "ncbi_patent_sequence",
                "protein subunit count exceeds the bounded search limit",
            )

        query_metadata = {
            index: {
                "sha256": hashlib.sha256(sequence.encode("ascii")).hexdigest(),
                "length": len(sequence),
            }
            for index, sequence in enumerate(distinct_sequences, start=1)
        }
        fasta = "\n".join(
            f">subunit_{index}\n{sequence}"
            for index, sequence in enumerate(distinct_sequences, start=1)
        )
        submission = await self._request(
            "POST",
            data={
                "CMD": "Put",
                "PROGRAM": "blastp",
                "DATABASE": PATENT_PROTEIN_DATABASE,
                "QUERY": fasta,
                "HITLIST_SIZE": str(max_hits),
                "SHORT_QUERY_ADJUST": "true",
                "tool": "Praviar",
                **optional_contact_parameter(self._source_contact_email),
            },
        )
        rid, estimated_seconds = _parse_submission_receipt(submission)
        await asyncio.sleep(max(10.0, float(estimated_seconds)))

        result_text = ""
        for attempt in range(max_polls):
            result_text = await self._request(
                "GET",
                params={
                    "CMD": "Get",
                    "RID": rid,
                    "FORMAT_TYPE": "JSON2_S",
                    "HITLIST_SIZE": str(max_hits),
                    "tool": "Praviar",
                    **optional_contact_parameter(self._source_contact_email),
                },
            )
            if result_text.lstrip().startswith("{"):
                break
            status = _parse_pending_status(result_text)
            if status in {"FAILED", "UNKNOWN"}:
                raise SourceUnavailableError(
                    "ncbi_patent_sequence",
                    f"NCBI BLAST request entered terminal status {status.lower()}",
                )
            if status != "WAITING" or attempt + 1 >= max_polls:
                raise SourceUnavailableError(
                    "ncbi_patent_sequence",
                    "NCBI BLAST request did not complete within the bounded polling window",
                )
            await asyncio.sleep(poll_interval_seconds)

        try:
            payload = json.loads(result_text)
        except (TypeError, ValueError):
            raise SourceUnavailableError(
                "ncbi_patent_sequence",
                "NCBI BLAST result parsing failed",
            ) from None
        if not isinstance(payload, dict):
            raise SourceUnavailableError(
                "ncbi_patent_sequence",
                "NCBI BLAST returned an invalid result envelope",
            )
        return _result_rows(
            payload,
            rid=rid,
            query_metadata=query_metadata,
            allowed_jurisdictions={value.upper() for value in allowed_jurisdictions},
            min_identity=min_identity,
            min_query_coverage=min_query_coverage,
        )

    async def _request(
        self,
        method: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
    ) -> str:
        try:
            async with self._client.stream(
                method,
                BLAST_PATH,
                params=params,
                data=data,
            ) as response:
                if response.status_code >= 400:
                    raise SourceUnavailableError(
                        "ncbi_patent_sequence",
                        "NCBI BLAST request failed",
                        status_code=response.status_code,
                    )
                body = await read_bounded_response_body(
                    response,
                    max_bytes=MAX_RESPONSE_BYTES,
                    source="ncbi_patent_sequence",
                    detail="NCBI BLAST response exceeded the configured size bound",
                )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise SourceUnavailableError(
                "ncbi_patent_sequence",
                "NCBI BLAST transport failure",
            ) from exc
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError:
            raise SourceUnavailableError(
                "ncbi_patent_sequence",
                "NCBI BLAST response was not UTF-8",
            ) from None


def _parse_submission_receipt(payload: str) -> tuple[str, int]:
    rid_match = _RID_PATTERN.search(payload)
    rtoe_match = _RTOE_PATTERN.search(payload)
    if rid_match is None or rtoe_match is None:
        raise SourceUnavailableError(
            "ncbi_patent_sequence",
            "NCBI BLAST submission receipt was incomplete",
        )
    return rid_match.group(1), int(rtoe_match.group(1))


def _parse_pending_status(payload: str) -> str:
    match = re.search(r"\bStatus\s*=\s*([A-Z]+)", payload, re.IGNORECASE)
    return match.group(1).upper() if match else ""


def _result_artifact_metadata(payload: dict[str, Any]) -> tuple[str, str]:
    retrieved_at = datetime.now(UTC).isoformat()
    result_sha256 = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    return retrieved_at, result_sha256


def _query_search_context(
    raw_report: object,
    *,
    report_index: int,
    query_metadata: dict[int, dict[str, Any]],
) -> _QuerySearchContext | None:
    if not isinstance(raw_report, dict):
        return None
    report = raw_report.get("report")
    results = report.get("results") if isinstance(report, dict) else None
    search = results.get("search") if isinstance(results, dict) else None
    if not isinstance(search, dict):
        return None
    query_number = _query_number(search, fallback=report_index)
    metadata = query_metadata.get(query_number)
    if metadata is None:
        return None
    query_length = int(search.get("query_len") or metadata["length"])
    raw_hits = search.get("hits")
    if not isinstance(raw_hits, list):
        return None
    return _QuerySearchContext(
        query_number=query_number,
        metadata=metadata,
        query_length=query_length,
        raw_hits=raw_hits,
    )


def _hit_context(raw_hit: object) -> _HitContext | None:
    if not isinstance(raw_hit, dict):
        return None
    descriptions = raw_hit.get("description")
    hsps = raw_hit.get("hsps")
    if not isinstance(descriptions, list) or not isinstance(hsps, list) or not hsps:
        return None
    best_hsp = max(
        (item for item in hsps if isinstance(item, dict)),
        key=lambda item: float(item.get("bit_score") or 0.0),
        default=None,
    )
    if best_hsp is None:
        return None
    return _HitContext(descriptions=descriptions, best_hsp=best_hsp)


def _hsp_metrics(best_hsp: dict[str, Any], *, query_length: int) -> _HSPMetrics:
    align_length = int(best_hsp.get("align_len") or 0)
    identity_count = int(best_hsp.get("identity") or 0)
    query_from = int(best_hsp.get("query_from") or 0)
    query_to = int(best_hsp.get("query_to") or 0)
    identity = identity_count / align_length if align_length else 0.0
    query_coverage = (abs(query_to - query_from) + 1) / query_length if query_length else 0.0
    return _HSPMetrics(identity=identity, query_coverage=query_coverage)


def _description_match(
    raw_description: object,
    *,
    hit: _HitContext,
    query: _QuerySearchContext,
    metrics: _HSPMetrics,
    rid: str,
    result_sha256: str,
    retrieved_at: str,
    allowed_jurisdictions: set[str],
) -> tuple[str, str, dict[str, Any]] | None:
    if not isinstance(raw_description, dict):
        return None
    subject_title = str(raw_description.get("title") or "").strip()
    patent_id = _patent_id_from_title(
        subject_title,
        allowed_jurisdictions=allowed_jurisdictions,
    )
    if not patent_id:
        return None
    evidence = {
        "schema_version": "ncbi-patent-sequence-match-v1",
        "program": "blastp",
        "database": PATENT_PROTEIN_DATABASE,
        "request_id": rid,
        "result_sha256": result_sha256,
        "query_subunit_index": query.query_number,
        "query_sha256": query.metadata["sha256"],
        "query_length": query.query_length,
        "subject_accession": str(
            raw_description.get("accession") or raw_description.get("id") or ""
        ).strip(),
        "subject_title": subject_title,
        "identity": metrics.identity,
        "query_coverage": min(metrics.query_coverage, 1.0),
        "evalue": float(hit.best_hsp.get("evalue") or 0.0),
        "bit_score": float(hit.best_hsp.get("bit_score") or 0.0),
        "retrieved_at": retrieved_at,
        "artifact_locator": f"{BASE_URL}{BLAST_PATH}?CMD=Get&RID={rid}",
    }
    return patent_id, subject_title, evidence


def _collect_report_matches(
    raw_report: object,
    *,
    report_index: int,
    rid: str,
    result_sha256: str,
    retrieved_at: str,
    query_metadata: dict[int, dict[str, Any]],
    allowed_jurisdictions: set[str],
    min_identity: float,
    min_query_coverage: float,
    matches_by_patent: dict[str, list[dict[str, Any]]],
    titles_by_patent: dict[str, str],
) -> None:
    query = _query_search_context(
        raw_report,
        report_index=report_index,
        query_metadata=query_metadata,
    )
    if query is None:
        return
    for raw_hit in query.raw_hits:
        hit = _hit_context(raw_hit)
        if hit is None:
            continue
        metrics = _hsp_metrics(hit.best_hsp, query_length=query.query_length)
        if metrics.identity < min_identity or metrics.query_coverage < min_query_coverage:
            continue
        for raw_description in hit.descriptions:
            match = _description_match(
                raw_description,
                hit=hit,
                query=query,
                metrics=metrics,
                rid=rid,
                result_sha256=result_sha256,
                retrieved_at=retrieved_at,
                allowed_jurisdictions=allowed_jurisdictions,
            )
            if match is None:
                continue
            patent_id, subject_title, evidence = match
            matches_by_patent[patent_id].append(evidence)
            titles_by_patent.setdefault(patent_id, subject_title)


def _sorted_result_rows(
    matches_by_patent: dict[str, list[dict[str, Any]]],
    titles_by_patent: dict[str, str],
) -> list[dict[str, Any]]:
    return [
        {
            "publication_number": patent_id,
            "title": titles_by_patent.get(patent_id, ""),
            "abstract": "",
            "sequence_matches": sorted(
                matches,
                key=lambda item: (
                    -float(item["bit_score"]),
                    int(item["query_subunit_index"]),
                    str(item["subject_accession"]),
                ),
            ),
        }
        for patent_id, matches in sorted(matches_by_patent.items())
    ]


def _result_rows(
    payload: dict[str, Any],
    *,
    rid: str,
    query_metadata: dict[int, dict[str, Any]],
    allowed_jurisdictions: set[str],
    min_identity: float,
    min_query_coverage: float,
) -> list[dict[str, Any]]:
    raw_reports = payload.get("BlastOutput2")
    if not isinstance(raw_reports, list):
        raise SourceUnavailableError(
            "ncbi_patent_sequence",
            "NCBI BLAST result did not contain BlastOutput2",
        )

    retrieved_at, result_sha256 = _result_artifact_metadata(payload)
    matches_by_patent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    titles_by_patent: dict[str, str] = {}
    for report_index, raw_report in enumerate(raw_reports, start=1):
        _collect_report_matches(
            raw_report,
            report_index=report_index,
            rid=rid,
            result_sha256=result_sha256,
            retrieved_at=retrieved_at,
            query_metadata=query_metadata,
            allowed_jurisdictions=allowed_jurisdictions,
            min_identity=min_identity,
            min_query_coverage=min_query_coverage,
            matches_by_patent=matches_by_patent,
            titles_by_patent=titles_by_patent,
        )

    return _sorted_result_rows(matches_by_patent, titles_by_patent)


def _query_number(search: dict[str, Any], *, fallback: int) -> int:
    query_text = " ".join(str(search.get(key) or "") for key in ("query_title", "query_id"))
    match = re.search(r"\bsubunit_(\d+)\b", query_text)
    return int(match.group(1)) if match else fallback


def _patent_id_from_title(
    title: str,
    *,
    allowed_jurisdictions: set[str],
) -> str:
    match = _PATENT_TITLE_PATTERN.search(title)
    if match is None:
        return ""
    jurisdiction = match.group(1).upper()
    if allowed_jurisdictions and jurisdiction not in allowed_jurisdictions:
        return ""
    number = re.sub(r"[^0-9A-Z]", "", match.group(2).upper())
    return f"{jurisdiction}{number}" if number else ""
