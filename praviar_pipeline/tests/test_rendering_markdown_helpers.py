"""Tests for pure Markdown rendering helpers."""

from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.models.analysis import RiskLevel
from praviar_pipeline.rendering.markdown_support import (
    collect_family_jurisdictions,
    format_assignment_entry,
    format_claim_numbers,
    format_graham_factor_lines,
    format_orange_book_status,
    format_patent_term_lines,
    format_ptab_status,
    risk_sort_key,
)


def test_risk_sort_key_orders_expected_levels() -> None:
    assert risk_sort_key(RiskLevel.HIGH) == 0
    assert risk_sort_key(RiskLevel.MEDIUM) == 1
    assert risk_sort_key(RiskLevel.LOW) == 2
    assert risk_sort_key(RiskLevel.CLEAR) == 3


def test_format_claim_and_disclosure_helpers() -> None:
    claims = [SimpleNamespace(claim_number=1), SimpleNamespace(claim_number=7)]
    assert format_claim_numbers(claims) == "1, 7"

    assert format_ptab_status({"ptab_proceedings": [{"id": "a"}, {"id": "b"}]}) == "2 proceeding(s)"
    assert format_ptab_status({}) == "-"

    assert (
        format_orange_book_status(
            {
                "orange_book_info": {
                    "is_listed": True,
                    "delist_requested": False,
                }
            },
            None,
        )
        == "LISTED"
    )
    assert (
        format_orange_book_status(
            {},
            SimpleNamespace(is_listed=True, delist_requested=True),
        )
        == "LISTED — DELIST REQUESTED"
    )
    assert format_orange_book_status({}, None) == "-"


def test_format_patent_term_and_assignment_helpers() -> None:
    term_lines = format_patent_term_lines(
        {
            "effective_filing_date": "2014-01-02",
            "grant_date": "2017-02-03",
            "adjusted_expiry": "2037-02-03",
            "pta_days": 12,
            "pta_breakdown": {
                "a_delay_days": 2,
                "b_delay_days": 4,
                "c_delay_days": 1,
                "applicant_delay_days": 3,
            },
            "pte_days": 5,
            "terminal_disclaimer": True,
            "td_linked_patent": "US1234567",
            "td_linked_expiry": "2035-01-01",
            "maintenance_fee_status": "current",
            "calculation_confidence": 0.8,
        }
    )
    assert "- **Effective Filing Date:** 2014-01-02" in term_lines
    assert "- **Patent Term Adjustment:** 12 days" in term_lines
    assert "  - Applicant delay: -3 days" in term_lines
    assert "- **Patent Term Extension (Hatch-Waxman):** 5 days" in term_lines
    assert "- **Terminal Disclaimer:** Yes (linked to US1234567, expires 2035-01-01)" in term_lines
    assert "- **Maintenance Fee Status:** CURRENT" in term_lines
    assert "- **Calculation Confidence:** 80%" in term_lines

    assert (
        format_assignment_entry(
            {
                "recorded_date": "2020-01-01",
                "conveyance": "Assignment",
                "assignor": "OldCo",
                "assignee": "NewCo",
                "reel_frame": "1234/5678",
            }
        )
        == "- **2020-01-01**: Assignment — OldCo → NewCo (Reel/Frame: 1234/5678)"
    )
    assert collect_family_jurisdictions(
        {"members": [{"country": "US"}, {"country": "EP"}, {}]}
    ) == [
        "EP",
        "US",
    ]


def test_format_graham_factor_lines() -> None:
    factors = SimpleNamespace(
        scope_and_content="scope text",
        differences_from_prior_art="difference text",
        level_of_ordinary_skill="skill text",
        overall_obviousness_assessment="assessment text",
    )
    lines = format_graham_factor_lines(factors, 6)
    assert lines == [
        "- Scope: scope ",
        "- Differences: differ",
        "- Skill level: skill ",
        "- Assessment: assess",
    ]
