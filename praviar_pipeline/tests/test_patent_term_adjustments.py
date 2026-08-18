from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

import praviar_pipeline.config as pipeline_config
import praviar_pipeline.utils.patent_expiry as patent_expiry
from praviar_pipeline.utils.patent_term_adjustments import (
    extract_pta_terms,
    infer_pte_days,
)
from praviar_pipeline.utils.patent_term_maintenance import resolve_maintenance_status


def test_extract_pta_terms_builds_breakdown_from_odp_payload() -> None:
    pta_days, pta_breakdown, notes, confidence_delta = extract_pta_terms(
        {
            "patentTermAdjustmentData": {
                "aDelayQuantity": 10,
                "bDelayQuantity": 20,
                "cDelayQuantity": 3,
                "overlappingDayQuantity": 2,
                "applicantDayDelayQuantity": 4,
                "adjustmentTotalQuantity": 27,
            }
        },
        {},
    )

    assert pta_days == 27
    assert pta_breakdown is not None
    assert pta_breakdown.total_days == 27
    assert notes == ["PTA: 27 days (A=10, B=20, C=3, overlap=2, applicant delay=4)"]
    assert confidence_delta == 0.15


def test_resolve_maintenance_status_uses_legal_event_fallback() -> None:
    status, lapse_date, notes, confidence_delta = resolve_maintenance_status(
        app_data={},
        legal_events=[
            {
                "event_description": "Patent lapsed due to non-payment of maintenance fee",
                "event_code": "LAPS",
                "event_date": date(2024, 6, 1),
            }
        ],
    )

    assert status == "lapsed"
    assert lapse_date == date(2024, 6, 1)
    assert notes == ["Maintenance fee lapsed (INPADOC) on 2024-06-01"]
    assert confidence_delta == 0.0


@pytest.mark.parametrize(
    "description",
    [
        "Request for reinstatement filed",
        "Reinstatement denied",
        "Notice: not reinstated",
    ],
)
def test_reinstatement_prose_cannot_establish_current_payment(
    description: str,
) -> None:
    status, lapse_date, notes, confidence_delta = resolve_maintenance_status(
        app_data={},
        legal_events=[
            {
                "event_description": description,
                "event_code": "REQUEST",
                "event_date": date(2026, 1, 1),
            }
        ],
    )

    assert (status, lapse_date, notes, confidence_delta) == (
        "unknown",
        None,
        [],
        0.0,
    )


def test_historic_payment_cannot_override_later_final_expiration() -> None:
    status, _, _, _ = resolve_maintenance_status(
        app_data={
            "eventDataBag": [
                {
                    "eventCode": "M1551",
                    "eventDescriptionText": "First maintenance fee paid",
                    "eventDate": "2020-01-01",
                },
                {
                    "eventCode": "EXP",
                    "eventDescriptionText": (
                        "Patent expired due to failure to pay maintenance fee"
                    ),
                    "eventDate": "2024-01-01",
                },
            ]
        },
        legal_events=None,
    )

    assert status == "lapsed"


def test_historic_payment_alone_does_not_prove_current_status() -> None:
    status, _, _, _ = resolve_maintenance_status(
        app_data={
            "eventDataBag": [
                {
                    "eventCode": "M1551",
                    "eventDescriptionText": "First maintenance fee paid",
                    "eventDate": "2014-01-01",
                }
            ]
        },
        legal_events=None,
    )

    assert status == "unknown"


@pytest.mark.asyncio
async def test_infer_pte_days_never_reads_orange_book_expiry(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        pipeline_config,
        "get_settings",
        lambda: SimpleNamespace(
            pte_certificates_csv_path="",
            orange_book_patent_txt_path="/must-not-be-read/patent.txt",
        ),
    )

    def _unexpected_orange_book_read(path: str):
        raise AssertionError(f"Orange Book term inference attempted: {path}")

    monkeypatch.setattr(
        patent_expiry,
        "_get_orange_book_cache",
        _unexpected_orange_book_read,
    )

    pte_days, notes = await infer_pte_days(
        "US7851188B2",
        app_data={},
        meta={},
        base_expiry=date(2030, 3, 15),
        pta_days=0,
    )

    assert pte_days == 0
    assert notes == []
