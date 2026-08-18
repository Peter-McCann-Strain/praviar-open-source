"""Tests for praviar_pipeline.rendering.csv — CSV export for risk matrix and claim charts."""

import csv
import io
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.invalidity import ClaimChart, ClaimChartEntry, InvalidityAssessment
from praviar_pipeline.models.report_common import (
    SourceHealth,
    SourceHealthEntry,
    SourceStatus,
)
from praviar_pipeline.rendering.csv import render_csv
from praviar_pipeline.rendering.export_options import ExportRenderOptions
from praviar_pipeline.rendering.spreadsheet_safety import neutralize_spreadsheet_value


def _make_analysis(
    patent_id: str = "US1234567B2",
    risk_level: RiskLevel = RiskLevel.HIGH,
    expiry_date: date | None = date(2035, 6, 15),
    claim_numbers: list[int] | None = None,
) -> PatentAnalysis:
    claims = []
    for n in claim_numbers or [1]:
        claims.append(
            ClaimAnalysis(
                claim_number=n,
                claim_type="independent",
                elements=[],
                overall_status=ElementStatus.MET,
                overall_confidence=0.9,
            )
        )
    return PatentAnalysis(
        patent_id=patent_id,
        title=f"Patent {patent_id}",
        assignee="Acme Corp",
        claims_analyzed=claims,
        risk_level=risk_level,
        risk_summary=f"Risk summary for {patent_id}",
        expiry_date=expiry_date,
    )


def _make_invalidity_with_chart() -> InvalidityAssessment:
    entry = ClaimChartEntry(
        element_number=1,
        element_text="fermenting a microorganism",
        prior_art_reference_id="REF-001",
        prior_art_disclosure="Prior art discloses fermentation",
        citation_location="col. 5, lines 10-20",
        disclosed="yes",
    )
    chart = ClaimChart(
        patent_id="US1234567B2",
        claim_number=1,
        prior_art_reference_id="REF-001",
        entries=[entry],
        chart_summary="All elements disclosed",
    )
    return InvalidityAssessment(
        patent_id="US1234567B2",
        claim_numbers=[1],
        claim_charts=[chart],
    )


def _make_report(**overrides):
    defaults = {
        "report_id": "csv-test-001",
        "compound": SimpleNamespace(name="test compound"),
        "patent_analyses": [],
        "invalidity_assessments": [],
        "search_sources_used": [],
        "source_health": SourceHealth(),
        "disclaimer": "",
    }
    defaults.update(overrides)
    report = MagicMock()
    for k, v in defaults.items():
        setattr(report, k, v)
    return report


class TestRenderCsv:
    def test_returns_two_files(self):
        report = _make_report()
        result = render_csv(report)
        assert "export_metadata.csv" in result
        assert "source_audit.csv" in result
        assert "risk_matrix.csv" in result
        assert "claim_charts.csv" in result

    def test_executive_scope_omits_claim_chart_file(self):
        ia = _make_invalidity_with_chart()
        report = _make_report(invalidity_assessments=[ia])
        options = ExportRenderOptions.from_values(
            ["executive_summary"],
            audience="executive",
        )

        result = render_csv(report, options=options)

        assert set(result) == {"export_metadata.csv", "source_audit.csv"}
        assert "Executive Brief" in result["export_metadata.csv"]

    @pytest.mark.parametrize(
        "payload",
        [
            '=HYPERLINK("https://example.com")',
            "+1+1",
            "-2+3",
            "@SUM(1,2)",
            ' \t=HYPERLINK("https://example.com")',
            "\r=1+1",
            "\n@SUM(1,2)",
            "\x00=1+1",
        ],
    )
    def test_external_text_is_escaped_for_spreadsheet_imports(self, payload: str):
        report = _make_report(
            report_id=payload,
            patent_analyses=[
                _make_analysis(
                    patent_id="US-FORMULA",
                    risk_level=RiskLevel.HIGH,
                )
            ],
        )
        report.compound.name = payload
        report.patent_analyses[0].title = payload
        report.patent_analyses[0].assignee = payload
        report.patent_analyses[0].risk_summary = payload

        result = render_csv(report)

        expected = neutralize_spreadsheet_value(payload)
        metadata_rows = list(csv.reader(io.StringIO(result["export_metadata.csv"])))
        risk_rows = list(csv.reader(io.StringIO(result["risk_matrix.csv"])))
        assert ["Report ID", expected] in metadata_rows
        assert ["Compound", expected] in metadata_rows
        assert risk_rows[1].count(expected) >= 3

        for csv_payload in result.values():
            for row in csv.reader(io.StringIO(csv_payload)):
                for value in row:
                    probe = value.lstrip(" \t\r\n\x00")
                    assert not probe.startswith(("=", "+", "-", "@")), value

    def test_risk_matrix_has_header(self):
        report = _make_report()
        result = render_csv(report)
        reader = csv.reader(io.StringIO(result["risk_matrix.csv"]))
        header = next(reader)
        assert "Patent ID" in header
        assert "Matter Clearance Decision" in header
        assert "Governed Patent Posture" in header
        assert "Claim-Coverage Screen" in header
        assert "Expiry Date" in header

    def test_risk_matrix_sorted_by_risk(self):
        analyses = [
            _make_analysis("US-LOW", RiskLevel.LOW),
            _make_analysis("US-HIGH", RiskLevel.HIGH),
            _make_analysis("US-MED", RiskLevel.MEDIUM),
        ]
        report = _make_report(patent_analyses=analyses)
        result = render_csv(report)
        reader = csv.reader(io.StringIO(result["risk_matrix.csv"]))
        next(reader)  # skip header
        rows = list(reader)
        assert rows[0][0] == "US-HIGH"
        assert rows[1][0] == "US-MED"
        assert rows[2][0] == "US-LOW"

    def test_risk_matrix_formats_expiry_date(self):
        analyses = [_make_analysis(expiry_date=date(2040, 12, 31))]
        report = _make_report(patent_analyses=analyses)
        result = render_csv(report)
        assert "2040-12-31" in result["risk_matrix.csv"]

    def test_risk_matrix_empty_expiry(self):
        analyses = [_make_analysis(expiry_date=None)]
        report = _make_report(patent_analyses=analyses)
        result = render_csv(report)
        reader = csv.reader(io.StringIO(result["risk_matrix.csv"]))
        next(reader)
        row = next(reader)
        assert row[6] == ""  # Expiry Date column

    def test_risk_matrix_claims_comma_separated(self):
        analyses = [_make_analysis(claim_numbers=[1, 3, 5])]
        report = _make_report(patent_analyses=analyses)
        result = render_csv(report)
        assert "1, 3, 5" in result["risk_matrix.csv"]

    def test_risk_level_uppercased(self):
        analyses = [_make_analysis(risk_level=RiskLevel.HIGH)]
        report = _make_report(patent_analyses=analyses)
        result = render_csv(report)
        assert "HIGH" in result["risk_matrix.csv"]

    def test_claim_charts_has_header(self):
        report = _make_report()
        result = render_csv(report)
        reader = csv.reader(io.StringIO(result["claim_charts.csv"]))
        header = next(reader)
        assert "Patent ID" in header
        assert "Element Text" in header
        assert "Disclosed" in header

    def test_claim_charts_with_entries(self):
        ia = _make_invalidity_with_chart()
        report = _make_report(invalidity_assessments=[ia])
        result = render_csv(report)
        reader = csv.reader(io.StringIO(result["claim_charts.csv"]))
        next(reader)  # skip header
        row = next(reader)
        assert row[0] == "US1234567B2"
        assert row[4] == "fermenting a microorganism"
        assert row[7] == "yes"
        assert row[9] == "Yes"  # all_elements_disclosed

    def test_empty_report(self):
        report = _make_report()
        result = render_csv(report)
        # Should have headers only
        risk_lines = result["risk_matrix.csv"].strip().split("\n")
        chart_lines = result["claim_charts.csv"].strip().split("\n")
        assert len(risk_lines) == 1  # header only
        assert len(chart_lines) == 1  # header only

    def test_source_audit_includes_failed_and_zero_hit_sources(self):
        report = _make_report(
            source_health=SourceHealth(
                entries=[
                    SourceHealthEntry(
                        source="pubchem",
                        status=SourceStatus.OK,
                        patent_count=0,
                    ),
                    SourceHealthEntry(
                        source="lens",
                        status=SourceStatus.FAILED,
                        patent_count=0,
                        error_message=(
                            "401 for https://api.openalex.org/works?api_key=SUPERSECRET"
                        ),
                    ),
                    SourceHealthEntry(
                        source="patentscope",
                        status=SourceStatus.NOT_CONFIGURED,
                        patent_count=0,
                        error_message="API key missing",
                    ),
                ]
            )
        )

        result = render_csv(report)
        reader = csv.reader(io.StringIO(result["source_audit.csv"]))
        rows = list(reader)

        assert rows[0] == ["Record Type", "Source", "Status", "Patents Found", "Detail"]
        assert any(row[1] == "pubchem" and row[2] == "Successful" for row in rows)
        assert any(row[1] == "lens" and row[2] == "Unavailable" for row in rows)
        assert any("Provider request failed" in row[4] for row in rows)
        assert "SUPERSECRET" not in result["source_audit.csv"]
        assert "api_key=" not in result["source_audit.csv"]
        assert any(row[1] == "patentscope" and row[2] == "Not configured" for row in rows)
        assert any("exhaustive legal clearance" in row[4] for row in rows)
