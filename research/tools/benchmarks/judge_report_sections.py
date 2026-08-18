#!/usr/bin/env python3
"""Batch scoring script for LLM-as-Judge evaluation of GEPA report sections.

Loads generated sections from output/gepa_sections/, matches them against
enriched GT cases, and either:
  (a) prints the judge prompt for agent-based evaluation, or
  (b) calls the Anthropic API directly for automated scoring.

Usage:
    # Print judge prompt for a specific section type (agent mode)
    python research/tools/benchmarks/judge_report_sections.py --section s1_v2 --mode agent

    # Score a random sample of 5 cases via API
    python research/tools/benchmarks/judge_report_sections.py --section s1_v2 --sample 5 --mode api

    # Score all cases for s2_v2 via API
    python research/tools/benchmarks/judge_report_sections.py --section s2_v2 --mode api

    # Print prompts for all section types
    python research/tools/benchmarks/judge_report_sections.py --mode agent

    # Score specific case IDs
    python research/tools/benchmarks/judge_report_sections.py --section s1_v2 --cases bpcia_001,bpcia_002
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

# Add project roots to path for imports
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "praviar_pipeline" / "src"))
sys.path.insert(0, str(REPO_ROOT / "research" / "experiments"))
sys.path.insert(0, str(REPO_ROOT))

import structlog

logger = structlog.get_logger()

GEPA_SECTIONS_DIR = REPO_ROOT / "praviar_pipeline" / "output" / "gepa_sections"
ENRICHED_DIR = REPO_ROOT / "research" / "benchmarks" / "enriched"

# Map file naming patterns to section_type identifiers
SECTION_FILE_PATTERNS = {
    "s1": "s1_executive",
    "s1_v2": "s1_v2",
    "s2": "s2_key_patents",
    "s2_v2": "s2_v2",
    "s3": "s3_damages",
    "s4": "s4_invalidity",
    "s5": "s5_recommendations",
    "s6": "s6_data_quality",
}


def _load_all_gt() -> dict[str, dict]:
    """Load all enriched GT cases into a dict keyed by case ID.

    Thin shim around :func:`research.tools.benchmarks.data_loader.load_enriched_ground_truth`
    so the existing call sites continue to work without churn.
    """
    return load_enriched_ground_truth(ENRICHED_DIR)


def _load_section_results(section_key: str) -> list[dict]:
    """Load all generated section results for a given section key.

    Scans batch_*_{section_key}_results.json files in the output dir.
    Returns a flat list of case result dicts with keys:
        case_id, compound_name, overall_risk, section_text
    """
    results: list[dict] = []
    pattern = f"batch_*_{section_key}_results.json"
    for path in sorted(GEPA_SECTIONS_DIR.glob(pattern)):
        with open(path) as f:
            batch = json.load(f)
        if isinstance(batch, list):
            results.extend(batch)
        elif isinstance(batch, dict) and "results" in batch:
            results.extend(batch["results"])
    return results


def _available_sections() -> list[str]:
    """Discover which section types have generated output."""
    available = set()
    for path in GEPA_SECTIONS_DIR.glob("batch_*_results.json"):
        name = path.stem
        # Extract section key from batch_N_{section_key}_results
        parts = name.replace("_results", "").split("_")
        # Skip "batch" and the batch number
        if len(parts) >= 3 and parts[0] == "batch":
            section_key = "_".join(parts[2:])
            available.add(section_key)
    return sorted(available)


def _print_separator() -> None:
    print("\n" + "=" * 80 + "\n")


def run_agent_mode(
    section_key: str | None,
    sample_n: int | None,
    case_ids: list[str] | None,
) -> None:
    """Print judge prompts for agent-based evaluation."""
    from optimization.report_judge import SECTION_TYPE_LABELS, build_judge_prompt

    gt_cases = _load_all_gt()

    if section_key:
        section_keys = [section_key]
    else:
        section_keys = _available_sections()

    for skey in section_keys:
        section_type = SECTION_FILE_PATTERNS.get(skey, skey)
        label = SECTION_TYPE_LABELS.get(section_type, section_type)
        results = _load_section_results(skey)

        if not results:
            logger.warning("no_results_found", section_key=skey)
            continue

        # Filter to specific case IDs if requested
        if case_ids:
            results = [r for r in results if r.get("case_id") in case_ids]

        # Sample if requested
        if sample_n and sample_n < len(results):
            results = random.sample(results, sample_n)

        print(f"# Judge Prompts for {label} ({len(results)} cases)")
        _print_separator()

        for i, result in enumerate(results, 1):
            cid = result.get("case_id", "unknown")
            section_text = result.get("section_text", "")
            compound = result.get("compound_name", "unknown")

            gt = gt_cases.get(cid)
            if not gt:
                logger.warning("gt_not_found", case_id=cid)
                continue

            system_prompt, user_prompt = build_judge_prompt(section_text, gt, section_type)

            print(f"## Case {i}: {cid} — {compound}")
            print(f"## Section: {label}")
            print()
            print("### System Prompt")
            print()
            print(system_prompt)
            print()
            print("### User Prompt")
            print()
            print(user_prompt)
            _print_separator()

        print(f"# Total: {len(results)} judge prompts for {label}")
        print()


async def run_api_mode(
    section_key: str | None,
    sample_n: int | None,
    case_ids: list[str] | None,
    model: str,
    max_concurrent: int,
    output_path: Path | None,
) -> None:
    """Score sections via Anthropic API and print/save results."""
    from optimization.report_judge import (
        SECTION_TYPE_LABELS,
        judge_report_section,
    )

    gt_cases = _load_all_gt()

    if section_key:
        section_keys = [section_key]
    else:
        section_keys = _available_sections()

    all_results: list[dict] = []

    for skey in section_keys:
        section_type = SECTION_FILE_PATTERNS.get(skey, skey)
        label = SECTION_TYPE_LABELS.get(section_type, section_type)
        results = _load_section_results(skey)

        if not results:
            logger.warning("no_results_found", section_key=skey)
            continue

        if case_ids:
            results = [r for r in results if r.get("case_id") in case_ids]

        if sample_n and sample_n < len(results):
            results = random.sample(results, sample_n)

        print(f"Scoring {len(results)} cases for {label} using {model}...")

        import asyncio as _asyncio

        semaphore = _asyncio.Semaphore(max_concurrent)

        async def _score_one(r: dict) -> dict:
            async with semaphore:
                cid = r.get("case_id", "unknown")
                section_text = r.get("section_text", "")
                gt = gt_cases.get(cid)
                if not gt:
                    return {
                        "case_id": cid,
                        "section_type": section_type,
                        "error": "GT not found",
                    }
                try:
                    score = await judge_report_section(section_text, gt, section_type, model=model)
                    return {
                        "case_id": cid,
                        "compound_name": r.get("compound_name", ""),
                        "section_type": section_type,
                        **score,
                    }
                except Exception as e:
                    logger.error("judge_failed", case_id=cid, error=str(e))
                    return {
                        "case_id": cid,
                        "section_type": section_type,
                        "error": str(e),
                    }

        tasks = [_score_one(r) for r in results]
        scored = await _asyncio.gather(*tasks)
        all_results.extend(scored)

        # Print summary
        valid = [s for s in scored if "composite" in s]
        if valid:
            composites = [s["composite"] for s in valid]
            mean_composite = sum(composites) / len(composites)
            print(f"  {label}: {len(valid)} scored, mean composite = {mean_composite:.4f}")

            # Per-dimension summary
            for dim in [
                "legal_accuracy",
                "defensibility",
                "completeness",
                "professional_quality",
                "patent_accuracy",
            ]:
                scores = [
                    s["dimensions"][dim]["score"] for s in valid if dim in s.get("dimensions", {})
                ]
                if scores:
                    print(
                        f"    {dim}: mean={sum(scores) / len(scores):.2f} "
                        f"(min={min(scores)}, max={max(scores)})"
                    )
        else:
            print(f"  {label}: no valid scores")

    # Save results
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"\nResults saved to {output_path}")
    else:
        # Default output path
        default_out = GEPA_SECTIONS_DIR / "judge_scores.json"
        default_out.parent.mkdir(parents=True, exist_ok=True)
        with open(default_out, "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"\nResults saved to {default_out}")

    # Overall summary
    valid_all = [s for s in all_results if "composite" in s]
    if valid_all:
        print(f"\nOverall: {len(valid_all)} sections scored")
        mean_all = sum(s["composite"] for s in valid_all) / len(valid_all)
        print(f"Overall mean composite: {mean_all:.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-as-Judge scoring for GEPA report sections")
    parser.add_argument(
        "--section",
        type=str,
        default=None,
        help="Section type to judge (e.g., s1_v2, s2_v2, s3, s4, s5, s6). "
        "If omitted, judges all available sections.",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Random sample of N cases to judge (for efficiency).",
    )
    parser.add_argument(
        "--cases",
        type=str,
        default=None,
        help="Comma-separated case IDs to judge (e.g., bpcia_001,bpcia_002).",
    )
    parser.add_argument(
        "--mode",
        choices=["agent", "api"],
        default="agent",
        help="'agent' prints prompts for Claude Code agents; 'api' calls Anthropic API directly.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-haiku-4-5-20251001",
        help="Model for API mode (default: claude-haiku-4-5-20251001).",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=5,
        help="Max concurrent API calls in API mode.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output path for API mode results JSON.",
    )
    parser.add_argument(
        "--list-sections",
        action="store_true",
        help="List available section types and exit.",
    )

    args = parser.parse_args()

    if args.list_sections:
        available = _available_sections()
        print("Available section types:")
        for s in available:
            results = _load_section_results(s)
            print(f"  {s}: {len(results)} cases")
        return

    case_ids = args.cases.split(",") if args.cases else None

    if args.mode == "agent":
        run_agent_mode(args.section, args.sample, case_ids)
    elif args.mode == "api":
        output_path = Path(args.output) if args.output else None
        asyncio.run(
            run_api_mode(
                args.section,
                args.sample,
                case_ids,
                args.model,
                args.max_concurrent,
                output_path,
            )
        )


if __name__ == "__main__":
    main()
