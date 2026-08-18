"""Tests for the source-health downgrade rule in ``_determine_overall_risk``.

Historically the report's PDF coverage banner displayed a "Confidence impact:
Moderate" label when sources failed, but the risk rollup itself ignored
source health on the CLEAR path — so an FTO report could proudly say
"CLEAR" even though 30% of the search sources were down. That's misleading
to the attorney consuming the report.

The policy now says: if any queried source failed, the overall risk cannot
be CLEAR. The floor is LOW. MEDIUM / HIGH results earned by real analyses
are never downgraded — we only clamp the "nothing interesting was found"
branch where the absence of risk could easily be an absence of data.
"""

from __future__ import annotations

from praviar_pipeline.models.analysis import RiskLevel
from praviar_pipeline.models.report import (
    SourceHealth,
    SourceHealthEntry,
    SourceStatus,
)
from praviar_pipeline.pipeline.report.policy import _determine_overall_risk


def _health_with_failure() -> SourceHealth:
    """One primary OK, one secondary FAILED — ``any_failed`` is True."""
    return SourceHealth(
        entries=[
            SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=100),
            SourceHealthEntry(
                source="bigquery",
                status=SourceStatus.FAILED,
                error_message="timeout",
            ),
        ]
    )


def _health_all_ok() -> SourceHealth:
    return SourceHealth(
        entries=[
            SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=50),
            SourceHealthEntry(source="bigquery", status=SourceStatus.OK, patent_count=20),
        ]
    )


class TestSourceHealthDowngrade:
    def test_any_failed_plus_all_clear_downgrades_to_low(self) -> None:
        """Sources failed + zero risky analyses -> LOW, not CLEAR."""
        health = _health_with_failure()
        risk = _determine_overall_risk([], [], source_health=health)
        assert risk == RiskLevel.LOW

    def test_any_failed_plus_high_analysis_stays_high(self, sample_high_risk_analysis) -> None:
        """A real HIGH risk is never clamped by source health — we must not
        hide a risk the analyst actually found just because a data source
        was down. The source-health clamp only affects the CLEAR branch."""
        health = _health_with_failure()
        risk = _determine_overall_risk([sample_high_risk_analysis], [], source_health=health)
        assert risk == RiskLevel.HIGH

    def test_any_failed_plus_medium_analysis_stays_medium(self, sample_analysis) -> None:
        """MEDIUM risks are also preserved — no downgrade OR upgrade."""
        health = _health_with_failure()
        risk = _determine_overall_risk([sample_analysis], [], source_health=health)
        assert risk == RiskLevel.MEDIUM

    def test_all_sources_ok_plus_all_clear_stays_clear(self) -> None:
        """When nothing failed, CLEAR is still the right answer."""
        health = _health_all_ok()
        risk = _determine_overall_risk([], [], source_health=health)
        assert risk == RiskLevel.CLEAR

    def test_regulatory_failure_does_not_clamp_clear_patent_risk(self) -> None:
        """Regulatory enrichment failures do not imply missing patent coverage."""
        health = SourceHealth(
            entries=[
                SourceHealthEntry(source="pubchem_sdq", status=SourceStatus.OK, patent_count=100),
                SourceHealthEntry(
                    source="pte_data",
                    status=SourceStatus.FAILED,
                    error_message="PTE source unavailable",
                ),
                SourceHealthEntry(
                    source="orange_book",
                    status=SourceStatus.FAILED,
                    error_message="Orange Book unavailable",
                ),
            ]
        )
        risk = _determine_overall_risk([], [], source_health=health)
        assert risk == RiskLevel.CLEAR

    def test_source_health_none_legacy_caller_no_downgrade(self) -> None:
        """Callers that don't pass source_health at all (legacy) get the
        pre-existing behaviour — no clamp, CLEAR is allowed."""
        risk = _determine_overall_risk([], [], source_health=None)
        assert risk == RiskLevel.CLEAR

    def test_empty_entries_behaves_like_none(self) -> None:
        """``SourceHealth(entries=[])`` means nothing was queried at all.
        Treat identically to ``None`` — no signal, no clamp."""
        health = SourceHealth(entries=[])
        risk = _determine_overall_risk([], [], source_health=health)
        assert risk == RiskLevel.CLEAR
