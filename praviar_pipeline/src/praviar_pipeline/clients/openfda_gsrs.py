"""Fail-closed FDA GSRS identity resolution through openFDA."""

from __future__ import annotations

import json
from typing import Any, cast

import httpx
from aiolimiter import AsyncLimiter
from pydantic import BaseModel, ConfigDict, Field
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from praviar_pipeline.clients.base import AsyncClientMixin, cached_request
from praviar_pipeline.clients.http_identity import source_user_agent
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.utils.http_bodies import read_bounded_response_body

BASE_URL = "https://api.fda.gov"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def _is_retryable_error(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    return isinstance(exc, SourceUnavailableError) and (
        exc.status_code is None or exc.status_code == 429 or exc.status_code >= 500
    )


class GSRSBiologicIdentity(BaseModel):
    """Validated identity receipt from the FDA GSRS name and substance indexes."""

    model_config = ConfigDict(extra="forbid")

    preferred_name: str
    aliases: list[str] = Field(default_factory=list)
    unii: str
    uuid: str
    substance_class: str
    definition_type: str
    definition_level: str
    record_version: str
    names_last_updated: str
    record_last_updated: str
    protein_type: str = ""
    protein_sub_type: str = ""
    sequence_origin: str = ""
    sequence_type: str = ""
    protein_subunit_sequences: list[str] = Field(default_factory=list, max_length=20)


class OpenFDAGSRSClient(AsyncClientMixin):
    """Resolve an exact biologic name to one primary, complete FDA GSRS record."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._external_client = client is not None
        settings = get_settings()
        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(
                settings.http_timeout_default,
                connect=settings.http_connect_timeout,
            ),
            limits=httpx.Limits(
                max_connections=settings.http_max_connections,
                max_keepalive_connections=settings.http_max_keepalive,
            ),
            headers={"User-Agent": source_user_agent(settings.source_contact_email)},
        )
        self._limiter = AsyncLimiter(
            max_rate=settings.openfda_requests_per_second,
            time_period=1,
        )

    async def close(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    async def resolve_exact_biologic(self, name: str) -> GSRSBiologicIdentity | None:
        """Return one exact-name, primary/complete GSRS protein record or ``None``."""
        normalized_name = _normalize_name(name)
        if not normalized_name:
            return None
        # The openFDA UNII exact-match index stores substance names in uppercase.
        escaped_name = _escape_openfda_term(name.strip().upper())
        names_payload = await self._get(
            "/other/unii.json",
            params={
                "search": f'substance_name.exact:"{escaped_name}"',
                "limit": "10",
            },
            semantic_not_found=True,
        )
        if not names_payload:
            return None

        exact_name_rows = [
            row
            for row in _result_rows(names_payload)
            if _normalize_name(str(row.get("substance_name", ""))) == normalized_name
        ]
        unique_uniis = {
            str(row.get("unii", "")).strip().upper()
            for row in exact_name_rows
            if str(row.get("unii", "")).strip()
        }
        if len(unique_uniis) != 1:
            return None
        unii = next(iter(unique_uniis))

        record_payload = await self._get(
            "/other/substance.json",
            params={"search": f'unii:"{_escape_openfda_term(unii)}"', "limit": "10"},
            semantic_not_found=True,
        )
        if not record_payload:
            return None
        records = [
            row
            for row in _result_rows(record_payload)
            if str(row.get("unii", "")).strip().upper() == unii
            and str(row.get("substance_class", "")).strip() == "protein"
            and str(row.get("definition_type", "")).strip().upper() == "PRIMARY"
            and str(row.get("definition_level", "")).strip().upper() == "COMPLETE"
        ]
        unique_records = {
            str(row.get("uuid", "")).strip(): row
            for row in records
            if str(row.get("uuid", "")).strip()
        }
        if len(unique_records) != 1:
            return None
        record = next(iter(unique_records.values()))

        names = _record_names(record)
        if normalized_name not in {_normalize_name(value) for value in names}:
            return None
        display_names = [
            str(row.get("name", "")).strip()
            for row in record.get("names", [])
            if isinstance(row, dict)
            and row.get("display_name") is True
            and str(row.get("name", "")).strip()
        ]
        preferred_name = display_names[0] if len(display_names) == 1 else name.strip()
        raw_protein = record.get("protein")
        protein: dict[str, Any] = raw_protein if isinstance(raw_protein, dict) else {}
        protein_subunit_sequences = _protein_subunit_sequences(protein)

        return GSRSBiologicIdentity(
            preferred_name=preferred_name,
            aliases=[value for value in names if _normalize_name(value) != normalized_name][:20],
            unii=unii,
            uuid=str(record["uuid"]).strip(),
            substance_class="protein",
            definition_type="PRIMARY",
            definition_level="COMPLETE",
            record_version=str(record.get("version", "")).strip(),
            names_last_updated=_last_updated(names_payload),
            record_last_updated=_last_updated(record_payload),
            protein_type=str(protein.get("protein_type", "")).strip(),
            protein_sub_type=str(protein.get("protein_sub_type", "")).strip(),
            sequence_origin=str(protein.get("sequence_origin", "")).strip(),
            sequence_type=str(protein.get("sequence_type", "")).strip(),
            protein_subunit_sequences=protein_subunit_sequences,
        )

    async def _get(
        self,
        path: str,
        *,
        params: dict[str, str],
        semantic_not_found: bool,
    ) -> dict[str, Any]:
        cache_url = f"{path}?{httpx.QueryParams(params)}"
        payload = await cached_request(
            source="openfda_gsrs",
            method="GET",
            url=cache_url,
            body=None,
            call=lambda: self._get_uncached(
                path,
                params=params,
                semantic_not_found=semantic_not_found,
            ),
        )
        if not isinstance(payload, dict):
            raise SourceUnavailableError(
                "openfda_gsrs",
                "cached response has an invalid envelope",
            )
        return payload

    @retry(
        retry=retry_if_exception(_is_retryable_error),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=8),
        reraise=True,
    )
    async def _get_uncached(
        self,
        path: str,
        *,
        params: dict[str, str],
        semantic_not_found: bool,
    ) -> dict[str, Any]:
        try:
            async with (
                self._limiter,
                self._client.stream("GET", path, params=params) as response,
            ):
                if response.status_code == 404 and semantic_not_found:
                    return {}
                if response.status_code >= 400:
                    raise SourceUnavailableError(
                        "openfda_gsrs",
                        "request failed",
                        status_code=response.status_code,
                    )
                body = await read_bounded_response_body(
                    response,
                    max_bytes=MAX_RESPONSE_BYTES,
                    source="openfda_gsrs",
                    detail="response exceeded the configured size bound",
                )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise SourceUnavailableError("openfda_gsrs", "transport failure") from exc

        try:
            payload = json.loads(body)
        except (TypeError, ValueError):
            raise SourceUnavailableError(
                "openfda_gsrs",
                "response parsing failed",
            ) from None
        if not isinstance(payload, dict):
            raise SourceUnavailableError("openfda_gsrs", "invalid response envelope")
        # JSON object keys are strings; the runtime envelope check above narrows
        # the value shape while this cast records that JSON contract for mypy.
        return cast("dict[str, Any]", payload)


def _result_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("results")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _record_names(record: dict[str, Any]) -> list[str]:
    names = record.get("names")
    if not isinstance(names, list):
        return []
    values = [
        str(row.get("name", "")).strip()
        for row in names
        if isinstance(row, dict) and str(row.get("name", "")).strip()
    ]
    return list(dict.fromkeys(values))


def _last_updated(payload: dict[str, Any]) -> str:
    meta = payload.get("meta")
    return str(meta.get("last_updated", "")).strip() if isinstance(meta, dict) else ""


def _normalize_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _escape_openfda_term(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _protein_subunit_sequences(protein: dict[str, Any]) -> list[str]:
    """Extract exact public L-amino-acid subunits from an FDA GSRS protein record."""
    raw_subunits = protein.get("subunits")
    if raw_subunits is None:
        return []
    if not isinstance(raw_subunits, list):
        raise SourceUnavailableError(
            "openfda_gsrs",
            "protein subunits have an invalid envelope",
        )

    indexed_sequences: list[tuple[int, str]] = []
    allowed = frozenset("ACDEFGHIKLMNPQRSTVWYBXZJUO")
    for position, subunit in enumerate(raw_subunits, start=1):
        if not isinstance(subunit, dict):
            raise SourceUnavailableError(
                "openfda_gsrs",
                "protein subunit has an invalid envelope",
            )
        sequence = str(subunit.get("sequence", ""))
        raw_index = subunit.get("subunit_index", position)
        if (
            not sequence
            or len(sequence) > 10000
            or sequence != sequence.upper()
            or not set(sequence).issubset(allowed)
        ):
            raise SourceUnavailableError(
                "openfda_gsrs",
                "protein subunit sequence is unsupported or malformed",
            )
        try:
            subunit_index = int(raw_index)
        except (TypeError, ValueError):
            raise SourceUnavailableError(
                "openfda_gsrs",
                "protein subunit index is invalid",
            ) from None
        if subunit_index < 1:
            raise SourceUnavailableError(
                "openfda_gsrs",
                "protein subunit index is invalid",
            )
        indexed_sequences.append((subunit_index, sequence))

    indexed_sequences.sort(key=lambda item: item[0])
    return list(dict.fromkeys(sequence for _, sequence in indexed_sequences))
