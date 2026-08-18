"""Unit tests for verify_report() two-phase approach."""

from __future__ import annotations

import hashlib
import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from praviar_pipeline.agents.tools.report_verification_tools import (
    ReportVerificationToolkit,
    VerificationToolReceipt,
)
from praviar_pipeline.pipeline.report_verifier import (
    MAX_VERIFICATION_CHUNK_CHARS,
    _tool_receipts_support_outcomes,
    count_verifiable_assertions,
    enumerate_verifiable_assertions,
    verify_report,
)

_PASS_JSON = json.dumps(
    {
        "total_claims_checked": 1,
        "claims_correct": 1,
        "claims_incorrect": 0,
        "claims_unverifiable": 0,
        "factual_accuracy_rate": 1.0,
        "corrections_needed": [],
        "omissions_found": [],
        "overall_assessment": "PASS",
    }
)


def _make_claude_mock(
    *,
    phase1_result: str | Exception | None = None,
    phase2_result: str | Exception = _PASS_JSON,
    phase1_usage: dict | None = None,
    phase2_usage: dict | None = None,
    with_tool_receipts: bool = True,
):
    """Build a ClaudeClient mock for the two-phase verifier.

    complete_text is called twice: first for the tool-based analysis (phase 1),
    then for the JSON extraction (phase 2).
    """
    claude = MagicMock()
    claude._models.analysis = "claude-sonnet-4-6"
    claude.load_prompt = MagicMock(return_value="system prompt text")

    p1_usage = phase1_usage or {"input_tokens": 100, "output_tokens": 200}
    p2_usage = phase2_usage or {"input_tokens": 50, "output_tokens": 100}
    call_count: list[int] = [0]

    async def _complete_text(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            if isinstance(phase1_result, Exception):
                raise phase1_result
            resolved_phase1 = phase1_result
            assertions_by_id = dict(
                re.findall(
                    r"^\[(A\d{5}-[a-f0-9]{12})\] (.+)$",
                    kwargs["user"],
                    flags=re.MULTILINE,
                )
            )
            if resolved_phase1 is None:
                resolved_phase1 = "\n".join(
                    f"[{assertion_id}] CORRECT — verified by source evidence"
                    for assertion_id in assertions_by_id
                )
            if with_tool_receipts:
                kwargs["toolkit"].receipts = _receipts_for_analysis(
                    resolved_phase1,
                    assertions_by_id,
                )
            return (resolved_phase1, p1_usage)
        else:
            if isinstance(phase2_result, Exception):
                raise phase2_result
            return (phase2_result, p2_usage)

    claude.complete_text = AsyncMock(side_effect=_complete_text)
    return claude


def _analysis_for(report_text: str, statuses: list[str]) -> str:
    inventory = enumerate_verifiable_assertions(report_text)
    assert len(inventory) == len(statuses)
    return "\n".join(
        f"[{assertion_id}] {status} — evidence outcome"
        for (assertion_id, _), status in zip(inventory, statuses, strict=True)
    )


def _receipts_for_analysis(
    analysis_text: str,
    assertions_by_id: dict[str, str],
) -> tuple[VerificationToolReceipt, ...]:
    receipts = []
    for assertion_id, status in re.findall(
        r"\[(A\d{5}-[a-f0-9]{12})\]\s+"
        r"(CORRECT|INCORRECT|UNVERIFIABLE)\b",
        analysis_text,
    ):
        assertion_text = assertions_by_id[assertion_id]
        patent_match = re.search(r"\b(?:US|EP|WO)\s?[A-Z0-9,/-]+\b", assertion_text)
        patent_id = patent_match.group(0) if patent_match else assertion_text
        tool_input_json = json.dumps(
            {"patent_id": patent_id},
            sort_keys=True,
            separators=(",", ":"),
        )
        assertion_sha256 = hashlib.sha256(assertion_text.encode()).hexdigest()
        tool_input_sha256 = hashlib.sha256(tool_input_json.encode()).hexdigest()
        result = {
            "CORRECT": f"FOUND: {patent_id}",
            "INCORRECT": f"MISMATCH: {patent_id}",
            "UNVERIFIABLE": (
                "Tool call rejected: verification query is not applicable to the bound assertion"
            ),
        }[status]
        canonical = json.dumps(
            {
                "assertion_id": assertion_id,
                "assertion_sha256": assertion_sha256,
                "result": result,
                "tool_input_json": tool_input_json,
                "tool_input_sha256": tool_input_sha256,
                "tool_name": "check_patent_exists",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        receipts.append(
            VerificationToolReceipt(
                assertion_id=assertion_id,
                assertion_sha256=assertion_sha256,
                receipt_id=hashlib.sha256(canonical.encode()).hexdigest(),
                result=result,
                tool_input_json=tool_input_json,
                tool_input_sha256=tool_input_sha256,
                tool_name="check_patent_exists",
            )
        )
    return tuple(receipts)


@pytest.mark.asyncio
async def test_verify_report_success_path() -> None:
    """Phase 1 produces analysis text, Phase 2 extracts PASS JSON."""
    claude = _make_claude_mock()
    data_store = MagicMock()

    with patch(
        "praviar_pipeline.pipeline.report_verifier.ReportVerificationToolkit",
        return_value=MagicMock(),
    ):
        result, in_tokens, out_tokens = await verify_report(
            claude,
            "Patent US10000001B2 exists in pipeline data.",
            data_store,
        )

    assert result.overall_assessment == "PASS"
    assert result.total_claims_checked == 1
    assert result.claims_incorrect == 0
    assert result.factual_accuracy_rate == 1.0
    assert in_tokens == 150  # 100 + 50
    assert out_tokens == 300  # 200 + 100
    assert claude.complete_text.call_count == 2


@pytest.mark.asyncio
async def test_verify_report_phase1_failure_abstains_without_phase2() -> None:
    """A missing verification analysis can never be coerced into a PASS."""
    claude = _make_claude_mock(phase1_result=RuntimeError("network error"))
    data_store = MagicMock()

    with patch(
        "praviar_pipeline.pipeline.report_verifier.ReportVerificationToolkit",
        return_value=MagicMock(),
    ):
        result, in_tokens, out_tokens = await verify_report(claude, "report text", data_store)

    assert result.overall_assessment == "ERROR"
    assert result.factual_accuracy_rate == 0.0
    assert in_tokens == 0
    assert out_tokens == 0
    assert claude.complete_text.call_count == 1


@pytest.mark.asyncio
async def test_verify_report_preserves_unverifiable_claim_coverage() -> None:
    report_text = "Patent US10000001B2 exists in pipeline data. Second assertion. Third assertion."
    phase2 = json.dumps(
        {
            "total_claims_checked": 3,
            "claims_correct": 1,
            "claims_incorrect": 0,
            "claims_unverifiable": 2,
            "factual_accuracy_rate": 1 / 3,
            "corrections_needed": [],
            "omissions_found": ["Claim text unavailable for two assertions"],
            "overall_assessment": "FAIL",
        }
    )
    claude = _make_claude_mock(
        phase1_result=_analysis_for(
            report_text,
            ["CORRECT", "UNVERIFIABLE", "UNVERIFIABLE"],
        ),
        phase2_result=phase2,
    )

    with patch(
        "praviar_pipeline.pipeline.report_verifier.ReportVerificationToolkit",
        return_value=MagicMock(),
    ):
        result, _, _ = await verify_report(
            claude,
            report_text,
            MagicMock(),
        )

    assert result.claims_unverifiable == 2
    assert result.overall_assessment == "FAIL"
    extraction_prompt = claude.complete_text.await_args_list[1].kwargs["user"]
    assert "claims_unverifiable MUST be 0" not in extraction_prompt
    assert '"overall_assessment": "PASS"' not in extraction_prompt


@pytest.mark.asyncio
async def test_verify_report_fails_closed_on_uncategorized_assertions() -> None:
    phase2 = json.dumps(
        {
            "total_claims_checked": 3,
            "claims_correct": 2,
            "claims_incorrect": 0,
            "claims_unverifiable": 0,
            "factual_accuracy_rate": 2 / 3,
            "corrections_needed": [],
            "omissions_found": [],
            "overall_assessment": "PASS",
        }
    )
    claude = _make_claude_mock(phase2_result=phase2)

    with patch(
        "praviar_pipeline.pipeline.report_verifier.ReportVerificationToolkit",
        return_value=MagicMock(),
    ):
        result, _, _ = await verify_report(claude, "report text", MagicMock())

    assert result.overall_assessment == "ERROR"
    assert result.total_claims_checked == 1
    assert result.claims_unverifiable == 1


@pytest.mark.asyncio
async def test_verify_report_returns_error_when_extraction_fails() -> None:
    """When Phase 2 JSON extraction raises, returns ERROR VerificationReport."""
    claude = _make_claude_mock(
        phase1_result=RuntimeError("phase 1 failed"),
        phase2_result=ValueError("phase 2 also failed"),
    )
    data_store = MagicMock()

    with patch(
        "praviar_pipeline.pipeline.report_verifier.ReportVerificationToolkit",
        return_value=MagicMock(),
    ):
        result, in_tokens, out_tokens = await verify_report(claude, "report text", data_store)

    assert result.overall_assessment == "ERROR"
    assert result.factual_accuracy_rate == 0.0
    assert in_tokens == 0
    assert out_tokens == 0


@pytest.mark.asyncio
async def test_verify_report_bad_json_in_phase2_returns_error() -> None:
    """When Phase 2 returns non-parseable text, returns ERROR VerificationReport."""
    claude = _make_claude_mock(phase2_result="This is not JSON at all.")
    data_store = MagicMock()

    with patch(
        "praviar_pipeline.pipeline.report_verifier.ReportVerificationToolkit",
        return_value=MagicMock(),
    ):
        result, _, _ = await verify_report(
            claude,
            "Patent US10000001B2 exists in pipeline data.",
            data_store,
        )

    assert result.overall_assessment == "ERROR"
    assert result.factual_accuracy_rate == 0.0


@pytest.mark.asyncio
async def test_verify_report_skipped_when_disabled() -> None:
    """When verification is disabled in settings, returns SKIPPED immediately."""
    claude = _make_claude_mock()
    data_store = MagicMock()

    with patch(
        "praviar_pipeline.pipeline.report_verifier.get_settings",
        return_value=MagicMock(report_verification_enabled=False),
    ):
        result, in_tokens, out_tokens = await verify_report(claude, "report text", data_store)

    assert result.overall_assessment == "SKIPPED"
    assert result.factual_accuracy_rate == 1.0
    assert in_tokens == 0
    assert out_tokens == 0
    claude.complete_text.assert_not_called()


@pytest.mark.asyncio
async def test_verify_report_covers_long_reports_in_complete_chunks() -> None:
    claude = MagicMock()
    claude._models.analysis = "claude-sonnet-4-6"
    claude.load_prompt.return_value = "system prompt text"
    chunk_json = json.dumps(
        {
            "total_claims_checked": 1,
            "claims_correct": 0,
            "claims_incorrect": 0,
            "claims_unverifiable": 1,
            "factual_accuracy_rate": 0.0,
            "corrections_needed": [],
            "omissions_found": [],
            "overall_assessment": "FAIL",
        }
    )
    first_chunk = "A" * MAX_VERIFICATION_CHUNK_CHARS
    second_chunk = "UNIQUE_FINAL_TAIL"
    responses = [
        (
            _analysis_for(first_chunk, ["UNVERIFIABLE"]),
            {"input_tokens": 10, "output_tokens": 2},
        ),
        (chunk_json, {"input_tokens": 3, "output_tokens": 1}),
        (
            _analysis_for(second_chunk, ["UNVERIFIABLE"]),
            {"input_tokens": 5, "output_tokens": 2},
        ),
        (chunk_json, {"input_tokens": 3, "output_tokens": 1}),
    ]
    claude.complete_text = AsyncMock(side_effect=responses)
    report_text = first_chunk + second_chunk
    toolkit = MagicMock()
    toolkit.receipts = (
        *_receipts_for_analysis(
            responses[0][0],
            dict(enumerate_verifiable_assertions(first_chunk)),
        ),
        *_receipts_for_analysis(
            responses[2][0],
            dict(enumerate_verifiable_assertions(second_chunk)),
        ),
    )

    with patch(
        "praviar_pipeline.pipeline.report_verifier.ReportVerificationToolkit",
        return_value=toolkit,
    ):
        result, in_tokens, out_tokens = await verify_report(
            claude,
            report_text,
            MagicMock(),
        )

    verification_calls = [
        call
        for call in claude.complete_text.await_args_list
        if call.kwargs["role"] == "verification"
    ]
    assert len(verification_calls) == 2
    assert "Chunk 1/2" in verification_calls[0].kwargs["user"]
    assert "Chunk 2/2" in verification_calls[1].kwargs["user"]
    assert "UNIQUE_FINAL_TAIL" in verification_calls[1].kwargs["user"]
    assert "truncated" not in verification_calls[0].kwargs["user"].lower()
    assert result.total_claims_checked == 2
    assert result.claims_correct == 0
    assert result.claims_unverifiable == 2
    assert result.factual_accuracy_rate == 0.0
    assert result.overall_assessment == "FAIL"
    assert in_tokens == 21
    assert out_tokens == 6


def test_count_verifiable_assertions_ignores_headings_and_counts_material_rows() -> None:
    assert (
        count_verifiable_assertions(
            "# Risk summary\n"
            "The compound maps to claim 1. Evidence is incomplete; counsel must review.\n"
            "- US123 remains active\n"
            "---\n"
        )
        == 4
    )


@pytest.mark.asyncio
async def test_verify_report_rejects_model_selected_smaller_denominator() -> None:
    claude = _make_claude_mock(phase2_result=_PASS_JSON)

    with patch(
        "praviar_pipeline.pipeline.report_verifier.ReportVerificationToolkit",
        return_value=MagicMock(),
    ):
        result, _, _ = await verify_report(
            claude,
            "First assertion. Second assertion. Third assertion.",
            MagicMock(),
        )

    assert result.total_claims_checked == 3
    assert result.claims_unverifiable == 3
    assert result.overall_assessment == "ERROR"


@pytest.mark.asyncio
async def test_verify_report_rejects_aggregate_pass_without_every_assertion_outcome() -> None:
    report_text = "First assertion. Second assertion. Third assertion."
    first_assertion_id = enumerate_verifiable_assertions(report_text)[0][0]
    aggregate_pass = json.dumps(
        {
            "total_claims_checked": 3,
            "claims_correct": 3,
            "claims_incorrect": 0,
            "claims_unverifiable": 0,
            "factual_accuracy_rate": 1.0,
            "corrections_needed": [],
            "omissions_found": [],
            "overall_assessment": "PASS",
        }
    )
    claude = _make_claude_mock(
        phase1_result=(f"[{first_assertion_id}] CORRECT — only the first assertion was checked"),
        phase2_result=aggregate_pass,
        with_tool_receipts=False,
    )

    with patch(
        "praviar_pipeline.pipeline.report_verifier.ReportVerificationToolkit",
        return_value=MagicMock(),
    ):
        result, _, _ = await verify_report(claude, report_text, MagicMock())

    assert result.total_claims_checked == 3
    assert result.claims_unverifiable == 3
    assert result.overall_assessment == "ERROR"


@pytest.mark.asyncio
async def test_verify_report_rejects_all_correct_outcomes_without_tool_receipts() -> None:
    """A model cannot self-attest a PASS without deterministic tool evidence."""
    report_text = "First assertion. Second assertion. Third assertion."
    aggregate_pass = json.dumps(
        {
            "total_claims_checked": 3,
            "claims_correct": 3,
            "claims_incorrect": 0,
            "claims_unverifiable": 0,
            "factual_accuracy_rate": 1.0,
            "corrections_needed": [],
            "omissions_found": [],
            "overall_assessment": "PASS",
        }
    )
    claude = _make_claude_mock(
        phase1_result=_analysis_for(
            report_text,
            ["CORRECT", "CORRECT", "CORRECT"],
        ),
        phase2_result=aggregate_pass,
        with_tool_receipts=False,
    )

    with patch(
        "praviar_pipeline.pipeline.report_verifier.ReportVerificationToolkit",
        return_value=MagicMock(receipts=()),
    ):
        result, _, _ = await verify_report(claude, report_text, MagicMock())

    assert result.total_claims_checked == 3
    assert result.claims_correct == 0
    assert result.claims_unverifiable == 3
    assert result.overall_assessment == "ERROR"


@pytest.mark.asyncio
async def test_unrelated_found_receipt_cannot_prove_design_around_assertion() -> None:
    """A positive entity lookup is not semantic proof of an unrelated conclusion."""
    assertion_text = "US10000001B2 has no design-around."
    assertion_id = enumerate_verifiable_assertions(assertion_text)[0][0]
    store = MagicMock()
    store.get_analysis.return_value = SimpleNamespace(
        risk_level=SimpleNamespace(value="high"),
        assignee="Pfizer Inc.",
        expiry_date=None,
    )
    toolkit = ReportVerificationToolkit(store)

    result = await toolkit.execute(
        "check_patent_exists",
        {
            "assertion_id": assertion_id,
            "assertion_text": assertion_text,
            "patent_id": "US10000001B2",
        },
    )

    assert result.startswith("FOUND:")
    assert (
        _tool_receipts_support_outcomes(
            toolkit,
            {assertion_id: "CORRECT"},
            {assertion_id: assertion_text},
        )
        is False
    )


@pytest.mark.asyncio
async def test_unrelated_patent_query_is_rejected_before_data_access() -> None:
    assertion_text = "No design-around exists."
    assertion_id = enumerate_verifiable_assertions(assertion_text)[0][0]
    store = MagicMock()
    toolkit = ReportVerificationToolkit(store)

    result = await toolkit.execute(
        "check_patent_exists",
        {
            "assertion_id": assertion_id,
            "assertion_text": assertion_text,
            "patent_id": "US10000001B2",
        },
    )

    assert "not applicable" in result
    store.get_analysis.assert_not_called()


@pytest.mark.asyncio
async def test_positive_and_negative_receipts_cannot_compose_a_correct_outcome() -> None:
    assertion_text = "Patent US10000001B2 and patent US9999999A1 exist in pipeline data."
    assertion_id = enumerate_verifiable_assertions(assertion_text)[0][0]
    known = SimpleNamespace(
        risk_level=SimpleNamespace(value="high"),
        assignee="Pfizer Inc.",
        expiry_date=None,
    )
    store = MagicMock()
    store.get_analysis.side_effect = lambda patent_id: (
        known if patent_id == "US10000001B2" else None
    )
    store.all_patent_ids.return_value = {"US10000001B2"}
    toolkit = ReportVerificationToolkit(store)
    for patent_id in ("US10000001B2", "US9999999A1"):
        await toolkit.execute(
            "check_patent_exists",
            {
                "assertion_id": assertion_id,
                "assertion_text": assertion_text,
                "patent_id": patent_id,
            },
        )

    assert toolkit.receipts[0].result.startswith("FOUND:")
    assert toolkit.receipts[1].result.startswith("NOT FOUND:")
    assert (
        _tool_receipts_support_outcomes(
            toolkit,
            {assertion_id: "CORRECT"},
            {assertion_id: assertion_text},
        )
        is False
    )
