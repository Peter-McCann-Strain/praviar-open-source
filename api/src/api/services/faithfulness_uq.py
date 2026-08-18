"""Faithfulness-Aware Uncertainty Quantification (T3-02) — shadow signal.

# -----------------------------------------------------------------------------
# Paper citation
# -----------------------------------------------------------------------------
# Vashurin, Fadeeva et al., "Faithfulness-Aware Uncertainty Quantification for
# Fact-Checking the Output of Retrieval Augmented Generation".
# arXiv:2505.21072 (May 2025). https://arxiv.org/abs/2505.21072
#
# Feasibility verdict on this codebase: VIABLE WITH ADAPTATION
# (.claude/literature-findings.md finding #7).
#
# Claimed gain (paper): improved precision in detecting hallucinated claims
# vs. retrieved evidence on QA-style RAG benchmarks (NQ, TriviaQA, BioASQ).
# Per-claim entailment against the cited span lets the reviewer queue
# prioritise the "most likely to be wrong" sentences first.
#
# Deterministic smoke coverage: ``bench/faithfulness_uq_benchmark.py`` uses
# programmed synthetic responses to exercise wiring. It is not empirical
# performance evidence. Real correlation with reviewer overrides cannot be
# measured until a labelled FTO decision corpus is built (see plan item T3-03).
#
# Feasibility caveats (per critic):
#   1. Paper numbers are on short QA passages. Patent claim spans are long
#      and nested; entailment accuracy may degrade on dense legal prose.
#   2. Per-report cost scales as O(cited spans). A typical FTO report has
#      10 to 30 cited spans per element, so this runs asynchronously and
#      strictly out of the request path.
#   3. Score must not order the reviewer queue until correlation with
#      reviewer-override events has been measured. Shadow mode only.
#
# Feature flag: ``PRAVIAR_FAITHFULNESS_UQ_ENABLED`` (env var). When unset or
# false, none of the code in this module runs.
# -----------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger()

# Model identifier for the shadow NLI pass. Kept as a module constant so test
# code, benchmark and DB rows agree on a single value.
FAITHFULNESS_MODEL_ID = "claude-haiku-4-5-20251001"

# Maximum character lengths for the prompt body. Patent prose can be very long;
# these caps protect against runaway tokens while preserving the load-bearing
# context. Numbers are conservative defaults; widen only if the paper-faithful
# precision regresses on real workloads.
MAX_CLAIM_CHARS = 2000
MAX_EVIDENCE_CHARS = 4000

VERDICT_LABELS = ("ENTAILED", "NEUTRAL", "CONTRADICTS")

_TRUE_VALUES = {"1", "true", "yes", "on"}


def is_feature_enabled() -> bool:
    """Return True when ``PRAVIAR_FAITHFULNESS_UQ_ENABLED`` is set truthily.

    All entry points must guard with this function. With the env var unset or
    falsey, none of the new behaviour runs and existing analyses are unaffected.
    """
    return os.environ.get("PRAVIAR_FAITHFULNESS_UQ_ENABLED", "").strip().lower() in _TRUE_VALUES


@dataclass(frozen=True)
class EvidencePair:
    """One (claim sentence, evidence span) pair sourced from report_data."""

    finding_index: int
    evidence_index: int
    claim_sentence: str
    evidence_span: str


@dataclass(frozen=True)
class FaithfulnessVerdict:
    """Structured NLI result returned by ``score_pair``."""

    verdict: str  # one of VERDICT_LABELS
    confidence: float  # 0.0 to 1.0
    model_id: str
    raw: str = ""


def _truncate(value: str | None, limit: int) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) <= limit:
        return text
    # Keep the head, which usually carries the load-bearing claim language.
    return text[: limit - 1] + "…"


def _normalise_verdict(value: object) -> str:
    text = str(value or "").strip().upper()
    if text in VERDICT_LABELS:
        return text
    if text in {"ENTAIL", "ENTAILS", "SUPPORTED", "YES"}:
        return "ENTAILED"
    if text in {"CONTRADICT", "CONTRADICTED", "NO", "UNSUPPORTED"}:
        return "CONTRADICTS"
    return "NEUTRAL"


def _normalise_confidence(value: object) -> float:
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(result):
        return 0.0
    if result < 0.0:
        return 0.0
    if result > 1.0:
        # Some models report 0 to 100; rescale defensively rather than fail.
        if result <= 100.0:
            return result / 100.0
        return 1.0
    return result


def _build_prompt(claim_sentence: str, evidence_span: str) -> str:
    """Return the user-message body for the NLI entailment check."""
    claim = _truncate(claim_sentence, MAX_CLAIM_CHARS)
    evidence = _truncate(evidence_span, MAX_EVIDENCE_CHARS)
    return (
        "You are a Natural Language Inference (NLI) classifier specialised for "
        "patent claim text and FTO analysis sentences. For the (CLAIM, EVIDENCE) "
        "pair below, decide whether the EVIDENCE supports the CLAIM.\n\n"
        "Output exactly one JSON object on a single line with the following keys:\n"
        '  "verdict": one of "ENTAILED", "NEUTRAL", "CONTRADICTS".\n'
        '  "confidence": a float between 0.0 and 1.0 describing your certainty.\n\n'
        "Definitions:\n"
        "  ENTAILED   - the EVIDENCE clearly supports the CLAIM.\n"
        "  NEUTRAL    - the EVIDENCE is related but neither supports nor refutes.\n"
        "  CONTRADICTS - the EVIDENCE directly refutes the CLAIM.\n\n"
        f"CLAIM:\n{claim}\n\nEVIDENCE:\n{evidence}\n\n"
        "Return only the JSON object; no prose, no markdown."
    )


def _parse_response(text: str) -> tuple[str, float, str]:
    """Extract (verdict, confidence, raw) from an Anthropic text response."""
    raw = (text or "").strip()
    # Strip code fences and stray prose around the JSON.
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].lstrip()
    # If the model wrapped the JSON in prose, find the first '{' to the last '}'.
    start = raw.find("{")
    end = raw.rfind("}")
    candidate = raw[start : end + 1] if start >= 0 and end > start else raw
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return "NEUTRAL", 0.0, raw
    return (
        _normalise_verdict(data.get("verdict")),
        _normalise_confidence(data.get("confidence")),
        raw,
    )


def score_pair(
    *,
    claim_sentence: str,
    evidence_span: str,
    client: Any,
    model_id: str = FAITHFULNESS_MODEL_ID,
    max_tokens: int = 200,
) -> FaithfulnessVerdict:
    """Score one (claim, evidence) pair using a Claude Haiku NLI prompt.

    ``client`` is an ``anthropic.Anthropic`` instance (or any object exposing
    ``messages.create`` with the same shape). The function is synchronous because
    the caller is a Celery worker; the Anthropic SDK is happy in either mode.

    Errors are caught and returned as a NEUTRAL verdict with confidence 0.0 so
    that one bad pair never aborts a whole shadow-mode pass.
    """
    prompt = _build_prompt(claim_sentence, evidence_span)
    try:
        response = client.messages.create(
            model=model_id,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # noqa: BLE001 - shadow mode swallows errors
        logger.warning(
            "faithfulness_uq_call_failed",
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return FaithfulnessVerdict(verdict="NEUTRAL", confidence=0.0, model_id=model_id, raw="")

    # Anthropic SDK returns content blocks; collect any text.
    text_parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        block_text = getattr(block, "text", None)
        if block_text:
            text_parts.append(block_text)
    raw_text = "\n".join(text_parts)
    verdict, confidence, raw = _parse_response(raw_text)
    return FaithfulnessVerdict(verdict=verdict, confidence=confidence, model_id=model_id, raw=raw)


def iter_evidence_pairs(report_data: dict | None) -> Iterable[EvidencePair]:
    """Yield ``EvidencePair`` rows from a Praviar report_data structure.

    The report's findings live under ``patent_analyses`` and each finding has a
    ``claims_analyzed`` array; per claim, each entry in ``elements`` carries a
    ``reasoning`` or ``element_text`` sentence (the claim) and an ``evidence``
    span (the cited source text). Only pairs with both sides non-empty are
    yielded; empty pairs would produce vacuous NLI calls.

    ``finding_index`` corresponds to the position in ``patent_analyses``.
    ``evidence_index`` is the flat index of the (claim, element) pair within
    that finding, counted across all ``claims_analyzed`` items.
    """
    if not isinstance(report_data, dict):
        return
    patent_analyses = report_data.get("patent_analyses") or []
    for f_idx, finding in enumerate(patent_analyses):
        if not isinstance(finding, dict):
            continue
        evidence_index = 0
        for claim in finding.get("claims_analyzed", []) or []:
            if not isinstance(claim, dict):
                continue
            for element in claim.get("elements", []) or []:
                if not isinstance(element, dict):
                    continue
                claim_sentence = (
                    element.get("reasoning") or element.get("element_text") or ""
                ).strip()
                evidence_span = (element.get("evidence") or "").strip()
                if claim_sentence and evidence_span:
                    yield EvidencePair(
                        finding_index=f_idx,
                        evidence_index=evidence_index,
                        claim_sentence=claim_sentence,
                        evidence_span=evidence_span,
                    )
                evidence_index += 1


def score_report(
    *,
    report_data: dict | None,
    client: Any,
    model_id: str = FAITHFULNESS_MODEL_ID,
    max_pairs: int | None = None,
) -> list[tuple[EvidencePair, FaithfulnessVerdict]]:
    """Score every (claim, evidence) pair extracted from ``report_data``.

    ``max_pairs`` caps the number of pairs scored per analysis. Without a cap, a
    pathological report could trigger hundreds of model calls; the cap protects
    the worker without changing semantics (any unscored pair simply does not get
    a row in ``faithfulness_scores`` for this run).
    """
    results: list[tuple[EvidencePair, FaithfulnessVerdict]] = []
    pairs = list(iter_evidence_pairs(report_data))
    if max_pairs is not None and max_pairs >= 0:
        pairs = pairs[:max_pairs]
    for pair in pairs:
        verdict = score_pair(
            claim_sentence=pair.claim_sentence,
            evidence_span=pair.evidence_span,
            client=client,
            model_id=model_id,
        )
        results.append((pair, verdict))
    return results
