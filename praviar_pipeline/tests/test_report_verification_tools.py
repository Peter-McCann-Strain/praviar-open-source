"""Tests for ReportVerificationToolkit — fact-checking tools."""

from __future__ import annotations

import hashlib
from datetime import date

import pytest

pytest.importorskip("praviar_pipeline.agents.tools.report_verification_tools")

from praviar_pipeline.agents.tools.report_verification_tools import (
    ReportVerificationToolkit,
    _normalize_assignee,
)
from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.compound import ResolvedCompound
from praviar_pipeline.models.verification import VerificationResult
from praviar_pipeline.pipeline.report_data_store import ReportDataStore

_ASSERTION_TEXT = (
    "Patents US10000001B2, US9999999A1, and US9999998A1 have high and low risk; "
    "Claim 1 Element 1, Claim 1 Element 2, and Claim 99 Element 1 are met; "
    "expiry and filing dates "
    "include 2030-06-15, 2025-01-01, and 2020-01-01; assignees include Pfizer "
    "Inc., Pfizer, and Novartis."
)
_ASSERTION_ID = f"A00001-{hashlib.sha256(_ASSERTION_TEXT.encode('utf-8')).hexdigest()[:12]}"


def _bound_input(**values: object) -> dict[str, object]:
    return {
        "assertion_id": _ASSERTION_ID,
        "assertion_text": _ASSERTION_TEXT,
        **values,
    }


def _make_store() -> ReportDataStore:
    compound = ResolvedCompound(
        name="test",
        canonical_smiles="C",
        original_input="test",
        input_type="name",
        compound_type="small_molecule",
    )
    analyses = [
        PatentAnalysis(
            patent_id="US10000001B2",
            title="Test Patent",
            assignee="Pfizer Inc.",
            expiry_date=date(2030, 6, 15),
            risk_level=RiskLevel.HIGH,
            risk_summary="HIGH risk",
            claims_analyzed=[
                ClaimAnalysis(
                    claim_number=1,
                    claim_type="independent",
                    overall_status=ElementStatus.NOT_MET,
                    elements=[
                        ClaimElement(
                            element_number=1,
                            element_text="compound X",
                            status=ElementStatus.MET,
                            reasoning="Match",
                        ),
                        ClaimElement(
                            element_number=2,
                            element_text="amount Y",
                            status=ElementStatus.NOT_MET,
                            reasoning="Outside range",
                        ),
                    ],
                ),
            ],
        ),
    ]
    return ReportDataStore(
        compound=compound,
        analyses=analyses,
        doe_assessments=[],
        invalidity_assessments=[],
        verification=VerificationResult(),
        overall_risk=RiskLevel.HIGH,
    )


class TestNormalizeAssignee:
    def test_strips_inc(self):
        assert _normalize_assignee("Pfizer Inc.") == "pfizer"

    def test_strips_corp(self):
        assert _normalize_assignee("Abbott Corp.") == "abbott"

    def test_strips_llc(self):
        assert _normalize_assignee("Patent LLC") == "patent"

    def test_handles_empty(self):
        assert _normalize_assignee("") == ""


class TestCheckPatentExists:
    @pytest.mark.asyncio
    async def test_found(self):
        toolkit = ReportVerificationToolkit(_make_store())
        result = await toolkit.execute(
            "check_patent_exists",
            _bound_input(patent_id="US10000001B2"),
        )
        assert "FOUND" in result
        assert "high" in result.lower()

    @pytest.mark.asyncio
    async def test_not_found(self):
        toolkit = ReportVerificationToolkit(_make_store())
        result = await toolkit.execute(
            "check_patent_exists",
            _bound_input(patent_id="US9999999A1"),
        )
        assert "NOT FOUND" in result


class TestCheckRiskLevel:
    @pytest.mark.asyncio
    async def test_match(self):
        toolkit = ReportVerificationToolkit(_make_store())
        result = await toolkit.execute(
            "check_risk_level",
            _bound_input(
                patent_id="US10000001B2",
                claimed_risk_level="high",
            ),
        )
        assert "MATCH" in result

    @pytest.mark.asyncio
    async def test_mismatch(self):
        toolkit = ReportVerificationToolkit(_make_store())
        result = await toolkit.execute(
            "check_risk_level",
            _bound_input(
                patent_id="US10000001B2",
                claimed_risk_level="low",
            ),
        )
        assert "MISMATCH" in result

    @pytest.mark.asyncio
    async def test_unknown_patent(self):
        toolkit = ReportVerificationToolkit(_make_store())
        result = await toolkit.execute(
            "check_risk_level",
            _bound_input(
                patent_id="US9999998A1",
                claimed_risk_level="high",
            ),
        )
        assert "CANNOT VERIFY" in result


class TestCheckElementStatus:
    @pytest.mark.asyncio
    async def test_match(self):
        toolkit = ReportVerificationToolkit(_make_store())
        result = await toolkit.execute(
            "check_element_status",
            _bound_input(
                patent_id="US10000001B2",
                claim_number=1,
                element_number=1,
                claimed_status="met",
            ),
        )
        assert "MATCH" in result

    @pytest.mark.asyncio
    async def test_mismatch(self):
        toolkit = ReportVerificationToolkit(_make_store())
        result = await toolkit.execute(
            "check_element_status",
            _bound_input(
                patent_id="US10000001B2",
                claim_number=1,
                element_number=2,
                claimed_status="met",
            ),
        )
        assert "MISMATCH" in result
        assert "NOT_MET" in result

    @pytest.mark.asyncio
    async def test_claim_not_found(self):
        toolkit = ReportVerificationToolkit(_make_store())
        result = await toolkit.execute(
            "check_element_status",
            _bound_input(
                patent_id="US10000001B2",
                claim_number=99,
                element_number=1,
                claimed_status="met",
            ),
        )
        assert "CANNOT VERIFY" in result


class TestCheckDate:
    @pytest.mark.asyncio
    async def test_expiry_match(self):
        toolkit = ReportVerificationToolkit(_make_store())
        result = await toolkit.execute(
            "check_date",
            _bound_input(
                patent_id="US10000001B2",
                date_type="expiry",
                claimed_date="2030-06-15",
            ),
        )
        assert "MATCH" in result

    @pytest.mark.asyncio
    async def test_expiry_mismatch(self):
        toolkit = ReportVerificationToolkit(_make_store())
        result = await toolkit.execute(
            "check_date",
            _bound_input(
                patent_id="US10000001B2",
                date_type="expiry",
                claimed_date="2025-01-01",
            ),
        )
        assert "MISMATCH" in result

    @pytest.mark.asyncio
    async def test_unknown_date_type(self):
        toolkit = ReportVerificationToolkit(_make_store())
        result = await toolkit.execute(
            "check_date",
            _bound_input(
                patent_id="US10000001B2",
                date_type="filing",
                claimed_date="2020-01-01",
            ),
        )
        assert "CANNOT VERIFY" in result


class TestCheckAssignee:
    @pytest.mark.asyncio
    async def test_exact_match(self):
        toolkit = ReportVerificationToolkit(_make_store())
        result = await toolkit.execute(
            "check_assignee",
            _bound_input(
                patent_id="US10000001B2",
                claimed_assignee="Pfizer Inc.",
            ),
        )
        assert "MATCH" in result

    @pytest.mark.asyncio
    async def test_fuzzy_match(self):
        toolkit = ReportVerificationToolkit(_make_store())
        result = await toolkit.execute(
            "check_assignee",
            _bound_input(
                patent_id="US10000001B2",
                claimed_assignee="Pfizer",
            ),
        )
        assert "MATCH" in result

    @pytest.mark.asyncio
    async def test_mismatch(self):
        toolkit = ReportVerificationToolkit(_make_store())
        result = await toolkit.execute(
            "check_assignee",
            _bound_input(
                patent_id="US10000001B2",
                claimed_assignee="Novartis",
            ),
        )
        assert "MISMATCH" in result


def test_every_verification_tool_requires_a_bound_assertion_id() -> None:
    toolkit = ReportVerificationToolkit(_make_store())

    for definition in toolkit.tool_definitions:
        schema = definition["input_schema"]
        assert "assertion_id" in schema["required"]
        assert "assertion_text" in schema["required"]
        assert schema["properties"]["assertion_id"]["pattern"] == (r"^A[0-9]{5}-[a-f0-9]{12}$")
        assert schema["additionalProperties"] is False


@pytest.mark.asyncio
async def test_verification_tool_rejects_unbound_calls_and_records_receipt() -> None:
    toolkit = ReportVerificationToolkit(_make_store())

    result = await toolkit.execute(
        "check_patent_exists",
        {"patent_id": "US10000001B2"},
    )

    assert result == (
        "Tool call rejected: assertion_id and exact assertion_text are missing or do not match"
    )
    assert len(toolkit.receipts) == 1
    receipt = toolkit.receipts[0]
    assert receipt.assertion_id == ""
    assert len(receipt.receipt_id) == 64
    assert receipt.result == result


@pytest.mark.asyncio
async def test_verification_receipt_is_immutable_and_assertion_bound() -> None:
    toolkit = ReportVerificationToolkit(_make_store())

    await toolkit.execute(
        "check_patent_exists",
        _bound_input(patent_id="US10000001B2"),
    )

    receipt = toolkit.receipts[0]
    assert receipt.assertion_id == _ASSERTION_ID
    assert receipt.assertion_sha256 == hashlib.sha256(_ASSERTION_TEXT.encode("utf-8")).hexdigest()
    assert receipt.tool_name == "check_patent_exists"
    assert receipt.tool_input_json == '{"patent_id":"US10000001B2"}'
    assert len(receipt.receipt_id) == 64
    with pytest.raises((AttributeError, TypeError)):
        receipt.result = "MISMATCH: tampered"  # type: ignore[misc]
