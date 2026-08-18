import { formatDuration, truncate } from "@/lib/utils";
import type { AnalysisListItem } from "@/types/api";

export type StatusFilter =
  | "all"
  | "running"
  | "completed"
  | "failed"
  | "pending"
  | "cancelled";
export type RiskFilter = "all" | "high" | "medium" | "low" | "clear";
export type SortOption = "date-desc" | "date-asc" | "risk-desc" | "risk-asc";

const RISK_ORDER: Record<string, number> = {
  high: 3,
  medium: 2,
  low: 1,
  clear: 0,
};

export function formatAnalysisDate(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function buildStatusCounts(analyses: AnalysisListItem[]) {
  const counts: Record<string, number> = {
    all: analyses.length,
    pending: 0,
    running: 0,
    completed: 0,
    failed: 0,
    cancelled: 0,
  };
  for (const analysis of analyses) {
    counts[analysis.status] = (counts[analysis.status] || 0) + 1;
  }
  return counts;
}

export function getFilteredAnalyses(
  analyses: AnalysisListItem[],
  searchQuery: string,
  statusFilter: StatusFilter,
  riskFilter: RiskFilter,
  sortBy: SortOption,
) {
  const query = searchQuery.toLowerCase().trim();

  return analyses
    .filter((analysis) => {
      if (statusFilter !== "all" && analysis.status !== statusFilter) {
        return false;
      }

      if (riskFilter !== "all" && analysis.overall_risk !== riskFilter) {
        return false;
      }

      if (!query) {
        return true;
      }

      const matchesName = analysis.compound_name.toLowerCase().includes(query);
      const matchesSmiles = analysis.compound_smiles
        .toLowerCase()
        .includes(query);
      const matchesId = analysis.id.toLowerCase().includes(query);
      return matchesName || matchesSmiles || matchesId;
    })
    .sort((first, second) => {
      switch (sortBy) {
        case "date-asc":
          return (
            new Date(first.created_at).getTime() -
            new Date(second.created_at).getTime()
          );
        case "risk-desc":
          return (
            (RISK_ORDER[second.overall_risk ?? ""] ?? -1) -
            (RISK_ORDER[first.overall_risk ?? ""] ?? -1)
          );
        case "risk-asc":
          return (
            (RISK_ORDER[first.overall_risk ?? ""] ?? -1) -
            (RISK_ORDER[second.overall_risk ?? ""] ?? -1)
          );
        case "date-desc":
        default:
          return (
            new Date(second.created_at).getTime() -
            new Date(first.created_at).getTime()
          );
      }
    });
}

export function getAnalysisDuration(
  durationSeconds: number | null | undefined,
) {
  return durationSeconds == null ? "..." : formatDuration(durationSeconds);
}

export function getAnalysisSmiles(smiles: string) {
  return truncate(smiles, 32);
}
