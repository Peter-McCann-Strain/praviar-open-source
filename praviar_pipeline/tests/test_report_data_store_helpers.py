"""Direct tests for report_data_store indexing and formatter helpers."""

from __future__ import annotations

from datetime import date

from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.drawing import DrawingStructure, PatentDrawingAnalysis
from praviar_pipeline.models.equivalents import DoEAssessment, EstoppelResult, FWRAssessment
from praviar_pipeline.models.invalidity import (
    InvalidityAssessment,
    PriorArtReference,
    PTABProceeding,
    PTABResult,
)
from praviar_pipeline.pipeline.report_data_store_formatters import (
    format_analysis_text,
    format_doe_text,
    format_drawing_evidence_text,
    format_invalidity_text,
    format_patent_details_text,
    format_prior_art_references_text,
)
from praviar_pipeline.pipeline.report_data_store_indexing import (
    index_analyses,
    index_doe_assessments,
    index_invalidity_assessments,
    index_patent_details,
)


def _analysis(patent_id: str = "US10000001B2") -> PatentAnalysis:
    return PatentAnalysis(
        patent_id=patent_id,
        title="Test Patent",
        assignee="Acme Corp",
        expiry_date=date(2030, 6, 15),
        risk_level=RiskLevel.HIGH,
        risk_summary="HIGH risk — covers compound class",
        claims_analyzed=[
            ClaimAnalysis(
                claim_number=1,
                claim_type="independent",
                overall_status=ElementStatus.MET,
                elements=[
                    ClaimElement(
                        element_number=1,
                        element_text="compound of Formula I",
                        status=ElementStatus.MET,
                        reasoning="Falls within genus",
                    ),
                ],
            ),
        ],
    )


def test_index_analyses_groups_by_patent_id():
    analyses = [_analysis(), _analysis(patent_id="US10000002B2")]
    indexed = index_analyses(analyses)

    assert set(indexed) == {"US10000001B2", "US10000002B2"}
    assert indexed["US10000001B2"].title == "Test Patent"


def test_index_doe_assessments_groups_multiple_entries():
    assessments = [
        DoEAssessment(
            patent_id="US10000001B2",
            claim_number=1,
            element_number=1,
            element_text="compound",
            estoppel=EstoppelResult(estoppel_applies=False),
            fwr=FWRAssessment(
                same_function=True,
                function_reasoning="same",
                same_way=True,
                way_reasoning="same",
                same_result=True,
                result_reasoning="same",
                equivalent=True,
            ),
            overall_equivalent=True,
            confidence=0.9,
            confidence_band="HIGH",
        ),
        DoEAssessment(
            patent_id="US10000001B2",
            claim_number=2,
            element_number=1,
            element_text="salt",
            estoppel=EstoppelResult(estoppel_applies=False),
            fwr=FWRAssessment(
                same_function=False,
                function_reasoning="not same",
                same_way=False,
                way_reasoning="not same",
                same_result=False,
                result_reasoning="not same",
                equivalent=False,
            ),
            overall_equivalent=False,
            confidence=0.1,
            confidence_band="LOW",
        ),
    ]

    indexed = index_doe_assessments(assessments)
    assert len(indexed["US10000001B2"]) == 2


def test_index_invalidity_assessments_overwrites_by_patent_id():
    first = InvalidityAssessment(
        patent_id="US10000001B2",
        overall_invalidity_strength="weak",
        reasoning="first",
    )
    second = InvalidityAssessment(
        patent_id="US10000001B2",
        overall_invalidity_strength="strong",
        reasoning="second",
    )

    indexed = index_invalidity_assessments([first, second])
    assert indexed["US10000001B2"].overall_invalidity_strength == "strong"


class _FakePatentHit:
    def __init__(self, patent_id: str) -> None:
        self.patent_id = patent_id

    def model_dump(self, *, mode: str) -> dict:
        return {"patent_id": self.patent_id, "mode": mode}


def test_index_patent_details_skips_unrelated_hits():
    indexed = index_patent_details(
        [_FakePatentHit("US10000001B2"), _FakePatentHit("US10000002B2")],
        {"US10000001B2"},
    )

    assert indexed["US10000001B2"] == {"patent_id": "US10000001B2", "mode": "json"}
    assert "US10000002B2" not in indexed


def test_format_analysis_text_populated():
    text = format_analysis_text(_analysis(), "US10000001B2")
    assert "Patent: US10000001B2" in text
    assert "Claims Analyzed: 1" in text
    assert "Element 1: MET" in text


def test_format_doe_text_populated():
    assessment = DoEAssessment(
        patent_id="US10000001B2",
        claim_number=1,
        element_number=1,
        element_text="compound",
        estoppel=EstoppelResult(
            estoppel_applies=True,
            file_wrapper_available=True,
            surrendered_scope="narrowed genus",
        ),
        fwr=FWRAssessment(
            same_function=True,
            function_reasoning="same",
            same_way=True,
            way_reasoning="same",
            same_result=True,
            result_reasoning="same",
            equivalent=True,
        ),
        overall_equivalent=False,
        confidence=0.4,
        confidence_band="MODERATE",
    )

    text = format_doe_text([assessment], "US10000001B2")
    assert "DoE Assessment for US10000001B2" in text
    assert "Estoppel Applies: True" in text
    assert "Surrendered Scope: narrowed genus" in text


def test_format_invalidity_text_populated():
    invalidity = InvalidityAssessment(
        patent_id="US10000001B2",
        claim_numbers=[1],
        ptab=PTABResult(
            has_been_challenged=True,
            proceedings=[
                PTABProceeding(
                    proceeding_number="IPR2021-00555",
                    type="IPR",
                    status="Instituted",
                    outcome_summary="Challenge pending",
                ),
            ],
        ),
        prior_art=[
            PriorArtReference(
                reference_id="ref-001",
                title="Important Prior Art Paper",
                publication_date=date(2015, 5, 1),
                doi="10.1234/test",
            ),
        ],
        overall_invalidity_strength="strong",
        reasoning="Prior art found",
        confidence=0.6,
        confidence_band="HIGH",
    )

    text = format_invalidity_text(invalidity, "US10000001B2")
    assert "Invalidity Assessment for US10000001B2" in text
    assert "Prior Art References (1)" in text
    assert "PTAB Proceedings" in text


def test_format_patent_details_text_populated():
    detail = {
        "ptab_proceedings": [
            {
                "proceeding_type": "IPR",
                "proceeding_number": "IPR2021-00555",
                "status": "Instituted",
                "petitioner": "Acme",
            },
        ],
        "orange_book_info": {
            "is_listed": True,
            "nda_numbers": ["NDA123"],
            "product_names": ["Drug A", "Drug B"],
        },
        "patent_term_info": {
            "adjusted_expiry": "2030-06-15",
            "pta_days": 12,
            "maintenance_fee_status": "paid",
            "terminal_disclaimer": True,
            "td_linked_patent": "US9999999B2",
        },
        "assignments": [
            {
                "conveyance": "Assignment",
                "recorded_date": "2024-01-01",
                "assignor": "OldCo",
                "assignee": "NewCo",
            },
        ],
        "legal_events": [
            {
                "date": "2024-02-01",
                "description": "Maintenance fee paid",
            },
        ],
    }

    text = format_patent_details_text(detail, "US10000001B2")
    assert "Patent Details for US10000001B2" in text
    assert "Orange Book: Listed" in text
    assert "Patent Term: expires 2030-06-15" in text
    assert "Ownership History" in text
    assert "Legal Events (1 total)" in text


def test_format_drawing_evidence_text_populated():
    drawing = PatentDrawingAnalysis(
        patent_id="US10000001B2",
        structures_found=2,
        highest_tanimoto=0.812,
        structures=[
            DrawingStructure(
                patent_id="US10000001B2",
                page_number=1,
                structure_index=1,
                tanimoto_to_target=0.812,
                is_substructure_of_target=True,
            ),
        ],
    )

    text = format_drawing_evidence_text(drawing, "US10000001B2")
    assert "Drawing Analysis for US10000001B2" in text
    assert "Highest Tanimoto Similarity: 0.812" in text
    assert "Structure 1" in text


def test_format_prior_art_references_text_populated():
    invalidity = InvalidityAssessment(
        patent_id="US10000001B2",
        prior_art=[
            PriorArtReference(
                reference_id="ref-001",
                title="Important Prior Art Paper",
                reference_type="journal_article",
                publication_date=date(2015, 5, 1),
                doi="10.1234/test",
                url="https://example.com/test",
                anticipation_score=0.7,
                obviousness_score=0.5,
            ),
        ],
        overall_invalidity_strength="moderate",
        reasoning="Prior art found",
        confidence=0.6,
    )

    text = format_prior_art_references_text(invalidity, "US10000001B2")
    assert "Prior Art References for US10000001B2" in text
    assert "Important Prior Art Paper" in text
    assert "DOI: 10.1234/test" in text
