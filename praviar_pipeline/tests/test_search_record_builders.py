from __future__ import annotations

from datetime import date

from praviar_pipeline.models.patent import LegalEvent, PatentHit, PatentSource
from praviar_pipeline.pipeline.search.enrichment import (
    build_assignment_record,
    build_legal_event,
    build_patent_family,
    build_priority_claim,
    build_ptab_proceeding,
    dump_legal_events,
    parse_optional_iso_date,
)


def test_parse_optional_iso_date_handles_missing_and_invalid_values() -> None:
    assert parse_optional_iso_date("") is None
    assert parse_optional_iso_date("not-a-date") is None
    assert parse_optional_iso_date("2026-04-12T10:30:00Z") == date(2026, 4, 12)


def test_build_legal_event_and_priority_claim_parse_dates() -> None:
    legal_event = build_legal_event(
        {
            "event_date": "2026-04-10",
            "event_code": "OPP",
            "event_description": "Opposition filed",
            "country": "EP",
        }
    )
    priority_claim = build_priority_claim(
        {
            "country": "US",
            "doc_number": "17/123456",
            "date": "2024-01-15",
        }
    )

    assert legal_event == LegalEvent(
        event_date=date(2026, 4, 10),
        event_code="OPP",
        event_description="Opposition filed",
        country="EP",
    )
    assert priority_claim.application_number == "17/123456"
    assert priority_claim.priority_date == date(2024, 1, 15)


def test_build_patent_family_creates_members() -> None:
    family = build_patent_family(
        {
            "family_id": "FAM-1",
            "members": [
                {"country": "US", "doc_number": "1234567", "kind": "B2"},
                {"country": "EP", "doc_number": "7654321", "kind": "B1"},
            ],
        }
    )

    assert family.family_id == "FAM-1"
    assert len(family.members) == 2
    assert family.members[0].doc_number == "1234567"


def test_dump_legal_events_returns_model_dump_list() -> None:
    hit = PatentHit(
        patent_id="US1234567B2",
        title="Test",
        sources=[PatentSource.PUBCHEM],
        confidence_score=0.9,
        legal_events=[
            LegalEvent(
                event_date=date(2026, 4, 10),
                event_code="OPP",
                event_description="Opposition filed",
                country="EP",
            )
        ],
    )

    assert dump_legal_events(hit) == [
        {
            "event_date": date(2026, 4, 10),
            "event_code": "OPP",
            "event_description": "Opposition filed",
            "country": "EP",
        }
    ]


def test_build_assignment_record_and_ptab_proceeding_map_fields() -> None:
    assignment = build_assignment_record(
        {
            "conveyanceText": "ASSIGNMENT",
            "assignmentRecordedDate": "2025-03-01",
            "reelAndFrameNumber": "012345/0678",
        }
    )
    proceeding = build_ptab_proceeding(
        {
            "trialNumber": "IPR2025-00001",
            "trialType": "IPR",
            "filingDate": "2025-02-01",
            "institutionDecisionDate": "2025-08-01",
            "status": "Instituted",
            "petitionerPartyName": "Generic Pharma",
        }
    )

    assert assignment.recorded_date == date(2025, 3, 1)
    assert assignment.reel_frame == "012345/0678"
    assert proceeding.proceeding_number == "IPR2025-00001"
    assert proceeding.filing_date == date(2025, 2, 1)
    assert proceeding.institution_date == date(2025, 8, 1)
    assert proceeding.petitioner == "Generic Pharma"
