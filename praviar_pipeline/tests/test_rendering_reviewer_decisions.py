"""SG-reviewer (WS-3) — Reviewer Decisions appendix in the Typst PDF template.

When attorneys capture per-finding accept / reject / edit decisions during
review, the exported PDF must print a dedicated appendix table so the
reviewer's verdict is visible to downstream readers.

These tests mirror the structure of ``test_rendering_coverage_banner.py``:

1. Always-run fixtures / contract tests verify:
   - ``render_pdf`` accepts the ``reviewer_decisions`` kwarg and writes it
     into the JSON payload handed to Typst.
   - ``report.typ`` imports and invokes the new component.
   - The component file itself contains the user-visible strings.

2. Optional Typst integration tests (skipped when ``typst`` is not on PATH)
   verify the template compiles end-to-end with / without decisions, and
   handles edit-with-text, long notes, and the empty-list fallback.
"""

from __future__ import annotations

import json
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


def _build_report() -> FTOReport:
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
        report_id="rev-test-001",
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
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=42),
            ]
        ),
        llm_models_used={"triage": "claude-haiku-4-5-20251001"},
        manifest=make_test_report_manifest("succinic acid"),
    )


def _sample_decisions() -> list[dict]:
    return [
        {
            "finding_type": "patent",
            "finding_ref": "US7851188B2",
            "decision": "accept",
            "note": "Clear blocking patent — no design-around.",
            "edited_text": "",
            "reviewer_name": "Jane Attorney",
            "reviewer_email": "jane@example.com",
            "created_at": "2026-04-15T09:30:00+00:00",
        },
        {
            "finding_type": "claim",
            "finding_ref": "US7851188B2::claim-1",
            "decision": "edit",
            "note": "Element 2 reasoning is too strong.",
            "edited_text": (
                "Element 2 is only *partially* met — the reference teaches "
                "the salt form, not the free acid."
            ),
            "reviewer_name": "Jane Attorney",
            "reviewer_email": "jane@example.com",
            "created_at": "2026-04-15T10:05:12+00:00",
        },
        {
            "finding_type": "recommendation",
            "finding_ref": "rec-3",
            "decision": "reject",
            "note": "Not commercially realistic in our pipeline.",
            "edited_text": "",
            "reviewer_name": "Rahul Partner",
            "reviewer_email": "rahul@example.com",
            "created_at": "2026-04-15T11:20:00+00:00",
        },
    ]


# ---------------------------------------------------------------------------
# Contract tests — always run
# ---------------------------------------------------------------------------


def test_render_pdf_accepts_reviewer_decisions_kwarg() -> None:
    """The signature must expose ``reviewer_decisions`` so API workers can
    forward the list without relying on private helpers."""
    import inspect

    sig = inspect.signature(render_pdf)
    assert "reviewer_decisions" in sig.parameters


def test_reviewer_decisions_serialize_into_typst_payload(tmp_path: Path) -> None:
    """Hook the subprocess call so we can read back the JSON payload Typst
    would receive — and assert the reviewer decisions appear under the
    top-level ``reviewer_decisions`` key exactly as passed in."""
    captured_payload: dict = {}

    def fake_run(cmd, *args, **kwargs):
        # cmd: ["typst", "compile", "--input", "data-path=<path>", ...]
        data_path = None
        for arg in cmd:
            if isinstance(arg, str) and arg.startswith("data-path="):
                raw_data_path = Path(arg.split("=", 1)[1])
                data_path = raw_data_path
                if not data_path.is_absolute():
                    data_path = Path(kwargs["cwd"]) / data_path
                break
        assert data_path is not None and data_path.exists()
        captured_payload.update(json.loads(data_path.read_text(encoding="utf-8")))
        # Create an empty output file so the caller's subsequent checks don't blow up.
        output = Path(cmd[-1])
        output.write_bytes(b"%PDF-1.4\n% fake\n")
        result = type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})()
        return result

    decisions = _sample_decisions()
    report = _build_report()
    out = tmp_path / "report.pdf"

    fake_settings = type("S", (), {"pdf_typst_timeout": 60})()
    with (
        patch("praviar_pipeline.rendering.pdf._typst_available", return_value=True),
        patch("praviar_pipeline.rendering.pdf.subprocess.run", side_effect=fake_run),
        patch("praviar_pipeline.rendering.pdf.get_settings", return_value=fake_settings),
        patch("praviar_pipeline.rendering.artifact_quality.validate_pdf_artifact"),
    ):
        render_pdf(report, out, reviewer_decisions=decisions)

    assert "reviewer_decisions" in captured_payload
    loaded = captured_payload["reviewer_decisions"]
    assert len(loaded) == 3
    kinds = [d["decision"] for d in loaded]
    assert kinds == ["accept", "edit", "reject"]
    edit = loaded[1]
    assert edit["edited_text"].startswith("Element 2 is only")
    assert edit["reviewer_name"] == "Jane Attorney"


def test_reviewer_decisions_empty_list_still_injected(tmp_path: Path) -> None:
    """When no decisions are recorded, the key must still be present with
    an empty list so the Typst appendix can render its explicit fallback."""
    captured_payload: dict = {}

    def fake_run(cmd, *args, **kwargs):
        data_path = None
        for arg in cmd:
            if isinstance(arg, str) and arg.startswith("data-path="):
                raw_data_path = Path(arg.split("=", 1)[1])
                data_path = raw_data_path
                if not data_path.is_absolute():
                    data_path = Path(kwargs["cwd"]) / data_path
                break
        captured_payload.update(json.loads(data_path.read_text(encoding="utf-8")))
        Path(cmd[-1]).write_bytes(b"%PDF-1.4\n")
        return type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    report = _build_report()
    out = tmp_path / "report.pdf"

    fake_settings = type("S", (), {"pdf_typst_timeout": 60})()
    with (
        patch("praviar_pipeline.rendering.pdf._typst_available", return_value=True),
        patch("praviar_pipeline.rendering.pdf.subprocess.run", side_effect=fake_run),
        patch("praviar_pipeline.rendering.pdf.get_settings", return_value=fake_settings),
        patch("praviar_pipeline.rendering.artifact_quality.validate_pdf_artifact"),
    ):
        render_pdf(report, out)  # kwarg omitted

    assert captured_payload.get("reviewer_decisions") == []


def test_reviewer_decisions_typ_component_is_wired_into_main_template() -> None:
    """Regression guard: ``report.typ`` must import and invoke the new
    component so removing the wiring during refactor fails loudly."""
    template = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "praviar_pipeline"
        / "rendering"
        / "templates"
        / "report.typ"
    )
    body = template.read_text(encoding="utf-8")
    assert 'import "components/reviewer_decisions.typ": reviewer-decisions-section' in body
    assert "#reviewer-decisions-section(data)" in body


def test_reviewer_decisions_component_file_has_expected_surfaces() -> None:
    """The component file must include user-facing strings + decision
    branches, so stripping them in a reformatter is caught without a
    full Typst build."""
    component = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "praviar_pipeline"
        / "rendering"
        / "templates"
        / "components"
        / "reviewer_decisions.typ"
    )
    body = component.read_text(encoding="utf-8")
    assert "SG-reviewer" in body
    assert "Reviewer Decisions" in body
    assert "No reviewer decisions recorded" in body
    # Each decision variant must be handled.
    assert '"accept"' in body
    assert '"reject"' in body
    assert '"edit"' in body
    # Truncation must exist — keeps the section to about one page.
    assert "200" in body


# ---------------------------------------------------------------------------
# Optional Typst integration tests — skipped without the binary
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _typst_installed, reason="Typst not installed")
def test_reviewer_decisions_appendix_renders_with_three_decisions(
    mock_settings, tmp_path: Path
) -> None:
    """End-to-end: with three decisions (accept / edit / reject), the real
    Typst renderer produces a non-empty PDF."""
    report = _build_report()
    out = tmp_path / "with_decisions.pdf"
    render_pdf(report, out, reviewer_decisions=_sample_decisions())
    assert out.exists()
    assert out.stat().st_size > 1000
    with open(out, "rb") as fh:
        assert fh.read(5) == b"%PDF-"


@pytest.mark.skipif(not _typst_installed, reason="Typst not installed")
def test_reviewer_decisions_appendix_renders_empty_fallback(mock_settings, tmp_path: Path) -> None:
    """Empty decisions list must still render (no-decisions fallback line)."""
    report = _build_report()
    out = tmp_path / "no_decisions.pdf"
    render_pdf(report, out, reviewer_decisions=[])
    assert out.exists()
    assert out.stat().st_size > 1000


@pytest.mark.skipif(not _typst_installed, reason="Typst not installed")
def test_reviewer_decisions_appendix_truncates_long_notes(mock_settings, tmp_path: Path) -> None:
    """A 500-char note must not blow the page — the component truncates
    at 200 chars to keep the appendix to a readable size."""
    long = "x" * 500
    decisions = [
        {
            "finding_type": "patent",
            "finding_ref": "US7851188B2",
            "decision": "edit",
            "note": long,
            "edited_text": long,
            "reviewer_name": "Jane Attorney",
            "reviewer_email": "jane@example.com",
            "created_at": "2026-04-15T09:30:00+00:00",
        }
    ]
    report = _build_report()
    out = tmp_path / "long_note.pdf"
    render_pdf(report, out, reviewer_decisions=decisions)
    assert out.exists()
    assert out.stat().st_size > 1000
