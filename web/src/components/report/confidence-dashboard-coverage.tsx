import { cn } from "@/lib/utils";

interface ConfidenceDashboardCoverageProps {
  sourceCoverage: number;
  coverageLabel: string;
  decisionEvidenceLabel: string;
}

export function ConfidenceDashboardCoverage({
  sourceCoverage,
  coverageLabel,
  decisionEvidenceLabel,
}: ConfidenceDashboardCoverageProps) {
  return (
    <div className="pt-4">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-medium text-[var(--text-secondary)]">
          Search Coverage
        </span>
        <span className="text-xs tabular-nums text-[var(--text-tertiary)]">
          {coverageLabel}
          {decisionEvidenceLabel ? ` · ${decisionEvidenceLabel}` : ""}
        </span>
      </div>
      <div className="h-2 rounded-full bg-[var(--surface-muted)]">
        <div
          className={cn(
            "h-full rounded-full transition-all",
            sourceCoverage >= 0.8
              ? "bg-success"
              : sourceCoverage >= 0.5
                ? "bg-warning"
                : "bg-error",
          )}
          style={{ width: `${sourceCoverage * 100}%` }}
        />
      </div>
    </div>
  );
}
