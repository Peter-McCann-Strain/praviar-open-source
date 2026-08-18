from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.models.report import PatentEvidenceRecord
from praviar_pipeline.pipeline.report.evidence_index_families import build_family_gate_failures
from praviar_pipeline.pipeline.report.evidence_index_patent_helpers import (
    build_patent_component_statuses,
    build_patent_gate_failures,
    classify_source_authority,
    collect_source_names,
    derive_jurisdiction,
    normalize_dossier,
)
from praviar_pipeline.pipeline.report.evidence_index_records import collect_material_patent_ids


def test_collect_material_patent_ids_preserves_analysis_order_and_deduplicates_failures() -> None:
    analyses = [
        SimpleNamespace(patent_id="US1234567B2"),
        SimpleNamespace(patent_id="EP2345678B1"),
    ]
    analysis_failures = [
        SimpleNamespace(patent_id="EP2345678B1"),
        SimpleNamespace(patent_id="US9999999A1"),
    ]

    assert collect_material_patent_ids(analyses, analysis_failures) == [
        "US1234567B2",
        "EP2345678B1",
        "US9999999A1",
    ]


def test_build_family_gate_failures_reports_missing_structure() -> None:
    assert build_family_gate_failures(
        family_id="",
        jurisdictions=[],
        broadest_patent_id="",
        incomplete_patent_ids=["US123"],
    ) == [
        "missing_family_id",
        "missing_family_jurisdictions",
        "missing_broadest_material_patent",
        "incomplete_material_patent_records",
    ]


def test_normalize_dossier_supports_dict_input() -> None:
    dossier = normalize_dossier({"patent_id": "US123", "source_name": "uspto_odp"})
    assert dossier.patent_id == "US123"
    assert dossier.source_name == "uspto_odp"


def test_derive_jurisdiction_prefers_detail_then_patent_prefix() -> None:
    assert derive_jurisdiction("EP123", SimpleNamespace(jurisdiction="us")) == "US"
    assert derive_jurisdiction("EP123", None) == "EP"


def test_classify_source_authority_splits_authoritative_and_supporting() -> None:
    authoritative, supporting = classify_source_authority(
        ["epo_search", "bigquery", "uspto_odp", "pubchem"]
    )
    assert authoritative == ["epo_search", "uspto_odp"]
    assert supporting == ["bigquery", "pubchem"]


def test_collect_source_names_adds_dossier_and_derived_sources() -> None:
    detail = SimpleNamespace(sources=[SimpleNamespace(value="bigquery")])
    dossier = SimpleNamespace(source_name="uspto_odp")
    assert collect_source_names(
        detail=detail,
        dossier=dossier,
        has_ptab_proceedings=True,
        has_orange_book_listing=True,
        has_ep_register_context=False,
    ) == ["bigquery", "uspto_odp", "ptab", "orange_book"]


def test_build_patent_gate_failures_reports_missing_file_wrapper_for_us_blocker() -> None:
    record = PatentEvidenceRecord(
        patent_id="US123",
        jurisdiction="US",
        has_claims_text=True,
        has_family_context=True,
        has_us_prosecution_context=True,
        has_us_file_wrapper_dossier=False,
        analysis_completed=True,
        claims_analyzed_count=1,
        risk_level="high",
        doe_assessed=False,
        invalidity_assessed=False,
        critic_issue_severities=[],
        component_statuses=build_patent_component_statuses(
            patent_id="US123",
            jurisdiction="US",
            has_claims_text=True,
            has_family_context=True,
            has_authoritative_records=True,
            has_us_prosecution_context=True,
            has_us_file_wrapper_dossier=False,
            has_ep_register_context=False,
            has_ptab_proceedings=False,
            has_orange_book_listing=False,
            analysis_completed=True,
            analysis_failed=False,
            claims_analyzed_count=1,
            doe_assessed=False,
            invalidity_assessed=False,
        ),
    )
    assert build_patent_gate_failures(record) == [
        "missing_us_file_wrapper_dossier",
        "blocking_patent_missing_doe_assessment",
        "blocking_patent_missing_invalidity_assessment",
    ]
