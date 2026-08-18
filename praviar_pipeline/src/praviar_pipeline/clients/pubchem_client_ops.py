"""PubChem request orchestration helpers."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol
from urllib.parse import quote

import structlog

from praviar_pipeline.clients.pubchem_helpers import (
    extract_first_property,
    extract_info_values,
    normalize_props,
)
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import SourceUnavailableError

logger = structlog.get_logger()

PUBCHEM_PROPERTY_FIELDS = (
    "IUPACName,MolecularFormula,MolecularWeight,CanonicalSMILES,InChI,InChIKey"
)


class _PubChemClientLike(Protocol):
    _client: Any
    _limiter: Any

    async def _get(self, path: str, *, ok_on_404: bool = False) -> dict: ...


def build_property_path(kind: str, value: str) -> str:
    """Build a property lookup path for the PubChem compound endpoints."""
    encoded_value = quote(value, safe="") if kind == "name" else value
    return f"/compound/{kind}/{encoded_value}/property/{PUBCHEM_PROPERTY_FIELDS}/JSON"


async def resolve_by_name(client: _PubChemClientLike, name: str) -> dict:
    # 404 here means "PubChem has never seen this name" — semantic empty.
    data = await client._get(build_property_path("name", name), ok_on_404=True)
    if not data:
        return {}
    properties = data.get("PropertyTable", {}).get("Properties", [])
    if len(properties) > 1:
        logger.warning(
            "pubchem_multiple_compounds",
            count=len(properties),
        )
    return extract_first_property(data)


async def resolve_by_smiles(client: _PubChemClientLike, smiles: str) -> dict:
    # 404 here means "PubChem has no record for this SMILES" — semantic empty.
    data = await client._get(build_property_path("smiles", smiles), ok_on_404=True)
    if not data:
        return {}
    return extract_first_property(data)


async def resolve_by_inchikey(client: _PubChemClientLike, inchikey: str) -> dict:
    # 404 here means "PubChem has no record for this InChIKey" — semantic empty.
    data = await client._get(build_property_path("inchikey", inchikey), ok_on_404=True)
    if not data:
        return {}
    return extract_first_property(data)


async def get_synonyms(client: _PubChemClientLike, cid: int) -> list[str]:
    # 404 on /synonyms indicates the CID has no synonym record — semantic empty.
    data = await client._get(f"/compound/cid/{cid}/synonyms/JSON", ok_on_404=True)
    if not data:
        return []
    return extract_info_values(data, "Synonym")


async def get_patent_links(client: _PubChemClientLike, cid: int) -> list[str]:
    # 404 on /xrefs/PatentID indicates the CID has no linked patents — semantic empty.
    data = await client._get(f"/compound/cid/{cid}/xrefs/PatentID/JSON", ok_on_404=True)
    if not data:
        return []
    return extract_info_values(data, "PatentID")


async def get_patent_links_for_cids(
    client: _PubChemClientLike,
    cids: list[int],
    *,
    chunk_size: int = 50,
) -> list[dict]:
    """Return deterministic CID-to-patent mappings using bounded PUG requests."""
    if not cids:
        return []
    if chunk_size < 1 or chunk_size > 100:
        raise ValueError("chunk_size must be between 1 and 100")

    rows: list[dict] = []
    for offset in range(0, len(cids), chunk_size):
        chunk = cids[offset : offset + chunk_size]
        cid_path = ",".join(str(cid) for cid in chunk)
        data = await client._get(
            f"/compound/cid/{cid_path}/xrefs/PatentID/JSON",
            ok_on_404=True,
        )
        if not data:
            continue
        information = data.get("InformationList", {}).get("Information", [])
        if not isinstance(information, list):
            raise SourceUnavailableError(
                "pubchem_genus",
                "patent cross-reference response schema is invalid",
            )
        for item in information:
            if not isinstance(item, dict):
                raise SourceUnavailableError(
                    "pubchem_genus",
                    "patent cross-reference row is invalid",
                )
            cid = item.get("CID")
            patent_ids = item.get("PatentID", [])
            if not isinstance(cid, int) or not isinstance(patent_ids, list):
                raise SourceUnavailableError(
                    "pubchem_genus",
                    "patent cross-reference row fields are invalid",
                )
            rows.append(
                {
                    "cid": cid,
                    "patent_ids": [
                        str(patent_id) for patent_id in patent_ids if str(patent_id).strip()
                    ],
                }
            )
    return rows


async def substructure_search_cids(
    client: _PubChemClientLike,
    smiles: str,
    *,
    max_records: int = 200,
    max_seconds: int = 60,
) -> list[int]:
    """Search the public PubChem corpus for compounds containing ``smiles``."""
    import httpx

    if not smiles.strip():
        raise ValueError("substructure query SMILES is required")
    if max_records < 1:
        raise ValueError("max_records must be positive")

    settings = get_settings()
    encoded_smiles = quote(smiles, safe="")
    path = f"/compound/fastsubstructure/smiles/{encoded_smiles}/cids/JSON"
    async with client._limiter:
        resp = await client._client.get(
            path,
            params={
                "MaxRecords": max_records,
                "MaxSeconds": max_seconds,
                "Stereo": "ignore",
                "RingsNotEmbedded": "false",
            },
            timeout=httpx.Timeout(
                settings.http_timeout_long,
                connect=settings.http_connect_timeout,
            ),
        )
    if resp.status_code == 404:
        raise SourceUnavailableError(
            "pubchem_genus",
            f"404 on {path}",
            status_code=404,
        )
    if resp.status_code >= 400:
        raise SourceUnavailableError(
            "pubchem_genus",
            "substructure request failed",
            status_code=resp.status_code,
        )
    try:
        data = resp.json()
    except (TypeError, ValueError):
        raise SourceUnavailableError(
            "pubchem_genus",
            "substructure response parsing failed",
        ) from None
    if not isinstance(data, dict):
        raise SourceUnavailableError(
            "pubchem_genus",
            "substructure response schema is invalid",
        )
    if "Waiting" in data:
        waiting = data.get("Waiting")
        list_key = waiting.get("ListKey") if isinstance(waiting, dict) else None
        if not list_key:
            raise SourceUnavailableError(
                "pubchem_genus",
                "substructure response omitted its list key",
            )
        return await poll_list_key_cids(
            client,
            str(list_key),
            max_records=max_records,
        )
    cids = data.get("IdentifierList", {}).get("CID", [])
    if not isinstance(cids, list) or any(not isinstance(cid, int) for cid in cids):
        raise SourceUnavailableError(
            "pubchem_genus",
            "substructure result identifiers are invalid",
        )
    return cids[:max_records]


async def poll_list_key_cids(
    client: _PubChemClientLike,
    list_key: str,
    *,
    max_records: int,
    max_polls: int | None = None,
) -> list[int]:
    """Poll an asynchronous PubChem structure search and return its CIDs."""
    settings = get_settings()
    attempts = max_polls if max_polls is not None else settings.pubchem_poll_max_attempts
    for _ in range(attempts):
        await asyncio.sleep(settings.pubchem_poll_sleep_seconds)
        data = await client._get(f"/compound/listkey/{list_key}/cids/JSON")
        if "Waiting" in data:
            continue
        cids = data.get("IdentifierList", {}).get("CID", [])
        if not isinstance(cids, list) or any(not isinstance(cid, int) for cid in cids):
            raise SourceUnavailableError(
                "pubchem_genus",
                "polled substructure result identifiers are invalid",
            )
        return cids[:max_records]
    raise SourceUnavailableError(
        "pubchem_genus",
        "substructure search list-key polling timed out",
    )


async def similarity_search(
    client: _PubChemClientLike,
    smiles: str,
    *,
    threshold: float = 0.7,
    max_records: int = 50,
) -> list[dict]:
    import httpx

    settings = get_settings()
    encoded_smiles = quote(smiles, safe="")
    path = f"/compound/fastsimilarity_2d/smiles/{encoded_smiles}/cids/JSON"
    async with client._limiter:
        resp = await client._client.get(
            path,
            params={"Threshold": int(threshold * 100), "MaxRecords": max_records},
            timeout=httpx.Timeout(
                settings.http_timeout_long, connect=settings.http_connect_timeout
            ),
        )
        if resp.status_code == 404:
            # fastsimilarity_2d is a computational endpoint — a 404 is an
            # endpoint/server failure, not "no similar compounds found"
            # (empty similarity results come back as an empty CID list).
            logger.warning(
                "api_404_source_failure",
                source="pubchem",
            )
            raise SourceUnavailableError(
                "pubchem",
                f"404 on {path}",
                status_code=404,
            )
        resp.raise_for_status()
        data = resp.json()

    if "Waiting" in data:
        list_key = data["Waiting"]["ListKey"]
        return await poll_list_key(client, list_key, max_records=max_records)

    cids = data.get("IdentifierList", {}).get("CID", [])
    if not cids:
        return []
    return await get_properties_for_cids(client, cids[:max_records])


async def poll_list_key(
    client: _PubChemClientLike,
    list_key: str,
    *,
    max_records: int = 50,
    max_polls: int | None = None,
) -> list[dict]:
    settings = get_settings()
    max_polls = max_polls if max_polls is not None else settings.pubchem_poll_max_attempts
    for _ in range(max_polls):
        await asyncio.sleep(settings.pubchem_poll_sleep_seconds)
        async with client._limiter:
            listkey_path = f"/compound/listkey/{list_key}/cids/JSON"
            resp = await client._client.get(listkey_path)
            if resp.status_code == 404:
                # A 404 during listkey polling means the key is invalid or
                # expired on the PubChem side — source failure, not an
                # empty-results semantic case.
                logger.warning(
                    "api_404_source_failure",
                    source="pubchem",
                )
                raise SourceUnavailableError(
                    "pubchem",
                    f"404 on {listkey_path}",
                    status_code=404,
                )
            resp.raise_for_status()
            data = resp.json()

        if "Waiting" in data:
            continue

        cids = data.get("IdentifierList", {}).get("CID", [])
        return await get_properties_for_cids(client, cids[:max_records])

    raise SourceUnavailableError(
        "pubchem",
        f"similarity_search_list_key_timeout list_key={list_key}",
    )


async def get_properties_for_cids(client: _PubChemClientLike, cids: list[int]) -> list[dict]:
    if not cids:
        return []
    cid_str = ",".join(str(c) for c in cids)
    data = await client._get(f"/compound/cid/{cid_str}/property/{PUBCHEM_PROPERTY_FIELDS}/JSON")
    if not data:
        return []
    return [normalize_props(p) for p in data.get("PropertyTable", {}).get("Properties", [])]
