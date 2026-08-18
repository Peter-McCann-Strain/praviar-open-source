from __future__ import annotations

from praviar_pipeline.models.patent import LegalStatus
from praviar_pipeline.utils.legal_status_events import derive_legal_status_from_events


def test_latest_dated_status_event_wins_independent_of_provider_order() -> None:
    events = [
        {
            "event_date": "2025-06-01",
            "event_code": "REVOKED_FINAL",
            "event_description": "Patent revoked",
        },
        {
            "event_date": "2020-01-01",
            "event_code": "B1",
            "event_description": "Patent granted",
        },
    ]

    assert derive_legal_status_from_events(events) == LegalStatus.REVOKED
    assert derive_legal_status_from_events(list(reversed(events))) == LegalStatus.REVOKED


def test_undated_or_same_day_conflicting_status_events_fail_closed() -> None:
    assert (
        derive_legal_status_from_events(
            [{"event_code": "B1", "event_description": "Patent granted"}]
        )
        == LegalStatus.UNKNOWN
    )
    assert (
        derive_legal_status_from_events(
            [
                {
                    "event_date": "2025-06-01",
                    "event_code": "B1",
                    "event_description": "Patent granted",
                },
                {
                    "event_date": "2025-06-01",
                    "event_code": "REVOKED_FINAL",
                    "event_description": "Patent revoked",
                },
            ]
        )
        == LegalStatus.UNKNOWN
    )


def test_requests_notices_appeals_and_denials_never_establish_final_status() -> None:
    hostile_descriptions = [
        "Request to revoke filed",
        "Revoked status appealed",
        "Restoration request filed",
        "Restoration denied",
        "Lapse fee notice",
        "Withdrawal request filed",
    ]

    for description in hostile_descriptions:
        assert (
            derive_legal_status_from_events(
                [
                    {
                        "event_date": "2020-01-01",
                        "event_code": "GRANT",
                        "event_description": "Patent granted",
                    },
                    {
                        "event_date": "2025-06-01",
                        "event_code": "",
                        "event_description": description,
                    },
                ]
            )
            == LegalStatus.UNKNOWN
        )


def test_only_explicit_final_outcome_codes_can_change_status() -> None:
    assert (
        derive_legal_status_from_events(
            [
                {
                    "event_date": "2020-01-01",
                    "event_code": "GRANT",
                    "event_description": "Patent granted",
                },
                {
                    "event_date": "2025-06-01",
                    "event_code": "RESTORED_FINAL",
                    "event_description": "Restoration granted and final",
                },
            ]
        )
        == LegalStatus.ACTIVE
    )
