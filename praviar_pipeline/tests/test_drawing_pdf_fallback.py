from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from praviar_pipeline.errors import ConfigurationError, SourceUnavailableError
from praviar_pipeline.pipeline.drawings.pdf_fallback import fetch_pdf_fallback


@pytest.mark.asyncio
async def test_fetch_pdf_fallback_fails_closed_when_pdfium_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    def fake_import_module(name: str):
        if name == "pypdfium2":
            raise ImportError("missing pypdfium2")
        raise AssertionError(f"unexpected module import: {name}")

    monkeypatch.setattr(
        "praviar_pipeline.pipeline.drawings.pdf_fallback.importlib.import_module",
        fake_import_module,
    )

    with pytest.raises(ConfigurationError, match="pypdfium2"):
        await fetch_pdf_fallback("US123", AsyncMock(), tmp_path)


@pytest.mark.asyncio
async def test_fetch_pdf_fallback_returns_empty_when_pdf_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "praviar_pipeline.pipeline.drawings.pdf_fallback.importlib.import_module",
        lambda name: (
            SimpleNamespace(PdfDocument=lambda _path: None) if name == "pypdfium2" else None
        ),
    )
    epo_client = AsyncMock()
    epo_client._get_binary = AsyncMock(return_value=b"")

    pages = await fetch_pdf_fallback("US123", epo_client, tmp_path)

    assert pages == []


@pytest.mark.asyncio
async def test_fetch_pdf_fallback_renders_pages_and_closes_document(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    class FakeImage:
        def __init__(self, content: bytes) -> None:
            self._content = content

        def save(self, output, format: str) -> None:
            assert format == "PNG"
            output.write(self._content)

    class FakeBitmap:
        def __init__(self, content: bytes) -> None:
            self._content = content
            self.closed = False

        def to_pil(self) -> FakeImage:
            return FakeImage(self._content)

        def close(self) -> None:
            self.closed = True

    class FakePage:
        def __init__(self, content: bytes) -> None:
            self._content = content
            self.closed = False

        def render(self, scale: float) -> FakeBitmap:
            assert scale == 300 / 72
            return FakeBitmap(self._content)

        def get_size(self) -> tuple[int, int]:
            return (612, 792)

        def close(self) -> None:
            self.closed = True

    class FakeDocument:
        def __init__(self) -> None:
            self.closed = False
            self._pages = [FakePage(b"page-1"), FakePage(b"page-2")]

        def __len__(self) -> int:
            return len(self._pages)

        def __getitem__(self, index: int) -> FakePage:
            return self._pages[index]

        def close(self) -> None:
            self.closed = True

    document = FakeDocument()
    pdfium_module = SimpleNamespace(PdfDocument=lambda _path: document)
    monkeypatch.setattr(
        "praviar_pipeline.pipeline.drawings.pdf_fallback.importlib.import_module",
        lambda name: pdfium_module if name == "pypdfium2" else None,
    )
    monkeypatch.setattr(
        "praviar_pipeline.pipeline.drawings.pdf_fallback._to_docdb_format",
        lambda patent_id: patent_id,
    )

    epo_client = AsyncMock()
    epo_client._get_binary = AsyncMock(return_value=b"%PDF")

    pages = await fetch_pdf_fallback("US123", epo_client, tmp_path, max_pages=1)

    assert pages == [(1, b"page-1")]
    assert document.closed is True
    assert (tmp_path / "US123_full.pdf").read_bytes() == b"%PDF"
    epo_client._get_binary.assert_awaited_once_with(
        "/published-data/publication/docdb/US123/fulltext.pdf",
        accept="application/pdf",
        max_bytes=100 * 1024 * 1024,
    )


@pytest.mark.asyncio
async def test_fetch_pdf_fallback_rejects_pdf_one_byte_over_cap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "praviar_pipeline.pipeline.drawings.pdf_fallback.importlib.import_module",
        lambda _name: SimpleNamespace(PdfDocument=lambda _path: None),
    )
    monkeypatch.setattr(
        "praviar_pipeline.pipeline.drawings.pdf_fallback._to_docdb_format",
        lambda patent_id: patent_id,
    )
    epo_client = AsyncMock()
    epo_client._get_binary = AsyncMock(return_value=b"123456")

    with pytest.raises(SourceUnavailableError, match="byte limit"):
        await fetch_pdf_fallback("US123", epo_client, tmp_path, max_pdf_bytes=5)

    assert not (tmp_path / "US123_full.pdf").exists()


@pytest.mark.asyncio
async def test_fetch_pdf_fallback_rejects_pixel_bomb_before_render(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    class HugePage:
        def __init__(self) -> None:
            self.closed = False
            self.rendered = False

        def get_size(self) -> tuple[int, int]:
            return (100_000, 100_000)

        def render(self, *, scale: float):
            self.rendered = True
            raise AssertionError(f"pixel bomb rendered at {scale}")

        def close(self) -> None:
            self.closed = True

    class Document:
        def __init__(self, page) -> None:
            self.page = page
            self.closed = False

        def __len__(self) -> int:
            return 1

        def __getitem__(self, _index: int):
            return self.page

        def close(self) -> None:
            self.closed = True

    page = HugePage()
    document = Document(page)
    monkeypatch.setattr(
        "praviar_pipeline.pipeline.drawings.pdf_fallback.importlib.import_module",
        lambda _name: SimpleNamespace(PdfDocument=lambda _path: document),
    )
    monkeypatch.setattr(
        "praviar_pipeline.pipeline.drawings.pdf_fallback._to_docdb_format",
        lambda patent_id: patent_id,
    )
    epo_client = AsyncMock()
    epo_client._get_binary = AsyncMock(return_value=b"%PDF")

    with pytest.raises(SourceUnavailableError, match="pixel limit"):
        await fetch_pdf_fallback(
            "US123",
            epo_client,
            tmp_path,
            max_pixels_per_page=1_000_000,
        )

    assert page.rendered is False
    assert page.closed is True
    assert document.closed is True
