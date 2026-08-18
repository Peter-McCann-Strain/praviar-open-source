from __future__ import annotations

from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.invalidity import (
    PriorArtReference,
    PTABProceeding,
    PTABResult,
)
from praviar_pipeline.pipeline.invalidity.prompting import build_invalidity_prompt


def test_build_invalidity_prompt_includes_context_sections(succinic_acid, mock_settings):
    analysis = PatentAnalysis(
        patent_id="US1234567B2",
        title="Fermentation process",
        assignee="Praviar",
        risk_level=RiskLevel.HIGH,
        risk_summary="Blocking",
        claims_analyzed=[
            ClaimAnalysis(
                claim_number=1,
                claim_type="independent",
                elements=[
                    ClaimElement(
                        element_number=1,
                        element_text="producing succinic acid",
                        status=ElementStatus.MET,
                        reasoning="Exact match",
                    )
                ],
                overall_status=ElementStatus.MET,
            )
        ],
    )

    prompt = build_invalidity_prompt(
        analysis=analysis,
        compound=succinic_acid,
        ptab=PTABResult(
            has_been_challenged=True,
            proceedings=[
                PTABProceeding(
                    proceeding_number="IPR2025-00001",
                    type="IPR",
                    status="Final Written Decision",
                    claims_reported_cancelled=[1],
                    claims_cancelled=[1],
                    final_written_decision_verified=True,
                    cancellation_certificate_verified=True,
                    review_and_appeal_posture="Appeal period exhausted",
                )
            ],
            all_claims_cancelled=[1],
        ),
        prior_art=[
            PriorArtReference(
                reference_id="ref-1",
                title="Succinic acid fermentation",
                publication_date=None,
                reference_type="journal_article",
                authors=["A. Author"],
                doi="10.1000/test",
                source_database="pubmed",
            )
        ],
        examiner_citations={"examiner": ["US7654321"], "applicant": ["WO2020123456"]},
        drawing_evidence=None,
    )

    assert "PTAB History" in prompt
    assert "Prosecution Citation History" in prompt
    assert "Scholarly Prior Art Found" in prompt
    assert "Claim Elements for Chart Construction" in prompt
    assert "Succinic acid fermentation" in prompt
    assert "US7654321" in prompt
