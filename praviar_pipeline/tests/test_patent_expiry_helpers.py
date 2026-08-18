from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from praviar_pipeline.utils import patent_expiry as patent_expiry_module
from praviar_pipeline.utils.patent_expiry_helpers import (
    build_orange_book_entry,
    build_pte_certificate_entry,
    load_orange_book_entries,
    load_pte_certificate_entries,
    normalize_patent_number,
    parse_excel_serial_date,
    parse_orange_book_date,
    parse_pte_extension_days,
)


def test_normalize_patent_number_handles_common_formats() -> None:
    assert normalize_patent_number("US7851188B2") == "7851188"
    assert normalize_patent_number("7851188.0") == "7851188"
    assert normalize_patent_number("RE30577") == "RE30577"
    assert normalize_patent_number("12545646*PED") == "12545646"


def test_parse_date_helpers_handle_valid_and_invalid_values() -> None:
    assert parse_orange_book_date("Aug 24, 2026") == date(2026, 8, 24)
    assert parse_orange_book_date("not-a-date") is None
    assert parse_excel_serial_date("44197") == date(2021, 1, 1)
    assert parse_excel_serial_date("0") is None
    assert parse_pte_extension_days("931 days") == 931
    assert parse_pte_extension_days("2 years") == 730
    assert parse_pte_extension_days("") == 0


def test_entry_builders_normalize_rows() -> None:
    orange_entry = build_orange_book_entry(
        {
            "Patent_Expire_Date_Text": "Aug 24, 2026",
            "Patent_Use_Code": "U123",
            "Drug_Substance_Flag": "Y",
            "Drug_Product_Flag": "N",
            "Appl_Type": "N",
            "Appl_No": "123456",
            "Trade_Name": "Demo Drug",
        }
    )
    assert orange_entry["patent_expiry"] == date(2026, 8, 24)
    assert orange_entry["drug_substance"] is True
    assert orange_entry["drug_product"] is False
    assert orange_entry["nda_number"] == "N123456"

    pte_entry = build_pte_certificate_entry(
        {
            "Tradename of Product (generic name; if applicable)": "Demo Drug",
            "Original Expiration Date*": "44197",
            "Period of Extension Granted": "2 years",
        }
    )
    assert pte_entry["original_expiry"] == date(2021, 1, 1)
    assert pte_entry["extension_days"] == 730
    assert pte_entry["extension_text"] == "2 years"


def test_load_helpers_build_indexes() -> None:
    orange_content = (
        "Patent_No~Patent_Expire_Date_Text~Patent_Use_Code~Drug_Substance_Flag~"
        "Drug_Product_Flag~Appl_Type~Appl_No~Trade_Name\n"
        "US7851188B2~Aug 24, 2026~U123~Y~N~N~123456~Demo Drug\n"
        "7851188*PED~Feb 24, 2027~U123~Y~N~N~123456~Demo Drug\n"
    )
    pte_content = (
        "Patent No.,Tradename of Product (generic name; if applicable),"
        "Original Expiration Date*,Period of Extension Granted\n"
        "US7851188B2,Demo Drug,44197,2 years\n"
    )

    orange_entries = load_orange_book_entries(orange_content)
    pte_entries = load_pte_certificate_entries(pte_content)

    assert list(orange_entries) == ["7851188"]
    assert orange_entries["7851188"][0]["patent_use_code"] == "U123"
    assert orange_entries["7851188"][1]["pediatric_exclusivity"] is True
    assert pte_entries["7851188"]["extension_days"] == 730


@pytest.mark.asyncio
async def test_orange_book_date_is_metadata_not_pte_or_term_evidence(
    tmp_path,
    monkeypatch,
) -> None:
    orange_path = tmp_path / "patent.txt"
    orange_path.write_text(
        "Patent_No~Patent_Expire_Date_Text~Patent_Use_Code~Drug_Substance_Flag~"
        "Drug_Product_Flag~Appl_Type~Appl_No~Trade_Name\n"
        "US7851188B2~Aug 24, 2031~U123~Y~N~N~123456~Demo Drug\n"
        "7851188*PED~Feb 24, 2032~U123~Y~N~N~123456~Demo Drug\n",
        encoding="utf-8",
    )
    pte_path = tmp_path / "pte.csv"
    pte_path.write_text(
        "Patent No.,Tradename of Product (generic name; if applicable),"
        "Original Expiration Date*,Period of Extension Granted\n"
        "US7851188B2,Demo Drug,44197,2 years\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(patent_expiry_module, "_orange_book_expiry_cache", None)
    monkeypatch.setattr(patent_expiry_module, "_pte_certificates_cache", None)
    monkeypatch.setattr(
        patent_expiry_module,
        "get_settings",
        lambda: SimpleNamespace(
            uspto_odp_api_key="token",
            orange_book_patent_txt_path=str(orange_path),
            pte_certificates_csv_path=str(pte_path),
        ),
    )

    mock_client = AsyncMock()
    mock_client.get_application_data.return_value = {
        "applicationMetaData": {"filingDate": "2010-03-15"},
        "patentTermAdjustmentData": {},
    }
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("praviar_pipeline.clients.uspto_odp.USPTOODPClient", return_value=mock_client):
        result = await patent_expiry_module.get_patent_expiry_with_extensions("US7851188B2")

    assert result["source"] == "pte_certificates"
    assert result["orange_book_expiry"] == date(2031, 8, 24)
    assert result["orange_book_pediatric_exclusivity"] is True
    assert result["patent_use_code"] == "U123"
    assert result["pte_days"] == 730
    assert result["actual_expiry"] == date(2030, 3, 15) + timedelta(days=730)
    assert any("Orange Book expiry" in note for note in result["notes"])
    assert not any("inferred PTE" in note for note in result["notes"])


@pytest.mark.asyncio
async def test_get_patent_expiry_uses_pte_certificate_fallback(tmp_path, monkeypatch) -> None:
    pte_path = tmp_path / "pte.csv"
    pte_path.write_text(
        "Patent No.,Tradename of Product (generic name; if applicable),"
        "Original Expiration Date*,Period of Extension Granted\n"
        "US9000000B2,Demo Drug,44197,931 days\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(patent_expiry_module, "_orange_book_expiry_cache", None)
    monkeypatch.setattr(patent_expiry_module, "_pte_certificates_cache", None)
    monkeypatch.setattr(
        patent_expiry_module,
        "get_settings",
        lambda: SimpleNamespace(
            uspto_odp_api_key="token",
            orange_book_patent_txt_path="",
            pte_certificates_csv_path=str(pte_path),
        ),
    )

    mock_client = AsyncMock()
    mock_client.get_application_data.return_value = {
        "applicationMetaData": {"filingDate": "2015-06-01"},
        "patentTermAdjustmentData": {},
    }
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("praviar_pipeline.clients.uspto_odp.USPTOODPClient", return_value=mock_client):
        result = await patent_expiry_module.get_patent_expiry_with_extensions("US9000000B2")

    assert result["source"] == "pte_certificates"
    assert result["pte_days"] == 931
    assert result["actual_expiry"] == date(2035, 6, 1) + timedelta(days=931)
    assert any("PTE certificate" in note for note in result["notes"])


@pytest.mark.asyncio
async def test_orange_book_date_cannot_supply_missing_uspto_base_term(
    tmp_path,
    monkeypatch,
) -> None:
    orange_path = tmp_path / "patent.txt"
    orange_path.write_text(
        "Patent_No~Patent_Expire_Date_Text~Patent_Use_Code~Drug_Substance_Flag~"
        "Drug_Product_Flag~Appl_Type~Appl_No~Trade_Name\n"
        "US7851188B2~Aug 24, 2031~U123~Y~N~N~123456~Demo Drug\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(patent_expiry_module, "_orange_book_expiry_cache", None)
    monkeypatch.setattr(patent_expiry_module, "_pte_certificates_cache", None)
    monkeypatch.setattr(
        patent_expiry_module,
        "get_settings",
        lambda: SimpleNamespace(
            uspto_odp_api_key="token",
            orange_book_patent_txt_path=str(orange_path),
            pte_certificates_csv_path="",
        ),
    )

    mock_client = AsyncMock()
    mock_client.get_application_data.return_value = {}
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "praviar_pipeline.clients.uspto_odp.USPTOODPClient",
        return_value=mock_client,
    ):
        result = await patent_expiry_module.get_patent_expiry_with_extensions("US7851188B2")

    assert result["orange_book_expiry"] == date(2031, 8, 24)
    assert result["base_expiry"] is None
    assert result["actual_expiry"] is None
    assert result["pte_days"] == 0
    assert result["source"] == "calculated"
