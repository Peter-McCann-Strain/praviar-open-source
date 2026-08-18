"""ReportDataStore — in-memory index over all pipeline data for report generation."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.models.analysis import PatentAnalysis, RiskLevel
from praviar_pipeline.output_safety import (
    safe_processing_error_detail,
    safe_source_error_detail,
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


def _source_status_value(entry) -> str:
    status = getattr(entry, "status", "")
    return str(getattr(status, "value", status))


def _source_status_label(entry) -> str:
    status = _source_status_value(entry)
    if status == "ok":
        return "Successful"
    if status == "failed":
        return "Unavailable"
    if status == "not_configured":
        return "Not configured"
    if status == "skipped":
        return "Skipped"
    return status or "Unknown"


def _source_status_detail(entry) -> str:
    pieces = [_source_status_label(entry)]
    count = int(getattr(entry, "patent_count", 0) or 0)
    pieces.append(f"{count:,} patents")
    detail = safe_source_error_detail(
        getattr(entry, "error_message", ""),
        status=getattr(entry, "status", ""),
    )
    if detail:
        pieces.append(detail)
    return " | ".join(pieces)


_PATENT_JURISDICTION_RE = re.compile(r"^([A-Z]{2})(?:[/\d])")


def _normalize_jurisdiction(value: object) -> str:
    code = str(value or "").strip().upper()
    if code == "GB":
        return "UK"
    return code if re.fullmatch(r"[A-Z]{2}", code) else ""


def _jurisdiction_from_patent_id(value: object) -> str:
    match = _PATENT_JURISDICTION_RE.match(str(value or "").strip().upper())
    return _normalize_jurisdiction(match.group(1)) if match else ""


if TYPE_CHECKING:
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.critic import CriticReport
    from praviar_pipeline.models.drawing import DrawingEvidenceStore, PatentDrawingAnalysis
    from praviar_pipeline.models.equivalents import DoEAssessment
    from praviar_pipeline.models.invalidity import InvalidityAssessment
    from praviar_pipeline.models.report import ActionItem, AnalysisFailure, SourceHealth
    from praviar_pipeline.models.verification import VerificationResult

logger = structlog.get_logger()


class ReportDataStore:
    """In-memory index over all pipeline outputs for O(1) lookup by patent_id.

    Used by ReportDataToolkit and ReportVerificationToolkit to provide
    tool-based data access to LLMs during report generation.
    """

    def __init__(
        self,
        compound: ResolvedCompound,
        analyses: list[PatentAnalysis],
        doe_assessments: list[DoEAssessment],
        invalidity_assessments: list[InvalidityAssessment],
        verification: VerificationResult,
        patent_hits: list | None = None,
        drawing_evidence: DrawingEvidenceStore | None = None,
        source_health: SourceHealth | None = None,
        analysis_failures: list[AnalysisFailure] | None = None,
        critic_report: CriticReport | None = None,
        action_items: list[ActionItem] | None = None,
        overall_risk: RiskLevel = RiskLevel.CLEAR,
        prospective_blocking_patent_ids: set[str] | None = None,
    ) -> None:
        self.compound = compound
        self.overall_risk = overall_risk
        self.verification = verification
        self.source_health = source_health
        self.critic_report = critic_report
        self.analysis_failures = analysis_failures or []
        self.action_items = action_items or []
        self._prospective_blocking_patent_ids = (
            set(prospective_blocking_patent_ids)
            if prospective_blocking_patent_ids is not None
            else None
        )
        self._drawing_evidence = drawing_evidence

        self._analyses = index_analyses(analyses)
        self._doe = index_doe_assessments(doe_assessments)
        self._invalidity = index_invalidity_assessments(invalidity_assessments)
        self._patent_details = index_patent_details(patent_hits, set(self._analyses.keys()))

        logger.debug(
            "report_data_store_built",
            analyses=len(self._analyses),
            doe=sum(len(v) for v in self._doe.values()),
            invalidity=len(self._invalidity),
            patent_details=len(self._patent_details),
            has_drawings=drawing_evidence is not None,
            has_critic=critic_report is not None,
        )

    # ── Indexed lookups ──────────────────────────────────────────────────

    def get_analysis(self, patent_id: str) -> PatentAnalysis | None:
        return self._analyses.get(patent_id)

    def get_doe(self, patent_id: str) -> list[DoEAssessment]:
        return self._doe.get(patent_id, [])

    def get_invalidity(self, patent_id: str) -> InvalidityAssessment | None:
        return self._invalidity.get(patent_id)

    def get_patent_detail(self, patent_id: str) -> dict | None:
        return self._patent_details.get(patent_id)

    def get_drawing(self, patent_id: str) -> PatentDrawingAnalysis | None:
        if self._drawing_evidence is None:
            return None
        return self._drawing_evidence.get(patent_id)

    # ── Aggregation ──────────────────────────────────────────────────────

    def all_analyses(self) -> list[PatentAnalysis]:
        return list(self._analyses.values())

    def all_patent_ids(self) -> set[str]:
        failed_ids = {f.patent_id for f in self.analysis_failures}
        return set(self._analyses.keys()) | failed_ids

    def patents_by_risk(self, level: RiskLevel) -> list[PatentAnalysis]:
        return [a for a in self._analyses.values() if a.risk_level == level]

    def blocking_count(self) -> int:
        if self._prospective_blocking_patent_ids is not None:
            return len(self._prospective_blocking_patent_ids)
        return sum(
            1 for a in self._analyses.values() if a.risk_level in (RiskLevel.HIGH, RiskLevel.MEDIUM)
        )

    def assignee_distribution(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = defaultdict(list)
        for a in self._analyses.values():
            result[a.assignee].append(a.patent_id)
        return dict(result)

    def jurisdiction_counts(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for analysis in self._analyses.values():
            code = _normalize_jurisdiction(getattr(analysis, "jurisdiction", ""))
            if not code:
                code = _jurisdiction_from_patent_id(analysis.patent_id)
            if code:
                counts[code] += 1
        for patent_id, detail in self._patent_details.items():
            code = _normalize_jurisdiction(detail.get("jurisdiction", ""))
            if not code:
                code = _jurisdiction_from_patent_id(detail.get("patent_id", patent_id))
            if code and code not in counts:
                counts[code] += 0
        return dict(sorted(counts.items()))

    # ── Formatting for tools ─────────────────────────────────────────────

    def format_analysis(self, patent_id: str) -> str:
        """Format a PatentAnalysis as human-readable text for tool output."""
        return format_analysis_text(self.get_analysis(patent_id), patent_id)

    def format_doe(self, patent_id: str) -> str:
        """Format DoE assessments for a patent."""
        return format_doe_text(self.get_doe(patent_id), patent_id)

    def format_invalidity(self, patent_id: str) -> str:
        """Format InvalidityAssessment for a patent."""
        return format_invalidity_text(self.get_invalidity(patent_id), patent_id)

    def format_patent_details(self, patent_id: str) -> str:
        """Format enrichment data for a patent (PTAB, OB, term, assignments)."""
        return format_patent_details_text(self.get_patent_detail(patent_id), patent_id)

    def format_drawing_evidence(self, patent_id: str) -> str:
        """Format drawing/OCSR analysis for a patent."""
        return format_drawing_evidence_text(self.get_drawing(patent_id), patent_id)

    def format_portfolio_summary(self) -> str:
        """Format full portfolio overview for the executive summary tool."""
        analyses = self.all_analyses()
        high = self.patents_by_risk(RiskLevel.HIGH)
        medium = self.patents_by_risk(RiskLevel.MEDIUM)
        low = self.patents_by_risk(RiskLevel.LOW)
        clear = self.patents_by_risk(RiskLevel.CLEAR)

        lines = [
            f"Compound: {self.compound.name}",
            f"SMILES: {self.compound.canonical_smiles}",
        ]
        if self.compound.cas_numbers:
            lines.append(f"CAS: {', '.join(self.compound.cas_numbers[:3])}")
        if hasattr(self.compound, "compound_type") and self.compound.compound_type:
            lines.append(f"Type: {self.compound.compound_type}")

        lines.extend(
            [
                f"\nUpstream Claim-Coverage Screen: {self.overall_risk.value.upper()}",
                f"Total Patents Analyzed: {len(analyses)}",
                f"Verified Prospective Blockers: {self.blocking_count()}",
                f"  HIGH coverage screens: {len(high)}",
                f"  MEDIUM coverage screens: {len(medium)}",
                f"  LOW coverage screens: {len(low)}",
                f"  CLEAR coverage screens: {len(clear)}",
                f"Analysis Date: {datetime.now(UTC).strftime('%Y-%m-%d')}",
            ]
        )

        # Patents by risk
        if high:
            lines.append("\nHIGH Risk Patents:")
            for a in high:
                lines.append(f"  - {a.patent_id} ({a.assignee}): {a.risk_summary[:200]}")
        if medium:
            lines.append("\nMEDIUM Risk Patents:")
            for a in medium:
                lines.append(f"  - {a.patent_id} ({a.assignee}): {a.risk_summary[:200]}")

        # Assignee distribution
        dist = self.assignee_distribution()
        if dist:
            lines.append(f"\nAssignee Distribution ({len(dist)} unique):")
            for assignee, pids in sorted(dist.items(), key=lambda x: -len(x[1]))[:10]:
                lines.append(f"  - {assignee}: {len(pids)} patents ({', '.join(pids[:5])})")

        # Verification
        if self.verification:
            status = "All passed" if self.verification.all_passed else "Issues found"
            lines.append(f"\nVerification: {status}")

        # Source health
        source_entries = (
            list(self.source_health.entries)
            if self.source_health is not None and hasattr(self.source_health, "entries")
            else []
        )
        if source_entries:
            successful = sum(1 for entry in source_entries if _source_status_value(entry) == "ok")
            unavailable = sum(
                1
                for entry in source_entries
                if _source_status_value(entry) in {"failed", "not_configured"}
            )
            skipped = sum(1 for entry in source_entries if _source_status_value(entry) == "skipped")
            lines.extend(
                [
                    "\nSource Health:",
                    (
                        f"  Configured source requests: {successful} of "
                        f"{len(source_entries)} completed "
                        f"({unavailable} unavailable/not configured, {skipped} skipped)"
                    ),
                    (
                        "  Scope rule: source and jurisdiction claims must be based "
                        "on this telemetry; do not infer coverage from patent-hit "
                        "sources alone."
                    ),
                ]
            )
            for entry in source_entries:
                lines.append(
                    f"  - {getattr(entry, 'source', 'unknown')}: {_source_status_detail(entry)}"
                )
        else:
            lines.append(
                "\nSource Health: not recorded. Do not infer database or "
                "jurisdiction coverage from patent-hit sources alone."
            )

        # Data limitations
        if self.analysis_failures:
            lines.append(f"\nAnalysis Failures: {len(self.analysis_failures)}")
            for f in self.analysis_failures[:5]:
                lines.append(f"  - {f.patent_id}: {safe_processing_error_detail(f.error_message)}")

        # Action items
        if self.action_items:
            lines.append(f"\nAction Items ({len(self.action_items)}):")
            for item in self.action_items:
                lines.append(
                    f"  - [{item.priority.value.upper()}] {item.action_type.value}: "
                    f"{item.description[:200]}"
                )

        # Critic findings
        if self.critic_report:
            lines.append(f"\nCritic Quality Score: {self.critic_report.overall_quality_score}")
            if hasattr(self.critic_report, "findings") and self.critic_report.findings:
                lines.append(f"Critic Findings ({len(self.critic_report.findings)}):")
                for finding in self.critic_report.findings[:5]:
                    lines.append(
                        f"  - [{finding.severity}] {finding.issue_type}: "
                        f"{finding.description[:200]}"
                    )

        return "\n".join(lines)[:12000]

    def format_scope_and_reliance(self) -> str:
        """Return structured guardrails for source, jurisdiction, and reliance claims."""

        lines = [
            "Report Scope and Reliance Guardrails",
            "Reliance posture: AI-assisted screening, not legal advice.",
            (
                "Privilege/work-product marking allowed: false unless separately "
                "recorded by export metadata."
            ),
            (
                "Coverage rule: do not state that a source, database, or jurisdiction "
                "was searched/covered unless listed below with recorded telemetry."
            ),
        ]

        source_entries = (
            list(self.source_health.entries)
            if self.source_health is not None and hasattr(self.source_health, "entries")
            else []
        )
        lines.append("\nSource entries:")
        if source_entries:
            for entry in source_entries:
                lines.append(
                    f"  - {getattr(entry, 'source', 'unknown')}: {_source_status_detail(entry)}"
                )
        else:
            lines.append("  - Source-health telemetry not recorded.")

        zero_result_sources = [
            getattr(entry, "source", "unknown")
            for entry in source_entries
            if _source_status_value(entry) == "ok"
            and int(getattr(entry, "patent_count", 0) or 0) == 0
        ]
        lines.append("\nNegative-search guardrail:")
        if zero_result_sources:
            lines.append(
                "  Sources with completed zero-result telemetry: " + ", ".join(zero_result_sources)
            )
            lines.append(
                "  Permitted wording: 'no records returned by [source]'. "
                "Do not convert this into 'no blocking patents' unless analyzed "
                "evidence independently supports that conclusion."
            )
        else:
            lines.append("  No completed zero-result source telemetry recorded.")

        counts = self.jurisdiction_counts()
        lines.append("\nRecorded jurisdiction signals:")
        if counts:
            for jurisdiction, count in counts.items():
                lines.append(f"  - {jurisdiction}: {count} analyzed patent(s)")
        else:
            lines.append("  - No jurisdiction signals recorded.")

        lines.append("\nClaim text coverage:")
        for analysis in self._analyses.values():
            element_count = sum(len(claim.elements) for claim in analysis.claims_analyzed)
            if element_count:
                lines.append(
                    f"  - {analysis.patent_id}: element analysis recorded "
                    f"({element_count} element(s)); use recorded statuses only."
                )
            else:
                lines.append(
                    f"  - {analysis.patent_id}: claim text/element analysis not "
                    "recorded; do not provide element-by-element conclusions."
                )

        return "\n".join(lines)[:12000]

    def format_prior_art_references(self, patent_id: str) -> str:
        """Format prior art references for bibliography building."""
        return format_prior_art_references_text(self.get_invalidity(patent_id), patent_id)

    def format_critic_findings(self) -> str:
        """Format critic report for QA integration."""
        if self.critic_report is None:
            return "No critic report available."

        lines = [
            "Critic Report:",
            f"Quality Score: {self.critic_report.overall_quality_score}",
        ]

        if hasattr(self.critic_report, "findings") and self.critic_report.findings:
            lines.append(f"\nFindings ({len(self.critic_report.findings)}):")
            for f in self.critic_report.findings:
                # For risk_claim_mismatch findings, omit the description — it contains
                # FTO risk level language that the LLM echoes into sections (e.g.,
                # "HIGH element coverage" becomes "HIGH risk" in the report, contradicting
                # the canonical table).  The section prompt's RISK LEVEL LOCK and the
                # canonical table in the system prompt are the authoritative source.
                if f.issue_type == "risk_claim_mismatch":
                    desc = (
                        "Element coverage assessment differs from FTO risk conclusion. "
                        "Refer to canonical risk table."
                    )
                else:
                    desc = f.description[:300]
                lines.append(f"  [{f.severity}] {f.issue_type} — Patent: {f.patent_id} — {desc}")

        if self.critic_report.portfolio_level_observations:
            lines.append("\nPortfolio Observations:")
            for obs in self.critic_report.portfolio_level_observations[:5]:
                lines.append(f"  - {obs[:200]}")

        return "\n".join(lines)[:8000]
