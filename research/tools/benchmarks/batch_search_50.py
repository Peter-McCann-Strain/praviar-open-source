"""Batch search 50 compounds via real patent APIs (no LLM calls).

Runs Steps 1 (resolve) + 2 (search) only — no query expansion (Step 1b)
or triage (Step 3) since those use LLM calls. Those will be simulated by
Claude Code agents on the cached results.

Usage:
    python research/tools/benchmarks/batch_search_50.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "praviar_pipeline" / "src"))

import structlog

from praviar_pipeline.pipeline.step1_resolve import resolve_compound
from praviar_pipeline.pipeline.step2_search import search_patents

logger = structlog.get_logger()

# 50 compounds — deliberately diverse
COMPOUNDS = [
    # --- HIGH complexity (active patents, thickets, biologics) ---
    "semaglutide",
    "pembrolizumab",
    "trastuzumab",
    "upadacitinib",
    "darolutamide",
    "elexacaftor",
    "osimertinib",
    "dupilumab",
    "sacubitril",
    "abemaciclib",
    # --- MEDIUM complexity (mix of expired/active, litigation) ---
    "apixaban",
    "ibrutinib",
    "enzalutamide",
    "apalutamide",
    "venetoclax",
    "baricitinib",
    "ruxolitinib",
    "tofacitinib",
    "cabozantinib",
    "olaparib",
    # --- Biologics (BPCIA pathway) ---
    "bevacizumab",
    "rituximab",
    "infliximab",
    "denosumab",
    "secukinumab",
    "aflibercept",
    "ranibizumab",
    "tocilizumab",
    "natalizumab",
    "vedolizumab",
    # --- CLEAR / expired (baseline comparison) ---
    "atorvastatin",
    "metformin",
    "omeprazole",
    "amlodipine",
    "lisinopril",
    "sertraline",
    "montelukast",
    "valsartan",
    "losartan",
    "clopidogrel",
    # --- Recently approved / novel (not in GT) ---
    "tirzepatide",
    "teclistamab",
    "teplizumab",
    "oteseconazole",
    "mavacamten",
    "tremelimumab",
    "nirsevimab",
    "elranatamab",
    "suzetrigine",
    "rezatapopt",
]

OUTPUT_DIR = REPO_ROOT / "research" / "output" / "batch_search_50"


COMPOUND_TIMEOUT = 2400  # 40 minutes — EPO rate limit (30/min): 800 patents = ~27min, plus margin


async def search_one(compound_name: str, idx: int) -> dict:
    """Resolve and search one compound. No LLM calls. Timeout per compound."""
    result = {
        "index": idx,
        "input": compound_name,
        "resolved": None,
        "patents_found": 0,
        "search_results": None,
        "error": None,
        "duration_s": 0,
    }
    t0 = time.time()
    try:
        # Step 1: Resolve via PubChem (free API)
        compound = await resolve_compound(compound_name)
        result["resolved"] = {
            "name": compound.name,
            "cid": compound.pubchem_cid,
            "smiles": compound.canonical_smiles,
            "compound_type": compound.compound_type,
            "molecular_weight": compound.molecular_weight,
            "synonyms_count": len(compound.synonyms),
        }

        # Step 2: Search via patent APIs (no LLM expansion, with timeout)
        patent_hits, source_health, _search_funnel = await asyncio.wait_for(
            search_patents(compound=compound, expanded_queries=None),
            timeout=COMPOUND_TIMEOUT,
        )

        result["patents_found"] = len(patent_hits)
        result["search_results"] = {
            "total_hits": len(patent_hits),
            "source_health": {
                e.source: {"status": e.status.value, "patent_count": e.patent_count}
                for e in source_health.entries
            },
            "patents": [
                {
                    "patent_id": p.patent_id,
                    "title": p.title,
                    "assignees": p.assignees,
                    "filing_date": str(p.filing_date) if p.filing_date else None,
                    "expiry_date": str(p.expiry_date) if p.expiry_date else None,
                    "priority_date": str(p.priority_date) if p.priority_date else None,
                    "abstract": p.abstract or "",
                    "claims_text": p.claims_text or "",
                    "sources": [s.value if hasattr(s, "value") else str(s) for s in p.sources],
                    "confidence_score": p.confidence_score,
                    "cpc_codes": [c for c in (p.cpc_codes if hasattr(p, "cpc_codes") else [])],
                    "patent_type": p.patent_type if hasattr(p, "patent_type") else None,
                }
                for p in patent_hits[:200]
            ],
        }

    except TimeoutError:
        result["error"] = f"TimeoutError: search exceeded {COMPOUND_TIMEOUT}s limit"
        logger.error("search_timeout", compound=compound_name, timeout=COMPOUND_TIMEOUT)
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        logger.error("search_failed", compound=compound_name, error=str(e))

    result["duration_s"] = round(time.time() - t0, 1)
    return result


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Searching {len(COMPOUNDS)} compounds via patent APIs (no LLM calls)...")
    print(f"Output: {OUTPUT_DIR}/")

    results = []
    for i, compound in enumerate(COMPOUNDS):
        outfile = OUTPUT_DIR / f"{compound.replace(' ', '_').lower()}.json"
        # Skip compounds that already have successful results
        if outfile.exists():
            existing = json.loads(outfile.read_text())
            if not existing.get("error") and existing.get("patents_found", 0) > 0:
                print(
                    f"[{i + 1}/{len(COMPOUNDS)}] {compound}... CACHED ({existing['patents_found']} patents)"
                )
                results.append(existing)
                continue

        print(f"[{i + 1}/{len(COMPOUNDS)}] {compound}...", end=" ", flush=True)
        result = await search_one(compound, i)
        results.append(result)

        outfile = OUTPUT_DIR / f"{compound.replace(' ', '_').lower()}.json"
        outfile.write_text(json.dumps(result, indent=2, default=str))

        status = "OK" if not result["error"] else "FAIL"
        print(f"{status} — {result['patents_found']} patents, {result['duration_s']}s")

        await asyncio.sleep(0.5)

    summary = {
        "total_compounds": len(COMPOUNDS),
        "successful": sum(1 for r in results if not r["error"]),
        "failed": sum(1 for r in results if r["error"]),
        "total_patents": sum(r["patents_found"] for r in results),
        "mean_patents": round(sum(r["patents_found"] for r in results) / max(len(results), 1), 1),
        "compounds": [
            {
                "name": r["input"],
                "patents": r["patents_found"],
                "type": r["resolved"]["compound_type"] if r["resolved"] else None,
                "error": r["error"],
            }
            for r in results
        ],
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))

    print(
        f"\nDone. {summary['successful']}/{summary['total_compounds']} resolved. "
        f"{summary['total_patents']} total patents found."
    )


if __name__ == "__main__":
    asyncio.run(main())
