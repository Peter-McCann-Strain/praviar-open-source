"""Customer-visible verdict helpers derived from deterministic decisioning."""

from __future__ import annotations

from praviar_pipeline.models.analysis import RiskLevel
from praviar_pipeline.models.report_decisioning import ClearanceOutcome

_DECISION_RISK_LEVEL = {
    ClearanceOutcome.CLEAR: RiskLevel.CLEAR,
    ClearanceOutcome.UNCLEAR: RiskLevel.MEDIUM,
    ClearanceOutcome.BLOCKED: RiskLevel.HIGH,
}


def governed_risk_level(report) -> RiskLevel:
    """Map the governed clearance outcome to the legacy display risk scale."""
    return _DECISION_RISK_LEVEL[report.clearance_decision.decision]


def governed_decision_label(report) -> str:
    """Return the governed matter verdict for customer-visible headings."""
    return str(report.clearance_decision.decision.value).upper()


def governed_blocking_count(report) -> int:
    """Return blocker count from the governed decision audit."""
    return len(report.clearance_decision.decision_audit.claim_program_summary.blocking_patent_ids)


def governed_executive_summary(report) -> str:
    """Render deterministic matter prose from governed fields only."""
    count = governed_blocking_count(report)
    analyzed = report.risk_summary.total_patents_analyzed
    return (
        f"Clearance decision: {governed_decision_label(report)}. "
        f"{count} blocking patent{'s' if count != 1 else ''} identified "
        f"from {analyzed} analyzed."
    )


def governed_patent_posture(report, patent_id: str) -> str:
    """Return a target-scope patent posture without reusing upstream risk labels."""
    decision_scope = set(getattr(report.decision_scope, "jurisdictions", []) or [])
    decisions = [
        decision
        for decision in getattr(report, "claim_program_decisions", []) or []
        if decision.patent_id == patent_id
    ]
    if (
        decisions
        and decision_scope
        and all(decision.jurisdiction not in decision_scope for decision in decisions)
    ):
        return "SUPPORTING ONLY"
    summary = report.clearance_decision.decision_audit.claim_program_summary
    if patent_id in summary.blocking_patent_ids:
        return "BLOCKING"
    if not decisions or any(not decision.evidence_sufficient for decision in decisions):
        return "UNRESOLVED"
    return "NON-BLOCKING"


def governed_patent_basis(report, patent_id: str) -> str:
    """Return compact governed claims/gaps explaining a patent posture."""
    summary = report.clearance_decision.decision_audit.claim_program_summary
    blocking_claims = [
        claim_id for claim_id in summary.blocking_claim_ids if claim_id.startswith(f"{patent_id}#")
    ]
    if blocking_claims:
        return "Governed blockers: " + ", ".join(blocking_claims)
    decisions = [
        decision
        for decision in getattr(report, "claim_program_decisions", []) or []
        if decision.patent_id == patent_id
    ]
    missing = sorted(
        {component for decision in decisions for component in decision.missing_components}
    )
    if missing:
        return "Unresolved record: " + ", ".join(missing[:8])
    return "No governed blocking claim identified in the target scope."
