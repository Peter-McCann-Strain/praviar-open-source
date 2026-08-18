from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from praviar_pipeline.rendering import artifact_quality
from praviar_pipeline.rendering.artifact_quality import PdfArtifactQualityError

if TYPE_CHECKING:
    from pathlib import Path


class _Image:
    def __init__(self, payload: bytes, minimum_pixel: int = 0) -> None:
        self.payload = payload
        self.minimum_pixel = minimum_pixel

    def convert(self, _mode: str):
        return self

    def getextrema(self) -> tuple[int, int]:
        return self.minimum_pixel, 255

    def tobytes(self) -> bytes:
        return self.payload


class _Closable:
    def close(self) -> None:
        return None


class _TextPage(_Closable):
    def __init__(self, text: str) -> None:
        self.text = text

    def get_text_range(self) -> str:
        return self.text

    def get_text_bounded(self) -> str:
        return self.text


class _Bitmap(_Closable):
    def __init__(self, image: _Image) -> None:
        self.image = image

    def to_pil(self) -> _Image:
        return self.image


class _Page(_Closable):
    def __init__(self, *, text: str, pixels: bytes, minimum_pixel: int = 0) -> None:
        self.text = text
        self.image = _Image(pixels, minimum_pixel)

    def get_size(self) -> tuple[int, int]:
        return 612, 792

    def get_textpage(self) -> _TextPage:
        return _TextPage(self.text)

    def render(self, *, scale: float) -> _Bitmap:
        assert scale == 0.5
        return _Bitmap(self.image)


class _Document(_Closable):
    def __init__(self, pages: list[_Page]) -> None:
        self.pages = pages

    def __len__(self) -> int:
        return len(self.pages)

    def __getitem__(self, index: int) -> _Page:
        return self.pages[index]


class _Pdfium:
    def __init__(self, pages: list[_Page]) -> None:
        self.pages = pages

    def PdfDocument(self, _path: Path) -> _Document:  # noqa: N802
        return _Document(self.pages)


def _pdf_file(tmp_path: Path) -> Path:
    path = tmp_path / "report.pdf"
    path.write_bytes(b"%PDF-1.7\n" + (b"x" * 600))
    return path


def test_validate_pdf_artifact_returns_bound_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        _Page(text="Tavaborole freedom to operate report " * 4, pixels=b"page-one"),
        _Page(text="Evidence and limitations " * 5, pixels=b"page-two"),
    ]
    monkeypatch.setattr(artifact_quality, "_load_pdfium", lambda: _Pdfium(pages))

    receipt = artifact_quality.validate_pdf_artifact(
        _pdf_file(tmp_path),
        expected_text=("Tavaborole",),
    )

    assert receipt.page_count == 2
    assert len(receipt.sha256) == 64
    assert receipt.extracted_text_characters >= 100


def test_validate_pdf_artifact_rejects_blank_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [_Page(text="", pixels=b"white", minimum_pixel=255)]
    monkeypatch.setattr(artifact_quality, "_load_pdfium", lambda: _Pdfium(pages))

    with pytest.raises(PdfArtifactQualityError, match="blank pages"):
        artifact_quality.validate_pdf_artifact(
            _pdf_file(tmp_path),
            minimum_page_text_characters=0,
        )


def test_validate_pdf_artifact_rejects_duplicate_pages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        _Page(text="Tavaborole " * 20, pixels=b"same"),
        _Page(text="Evidence " * 20, pixels=b"same"),
    ]
    monkeypatch.setattr(artifact_quality, "_load_pdfium", lambda: _Pdfium(pages))

    with pytest.raises(PdfArtifactQualityError, match="duplicate"):
        artifact_quality.validate_pdf_artifact(_pdf_file(tmp_path))


def test_validate_pdf_artifact_rejects_header_footer_only_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        _Page(text="Report body " * 20, pixels=b"body"),
        _Page(text="Confidential Page 2", pixels=b"header-footer"),
    ]
    monkeypatch.setattr(artifact_quality, "_load_pdfium", lambda: _Pdfium(pages))

    with pytest.raises(PdfArtifactQualityError, match="low-content"):
        artifact_quality.validate_pdf_artifact(_pdf_file(tmp_path))


def test_validate_pdf_artifact_rejects_missing_identity_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [_Page(text="A different compound report " * 10, pixels=b"page")]
    monkeypatch.setattr(artifact_quality, "_load_pdfium", lambda: _Pdfium(pages))

    with pytest.raises(PdfArtifactQualityError, match="identity"):
        artifact_quality.validate_pdf_artifact(
            _pdf_file(tmp_path),
            expected_text=("Fingolimod",),
        )


def test_validate_pdf_ua1_artifact_fails_closed_when_validator_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(artifact_quality.shutil, "which", lambda _name: None)

    with pytest.raises(PdfArtifactQualityError, match="veraPDF is unavailable"):
        artifact_quality.validate_pdf_ua1_artifact(_pdf_file(tmp_path))


def test_validate_pdf_ua1_artifact_returns_verapdf_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        artifact_quality.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=(
                '{"report":{"jobs":[{"validationResult":[{"details":'
                '{"passedRules":106,"failedRules":0,"passedChecks":40742,'
                '"failedChecks":0},"profileName":"PDF/UA-1 validation profile",'
                '"compliant":true}]}]}}'
            ),
        ),
    )

    receipt = artifact_quality.validate_pdf_ua1_artifact(
        _pdf_file(tmp_path),
        validator_binary="/opt/verapdf/bin/verapdf",
    )

    assert receipt.profile_name == "PDF/UA-1 validation profile"
    assert receipt.passed_rules == 106
    assert receipt.passed_checks == 40742


def test_validate_pdf_ua1_artifact_rejects_nonconforming_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        artifact_quality.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1,
            stdout=(
                '{"report":{"jobs":[{"validationResult":[{"details":'
                '{"passedRules":105,"failedRules":1,"passedChecks":100,'
                '"failedChecks":1},"profileName":"PDF/UA-1 validation profile",'
                '"compliant":false}]}]}}'
            ),
        ),
    )

    with pytest.raises(PdfArtifactQualityError, match="does not conform"):
        artifact_quality.validate_pdf_ua1_artifact(
            _pdf_file(tmp_path),
            validator_binary="/opt/verapdf/bin/verapdf",
        )


def test_validate_docx_document_accepts_report_identity_and_sections() -> None:
    document = SimpleNamespace(
        paragraphs=[SimpleNamespace(text="Alendronate report " * 10)],
        tables=[],
        sections=[object()],
    )

    receipt = artifact_quality.validate_docx_document(
        document,
        expected_text=("Alendronate",),
    )

    assert receipt.section_count == 1
    assert receipt.extracted_text_characters >= 100


def test_validate_docx_document_rejects_missing_identity() -> None:
    document = SimpleNamespace(
        paragraphs=[SimpleNamespace(text="A different compound report " * 10)],
        tables=[],
        sections=[object()],
    )

    with pytest.raises(RuntimeError, match="identity"):
        artifact_quality.validate_docx_document(
            document,
            expected_text=("Tavaborole",),
        )
