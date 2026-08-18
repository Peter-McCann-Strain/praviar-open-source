"""Real Typst regressions for representative low-cost compound reports."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from praviar_pipeline.models.report import FTOReport, ReportManifest
from praviar_pipeline.rendering.artifact_quality import validate_pdf_ua1_artifact
from praviar_pipeline.rendering.pdf import render_pdf

from api.fixtures.demo_reports import (
    aspirin_report,
    sofosbuvir_report,
    succinic_acid_report,
)

pytestmark = pytest.mark.skipif(
    shutil.which("typst") is None
    or shutil.which("pdftotext") is None
    or importlib.util.find_spec("pypdfium2") is None,
    reason=(
        "Typst, pdftotext, and the production PDF validator dependency are "
        "required for real PDF rendering regressions"
    ),
)


def _manifest(compound_query: str) -> ReportManifest:
    return ReportManifest(
        pipeline_version="0" * 40,
        source_tree_state="representative-pdf-regression",
        source_tree_digest="1" * 64,
        generated_at=datetime(2026, 7, 31, 12, 0, tzinfo=UTC),
        compound_query=compound_query,
        tool_trace_digest="2" * 64,
    )


def _pdf_text(path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", str(path), "-"],
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout


@pytest.mark.parametrize(
    ("slug", "factory", "expected_compound", "expects_blocker_docket"),
    [
        ("aspirin", aspirin_report, "Aspirin", False),
        ("succinic-acid", succinic_acid_report, "Succinic Acid", True),
        ("sofosbuvir", sofosbuvir_report, "Sofosbuvir", True),
    ],
)
def test_representative_compound_report_compiles_as_real_pdf(
    tmp_path: Path,
    slug: str,
    factory: Callable[[], dict],
    expected_compound: str,
    expects_blocker_docket: bool,
) -> None:
    report = FTOReport.model_validate(factory()).model_copy(update={"manifest": _manifest(slug)})

    output = render_pdf(report, tmp_path / f"{slug}.pdf")
    text = _pdf_text(output)

    assert output.stat().st_size > 50_000
    assert expected_compound.lower() in text.lower()
    assert "Recommendations" in text
    if expects_blocker_docket:
        assert "National-right blocker docket" in text
        assert "Primary docket reference" in text
        assert "never to a WO publication or patent-family label" in text


@pytest.mark.parametrize(
    ("governance", "expected_label"),
    [
        (None, "RELIANCE BLOCKED - GOVERNANCE PROVENANCE MISSING"),
        (
            {
                "rollout_state": "shadow",
                "influence_permitted": False,
                "evidence_gate_passed": False,
            },
            "SHADOW EVIDENCE - NON-INFLUENTIAL",
        ),
    ],
)
def test_pdf_makes_drawing_reliance_boundary_prominent(
    tmp_path: Path,
    governance: dict | None,
    expected_label: str,
) -> None:
    payload = aspirin_report()
    payload["drawing_analyses"] = [
        {
            "patent_id": "US0000000011A1",
            "pages_fetched": 1,
            "pages_with_structures": 1,
            "structures_found": 1,
            "structures_valid": 1,
            "structures": [
                {
                    "patent_id": "US0000000011A1",
                    "page_number": 1,
                    "structure_index": 1,
                    "canonical_smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
                    "confidence": 0.91,
                    "tanimoto_to_target": 1.0,
                    "drawing_risk_signal": "high",
                }
            ],
            "governance_provenance": governance,
            "highest_risk_signal": "high",
            "highest_tanimoto": 1.0,
        }
    ]
    payload["drawing_summary"] = {
        "patents_analyzed": 1,
        "patents_with_structures": 1,
        "total_structures": 1,
        "patents_with_high_risk": 1,
    }
    report = FTOReport.model_validate(payload).model_copy(
        update={"manifest": _manifest("aspirin-drawing-governance")}
    )

    output = render_pdf(report, tmp_path / "aspirin-drawings.pdf")

    assert expected_label in _pdf_text(output)


@pytest.mark.skipif(
    shutil.which("verapdf") is None,
    reason="A real veraPDF binary is required for PDF/UA-1 validation",
)
def test_real_verapdf_accepts_representative_pdf(tmp_path: Path) -> None:
    report = FTOReport.model_validate(aspirin_report()).model_copy(
        update={"manifest": _manifest("aspirin-verapdf")}
    )
    output = render_pdf(report, tmp_path / "aspirin-verapdf.pdf")

    receipt = validate_pdf_ua1_artifact(output)

    assert receipt.profile_name == "PDF/UA-1 validation profile"
    assert receipt.passed_rules > 0
    assert receipt.passed_checks > 0
