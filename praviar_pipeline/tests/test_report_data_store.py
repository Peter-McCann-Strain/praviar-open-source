"""Tests for ReportDataStore — in-memory data index for report generation."""

from __future__ import annotations

from datetime import date

from praviar_pipeline.models.analysis import (
    ClaimAnalysis,
    ClaimElement,
    ElementStatus,
    PatentAnalysis,
    RiskLevel,
)
from praviar_pipeline.models.compound import ResolvedCompound
from praviar_pipeline.models.report_common import SourceHealth, SourceHealthEntry, SourceStatus
from praviar_pipeline.models.verification import VerificationResult
from praviar_pipeline.pipeline.report_data_store import ReportDataStore


def _make_compound() -> ResolvedCompound:
    return ResolvedCompound(
        name="osimertinib",
        canonical_smiles="C=CC(=O)Nc1cc(OC)c(Nc2ccc(F)c(Cl)c2)nc1",
        cas_numbers=["1421373-65-0"],
        original_input="osimertinib",
        input_type="name",
        compound_type="small_molecule",
    )


def _make_analysis(
    patent_id: str = "US10000001B2",
    risk: RiskLevel = RiskLevel.HIGH,
    assignee: str = "Acme Corp",
) -> PatentAnalysis:
    return PatentAnalysis(
        patent_id=patent_id,
        title="Test Patent",
        assignee=assignee,
        expiry_date=date(2030, 6, 15),
        risk_level=risk,
        risk_summary=f"{risk.value} risk — covers compound class",
        claims_analyzed=[
            ClaimAnalysis(
                claim_number=1,
                claim_type="independent",
                overall_status=ElementStatus.MET,
                preamble="A compound of Formula I",
                elements=[
                    ClaimElement(
                        element_number=1,
                        element_text="compound of Formula I",
                        status=ElementStatus.MET,
                        reasoning="Target falls within Markush genus",
                    ),
                    ClaimElement(
                        element_number=2,
                        element_text="therapeutically effective amount",
                        status=ElementStatus.MET,
                        reasoning="Proposed dose within claimed range",
                    ),
                ],
            ),
        ],
    )


def _make_store(**kwargs) -> ReportDataStore:
    defaults = {
        "compound": _make_compound(),
        "analyses": [_make_analysis()],
        "doe_assessments": [],
        "invalidity_assessments": [],
        "verification": VerificationResult(),
        "overall_risk": RiskLevel.HIGH,
    }
    defaults.update(kwargs)
    return ReportDataStore(**defaults)


class TestLookups:
    def test_get_analysis_found(self):
        store = _make_store()
        result = store.get_analysis("US10000001B2")
        assert result is not None
        assert result.risk_level == RiskLevel.HIGH

    def test_get_analysis_not_found(self):
        store = _make_store()
        assert store.get_analysis("US9999999A1") is None

    def test_all_patent_ids(self):
        store = _make_store()
        assert store.all_patent_ids() == {"US10000001B2"}

    def test_patents_by_risk(self):
        analyses = [
            _make_analysis("US1", RiskLevel.HIGH),
            _make_analysis("US2", RiskLevel.MEDIUM),
            _make_analysis("US3", RiskLevel.CLEAR),
        ]
        store = _make_store(analyses=analyses)
        assert len(store.patents_by_risk(RiskLevel.HIGH)) == 1
        assert len(store.patents_by_risk(RiskLevel.CLEAR)) == 1
        assert len(store.patents_by_risk(RiskLevel.LOW)) == 0

    def test_blocking_count(self):
        analyses = [
            _make_analysis("US1", RiskLevel.HIGH),
            _make_analysis("US2", RiskLevel.MEDIUM),
            _make_analysis("US3", RiskLevel.LOW),
        ]
        store = _make_store(analyses=analyses)
        assert store.blocking_count() == 2

    def test_assignee_distribution(self):
        analyses = [
            _make_analysis("US1", assignee="Pfizer"),
            _make_analysis("US2", assignee="Pfizer"),
            _make_analysis("US3", assignee="Novartis"),
        ]
        store = _make_store(analyses=analyses)
        dist = store.assignee_distribution()
        assert len(dist["Pfizer"]) == 2
        assert len(dist["Novartis"]) == 1


class TestFormatting:
    def test_format_analysis(self):
        store = _make_store()
        text = store.format_analysis("US10000001B2")
        assert "US10000001B2" in text
        assert "HIGH" in text
        assert "Acme Corp" in text
        assert "Element 1" in text
        assert "MET" in text

    def test_format_analysis_not_found(self):
        store = _make_store()
        text = store.format_analysis("USNOTFOUND")
        assert "No analysis found" in text

    def test_format_portfolio_summary(self):
        store = _make_store()
        text = store.format_portfolio_summary()
        assert "osimertinib" in text
        assert "HIGH" in text
        assert "US10000001B2" in text
        assert "Acme Corp" in text

    def test_format_portfolio_summary_with_cas(self):
        store = _make_store()
        text = store.format_portfolio_summary()
        assert "1421373-65-0" in text

    def test_format_portfolio_summary_lists_all_source_health_entries(self):
        store = _make_store(
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
            )
        )

        text = store.format_portfolio_summary()

        assert "Configured source requests: 1 of 2 completed" in text
        assert "zero_hit_source: Successful | 0 patents" in text
        assert (
            "failed_source: Unavailable | 0 patents | Provider request failed; "
            "protected diagnostics are available to operators."
        ) in text
        assert "timeout" not in text
        assert "do not infer coverage from patent-hit sources alone" in text

    def test_anthropic_tool_text_never_contains_provider_query_credentials(self):
        store = _make_store(
            source_health=SourceHealth(
                entries=[
                    SourceHealthEntry(
                        source="openalex",
                        status=SourceStatus.FAILED,
                        error_message=(
                            "401 for https://api.openalex.org/works?api_key=SUPERSECRET&q=aspirin"
                        ),
                    )
                ]
            )
        )

        text = store.format_scope_and_reliance()

        assert "Provider request failed" in text
        assert "SUPERSECRET" not in text
        assert "api_key=" not in text

    def test_format_scope_and_reliance_blocks_overclaims(self):
        analysis_without_claims = _make_analysis("EP20000001A1", RiskLevel.MEDIUM)
        analysis_without_claims.claims_analyzed = []
        store = _make_store(
            analyses=[_make_analysis(), analysis_without_claims],
            source_health=SourceHealth(
                entries=[
                    SourceHealthEntry(
                        source="surechembl",
                        status=SourceStatus.OK,
                        patent_count=0,
                    )
                ]
            ),
        )

        text = store.format_scope_and_reliance()

        assert "Reliance posture: AI-assisted screening, not legal advice." in text
        assert "Privilege/work-product marking allowed: false" in text
        assert "Permitted wording: 'no records returned by [source]'" in text
        assert "US: 1 analyzed patent(s)" in text
        assert "EP: 1 analyzed patent(s)" in text
        assert "EP20000001A1: claim text/element analysis not recorded" in text

    def test_format_doe_empty(self):
        store = _make_store()
        text = store.format_doe("US10000001B2")
        assert "No Doctrine" in text

    def test_format_invalidity_empty(self):
        store = _make_store()
        text = store.format_invalidity("US10000001B2")
        assert "No invalidity" in text

    def test_format_patent_details_empty(self):
        store = _make_store()
        text = store.format_patent_details("US10000001B2")
        assert "No enrichment" in text

    def test_format_drawing_evidence_empty(self):
        store = _make_store()
        text = store.format_drawing_evidence("US10000001B2")
        assert "No drawing" in text

    def test_format_critic_findings_none(self):
        store = _make_store()
        text = store.format_critic_findings()
        assert "No critic report" in text

    def test_format_prior_art_empty(self):
        store = _make_store()
        text = store.format_prior_art_references("US10000001B2")
        assert "No prior art" in text

    def test_format_analysis_truncated(self):
        """Verify output is capped at 8000 chars."""
        store = _make_store()
        text = store.format_analysis("US10000001B2")
        assert len(text) <= 8000
