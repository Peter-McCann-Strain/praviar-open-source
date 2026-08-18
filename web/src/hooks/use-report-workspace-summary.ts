"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { useAuthToken } from "@/hooks/use-auth-token";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import {
  getDemoAnalysis,
  getDemoReport,
  isDemoAnalysisId,
  isSeedDemoAnalysisId,
} from "@/lib/demo-data";
import { authScopedQueryKey } from "@/lib/query-keys";
import { useClientReady } from "@/hooks/use-client-ready";

export interface ReportWorkspaceEvidenceQuery {
  kind: "compound" | "modality" | "jurisdiction" | "search_strategy" | "risk";
  query: string;
  rationale: string;
  source: string;
}

export interface ReportWorkspaceMonitorSeedDefaults {
  analysis_id: string;
  compound_name: string;
  compound_smiles: string;
  schedule: "daily" | "weekly" | "monthly";
  source_report_id: string;
  source_trust_mode: "explorer" | "counsel" | "monitor" | string;
  requires_manual_input: boolean;
  missing_fields: string[];
}

export interface ReportWorkspaceEvidenceProviderCapability {
  provider_name: string;
  provider_class:
    | "report_derived"
    | "public_open"
    | "licensed_overlay"
    | string;
  provider_status?: "active" | "caution_only" | "declared_only" | string;
  live_retrieval_supported: boolean;
  modality_coverage: string[];
  jurisdiction_coverage: string[];
  governance_note: string;
}

export interface ReportWorkspaceEvidenceScope {
  mode: "report_evidence" | string;
  external_live_retrieval: boolean;
  comment_routing_available: boolean;
  sources_considered: string[];
  governed_note: string;
  provider_capabilities: ReportWorkspaceEvidenceProviderCapability[];
  providers: ReportWorkspaceEvidenceProviderCapability[];
  hybrid_evidence_ready: boolean;
}

export interface ReportWorkspaceSummaryResponse {
  analysis_id: string;
  report_id: string;
  trust_mode: "explorer" | "counsel" | "monitor";
  target_jurisdictions?: string[];
  jurisdiction_matrix?: Array<Record<string, unknown>>;
  report_summary: {
    overall_risk: string;
    blocking_patents_count: number;
    total_patents_found: number;
    executive_summary: string;
  };
  capability_metadata: Record<string, unknown>;
  suggested_evidence_queries: ReportWorkspaceEvidenceQuery[];
  monitor_seed_defaults: ReportWorkspaceMonitorSeedDefaults;
  routing_profile: Record<string, unknown>;
  opinion_readiness: Record<string, unknown>;
  data_coverage: Record<string, unknown>;
  source_convergence: Record<string, unknown>;
  uncertainty_register: Record<string, unknown>[];
  evidence_scope: ReportWorkspaceEvidenceScope;
}

function buildDemoWorkspaceSummary(
  analysisId: string,
): ReportWorkspaceSummaryResponse {
  const analysis = getDemoAnalysis(analysisId);
  const report = getDemoReport(analysisId);

  if (!analysis || !report) {
    throw new Error("Demo workspace summary not available.");
  }

  const sourceEntries = report.source_health?.entries ?? [];
  const failedSources = sourceEntries.filter((entry) => entry.status !== "ok");
  const sourcesConsidered =
    report.search_sources_used.length > 0
      ? report.search_sources_used
      : sourceEntries.map((entry) => entry.source);
  const targetJurisdictions = Array.from(
    new Set(
      (report.jurisdiction_decisions ?? [])
        .map((decision) =>
          typeof decision === "object" && decision && "jurisdiction" in decision
            ? String(decision.jurisdiction)
            : "",
        )
        .filter(Boolean),
    ),
  );
  const exportReady =
    analysis.overall_risk !== "high" && !analysis.flagged_for_review;
  const providerCapabilities: ReportWorkspaceEvidenceProviderCapability[] = [
    {
      provider_name: "Report-derived evidence layer",
      provider_class: "report_derived",
      provider_status: "active",
      live_retrieval_supported: false,
      modality_coverage: ["small_molecule"],
      jurisdiction_coverage:
        targetJurisdictions.length > 0 ? targetJurisdictions : ["US"],
      governance_note:
        "Search and AI responses are constrained to evidence already captured in this demo report.",
    },
  ];

  return {
    analysis_id: analysisId,
    report_id: report.report_id,
    trust_mode: "counsel",
    target_jurisdictions: targetJurisdictions,
    jurisdiction_matrix: (report.jurisdiction_decisions ?? []).map(
      (decision) => ({
        ...decision,
      }),
    ),
    report_summary: {
      overall_risk: report.risk_summary.overall_risk,
      blocking_patents_count: report.risk_summary.blocking_patents_count,
      total_patents_found: report.total_patents_found,
      executive_summary: report.risk_summary.executive_summary,
    },
    capability_metadata: {
      source: "demo_report_fixture",
      capability_profile: "report_grounded",
      trust_mode: "counsel",
    },
    suggested_evidence_queries: [
      {
        kind: "compound",
        query: `${report.compound.name} patent claims`,
        rationale: "Open the strongest report-grounded compound evidence.",
        source: "compound.name",
      },
      {
        kind: "risk",
        query: "blocking claim elements",
        rationale: "Focus AI answers on material risk findings and caveats.",
        source: "risk_summary",
      },
    ],
    monitor_seed_defaults: {
      analysis_id: analysisId,
      compound_name: analysis.compound_name,
      compound_smiles: analysis.compound_smiles,
      schedule: "weekly",
      source_report_id: report.report_id,
      source_trust_mode: "counsel",
      requires_manual_input: false,
      missing_fields: [],
    },
    routing_profile: {
      modality: "small_molecule",
      evidence_path: "report_grounded_demo",
    },
    opinion_readiness: {
      export_ready: exportReady,
      summary: exportReady
        ? "Demo packet is ready for a counsel-formatted export."
        : "Counsel review must complete before downstream reliance.",
      jurisdictions_blocking_export: exportReady
        ? []
        : targetJurisdictions.length > 0
          ? targetJurisdictions
          : ["US"],
    },
    data_coverage: {
      sources_considered: sourcesConsidered.length,
      failed_sources: failedSources.length,
      coverage_pct: 80,
    },
    source_convergence: {
      score: 0.8,
      summary: "Demo evidence remains report-grounded with explicit gaps.",
    },
    uncertainty_register: failedSources.map((entry) => ({
      source: entry.source,
      severity: "coverage_gap",
      summary:
        entry.error_message ?? `${entry.source} coverage was incomplete.`,
    })),
    evidence_scope: {
      mode: "report_evidence",
      external_live_retrieval: false,
      comment_routing_available: true,
      sources_considered: sourcesConsidered,
      governed_note:
        "Demo workspace uses report-derived evidence only; external live retrieval is disabled.",
      provider_capabilities: providerCapabilities,
      providers: providerCapabilities,
      hybrid_evidence_ready: false,
    },
  };
}

export function useReportWorkspaceSummary(analysisId: string | null) {
  const token = useAuthToken();
  const clientReady = useClientReady();
  const isLocalDemoEnvironment = DEMO_MODE_ENABLED;
  const isDemoId = isDemoAnalysisId(analysisId);
  const waitForGeneratedDemoState =
    isLocalDemoEnvironment &&
    isDemoId &&
    !isSeedDemoAnalysisId(analysisId) &&
    !clientReady;
  const shouldUseLocalDemoSummary =
    isLocalDemoEnvironment && isDemoId && !waitForGeneratedDemoState;

  return useQuery({
    queryKey: authScopedQueryKey(
      ["reports", analysisId, "workspace-summary"] as const,
      token,
    ),
    queryFn: async ({ signal }) => {
      if (!analysisId) {
        throw new Error("Analysis ID is required");
      }

      if (shouldUseLocalDemoSummary) {
        return buildDemoWorkspaceSummary(analysisId);
      }

      return apiClient<ReportWorkspaceSummaryResponse>(
        `/reports/${analysisId}/workspace-summary`,
        {
          token: token || undefined,
          signal,
        },
      );
    },
    enabled:
      !!analysisId &&
      !waitForGeneratedDemoState &&
      (shouldUseLocalDemoSummary || !!token),
  });
}

export { buildDemoWorkspaceSummary };
