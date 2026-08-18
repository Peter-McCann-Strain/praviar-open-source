"""Fail-closed structural quality checks for rendered report artifacts."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


class PdfArtifactQualityError(RuntimeError):
    """Raised when a compiled report PDF is structurally unsafe to publish."""


@dataclass(frozen=True, slots=True)
class PdfQualityReceipt:
    sha256: str
    page_count: int
    extracted_text_characters: int
    rendered_page_hashes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PdfUa1Receipt:
    profile_name: str
    passed_rules: int
    passed_checks: int
    validator_binary: str


@dataclass(frozen=True, slots=True)
class DocxQualityReceipt:
    extracted_text_characters: int
    section_count: int
    table_count: int


def _load_pdfium() -> Any:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:  # pragma: no cover - dependency contract
        raise PdfArtifactQualityError(
            "PDF validation dependency is unavailable; refusing to publish."
        ) from exc
    return pdfium


def _normalized_marker(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def validate_pdf_artifact(
    path: Path,
    *,
    expected_text: tuple[str, ...] = (),
    minimum_text_characters: int = 100,
    minimum_page_text_characters: int = 100,
) -> PdfQualityReceipt:
    """Validate page rendering, selectable text, markers, and duplicate pages."""
    if not path.is_file():
        raise PdfArtifactQualityError("Rendered PDF is missing.")
    payload = path.read_bytes()
    if len(payload) < 512 or not payload.startswith(b"%PDF-"):
        raise PdfArtifactQualityError("Rendered PDF is truncated or has an invalid header.")

    pdfium = _load_pdfium()
    try:
        document = pdfium.PdfDocument(path)
    except Exception as exc:
        raise PdfArtifactQualityError("Rendered PDF cannot be opened.") from exc

    page_hashes: list[str] = []
    extracted_pages: list[str] = []
    blank_pages: list[int] = []
    low_content_pages: list[int] = []
    try:
        page_count = len(document)
        if page_count < 1:
            raise PdfArtifactQualityError("Rendered PDF contains no pages.")

        for page_index in range(page_count):
            page = document[page_index]
            text_page = None
            bitmap = None
            try:
                width, height = page.get_size()
                if width <= 0 or height <= 0:
                    raise PdfArtifactQualityError(
                        f"Rendered PDF page {page_index + 1} has invalid dimensions."
                    )

                text_page = page.get_textpage()
                get_text = getattr(text_page, "get_text_bounded", None)
                if not callable(get_text):
                    get_text = text_page.get_text_range
                text = str(get_text() or "")
                extracted_pages.append(text)
                if len("".join(text.split())) < minimum_page_text_characters:
                    low_content_pages.append(page_index + 1)

                bitmap = page.render(scale=0.5)
                image = bitmap.to_pil().convert("L")
                extrema = image.getextrema()
                minimum_pixel = int(extrema[0] if isinstance(extrema, tuple) else extrema)
                page_hashes.append(hashlib.sha256(image.tobytes()).hexdigest())
                if not text.strip() and minimum_pixel >= 245:
                    blank_pages.append(page_index + 1)
            finally:
                if bitmap is not None:
                    bitmap.close()
                if text_page is not None:
                    text_page.close()
                page.close()
    finally:
        document.close()

    if blank_pages:
        raise PdfArtifactQualityError(
            "Rendered PDF contains blank pages: "
            + ", ".join(str(page) for page in blank_pages)
            + "."
        )
    if low_content_pages:
        raise PdfArtifactQualityError(
            "Rendered PDF contains header/footer-only or low-content pages: "
            + ", ".join(str(page) for page in low_content_pages)
            + "."
        )
    if len(set(page_hashes)) != len(page_hashes):
        raise PdfArtifactQualityError("Rendered PDF contains duplicate page images.")

    extracted_text = "\n".join(extracted_pages)
    if len(extracted_text.strip()) < minimum_text_characters:
        raise PdfArtifactQualityError(
            "Rendered PDF does not contain enough selectable report text."
        )
    searchable_text = _normalized_marker(extracted_text)
    missing_markers = [
        marker
        for raw_marker in expected_text
        if (marker := _normalized_marker(raw_marker)) and marker not in searchable_text
    ]
    if missing_markers:
        raise PdfArtifactQualityError("Rendered PDF is missing required report identity text.")

    return PdfQualityReceipt(
        sha256=hashlib.sha256(payload).hexdigest(),
        page_count=len(page_hashes),
        extracted_text_characters=len(extracted_text),
        rendered_page_hashes=tuple(page_hashes),
    )


def validate_pdf_ua1_artifact(
    path: Path,
    *,
    validator_binary: str | None = None,
    timeout_seconds: int = 60,
) -> PdfUa1Receipt:
    """Run veraPDF's PDF/UA-1 profile and fail closed on any uncertainty.

    This helper is deliberately separate from ``validate_pdf_artifact`` until
    the production export image installs an authenticated, pinned validator.
    Callers that opt in cannot silently skip validation when the binary is
    absent or its machine-readable result is malformed.
    """
    if not path.is_file():
        raise PdfArtifactQualityError("Rendered PDF is missing.")
    resolved_binary = validator_binary or shutil.which("verapdf")
    if not resolved_binary:
        raise PdfArtifactQualityError(
            "veraPDF is unavailable; PDF/UA-1 conformance cannot be confirmed."
        )

    try:
        result = subprocess.run(
            [
                resolved_binary,
                "--format",
                "json",
                "--flavour",
                "ua1",
                str(path),
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PdfArtifactQualityError(
            "veraPDF execution failed; PDF/UA-1 conformance cannot be confirmed."
        ) from exc

    try:
        payload = json.loads(result.stdout)
        validation = payload["report"]["jobs"][0]["validationResult"][0]
        details = validation["details"]
        compliant = validation["compliant"] is True
        profile_name = str(validation["profileName"])
        passed_rules = int(details["passedRules"])
        failed_rules = int(details["failedRules"])
        passed_checks = int(details["passedChecks"])
        failed_checks = int(details["failedChecks"])
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PdfArtifactQualityError(
            "veraPDF returned an unreadable result; PDF/UA-1 conformance cannot be confirmed."
        ) from exc

    if (
        result.returncode != 0
        or not compliant
        or failed_rules != 0
        or failed_checks != 0
        or "PDF/UA-1" not in profile_name
    ):
        raise PdfArtifactQualityError(
            "Rendered PDF does not conform to the veraPDF PDF/UA-1 profile."
        )

    return PdfUa1Receipt(
        profile_name=profile_name,
        passed_rules=passed_rules,
        passed_checks=passed_checks,
        validator_binary=resolved_binary,
    )


def validate_docx_document(
    document: Any,
    *,
    expected_text: tuple[str, ...] = (),
    minimum_text_characters: int = 100,
) -> DocxQualityReceipt:
    """Validate report identity and readable content before DOCX serialization."""
    paragraph_text = [str(paragraph.text or "") for paragraph in document.paragraphs]
    table_text = [
        str(paragraph.text or "")
        for table in document.tables
        for row in table.rows
        for cell in row.cells
        for paragraph in cell.paragraphs
    ]
    extracted_text = "\n".join([*paragraph_text, *table_text])
    if len(extracted_text.strip()) < minimum_text_characters:
        raise RuntimeError("Rendered DOCX does not contain enough report text.")
    searchable_text = _normalized_marker(extracted_text)
    if any(
        marker not in searchable_text
        for raw_marker in expected_text
        if (marker := _normalized_marker(raw_marker))
    ):
        raise RuntimeError("Rendered DOCX is missing required report identity text.")
    section_count = len(document.sections)
    if section_count < 1:
        raise RuntimeError("Rendered DOCX contains no document sections.")
    return DocxQualityReceipt(
        extracted_text_characters=len(extracted_text),
        section_count=section_count,
        table_count=len(document.tables),
    )
