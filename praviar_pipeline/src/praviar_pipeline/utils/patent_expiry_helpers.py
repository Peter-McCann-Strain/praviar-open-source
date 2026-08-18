"""Pure helpers for patent expiry parsing and cache entry building."""

from __future__ import annotations

import csv
import datetime
import io
import re
from datetime import date

import structlog

logger = structlog.get_logger()


def normalize_patent_number(raw: str) -> str:
    """Normalize a patent number to plain digits for lookup.

    'US7851188B2' -> '7851188'
    'RE30577' -> 'RE30577'
    '7851188.0' -> '7851188'
    """
    cleaned = re.sub(r"^US\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\*PED\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*[A-Z]\d?\s*$", "", cleaned)
    cleaned = cleaned.replace(",", "").replace(" ", "")
    return re.sub(r"\.0$", "", cleaned)


def parse_orange_book_date(date_text: str) -> date | None:
    """Parse Orange Book date format 'MMM DD, YYYY'."""
    if not date_text or not date_text.strip():
        return None
    try:
        return datetime.datetime.strptime(date_text.strip(), "%b %d, %Y").date()
    except ValueError:
        logger.debug("orange_book_date_parse_failed")
        return None


def parse_excel_serial_date(serial: str) -> date | None:
    """Parse Excel serial date number to a Python date."""
    if not serial or not serial.strip():
        return None
    try:
        serial_num = float(serial.strip())
        if serial_num < 1:
            return None
        return date(1899, 12, 30) + datetime.timedelta(days=int(serial_num))
    except (ValueError, OverflowError):
        logger.debug("excel_date_parse_failed")
        return None


def parse_pte_extension_days(period_text: str) -> int:
    """Parse PTE extension period text to days."""
    if not period_text or not period_text.strip():
        return 0
    text = period_text.strip().lower()

    days_match = re.match(r"(\d+)\s*days?", text)
    if days_match:
        return int(days_match.group(1))

    years_match = re.match(r"(\d+)\s*years?", text)
    if years_match:
        return int(years_match.group(1)) * 365

    logger.debug("pte_extension_parse_failed")
    return 0


def build_orange_book_entry(row: dict[str, str]) -> dict[str, object]:
    """Build Orange Book regulatory metadata without deriving patent term."""
    expiry_text = row.get("Patent_Expire_Date_Text", "")
    raw_patent_number = row.get("Patent_No", "").strip().upper()
    return {
        "raw_patent_number": raw_patent_number,
        "pediatric_exclusivity": raw_patent_number.endswith("*PED"),
        "patent_expiry_text": expiry_text,
        "patent_expiry": parse_orange_book_date(expiry_text),
        "patent_use_code": row.get("Patent_Use_Code", ""),
        "drug_substance": row.get("Drug_Substance_Flag", "") == "Y",
        "drug_product": row.get("Drug_Product_Flag", "") == "Y",
        "nda_number": f"{row.get('Appl_Type', '')}{row.get('Appl_No', '')}",
        "product_name": row.get("Trade_Name", ""),
    }


def build_pte_certificate_entry(row: dict[str, str]) -> dict[str, object]:
    """Build a normalized PTE certificate entry from a CSV row."""
    extension_text = row.get("Period of Extension Granted", "")
    return {
        "tradename": row.get("Tradename of Product (generic name; if applicable)", ""),
        "original_expiry": parse_excel_serial_date(row.get("Original Expiration Date*", "")),
        "extension_days": parse_pte_extension_days(extension_text),
        "extension_text": extension_text,
    }


def load_orange_book_entries(content: str) -> dict[str, list[dict[str, object]]]:
    """Parse Orange Book patent.txt content into an index by patent number."""
    reader = csv.DictReader(io.StringIO(content), delimiter="~")
    entries: dict[str, list[dict[str, object]]] = {}
    for row in reader:
        patent_no = normalize_patent_number(row.get("Patent_No", ""))
        if not patent_no:
            continue
        entries.setdefault(patent_no, []).append(build_orange_book_entry(row))
    return entries


def load_pte_certificate_entries(content: str) -> dict[str, dict[str, object]]:
    """Parse PTE certificate CSV content into an index by patent number."""
    reader = csv.DictReader(io.StringIO(content))
    entries: dict[str, dict[str, object]] = {}
    for row in reader:
        patent_no = normalize_patent_number(row.get("Patent No.", ""))
        if not patent_no:
            continue
        entries[patent_no] = build_pte_certificate_entry(row)
    return entries
