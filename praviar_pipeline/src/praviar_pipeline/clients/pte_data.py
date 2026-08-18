"""USPTO Patent Term Extension (PTE) data client.

Downloads and parses PTE certificate data from two sources:

1. USPTO quarterly Excel files:
   - All-time: https://www.uspto.gov/sites/default/files/documents/pte_certs.xls
   - Last 5 years: https://www.uspto.gov/sites/default/files/documents/pte_past5years.xlsx

2. Federal Register API for early PTE notices (no auth required):
   https://www.federalregister.gov/api/v1/documents.json

PTE grants extend a US patent term to compensate for regulatory review delays,
typically for FDA-approved drugs. The extension is capped at 5 years and cannot
push the patent beyond 14 years post-approval.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import io
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import openpyxl
import structlog

from praviar_pipeline.clients.base import cached_request
from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.utils.http_bodies import read_bounded_response_body
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

logger = structlog.get_logger()

PTE_ALL_TIME_URL = "https://www.uspto.gov/sites/default/files/documents/pte_certs.xls"
PTE_PAST_5_YEARS_URL = "https://www.uspto.gov/sites/default/files/documents/pte_past5years.xlsx"
PTE_OFFICIAL_PAGE_URL = (
    "https://www.uspto.gov/patents/laws/patent-term-extension/"
    "patent-terms-extended-under-35-usc-156"
)
FEDERAL_REGISTER_API_URL = "https://www.federalregister.gov/api/v1/documents.json"
PTE_CERTIFICATE_COVERAGE_SCOPE = "all_time_issued_certificates_excluding_interim_only"
PTE_MAX_WORKBOOK_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class PTECertificateDataset:
    """Issued-certificate records plus explicit source coverage and freshness."""

    records: list[dict[str, Any]]
    source_url: str
    official_page_url: str
    coverage_scope: str
    coverage_note: str
    retrieved_at: datetime
    publisher_last_modified: str = ""


# Columns expected in the USPTO PTE Excel files.
# The actual header names vary slightly between the two files; we normalise by
# position for the all-time XLS and by name for the xlsx.
_PTE_COLUMN_ALIASES: dict[str, list[str]] = {
    "patent_number": ["Patent Number", "Patent No.", "Patent No", "PATENT NUMBER"],
    "product_name": [
        "Product Name",
        "Drug/Product Name",
        "Drug Name",
        "PRODUCT NAME",
        "Brand Name",
    ],
    "nda_bla_number": [
        "NDA/BLA Number",
        "NDA Number",
        "BLA Number",
        "NDA/BLA No.",
        "Application Number",
        "NDA/BLA",
    ],
    "extension_days": [
        "Extension (days)",
        "Extension Days",
        "Days Extended",
        "Extension",
        "Days",
    ],
    "status": ["Status", "Certificate Status", "PTE Status"],
}


def _resolve_column(headers: list[str], canonical: str) -> str | None:
    """Find the actual header name for a canonical field, or None."""
    aliases = _PTE_COLUMN_ALIASES.get(canonical, [canonical])
    headers_lower = {h.lower().strip(): h for h in headers}
    for alias in aliases:
        match = headers_lower.get(alias.lower().strip())
        if match is not None:
            return match
    return None


def _cell_text(value: Any) -> str:
    """Render spreadsheet cells without xlrd's integer-looking ``.0`` suffix."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _parse_pte_workbook(wb: openpyxl.Workbook) -> list[dict[str, Any]]:
    """Parse an openpyxl Workbook into a list of normalised PTE records.

    Handles both the all-time XLS (loaded via openpyxl read_only mode after
    xlrd fallback) and the past-5-years XLSX. Skips blank rows and header rows.
    """
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    # Find the header row -- it is the first row that contains something
    # recognisable as a patent-number header.
    header_row_idx = 0
    headers: list[str] = []
    for i, row in enumerate(rows):
        cells = [_cell_text(cell) for cell in row]
        if _resolve_column(cells, "patent_number") is not None:
            headers = cells
            header_row_idx = i
            break

    if not headers:
        return []

    # Resolve canonical column names to actual header strings
    col_map: dict[str, int] = {}
    for canonical in _PTE_COLUMN_ALIASES:
        actual = _resolve_column(headers, canonical)
        if actual is not None:
            with contextlib.suppress(ValueError):
                col_map[canonical] = headers.index(actual)

    records: list[dict[str, Any]] = []
    for row in rows[header_row_idx + 1 :]:
        cells = [_cell_text(cell) for cell in row]
        if not any(cells):
            continue  # blank row

        def _get(field: str, _cells: list[str] = cells) -> str:
            idx = col_map.get(field)
            if idx is None or idx >= len(_cells):
                return ""
            return _cells[idx]

        patent_number = _get("patent_number")
        if not patent_number or patent_number.lower() in {"patent number", "none", ""}:
            continue

        records.append(
            {
                "patent_number": patent_number,
                "product_name": _get("product_name"),
                "nda_bla_number": _get("nda_bla_number"),
                "extension_days": _get("extension_days"),
                "status": _get("status"),
            }
        )

    return records


async def _fetch_pte_records(url: str) -> tuple[list[dict[str, Any]], datetime, str]:
    """Download and parse one USPTO PTE workbook with freshness metadata."""
    logger.info("pte_downloading")

    async def _download() -> dict[str, str]:
        async with (
            httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client,
            client.stream("GET", url) as response,
        ):
            response.raise_for_status()
            body = await read_bounded_response_body(
                response,
                max_bytes=PTE_MAX_WORKBOOK_BYTES,
                source="pte_data",
                detail="workbook body exceeded byte limit",
            )
            headers = response.headers if isinstance(response.headers, Mapping) else {}
            return {
                "body_base64": base64.b64encode(body).decode("ascii"),
                "publisher_last_modified": str(headers.get("last-modified", "")),
            }

    cached = await cached_request(
        source="pte_data",
        method="GET",
        url=url,
        body=None,
        call=_download,
    )
    if not isinstance(cached, dict):
        raise SourceUnavailableError("pte_data", "cached workbook envelope is invalid")
    try:
        raw = base64.b64decode(str(cached["body_base64"]), validate=True)
        publisher_last_modified = str(cached.get("publisher_last_modified", ""))
    except (KeyError, TypeError, ValueError, binascii.Error):
        raise SourceUnavailableError("pte_data", "cached workbook envelope is malformed") from None
    if len(raw) > PTE_MAX_WORKBOOK_BYTES:
        raise SourceUnavailableError("pte_data", "cached workbook exceeded byte limit")

    retrieved_at = datetime.now(UTC)
    logger.info("pte_downloaded", bytes=len(raw))

    fallback_failure_kind: str | None = None
    fallback_failure_type: str | None = None
    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception:
        try:
            import xlrd

            book = xlrd.open_workbook(file_contents=raw)
            sheet = book.sheet_by_index(0)
            rows_raw: list[tuple[Any, ...]] = []
            for row_index in range(sheet.nrows):
                rows_raw.append(
                    tuple(sheet.cell_value(row_index, column) for column in range(sheet.ncols))
                )
            records = _parse_pte_workbook_from_rows(rows_raw)
        except ImportError as exc:
            fallback_failure_kind = "missing_parser"
            fallback_failure_type = safe_exception_type(exc)
            logger.warning("pte_xls_fallback_unavailable", error_type=fallback_failure_type)
        except Exception as exc:
            fallback_failure_kind = "parse"
            fallback_failure_type = safe_exception_type(exc)
            logger.warning(
                "pte_workbook_parse_failed",
                error_type=fallback_failure_type,
                bytes_received=len(raw),
            )
    else:
        records = _parse_pte_workbook(wb)

    if fallback_failure_kind == "missing_parser":
        raise ImportError(
            "The all-time PTE file requires the configured legacy XLS parser"
        ) from None
    if fallback_failure_kind == "parse":
        raise SourceUnavailableError("pte_data", "workbook parsing failed") from None

    logger.info("pte_parsed", records=len(records))
    return records, retrieved_at, publisher_last_modified


async def fetch_pte_certificate_dataset() -> PTECertificateDataset:
    """Fetch the USPTO's all-time list of issued 35 U.S.C. 156 certificates.

    The USPTO labels the separate past-five-year workbook as *applications* and
    says application disposition must be checked in Patent Center. It is never
    used here as certificate evidence. The official certificate list excludes
    patents that received only interim extensions under 156(d)(5) or 156(e)(2).
    """
    records, retrieved_at, publisher_last_modified = await _fetch_pte_records(PTE_ALL_TIME_URL)
    issued_records = [{**record, "status": "issued"} for record in records]
    return PTECertificateDataset(
        records=issued_records,
        source_url=PTE_ALL_TIME_URL,
        official_page_url=PTE_OFFICIAL_PAGE_URL,
        coverage_scope=PTE_CERTIFICATE_COVERAGE_SCOPE,
        coverage_note=(
            "USPTO all-time issued-certificate list; informational only and excludes "
            "patents receiving only interim extensions under 35 U.S.C. 156(d)(5) "
            "or 156(e)(2)."
        ),
        retrieved_at=retrieved_at,
        publisher_last_modified=publisher_last_modified,
    )


async def fetch_pte_certificates() -> list[dict[str, Any]]:
    """Return only all-time issued PTE certificate records.

    Use :func:`fetch_pte_applications_last_five_years` when the application
    inventory—not issued-certificate evidence—is explicitly required.

    Returns:
        List of dicts, each with keys:
          patent_number, product_name, nda_bla_number, extension_days, status.

    Raises:
        httpx.HTTPStatusError: If the download fails.
        ImportError: If the declared regulatory feature dependencies are absent.
    """
    return (await fetch_pte_certificate_dataset()).records


async def fetch_pte_applications_last_five_years(
    *,
    statuses: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch recent PTE applications, optionally filtered by disposition.

    Returned rows remain application records even when their status is
    ``granted``. Certificate evidence must come from the issued-certificate
    dataset because the USPTO directs users to Patent Center for disposition.
    """
    records, _retrieved_at, _publisher_last_modified = await _fetch_pte_records(
        PTE_PAST_5_YEARS_URL
    )
    if statuses is None:
        return records
    normalized_statuses = {status.strip().casefold() for status in statuses}
    return [
        record
        for record in records
        if str(record.get("status", "")).strip().casefold() in normalized_statuses
    ]


def _parse_pte_workbook_from_rows(rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    """Parse PTE data from a list of raw row tuples (xlrd path)."""
    if not rows:
        return []

    # Find header row
    header_row_idx = 0
    headers: list[str] = []
    for i, row in enumerate(rows):
        cells = [_cell_text(cell) for cell in row]
        if _resolve_column(cells, "patent_number") is not None:
            headers = cells
            header_row_idx = i
            break

    col_map: dict[str, int] = {}
    for canonical in _PTE_COLUMN_ALIASES:
        actual = _resolve_column(headers, canonical)
        if actual is not None:
            with contextlib.suppress(ValueError):
                col_map[canonical] = headers.index(actual)

    records: list[dict[str, Any]] = []
    for row in rows[header_row_idx + 1 :]:
        cells = [_cell_text(cell) for cell in row]
        if not any(cells):
            continue

        def _get(field: str, _cells: list[str] = cells) -> str:
            idx = col_map.get(field)
            if idx is None or idx >= len(_cells):
                return ""
            return _cells[idx]

        patent_number = _get("patent_number")
        if not patent_number or patent_number.lower() in {"patent number", "none", ""}:
            continue

        records.append(
            {
                "patent_number": patent_number,
                "product_name": _get("product_name"),
                "nda_bla_number": _get("nda_bla_number"),
                "extension_days": _get("extension_days"),
                "status": _get("status"),
            }
        )
    return records


async def search_pte_federal_register(
    drug_name: str,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Query the Federal Register API for PTE-related notices for a drug.

    Searches for documents from FDA containing the terms
    "patent term extension" and the given drug name.

    Args:
        drug_name:   Drug or product name to search for.
        max_results: Maximum number of results to return (default 10).

    Returns:
        List of dicts, each with keys:
          title, document_number, publication_date, html_url, abstract, agencies.

    Raises:
        httpx.HTTPStatusError: If the API request fails.
    """
    if not drug_name.strip():
        raise ValueError("drug_name must not be empty")

    # Build the query term: "patent term extension <drug_name>"
    term = f"patent term extension {drug_name.strip()}"

    params: dict[str, Any] = {
        "conditions[term]": term,
        "conditions[agencies][]": "food-and-drug-administration",
        "conditions[type][]": "Notice",
        "per_page": min(max_results, 100),
        "order": "newest",
        "fields[]": [
            "title",
            "document_number",
            "publication_date",
            "html_url",
            "abstract",
            "agencies",
        ],
    }

    logger.info("pte_federal_register_search")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(FEDERAL_REGISTER_API_URL, params=params)
        response.raise_for_status()

    data = response.json()
    results_raw: list[dict[str, Any]] = data.get("results", [])

    records: list[dict[str, Any]] = []
    for item in results_raw[:max_results]:
        agencies = item.get("agencies") or []
        agency_names = [a.get("name", "") for a in agencies if isinstance(a, dict)]
        records.append(
            {
                "title": item.get("title", ""),
                "document_number": item.get("document_number", ""),
                "publication_date": item.get("publication_date", ""),
                "html_url": item.get("html_url", ""),
                "abstract": item.get("abstract", ""),
                "agencies": agency_names,
            }
        )

    logger.info("pte_federal_register_results", count=len(records))
    return records
