"""FDA Paragraph IV certification client.

Fetches and parses the FDA list of Paragraph IV ANDA certifications
(drug patent challenges under the Hatch-Waxman Act).

Data source: FDA publishes a PDF updated ~biweekly. The URL contains a
media ID that changes with each release. Callers must supply the current
URL; the historical archive at https://www.thefdalawblog.com/anda-paragraph-iv-patent-certifications-list-archive/
can be used to locate past releases.

FTO significance: a Paragraph IV certification is a leading indicator that
a patent is actively contested, which materially elevates risk in an FTO
assessment.
"""

from __future__ import annotations

import io
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, Field

from praviar_pipeline.clients.base import cached_bytes_request
from praviar_pipeline.errors import ConfigurationError, SourceUnavailableError
from praviar_pipeline.utils.http_bodies import read_bounded_response_body
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

logger = structlog.get_logger()

PARAGRAPH_IV_MAX_PDF_BYTES = 20 * 1024 * 1024


class ParagraphIVEntry(BaseModel):
    """A single row from the FDA Paragraph IV certifications list."""

    drug_name: str
    dosage_form: str | None = None
    strength: str | None = None
    nda_number: str | None = None
    submission_count: int | None = Field(
        default=None,
        description="Number of ANDAs carrying a Paragraph IV certification for this product.",
    )
    first_filing_date: str | None = None
    patent_expiry_date: str | None = None
    has_180_day_exclusivity: bool = False


async def fetch_paragraph_iv_pdf(pdf_url: str) -> bytes:
    """Download the Paragraph IV PDF from the given FDA URL.

    Args:
        pdf_url: Direct URL to the current FDA Paragraph IV PDF.

    Returns:
        Raw PDF bytes.

    Raises:
        httpx.HTTPStatusError: if the server returns a non-2xx response.
        httpx.TimeoutException: if the download exceeds 30 seconds.
    """
    logger.info("paragraph_iv_download_start")

    async def _download() -> bytes:
        async with (
            httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client,
            client.stream("GET", pdf_url) as resp,
        ):
            resp.raise_for_status()
            return await read_bounded_response_body(
                resp,
                max_bytes=PARAGRAPH_IV_MAX_PDF_BYTES,
                source="paragraph_iv",
                detail="PDF body exceeded byte limit",
            )

    body = await cached_bytes_request(
        source="paragraph_iv",
        method="GET",
        url=pdf_url,
        body=None,
        call=_download,
    )
    if len(body) > PARAGRAPH_IV_MAX_PDF_BYTES:
        raise SourceUnavailableError("paragraph_iv", "cached PDF exceeded byte limit")
    logger.info("paragraph_iv_download_complete", bytes=len(body))
    return body


# ---------------------------------------------------------------------------
# Column-header normalisation helpers
# ---------------------------------------------------------------------------

_DRUG_NAME_KEYS = frozenset(
    ["drug name", "trade name", "proprietary name", "brand name", "product name"]
)
_DOSAGE_KEYS = frozenset(["dosage form", "dose form", "form"])
_STRENGTH_KEYS = frozenset(["strength", "dose strength"])
_NDA_KEYS = frozenset(["nda", "nda number", "nda no", "nda no.", "application number"])
_SUBMISSION_COUNT_KEYS = frozenset(
    ["number of anda", "no. of anda", "# of anda", "submission count", "anda count", "anda #"]
)
_FIRST_FILING_KEYS = frozenset(
    ["first filing date", "filing date", "date of first filing", "first certification date"]
)
_PATENT_EXPIRY_KEYS = frozenset(["patent expiry", "patent expiration", "patent expire date"])
_EXCLUSIVITY_KEYS = frozenset(["180-day", "180 day", "exclusivity", "first applicant exclusivity"])


def _match_key(raw: str, candidates: frozenset[str]) -> bool:
    """Return True if the normalised column header appears in the candidate set."""
    return raw.strip().lower() in candidates


def _normalise_submission_count(raw: str) -> int | None:
    """Convert a raw cell value to an integer submission count, or None."""
    cleaned = raw.strip().replace(",", "")
    if not cleaned or cleaned == "-":
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _normalise_exclusivity(raw: str) -> bool:
    """Return True if the cell indicates 180-day exclusivity is present."""
    lowered = raw.strip().lower()
    return lowered in ("y", "yes", "x", "1", "true")


def _extract_row(
    row: list[str],
    headers: list[str],
) -> ParagraphIVEntry | None:
    """Map a single table row to a ParagraphIVEntry.

    Returns None if the row is empty or has no recognisable drug name.
    """
    if not any(cell.strip() for cell in row):
        return None

    cell: dict[str, str] = {}
    for col_idx, header in enumerate(headers):
        if col_idx < len(row):
            cell[header] = row[col_idx]

    drug_name = ""
    dosage_form: str | None = None
    strength: str | None = None
    nda_number: str | None = None
    submission_count: int | None = None
    first_filing_date: str | None = None
    patent_expiry_date: str | None = None
    has_180_day_exclusivity = False

    for raw_header, value in cell.items():
        v = value.strip()
        norm = raw_header.strip().lower()

        if _match_key(norm, _DRUG_NAME_KEYS):
            drug_name = v
        elif _match_key(norm, _DOSAGE_KEYS):
            dosage_form = v or None
        elif _match_key(norm, _STRENGTH_KEYS):
            strength = v or None
        elif _match_key(norm, _NDA_KEYS):
            nda_number = v or None
        elif _match_key(norm, _SUBMISSION_COUNT_KEYS):
            submission_count = _normalise_submission_count(v)
        elif _match_key(norm, _FIRST_FILING_KEYS):
            first_filing_date = v or None
        elif _match_key(norm, _PATENT_EXPIRY_KEYS):
            patent_expiry_date = v or None
        elif _match_key(norm, _EXCLUSIVITY_KEYS):
            has_180_day_exclusivity = _normalise_exclusivity(v)

    if not drug_name:
        return None

    return ParagraphIVEntry(
        drug_name=drug_name,
        dosage_form=dosage_form,
        strength=strength,
        nda_number=nda_number,
        submission_count=submission_count,
        first_filing_date=first_filing_date,
        patent_expiry_date=patent_expiry_date,
        has_180_day_exclusivity=has_180_day_exclusivity,
    )


def _find_header_row(table: list[list[Any]]) -> int | None:
    """Return the index of the header row in a pdfplumber table.

    The FDA PDF header row contains at least one of the known drug-name
    column labels. Returns None if no header is found.
    """
    for idx, row in enumerate(table):
        cells = [str(c or "").strip().lower() for c in row]
        if any(c in _DRUG_NAME_KEYS for c in cells):
            return idx
    return None


def parse_paragraph_iv_pdf(pdf_bytes: bytes) -> list[ParagraphIVEntry]:
    """Parse the Paragraph IV certification PDF into structured records.

    Uses pdfplumber to extract tabular data from the FDA PDF. Missing parser
    dependencies fail closed so unavailable evidence cannot be represented as
    a successful source with zero findings.

    Args:
        pdf_bytes: Raw bytes of the FDA Paragraph IV PDF.

    Returns:
        List of ParagraphIVEntry records.
    """
    if len(pdf_bytes) > PARAGRAPH_IV_MAX_PDF_BYTES:
        raise SourceUnavailableError("paragraph_iv", "PDF body exceeded byte limit")

    try:
        import pdfplumber
    except ImportError:
        logger.warning(
            "pdfplumber_not_installed",
            feature="paragraph_iv_parsing",
        )
        raise ConfigurationError(
            "pdfplumber is required for Paragraph IV evidence parsing",
            source="paragraph_iv",
            step="paragraph_iv_parsing",
        ) from None

    entries: list[ParagraphIVEntry] = []
    skipped_rows = 0
    parse_failure_type: str | None

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables()
                if not tables:
                    continue

                for table in tables:
                    if not table:
                        continue

                    header_idx = _find_header_row(table)
                    if header_idx is None:
                        # No recognisable header; skip this table fragment.
                        continue

                    headers = [str(c or "").strip() for c in table[header_idx]]

                    for row in table[header_idx + 1 :]:
                        try:
                            entry = _extract_row(
                                [str(c or "") for c in row],
                                headers,
                            )
                            if entry is not None:
                                entries.append(entry)
                        except Exception as exc:
                            skipped_rows += 1
                            logger.debug(
                                "paragraph_iv_row_skip",
                                page=page_num,
                                error_type=safe_exception_type(exc),
                            )

    except Exception as exc:
        parse_failure_type = safe_exception_type(exc)
        logger.error(
            "paragraph_iv_parse_error",
            error_type=parse_failure_type,
            bytes_received=len(pdf_bytes),
        )
    else:
        parse_failure_type = None

    if parse_failure_type is not None:
        raise SourceUnavailableError("paragraph_iv", "PDF parsing failed") from None

    logger.info(
        "paragraph_iv_parsed",
        entries=len(entries),
        skipped_rows=skipped_rows,
    )
    return entries


def lookup_paragraph_iv_status(
    nda_number: str,
    pdf_entries: list[ParagraphIVEntry],
) -> list[ParagraphIVEntry]:
    """Filter entries matching a given NDA number.

    Matching is exact and case-insensitive after stripping whitespace.
    The NDA number may be supplied with or without the leading 'N' prefix
    used in some FDA publications (e.g., 'N021343' and '021343' both match
    a stored value of 'N021343' because a common normalisation is applied).

    Args:
        nda_number: The NDA number to look up.
        pdf_entries: The full list of ParagraphIVEntry records from the PDF.

    Returns:
        All entries whose nda_number matches, or an empty list.
    """

    def _normalise(raw: str | None) -> str:
        if raw is None:
            return ""
        return raw.strip().lstrip("Nn").lstrip("0").lower()

    target = _normalise(nda_number)
    if not target:
        return []

    return [e for e in pdf_entries if _normalise(e.nda_number) == target]
