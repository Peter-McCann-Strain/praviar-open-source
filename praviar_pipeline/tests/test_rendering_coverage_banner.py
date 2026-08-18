"""SG-111 — Search Coverage banner in the Typst report front matter.

These tests pin the contract that when a source fails during a pipeline
run, the resulting PDF surfaces the failure to the reader (rather than
silently showing findings that reflect a degraded dataset).

Rather than binary-grepping the PDF output, we:

1. Assert the `source_health` serialization embedded in the JSON payload
   handed to Typst contains the FAILED entry + its error message.
2. If Typst is installed on the host, run the real renderer end-to-end
   and confirm a non-empty PDF is produced — i.e. the new coverage.typ
   component compiles and does not blow up the rest of the template.
"""

from __future__ import annotations

import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.audit import PipelineAuditTrail
from praviar_pipeline.models.compound import ResolvedCompound
from praviar_pipeline.models.report import FTOReport, RiskSummary
from praviar_pipeline.models.report_common import (
    SourceHealth,
    SourceHealthEntry,
    SourceStatus,
)
from praviar_pipeline.models.verification import VerificationCheck, VerificationResult
from praviar_pipeline.rendering.pdf import render_pdf

from .pdf_test_support import make_test_report_manifest

_typst_installed = shutil.which("typst") is not None


def test_typst_doe_badges_preserve_unresolved_tristate() -> None:
    template = (
        Path(__file__).parents[1]
        / "src/praviar_pipeline/rendering/templates/components/patent-detail.typ"
    ).read_text()

    assert "if value == none" in template
    assert 'overall_equivalent", default: none' in template
    assert 'same_function", default: none' in template


def _build_report(source_health: SourceHealth) -> FTOReport:
    compound = ResolvedCompound(
        name="succinic acid",
        canonical_smiles="OC(=O)CCC(O)=O",
        inchi="InChI=1S/C4H6O4/c5-3(6)1-2-4(7)8/h1-2H2,(H,5,6)(H,7,8)",
        inchi_key="KDYFGRWQOYBRFD-UHFFFAOYSA-N",
        pubchem_cid=1110,
        molecular_formula="C4H6O4",
        molecular_weight=118.09,
        cas_numbers=["110-15-6"],
        functional_groups=["carboxylic_acid"],
        original_input="succinic acid",
        input_type="name",
    )
    analysis = PatentAnalysis(
        patent_id="US7851188B2",
        title="Methods for producing succinic acid",
        assignee="BioAmber Inc.",
        expiry_date=date(2028, 3, 15),
        claims_analyzed=[
            ClaimAnalysis(
                claim_number=1,
                claim_type="independent",
                elements=[
                    ClaimElement(
                        element_number=1,
                        element_text="A method for producing succinic acid",
                        status=ElementStatus.MET,
                        reasoning="Target compound is succinic acid",
                        confidence=0.95,
                    ),
                ],
                overall_status=ElementStatus.MET,
                overall_confidence=0.95,
            ),
        ],
        risk_level=RiskLevel.HIGH,
        risk_summary="High risk",
    )
    return FTOReport(
        report_id="cov-test-001",
        generated_at=datetime.now(UTC),
        compound=compound,
        risk_summary=RiskSummary(
            overall_risk=RiskLevel.HIGH,
            blocking_patents_count=1,
            total_patents_analyzed=1,
            key_risks=["US7851188B2: high risk"],
            executive_summary="High FTO risk.",
        ),
        patent_analyses=[analysis],
        verification=VerificationResult(
            checks=[
                VerificationCheck(
                    check_name="citation_grounding",
                    passed=True,
                    details="All patent IDs verified",
                ),
            ],
            all_citations_valid=True,
            all_claims_grounded=True,
            all_entities_valid=True,
            dates_consistent=True,
            risk_levels_justified=True,
        ),
        total_patents_found=10,
        patents_after_triage=3,
        search_sources_used=["pubchem_sdq", "lens", "patentscope"],
        audit_trail=PipelineAuditTrail(),
        source_health=source_health,
        llm_models_used={"triage": "claude-haiku-4-5-20251001"},
        manifest=make_test_report_manifest("succinic acid"),
    )


def test_source_health_serialized_into_typst_payload() -> None:
    """The JSON handed to Typst must include the FAILED entry + error message
    so the coverage component can render an attorney-legible warning."""
    source_health = SourceHealth(
        entries=[
            SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=42),
            SourceHealthEntry(
                source="lens",
                status=SourceStatus.FAILED,
                patent_count=0,
                error_message="HTTP 500 internal error from Lens API",
            ),
            SourceHealthEntry(
                source="patentscope",
                status=SourceStatus.FAILED,
                patent_count=0,
                error_message="HTTP 504 timeout after 3 retries",
            ),
        ]
    )
    report = _build_report(source_health)

    payload = report.model_dump(mode="json")
    assert "source_health" in payload
    entries = payload["source_health"]["entries"]
    statuses = {e["source"]: e["status"] for e in entries}
    assert statuses["pubchem_sdq"] == "ok"
    assert statuses["lens"] == "failed"
    assert statuses["patentscope"] == "failed"

    lens_entry = next(e for e in entries if e["source"] == "lens")
    assert "HTTP 500" in lens_entry["error_message"]
    pscope_entry = next(e for e in entries if e["source"] == "patentscope")
    assert "HTTP 504 timeout" in pscope_entry["error_message"]


def test_coverage_typ_component_is_wired_into_main_template() -> None:
    """Regression guard: ensure report.typ imports & invokes render-coverage.
    If someone removes the import during refactor, this test fails loudly."""
    template = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "praviar_pipeline"
        / "rendering"
        / "templates"
        / "report.typ"
    )
    body = template.read_text(encoding="utf-8")
    assert 'import "components/coverage.typ": render-coverage' in body
    assert "#render-coverage(data)" in body


def test_coverage_component_file_mentions_failure_messaging() -> None:
    """The component file must include user-facing strings about source-health
    so visual regressions (someone stripping the failed-source loop) are
    caught even without running Typst."""
    component = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "praviar_pipeline"
        / "rendering"
        / "templates"
        / "components"
        / "coverage.typ"
    )
    body = component.read_text(encoding="utf-8")
    # Heading text that the user will see.
    assert "Search Coverage" in body
    # Must surface failed source names + their error message.
    assert 'status", default: ""' in body or '"failed"' in body
    assert "not_configured" in body
    assert "error_message" in body
    assert "Confidence impact" in body
    assert "Source-health telemetry not recorded" in body
    assert "full source coverage" not in body


def test_render_pdf_raises_helpful_error_when_typst_missing(tmp_path: Path) -> None:
    """Smoke: without typst we get a clear RuntimeError (not an AttributeError
    from the new component)."""
    source_health = SourceHealth(
        entries=[
            SourceHealthEntry(
                source="lens",
                status=SourceStatus.FAILED,
                patent_count=0,
                error_message="HTTP 500",
            ),
        ]
    )
    report = _build_report(source_health)
    output = tmp_path / "out.pdf"
    with patch("praviar_pipeline.rendering.pdf._typst_available", return_value=False):
        with pytest.raises(RuntimeError, match="Typst is not installed"):
            render_pdf(report, output)


@pytest.mark.skipif(not _typst_installed, reason="Typst not installed")
def test_coverage_banner_renders_when_source_failed(tmp_path: Path) -> None:
    """End-to-end: with a FAILED source, the real Typst renderer must produce
    a non-empty PDF — i.e. the new coverage.typ component compiles cleanly
    alongside the rest of the template."""
    source_health = SourceHealth(
        entries=[
            SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=42),
            SourceHealthEntry(
                source="lens",
                status=SourceStatus.FAILED,
                patent_count=0,
                error_message="HTTP 500 internal error from Lens API",
            ),
        ]
    )
    report = _build_report(source_health)
    output = tmp_path / "coverage.pdf"
    result = render_pdf(report, output)
    assert result == output
    assert output.exists()
    assert output.stat().st_size > 1000
    with open(output, "rb") as fh:
        assert fh.read(5) == b"%PDF-"


@pytest.mark.skipif(not _typst_installed, reason="Typst not installed")
def test_coverage_banner_renders_when_all_sources_ok(tmp_path: Path) -> None:
    """All-OK path must also render cleanly (no failed-entry branch divides-by-zero
    or similar)."""
    source_health = SourceHealth(
        entries=[
            SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=100),
            SourceHealthEntry(source="surechembl", status=SourceStatus.OK, patent_count=50),
        ]
    )
    report = _build_report(source_health)
    output = tmp_path / "coverage_ok.pdf"
    render_pdf(report, output)
    assert output.exists()
    assert output.stat().st_size > 1000


@pytest.mark.skipif(not _typst_installed, reason="Typst not installed")
def test_coverage_banner_caveats_when_source_health_empty(tmp_path: Path) -> None:
    """Legacy reports without source_health entries render with a caveat
    and without crashing."""
    source_health = SourceHealth(entries=[])
    report = _build_report(source_health)
    output = tmp_path / "coverage_empty.pdf"
    render_pdf(report, output)
    assert output.exists()
    assert output.stat().st_size > 1000
