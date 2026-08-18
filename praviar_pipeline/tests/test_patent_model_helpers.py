from __future__ import annotations

from datetime import date

from praviar_pipeline.models.patent import PatentFamily, PatentFamilyMember, PatentTermInfo


def test_patent_family_jurisdictions_are_unique_and_sorted() -> None:
    family = PatentFamily(
        family_id="fam-1",
        members=[
            PatentFamilyMember(country="EP", doc_number="1", kind="B1"),
            PatentFamilyMember(country="US", doc_number="2", kind="B2"),
            PatentFamilyMember(country="EP", doc_number="3", kind="A1"),
            PatentFamilyMember(country="", doc_number="4", kind="A1"),
        ],
    )

    assert family.jurisdictions == ["EP", "US"]


def test_patent_term_info_computes_adjusted_expiry_from_pta_and_pte() -> None:
    patent_term = PatentTermInfo(
        patent_id="US1234567B2",
        base_expiry=date(2030, 1, 1),
        pta_days=10,
        pte_days=5,
    )

    assert patent_term.adjusted_expiry == date(2030, 1, 16)
