"""FDA Purple Book client -- biologic product regulatory data.

Loads and searches the FDA Purple Book (Biologics) dataset to identify
approved biologic products, their BLA numbers, reference products,
and biosimilar applications.

Data source (bundled): local CSV snapshot.
Data source (HTTP download): monthly CSV at
  https://purplebooksearch.fda.gov/files/{YEAR}/purplebook-search-{MONTH}-data-download.csv

Format: CSV file with header on row 4 (rows 1-3 are title/metadata).

Note: patent numbers are NOT in the Purple Book. Only exclusivity expiry dates
and licensure dates are present. BLA-to-patent mapping requires the Orange Book
(for small-molecule NDAs) or separate patent litigation databases.
"""

from __future__ import annotations

import asyncio
import calendar
import csv
import io
from pathlib import Path
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field

from praviar_pipeline.clients.base import cached_bytes_request
from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.utils.http_bodies import read_bounded_response_body

logger = structlog.get_logger()

PURPLE_BOOK_MAX_CSV_BYTES = 20 * 1024 * 1024

# URL pattern for monthly Purple Book downloads.
# MONTH is the full month name in lowercase (e.g. "january", "march").
PURPLE_BOOK_URL_TEMPLATE = (
    "https://purplebooksearch.fda.gov/files/{year}/purplebook-search-{month}-data-download.csv"
)

# Default path to the bundled Purple Book CSV
_DEFAULT_CSV_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent.parent.parent
    / "validation"
    / "external-datasets"
    / "purple-book"
    / "purplebook-search-march-2026.csv"
)


# ---------------------------------------------------------------------------
# Pydantic model (for callers that want validated, typed output)
# ---------------------------------------------------------------------------


class PurpleBookRecord(BaseModel):
    """Validated Purple Book entry returned by fetch_purple_book_data().

    Note: patent numbers are absent from the Purple Book data source.
    Only exclusivity and licensure dates are provided.
    """

    model_config = ConfigDict(extra="forbid")

    bla_number: str = Field(description="BLA application number")
    proprietary_name: str = Field(default="", description="Brand name (e.g. Humira)")
    proper_name: str = Field(default="", description="INN / proper name (e.g. adalimumab)")
    applicant: str = Field(default="")
    bla_type: str = Field(
        default="",
        description="351(a) for reference products, 351(k) for biosimilars",
    )
    strength: str = Field(default="")
    dosage_form: str = Field(default="")
    route: str = Field(default="")
    product_presentation: str = Field(default="")
    marketing_status: str = Field(default="")
    licensure: str = Field(default="")
    approval_date: str = Field(default="")
    ref_product_proper_name: str = Field(default="")
    ref_product_proprietary_name: str = Field(default="")
    ref_product_exclusivity_expiry: str = Field(
        default="",
        description="Reference Product Exclusivity Expiry Date (BPCIA 12-year exclusivity)",
    )
    date_of_first_licensure: str = Field(default="")
    exclusivity_expiration: str = Field(
        default="",
        description="General exclusivity expiration date",
    )
    orphan_exclusivity_expiration: str = Field(default="")
    biosimilar_designation: str = Field(
        default="",
        description="Whether the product has a biosimilar designation",
    )
    interchangeable_designation: str = Field(
        default="",
        description="Whether the product has an interchangeable designation",
    )

    @property
    def is_biosimilar(self) -> bool:
        return "351(k)" in self.bla_type

    @property
    def is_reference_product(self) -> bool:
        return "351(a)" in self.bla_type


class PurpleBookEntry(PurpleBookRecord):
    """Purple Book biologic product entry used in report regulatory data."""


class PurpleBookIndex:
    """In-memory index of Purple Book biologic product listings.

    Indexed by proper name (lowercased) and BLA number for fast lookup.
    """

    def __init__(self, entries: list[PurpleBookEntry]) -> None:
        self._entries = entries
        # Index by proper name (lowercased) -- maps to list of entries
        self._by_proper_name: dict[str, list[PurpleBookEntry]] = {}
        # Index by proprietary name (lowercased)
        self._by_proprietary_name: dict[str, list[PurpleBookEntry]] = {}
        # Index by BLA number
        self._by_bla: dict[str, list[PurpleBookEntry]] = {}

        for entry in entries:
            pn = entry.proper_name.lower().strip()
            if pn:
                self._by_proper_name.setdefault(pn, []).append(entry)
            prn = entry.proprietary_name.lower().strip()
            if prn:
                self._by_proprietary_name.setdefault(prn, []).append(entry)
            bla = entry.bla_number.strip()
            if bla:
                self._by_bla.setdefault(bla, []).append(entry)

    @property
    def product_count(self) -> int:
        return len(self._entries)

    def lookup_biologic(self, name: str) -> dict | None:
        """Search by product name (proper or proprietary) or BLA number.

        Returns a dict with product info if found, or None.
        """
        query = name.strip()
        if not query:
            return None

        query_lower = query.lower()

        # Try exact match on proper name
        entries = self._by_proper_name.get(query_lower, [])
        if not entries:
            # Try exact match on proprietary name
            entries = self._by_proprietary_name.get(query_lower, [])
        if not entries:
            # Try BLA number
            entries = self._by_bla.get(query, [])
        if not entries:
            # Try substring match on proper name
            for pn, pn_entries in self._by_proper_name.items():
                if query_lower in pn or pn in query_lower:
                    entries = pn_entries
                    break
        if not entries:
            # Try substring match on proprietary name
            for prn, prn_entries in self._by_proprietary_name.items():
                if query_lower in prn or prn in query_lower:
                    entries = prn_entries
                    break

        if not entries:
            return None

        # Find the reference product entry (351(a)) if available
        reference_entries = [e for e in entries if e.is_reference_product]
        primary = reference_entries[0] if reference_entries else entries[0]

        # Count unique biosimilar BLA numbers for this proper name
        proper_name_lower = primary.proper_name.lower().strip()
        biosimilar_blas: set[str] = set()
        for pn_entries in self._by_proper_name.values():
            for e in pn_entries:
                if e.is_biosimilar and (
                    e.ref_product_proper_name.lower().strip() == proper_name_lower
                ):
                    biosimilar_blas.add(e.bla_number)

        return {
            "product_name": primary.proprietary_name or primary.proper_name,
            "proper_name": primary.proper_name,
            "bla_number": primary.bla_number,
            "applicant": primary.applicant,
            "bla_type": primary.bla_type,
            "dosage_form": primary.dosage_form,
            "route": primary.route,
            "strength": primary.strength,
            "marketing_status": primary.marketing_status,
            "approval_date": primary.approval_date,
            "reference_product": primary.ref_product_proprietary_name or "N/A",
            "ref_product_exclusivity_expiry": primary.ref_product_exclusivity_expiry,
            "date_of_first_licensure": primary.date_of_first_licensure,
            "exclusivity_expiration": primary.exclusivity_expiration,
            "orphan_exclusivity_expiration": primary.orphan_exclusivity_expiration,
            "biosimilar_designation": primary.biosimilar_designation,
            "interchangeable_designation": primary.interchangeable_designation,
            "biosimilar_count": len(biosimilar_blas),
        }


def _parse_purple_book_csv(content: str) -> list[PurpleBookEntry]:
    """Parse the Purple Book CSV file.

    The CSV has 3 header/title rows before the actual column headers on row 4.
    """
    lines = content.splitlines()

    # Find the header row -- it contains "BLA Number"
    header_idx = 0
    for i, line in enumerate(lines):
        if "BLA Number" in line:
            header_idx = i
            break

    # Parse from header row onward
    data_text = "\n".join(lines[header_idx:])
    reader = csv.DictReader(data_text.splitlines())

    entries: list[PurpleBookEntry] = []
    for row in reader:
        bla = row.get("BLA Number", "").strip()
        if not bla:
            continue

        entry = PurpleBookEntry(
            bla_number=bla,
            proprietary_name=row.get("Proprietary Name", "").strip(),
            proper_name=row.get("Proper Name", "").strip(),
            applicant=row.get("Applicant", "").strip(),
            bla_type=row.get("BLA Type", "").strip(),
            strength=row.get("Strength", "").strip(),
            dosage_form=row.get("Dosage Form", "").strip(),
            route=row.get("Route of Administration", "").strip(),
            product_presentation=row.get("Product Presentation", "").strip(),
            marketing_status=row.get("Marketing Status", "").strip(),
            licensure=row.get("Licensure", "").strip(),
            approval_date=row.get("Approval Date", "").strip(),
            ref_product_proper_name=row.get("Ref. Product Proper Name", "").strip(),
            ref_product_proprietary_name=row.get("Ref. Product Proprietary Name", "").strip(),
            ref_product_exclusivity_expiry=row.get(
                "Ref. Product Exclusivity Exp. Date", ""
            ).strip(),
            date_of_first_licensure=row.get("Date of First Licensure", "").strip(),
            exclusivity_expiration=row.get("Exclusivity Expiration Date", "").strip(),
            orphan_exclusivity_expiration=row.get("Orphan Exclusivity Exp. Date", "").strip(),
            biosimilar_designation=row.get("Biosimilar Designation", "").strip(),
            interchangeable_designation=row.get("Interchangeable Designation", "").strip(),
        )
        entries.append(entry)

    return entries


def _parse_purple_book_csv_to_records(content: str) -> list[dict[str, Any]]:
    """Parse Purple Book CSV into raw dicts with snake_case keys.

    Used by fetch_purple_book_data() to return normalised records.
    """
    lines = content.splitlines()

    header_idx = 0
    for i, line in enumerate(lines):
        if "BLA Number" in line:
            header_idx = i
            break

    data_text = "\n".join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(data_text))

    records: list[dict[str, Any]] = []
    for row in reader:
        bla = row.get("BLA Number", "").strip()
        if not bla:
            continue
        records.append(
            {
                "bla_number": bla,
                "proprietary_name": row.get("Proprietary Name", "").strip(),
                "proper_name": row.get("Proper Name", "").strip(),
                "applicant": row.get("Applicant", "").strip(),
                "bla_type": row.get("BLA Type", "").strip(),
                "strength": row.get("Strength", "").strip(),
                "dosage_form": row.get("Dosage Form", "").strip(),
                "route": row.get("Route of Administration", "").strip(),
                "product_presentation": row.get("Product Presentation", "").strip(),
                "marketing_status": row.get("Marketing Status", "").strip(),
                "licensure": row.get("Licensure", "").strip(),
                "approval_date": row.get("Approval Date", "").strip(),
                "ref_product_proper_name": row.get("Ref. Product Proper Name", "").strip(),
                "ref_product_proprietary_name": row.get(
                    "Ref. Product Proprietary Name", ""
                ).strip(),
                "ref_product_exclusivity_expiry": row.get(
                    "Ref. Product Exclusivity Exp. Date", ""
                ).strip(),
                "date_of_first_licensure": row.get("Date of First Licensure", "").strip(),
                "exclusivity_expiration": row.get("Exclusivity Expiration Date", "").strip(),
                "orphan_exclusivity_expiration": row.get(
                    "Orphan Exclusivity Exp. Date", ""
                ).strip(),
                "biosimilar_designation": row.get("Biosimilar Designation", "").strip(),
                "interchangeable_designation": row.get("Interchangeable Designation", "").strip(),
            }
        )
    return records


# ---------------------------------------------------------------------------
# HTTP download functions (monthly CSV)
# ---------------------------------------------------------------------------


def _month_name(month: int) -> str:
    """Convert month integer (1-12) to lowercase month name."""
    return calendar.month_name[month].lower()


async def fetch_purple_book_data(year: int, month: int) -> list[dict[str, Any]]:
    """Download and parse the monthly Purple Book CSV.

    Args:
        year:  Four-digit year (e.g. 2026).
        month: Month number 1-12.

    Returns:
        List of dicts with snake_case field names. Each dict maps to the fields
        in PurpleBookRecord. Patent numbers are NOT present in Purple Book data.

    Raises:
        httpx.HTTPStatusError: If the download fails.
        ValueError: If month is outside 1-12.
    """
    if not 1 <= month <= 12:
        raise ValueError(f"month must be 1-12, got {month!r}")

    url = PURPLE_BOOK_URL_TEMPLATE.format(year=year, month=_month_name(month))
    logger.info("purple_book_downloading", year=year, month=month)

    async def _download() -> bytes:
        async with (
            httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client,
            client.stream("GET", url) as response,
        ):
            response.raise_for_status()
            return await read_bounded_response_body(
                response,
                max_bytes=PURPLE_BOOK_MAX_CSV_BYTES,
                source="purple_book",
                detail="CSV body exceeded byte limit",
            )

    raw = await cached_bytes_request(
        source="purple_book",
        method="GET",
        url=url,
        body=None,
        call=_download,
    )
    if len(raw) > PURPLE_BOOK_MAX_CSV_BYTES:
        raise SourceUnavailableError("purple_book", "cached CSV exceeded byte limit")
    content = raw.decode("utf-8", errors="replace")
    records = await asyncio.to_thread(_parse_purple_book_csv_to_records, content)
    logger.info("purple_book_fetched", year=year, month=month, records=len(records))
    return records


async def lookup_biologic_exclusivity(
    proper_name: str,
    year: int,
    month: int,
) -> dict[str, Any] | None:
    """Look up a biologic by proper name and return its exclusivity information.

    Downloads the specified monthly Purple Book release and searches for the
    given proper name (INN). Returns a dict with exclusivity fields, or None
    if no matching product is found.

    Args:
        proper_name: INN / proper name (e.g. "adalimumab").
        year:        Four-digit year of the Purple Book release to query.
        month:       Month number 1-12 of the Purple Book release.

    Returns:
        Dict with exclusivity fields, or None if not found. Keys:
          bla_number, proper_name, proprietary_name, applicant, bla_type,
          ref_product_exclusivity_expiry, date_of_first_licensure,
          exclusivity_expiration, orphan_exclusivity_expiration,
          biosimilar_designation, interchangeable_designation.
    """
    records = await fetch_purple_book_data(year, month)
    query = proper_name.strip().lower()

    # Prefer exact proper_name match; fall back to substring
    exact: list[dict[str, Any]] = [r for r in records if r["proper_name"].lower() == query]
    partial: list[dict[str, Any]] = [
        r for r in records if query in r["proper_name"].lower() or r["proper_name"].lower() in query
    ]
    candidates = exact or partial
    if not candidates:
        return None

    # Prefer reference product (351(a)) over biosimilar
    reference = [c for c in candidates if "351(a)" in c.get("bla_type", "")]
    primary = reference[0] if reference else candidates[0]

    return {
        "bla_number": primary["bla_number"],
        "proper_name": primary["proper_name"],
        "proprietary_name": primary["proprietary_name"],
        "applicant": primary["applicant"],
        "bla_type": primary["bla_type"],
        "ref_product_exclusivity_expiry": primary["ref_product_exclusivity_expiry"],
        "date_of_first_licensure": primary["date_of_first_licensure"],
        "exclusivity_expiration": primary["exclusivity_expiration"],
        "orphan_exclusivity_expiration": primary["orphan_exclusivity_expiration"],
        "biosimilar_designation": primary["biosimilar_designation"],
        "interchangeable_designation": primary["interchangeable_designation"],
    }


# ---------------------------------------------------------------------------
# Bundled-CSV index (existing API, unchanged)
# ---------------------------------------------------------------------------

# Module-level cache for the loaded index
_cached_index: PurpleBookIndex | None = None


async def load_purple_book(csv_path: Path | None = None) -> PurpleBookIndex:
    """Load the Purple Book product index from a local CSV.

    Args:
        csv_path: Optional path to the Purple Book CSV file.
                  Defaults to the bundled dataset.
    """
    global _cached_index
    if _cached_index is not None:
        return _cached_index

    if csv_path is None:
        csv_path = _DEFAULT_CSV_PATH

    if not csv_path.exists():
        logger.warning("purple_book_csv_not_found")
        _cached_index = PurpleBookIndex([])
        return _cached_index

    def _read_and_parse() -> list[PurpleBookEntry]:
        content = csv_path.read_text(encoding="utf-8-sig", errors="replace")
        return _parse_purple_book_csv(content)

    entries = await asyncio.to_thread(_read_and_parse)
    _cached_index = PurpleBookIndex(entries)
    logger.info("purple_book_loaded")
    return _cached_index


def reset_purple_book_cache() -> None:
    """Reset the module-level cache. Used in tests."""
    global _cached_index
    _cached_index = None
