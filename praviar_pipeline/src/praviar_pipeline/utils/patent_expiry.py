"""Patent expiry calculator using USPTO term evidence.

FDA Orange Book dates are retained as regulatory-listing metadata only. They
are sponsor-submitted dates and must not be treated as USPTO patent-term or PTE
evidence.
"""

from __future__ import annotations

import asyncio
import datetime
from datetime import date
from pathlib import Path
from typing import Literal

import structlog

from praviar_pipeline.config import get_settings
from praviar_pipeline.utils.patent_expiry_helpers import (
    load_orange_book_entries,
    load_pte_certificate_entries,
)
from praviar_pipeline.utils.patent_expiry_helpers import (
    normalize_patent_number as _normalize_patent_number_impl,
)
from praviar_pipeline.utils.patent_term_dates import _safe_add_years

logger = structlog.get_logger()

# Module-level caches (loaded once per process)
_orange_book_expiry_cache: dict[str, list[dict]] | None = None
_pte_certificates_cache: dict[str, dict] | None = None


def _normalize_patent_number(raw: str) -> str:
    """Normalize a patent number to plain digits for lookup.

    'US7851188B2' -> '7851188'
    'RE30577' -> 'RE30577'
    '7851188.0' -> '7851188'
    """
    return _normalize_patent_number_impl(raw)


def _load_orange_book_expiry_data(path: str) -> dict[str, list[dict]]:
    """Load Orange Book patent.txt and index by patent number.

    Returns dict mapping normalized patent number to list of entries with
    patent_expiry, patent_use_code, drug_substance, drug_product.
    """
    file_path = Path(path)
    if not file_path.exists():
        logger.warning("orange_book_patent_txt_not_found")
        return {}

    content = file_path.read_text(encoding="utf-8", errors="replace")
    entries = load_orange_book_entries(content)

    logger.info("orange_book_expiry_data_loaded", patents=len(entries))
    return entries


def _load_pte_certificates(path: str) -> dict[str, dict]:
    """Load USPTO PTE certificates CSV and index by patent number.

    Returns dict mapping normalized patent number to PTE data.
    """
    file_path = Path(path)
    if not file_path.exists():
        logger.warning("pte_certificates_not_found")
        return {}

    content = file_path.read_text(encoding="utf-8", errors="replace")
    entries = load_pte_certificate_entries(content)

    logger.info("pte_certificates_loaded", patents=len(entries))
    return entries


def _get_orange_book_cache(path: str) -> dict[str, list[dict]]:
    """Get or load the Orange Book expiry cache (singleton)."""
    global _orange_book_expiry_cache
    if _orange_book_expiry_cache is None:
        _orange_book_expiry_cache = _load_orange_book_expiry_data(path)
    return _orange_book_expiry_cache


def _get_pte_certificates_cache(path: str) -> dict[str, dict]:
    """Get or load the PTE certificates cache (singleton)."""
    global _pte_certificates_cache
    if _pte_certificates_cache is None:
        _pte_certificates_cache = _load_pte_certificates(path)
    return _pte_certificates_cache


ExpirySource = Literal["uspto_odp", "pte_certificates", "calculated"]


async def get_patent_expiry_with_extensions(patent_number: str) -> dict:
    """Get comprehensive patent expiry data with multi-source fallback.

    Uses sources in order:
    1. USPTO ODP (get_adjustment) for PTA/PTE data
    2. USPTO PTE certificates CSV for Hatch-Waxman extensions
    3. Calculated base (filing + 20 years) as final fallback

    Orange Book patent dates and use codes are returned separately as
    regulatory metadata and never influence the term calculation.

    Returns:
        dict with keys:
        - base_expiry: date | None (filing + 20 years)
        - pta_days: int (Patent Term Adjustment)
        - pte_days: int (Patent Term Extension, Hatch-Waxman)
        - pediatric_exclusivity_days: int (always zero; not patent term)
        - actual_expiry: date | None (computed final date)
        - source: ExpirySource
        - notes: list[str]
        - orange_book_expiry: date | None (if from Orange Book)
        - orange_book_pediatric_exclusivity: bool
        - patent_use_code: str (if from Orange Book)
    """
    from praviar_pipeline.clients.uspto_odp import USPTOODPClient

    settings = get_settings()
    norm_num = _normalize_patent_number(patent_number)

    result: dict = {
        "base_expiry": None,
        "pta_days": 0,
        "pte_days": 0,
        "pediatric_exclusivity_days": 0,
        "actual_expiry": None,
        "source": "calculated",
        "notes": [],
        "orange_book_expiry": None,
        "orange_book_pediatric_exclusivity": False,
        "patent_use_code": "",
    }

    # ── Source 1: USPTO ODP ──────────────────────────────────────────
    odp_pta_days = 0
    odp_pte_days = 0
    odp_has_data = False

    if settings.uspto_odp_api_key:
        try:
            async with USPTOODPClient() as client:
                app_data = await client.get_application_data(patent_number)
                if app_data:
                    meta = app_data.get("applicationMetaData", app_data)
                    filing_str = meta.get("filingDate", "")
                    if filing_str:
                        try:
                            filing_date = date.fromisoformat(filing_str[:10])
                            result["base_expiry"] = _safe_add_years(filing_date, 20)
                        except ValueError:
                            pass

                    # PTA data
                    pta_data = app_data.get("patentTermAdjustmentData", {})
                    if pta_data:
                        odp_pta_days = int(pta_data.get("adjustmentTotalQuantity", 0))
                        odp_has_data = True

                    # PTE data from ODP
                    pte_raw = meta.get("patentTermExtensionDays", meta.get("pteDays", 0))
                    if pte_raw:
                        odp_pte_days = int(pte_raw)
                        odp_has_data = True

                    if odp_has_data:
                        result["pta_days"] = odp_pta_days
                        result["pte_days"] = odp_pte_days
                        result["source"] = "uspto_odp"
                        result["notes"].append(
                            f"USPTO ODP: PTA={odp_pta_days}d, PTE={odp_pte_days}d"
                        )
        except Exception as exc:
            logger.warning(
                "patent_expiry_odp_failed",
            )
            result["notes"].append(f"USPTO ODP lookup failed: {type(exc).__name__}")

    # ── Regulatory metadata: Orange Book (never term evidence) ──────
    ob_path = settings.orange_book_patent_txt_path
    if ob_path:
        ob_data = await asyncio.to_thread(_get_orange_book_cache, ob_path)
        ob_entries = ob_data.get(norm_num, [])
        if ob_entries:
            result["orange_book_pediatric_exclusivity"] = any(
                bool(entry.get("pediatric_exclusivity")) for entry in ob_entries
            )
            # Use the first entry with a valid expiry date
            for entry in ob_entries:
                ob_expiry = entry.get("patent_expiry")
                if ob_expiry:
                    result["orange_book_expiry"] = ob_expiry
                    result["notes"].append(
                        f"Orange Book expiry: {ob_expiry.isoformat()} "
                        f"(NDA: {entry.get('nda_number', '?')})"
                    )
                    break

            # Collect use codes
            use_codes = [
                e.get("patent_use_code", "") for e in ob_entries if e.get("patent_use_code")
            ]
            if use_codes:
                result["patent_use_code"] = use_codes[0]
                result["notes"].append(f"Orange Book use codes: {', '.join(use_codes)}")

    # ── Source 2: PTE Certificates CSV ──────────────────────────────
    pte_path = settings.pte_certificates_csv_path
    if pte_path and result["pte_days"] == 0:
        pte_data = await asyncio.to_thread(_get_pte_certificates_cache, pte_path)
        pte_entry = pte_data.get(norm_num)
        if pte_entry:
            cert_days = pte_entry.get("extension_days", 0)
            if cert_days > 0:
                result["pte_days"] = cert_days
                if result["source"] in ("calculated",):
                    result["source"] = "pte_certificates"
                result["notes"].append(
                    f"PTE certificate: {cert_days}d ({pte_entry.get('extension_text', '')}) "
                    f"for {pte_entry.get('tradename', 'unknown product')}"
                )

    # ── Compute actual expiry ────────────────────────────────────────
    base = result.get("base_expiry")
    if base:
        total_adj = result["pta_days"] + result["pte_days"]
        result["actual_expiry"] = base + datetime.timedelta(days=total_adj)

    logger.info(
        "patent_expiry_resolved",
        source=result["source"],
        pta_days=result["pta_days"],
        pte_days=result["pte_days"],
    )

    return result
