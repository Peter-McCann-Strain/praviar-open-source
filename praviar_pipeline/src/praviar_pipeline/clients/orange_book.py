"""FDA Orange Book client — drug-patent regulatory linkage data.

Downloads and parses the FDA Orange Book patent data to identify
which patents are listed as covering approved drug products.

Data source: https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files
Format: Tilde-delimited text files in a ZIP archive.
"""

from __future__ import annotations

import asyncio
import csv
import io
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field, model_validator

from praviar_pipeline.clients.base import cached_bytes_request
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.models.patent_term_models import OrangeBookExclusivity
from praviar_pipeline.utils.http_bodies import read_bounded_response_body
from praviar_pipeline.utils.private_artifacts import (
    atomic_write_text,
    prepare_private_output_path,
    read_private_bytes,
)

logger = structlog.get_logger()

ORANGE_BOOK_URL = "https://www.fda.gov/media/76860/download"
ORANGE_BOOK_MAX_ZIP_BYTES = 25 * 1024 * 1024
ORANGE_BOOK_MAX_MEMBER_BYTES = 50 * 1024 * 1024
ORANGE_BOOK_MAX_COMPRESSION_RATIO = 100.0

PRODUCT_HEADERS = (
    "Ingredient",
    "DF;Route",
    "Trade_Name",
    "Applicant",
    "Strength",
    "Appl_Type",
    "Appl_No",
    "Product_No",
    "TE_Code",
    "Approval_Date",
    "RLD",
    "RS",
    "Type",
    "Applicant_Full_Name",
)
PATENT_HEADERS = (
    "Appl_Type",
    "Appl_No",
    "Product_No",
    "Patent_No",
    "Patent_Expire_Date_Text",
    "Drug_Substance_Flag",
    "Drug_Product_Flag",
    "Patent_Use_Code",
    "Delist_Flag",
    "Submission_Date",
)
EXCLUSIVITY_HEADERS = (
    "Appl_Type",
    "Appl_No",
    "Product_No",
    "Exclusivity_Code",
    "Exclusivity_Date",
)
_PATENT_NUMBER_RE = re.compile(r"^(?P<number>\d{5,11})(?P<ped>\*PED)?$")


class OrangeBookEntry(BaseModel):
    """A single Orange Book patent listing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    patent_number: str = Field(pattern=r"^\d{5,11}$")
    raw_patent_number: str = Field(pattern=r"^\d{5,11}(?:\*PED)?$")
    pediatric_exclusivity: bool = False
    application_type: str = Field(pattern=r"^[AN]$")
    application_number: str = Field(pattern=r"^\d{6}$")
    product_number: str = Field(pattern=r"^\d{3}$")
    nda_number: str
    product_name: str = ""
    active_ingredient: str = ""
    dosage_form_route: str = ""
    reference_listed_drug: bool = False
    reference_standard: bool = False
    exclusivities: list[OrangeBookExclusivity] = Field(default_factory=list)
    patent_expiry: str = ""
    drug_substance_patent: bool = False
    drug_product_patent: bool = False
    patent_use_code: str = ""
    delist_requested: bool = False

    @model_validator(mode="after")
    def _validate_relational_identity(self) -> OrangeBookEntry:
        raw_base = self.raw_patent_number.removesuffix("*PED")
        if raw_base != self.patent_number:
            raise ValueError("raw_patent_number conflicts with patent_number")
        if self.raw_patent_number.endswith("*PED") != self.pediatric_exclusivity:
            raise ValueError("pediatric_exclusivity conflicts with the raw patent number")
        if self.nda_number != f"{self.application_type}{self.application_number}":
            raise ValueError("nda_number conflicts with the relational key")
        return self

    @property
    def exclusivity_codes(self) -> list[str]:
        """Compatibility projection; the paired records remain authoritative."""
        return sorted({record.code for record in self.exclusivities})

    @property
    def exclusivity_expiration_dates(self) -> list[str]:
        """Compatibility projection; the paired records remain authoritative."""
        return sorted({record.expiration_date for record in self.exclusivities})


def _normalize_patent_id(raw: str) -> str:
    """Normalize Orange Book patent number to match pipeline format.

    Orange Book uses plain numbers (e.g., '7851188').
    Pipeline uses 'US7851188B2' format. We store the plain number
    and match by stripping prefix/suffix from pipeline IDs.
    """
    cleaned = raw.strip().upper().replace(",", "").replace(" ", "")
    match = _PATENT_NUMBER_RE.fullmatch(cleaned)
    return match.group("number") if match else cleaned


def _parse_orange_book_patent_id(raw: str) -> tuple[str, bool, str]:
    """Return the base patent number, PED tag, and normalized source value."""
    normalized = raw.strip().upper().replace(",", "").replace(" ", "")
    match = _PATENT_NUMBER_RE.fullmatch(normalized)
    if match is None:
        raise SourceUnavailableError(
            "orange_book",
            "patent.txt contains an invalid Patent_No",
        )
    return match.group("number"), bool(match.group("ped")), normalized


def _extract_patent_number(pipeline_id: str) -> str:
    """Extract the numeric patent number from a pipeline patent ID.

    'US7851188B2' -> '7851188'
    'US 7,851,188 B2' -> '7851188'
    """
    # Remove country prefix, pediatric tag, kind code suffix, spaces, commas.
    cleaned = pipeline_id.strip().upper()
    cleaned = re.sub(r"^[A-Z]{2}\s*", "", cleaned)
    cleaned = re.sub(r"\*PED\s*$", "", cleaned)
    cleaned = re.sub(r"\s*[A-Z]\d?\s*$", "", cleaned)
    cleaned = cleaned.replace(",", "").replace(" ", "")
    return cleaned


class OrangeBookIndex:
    """In-memory index of Orange Book patent listings.

    Keyed by normalized patent number for O(1) lookup.
    """

    def __init__(self, entries: dict[str, list[OrangeBookEntry]]) -> None:
        self._entries = entries

    @property
    def patent_count(self) -> int:
        return len(self._entries)

    def lookup(self, pipeline_patent_id: str) -> list[OrangeBookEntry]:
        """Look up a patent by its pipeline ID (e.g., 'US7851188B2').

        Returns all Orange Book listings for that patent, or empty list.
        """
        number = _extract_patent_number(pipeline_patent_id)
        return self._entries.get(number, [])

    def is_listed(self, pipeline_patent_id: str) -> bool:
        """Check if a patent is listed in the Orange Book."""
        return len(self.lookup(pipeline_patent_id)) > 0


def _product_key(row: dict[str, str]) -> tuple[str, str, str]:
    return (
        str(row.get("Appl_Type") or "").strip().upper(),
        str(row.get("Appl_No") or "").strip(),
        str(row.get("Product_No") or "").strip(),
    )


def _parse_rows(
    content: str,
    *,
    table_name: str,
    expected_headers: tuple[str, ...],
    require_data: bool,
) -> list[dict[str, str]]:
    """Parse one FDA table and fail closed on schema or row-shape drift."""
    reader = csv.DictReader(io.StringIO(content), delimiter="~")
    if tuple(reader.fieldnames or ()) != expected_headers:
        raise SourceUnavailableError(
            "orange_book",
            f"{table_name} headers do not match the FDA schema",
        )

    rows: list[dict[str, str]] = []
    for row_number, row in enumerate(reader, start=2):
        if None in row or any(value is None for value in row.values()):
            raise SourceUnavailableError(
                "orange_book",
                f"{table_name} row {row_number} has the wrong field count",
            )
        cleaned = {str(key).strip(): str(value).strip() for key, value in row.items()}
        _validate_product_key(cleaned, table_name=table_name, row_number=row_number)
        rows.append(cleaned)

    if require_data and not rows:
        raise SourceUnavailableError(
            "orange_book",
            f"{table_name} contains no data rows",
        )
    return rows


def _validate_product_key(
    row: dict[str, str],
    *,
    table_name: str,
    row_number: int,
) -> None:
    application_type, application_number, product_number = _product_key(row)
    if (
        application_type not in {"A", "N"}
        or re.fullmatch(r"\d{6}", application_number) is None
        or re.fullmatch(r"\d{3}", product_number) is None
    ):
        raise SourceUnavailableError(
            "orange_book",
            f"{table_name} row {row_number} has an invalid relational key",
        )


def _validate_flag(
    row: dict[str, str],
    field_name: str,
    *,
    table_name: str,
    row_number: int,
    allowed: frozenset[str],
) -> None:
    if row[field_name].upper() not in allowed:
        raise SourceUnavailableError(
            "orange_book",
            f"{table_name} row {row_number} has an invalid {field_name}",
        )


def _validate_date(
    value: str,
    *,
    table_name: str,
    row_number: int,
    field_name: str,
    required: bool,
) -> None:
    if not value and not required:
        return
    try:
        datetime.strptime(value, "%b %d, %Y")
    except ValueError:
        raise SourceUnavailableError(
            "orange_book",
            f"{table_name} row {row_number} has an invalid {field_name}",
        ) from None


def _parse_patent_file(
    content: str,
    *,
    products_content: str = "",
    exclusivity_content: str = "",
) -> dict[str, list[OrangeBookEntry]]:
    """Parse the Orange Book patent.txt tilde-delimited file.

    Expected columns (tilde-delimited):
    Appl_Type~Appl_No~Product_No~Patent_No~Patent_Expire_Date_Text~
    Drug_Substance_Flag~Drug_Product_Flag~Patent_Use_Code~Delist_Flag~...
    """
    patent_rows = _parse_rows(
        content,
        table_name="patent.txt",
        expected_headers=PATENT_HEADERS,
        require_data=True,
    )
    product_rows = _parse_rows(
        products_content,
        table_name="products.txt",
        expected_headers=PRODUCT_HEADERS,
        require_data=True,
    )
    exclusivity_rows = _parse_rows(
        exclusivity_content,
        table_name="exclusivity.txt",
        expected_headers=EXCLUSIVITY_HEADERS,
        require_data=False,
    )

    entries: dict[str, list[OrangeBookEntry]] = {}
    products_by_key: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for row_number, row in enumerate(product_rows, start=2):
        _validate_flag(
            row,
            "RLD",
            table_name="products.txt",
            row_number=row_number,
            allowed=frozenset({"", "YES", "NO"}),
        )
        _validate_flag(
            row,
            "RS",
            table_name="products.txt",
            row_number=row_number,
            allowed=frozenset({"", "YES", "NO"}),
        )
        products_by_key.setdefault(_product_key(row), []).append(row)

    exclusivity_by_key: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for row_number, row in enumerate(exclusivity_rows, start=2):
        key = _product_key(row)
        if key not in products_by_key:
            raise SourceUnavailableError(
                "orange_book",
                f"exclusivity.txt row {row_number} has no matching product",
            )
        if not row["Exclusivity_Code"]:
            raise SourceUnavailableError(
                "orange_book",
                f"exclusivity.txt row {row_number} has no Exclusivity_Code",
            )
        _validate_date(
            row["Exclusivity_Date"],
            table_name="exclusivity.txt",
            row_number=row_number,
            field_name="Exclusivity_Date",
            required=True,
        )
        exclusivity_by_key.setdefault(key, []).append(row)

    for row_number, row in enumerate(patent_rows, start=2):
        key = _product_key(row)
        products = products_by_key.get(key)
        if not products:
            raise SourceUnavailableError(
                "orange_book",
                f"patent.txt row {row_number} has no matching product",
            )

        patent_no, pediatric_exclusivity, raw_patent_no = _parse_orange_book_patent_id(
            row["Patent_No"]
        )
        _validate_date(
            row["Patent_Expire_Date_Text"],
            table_name="patent.txt",
            row_number=row_number,
            field_name="Patent_Expire_Date_Text",
            required=True,
        )
        _validate_date(
            row["Submission_Date"],
            table_name="patent.txt",
            row_number=row_number,
            field_name="Submission_Date",
            required=False,
        )
        for field_name in (
            "Drug_Substance_Flag",
            "Drug_Product_Flag",
            "Delist_Flag",
        ):
            _validate_flag(
                row,
                field_name,
                table_name="patent.txt",
                row_number=row_number,
                allowed=frozenset({"", "Y", "N"}),
            )

        paired_exclusivities = [
            OrangeBookExclusivity(
                code=exclusivity["Exclusivity_Code"],
                expiration_date=exclusivity["Exclusivity_Date"],
            )
            for exclusivity in exclusivity_by_key.get(key, [])
        ]
        for product in products:
            entry = OrangeBookEntry(
                patent_number=patent_no,
                raw_patent_number=raw_patent_no,
                pediatric_exclusivity=pediatric_exclusivity,
                application_type=key[0],
                application_number=key[1],
                product_number=key[2],
                nda_number=f"{key[0]}{key[1]}",
                product_name=product["Trade_Name"],
                active_ingredient=product["Ingredient"],
                dosage_form_route=product["DF;Route"],
                reference_listed_drug=product["RLD"].upper() == "YES",
                reference_standard=product["RS"].upper() == "YES",
                exclusivities=paired_exclusivities,
                patent_expiry=row["Patent_Expire_Date_Text"],
                drug_substance_patent=row["Drug_Substance_Flag"].upper() == "Y",
                drug_product_patent=row["Drug_Product_Flag"].upper() == "Y",
                patent_use_code=row["Patent_Use_Code"],
                delist_requested=row["Delist_Flag"].upper() == "Y",
            )
            entries.setdefault(patent_no, []).append(entry)

    return entries


def _extract_orange_book_files(archive_bytes: bytes) -> dict[str, str]:
    """Extract the three relational Orange Book tables from an untrusted ZIP."""
    if len(archive_bytes) > ORANGE_BOOK_MAX_ZIP_BYTES:
        raise SourceUnavailableError("orange_book", "ZIP body exceeded byte limit")

    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            extracted: dict[str, str] = {}
            for expected_name in ("patent.txt", "products.txt", "exclusivity.txt"):
                candidates = [
                    info
                    for info in archive.infolist()
                    if Path(info.filename).name.casefold() == expected_name
                ]
                if len(candidates) != 1:
                    raise SourceUnavailableError(
                        "orange_book",
                        f"ZIP must contain exactly one {expected_name} member",
                    )
                member = candidates[0]
                if member.flag_bits & 0x1:
                    raise SourceUnavailableError("orange_book", "encrypted ZIP member rejected")
                if member.file_size > ORANGE_BOOK_MAX_MEMBER_BYTES:
                    raise SourceUnavailableError(
                        "orange_book", "ZIP member exceeded uncompressed byte limit"
                    )
                if member.file_size and member.compress_size <= 0:
                    raise SourceUnavailableError(
                        "orange_book", "ZIP member compression ratio invalid"
                    )
                if (
                    member.file_size / max(member.compress_size, 1)
                    > ORANGE_BOOK_MAX_COMPRESSION_RATIO
                ):
                    raise SourceUnavailableError(
                        "orange_book", "ZIP member compression ratio exceeded"
                    )

                payload = bytearray()
                with archive.open(member, "r") as member_file:
                    while True:
                        chunk = member_file.read(1024 * 1024)
                        if not chunk:
                            break
                        if len(payload) + len(chunk) > ORANGE_BOOK_MAX_MEMBER_BYTES:
                            raise SourceUnavailableError(
                                "orange_book",
                                "ZIP member exceeded uncompressed byte limit",
                            )
                        payload.extend(chunk)
                extracted[expected_name] = bytes(payload).decode("utf-8")
    except SourceUnavailableError:
        raise
    except (
        OSError,
        UnicodeDecodeError,
        ValueError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
    ):
        raise SourceUnavailableError("orange_book", "ZIP parsing failed") from None

    return extracted


async def load_orange_book(cache_path: Path | None = None) -> OrangeBookIndex:
    """Load the Orange Book patent index.

    Downloads from FDA if no cached copy exists. Caches to disk
    for subsequent runs.

    Args:
        cache_path: Optional path to cache the downloaded ZIP.
                    Defaults to a temp directory.
    """
    if cache_path is None:
        import tempfile

        cache_path = (
            Path(tempfile.gettempdir())
            / f"praviar-{os.getuid() if hasattr(os, 'getuid') else 'user'}"
            / "orange_book"
            / "patent.txt"
        )
    cache_path = prepare_private_output_path(cache_path)

    # Use cached file if it exists and is recent enough
    settings = get_settings()
    products_cache_path = cache_path.with_name("products.txt")
    exclusivity_cache_path = cache_path.with_name("exclusivity.txt")
    if cache_path.exists() and products_cache_path.exists() and exclusivity_cache_path.exists():
        import time

        age_days = (time.time() - cache_path.lstat().st_mtime) / 86400
        if age_days < settings.orange_book_cache_max_age_days:
            logger.info("orange_book_cache_hit", age_days=round(age_days, 1))

            def _read_cached() -> dict[str, str]:
                return {
                    "patent.txt": read_private_bytes(
                        cache_path,
                        max_bytes=ORANGE_BOOK_MAX_MEMBER_BYTES,
                    ).decode("utf-8"),
                    "products.txt": read_private_bytes(
                        products_cache_path,
                        max_bytes=ORANGE_BOOK_MAX_MEMBER_BYTES,
                    ).decode("utf-8"),
                    "exclusivity.txt": read_private_bytes(
                        exclusivity_cache_path,
                        max_bytes=ORANGE_BOOK_MAX_MEMBER_BYTES,
                    ).decode("utf-8"),
                }

            try:
                contents = await asyncio.to_thread(_read_cached)
            except UnicodeDecodeError:
                raise SourceUnavailableError(
                    "orange_book",
                    "cached FDA tables are not valid UTF-8",
                ) from None
            entries = _parse_patent_file(
                contents["patent.txt"],
                products_content=contents["products.txt"],
                exclusivity_content=contents["exclusivity.txt"],
            )
            return OrangeBookIndex(entries)

    # Download fresh copy
    logger.info("orange_book_downloading")

    async def _download() -> bytes:
        async with (
            httpx.AsyncClient(timeout=settings.http_timeout_long) as client,
            client.stream("GET", ORANGE_BOOK_URL) as response,
        ):
            response.raise_for_status()
            return await read_bounded_response_body(
                response,
                max_bytes=ORANGE_BOOK_MAX_ZIP_BYTES,
                source="orange_book",
                detail="ZIP body exceeded byte limit",
            )

    archive_bytes = await cached_bytes_request(
        source="orange_book",
        method="GET",
        url=ORANGE_BOOK_URL,
        body=None,
        call=_download,
    )
    if len(archive_bytes) > ORANGE_BOOK_MAX_ZIP_BYTES:
        raise SourceUnavailableError("orange_book", "cached ZIP exceeded byte limit")

    def _extract_and_cache() -> dict[str, str]:
        contents = _extract_orange_book_files(archive_bytes)
        atomic_write_text(cache_path, contents["patent.txt"], encoding="utf-8")
        atomic_write_text(
            products_cache_path,
            contents["products.txt"],
            encoding="utf-8",
        )
        atomic_write_text(
            exclusivity_cache_path,
            contents["exclusivity.txt"],
            encoding="utf-8",
        )
        return contents

    contents = await asyncio.to_thread(_extract_and_cache)
    logger.info("orange_book_cached")

    entries = _parse_patent_file(
        contents["patent.txt"],
        products_content=contents["products.txt"],
        exclusivity_content=contents["exclusivity.txt"],
    )
    logger.info("orange_book_loaded", patents=len(entries))
    return OrangeBookIndex(entries)
