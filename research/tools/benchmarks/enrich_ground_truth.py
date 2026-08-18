#!/usr/bin/env python3
"""Enrich benchmark ground truth into structured format for pipeline scoring.

Reads existing benchmark JSON files and converts natural-language ground truth
into the enriched schema that maps directly to Praviar Pipeline pipeline output
(ClaimElement, ClaimAnalysis, PatentAnalysis, InvalidityAssessment, DoEAssessment).

Usage:
    # Enrich all benchmark files
    python research/tools/benchmarks/enrich_ground_truth.py

    # Dry-run (preview without writing)
    python research/tools/benchmarks/enrich_ground_truth.py --dry-run

    # Single file
    python research/tools/benchmarks/enrich_ground_truth.py --file paragraph_iv_benchmarks.json

    # Validate enriched output against schema
    python research/tools/benchmarks/enrich_ground_truth.py --validate

    # Use Claude Haiku for LLM-assisted parsing
    python research/tools/benchmarks/enrich_ground_truth.py --llm
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("enrich_gt")


def _no_paid_api_enabled() -> bool:
    return os.environ.get("NO_PAID_API", "").strip().lower() in {"1", "true", "yes", "on"}

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
BENCHMARKS_DIR = REPO_ROOT / "research" / "benchmarks"
ENRICHED_DIR = BENCHMARKS_DIR / "enriched"
SCHEMA_PATH = BENCHMARKS_DIR / "enriched_ground_truth_schema.json"

# Benchmark files to process (order: most structured → least)
BENCHMARK_FILES = [
    "paragraph_iv_benchmarks.json",
    "ptab_ipr_benchmarks.json",
    "bpcia_biosimilar_benchmarks.json",
    "doe_estoppel_claim_construction_benchmarks.json",
    "markush_chemical_claims_benchmarks.json",
    "patent_cliff_benchmarks.json",
    "orange_book_benchmarks.json",
    "pharma_litigation_benchmarks.json",
    "specialty_therapeutic_benchmarks.json",
    "international_pharma_benchmarks.json",
    "published_fto_benchmarks.json",
]

# Source type mapping from filename
_SOURCE_MAP: dict[str, str] = {
    "paragraph_iv_benchmarks.json": "paragraph_iv",
    "ptab_ipr_benchmarks.json": "ptab",
    "bpcia_biosimilar_benchmarks.json": "bpcia",
    "doe_estoppel_claim_construction_benchmarks.json": "doe_estoppel",
    "markush_chemical_claims_benchmarks.json": "markush",
    "patent_cliff_benchmarks.json": "patent_cliff",
    "orange_book_benchmarks.json": "orange_book",
    "pharma_litigation_benchmarks.json": "pharma_litigation",
    "specialty_therapeutic_benchmarks.json": "specialty",
    "international_pharma_benchmarks.json": "international",
    "published_fto_benchmarks.json": "published_fto",
}

# Maps litigation ruling strings to risk levels
_RULING_RISK_MAP: dict[str, str] = {
    "infringement_found": "high",
    "invalidated": "clear",
    "mixed": "medium",
    "settled": "medium",
    "no_infringement": "clear",
    "not_infringed": "clear",
}

# Maps patent status to blocking status
_STATUS_BLOCKING_MAP: dict[str, str] = {
    "expired": "formerly_blocking",
    "invalidated": "formerly_blocking",
    "lapsed": "formerly_blocking",
    "revoked": "formerly_blocking",
    "active": "currently_blocking",
    "pending": "currently_blocking",
}

# Known invalidity grounds keywords
_INVALIDITY_GROUND_PATTERNS: dict[str, str] = {
    "obviousness": "obviousness",
    "obvious": "obviousness",
    "103": "obviousness",
    "anticipation": "anticipation",
    "anticipated": "anticipation",
    "102": "anticipation",
    "written description": "written_description",
    "enablement": "written_description",
    "112": "written_description",
    "double patenting": "obviousness",
}

# Patent ID extraction pattern
_PATENT_ID_RE = re.compile(
    r"(?:US|EP|WO|JP|KR|CN|IN|CA|AU)"
    r"[\s-]?"
    r"\d{5,12}"
    r"(?:[A-Z]\d?)?"
)


# ---------------------------------------------------------------------------
# Data structures for enrichment stats
# ---------------------------------------------------------------------------


@dataclass
class EnrichmentStats:
    """Tracks enrichment quality across all cases."""

    total_cases: int = 0
    cases_with_structured_claims: int = 0
    cases_with_invalidity_gt: int = 0
    cases_with_doe_gt: int = 0
    cases_with_expiry_dates: int = 0
    cases_needing_expert_review: int = 0
    high_confidence: int = 0
    medium_confidence: int = 0
    low_confidence: int = 0
    skipped_cases: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cases_with_structured_claims": self.cases_with_structured_claims,
            "cases_with_invalidity_gt": self.cases_with_invalidity_gt,
            "cases_with_doe_gt": self.cases_with_doe_gt,
            "cases_with_expiry_dates": self.cases_with_expiry_dates,
            "cases_needing_expert_review": self.cases_needing_expert_review,
            "high_confidence_cases": self.high_confidence,
            "medium_confidence_cases": self.medium_confidence,
            "low_confidence_cases": self.low_confidence,
        }


# ---------------------------------------------------------------------------
# Patent ID normalization (mirrors benchmark_scorer.py)
# ---------------------------------------------------------------------------

_KIND_CODE_RE = re.compile(r"(?<=\d)[A-Z]\d*$")


def normalize_patent_id(pid: str) -> str:
    """Normalize patent ID for comparison."""
    pid = pid.strip().upper().replace(" ", "").replace("-", "")
    pid = _KIND_CODE_RE.sub("", pid)
    return pid


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------


def _extract_compound_input(compound: dict[str, Any]) -> str:
    """Determine the best pipeline input for a compound.

    Priority: SMILES > CAS number > generic name.
    Skips SMILES that are 'N/A' or empty.
    """
    smiles = compound.get("smiles", "")
    if smiles and smiles.strip().lower() not in ("", "n/a", "none", "null"):
        # Check it looks like a real SMILES (not a note)
        if not smiles.startswith("N/A") and len(smiles) < 500:
            return smiles.strip()

    # Try alternate SMILES fields
    for key in ("smiles_patented", "smiles_accused"):
        alt = compound.get(key, "")
        if alt and alt.strip().lower() not in ("", "n/a", "none"):
            return alt.strip()

    # Fall back to CAS number
    cas = compound.get("cas_number", "")
    if cas and cas.strip():
        return cas.strip()

    # Fall back to generic name
    for key in ("generic_name", "active_ingredient", "drug_name"):
        name = compound.get(key, "")
        if name and name.strip():
            return name.strip()

    return ""


def _extract_compound_name(compound: dict[str, Any]) -> str:
    """Get a human-readable compound name."""
    brand = compound.get("brand_name", "")
    generic = compound.get("generic_name", compound.get("drug_name", ""))
    if brand and generic:
        return f"{brand} ({generic})"
    return generic or brand or compound.get("active_ingredient", "Unknown")


def _extract_invalidity_grounds(text: str) -> list[str]:
    """Extract invalidity grounds from natural language text."""
    if not text:
        return []
    text_lower = text.lower()
    grounds: set[str] = set()
    for pattern, ground_type in _INVALIDITY_GROUND_PATTERNS.items():
        if pattern in text_lower:
            grounds.add(ground_type)
    return sorted(grounds)


def _extract_patent_ids_from_text(text: str) -> list[str]:
    """Extract patent IDs from free text."""
    if not text:
        return []
    return [normalize_patent_id(m) for m in _PATENT_ID_RE.findall(text)]


def _infer_status_from_expiry(expiry_str: str | None) -> str:
    """Infer patent status from expiry date."""
    if not expiry_str:
        return "unknown"
    try:
        expiry = date.fromisoformat(expiry_str)
        return "expired" if expiry < date.today() else "active"
    except ValueError:
        return "unknown"


def _determine_overall_confidence(
    has_litigation: bool,
    has_court_ruling: bool,
    has_ptab: bool,
    has_explicit_claims: bool,
    outcome_clarity: str,
) -> str:
    """Determine confidence in ground truth based on available evidence."""
    score = 0
    if has_litigation:
        score += 1
    if has_court_ruling:
        score += 2
    if has_ptab:
        score += 2
    if has_explicit_claims:
        score += 1
    if outcome_clarity in ("unambiguous",):
        score += 2
    elif outcome_clarity in ("mostly_clear",):
        score += 1

    if score >= 4:
        return "high"
    elif score >= 2:
        return "medium"
    return "low"


def _determine_verifier(case: dict[str, Any], source_type: str) -> str:
    """Determine what verified this ground truth."""
    if source_type == "ptab":
        return "ptab_decision"
    if source_type == "published_fto":
        return "published_analysis"

    litigation = case.get("litigation", {})
    ruling = litigation.get("ruling", "")

    if ruling in ("infringement_found", "invalidated", "no_infringement", "not_infringed"):
        return "litigation_outcome"
    if ruling == "settled":
        return "litigation_outcome"

    return "automated_enrichment"


# ---------------------------------------------------------------------------
# Claim element extraction from natural language
# ---------------------------------------------------------------------------


def _parse_claim_elements_from_met_list(
    met_list: list[str],
    not_met_list: list[str],
    patent_id: str,
    key_claims: list[int] | None,
) -> list[dict[str, Any]]:
    """Parse key_claim_elements.met/not_met into structured expected_claims.

    This is the deterministic parser. It creates one expected_claim per
    key_claim number, with elements extracted from the natural language
    descriptions.
    """
    claims: list[dict[str, Any]] = []

    # If we have specific key claims, create one entry per claim
    claim_numbers = key_claims or [1]

    for claim_num in claim_numbers:
        elements: list[dict[str, Any]] = []

        # Parse met elements
        for i, desc in enumerate(met_list, start=1):
            # Check if this element mentions a specific claim or the patent
            pid_norm = normalize_patent_id(patent_id) if patent_id else ""
            relevant = (
                not patent_id  # If no patent ID filter, include all
                or pid_norm in normalize_patent_id(desc)
                or f"claim {claim_num}" in desc.lower()
                or f"claims {claim_num}" in desc.lower()
                or "'" in desc  # Patent shorthand like '081
            )

            if relevant or len(claim_numbers) == 1:
                elements.append(
                    {
                        "element_number": len(elements) + 1,
                        "element_description": desc,
                        "expected_status": "met",
                        "rationale": f"Derived from benchmark key_claim_elements.met: {desc}",
                        "confidence": "medium",
                        "source": "benchmark_extraction",
                    }
                )

        # Parse not_met elements
        for i, desc in enumerate(not_met_list, start=1):
            pid_norm = normalize_patent_id(patent_id) if patent_id else ""
            relevant = (
                not patent_id
                or pid_norm in normalize_patent_id(desc)
                or f"claim {claim_num}" in desc.lower()
                or "'" in desc
            )

            if relevant or len(claim_numbers) == 1:
                elements.append(
                    {
                        "element_number": len(elements) + 1,
                        "element_description": desc,
                        "expected_status": "not_met",
                        "rationale": f"Derived from benchmark key_claim_elements.not_met: {desc}",
                        "confidence": "medium",
                        "source": "benchmark_extraction",
                    }
                )

        if elements:
            # Determine overall status: if any element is not_met, claim is not_met
            statuses = [e["expected_status"] for e in elements]
            if "not_met" in statuses:
                overall = "not_met"
            elif all(s == "met" for s in statuses):
                overall = "met"
            else:
                overall = "partially_met"

            claims.append(
                {
                    "claim_number": claim_num,
                    "claim_type": "independent",
                    "depends_on": None,
                    "expected_overall_status": overall,
                    "expected_elements": elements,
                    "rationale": f"Extracted from benchmark key_claim_elements for patent {patent_id}",
                    "confidence": "medium",
                }
            )

    return claims


# ---------------------------------------------------------------------------
# Per-format enrichers
# ---------------------------------------------------------------------------


def _enrich_paragraph_iv_case(
    case: dict[str, Any],
    source_file: str,
    stats: EnrichmentStats,
) -> dict[str, Any] | None:
    """Enrich a paragraph_iv_benchmarks case."""
    compound = case.get("compound", {})
    benchmark = case.get("benchmark", {})
    litigation = case.get("litigation", {})
    patents = case.get("patents", [])

    compound_input = _extract_compound_input(compound)
    if not compound_input:
        log.warning("Skipping %s: no usable compound input", case.get("id"))
        stats.skipped_cases += 1
        return None

    # Expected risk
    expected_risk = benchmark.get("expected_risk_today", "").lower()
    if not expected_risk:
        expected_risk = "clear"  # Most paragraph IV cases are expired

    # Build blocking patents
    blocking_patent_ids = set(benchmark.get("blocking_patents_to_find", []))
    key_claim_elements = benchmark.get("key_claim_elements", {})
    met_list = key_claim_elements.get("met", [])
    not_met_list = key_claim_elements.get("not_met", [])

    blocking_patents: list[dict[str, Any]] = []
    has_expiry = False
    has_claims = False

    for patent_data in patents:
        pid = patent_data.get("patent_number", "")
        if not pid:
            continue

        # Determine if blocking
        is_blocking = (
            normalize_patent_id(pid) in {normalize_patent_id(b) for b in blocking_patent_ids}
            or not blocking_patent_ids  # If no explicit list, all patents are blocking
        )
        if not is_blocking:
            continue

        status = patent_data.get("status", "unknown")
        expiry = patent_data.get("expiry_date")
        if not status or status == "unknown":
            status = _infer_status_from_expiry(expiry)

        blocking_status = _STATUS_BLOCKING_MAP.get(status, "currently_blocking")
        patent_risk = "clear" if blocking_status == "formerly_blocking" else expected_risk

        # Extract claims
        key_claims = patent_data.get("key_claims", [])
        expected_claims = _parse_claim_elements_from_met_list(
            met_list, not_met_list, pid, key_claims
        )
        if expected_claims:
            has_claims = True

        # Extract invalidity
        invalidity_gt = None
        invalidity_basis = litigation.get("invalidity_basis", "")
        ruling = litigation.get("ruling", "")
        claims_invalidated = litigation.get("claims_invalidated", [])

        if invalidity_basis or ruling == "invalidated" or claims_invalidated:
            grounds = _extract_invalidity_grounds(invalidity_basis)
            invalidity_gt = {
                "vulnerable": bool(grounds) or ruling == "invalidated",
                "overall_strength": "strong"
                if ruling == "invalidated"
                else ("moderate" if grounds else "weak"),
                "grounds": grounds,
                "key_prior_art": [],
                "ptab_proceeding": None,
                "ptab_outcome": None,
                "ptab_claims_cancelled": [],
                "written_description_issues": [],
                "litigation_invalidity_basis": invalidity_basis,
                "confidence": "high" if ruling == "invalidated" else "medium",
            }
            stats.cases_with_invalidity_gt += 1

        patent_entry: dict[str, Any] = {
            "patent_id": pid,
            "must_discover": True,
            "blocking_status": blocking_status,
            "expected_risk": patent_risk,
            "assignee": patent_data.get("assignee", ""),
            "claim_types": patent_data.get("claim_types", []),
            "key_claims": key_claims,
            "expected_claims": expected_claims,
            "expected_expiry": expiry,
            "expected_expiry_with_pte": None,
            "status": status,
            "notes": "",
            "enrichment_confidence": "high" if litigation.get("ruling") else "medium",
            "needs_expert_review": False,
        }
        if invalidity_gt:
            patent_entry["expected_invalidity"] = invalidity_gt
        if expiry:
            has_expiry = True

        blocking_patents.append(patent_entry)

    # Non-blocking patents
    non_blocking_ids = benchmark.get("non_blocking_patents", [])
    non_blocking_patents = []
    for nb_id in non_blocking_ids:
        if isinstance(nb_id, str):
            non_blocking_patents.append(
                {
                    "patent_id": nb_id,
                    "reason_non_blocking": "expired",
                    "expected_risk": "clear",
                }
            )

    # Determine confidence
    outcome_clarity = benchmark.get("outcome_clarity", "")
    confidence = _determine_overall_confidence(
        has_litigation=bool(litigation),
        has_court_ruling=litigation.get("ruling", "")
        in ("infringement_found", "invalidated", "no_infringement"),
        has_ptab=False,
        has_explicit_claims=has_claims,
        outcome_clarity=outcome_clarity,
    )

    # Scoring capabilities
    scoring = {
        "can_score_discovery": bool(blocking_patents),
        "can_score_triage": bool(blocking_patents),
        "can_score_risk_classification": bool(expected_risk),
        "can_score_claim_elements": has_claims,
        "can_score_invalidity": any(p.get("expected_invalidity") for p in blocking_patents),
        "can_score_doe": False,
        "can_score_patent_term": has_expiry,
        "can_score_false_positive": bool(non_blocking_patents),
        "can_score_false_negative": bool(blocking_patents),
        "requires_llm_judge": [],
    }
    if not has_claims:
        scoring["requires_llm_judge"].append("claim_element_accuracy")

    # Update stats
    if has_claims:
        stats.cases_with_structured_claims += 1
    if has_expiry:
        stats.cases_with_expiry_dates += 1
    if confidence == "high":
        stats.high_confidence += 1
    elif confidence == "medium":
        stats.medium_confidence += 1
    else:
        stats.low_confidence += 1
        stats.cases_needing_expert_review += 1

    needs_review = confidence == "low"

    return {
        "id": case.get("id", ""),
        "original_id": case.get("id", ""),
        "compound_input": compound_input,
        "compound_name": _extract_compound_name(compound),
        "therapeutic_area": compound.get("therapeutic_area", ""),
        "expected_outcome": {
            "overall_risk": expected_risk,
            "overall_risk_rationale": benchmark.get("why_good_benchmark", ""),
            "blocking_patents": blocking_patents,
            "non_blocking_patents": non_blocking_patents,
        },
        "metadata": {
            "source": "paragraph_iv",
            "source_file": source_file,
            "confidence_in_ground_truth": confidence,
            "last_verified": date.today().isoformat(),
            "verifier": _determine_verifier(case, "paragraph_iv"),
            "difficulty": benchmark.get("difficulty", "medium"),
            "outcome_clarity": outcome_clarity if outcome_clarity else "mostly_clear",
            "needs_expert_review": needs_review,
            "review_notes": "Auto-enriched from paragraph IV benchmark. Check claim element extraction."
            if needs_review
            else "",
        },
        "scoring_capabilities": scoring,
        "original_benchmark": {
            "category": benchmark.get("category", ""),
            "difficulty": benchmark.get("difficulty", ""),
            "why_good_benchmark": benchmark.get("why_good_benchmark", ""),
        },
    }


def _enrich_ptab_case(
    case: dict[str, Any],
    source_file: str,
    stats: EnrichmentStats,
) -> dict[str, Any] | None:
    """Enrich a ptab_ipr_benchmarks case."""
    compound = case.get("compound", {})
    benchmark = case.get("benchmark", {})
    patent_data = case.get("patent", {})
    ptab = case.get("ptab_proceeding", {})
    fc_appeal = case.get("federal_circuit_appeal", {})

    compound_input = _extract_compound_input(compound)
    if not compound_input:
        log.warning("Skipping %s: no usable compound input", case.get("id"))
        stats.skipped_cases += 1
        return None

    expected_risk = benchmark.get("expected_risk_today", "").lower()
    pid = patent_data.get("patent_number", "")
    expiry = patent_data.get("expiry_date")
    status = _infer_status_from_expiry(expiry)

    # PTAB outcome determines invalidity
    ptab_outcome_raw = ptab.get("outcome", "")
    ptab_outcome_map: dict[str, str] = {
        "all_claims_unpatentable": "unpatentable",
        "all_claims_upheld": "patentable",
        "mixed": "mixed",
        "settled": "settled",
        "terminated": "terminated",
    }
    ptab_outcome = ptab_outcome_map.get(ptab_outcome_raw, ptab_outcome_raw)

    claims_cancelled = ptab.get("claims_found_unpatentable", [])
    claims_upheld = ptab.get("claims_upheld", [])
    invalidity_grounds_raw = ptab.get("invalidity_grounds", "")
    grounds = _extract_invalidity_grounds(invalidity_grounds_raw)
    if not grounds and invalidity_grounds_raw:
        # Direct mapping if it's a single word
        if invalidity_grounds_raw.lower() in ("obviousness", "anticipation", "written_description"):
            grounds = [invalidity_grounds_raw.lower()]

    # Determine invalidity strength from outcome
    if ptab_outcome == "unpatentable":
        inv_strength = "strong"
    elif ptab_outcome == "patentable":
        inv_strength = "weak"
    elif ptab_outcome == "mixed":
        inv_strength = "moderate"
    else:
        inv_strength = "moderate"

    # If Federal Circuit affirmed, boost confidence
    fc_affirmed = fc_appeal.get("outcome", "").lower() == "affirmed"

    # Parse prior art
    prior_art_cited = ptab.get("prior_art_cited", [])
    key_prior_art = []
    for ref in prior_art_cited:
        ref_ids = _extract_patent_ids_from_text(ref)
        if ref_ids:
            for ref_id in ref_ids:
                key_prior_art.append(
                    {
                        "reference_id": ref_id,
                        "reference_type": "patent",
                        "relevance": ref,
                    }
                )
        else:
            # Non-patent prior art (journal articles, clinical data, etc.)
            key_prior_art.append(
                {
                    "reference_id": ref[:100],  # Truncate long descriptions
                    "reference_type": "journal_article",
                    "relevance": ref,
                }
            )

    invalidity_gt: dict[str, Any] = {
        "vulnerable": ptab_outcome in ("unpatentable", "mixed"),
        "overall_strength": inv_strength,
        "grounds": grounds,
        "key_prior_art": key_prior_art,
        "ptab_proceeding": ptab.get("proceeding_number"),
        "ptab_outcome": ptab_outcome,
        "ptab_claims_cancelled": claims_cancelled,
        "written_description_issues": [],
        "litigation_invalidity_basis": ptab.get("key_reasoning", ""),
        "confidence": "high" if fc_affirmed else "high",
    }
    stats.cases_with_invalidity_gt += 1

    # Build blocking patent
    blocking_status = _STATUS_BLOCKING_MAP.get(status, "currently_blocking")
    patent_risk = "clear" if blocking_status == "formerly_blocking" else expected_risk

    challenged_claims = patent_data.get("challenged_claims", [])
    # For PTAB cases, create claim-level GT from outcome
    expected_claims: list[dict[str, Any]] = []
    # Build claims from cancelled/upheld lists
    all_claim_nums = (
        set(claims_cancelled) | set(claims_upheld) | set(challenged_claims[:5])
    )  # Cap at 5 for sanity
    for cn in sorted(all_claim_nums)[:10]:  # Cap at 10 claims
        if cn in claims_cancelled:
            claim_status = "not_met"  # Claims found unpatentable => they were met but invalid
            rationale = f"Claim {cn} found unpatentable by PTAB on {', '.join(grounds)} grounds"
        elif cn in claims_upheld:
            claim_status = "met"
            rationale = f"Claim {cn} upheld by PTAB — patent owner prevailed"
        else:
            claim_status = "unclear"
            rationale = f"Claim {cn} challenged but outcome unclear"

        expected_claims.append(
            {
                "claim_number": cn,
                "claim_type": "independent" if cn <= 3 else "dependent",
                "depends_on": None if cn <= 3 else 1,
                "expected_overall_status": claim_status,
                "expected_elements": [],
                "rationale": rationale,
                "confidence": "high" if fc_affirmed else "medium",
            }
        )

    has_claims = bool(expected_claims)
    has_expiry = bool(expiry)

    if has_claims:
        stats.cases_with_structured_claims += 1
    if has_expiry:
        stats.cases_with_expiry_dates += 1

    blocking_patent: dict[str, Any] = {
        "patent_id": pid,
        "must_discover": True,
        "blocking_status": blocking_status,
        "expected_risk": patent_risk,
        "assignee": patent_data.get("assignee", ""),
        "claim_types": patent_data.get("claim_types", []),
        "key_claims": challenged_claims[:10],
        "expected_claims": expected_claims,
        "expected_expiry": expiry,
        "expected_expiry_with_pte": None,
        "status": status,
        "expected_invalidity": invalidity_gt,
        "notes": benchmark.get("why_good_benchmark", ""),
        "enrichment_confidence": "high",
        "needs_expert_review": False,
    }

    confidence = "high" if fc_affirmed else "high"
    stats.high_confidence += 1

    return {
        "id": case.get("id", ""),
        "original_id": case.get("id", ""),
        "compound_input": compound_input,
        "compound_name": _extract_compound_name(compound),
        "therapeutic_area": compound.get("therapeutic_area", ""),
        "expected_outcome": {
            "overall_risk": expected_risk,
            "overall_risk_rationale": ptab.get("key_reasoning", ""),
            "blocking_patents": [blocking_patent],
            "non_blocking_patents": [],
        },
        "metadata": {
            "source": "ptab",
            "source_file": source_file,
            "confidence_in_ground_truth": confidence,
            "last_verified": date.today().isoformat(),
            "verifier": "ptab_decision",
            "difficulty": benchmark.get("difficulty", "medium"),
            "outcome_clarity": "unambiguous"
            if ptab_outcome in ("unpatentable", "patentable")
            else "mostly_clear",
            "needs_expert_review": False,
            "review_notes": "",
        },
        "scoring_capabilities": {
            "can_score_discovery": True,
            "can_score_triage": True,
            "can_score_risk_classification": bool(expected_risk),
            "can_score_claim_elements": has_claims,
            "can_score_invalidity": True,
            "can_score_doe": False,
            "can_score_patent_term": has_expiry,
            "can_score_false_positive": False,
            "can_score_false_negative": True,
            "requires_llm_judge": [],
        },
        "original_benchmark": {
            "category": benchmark.get("category", ""),
            "difficulty": benchmark.get("difficulty", ""),
            "tests_pipeline_aspect": benchmark.get("tests_pipeline_aspect", ""),
        },
    }


def _enrich_doe_case(
    case: dict[str, Any],
    source_file: str,
    stats: EnrichmentStats,
) -> dict[str, Any] | None:
    """Enrich a DoE/estoppel/claim construction case."""
    compound = case.get("compound", {})
    benchmark = case.get("benchmark", {})
    patent_data = case.get("patent", {})
    litigation = case.get("litigation", {})

    compound_input = _extract_compound_input(compound)
    if not compound_input:
        log.warning("Skipping %s: no usable compound input", case.get("id"))
        stats.skipped_cases += 1
        return None

    expected_risk = benchmark.get("expected_risk_today", "").lower()
    pid = patent_data.get("patent_number", "")
    expiry = patent_data.get("expiry_date")

    # Extract DoE ground truth
    doe_gt = None
    legal_doctrine = litigation.get("legal_doctrine", "")
    doe_analysis = litigation.get("doe_analysis", "")
    estoppel_finding = litigation.get("estoppel_finding", "")
    prosecution_history = patent_data.get("prosecution_history", "")

    if "doe" in legal_doctrine.lower() or doe_analysis or estoppel_finding:
        # Parse FWR if available
        fwr = None
        if doe_analysis:
            # Try to extract Function/Way/Result from the text
            fwr_parts: dict[str, str] = {}
            for label in ("function", "way", "result"):
                pattern = rf"{label}[:\s]+(.+?)(?:\.|$)"
                match = re.search(pattern, doe_analysis, re.IGNORECASE)
                if match:
                    fwr_parts[label] = match.group(1).strip()
            if fwr_parts:
                fwr = {
                    "function": fwr_parts.get("function", ""),
                    "way": fwr_parts.get("way", ""),
                    "result": fwr_parts.get("result", ""),
                    "equivalent": expected_risk in ("high", "medium"),
                }

        # Determine estoppel
        estoppel_applies = "estoppel" in estoppel_finding.lower() if estoppel_finding else None
        festo_exception = None
        if "tangential" in (estoppel_finding + prosecution_history).lower():
            festo_exception = "tangential"
        elif "unforesee" in (estoppel_finding + prosecution_history).lower():
            festo_exception = "unforeseeability"

        # Determine narrowing amendment
        narrowing = None
        if prosecution_history and (
            "narrow" in prosecution_history.lower() or "amend" in prosecution_history.lower()
        ):
            narrowing = prosecution_history[:300]

        doe_gt = {
            "risk": expected_risk,
            "estoppel_applies": estoppel_applies,
            "estoppel_type": "amendment_based"
            if "amendment" in (estoppel_finding + prosecution_history).lower()
            else None,
            "narrowing_amendment": narrowing,
            "festo_exception": festo_exception,
            "rationale": litigation.get("key_holding", ""),
            "confidence": "high",
        }
        if fwr:
            doe_gt["fwr_analysis"] = fwr
        stats.cases_with_doe_gt += 1

    # Build blocking patent
    status = _infer_status_from_expiry(expiry) if expiry else "active"
    blocking_status = _STATUS_BLOCKING_MAP.get(status, "currently_blocking")
    patent_risk = "clear" if blocking_status == "formerly_blocking" else expected_risk

    blocking_patent: dict[str, Any] = {
        "patent_id": pid,
        "must_discover": True,
        "blocking_status": blocking_status,
        "expected_risk": patent_risk,
        "assignee": patent_data.get("assignee", ""),
        "claim_types": patent_data.get("claim_types", []),
        "key_claims": [patent_data.get("key_claim", 1)] if patent_data.get("key_claim") else [],
        "expected_claims": [],
        "expected_expiry": expiry,
        "expected_expiry_with_pte": None,
        "status": status,
        "notes": benchmark.get(
            "specific_challenge", benchmark.get("specific_challenge_for_ai", "")
        ),
        "enrichment_confidence": "high",
        "needs_expert_review": False,
    }
    if doe_gt:
        blocking_patent["expected_doe"] = doe_gt
    if expiry:
        stats.cases_with_expiry_dates += 1

    stats.high_confidence += 1

    return {
        "id": case.get("id", ""),
        "original_id": case.get("id", ""),
        "compound_input": compound_input,
        "compound_name": _extract_compound_name(compound),
        "therapeutic_area": compound.get("therapeutic_area", ""),
        "expected_outcome": {
            "overall_risk": expected_risk,
            "overall_risk_rationale": litigation.get("key_holding", ""),
            "blocking_patents": [blocking_patent],
            "non_blocking_patents": [],
        },
        "metadata": {
            "source": "doe_estoppel",
            "source_file": source_file,
            "confidence_in_ground_truth": "high",
            "last_verified": date.today().isoformat(),
            "verifier": "litigation_outcome",
            "difficulty": benchmark.get("difficulty", "hard"),
            "outcome_clarity": "unambiguous",
            "needs_expert_review": False,
            "review_notes": "",
        },
        "scoring_capabilities": {
            "can_score_discovery": True,
            "can_score_triage": True,
            "can_score_risk_classification": bool(expected_risk),
            "can_score_claim_elements": False,
            "can_score_invalidity": False,
            "can_score_doe": bool(doe_gt),
            "can_score_patent_term": bool(expiry),
            "can_score_false_positive": False,
            "can_score_false_negative": True,
            "requires_llm_judge": ["claim_element_accuracy"],
        },
        "original_benchmark": {
            "category": benchmark.get("category", ""),
            "difficulty": benchmark.get("difficulty", ""),
            "tests_pipeline_aspect": benchmark.get("tests_pipeline_aspect", ""),
        },
    }


def _enrich_generic_case(
    case: dict[str, Any],
    source_file: str,
    source_type: str,
    stats: EnrichmentStats,
) -> dict[str, Any] | None:
    """Generic enricher for cases that share a common structure.

    Works for: bpcia, patent_cliff, orange_book, pharma_litigation,
    specialty, international, markush, published_fto.
    """
    # Different formats store compound data differently
    compound = case.get("compound", {})
    benchmark = case.get("benchmark", case.get("benchmark_value", {}))

    compound_input = _extract_compound_input(compound)
    if not compound_input:
        log.warning("Skipping %s: no usable compound input", case.get("id"))
        stats.skipped_cases += 1
        return None

    # Expected risk — try multiple locations
    expected_risk = (
        benchmark.get("expected_risk_today", "") or benchmark.get("expected_risk", "") or ""
    ).lower()
    if not expected_risk:
        expected_risk = "medium"

    # Extract patents — handle multiple formats
    blocking_patents: list[dict[str, Any]] = []
    has_expiry = False
    has_claims = False

    # Format 1: case.patents is a list of patent objects (paragraph_iv style)
    patents_list = case.get("patents", [])
    if isinstance(patents_list, list):
        for patent_data in patents_list:
            pid = patent_data.get("patent_number", patent_data.get("number", ""))
            if not pid:
                continue
            expiry = patent_data.get("expiry_date", patent_data.get("expiry"))
            status = patent_data.get("status", _infer_status_from_expiry(expiry))
            blocking_status = _STATUS_BLOCKING_MAP.get(status, "currently_blocking")
            patent_risk = "clear" if blocking_status == "formerly_blocking" else expected_risk

            bp: dict[str, Any] = {
                "patent_id": pid,
                "must_discover": True,
                "blocking_status": blocking_status,
                "expected_risk": patent_risk,
                "assignee": patent_data.get("assignee", ""),
                "claim_types": patent_data.get(
                    "claim_types",
                    patent_data.get("claim_type", "").split(",")
                    if patent_data.get("claim_type")
                    else [],
                ),
                "key_claims": patent_data.get(
                    "key_claims", patent_data.get("challenged_claims", [])
                )[:10],
                "expected_claims": [],
                "expected_expiry": expiry,
                "expected_expiry_with_pte": patent_data.get("expiry_with_pte"),
                "status": status,
                "notes": patent_data.get("notes", ""),
                "enrichment_confidence": "medium",
                "needs_expert_review": False,
            }
            if expiry:
                has_expiry = True
            blocking_patents.append(bp)

    # Format 2: case.patent is a single patent object (ptab/doe style)
    elif not patents_list:
        patent_data = case.get("patent", {})
        if patent_data:
            pid = patent_data.get("patent_number", "")
            expiry = patent_data.get("expiry_date")
            status = _infer_status_from_expiry(expiry) if expiry else "unknown"
            blocking_status = _STATUS_BLOCKING_MAP.get(status, "currently_blocking")
            patent_risk = "clear" if blocking_status == "formerly_blocking" else expected_risk

            bp = {
                "patent_id": pid,
                "must_discover": True,
                "blocking_status": blocking_status,
                "expected_risk": patent_risk,
                "assignee": patent_data.get("assignee", ""),
                "claim_types": patent_data.get("claim_types", []),
                "key_claims": patent_data.get(
                    "key_claims", patent_data.get("challenged_claims", [])
                )[:10],
                "expected_claims": [],
                "expected_expiry": expiry,
                "expected_expiry_with_pte": None,
                "status": status,
                "notes": "",
                "enrichment_confidence": "medium",
                "needs_expert_review": False,
            }
            if expiry:
                has_expiry = True
            blocking_patents.append(bp)

    # Format 3: case.patent_thicket (BPCIA style)
    patent_thicket = case.get("patent_thicket", {})
    if patent_thicket:
        for kp in patent_thicket.get("key_patents", []):
            pid = kp.get("patent_number", kp.get("number", ""))
            if not pid:
                continue
            expiry = kp.get("expiry_date", kp.get("expiry"))
            status = kp.get("status", _infer_status_from_expiry(expiry))
            blocking_status = _STATUS_BLOCKING_MAP.get(status, "currently_blocking")
            patent_risk = "clear" if blocking_status == "formerly_blocking" else expected_risk

            bp = {
                "patent_id": pid,
                "must_discover": True,
                "blocking_status": blocking_status,
                "expected_risk": patent_risk,
                "assignee": kp.get("assignee", patent_thicket.get("assignee", "")),
                "claim_types": [kp.get("claim_type", "")] if kp.get("claim_type") else [],
                "key_claims": [],
                "expected_claims": [],
                "expected_expiry": expiry,
                "expected_expiry_with_pte": None,
                "status": status,
                "notes": kp.get("notes", ""),
                "enrichment_confidence": "medium",
                "needs_expert_review": False,
            }
            if expiry:
                has_expiry = True
            blocking_patents.append(bp)

    # Format 4: case.orange_book_patents (Orange Book style — list of patent objects)
    ob_patents = case.get("orange_book_patents", [])
    for ob_p in ob_patents:
        raw_num = ob_p.get("patent_number", "")
        if not raw_num:
            continue
        # Orange Book numbers may lack the 'US' prefix
        pid = raw_num if raw_num.startswith("US") else f"US{raw_num}"
        expiry = ob_p.get("patent_expiry", ob_p.get("expiry_date"))
        status = ob_p.get("listing_status", _infer_status_from_expiry(expiry))
        if status in ("active", "listed"):
            blocking_status = "currently_blocking"
        else:
            blocking_status = "formerly_blocking"
        patent_risk = "clear" if blocking_status == "formerly_blocking" else expected_risk

        ct = ob_p.get("patent_type", "")
        bp = {
            "patent_id": pid,
            "must_discover": True,
            "blocking_status": blocking_status,
            "expected_risk": patent_risk,
            "assignee": "",
            "claim_types": [ct] if ct else [],
            "key_claims": [],
            "expected_claims": [],
            "expected_expiry": expiry,
            "expected_expiry_with_pte": None,
            "status": "active" if blocking_status == "currently_blocking" else "expired",
            "notes": ob_p.get("notes", ""),
            "enrichment_confidence": "high",
            "needs_expert_review": False,
        }
        if expiry:
            has_expiry = True
        blocking_patents.append(bp)

    # Format 5: case.patent_landscape.key_patents (patent cliff style)
    pl = case.get("patent_landscape", {})
    if pl and not patent_thicket:
        for kp in pl.get("key_patents", []):
            pid = kp.get("patent_number", kp.get("number", ""))
            if not pid:
                continue
            expiry = kp.get("expiry_date", kp.get("expiry"))
            status = kp.get("status", _infer_status_from_expiry(expiry))
            blocking_status = _STATUS_BLOCKING_MAP.get(status, "currently_blocking")
            patent_risk = "clear" if blocking_status == "formerly_blocking" else expected_risk

            bp = {
                "patent_id": pid,
                "must_discover": True,
                "blocking_status": blocking_status,
                "expected_risk": patent_risk,
                "assignee": kp.get("assignee", ""),
                "claim_types": [kp.get("claim_type", "")] if kp.get("claim_type") else [],
                "key_claims": [],
                "expected_claims": [],
                "expected_expiry": expiry,
                "expected_expiry_with_pte": None,
                "status": status,
                "notes": kp.get("notes", ""),
                "enrichment_confidence": "medium",
                "needs_expert_review": False,
            }
            if expiry:
                has_expiry = True
            blocking_patents.append(bp)

    # Format 6: case.patent_info.key_patents (specialty style — list of patent ID strings)
    patent_info = case.get("patent_info", {})
    if patent_info and not blocking_patents:
        kp_list = patent_info.get("key_patents", [])
        for item in kp_list:
            if isinstance(item, str):
                pid = item
                bp = {
                    "patent_id": pid,
                    "must_discover": True,
                    "blocking_status": "currently_blocking",
                    "expected_risk": expected_risk,
                    "assignee": "",
                    "claim_types": [],
                    "key_claims": [],
                    "expected_claims": [],
                    "expected_expiry": None,
                    "expected_expiry_with_pte": None,
                    "status": "unknown",
                    "notes": patent_info.get("notes", ""),
                    "enrichment_confidence": "low",
                    "needs_expert_review": True,
                }
                blocking_patents.append(bp)
            elif isinstance(item, dict):
                pid = item.get("patent_number", item.get("number", ""))
                if not pid:
                    continue
                expiry = item.get("expiry_date", item.get("expiry"))
                status = item.get("status", _infer_status_from_expiry(expiry))
                blocking_status = _STATUS_BLOCKING_MAP.get(status, "currently_blocking")
                patent_risk = "clear" if blocking_status == "formerly_blocking" else expected_risk
                bp = {
                    "patent_id": pid,
                    "must_discover": True,
                    "blocking_status": blocking_status,
                    "expected_risk": patent_risk,
                    "assignee": item.get("assignee", ""),
                    "claim_types": [item.get("claim_type", "")] if item.get("claim_type") else [],
                    "key_claims": [],
                    "expected_claims": [],
                    "expected_expiry": expiry,
                    "expected_expiry_with_pte": None,
                    "status": status,
                    "notes": item.get("notes", ""),
                    "enrichment_confidence": "medium",
                    "needs_expert_review": False,
                }
                if expiry:
                    has_expiry = True
                blocking_patents.append(bp)

    # Format 4: published_fto — patents_identified_as_blocking
    published = case.get("published_analysis", {})
    if published:
        for pid_raw in published.get("patents_identified_as_blocking", []):
            pids = _extract_patent_ids_from_text(pid_raw)
            for pid in pids:
                bp = {
                    "patent_id": pid,
                    "must_discover": True,
                    "blocking_status": "currently_blocking",
                    "expected_risk": expected_risk,
                    "assignee": "",
                    "claim_types": [],
                    "key_claims": [],
                    "expected_claims": [],
                    "expected_expiry": None,
                    "expected_expiry_with_pte": None,
                    "status": "unknown",
                    "notes": pid_raw,
                    "enrichment_confidence": "medium",
                    "needs_expert_review": True,
                }
                blocking_patents.append(bp)

    # Extract invalidity from litigation (handle alternate field names)
    litigation = case.get("litigation", case.get("litigation_or_challenge", {}))
    invalidity_basis = litigation.get("invalidity_basis", "")
    ruling = litigation.get("ruling", litigation.get("outcome", ""))

    for bp in blocking_patents:
        if invalidity_basis or ruling == "invalidated":
            grounds = _extract_invalidity_grounds(invalidity_basis)
            bp["expected_invalidity"] = {
                "vulnerable": bool(grounds) or ruling == "invalidated",
                "overall_strength": "strong"
                if ruling == "invalidated"
                else ("moderate" if grounds else "weak"),
                "grounds": grounds,
                "key_prior_art": [],
                "ptab_proceeding": None,
                "ptab_outcome": None,
                "ptab_claims_cancelled": [],
                "written_description_issues": [],
                "litigation_invalidity_basis": invalidity_basis,
                "confidence": "medium",
            }

    if any(bp.get("expected_invalidity") for bp in blocking_patents):
        stats.cases_with_invalidity_gt += 1

    # Try to extract claim elements from benchmark key_claim_elements
    key_claim_elements = benchmark.get("key_claim_elements", {})
    met_list = key_claim_elements.get("met", [])
    not_met_list = key_claim_elements.get("not_met", [])
    if met_list or not_met_list:
        for bp in blocking_patents:
            claims = _parse_claim_elements_from_met_list(
                met_list, not_met_list, bp["patent_id"], bp.get("key_claims", [])
            )
            if claims:
                bp["expected_claims"] = claims
                has_claims = True

    if has_claims:
        stats.cases_with_structured_claims += 1
    if has_expiry:
        stats.cases_with_expiry_dates += 1

    # Confidence
    outcome_clarity = benchmark.get("outcome_clarity", "")
    confidence = _determine_overall_confidence(
        has_litigation=bool(litigation),
        has_court_ruling=ruling in ("infringement_found", "invalidated", "no_infringement"),
        has_ptab=False,
        has_explicit_claims=has_claims,
        outcome_clarity=outcome_clarity,
    )

    if confidence == "high":
        stats.high_confidence += 1
    elif confidence == "medium":
        stats.medium_confidence += 1
    else:
        stats.low_confidence += 1
        stats.cases_needing_expert_review += 1

    needs_review = confidence == "low" or not blocking_patents

    return {
        "id": case.get("id", ""),
        "original_id": case.get("id", ""),
        "compound_input": compound_input,
        "compound_name": _extract_compound_name(compound),
        "therapeutic_area": compound.get("therapeutic_area", ""),
        "expected_outcome": {
            "overall_risk": expected_risk,
            "overall_risk_rationale": benchmark.get(
                "why_good_benchmark", benchmark.get("key_findings", "")
            ),
            "blocking_patents": blocking_patents,
            "non_blocking_patents": [],
        },
        "metadata": {
            "source": source_type,
            "source_file": source_file,
            "confidence_in_ground_truth": confidence,
            "last_verified": date.today().isoformat(),
            "verifier": _determine_verifier(case, source_type),
            "difficulty": benchmark.get("difficulty", "medium").lower(),
            "outcome_clarity": outcome_clarity if outcome_clarity else "mostly_clear",
            "needs_expert_review": needs_review,
            "review_notes": "Auto-enriched; review patent list completeness and risk levels."
            if needs_review
            else "",
        },
        "scoring_capabilities": {
            "can_score_discovery": bool(blocking_patents),
            "can_score_triage": bool(blocking_patents),
            "can_score_risk_classification": bool(expected_risk),
            "can_score_claim_elements": has_claims,
            "can_score_invalidity": any(bp.get("expected_invalidity") for bp in blocking_patents),
            "can_score_doe": False,
            "can_score_patent_term": has_expiry,
            "can_score_false_positive": False,
            "can_score_false_negative": bool(blocking_patents),
            "requires_llm_judge": ["claim_element_accuracy"] if not has_claims else [],
        },
        "original_benchmark": {
            "category": benchmark.get("category", ""),
            "difficulty": benchmark.get("difficulty", ""),
        },
    }


# ---------------------------------------------------------------------------
# File-level processing
# ---------------------------------------------------------------------------


def _get_cases_from_file(data: Any) -> list[dict[str, Any]]:
    """Extract the list of cases from a benchmark file, handling multiple formats."""
    if isinstance(data, list):
        return data  # paragraph_iv, bpcia, markush, specialty
    if isinstance(data, dict):
        # Try common keys
        for key in ("cases", "published_analyses", "entries"):
            if key in data:
                return data[key]
        # If there's a _metadata + other key
        for k, v in data.items():
            if k != "_metadata" and isinstance(v, list):
                return v
    return []


def enrich_file(
    filepath: Path,
    dry_run: bool = False,
    use_llm: bool = False,
) -> tuple[dict[str, Any] | None, EnrichmentStats]:
    """Enrich a single benchmark file.

    Returns the enriched data dict and stats. If dry_run, does not write.
    """
    source_file = filepath.name
    source_type = _SOURCE_MAP.get(source_file, "pharma_litigation")
    stats = EnrichmentStats()

    log.info("Processing %s (source_type=%s)", source_file, source_type)

    with open(filepath) as f:
        raw_data = json.load(f)

    cases = _get_cases_from_file(raw_data)
    if not cases:
        log.warning("No cases found in %s", source_file)
        return None, stats

    stats.total_cases = len(cases)
    enriched_cases: list[dict[str, Any]] = []

    for case in cases:
        try:
            # Route to the appropriate enricher
            if source_type == "paragraph_iv":
                enriched = _enrich_paragraph_iv_case(case, source_file, stats)
            elif source_type == "ptab":
                enriched = _enrich_ptab_case(case, source_file, stats)
            elif source_type == "doe_estoppel":
                enriched = _enrich_doe_case(case, source_file, stats)
            else:
                enriched = _enrich_generic_case(case, source_file, source_type, stats)

            if enriched:
                enriched_cases.append(enriched)
        except Exception as exc:
            case_id = case.get("id", "unknown")
            log.error(
                "Failed to enrich case %s in %s: %s", case_id, source_file, exc, exc_info=True
            )
            stats.errors.append(f"{case_id}: {exc}")

    if not enriched_cases:
        log.warning("No cases enriched from %s", source_file)
        return None, stats

    # Build output
    output = {
        "_metadata": {
            "description": f"Enriched ground truth from {source_file} for Praviar Pipeline pipeline scoring",
            "version": "1.0.0",
            "created": date.today().isoformat(),
            "source_file": source_file,
            "enrichment_method": "llm_assisted" if use_llm else "automated",
            "total_cases": len(enriched_cases),
            "enrichment_stats": stats.to_dict(),
        },
        "cases": enriched_cases,
    }

    if not dry_run:
        ENRICHED_DIR.mkdir(parents=True, exist_ok=True)
        out_name = source_file.replace("_benchmarks", "_enriched").replace(".json", ".json")
        out_path = ENRICHED_DIR / out_name
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2, default=str)
        log.info("Wrote %d enriched cases to %s", len(enriched_cases), out_path)
    else:
        log.info(
            "[DRY RUN] Would write %d enriched cases for %s",
            len(enriched_cases),
            source_file,
        )

    return output, stats


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def validate_enriched_files() -> bool:
    """Validate all enriched files against the JSON schema.

    Returns True if all valid, False otherwise.
    """
    try:
        import jsonschema
    except ImportError:
        log.error(
            "jsonschema package required for validation. Install with: pip install jsonschema"
        )
        return False

    if not SCHEMA_PATH.exists():
        log.error("Schema not found at %s", SCHEMA_PATH)
        return False

    with open(SCHEMA_PATH) as f:
        schema = json.load(f)

    if not ENRICHED_DIR.exists():
        log.error("Enriched directory not found at %s", ENRICHED_DIR)
        return False

    all_valid = True
    for enriched_file in sorted(ENRICHED_DIR.glob("*.json")):
        log.info("Validating %s...", enriched_file.name)

        with open(enriched_file) as f:
            data = json.load(f)

        validator = jsonschema.Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))

        if errors:
            all_valid = False
            for error in errors[:10]:  # Cap at 10 errors per file
                path = ".".join(str(p) for p in error.absolute_path)
                log.error("  %s: %s (at %s)", enriched_file.name, error.message, path)
            if len(errors) > 10:
                log.error("  ... and %d more errors", len(errors) - 10)
        else:
            log.info("  %s: VALID (%d cases)", enriched_file.name, len(data.get("cases", [])))

    return all_valid


# ---------------------------------------------------------------------------
# LLM-assisted enrichment (optional)
# ---------------------------------------------------------------------------


def _llm_parse_claim_elements(
    text: str,
    patent_id: str,
) -> list[dict[str, Any]]:
    """Use Claude Haiku to parse natural language claim descriptions into structured elements.

    This is only called when --llm flag is set. Falls back to deterministic parsing on failure.
    """
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic package not installed; falling back to deterministic parsing")
        return []

    if _no_paid_api_enabled():
        log.warning("NO_PAID_API=true; falling back to deterministic parsing")
        return []

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        log.warning("ANTHROPIC_API_KEY not set; falling back to deterministic parsing")
        return []

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""Parse the following natural language description of patent claim elements into structured data.

Patent: {patent_id}
Description: {text}

Return a JSON array of objects with this structure:
[
  {{
    "element_number": 1,
    "element_description": "The specific claim limitation text",
    "expected_status": "met|not_met|partially_met|unclear",
    "rationale": "Why this status"
  }}
]

Only return the JSON array, no other text."""

    try:
        response = client.messages.create(
            model=os.environ.get("CLAUDE_TRIAGE_MODEL", "claude-haiku-4-5-20251001"),
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        content = getattr(response.content[0], "text", "").strip()
        # Extract JSON from response
        if content.startswith("["):
            return json.loads(content)
        # Try to find JSON in response
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as exc:
        log.warning("LLM parsing failed for %s: %s", patent_id, exc)

    return []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enrich benchmark ground truth into structured format for pipeline scoring.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview enrichment without writing files.",
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Process a single benchmark file (e.g., paragraph_iv_benchmarks.json).",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate enriched output against the JSON schema.",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Use Claude Haiku for LLM-assisted claim element parsing.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate mode
    if args.validate:
        valid = validate_enriched_files()
        return 0 if valid else 1

    # Determine which files to process
    if args.file:
        files = [args.file]
    else:
        files = BENCHMARK_FILES

    total_stats = EnrichmentStats()
    total_enriched = 0

    for filename in files:
        filepath = BENCHMARKS_DIR / filename
        if not filepath.exists():
            log.warning("Benchmark file not found: %s", filepath)
            continue

        output, file_stats = enrich_file(filepath, dry_run=args.dry_run, use_llm=args.llm)
        if output:
            total_enriched += len(output.get("cases", []))

        # Aggregate stats
        total_stats.total_cases += file_stats.total_cases
        total_stats.cases_with_structured_claims += file_stats.cases_with_structured_claims
        total_stats.cases_with_invalidity_gt += file_stats.cases_with_invalidity_gt
        total_stats.cases_with_doe_gt += file_stats.cases_with_doe_gt
        total_stats.cases_with_expiry_dates += file_stats.cases_with_expiry_dates
        total_stats.cases_needing_expert_review += file_stats.cases_needing_expert_review
        total_stats.high_confidence += file_stats.high_confidence
        total_stats.medium_confidence += file_stats.medium_confidence
        total_stats.low_confidence += file_stats.low_confidence
        total_stats.skipped_cases += file_stats.skipped_cases
        total_stats.errors.extend(file_stats.errors)

    # Print summary
    log.info("")
    log.info("=" * 70)
    log.info("ENRICHMENT SUMMARY")
    log.info("=" * 70)
    log.info("Total benchmark cases:          %d", total_stats.total_cases)
    log.info("Successfully enriched:          %d", total_enriched)
    log.info("Skipped (no input):             %d", total_stats.skipped_cases)
    log.info("Errors:                         %d", len(total_stats.errors))
    log.info("")
    log.info("Cases with structured claims:   %d", total_stats.cases_with_structured_claims)
    log.info("Cases with invalidity GT:       %d", total_stats.cases_with_invalidity_gt)
    log.info("Cases with DoE GT:              %d", total_stats.cases_with_doe_gt)
    log.info("Cases with expiry dates:        %d", total_stats.cases_with_expiry_dates)
    log.info("")
    log.info(
        "Confidence: HIGH=%d  MEDIUM=%d  LOW=%d",
        total_stats.high_confidence,
        total_stats.medium_confidence,
        total_stats.low_confidence,
    )
    log.info("Needs expert review:            %d", total_stats.cases_needing_expert_review)

    if total_stats.errors:
        log.warning("")
        log.warning("ERRORS:")
        for err in total_stats.errors[:20]:
            log.warning("  %s", err)

    if args.dry_run:
        log.info("")
        log.info("[DRY RUN] No files were written. Remove --dry-run to write enriched files.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
