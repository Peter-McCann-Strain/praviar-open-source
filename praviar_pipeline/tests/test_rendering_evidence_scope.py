"""Evidence-scope wording for counsel-facing report artifacts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from praviar_pipeline.models.report_common import (
    SourceHealth,
    SourceHealthEntry,
    SourceStatus,
)
from praviar_pipeline.pipeline.runtime.flow_finalize import _search_sources_from_run
from praviar_pipeline.rendering.evidence_scope import (
    build_evidence_scope_payload,
    collect_reported_jurisdiction_codes,
)


def test_evidence_scope_payload_uses_recorded_jurisdictions_only() -> None:
    report_data = {
        "source_health": {
            "entries": [
                {"source": "pubchem_sdq", "status": "ok", "patent_count": 12},
                {"source": "lens", "status": "failed", "patent_count": 0},
            ]
        },
        "search_sources_used": ["pubchem_sdq", "lens", "patentscope"],
        "decision_scope": {"jurisdictions": ["US"]},
        "jurisdiction_decisions": [{"jurisdiction": "EP"}],
        "patent_analyses": [
            {"patent_id": "WO/2026/123456", "jurisdiction": ""},
            {"patent_id": "BR112026000001", "jurisdiction": ""},
        ],
        "patent_details": {"JP202600001A": {"jurisdiction": "JP"}},
    }

    assert collect_reported_jurisdiction_codes(report_data) == (
        "US",
        "EP",
        "WO",
        "JP",
        "BR",
    )

    payload = build_evidence_scope_payload(report_data)

    assert payload["completed_source_count"] == 1
    assert payload["configured_source_count"] == 2
    assert "1 of 2 configured source requests completed" in payload["source_claim"]
    codes = [item["code"] for item in payload["reported_jurisdictions"]]
    assert codes == ["US", "EP", "WO", "JP", "BR"]
    assert "US, EP, WO, JP, BR" in payload["jurisdiction_claim"]
    assert "exhaustive global FTO clearance" in payload["jurisdiction_claim"]
    assert "CN" not in codes


def test_evidence_scope_payload_caveats_missing_scope_metadata() -> None:
    payload = build_evidence_scope_payload(
        {
            "source_health": {"entries": []},
            "search_sources_used": [],
            "patent_analyses": [],
            "patent_details": {},
        }
    )

    assert payload["configured_source_count"] == 0
    assert payload["reported_jurisdictions"] == []
    assert "No configured patent source telemetry" in payload["source_claim"]
    assert "No jurisdiction scope metadata" in payload["jurisdiction_claim"]


def test_typst_methodology_uses_evidence_scope_payload() -> None:
    component = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "praviar_pipeline"
        / "rendering"
        / "templates"
        / "components"
        / "methodology.typ"
    )
    body = component.read_text(encoding="utf-8")

    assert "_evidence_scope" in body
    assert "reported_jurisdictions" in body
    assert "coverage_caveat" in body
    assert "The search covered patents" not in body
    assert "United States Patent and Trademark Office" not in body


def test_typst_appendix_does_not_hardcode_global_jurisdiction_claim() -> None:
    component = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "praviar_pipeline"
        / "rendering"
        / "templates"
        / "components"
        / "appendices.typ"
    )
    body = component.read_text(encoding="utf-8")

    assert "_evidence_scope" in body
    assert "patent_search_step" in body
    assert "across 9 jurisdictions" not in body
    assert "US, EP, WO, JP, KR, CN, IN, CA, AU" not in body


def test_runtime_search_sources_preserve_zero_hit_and_failed_sources() -> None:
    sources = _search_sources_from_run(
        patent_hits=[SimpleNamespace(sources=[SimpleNamespace(value="hit_source")])],
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(
                    source="zero_hit_source",
                    status=SourceStatus.OK,
                    patent_count=0,
                ),
                SourceHealthEntry(
                    source="failed_source",
                    status=SourceStatus.FAILED,
                    patent_count=0,
                    error_message="timeout",
                ),
            ]
        ),
    )

    assert sources == ["failed_source", "zero_hit_source"]
