"""Patent term calculator — deterministic computation of US patent expiry dates.

Implements the 20-year term rule with adjustments for PTA, PTE,
terminal disclaimers, and maintenance fee lapse.
"""

from __future__ import annotations

import datetime
from datetime import date

import httpx
import structlog

from praviar_pipeline.clients.uspto_odp import USPTOODPClient
from praviar_pipeline.errors import InsufficientDataError, SourceUnavailableError
from praviar_pipeline.models.patent import PatentTermInfo
from praviar_pipeline.utils.patent_term_helpers import (
    _effective_filing_date_from_continuity,
    _safe_add_years,
    extract_grant_date,
    extract_pta_terms,
    infer_pte_days,
    resolve_maintenance_status,
)

logger = structlog.get_logger()


async def _check_terminal_disclaimer(
    client: USPTOODPClient,
    patent_id: str,
    visited: set[str] | None = None,
    max_depth: int = 3,
) -> tuple[bool, str, date | None]:
    """Check for terminal disclaimers recursively (max depth).

    Returns (has_td, linked_patent_id, linked_expiry).
    """
    if visited is None:
        visited = set()

    if patent_id in visited or len(visited) >= max_depth:
        return False, "", None

    visited.add(patent_id)

    try:
        docs = await client.get_file_wrapper_documents(patent_id)
        for doc in docs:
            if not isinstance(doc, dict):
                raise ValueError("file-wrapper document record is malformed")
            doc_code = doc.get("documentCode", "").upper()
            doc_desc = doc.get("documentDescription", "").lower()
            if doc_code == "DIST" or "terminal disclaimer" in doc_desc:
                # Found a terminal disclaimer
                # Try to extract the linked patent from document metadata
                linked = doc.get("linkedPatentNumber", "")
                return True, linked, None
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        logger.error(
            "td_check_failed",
        )
        raise

    return False, "", None


async def calculate_patent_term(
    patent_id: str,
    legal_events: list[dict] | None = None,
    *,
    _visited: frozenset[str] | None = None,
    _max_td_depth: int = 3,
) -> PatentTermInfo:
    """Deterministic patent term calculation for a US patent.

    1. Call USPTOODPClient for application data and continuity chain
    2. Walk continuity chain for effective filing date
    3. base_expiry = effective_filing_date + 20 years
    4. Add PTA days from application data
    5. Check terminal disclaimers
    6. Check maintenance fee lapse via legal events
    """
    normalized_patent_id = patent_id.strip().upper()
    visited = _visited or frozenset()
    if normalized_patent_id in visited:
        raise InsufficientDataError(
            "Terminal-disclaimer chain contains a cycle",
            source="uspto_odp",
            step="patent_term",
        )
    if len(visited) >= _max_td_depth:
        raise InsufficientDataError(
            "Terminal-disclaimer chain exceeds the configured resolution depth",
            source="uspto_odp",
            step="patent_term",
        )
    visited = visited | {normalized_patent_id}

    notes: list[str] = []
    confidence = 0.0

    async with USPTOODPClient() as client:
        # Get application data
        try:
            app_data = await client.get_application_data(patent_id)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.error(
                "patent_term_app_data_failed",
                error_type=type(exc).__name__,
            )
            raise SourceUnavailableError(
                "uspto_odp", "patent-term application fetch failed"
            ) from exc

        if not app_data:
            raise SourceUnavailableError("uspto_odp", "patent-term application data was empty")
        if not isinstance(app_data, dict):
            raise InsufficientDataError(
                "USPTO patent-term application data was malformed",
                source="uspto_odp",
                step="patent_term",
            )

        # Get continuity data
        try:
            continuity_data = await client.get_continuity_data(patent_id)
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise SourceUnavailableError(
                "uspto_odp", "patent-term continuity fetch failed"
            ) from exc

        # Extract metadata — new ODP v3 nests under applicationMetaData
        meta = app_data.get("applicationMetaData", app_data)

        try:
            grant_date = extract_grant_date(patent_id, meta, app_data)

            # Walk continuity chain for effective filing date
            effective_filing, continuity_notes = _effective_filing_date_from_continuity(
                meta,
                continuity_data,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InsufficientDataError(
                "USPTO patent-term filing data could not be parsed",
                source="uspto_odp",
                step="patent_term",
            ) from exc
        notes.extend(continuity_notes)

        if effective_filing:
            confidence += 0.4
        else:
            raise InsufficientDataError(
                "USPTO patent-term record has no determinable effective filing date",
                source="uspto_odp",
                step="patent_term",
            )

        # Base expiry: filing + 20 years
        base_expiry: date | None = None
        if effective_filing:
            base_expiry = _safe_add_years(effective_filing, 20)
            confidence += 0.2

        # PTA (Patent Term Adjustment) — extract full breakdown from ODP v3
        try:
            pta_days, pta_breakdown, pta_notes, pta_confidence = extract_pta_terms(app_data, meta)
        except (KeyError, TypeError, ValueError) as exc:
            raise InsufficientDataError(
                "USPTO patent-term adjustment data could not be parsed",
                source="uspto_odp",
                step="patent_term",
            ) from exc
        notes.extend(pta_notes)
        confidence += pta_confidence

        # PTE (Patent Term Extension — Hatch-Waxman)
        try:
            pte_days, pte_notes = await infer_pte_days(
                patent_id,
                app_data=app_data,
                meta=meta,
                base_expiry=base_expiry,
                pta_days=pta_days,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InsufficientDataError(
                "USPTO patent-term extension data could not be parsed",
                source="uspto_odp",
                step="patent_term",
            ) from exc
        notes.extend(pte_notes)

        # Terminal disclaimer check
        has_td, td_linked, _ = await _check_terminal_disclaimer(client, patent_id)
        if has_td:
            notes.append(f"Terminal disclaimer filed (linked to {td_linked or 'unknown patent'})")

        # Resolve linked patent expiry if TD exists
        td_linked_expiry: date | None = None
        if has_td:
            if not td_linked:
                raise InsufficientDataError(
                    "Terminal disclaimer has no resolvable linked patent",
                    source="uspto_odp",
                    step="patent_term",
                )
            linked_term = await calculate_patent_term(
                td_linked,
                _visited=visited,
                _max_td_depth=_max_td_depth,
            )
            td_linked_expiry = linked_term.adjusted_expiry
            if td_linked_expiry is None:
                raise InsufficientDataError(
                    "Terminal-disclaimer linked patent has no covered expiry",
                    source="uspto_odp",
                    step="patent_term",
                )
            notes.append(f"TD linked patent {td_linked} expires {td_linked_expiry.isoformat()}")

        # Maintenance fee check — prefer USPTO ODP data over INPADOC
        maint_status, maint_next_due, maint_notes, maint_confidence = resolve_maintenance_status(
            app_data=app_data,
            legal_events=legal_events,
        )
        notes.extend(maint_notes)
        confidence += maint_confidence

        # Compute adjusted expiry
        adjusted_expiry: date | None = None
        pte_extension_base_expiry: date | None = None
        if base_expiry:
            pta_adjusted_expiry = base_expiry + datetime.timedelta(days=pta_days)
            pte_extension_base_expiry = (
                min(pta_adjusted_expiry, td_linked_expiry)
                if td_linked_expiry is not None
                else pta_adjusted_expiry
            )
            adjusted_expiry = pte_extension_base_expiry + datetime.timedelta(days=pte_days)
            confidence += 0.2

        confidence = min(confidence, 1.0)

    return PatentTermInfo(
        patent_id=patent_id,
        effective_filing_date=effective_filing,
        grant_date=grant_date,
        base_expiry=base_expiry,
        pta_days=pta_days,
        pta_breakdown=pta_breakdown,
        pte_days=pte_days,
        terminal_disclaimer=has_td,
        td_linked_patent=td_linked,
        td_linked_expiry=td_linked_expiry,
        pte_extension_base_expiry=pte_extension_base_expiry,
        maintenance_fee_status=maint_status,
        maintenance_fee_next_due=maint_next_due,
        adjusted_expiry=adjusted_expiry,
        calculation_confidence=confidence,
        calculation_notes=notes,
    )
