"""Focused tests for chat document section builders."""

from __future__ import annotations

from api.services.chat_document_sections import (
    build_patent_sections,
    build_report_sections,
    find_patent_analysis,
)


def _sample_report() -> dict:
    return {
        "compound": {
            "name": "aspirin",
            "canonical_smiles": "CC(=O)Oc1ccccc1C(O)=O",
            "pubchem_cid": 2244,
            "molecular_weight": 180.16,
        },
        "risk_summary": {
            "overall_risk": "medium",
            "blocking_patents_count": 1,
            "executive_summary": "Moderate FTO risk.",
            "key_risks": ["US92000001A1 blocks the scaffold"],
        },
        "patent_analyses": [
            {
                "patent_id": "US92000001A1",
                "title": "Aspirin analogs",
                "assignee": "Praviar",
                "risk_level": "high",
                "expiry_date": "2032-01-01",
                "risk_summary": "Core scaffold coverage.",
                "claims_analyzed": [
                    {
                        "claim_number": "1",
                        "claim_type": "independent",
                        "overall_status": "potentially infringed",
                        "confidence": 0.8,
                        "preamble": "A compound comprising...",
                        "reasoning": "The scaffold overlaps.",
                        "elements": [
                            {
                                "element_number": "1.a",
                                "status": "matched",
                                "element_text": "an acetylated salicylate core",
                                "evidence": "Matches aspirin scaffold.",
                                "reasoning": "Direct structural overlap.",
                            }
                        ],
                    }
                ],
                "design_around_suggestions": [
                    {"strategy": "salt form", "description": "Change the salt form."}
                ],
            }
        ],
        "patent_narratives": {"US92000001A1": "Narrative"},
        "doe_assessments": [
            {
                "patent_id": "US92000001A1",
                "overall_equivalent": True,
                "prosecution_estoppel_applies": False,
            }
        ],
        "invalidity_assessments": [
            {
                "patent_id": "US92000001A1",
                "overall_strength": "moderate",
                "prior_art": [{"title": "Prior art ref", "anticipation_score": 0.6}],
            }
        ],
        "analysis_failures": [
            {
                "patent_id": "US92000002A1",
                "error_type": "timeout",
                "error_message": "Analysis timed out",
            }
        ],
        "audit_trail": {
            "total_patents_discovered": 10,
            "patents_after_hard_filter": 5,
            "patents_after_ranking": 3,
            "patents_after_triage": 2,
            "patents_analyzed": 1,
        },
        "patent_details": {
            "US92000001A1": {"abstract": "Patent abstract", "legal_status": "active"}
        },
    }


def test_build_report_sections_includes_invalidity_failures_and_audit():
    sections = build_report_sections(_sample_report())
    combined = "\n".join(section["text"] for section in sections)

    assert "Invalidity Assessments" in combined
    assert "Analysis Failures" in combined
    assert "Pipeline Audit" in combined


def test_find_patent_analysis_returns_matching_patent():
    patent_analysis = find_patent_analysis(_sample_report(), "US92000001A1")

    assert patent_analysis is not None
    assert patent_analysis["title"] == "Aspirin analogs"


def test_build_patent_sections_includes_details_narrative_and_doe():
    report = _sample_report()
    patent_analysis = find_patent_analysis(report, "US92000001A1")
    assert patent_analysis is not None

    sections = build_patent_sections(
        patent_id="US92000001A1",
        report_data=report,
        patent_analysis=patent_analysis,
    )
    combined = "\n".join(section["text"] for section in sections)

    assert "Patent Details" in combined
    assert "AI Narrative" in combined
    assert "Doctrine of Equivalents" in combined
