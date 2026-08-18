import { AlertTriangle } from "lucide-react";

import type { ConfidenceDashboardState } from "./confidence-dashboard-helpers";
import { sanitizeReportDiagnosticText } from "./report-diagnostic-copy";
import { SOURCE_LABELS } from "./summary-tab-helpers";

interface ConfidenceDashboardKnownGapsProps {
  decisionWarnings: ConfidenceDashboardState["decisionWarnings"];
  failedSources: ConfidenceDashboardState["failedSources"];
  limitations: ConfidenceDashboardState["limitations"];
  coverageSummary: ConfidenceDashboardState["coverageSummary"];
}

export function ConfidenceDashboardKnownGaps({
  decisionWarnings,
  failedSources,
  limitations,
  coverageSummary,
}: ConfidenceDashboardKnownGapsProps) {
  const hasCoverageSummaryGaps =
    (coverageSummary?.verification_gaps.length ?? 0) > 0 ||
    (coverageSummary?.patents_missing_claims.length ?? 0) > 0 ||
    (coverageSummary?.us_patents_missing_prosecution_context.length ?? 0) > 0 ||
    (coverageSummary?.ep_patents_missing_register_context.length ?? 0) > 0;

  if (
    decisionWarnings.length === 0 &&
    failedSources.length === 0 &&
    limitations.length === 0 &&
    !hasCoverageSummaryGaps
  ) {
    return null;
  }

  return (
    <div>
      <span className="text-xs font-medium text-[var(--text-secondary)] flex items-center gap-1.5 mb-2">
        <AlertTriangle className="h-3.5 w-3.5 text-warning" />
        Known Gaps
      </span>
      <ul className="space-y-1">
        {decisionWarnings.slice(0, 3).map((warning) => (
          <li
            key={warning}
            className="text-xs text-[var(--text-tertiary)] [overflow-wrap:anywhere]"
          >
            {sanitizeReportDiagnosticText(
              warning,
              "Decision warning available.",
            )}
          </li>
        ))}
        {failedSources.map((sourceEntry) => (
          <li
            key={sourceEntry.source}
            className="text-xs text-[var(--text-tertiary)] [overflow-wrap:anywhere]"
          >
            {SOURCE_LABELS[sourceEntry.source]?.label ?? sourceEntry.source}:{" "}
            {getSafeSourceGapLabel(sourceEntry.status)}
          </li>
        ))}
        {limitations.map((limitation, index) => (
          <li
            key={`${limitation.description}-${index}`}
            className="text-xs text-[var(--text-tertiary)] [overflow-wrap:anywhere]"
          >
            {sanitizeReportDiagnosticText(
              limitation.description,
              "A data limitation affected this report.",
            )}
          </li>
        ))}
        {coverageSummary?.verification_gaps.slice(0, 2).map((gap) => (
          <li
            key={gap}
            className="text-xs text-[var(--text-tertiary)] [overflow-wrap:anywhere]"
          >
            {sanitizeReportDiagnosticText(gap, "Verification gap available.")}
          </li>
        ))}
        {coverageSummary?.patents_missing_claims.slice(0, 2).map((patentId) => (
          <li key={patentId} className="text-xs text-[var(--text-tertiary)]">
            Missing claims text for {patentId}
          </li>
        ))}
        {coverageSummary?.us_patents_missing_prosecution_context
          .slice(0, 2)
          .map((patentId) => (
            <li key={patentId} className="text-xs text-[var(--text-tertiary)]">
              Missing prosecution context for {patentId}
            </li>
          ))}
        {coverageSummary?.ep_patents_missing_register_context
          .slice(0, 2)
          .map((patentId) => (
            <li key={patentId} className="text-xs text-[var(--text-tertiary)]">
              Missing EP register context for {patentId}
            </li>
          ))}
      </ul>
    </div>
  );
}

function getSafeSourceGapLabel(status: string): string {
  if (status === "not_configured") {
    return "not configured";
  }
  if (status === "skipped") {
    return "skipped";
  }
  return "unavailable";
}
