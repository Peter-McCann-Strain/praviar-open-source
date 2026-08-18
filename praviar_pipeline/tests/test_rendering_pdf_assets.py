"""Fail-closed tests for PDF asset generation."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest

from praviar_pipeline.models.report_decisioning import ClearanceDecision
from praviar_pipeline.rendering import charts, structures
from praviar_pipeline.rendering import pdf as pdf_renderer
from praviar_pipeline.rendering.branding import BrandingConfig

_PNG_1X1 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _report(**overrides):
    base = {
        "audit_trail": [],
        "patent_analyses": [],
        "patent_details": {},
        "source_health": SimpleNamespace(entries=[]),
        "risk_summary": SimpleNamespace(
            overall_risk="clear",
            blocking_patents_count=0,
            total_patents_analyzed=0,
        ),
        "clearance_decision": ClearanceDecision(),
        "compound": SimpleNamespace(canonical_smiles="CCO"),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_generate_charts_fails_closed_when_required_chart_errors(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        charts,
        "render_funnel_chart",
        lambda *_: (_ for _ in ()).throw(ValueError("boom")),
    )
    monkeypatch.setattr(charts, "render_risk_distribution_chart", lambda *_: _PNG_1X1)
    monkeypatch.setattr(charts, "render_risk_gauge", lambda *_: _PNG_1X1)

    with pytest.raises(RuntimeError, match="funnel_chart"):
        pdf_renderer._generate_charts(_report(), tmp_path)


def test_generate_structures_fails_closed_when_target_structure_missing(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(structures, "render_compound_svg", lambda *_: "")
    monkeypatch.setattr(structures, "render_comparison_svg", lambda *_: "<svg />")

    with pytest.raises(RuntimeError, match="target structure"):
        pdf_renderer._generate_structures(_report(), tmp_path)


def test_generate_structures_fails_closed_when_comparison_structure_errors(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    analysis = SimpleNamespace(patent_id="US123")
    monkeypatch.setattr(structures, "render_compound_svg", lambda *_: "<svg />")
    monkeypatch.setattr(
        structures,
        "render_comparison_svg",
        lambda *_: (_ for _ in ()).throw(ValueError("bad comparison")),
    )

    with pytest.raises(RuntimeError, match="US123"):
        pdf_renderer._generate_structures(
            _report(
                patent_analyses=[analysis],
                patent_details={"US123": {"canonical_smiles": "CCC"}},
            ),
            tmp_path,
        )


def test_render_via_typst_requires_manifest(tmp_path):
    with pytest.raises(RuntimeError, match="manifest is required"):
        pdf_renderer._render_via_typst(
            _report(manifest=None),
            tmp_path / "report.pdf",
        )


def test_public_pdf_renderer_refuses_to_synthesize_missing_manifest(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(pdf_renderer, "_typst_available", lambda: True)

    with pytest.raises(RuntimeError, match="cannot synthesize historical run provenance"):
        pdf_renderer.render_pdf(
            _report(manifest=None),
            tmp_path / "report.pdf",
        )


def test_risk_gauge_uses_governed_blocker_count(tmp_path, monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    monkeypatch.setattr(charts, "render_funnel_chart", lambda *_: _PNG_1X1)
    monkeypatch.setattr(charts, "render_risk_distribution_chart", lambda *_: _PNG_1X1)

    def render_risk_gauge(risk, blockers, analyzed):
        captured.update(risk=risk, blockers=blockers, analyzed=analyzed)
        return _PNG_1X1

    monkeypatch.setattr(charts, "render_risk_gauge", render_risk_gauge)
    report = _report(
        risk_summary=SimpleNamespace(
            overall_risk="high",
            blocking_patents_count=99,
            total_patents_analyzed=3,
        ),
        clearance_decision=ClearanceDecision(),
    )

    pdf_renderer._generate_charts(report, tmp_path)

    assert captured["blockers"] == 0


class _TypstPayloadReport:
    manifest: ClassVar[dict[str, str]] = {"pipeline_version": "test"}
    clearance_decision: ClassVar[ClearanceDecision] = ClearanceDecision()
    risk_summary: ClassVar[SimpleNamespace] = SimpleNamespace(total_patents_analyzed=1)

    def model_dump(self, *, mode: str) -> dict:
        assert mode == "json"
        return {
            "report_id": "pdf-assets-test",
            "manifest": self.manifest,
            "compound": {"canonical_smiles": "CCO", "name": "ethanol"},
            "risk_summary": {
                "overall_risk": "clear",
                "blocking_patents_count": 0,
                "total_patents_analyzed": 1,
            },
            "patent_analyses": [
                {
                    "patent_id": "WO/2026/123456",
                    "title": "Test patent",
                    "risk_level": "clear",
                    "claims_analyzed": [],
                }
            ],
        }


def test_typst_payload_uses_local_assets_dir_and_svg_comparison(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_payload: dict = {}
    captured_cmd: list[str] = []

    def fake_generate_charts(_report, _assets_path):
        return None

    def fake_generate_structures(_report, assets_path: Path):
        (assets_path / "target_structure.svg").write_text("<svg />", encoding="utf-8")
        (assets_path / "comparison_WO_2026_123456.svg").write_text(
            "<svg />",
            encoding="utf-8",
        )

    def fake_run(cmd, *args, **kwargs):
        captured_cmd.extend(cmd)
        data_path = None
        for arg in cmd:
            if isinstance(arg, str) and arg.startswith("data-path="):
                data_path = Path(kwargs["cwd"]) / arg.split("=", 1)[1]
                break
        assert data_path is not None
        captured_payload.update(json.loads(data_path.read_text(encoding="utf-8")))
        Path(cmd[-1]).write_bytes(b"%PDF-1.4\n")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    fake_settings = SimpleNamespace(pdf_typst_timeout=60)
    monkeypatch.setattr(pdf_renderer, "_generate_charts", fake_generate_charts)
    monkeypatch.setattr(pdf_renderer, "_generate_structures", fake_generate_structures)
    monkeypatch.setattr(pdf_renderer.subprocess, "run", fake_run)
    monkeypatch.setattr(pdf_renderer, "get_settings", lambda: fake_settings)

    pdf_renderer._render_via_typst(_TypstPayloadReport(), tmp_path / "report.pdf")

    assert "assets-dir=../assets" in captured_cmd
    assert "--ignore-system-fonts" in captured_cmd
    assert captured_cmd[captured_cmd.index("--pdf-standard") + 1] == "ua-1"
    patent = captured_payload["patent_analyses"][0]
    assert patent["_has_comparison_image"] is True
    assert patent["_comparison_image_id"] == "WO_2026_123456"
    assert patent["_comparison_image_ext"] == "svg"
    scope = captured_payload["_evidence_scope"]
    assert scope["reported_jurisdictions"][0]["code"] == "WO"
    assert "exhaustive global FTO clearance" in scope["jurisdiction_claim"]


def test_typst_branding_payload_copies_custom_logo_into_assets(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custom_logo = tmp_path / "firm-logo.svg"
    custom_logo.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10" />',
        encoding="utf-8",
    )
    captured_branding: dict = {}

    def fake_generate_charts(_report, _assets_path):
        return None

    def fake_generate_structures(_report, assets_path: Path):
        (assets_path / "target_structure.svg").write_text("<svg />", encoding="utf-8")

    def fake_run(cmd, *args, **kwargs):
        branding_path = None
        for arg in cmd:
            if isinstance(arg, str) and arg.startswith("branding-path="):
                branding_path = Path(kwargs["cwd"]) / arg.split("=", 1)[1]
                break
        assert branding_path is not None
        captured_branding.update(json.loads(branding_path.read_text(encoding="utf-8")))
        copied_logo = Path(kwargs["cwd"]) / "assets" / "branding_logo.svg"
        assert copied_logo.read_text(encoding="utf-8") == custom_logo.read_text(encoding="utf-8")
        Path(cmd[-1]).write_bytes(b"%PDF-1.4\n")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    fake_settings = SimpleNamespace(pdf_typst_timeout=60)
    monkeypatch.setattr(pdf_renderer, "_generate_charts", fake_generate_charts)
    monkeypatch.setattr(pdf_renderer, "_generate_structures", fake_generate_structures)
    monkeypatch.setattr(pdf_renderer.subprocess, "run", fake_run)
    monkeypatch.setattr(pdf_renderer, "get_settings", lambda: fake_settings)

    pdf_renderer._render_via_typst(
        _TypstPayloadReport(),
        tmp_path / "report.pdf",
        branding=BrandingConfig(
            logo_path=str(custom_logo),
            firm_name="Baker & McKenzie LLP",
        ),
    )

    assert captured_branding["logo_path"] == "../assets/branding_logo.svg"
    assert captured_branding["display_name"] == "Baker & McKenzie LLP"
    assert captured_branding["legal_marking"] == "CONFIDENTIAL DRAFT"
    assert captured_branding["privilege_header"] is None
    assert "does NOT constitute legal advice" in captured_branding["disclaimer_text"]


def test_typst_font_resolution_warnings_fail_closed(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_generate_charts(_report, _assets_path):
        return None

    def fake_generate_structures(_report, assets_path: Path):
        (assets_path / "target_structure.svg").write_text("<svg />", encoding="utf-8")

    def fake_run(cmd, *args, **kwargs):
        Path(cmd[-1]).write_bytes(b"%PDF-1.4\n")
        return SimpleNamespace(
            returncode=0,
            stderr="warning: unknown font family: Söhne",
            stdout="",
        )

    fake_settings = SimpleNamespace(pdf_typst_timeout=60)
    monkeypatch.setattr(pdf_renderer, "_generate_charts", fake_generate_charts)
    monkeypatch.setattr(pdf_renderer, "_generate_structures", fake_generate_structures)
    monkeypatch.setattr(pdf_renderer.subprocess, "run", fake_run)
    monkeypatch.setattr(pdf_renderer, "get_settings", lambda: fake_settings)

    with pytest.raises(RuntimeError, match="Typst font resolution failed"):
        pdf_renderer._render_via_typst(_TypstPayloadReport(), tmp_path / "report.pdf")


def test_typst_branding_payload_fails_when_custom_logo_is_missing(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="Branding logo not found"):
        pdf_renderer._typst_branding_payload(
            BrandingConfig(
                logo_path=str(tmp_path / "missing-logo.svg"),
                firm_name="Baker & McKenzie LLP",
            ),
            tmp_path,
        )


def test_patent_detail_template_uses_comparison_image_extension() -> None:
    template = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "praviar_pipeline"
        / "rendering"
        / "templates"
        / "components"
        / "patent-detail.typ"
    )

    body = template.read_text(encoding="utf-8")

    assert '_comparison_image_ext", default: "png"' in body
    assert '_comparison_image_id", default: pid' in body
    assert '"/comparison_" + comparison-id + "." + comparison-ext' in body
    assert 'alt: "Structural comparison between the target compound and " + pid' in body


def test_typst_templates_declare_accessible_document_metadata_and_image_text() -> None:
    template_root = (
        Path(__file__).resolve().parents[1] / "src" / "praviar_pipeline" / "rendering" / "templates"
    )
    report_template = (template_root / "report.typ").read_text(encoding="utf-8")
    component_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (template_root / "components").glob("*.typ")
    )

    assert "#set document(" in report_template
    assert "title:" in report_template
    assert "date: none" in report_template
    assert '#set text(lang: "en")' in report_template
    assert "alt:" in component_text
    assert "#image(" not in "\n".join(
        line
        for line in component_text.splitlines()
        if "alt:" not in line and line.lstrip().startswith("#image(") and ")" in line
    )
