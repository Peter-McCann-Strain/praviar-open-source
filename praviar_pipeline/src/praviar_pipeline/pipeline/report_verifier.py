"""LLM-based report verifier — tool-based analysis then structured JSON extraction."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.agents.tools.report_verification_tools import (
    ReportVerificationToolkit,
    VerificationToolReceipt,
    verification_tool_receipt_is_applicable,
)
from praviar_pipeline.clients.claude_prompting import extract_json
from praviar_pipeline.config import get_settings
from praviar_pipeline.models.report_sections import VerificationReport
from praviar_pipeline.sanitize import sanitize_untrusted_text
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from praviar_pipeline.clients.claude import ClaudeClient
    from praviar_pipeline.pipeline.report_data_store import ReportDataStore

logger = structlog.get_logger()
MAX_VERIFICATION_CHUNK_CHARS = 100_000
_ASSERTION_BOUNDARY = re.compile(r"(?<=[.!?])\s+|[\n;]+")
_ASSERTION_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'/-]*")
_RECEIPT_TOKEN = re.compile(r"[A-Za-z0-9]+")
_PROOF_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "with",
    }
)
_TOOL_PROOF_VOCABULARY = {
    "check_patent_exists": {
        "analysis",
        "analysed",
        "analyzed",
        "data",
        "exist",
        "exists",
        "found",
        "identified",
        "included",
        "patent",
        "pipeline",
        "publication",
        "report",
    },
    "check_risk_level": {
        "assessed",
        "assessment",
        "correct",
        "correctly",
        "level",
        "patent",
        "rated",
        "rating",
        "risk",
        "stated",
    },
    "check_element_status": {
        "claim",
        "correct",
        "correctly",
        "element",
        "met",
        "not",
        "partial",
        "partially",
        "patent",
        "stated",
        "status",
        "unclear",
    },
    "check_date": {
        "date",
        "expired",
        "expires",
        "expiry",
        "filed",
        "filing",
        "grant",
        "granted",
        "patent",
        "priority",
        "stated",
    },
    "check_assignee": {
        "assigned",
        "assignee",
        "correct",
        "correctly",
        "owner",
        "owned",
        "patent",
        "stated",
    },
}


def enumerate_verifiable_assertions(report_text: str) -> list[tuple[str, str]]:
    """Return a deterministic, text-bound assertion inventory."""
    assertions: list[tuple[str, str]] = []
    for raw_segment in _ASSERTION_BOUNDARY.split(report_text):
        segment = raw_segment.strip()
        if not segment or segment.startswith("#"):
            continue
        segment = re.sub(r"^(?:[-*+]|\d+[.)])\s+", "", segment).strip()
        tokens = _ASSERTION_TOKEN.findall(segment)
        if any(character.isalpha() for character in segment) and (
            len(tokens) >= 2 or len(segment) >= 8
        ):
            digest = hashlib.sha256(segment.encode("utf-8")).hexdigest()[:12]
            assertion_id = f"A{len(assertions) + 1:05d}-{digest}"
            assertions.append((assertion_id, segment))
    return assertions


def count_verifiable_assertions(report_text: str) -> int:
    """Return a deterministic denominator for verifier coverage.

    The LLM may categorize assertions, but it must never choose how much of the
    supplied report counts. Headings and visual separators are excluded; every
    substantive sentence, bullet, table row, or semicolon-delimited proposition
    contributes one independently required outcome.
    """
    return len(enumerate_verifiable_assertions(report_text))


def _parse_assertion_outcomes(
    analysis_text: str,
    assertion_ids: list[str],
) -> dict[str, str] | None:
    outcomes: dict[str, str] = {}
    for assertion_id in assertion_ids:
        matches = re.findall(
            rf"\[{re.escape(assertion_id)}\]\s+"
            r"(CORRECT|INCORRECT|UNVERIFIABLE)\b",
            analysis_text,
            flags=re.IGNORECASE,
        )
        if len(matches) != 1:
            return None
        outcomes[assertion_id] = matches[0].upper()
    return outcomes


def _tool_receipts_support_outcomes(
    toolkit: ReportVerificationToolkit,
    assertion_outcomes: dict[str, str],
    assertions_by_id: dict[str, str],
) -> bool:
    receipts = toolkit.receipts
    for assertion_id, outcome in assertion_outcomes.items():
        assertion_text = assertions_by_id[assertion_id]
        assertion_sha256 = hashlib.sha256(assertion_text.encode("utf-8")).hexdigest()
        applicable = [
            receipt
            for receipt in receipts
            if receipt.assertion_id == assertion_id
            and receipt.assertion_sha256 == assertion_sha256
            and (
                outcome == "UNVERIFIABLE"
                or verification_tool_receipt_is_applicable(receipt, assertion_text)
            )
        ]
        if not applicable:
            return False
        results = [receipt.result.strip().upper() for receipt in applicable]
        if outcome == "CORRECT":
            positive_prefixes = ("MATCH:", "MATCH (FUZZY):", "FOUND:")
            supported = bool(results) and all(
                result.startswith(positive_prefixes) for result in results
            )
        elif outcome == "INCORRECT":
            supported = any(
                result.startswith(("MISMATCH:", "PARTIAL MATCH:", "NOT FOUND:"))
                for result in results
            )
        else:
            supported = any(
                result.startswith(
                    (
                        "CANNOT VERIFY:",
                        "NOT FOUND:",
                        "TOOL CALL REJECTED:",
                        "TOOL '",
                        "UNKNOWN TOOL:",
                    )
                )
                for result in results
            )
        if not supported or (
            outcome != "UNVERIFIABLE"
            and not _receipts_cover_assertion_tokens(applicable, assertion_text)
        ):
            return False
    return True


def _receipts_cover_assertion_tokens(
    receipts: list[VerificationToolReceipt],
    assertion_text: str,
) -> bool:
    """Reject receipts that prove only an unrelated fragment of an assertion."""
    assertion_tokens = {
        token.lower()
        for token in _RECEIPT_TOKEN.findall(assertion_text)
        if token.lower() not in _PROOF_STOPWORDS
    }
    evidence_tokens: set[str] = set()
    for receipt in receipts:
        evidence_tokens.update(
            token.lower()
            for token in _RECEIPT_TOKEN.findall(f"{receipt.tool_input_json} {receipt.result}")
        )
        evidence_tokens.update(_TOOL_PROOF_VOCABULARY.get(receipt.tool_name, set()))
    return bool(assertion_tokens and assertion_tokens.issubset(evidence_tokens))


def _build_extraction_prompt(
    analysis_text: str,
    *,
    expected_assertion_count: int,
) -> str:
    """Build a prompt for the JSON extraction step."""
    if not analysis_text.strip():
        raise ValueError("Verification analysis is unavailable")
    context_section = sanitize_untrusted_text(
        analysis_text,
        max_len=8000,
        data_type="model_verification_analysis",
    )

    return f"""{context_section}

Based on the above, output ONLY a valid JSON object that summarises the
verification result. Start immediately with {{ - zero text before or after the JSON.

RULES:
1. total_claims_checked MUST equal {expected_assertion_count}, the deterministic number of
   substantive assertions in the supplied report chunk. You may classify that fixed
   inventory, but you may not choose, shrink, or expand the denominator.
2. Preserve every unavailable or unverified claim as claims_unverifiable; never infer that
   source or claim data was available.
3. factual_accuracy_rate = claims_correct / total_claims_checked when the denominator is
   nonzero; otherwise use 0.0 and overall_assessment="ERROR".
4. overall_assessment is "PASS" only when accuracy ≥ 0.95 AND claims_unverifiable=0;
   otherwise use "PASS_WITH_CORRECTIONS", "FAIL", or "ERROR" according to the analysis.
5. Do not invent checked claims, corrections, omissions, or successful tool results.

{{
  "total_claims_checked": <integer ≥ 0>,
  "claims_correct": <integer>,
  "claims_incorrect": <integer>,
  "claims_unverifiable": <integer>,
  "factual_accuracy_rate": <float 0-1>,
  "corrections_needed": <array>,
  "omissions_found": <array>,
  "overall_assessment": <"PASS"|"PASS_WITH_CORRECTIONS"|"FAIL"|"ERROR">
}}"""


async def verify_report(
    claude: ClaudeClient,
    assembled_text: str,
    data_store: ReportDataStore,
) -> tuple[VerificationReport, int, int]:
    """Verify the assembled report using LLM with verification tools.

    Two-phase approach:
    1. Tool-based analysis: Claude uses fact-check tools and produces prose analysis.
    2. JSON extraction: a short follow-up call converts the prose into structured output.

    This avoids both the "schema too complex" error from native structured output and the
    "model writes prose instead of JSON" failure from complete_with_thinking.

    Returns (VerificationReport, input_tokens, output_tokens).
    """
    settings = get_settings()

    if not settings.report_verification_enabled:
        logger.info("report_verification_skipped")
        return (
            VerificationReport(
                overall_assessment="SKIPPED",
                factual_accuracy_rate=1.0,
            ),
            0,
            0,
        )

    toolkit = ReportVerificationToolkit(data_store)
    system_prompt = claude.load_prompt("report_verification_system.txt")
    chunks = [
        assembled_text[start : start + MAX_VERIFICATION_CHUNK_CHARS]
        for start in range(0, len(assembled_text), MAX_VERIFICATION_CHUNK_CHARS)
    ] or [""]
    total_in = 0
    total_out = 0
    chunk_reports: list[VerificationReport] = []

    for chunk_index, report_text in enumerate(chunks, start=1):
        chunk_label = f"{chunk_index}/{len(chunks)}"
        assertion_inventory = enumerate_verifiable_assertions(report_text)
        expected_assertion_count = len(assertion_inventory)
        # IDs are ordered and include a digest of the exact assertion text. Give
        # the verifier the exact mapping once so every tool call can copy and
        # cryptographically bind the assertion without duplicating the chunk.
        inventory_text = "\n".join(
            f"[{assertion_id}] {assertion_text}"
            for assertion_id, assertion_text in assertion_inventory
        )
        user_prompt = (
            "Verify this complete deterministic assertion inventory, extracted "
            "from an untrusted report chunk, using the "
            "verification tools. Do not make claims about chunks you have not been "
            f"shown. Chunk {chunk_label}. The deterministic assertion inventory contains "
            f"exactly {expected_assertion_count} substantive assertions; return one "
            "categorized outcome for every assertion. Your analysis MUST contain exactly "
            "one line per inventory item in the form "
            "`[ASSERTION_ID] CORRECT|INCORRECT|UNVERIFIABLE — evidence`. Missing, "
            "duplicated, or unknown outcomes fail the report.\n\n"
            "Inventory IDs are in report order and each suffix is the SHA-256 prefix "
            "of the exact assertion text. Every tool call MUST copy both the exact "
            "assertion ID and exact assertion text from this inventory.\n"
            + sanitize_untrusted_text(
                inventory_text,
                max_len=MAX_VERIFICATION_CHUNK_CHARS + (len(assertion_inventory) * 32),
                data_type="deterministic_assertion_inventory",
            )
        )
        analysis_text = ""
        try:
            analysis_text, phase1_usage = await claude.complete_text(
                system=system_prompt,
                user=user_prompt,
                model=claude._models.analysis,
                max_tokens=16384,
                toolkit=toolkit,
                effort="high",
                cache_system=True,
                role="verification",
            )
            total_in += phase1_usage.get("input_tokens", 0)
            total_out += phase1_usage.get("output_tokens", 0)
            logger.info(
                "report_verification_analysis_complete",
                analysis_length=len(analysis_text),
                chunk=chunk_label,
            )
        except Exception as exc:
            logger.warning(
                "report_verification_analysis_failed",
                chunk=chunk_label,
                error_type=safe_exception_type(exc),
            )

        if not analysis_text.strip():
            return (
                VerificationReport(
                    total_claims_checked=expected_assertion_count,
                    claims_unverifiable=expected_assertion_count,
                    overall_assessment="ERROR",
                    factual_accuracy_rate=0.0,
                ),
                total_in,
                total_out,
            )

        assertion_outcomes = _parse_assertion_outcomes(
            analysis_text,
            [assertion_id for assertion_id, _ in assertion_inventory],
        )
        if assertion_outcomes is None:
            logger.error(
                "report_verification_assertion_outcomes_incomplete",
                chunk=chunk_label,
                expected_assertions=expected_assertion_count,
            )
            return (
                VerificationReport(
                    total_claims_checked=expected_assertion_count,
                    claims_unverifiable=expected_assertion_count,
                    overall_assessment="ERROR",
                    factual_accuracy_rate=0.0,
                ),
                total_in,
                total_out,
            )

        if not _tool_receipts_support_outcomes(
            toolkit,
            assertion_outcomes,
            dict(assertion_inventory),
        ):
            logger.error(
                "report_verification_tool_receipts_incomplete",
                chunk=chunk_label,
                expected_assertions=expected_assertion_count,
            )
            return (
                VerificationReport(
                    total_claims_checked=expected_assertion_count,
                    claims_unverifiable=expected_assertion_count,
                    overall_assessment="ERROR",
                    factual_accuracy_rate=0.0,
                ),
                total_in,
                total_out,
            )

        extraction_prompt = _build_extraction_prompt(
            analysis_text,
            expected_assertion_count=expected_assertion_count,
        )
        extraction_system = (
            "You are a JSON extractor for a patent verification system. "
            "Output ONLY a valid JSON object — the very first character must be `{`. "
            "Zero text before or after the JSON."
        )
        try:
            extraction_text, extract_usage = await claude.complete_text(
                system=extraction_system,
                user=extraction_prompt,
                model=claude._models.analysis,
                max_tokens=1024,
                role="verification_extraction",
            )
            total_in += extract_usage.get("input_tokens", 0)
            total_out += extract_usage.get("output_tokens", 0)
            chunk_report = VerificationReport.model_validate_json(extract_json(extraction_text))
            if chunk_report.total_claims_checked != expected_assertion_count:
                logger.error(
                    "report_verification_denominator_mismatch",
                    chunk=chunk_label,
                    expected_assertions=expected_assertion_count,
                    model_claims_checked=chunk_report.total_claims_checked,
                )
                return (
                    VerificationReport(
                        total_claims_checked=expected_assertion_count,
                        claims_unverifiable=expected_assertion_count,
                        overall_assessment="ERROR",
                        factual_accuracy_rate=0.0,
                    ),
                    total_in,
                    total_out,
                )
            outcome_counts = Counter(assertion_outcomes.values())
            expected_counts = {
                "claims_correct": outcome_counts["CORRECT"],
                "claims_incorrect": outcome_counts["INCORRECT"],
                "claims_unverifiable": outcome_counts["UNVERIFIABLE"],
            }
            observed_counts = {
                "claims_correct": chunk_report.claims_correct,
                "claims_incorrect": chunk_report.claims_incorrect,
                "claims_unverifiable": chunk_report.claims_unverifiable,
            }
            if observed_counts != expected_counts:
                logger.error(
                    "report_verification_assertion_outcomes_disagree",
                    chunk=chunk_label,
                    expected_counts=expected_counts,
                    observed_counts=observed_counts,
                )
                return (
                    VerificationReport(
                        total_claims_checked=expected_assertion_count,
                        claims_unverifiable=expected_assertion_count,
                        overall_assessment="ERROR",
                        factual_accuracy_rate=0.0,
                    ),
                    total_in,
                    total_out,
                )
            chunk_reports.append(chunk_report)
        except Exception as exc:
            logger.error(
                "report_verification_extraction_failed",
                chunk=chunk_label,
                error_type=safe_exception_type(exc),
            )
            return (
                VerificationReport(
                    total_claims_checked=expected_assertion_count,
                    claims_unverifiable=expected_assertion_count,
                    overall_assessment="ERROR",
                    factual_accuracy_rate=0.0,
                ),
                total_in,
                total_out,
            )

    claims_correct = sum(report.claims_correct for report in chunk_reports)
    total_claims_checked = sum(report.total_claims_checked for report in chunk_reports)
    claims_incorrect = sum(report.claims_incorrect for report in chunk_reports)
    claims_unverifiable = sum(report.claims_unverifiable for report in chunk_reports)
    corrections_needed = [
        correction for report in chunk_reports for correction in report.corrections_needed
    ]
    omissions_found = [omission for report in chunk_reports for omission in report.omissions_found]
    if any(str(report.overall_assessment).strip().upper() == "ERROR" for report in chunk_reports):
        overall_assessment = "ERROR"
    elif claims_incorrect or claims_unverifiable or corrections_needed:
        overall_assessment = "FAIL"
    elif all(str(report.overall_assessment).strip().upper() == "PASS" for report in chunk_reports):
        overall_assessment = "PASS"
    else:
        overall_assessment = "PASS_WITH_CORRECTIONS"
    result = VerificationReport(
        total_claims_checked=total_claims_checked,
        claims_correct=claims_correct,
        claims_incorrect=claims_incorrect,
        claims_unverifiable=claims_unverifiable,
        factual_accuracy_rate=(
            claims_correct / total_claims_checked if total_claims_checked else 0.0
        ),
        corrections_needed=corrections_needed,
        omissions_found=omissions_found,
        overall_assessment=overall_assessment,
    )
    logger.info(
        "report_verification_complete",
        report_chars=len(assembled_text),
        chunks_verified=len(chunks),
        claims_checked=result.total_claims_checked,
        claims_correct=result.claims_correct,
        claims_incorrect=result.claims_incorrect,
        claims_unverifiable=result.claims_unverifiable,
        accuracy_rate=result.factual_accuracy_rate,
        corrections=len(result.corrections_needed),
    )
    return (result, total_in, total_out)
