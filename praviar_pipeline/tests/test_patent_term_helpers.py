from __future__ import annotations

from datetime import date

from praviar_pipeline.utils.patent_term_helpers import (
    _check_maintenance_fee_lapse,
    _effective_filing_date_from_continuity,
    _safe_add_years,
)


def test_safe_add_years_handles_february_29() -> None:
    assert _safe_add_years(date(2020, 2, 29), 1) == date(2021, 2, 28)


def test_effective_filing_date_ignores_provisional_parent() -> None:
    effective_filing, notes = _effective_filing_date_from_continuity(
        {"filingDate": "2012-01-01"},
        [
            {
                "parentFilingDate": "2010-01-01",
                "claimType": "pro",
                "parentApplicationNumber": "60/123456",
            },
            {
                "parentFilingDate": "2011-01-01",
                "claimType": "continuation",
                "parentApplicationNumber": "11/111111",
            },
        ],
    )

    assert effective_filing == date(2011, 1, 1)
    assert notes == [
        "Effective filing date adjusted to parent 11/111111 (continuation): 2011-01-01"
    ]


def test_check_maintenance_fee_lapse_ignores_unverified_reinstatement_prose() -> None:
    status, lapse_date = _check_maintenance_fee_lapse(
        [
            {
                "event_description": "Patent lapsed due to non-payment of maintenance fee",
                "event_code": "LAPS",
                "event_date": date(2024, 6, 1),
            },
            {
                "event_description": "Patent reinstated after petition",
                "event_code": "REST",
                "event_date": date(2024, 7, 1),
            },
        ]
    )

    assert status == "lapsed"
    assert lapse_date == date(2024, 6, 1)
