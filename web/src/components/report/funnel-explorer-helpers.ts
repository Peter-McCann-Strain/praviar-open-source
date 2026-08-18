import {
  Brain,
  Database,
  Filter,
  Microscope,
  Search,
  type LucideIcon,
} from "lucide-react";
import type {
  AnalysisAuditEntry,
  PipelineAuditTrail,
  SearchFunnelEntry,
  TriageAuditEntry,
} from "@praviar/shared-types";

export type FunnelStage =
  | "discovered"
  | "hard_filter"
  | "ranked"
  | "triaged"
  | "analyzed";

export interface FunnelStageConfig {
  id: FunnelStage;
  label: string;
  icon: LucideIcon;
  color: string;
  bgColor: string;
  borderColor: string;
}

export const FUNNEL_STAGES: FunnelStageConfig[] = [
  {
    id: "discovered",
    label: "Discovered",
    icon: Database,
    color: "text-info",
    bgColor: "bg-info/10",
    borderColor: "border-info/20",
  },
  {
    id: "hard_filter",
    label: "Hard Filtered",
    icon: Filter,
    color: "text-warning",
    bgColor: "bg-warning/10",
    borderColor: "border-warning/20",
  },
  {
    id: "ranked",
    label: "Ranked",
    icon: Search,
    color: "text-info",
    bgColor: "bg-info/10",
    borderColor: "border-info/20",
  },
  {
    id: "triaged",
    label: "AI Triaged",
    icon: Brain,
    color: "text-brand-primary",
    bgColor: "bg-brand-primary/10",
    borderColor: "border-brand-primary/20",
  },
  {
    id: "analyzed",
    label: "Deep Analyzed",
    icon: Microscope,
    color: "text-success",
    bgColor: "bg-success/10",
    borderColor: "border-success/20",
  },
] as const;

export function getFunnelStageCounts(
  audit: PipelineAuditTrail,
): Record<FunnelStage, number> {
  return {
    discovered: audit.total_patents_discovered,
    hard_filter: audit.patents_after_hard_filter,
    ranked: audit.patents_after_ranking,
    triaged: audit.patents_after_triage,
    analyzed: audit.patents_analyzed,
  };
}

export function searchPatentInFunnel(
  audit: PipelineAuditTrail,
  query: string,
): { searchResult: string; selectedStage?: FunnelStage } {
  const normalized = query.trim().toUpperCase();

  if (!normalized) {
    return { searchResult: "" };
  }

  const funnelEntry = audit.search_funnel.find(
    (entry) => entry.patent_id.toUpperCase() === normalized,
  );
  if (funnelEntry) {
    if (!funnelEntry.passed_hard_filter) {
      return {
        searchResult: `${normalized} was removed at hard filter stage. Reason: ${funnelEntry.filter_reason || "unknown"}`,
        selectedStage: "hard_filter",
      };
    }
    if (!funnelEntry.included_in_triage) {
      return {
        searchResult: `${normalized} passed hard filters (score: ${funnelEntry.composite_score?.toFixed(2) ?? "?"}) but was not included in triage (below ranking cutoff).`,
        selectedStage: "ranked",
      };
    }
  }

  const triageEntry = audit.triage_audit.find(
    (entry) => entry.patent_id.toUpperCase() === normalized,
  );
  if (triageEntry && !triageEntry.passed_triage) {
    return {
      searchResult: `${normalized} was rejected at triage. Relevance: ${triageEntry.relevance}, Confidence: ${(triageEntry.confidence * 100).toFixed(0)}%. Reason: ${triageEntry.reason}`,
      selectedStage: "triaged",
    };
  }

  const analysisEntry = audit.analysis_audit.find(
    (entry) => entry.patent_id.toUpperCase() === normalized,
  );
  if (analysisEntry) {
    return {
      searchResult: `${normalized} reached claim analysis. Selected: ${analysisEntry.selected_for_analysis ? "Yes" : "No"}, Risk: ${analysisEntry.risk_level ?? "not analyzed"}`,
      selectedStage: "analyzed",
    };
  }

  return { searchResult: `${normalized} not found in pipeline funnel data.` };
}

export type { AnalysisAuditEntry, SearchFunnelEntry, TriageAuditEntry };
