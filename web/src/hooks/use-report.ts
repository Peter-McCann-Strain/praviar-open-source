"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import {
  getDemoReport,
  getDemoReportSummary,
  isDemoAnalysisId,
  isSeedDemoAnalysisId,
} from "@/lib/demo-data";
import { authScopedQueryKey } from "@/lib/query-keys";
import {
  ftoReportResponseSchema,
  reportSummaryResponseSchema,
  validateApiResponse,
} from "@/lib/validators";
import { useClientReady } from "@/hooks/use-client-ready";
import type { FTOReport, RiskLevel } from "@praviar/shared-types";

export function useReport(analysisId: string, token: string | null) {
  const clientReady = useClientReady();
  const isLocalDemoEnvironment = DEMO_MODE_ENABLED;
  const isDemoId = isDemoAnalysisId(analysisId);
  const waitForGeneratedDemoState =
    isLocalDemoEnvironment &&
    isDemoId &&
    !isSeedDemoAnalysisId(analysisId) &&
    !clientReady;
  const shouldUseLocalDemoReport =
    isLocalDemoEnvironment && isDemoId && !waitForGeneratedDemoState;
  const initialDemoReport = shouldUseLocalDemoReport
    ? (getDemoReport(analysisId) ?? undefined)
    : undefined;

  return useQuery({
    queryKey: authScopedQueryKey(["reports", analysisId] as const, token),
    queryFn: async ({ signal }) => {
      if (shouldUseLocalDemoReport) {
        const report = getDemoReport(analysisId);
        if (!report) {
          throw new Error("Report not available.");
        }
        return report;
      }
      const data = await apiClient<FTOReport>(`/reports/${analysisId}`, {
        token: token || undefined,
        signal,
      });
      validateApiResponse(
        ftoReportResponseSchema,
        data,
        `/reports/${analysisId}`,
      );
      return data;
    },
    enabled:
      !!analysisId &&
      !waitForGeneratedDemoState &&
      (shouldUseLocalDemoReport || !!token),
    initialData: initialDemoReport,
    staleTime: Infinity,
    // apiClient already owns bounded retries for 429/5xx responses. A second
    // query-layer retry delays terminal 403/404 states and leaves dead links
    // looking like an indefinite loading screen.
    retry: false,
  });
}

interface ReportSummary {
  overall_risk: RiskLevel | null;
  blocking_patents_count: number | null;
  total_patents_found: number;
  executive_summary: string;
  risk_ratings_restricted: boolean;
}

export function useReportSummary(analysisId: string, token: string | null) {
  const clientReady = useClientReady();
  const isLocalDemoEnvironment = DEMO_MODE_ENABLED;
  const isDemoId = isDemoAnalysisId(analysisId);
  const waitForGeneratedDemoState =
    isLocalDemoEnvironment &&
    isDemoId &&
    !isSeedDemoAnalysisId(analysisId) &&
    !clientReady;
  const shouldUseLocalDemoReport =
    isLocalDemoEnvironment && isDemoId && !waitForGeneratedDemoState;
  const initialDemoSummary = shouldUseLocalDemoReport
    ? (getDemoReportSummary(analysisId) ?? undefined)
    : undefined;

  return useQuery({
    queryKey: authScopedQueryKey(
      ["reports", analysisId, "summary"] as const,
      token,
    ),
    queryFn: async ({ signal }): Promise<ReportSummary> => {
      if (shouldUseLocalDemoReport) {
        const summary = getDemoReportSummary(analysisId);
        if (!summary) {
          throw new Error("Report summary not available.");
        }
        return summary;
      }
      const data = await apiClient<ReportSummary>(
        `/reports/${analysisId}/summary`,
        { token: token || undefined, signal },
      );
      validateApiResponse(
        reportSummaryResponseSchema,
        data,
        `/reports/${analysisId}/summary`,
      );
      return data;
    },
    enabled:
      !!analysisId &&
      !waitForGeneratedDemoState &&
      (shouldUseLocalDemoReport || !!token),
    initialData: initialDemoSummary,
    retry: false,
  });
}
