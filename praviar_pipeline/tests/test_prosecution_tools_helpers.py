"""Tests for prosecution tool helper modules."""

from __future__ import annotations

import pytest

pytest.importorskip("praviar_pipeline.agents.tools.prosecution_tools_definitions")

from praviar_pipeline.agents.tools.prosecution_tools_definitions import (
    build_prosecution_tool_definitions,
)
from praviar_pipeline.agents.tools.prosecution_tools_helpers import (
    format_assignment_chain,
    format_claim_text,
    format_file_wrapper_documents,
    format_patent_term_detail,
    format_prosecution_summary,
    format_transaction_log,
)


def test_build_prosecution_tool_definitions_returns_expected_names() -> None:
    names = {tool["name"] for tool in build_prosecution_tool_definitions()}
    assert names == {
        "fetch_file_wrapper",
        "fetch_prosecution_summary",
        "fetch_assignment_chain",
        "fetch_transaction_log",
        "fetch_patent_term_detail",
        "get_patent_claims",
    }


def test_format_file_wrapper_documents_limits_output() -> None:
    docs = [
        {
            "documentCode": "OA",
            "documentDescription": f"Doc {i}",
            "documentDate": "2021-01-01",
        }
        for i in range(50)
    ]
    result = format_file_wrapper_documents("US123", docs)
    assert "50 documents" in result
    assert len([line for line in result.splitlines() if line.startswith("  - ")]) == 40


def test_format_prosecution_summary_includes_key_sections() -> None:
    class History:
        def __init__(self) -> None:
            self.application_number = "16/123456"
            self.filing_date = None
            self.grant_date = None
            self.prosecution_duration_days = 730
            self.examiner_name = "Examiner"
            self.inventor_names = ["Alice", "Bob"]
            self.current_assignee = "Acme"
            self.total_office_actions = 3
            self.total_responses = 2
            self.has_terminal_disclaimer = True
            self.prosecution_complete = False
            self.rejections: list = []
            self.amendments: list = []

    result = format_prosecution_summary("US123", History())
    assert "Prosecution History for US123" in result
    assert "Prosecution duration: 730 days" in result
    assert "Current assignee: Acme" in result


def test_format_assignment_and_transaction_logs() -> None:
    assignments = [{"assignmentRecordedDate": "2022-01-01", "conveyanceText": "ASSIGNMENT"}]
    transactions = [
        {
            "transactionDate": "2021-01-01",
            "transactionCode": "CTNF",
            "transactionDescription": "Office Action",
        }
    ]
    assignment_result = format_assignment_chain("US123", assignments)
    transaction_result = format_transaction_log("US123", transactions)
    assert "Assignment chain for US123" in assignment_result
    assert "Reel/Frame" not in assignment_result
    assert "Transaction log for US123" in transaction_result
    assert "[CTNF] Office Action" in transaction_result


def test_format_patent_term_and_claim_text() -> None:
    class Term:
        def __init__(self) -> None:
            self.effective_filing_date = "2020-01-01"
            self.grant_date = "2022-01-01"
            self.base_expiry = "2040-01-01"
            self.adjusted_expiry = "2040-06-01"
            self.pta_days = 30
            self.pta_breakdown = None
            self.pte_days = 0
            self.terminal_disclaimer = False
            self.td_linked_patent = None
            self.td_linked_expiry = None
            self.maintenance_fee_status = "current"
            self.calculation_confidence = 0.75
            self.calculation_notes = ["note"]

    term_result = format_patent_term_detail("US123", Term())
    assert "Patent Term Detail for US123" in term_result
    assert "Confidence: 75%" in term_result
    assert "note" in term_result

    claims_text = "1. A first claim.\n2. A second claim.\n"
    assert "Claim 1 of US123" in format_claim_text("US123", claims_text, 1)
    assert "Claims for US123" in format_claim_text("US123", claims_text, None)
