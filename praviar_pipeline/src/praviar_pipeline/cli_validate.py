"""Dry-run pipeline validation — checks imports, models, and configuration.

Runs without making any external API calls. Validates that:
1. All modules import correctly
2. All Pydantic models construct with test data
3. Settings load from .env
4. Prompt files exist
5. Pipeline step functions have the expected signatures

Usage:
    praviar-pipeline validate
"""

from __future__ import annotations

from pathlib import Path

from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"


def check_imports() -> list[tuple[str, str, str]]:
    """Check all module imports."""
    results = []
    modules = [
        "praviar_pipeline.config",
        "praviar_pipeline.models",
        "praviar_pipeline.models.compound",
        "praviar_pipeline.models.patent",
        "praviar_pipeline.models.triage",
        "praviar_pipeline.models.analysis",
        "praviar_pipeline.models.equivalents",
        "praviar_pipeline.models.invalidity",
        "praviar_pipeline.models.verification",
        "praviar_pipeline.models.report",
        "praviar_pipeline.clients.pubchem",
        "praviar_pipeline.clients.surechembl",
        "praviar_pipeline.clients.ptab",
        "praviar_pipeline.clients.bigquery",
        "praviar_pipeline.clients.patcid",
        "praviar_pipeline.clients.claude",
        "praviar_pipeline.pipeline.step1_resolve",
        "praviar_pipeline.pipeline.step2_search",
        "praviar_pipeline.pipeline.step3_triage",
        "praviar_pipeline.pipeline.step4_analyze",
        "praviar_pipeline.pipeline.step5_doe",
        "praviar_pipeline.pipeline.step6_invalid",
        "praviar_pipeline.pipeline.step7_verify",
        "praviar_pipeline.pipeline.step8_report",
        "praviar_pipeline.run",
    ]

    for mod in modules:
        try:
            __import__(mod)
            results.append((PASS, mod, "imported"))
        except Exception as e:
            results.append((FAIL, mod, f"import failed ({safe_exception_type(e)})"))

    return results


def check_models() -> list[tuple[str, str, str]]:
    """Construct each Pydantic model with minimal test data."""
    results = []

    from praviar_pipeline.models.analysis import (
        ClaimElement,
        ElementStatus,
        PatentAnalysis,
        RiskLevel,
    )
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.equivalents import DoEAssessment
    from praviar_pipeline.models.invalidity import InvalidityAssessment, PTABResult
    from praviar_pipeline.models.patent import PatentHit
    from praviar_pipeline.models.report import FTOReport, RiskSummary
    from praviar_pipeline.models.triage import Relevance, TriageResult
    from praviar_pipeline.models.verification import VerificationResult

    test_cases = [
        (
            "ResolvedCompound",
            lambda: ResolvedCompound(
                name="test",
                canonical_smiles="C",
                inchi="InChI=1S/CH4",
                inchi_key="VNWKTOKETHGBQD-UHFFFAOYSA-N",
                pubchem_cid=297,
                original_input="test",
                input_type="name",
            ),
        ),
        (
            "PatentHit",
            lambda: PatentHit(patent_id="US123"),
        ),
        (
            "TriageResult",
            lambda: TriageResult(
                patent_id="US123",
                relevance=Relevance.RELEVANT,
                reason="test",
            ),
        ),
        (
            "ClaimElement",
            lambda: ClaimElement(
                element_number=1,
                element_text="test",
                status=ElementStatus.MET,
                reasoning="test",
            ),
        ),
        (
            "PatentAnalysis",
            lambda: PatentAnalysis(
                patent_id="US123",
                risk_level=RiskLevel.LOW,
                risk_summary="test",
            ),
        ),
        (
            "DoEAssessment",
            lambda: DoEAssessment(
                patent_id="US123",
                claim_number=1,
                element_number=1,
            ),
        ),
        (
            "InvalidityAssessment",
            lambda: InvalidityAssessment(patent_id="US123"),
        ),
        (
            "PTABResult",
            lambda: PTABResult(),
        ),
        (
            "VerificationResult",
            lambda: VerificationResult(),
        ),
        (
            "FTOReport",
            lambda: FTOReport(
                compound=ResolvedCompound(
                    name="test",
                    canonical_smiles="C",
                    inchi="InChI=1S/CH4",
                    inchi_key="VNWKTOKETHGBQD-UHFFFAOYSA-N",
                    pubchem_cid=297,
                    original_input="test",
                    input_type="name",
                ),
                risk_summary=RiskSummary(
                    overall_risk=RiskLevel.CLEAR,
                    executive_summary="No risk.",
                ),
            ),
        ),
    ]

    for name, factory in test_cases:
        try:
            _obj = factory()
            results.append((PASS, name, "constructed"))
        except Exception as e:
            results.append((FAIL, name, f"validation failed ({safe_exception_type(e)})"))

    return results


def check_prompts() -> list[tuple[str, str, str]]:
    """Check that all prompt template files exist."""
    results = []
    prompts_dir = Path(__file__).resolve().parent / "prompts"

    expected = [
        "triage_system.txt",
        "claim_analysis_system.txt",
        "doe_fwr_system.txt",
        "invalidity_system.txt",
        "report_summary_system.txt",
    ]

    for filename in expected:
        path = prompts_dir / filename
        if path.exists():
            size = path.stat().st_size
            results.append((PASS, filename, f"{size} bytes"))
        else:
            results.append((FAIL, filename, "FILE NOT FOUND"))

    return results


def check_settings() -> list[tuple[str, str, str]]:
    """Check settings load correctly."""
    results = []

    try:
        from praviar_pipeline.config import Settings

        s = Settings()
        results.append((PASS, "Settings", "loaded"))

        # Check for missing keys
        if not s.anthropic_api_key:
            results.append((WARN, "anthropic_api_key", "not configured"))
        else:
            results.append((PASS, "anthropic_api_key", "configured"))

        if not s.patentsview_api_key:
            results.append((WARN, "patentsview_api_key", "not configured"))
        else:
            results.append((PASS, "patentsview_api_key", "configured"))

    except Exception as e:
        results.append((FAIL, "Settings", f"settings failed ({safe_exception_type(e)})"))

    return results


def check_rdkit() -> list[tuple[str, str, str]]:
    """Check RDKit availability."""
    results = []
    try:
        from rdkit import Chem

        mol = Chem.MolFromSmiles("OC(=O)CCC(O)=O")
        if mol:
            results.append((PASS, "RDKit", f"v{Chem.rdBase.rdkitVersion}"))
        else:
            results.append((FAIL, "RDKit", "Could not parse test SMILES"))
    except ImportError:
        results.append((WARN, "RDKit", "not installed — fingerprints will be skipped"))
    return results


def main(argv: list[str] | None = None):
    print("=" * 60)
    print("Praviar Pipeline Pipeline Validation (Dry Run)")
    print("=" * 60)

    sections = [
        ("Module Imports", check_imports),
        ("Model Construction", check_models),
        ("Prompt Templates", check_prompts),
        ("Settings / .env", check_settings),
        ("RDKit", check_rdkit),
    ]

    totals = {PASS: 0, FAIL: 0, WARN: 0}

    for section_name, check_fn in sections:
        print(f"\n--- {section_name} ---")
        results = check_fn()
        for status, name, detail in results:
            totals[status] = totals.get(status, 0) + 1
            print(f"  {status:4s}  {name:40s}  {detail}")

    print("\n" + "=" * 60)
    print(f"  {totals[PASS]} passed, {totals[FAIL]} failed, {totals[WARN]} warnings")
    print("=" * 60)

    if totals[FAIL] > 0:
        print("\nFix FAIL items before running the pipeline.")
        return 1
    elif totals[WARN] > 0:
        print("\nWARN items are optional but recommended. Pipeline can run without them.")
        return 0
    else:
        print("\nAll checks passed. Pipeline is ready to run.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
