"""Contract tests for the integrity-bound report review checkpoint."""

from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from praviar_pipeline.models.hitl import CheckpointDecision, CheckpointType, HITLConfig
from praviar_pipeline.models.report_source_spans import (
    ClaimAssertionSupport,
    ClaimSourceSpanMap,
    SourceSpanReference,
    issue_source_span_attestation,
)
from praviar_pipeline.pipeline.checkpoints import await_checkpoint
from praviar_pipeline.pipeline.runtime.report_review import (
    REPORT_REVIEW_EXECUTIVE_SUMMARY_MAX_CHARS,
    build_report_review_checkpoint_context,
)

ATTESTATION_KEY = b"report-review-test-attestation-key-0001"
ATTESTATION_KEY_ID = "review-test-v1"
REPORT_ID = "report-123"
PROMPT_HASHES = {
    "report_system.txt": "a" * 64,
    "triage_system.txt": "b" * 64,
}


def _claim_source_span_map() -> ClaimSourceSpanMap:
    span = issue_source_span_attestation(
        SourceSpanReference(
            span_id="span-1",
            source_type="verified_claim_text",
            patent_id="US1234567B2",
            excerpt="PRIVATE CLAIM SOURCE TEXT",
            source_text_sha256="c" * 64,
        ),
        signing_key=ATTESTATION_KEY,
        key_id=ATTESTATION_KEY_ID,
        subject_id=REPORT_ID,
    )
    return ClaimSourceSpanMap(
        entries=[
            ClaimAssertionSupport(
                assertion_id="assertion-1",
                patent_id="US1234567B2",
                report_section="verified_claim_text",
                assertion_text="Claim 1 is supported.",
                source_span_ids=[span.span_id],
                support_status="supported",
            )
        ],
        spans={span.span_id: span},
    )


def _report(*, executive_summary: str = "High-risk claim overlap requires counsel review."):
    return SimpleNamespace(
        report_id=REPORT_ID,
        risk_summary=SimpleNamespace(
            overall_risk=SimpleNamespace(value="high"),
            executive_summary=executive_summary,
        ),
        patent_analyses=[SimpleNamespace(patent_id="US1234567B2")],
        claim_source_span_map=_claim_source_span_map(),
    )


def _build_context(*, report=None, prompt_hashes=None) -> dict:
    return build_report_review_checkpoint_context(
        report=report or _report(),
        run_id="run/123",
        analysis_failure_count=2,
        prompt_hashes=PROMPT_HASHES if prompt_hashes is None else prompt_hashes,
        evidence_attestation_key_id=ATTESTATION_KEY_ID,
        evidence_attestation_key=ATTESTATION_KEY,
    )


def test_report_review_context_is_bounded_json_safe_and_omits_private_evidence() -> None:
    report = _report(executive_summary="x" * 1_300)

    context = _build_context(report=report)
    serialized = json.dumps(context, sort_keys=True)

    assert set(context) == {
        "schema_version",
        "checkpoint_id",
        "run_id",
        "report_id",
        "overall_risk",
        "patent_count",
        "analysis_failure_count",
        "executive_summary_excerpt",
        "executive_summary_truncated",
        "claim_ledger",
        "prompt_hash_count",
        "review_payload_sha256",
    }
    assert context["schema_version"] == "report-review/v1"
    assert context["checkpoint_id"].startswith("run_123:report_review:")
    assert len(context["executive_summary_excerpt"]) == (REPORT_REVIEW_EXECUTIVE_SUMMARY_MAX_CHARS)
    assert context["executive_summary_truncated"] is True
    assert context["claim_ledger"] == {
        "assertion_count": 1,
        "source_span_count": 1,
        "needs_review_count": 0,
        "unsupported_count": 0,
        "attestation_key_ids": [ATTESTATION_KEY_ID],
    }
    assert context["prompt_hash_count"] == 2
    assert len(context["review_payload_sha256"]) == 64
    assert "PRIVATE CLAIM SOURCE TEXT" not in serialized
    assert "evidence_attestation_hmac_sha256" not in serialized
    assert PROMPT_HASHES["report_system.txt"] not in serialized
    assert ATTESTATION_KEY.decode() not in serialized


@pytest.mark.parametrize("mutation", ["preview", "ledger", "prompt_hash"])
def test_report_review_mutation_changes_digest_and_persisted_checkpoint_id(
    mutation: str,
) -> None:
    original_report = _report()
    original = _build_context(report=original_report)
    mutated_report = deepcopy(original_report)
    mutated_hashes = dict(PROMPT_HASHES)

    if mutation == "preview":
        mutated_report.risk_summary.executive_summary += " Updated."
    elif mutation == "ledger":
        mutated_report.claim_source_span_map.entries[0].assertion_text += " Updated."
    else:
        mutated_hashes["report_system.txt"] = "d" * 64

    mutated = _build_context(report=mutated_report, prompt_hashes=mutated_hashes)

    assert mutated["review_payload_sha256"] != original["review_payload_sha256"]
    assert mutated["checkpoint_id"] != original["checkpoint_id"]


@pytest.mark.parametrize("prompt_hashes", [{}, {"report.txt": "not-a-sha256"}])
def test_report_review_fails_closed_without_valid_prompt_hashes(prompt_hashes: dict) -> None:
    with pytest.raises(RuntimeError, match="prompt hash"):
        _build_context(prompt_hashes=prompt_hashes)


def test_report_review_fails_closed_for_invalid_verified_source_attestation() -> None:
    report = _report()
    span = report.claim_source_span_map.spans["span-1"]
    report.claim_source_span_map.spans["span-1"] = span.model_copy(
        update={"evidence_attestation_hmac_sha256": "0" * 64}
    )

    with pytest.raises(RuntimeError, match="attestation is missing or invalid"):
        _build_context(report=report)


@pytest.mark.parametrize("overall_risk", ["", "needs_review", "HIGH_RISK"])
def test_report_review_fails_closed_for_invalid_overall_risk(overall_risk: str) -> None:
    report = _report()
    report.risk_summary.overall_risk.value = overall_risk

    with pytest.raises(RuntimeError, match="overall risk is invalid"):
        _build_context(report=report)


def test_report_review_fails_closed_without_executive_summary() -> None:
    with pytest.raises(RuntimeError, match="executive summary is required"):
        _build_context(report=_report(executive_summary="  "))


def test_report_review_rejects_negative_analysis_failure_count() -> None:
    with pytest.raises(ValidationError, match="analysis_failure_count"):
        build_report_review_checkpoint_context(
            report=_report(),
            run_id="run-123",
            analysis_failure_count=-1,
            prompt_hashes=PROMPT_HASHES,
            evidence_attestation_key_id=ATTESTATION_KEY_ID,
            evidence_attestation_key=ATTESTATION_KEY,
        )


@pytest.mark.asyncio
async def test_report_review_event_and_provider_receive_exact_digest_bound_context() -> None:
    context = _build_context()
    progress = MagicMock()
    received: list[dict] = []
    approved = CheckpointDecision(
        checkpoint_type=CheckpointType.REPORT_REVIEW,
        action="approve",
        reviewer_id="reviewer-1",
    )

    async def provider(checkpoint_type: CheckpointType, provider_context: dict):
        assert checkpoint_type == CheckpointType.REPORT_REVIEW
        received.append(provider_context)
        return approved

    decision = await await_checkpoint(
        CheckpointType.REPORT_REVIEW,
        context,
        progress,
        HITLConfig(
            enabled=True,
            checkpoints=[CheckpointType.REPORT_REVIEW],
            auto_skip_timeout_minutes=1,
        ),
        decision_provider=provider,
        poll_interval_seconds=0,
    )

    assert decision is approved
    assert received == [context]
    event = progress.call_args.args[3]
    assert event["context"] == context
    assert event["checkpoint_id"] == context["checkpoint_id"]
