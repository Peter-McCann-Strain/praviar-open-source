import { ChevronDown, ChevronRight, Database } from "lucide-react";

import { cn } from "@/lib/utils";

import type { ConfidenceBand } from "./confidence-dashboard-helpers";
import { BAND_STYLES } from "./confidence-dashboard-helpers";

interface ConfidenceDashboardSummaryProps {
  expanded: boolean;
  band: ConfidenceBand;
  summaryLabel: string;
  onToggle: () => void;
}

export function ConfidenceDashboardSummary({
  expanded,
  band,
  summaryLabel,
  onToggle,
}: ConfidenceDashboardSummaryProps) {
  const colors = BAND_STYLES[band];

  return (
    <button
      onClick={onToggle}
      className="w-full flex items-center gap-3 p-4 text-left hover:bg-[var(--surface-hover)] transition-colors"
      aria-expanded={expanded}
    >
      {expanded ? (
        <ChevronDown className="h-4 w-4 text-[var(--text-tertiary)] shrink-0" />
      ) : (
        <ChevronRight className="h-4 w-4 text-[var(--text-tertiary)] shrink-0" />
      )}

      <Database className="h-4 w-4 text-[var(--text-tertiary)]" />

      <span className="text-sm font-medium text-[var(--text-primary)]">
        Evidence Readiness
      </span>

      <span
        className={cn(
          "px-2 py-0.5 rounded-full text-xs font-bold border",
          colors.bg,
          colors.text,
          colors.border,
        )}
      >
        {band}
      </span>

      <span className="ml-auto text-xs text-[var(--text-tertiary)]">
        {summaryLabel}
      </span>
    </button>
  );
}
