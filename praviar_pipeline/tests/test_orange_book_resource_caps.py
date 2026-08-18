"""Adversarial Orange Book archive and private-cache resource contracts."""

from __future__ import annotations

import io
import os
import stat
import zipfile

import pytest
from pytest_httpx import HTTPXMock

import praviar_pipeline.clients.orange_book as orange_book
from praviar_pipeline.errors import SourceUnavailableError

PATENT_HEADER = "~".join(orange_book.PATENT_HEADERS) + "\n"
PRODUCT_HEADER = "~".join(orange_book.PRODUCT_HEADERS) + "\n"
EXCLUSIVITY_HEADER = "~".join(orange_book.EXCLUSIVITY_HEADERS) + "\n"


def _zip_bytes(members: list[tuple[str, bytes]]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members:
            archive.writestr(name, payload)
    return output.getvalue()


def _complete_zip(patent_payload: bytes) -> bytes:
    return _zip_bytes(
        [
            ("data/patent.txt", patent_payload),
            (
                "data/products.txt",
                PRODUCT_HEADER.encode(),
            ),
            (
                "data/exclusivity.txt",
                EXCLUSIVITY_HEADER.encode(),
            ),
        ]
    )


def test_extracts_one_bounded_patent_member() -> None:
    payload = b"Appl_Type~Appl_No~Patent_No\nN~123~7654321\n"
    assert (
        orange_book._extract_orange_book_files(_complete_zip(payload))["patent.txt"].encode()
        == payload
    )


def test_rejects_member_one_byte_over_uncompressed_cap(monkeypatch) -> None:
    monkeypatch.setattr(orange_book, "ORANGE_BOOK_MAX_MEMBER_BYTES", 8)
    archive = _complete_zip(b"x" * 9)

    with pytest.raises(SourceUnavailableError, match="uncompressed byte limit"):
        orange_book._extract_orange_book_files(archive)


def test_rejects_high_compression_ratio_zip_bomb(monkeypatch) -> None:
    monkeypatch.setattr(orange_book, "ORANGE_BOOK_MAX_COMPRESSION_RATIO", 2.0)
    archive = _complete_zip(b"A" * 10_000)

    with pytest.raises(SourceUnavailableError, match="compression ratio"):
        orange_book._extract_orange_book_files(archive)


def test_rejects_ambiguous_patent_members() -> None:
    archive = _zip_bytes(
        [
            ("one/patent.txt", b"first"),
            ("two/patent.txt", b"second"),
            ("products.txt", b""),
            ("exclusivity.txt", b""),
        ]
    )

    with pytest.raises(SourceUnavailableError, match="exactly one"):
        orange_book._extract_orange_book_files(archive)


def test_rejects_invalid_zip_body() -> None:
    with pytest.raises(SourceUnavailableError, match="ZIP parsing failed"):
        orange_book._extract_orange_book_files(b"not-a-zip")


@pytest.mark.asyncio
async def test_cache_symlink_is_rejected_without_touching_target(tmp_path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("protected", encoding="utf-8")
    alias = tmp_path / "orange-book-cache.txt"
    alias.symlink_to(target)

    with pytest.raises(OSError, match="symlink"):
        await orange_book.load_orange_book(cache_path=alias)

    assert target.read_text(encoding="utf-8") == "protected"


@pytest.mark.asyncio
async def test_default_cache_is_private_and_atomic(
    tmp_path,
    monkeypatch,
    httpx_mock: HTTPXMock,
) -> None:
    import tempfile

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    payload = (
        PATENT_HEADER + "N~123456~001~7654321~Aug 24, 2031~Y~N~U-1234~N~Jan 02, 2020\n"
    ).encode()
    products = (
        PRODUCT_HEADER + "DEMO~TABLET;ORAL~DEMO DRUG~DEMO~10MG~N~123456~001~~"
        "Jan 02, 2020~Yes~Yes~RX~DEMO INC\n"
    ).encode()
    archive = _zip_bytes(
        [
            ("data/patent.txt", payload),
            ("data/products.txt", products),
            ("data/exclusivity.txt", EXCLUSIVITY_HEADER.encode()),
        ]
    )
    httpx_mock.add_response(url=orange_book.ORANGE_BOOK_URL, content=archive)

    index = await orange_book.load_orange_book()

    cache_path = (
        tmp_path
        / f"praviar-{os.getuid() if hasattr(os, 'getuid') else 'user'}"
        / "orange_book"
        / "patent.txt"
    )
    assert index.patent_count == 1
    assert cache_path.read_bytes() == payload
    assert (cache_path.parent / "products.txt").is_file()
    assert (cache_path.parent / "exclusivity.txt").is_file()
    assert stat.S_IMODE(cache_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(cache_path.stat().st_mode) == 0o600
    assert list(cache_path.parent.glob("*.tmp")) == []


def test_relational_tables_join_product_and_exclusivity_metadata() -> None:
    patent = PATENT_HEADER + "N~021588~001~7851188~Sep 25, 2032~Y~N~U-1234~N~Nov 13, 2015\n"
    products = (
        PRODUCT_HEADER + "OSIMERTINIB MESYLATE~TABLET;ORAL~TAGRISSO~ASTRAZENECA~80MG~"
        "N~021588~001~~Nov 13, 2015~Yes~Yes~RX~"
        "ASTRAZENECA PHARMACEUTICALS LP\n"
    )
    exclusivity = (
        EXCLUSIVITY_HEADER + "N~021588~001~NCE~Nov 13, 2020\n" + "N~021588~001~M-321~May 02, 2027\n"
    )

    entries = orange_book._parse_patent_file(
        patent,
        products_content=products,
        exclusivity_content=exclusivity,
    )["7851188"]

    assert len(entries) == 1
    entry = entries[0]
    assert entry.product_name == "TAGRISSO"
    assert entry.active_ingredient == "OSIMERTINIB MESYLATE"
    assert entry.dosage_form_route == "TABLET;ORAL"
    assert entry.reference_listed_drug is True
    assert entry.reference_standard is True
    assert [(record.code, record.expiration_date) for record in entry.exclusivities] == [
        ("NCE", "Nov 13, 2020"),
        ("M-321", "May 02, 2027"),
    ]
    assert entry.exclusivity_codes == ["M-321", "NCE"]
    assert entry.exclusivity_expiration_dates == [
        "May 02, 2027",
        "Nov 13, 2020",
    ]


def test_ob_join_preserves_every_product_row_for_a_shared_key() -> None:
    patent = PATENT_HEADER + "N~021588~001~7851188~Sep 25, 2032~Y~N~U-1234~N~Nov 13, 2015\n"
    products = (
        PRODUCT_HEADER + "INGREDIENT A~TABLET;ORAL~PART-A~APPLICANT~10MG~N~021588~001~~"
        "Nov 13, 2015~Yes~No~RX~APPLICANT INC\n"
        + "INGREDIENT B~KIT;ORAL~PART-B~APPLICANT~20MG~N~021588~001~~"
        "Nov 13, 2015~No~Yes~RX~APPLICANT INC\n"
    )

    entries = orange_book._parse_patent_file(
        patent,
        products_content=products,
        exclusivity_content=EXCLUSIVITY_HEADER,
    )["7851188"]

    assert [entry.product_name for entry in entries] == ["PART-A", "PART-B"]
    assert [entry.active_ingredient for entry in entries] == [
        "INGREDIENT A",
        "INGREDIENT B",
    ]


def test_ob_join_keeps_application_type_in_the_relational_key() -> None:
    patent = (
        PATENT_HEADER
        + "N~123456~001~7654321~Aug 24, 2031~Y~N~U-1~N~Jan 02, 2020\n"
        + "A~123456~001~7654321~Aug 24, 2031~N~Y~U-2~N~Jan 03, 2020\n"
    )
    products = (
        PRODUCT_HEADER + "NDA INGREDIENT~TABLET;ORAL~NDA PRODUCT~APPLICANT~10MG~N~123456~"
        "001~~Jan 02, 2020~Yes~Yes~RX~APPLICANT INC\n"
        + "ANDA INGREDIENT~TABLET;ORAL~ANDA PRODUCT~APPLICANT~10MG~A~123456~"
        "001~~Jan 03, 2020~No~No~RX~APPLICANT INC\n"
    )

    entries = orange_book._parse_patent_file(
        patent,
        products_content=products,
        exclusivity_content=EXCLUSIVITY_HEADER,
    )["7654321"]

    assert [
        (entry.application_type, entry.product_name, entry.patent_use_code) for entry in entries
    ] == [
        ("N", "NDA PRODUCT", "U-1"),
        ("A", "ANDA PRODUCT", "U-2"),
    ]


def test_ob_join_normalizes_ped_and_base_lookup_returns_both_rows() -> None:
    patent = (
        PATENT_HEADER
        + "N~123456~001~12545646~Jan 15, 2030~Y~N~U-1~N~Jan 02, 2020\n"
        + "N~123456~001~12545646*PED~Jul 15, 2030~Y~N~U-1~Y~Jan 03, 2020\n"
    )
    products = (
        PRODUCT_HEADER + "DEMO~TABLET;ORAL~DEMO DRUG~APPLICANT~10MG~N~123456~001~~"
        "Jan 02, 2020~Yes~Yes~RX~APPLICANT INC\n"
    )
    index = orange_book.OrangeBookIndex(
        orange_book._parse_patent_file(
            patent,
            products_content=products,
            exclusivity_content=EXCLUSIVITY_HEADER,
        )
    )

    entries = index.lookup("US12545646B2")

    assert len(entries) == 2
    assert [entry.raw_patent_number for entry in entries] == [
        "12545646",
        "12545646*PED",
    ]
    assert [entry.pediatric_exclusivity for entry in entries] == [False, True]
    assert entries[1].delist_requested is True
    assert index.lookup("12545646*PED") == entries


@pytest.mark.parametrize(
    ("patent", "products", "exclusivity", "message"),
    [
        (
            PATENT_HEADER + "N~123456~002~7654321~Aug 24, 2031~Y~N~U-1~N~Jan 02, 2020\n",
            PRODUCT_HEADER + "DEMO~TABLET;ORAL~DEMO~APPLICANT~10MG~N~123456~001~~"
            "Jan 02, 2020~Yes~Yes~RX~APPLICANT INC\n",
            EXCLUSIVITY_HEADER,
            "patent.txt row 2 has no matching product",
        ),
        (
            PATENT_HEADER + "N~123456~001~7654321~Aug 24, 2031~Y~N~U-1~N~Jan 02, 2020\n",
            PRODUCT_HEADER + "DEMO~TABLET;ORAL~DEMO~APPLICANT~10MG~N~123456~001~~"
            "Jan 02, 2020~Yes~Yes~RX~APPLICANT INC\n",
            EXCLUSIVITY_HEADER + "N~123456~002~NCE~Jan 02, 2025\n",
            "exclusivity.txt row 2 has no matching product",
        ),
    ],
)
def test_ob_join_rejects_orphan_relational_rows(
    patent: str,
    products: str,
    exclusivity: str,
    message: str,
) -> None:
    with pytest.raises(SourceUnavailableError, match=message):
        orange_book._parse_patent_file(
            patent,
            products_content=products,
            exclusivity_content=exclusivity,
        )


def test_ob_join_rejects_header_drift_and_invalid_key_widths() -> None:
    products = (
        PRODUCT_HEADER + "DEMO~TABLET;ORAL~DEMO~APPLICANT~10MG~N~123456~001~~"
        "Jan 02, 2020~Yes~Yes~RX~APPLICANT INC\n"
    )
    patent_without_submission_header = PATENT_HEADER.replace(
        "~Submission_Date",
        "",
    )
    patent_without_submission = (
        patent_without_submission_header + "N~123456~001~7654321~Aug 24, 2031~Y~N~U-1~N\n"
    )
    with pytest.raises(SourceUnavailableError, match="headers"):
        orange_book._parse_patent_file(
            patent_without_submission,
            products_content=products,
            exclusivity_content=EXCLUSIVITY_HEADER,
        )

    invalid_width_patent = (
        PATENT_HEADER + "N~12345~001~7654321~Aug 24, 2031~Y~N~U-1~N~Jan 02, 2020\n"
    )
    with pytest.raises(SourceUnavailableError, match="invalid relational key"):
        orange_book._parse_patent_file(
            invalid_width_patent,
            products_content=products,
            exclusivity_content=EXCLUSIVITY_HEADER,
        )


def test_ob_join_rejects_malformed_dates() -> None:
    patent = PATENT_HEADER + "N~123456~001~7654321~2031-08-24~Y~N~U-1~N~Jan 02, 2020\n"
    products = (
        PRODUCT_HEADER + "DEMO~TABLET;ORAL~DEMO~APPLICANT~10MG~N~123456~001~~"
        "Jan 02, 2020~Yes~Yes~RX~APPLICANT INC\n"
    )

    with pytest.raises(SourceUnavailableError, match="Patent_Expire_Date_Text"):
        orange_book._parse_patent_file(
            patent,
            products_content=products,
            exclusivity_content=EXCLUSIVITY_HEADER,
        )


@pytest.mark.asyncio
async def test_download_rejects_declared_zip_body_over_cap(httpx_mock: HTTPXMock, tmp_path) -> None:
    httpx_mock.add_response(
        url=orange_book.ORANGE_BOOK_URL,
        content=b"x",
        headers={"Content-Length": str(orange_book.ORANGE_BOOK_MAX_ZIP_BYTES + 1)},
    )

    with pytest.raises(SourceUnavailableError, match="ZIP body exceeded byte limit"):
        await orange_book.load_orange_book(cache_path=tmp_path / "patent.txt")
