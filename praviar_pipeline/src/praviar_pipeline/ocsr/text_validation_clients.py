"""External lookup helpers for OCSR text validation."""

from __future__ import annotations

from urllib.parse import quote

import httpx
import structlog
from aiolimiter import AsyncLimiter

from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

logger = structlog.get_logger()


def _get_pubchem_limiter() -> AsyncLimiter:
    """Create the shared PubChem limiter from runtime settings."""
    try:
        from praviar_pipeline.config import get_settings

        rate = get_settings().pubchem_requests_per_second
    except Exception:
        rate = 5.0
    return AsyncLimiter(max_rate=rate, time_period=1)


_pubchem_limiter = _get_pubchem_limiter()


async def opsin_resolve(name: str, timeout: float = 10.0) -> str | None:
    """Resolve an IUPAC chemical name to SMILES via OPSIN REST API."""
    from praviar_pipeline.config import get_settings

    settings = get_settings()
    if not settings.drawing_text_validation_enabled:
        return None

    encoded_name = quote(name, safe="")
    url = f"https://opsin.ch.cam.ac.uk/opsin/{encoded_name}.smi"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                smiles = resp.text.strip()
                if smiles and not smiles.startswith("<!"):
                    logger.debug(
                        "opsin_resolved",
                    )
                    return smiles
            logger.debug("opsin_not_resolved", status=resp.status_code)
    except (httpx.HTTPError, httpx.TimeoutException, OSError) as exc:
        logger.debug(
            "opsin_request_failed",
            error_type=safe_exception_type(exc),
        )

    return None


async def _pubchem_cas_lookup(cas_number: str) -> str | None:
    """Look up a CAS number in PubChem and return canonical SMILES."""
    async with _pubchem_limiter:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound"
                    f"/name/{cas_number}/property/CanonicalSMILES/JSON"
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()
                props = data.get("PropertyTable", {}).get("Properties", [])
                if props:
                    smiles = props[0].get("CanonicalSMILES")
                    return smiles if isinstance(smiles, str) else None
        except Exception as exc:
            logger.debug(
                "pubchem_cas_lookup_failed",
                error_type=safe_exception_type(exc),
            )
    return None


async def _pubchem_inchi_lookup(inchi_key: str) -> str | None:
    """Look up an InChI key in PubChem and return canonical SMILES."""
    async with _pubchem_limiter:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound"
                    f"/inchikey/{inchi_key}/property/CanonicalSMILES/JSON"
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()
                props = data.get("PropertyTable", {}).get("Properties", [])
                if props:
                    smiles = props[0].get("CanonicalSMILES")
                    return smiles if isinstance(smiles, str) else None
        except Exception as exc:
            logger.debug(
                "pubchem_inchi_lookup_failed",
                error_type=safe_exception_type(exc),
            )
    return None


async def _pubchem_name_lookup(name: str) -> str | None:
    """Look up a chemical name in PubChem and return canonical SMILES."""
    async with _pubchem_limiter:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound"
                    f"/name/{name}/property/CanonicalSMILES/JSON"
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()
                props = data.get("PropertyTable", {}).get("Properties", [])
                if props:
                    smiles = props[0].get("CanonicalSMILES")
                    return smiles if isinstance(smiles, str) else None
        except Exception as exc:
            logger.debug(
                "pubchem_name_lookup_failed",
                error_type=safe_exception_type(exc),
            )
    return None
