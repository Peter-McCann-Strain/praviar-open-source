"""PTA and PTE extraction helpers for deterministic patent term calculation."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.models.patent import PTABreakdown

if TYPE_CHECKING:
    from datetime import date

logger = structlog.get_logger()


def extract_pta_terms(
    app_data: dict,
    meta: dict,
) -> tuple[int, PTABreakdown | None, list[str], float]:
    """Extract PTA terms and notes from ODP metadata."""
    notes: list[str] = []
    confidence_delta = 0.0
    pta_days = 0
    pta_breakdown: PTABreakdown | None = None

    pta_data = app_data.get("patentTermAdjustmentData", {})
    if pta_data:
        a_days = int(pta_data.get("aDelayQuantity", 0))
        b_days = int(pta_data.get("bDelayQuantity", 0))
        c_days = int(pta_data.get("cDelayQuantity", 0))
        overlap = int(pta_data.get("overlappingDayQuantity", 0))
        applicant_delay = int(pta_data.get("applicantDayDelayQuantity", 0))
        total = int(pta_data.get("adjustmentTotalQuantity", 0))

        pta_breakdown = PTABreakdown(
            a_delay_days=a_days,
            b_delay_days=b_days,
            c_delay_days=c_days,
            overlap_days=overlap,
            applicant_delay_days=applicant_delay,
            total_days=total,
        )
        pta_days = total
        if pta_days > 0:
            notes.append(
                f"PTA: {pta_days} days (A={a_days}, B={b_days}, C={c_days}, "
                f"overlap={overlap}, applicant delay={applicant_delay})"
            )
            confidence_delta += 0.15
    else:
        pta_raw = meta.get("patentTermAdjustmentDays", meta.get("ptaDays", 0))
        if pta_raw:
            pta_days = int(pta_raw)
            if pta_days > 0:
                notes.append(f"PTA: {pta_days} days (breakdown unavailable)")
                confidence_delta += 0.1

    return pta_days, pta_breakdown, notes, confidence_delta


async def infer_pte_days(
    patent_id: str,
    *,
    app_data: dict,
    meta: dict,
    base_expiry: date | None,
    pta_days: int,
) -> tuple[int, list[str]]:
    """Resolve PTE days from USPTO ODP metadata or PTE certificates."""
    del app_data, base_expiry, pta_days
    notes: list[str] = []
    pte_days = 0
    pte_raw = meta.get("patentTermExtensionDays", meta.get("pteDays", 0))
    if pte_raw:
        pte_days = int(pte_raw)
        if pte_days > 0:
            notes.append(f"PTE: {pte_days} days added (Hatch-Waxman, from USPTO ODP)")
            return pte_days, notes

    if pte_days != 0:
        return pte_days, notes

    from praviar_pipeline.config import get_settings
    from praviar_pipeline.utils.patent_expiry import (
        _get_pte_certificates_cache,
        _normalize_patent_number,
    )

    settings = get_settings()

    try:
        norm_num = _normalize_patent_number(patent_id)

        pte_csv_path = settings.pte_certificates_csv_path
        if pte_csv_path:
            pte_certs = await asyncio.to_thread(_get_pte_certificates_cache, pte_csv_path)
            pte_entry = pte_certs.get(norm_num)
            if pte_entry and pte_entry.get("extension_days", 0) > 0:
                pte_days = pte_entry["extension_days"]
                notes.append(
                    f"PTE: {pte_days} days (Hatch-Waxman, "
                    f"from PTE certificates: "
                    f"{pte_entry.get('extension_text', '')} "
                    f"for {pte_entry.get('tradename', 'unknown')})"
                )
                return pte_days, notes

    except Exception as exc:
        logger.warning(
            "patent_term_pte_fallback_failed",
            error_type=type(exc).__name__,
        )
        raise SourceUnavailableError(
            "patent_term_pte_fallback",
            "configured PTE fallback could not be read",
        ) from exc

    return pte_days, notes
