import type { ClearanceDecision } from "./report-decision-helpers";
import { formatEvidenceScore } from "./report-decision-helpers";

interface DecisionEvidenceSummaryProps {
  decision: ClearanceDecision;
  failedSourceProviderCount?: number;
  sourceHealthProviderCount?: number;
}

export function DecisionEvidenceSummary({
  decision,
  failedSourceProviderCount = 0,
  sourceHealthProviderCount = 0,
}: DecisionEvidenceSummaryProps) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <div className="praviar-glass-chip rounded-lg px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
          Evidence-completeness score
        </p>
        <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          {formatEvidenceScore(decision.evidence_quality)}
        </p>
        <p className="mt-1 text-xs leading-4 text-[var(--text-secondary)]">
          Weighted decision-input coverage; provider health is reported
          separately.
        </p>
      </div>
      <div className="praviar-glass-chip rounded-lg px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
          Queried Search Sources
        </p>
        <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          {decision.decision_audit.successful_sources_count}/
          {decision.decision_audit.queried_sources_count} successful
        </p>
        {sourceHealthProviderCount > 0 ? (
          <p className="mt-1 text-xs leading-4 text-[var(--text-secondary)]">
            Source-health ledger: {failedSourceProviderCount} of{" "}
            {sourceHealthProviderCount} provider
            {sourceHealthProviderCount === 1 ? "" : "s"} failed.
          </p>
        ) : null}
      </div>
      <div className="praviar-glass-chip rounded-lg px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
          US With Prosecution
        </p>
        <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          {decision.decision_audit.us_patents_with_prosecution_context}/
          {decision.decision_audit.material_us_patents}
        </p>
      </div>
      <div className="praviar-glass-chip rounded-lg px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
          EP With Register
        </p>
        <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          {decision.decision_audit.ep_patents_with_register_context}/
          {decision.decision_audit.material_ep_patents}
        </p>
      </div>
    </div>
  );
}
