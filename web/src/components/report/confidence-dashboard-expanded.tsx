import { Clock } from "lucide-react";

import type { ConfidenceDashboardState } from "./confidence-dashboard-helpers";
import { ConfidenceDashboardCoverage } from "./confidence-dashboard-coverage";
import { ConfidenceDashboardKnownGaps } from "./confidence-dashboard-known-gaps";
import { ConfidenceDashboardSourceMatrix } from "./confidence-dashboard-source-matrix";

interface ConfidenceDashboardExpandedProps {
  state: ConfidenceDashboardState;
}

export function ConfidenceDashboardExpanded({
  state,
}: ConfidenceDashboardExpandedProps) {
  return (
    <div className="px-4 pb-4 space-y-4 border-t border-[var(--border-subtle)]">
      <ConfidenceDashboardCoverage
        sourceCoverage={state.sourceCoverage}
        coverageLabel={state.coverageLabel}
        decisionEvidenceLabel={state.decisionEvidenceLabel}
      />

      <ConfidenceDashboardSourceMatrix
        displayedSources={state.displayedSources}
      />

      <div className="flex items-center gap-2">
        <Clock className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
        <span className="text-xs text-[var(--text-secondary)]">
          Report generated {state.displayDateLabel}
        </span>
      </div>

      <ConfidenceDashboardKnownGaps
        decisionWarnings={state.decisionWarnings}
        failedSources={state.failedSources}
        limitations={state.limitations}
        coverageSummary={state.coverageSummary}
      />
    </div>
  );
}
