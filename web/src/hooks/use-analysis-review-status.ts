"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";
import { useAuthToken } from "@/hooks/use-auth-token";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import {
  getDemoAnalysis,
  isDemoAnalysisId,
  isSeedDemoAnalysisId,
} from "@/lib/demo-data";
import {
  authScopedQueryKey,
  invalidateAuthScopedQueries,
} from "@/lib/query-keys";
import { useClientReady } from "@/hooks/use-client-ready";

export type AnalysisReviewStatusValue =
  | "pending"
  | "under_review"
  | "approved"
  | "changes_requested";

export interface AnalysisReviewDecisionCounts {
  accept: number;
  reject: number;
  edit: number;
}

export interface AnalysisReviewStatusResponse {
  analysis_id: string;
  status: AnalysisReviewStatusValue;
  note: string | null;
  reviewer_name: string | null;
  reviewer_email: string | null;
  reviewed_at: string | null;
  updated_at: string;
  decision_counts: AnalysisReviewDecisionCounts;
  findings_total: number;
  findings_reviewed: number;
  completion_pct: number;
}

export interface UpdateAnalysisReviewStatusInput {
  status: AnalysisReviewStatusValue;
  note?: string;
}

export const analysisReviewStatusKey = (
  analysisId: string,
  token?: string | null,
) =>
  token === undefined
    ? (["analyses", analysisId, "review-status"] as const)
    : authScopedQueryKey(
        ["analyses", analysisId, "review-status"] as const,
        token,
      );

function buildDemoReviewStatus(
  analysisId: string,
): AnalysisReviewStatusResponse {
  const analysis = getDemoAnalysis(analysisId);

  if (!analysis) {
    throw new Error("Demo review status not available.");
  }

  if (analysis.status !== "completed") {
    return {
      analysis_id: analysisId,
      status: "pending",
      note: "Review opens after the report packet is complete.",
      reviewer_name: null,
      reviewer_email: null,
      reviewed_at: null,
      updated_at: analysis.updated_at,
      decision_counts: { accept: 0, reject: 0, edit: 0 },
      findings_total: 0,
      findings_reviewed: 0,
      completion_pct: 0,
    };
  }

  if (analysis.flagged_for_review || analysis.overall_risk === "high") {
    return {
      analysis_id: analysisId,
      status: "under_review",
      note: "Attorney review requested for material claim-chart findings.",
      reviewer_name: "Grace Hopper",
      reviewer_email: "grace@example.com",
      reviewed_at: null,
      updated_at: analysis.updated_at,
      decision_counts: { accept: 0, reject: 0, edit: 1 },
      findings_total: 5,
      findings_reviewed: 4,
      completion_pct: 80,
    };
  }

  return {
    analysis_id: analysisId,
    status: "approved",
    note: "Demo packet cleared for source-grounded export.",
    reviewer_name: "Ada Lovelace",
    reviewer_email: "ada@example.com",
    reviewed_at: analysis.updated_at,
    updated_at: analysis.updated_at,
    decision_counts: { accept: 3, reject: 0, edit: 0 },
    findings_total: 3,
    findings_reviewed: 3,
    completion_pct: 100,
  };
}

export function useAnalysisReviewStatus(analysisId: string) {
  const token = useAuthToken();
  const clientReady = useClientReady();
  const isLocalDemoEnvironment = DEMO_MODE_ENABLED;
  const isDemoId = isDemoAnalysisId(analysisId);
  const waitForGeneratedDemoState =
    isLocalDemoEnvironment &&
    isDemoId &&
    !isSeedDemoAnalysisId(analysisId) &&
    !clientReady;
  const shouldUseLocalDemoStatus =
    isLocalDemoEnvironment && isDemoId && !waitForGeneratedDemoState;

  return useQuery<AnalysisReviewStatusResponse>({
    queryKey: analysisReviewStatusKey(analysisId, token),
    queryFn: ({ signal }) => {
      if (shouldUseLocalDemoStatus) {
        return Promise.resolve(buildDemoReviewStatus(analysisId));
      }

      return apiClient<AnalysisReviewStatusResponse>(
        `/analyses/${analysisId}/review-status`,
        { token: token || undefined, signal },
      );
    },
    enabled:
      !!analysisId &&
      !waitForGeneratedDemoState &&
      (shouldUseLocalDemoStatus || !!token),
    // Poll every 30 s so changes submitted by reviewers in another tab
    // propagate without requiring the user to manually reload the page.
    refetchInterval: 30_000,
    // Background poll — a transient failure on a tick must not raise a global
    // error toast while the user is reading the report.
    meta: { suppressGlobalErrorToast: true },
  });
}

export function useUpdateAnalysisReviewStatus(analysisId: string) {
  const token = useAuthToken();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: UpdateAnalysisReviewStatusInput) => {
      const body = {
        status: input.status,
        ...(input.note !== undefined ? { note: input.note } : {}),
      };

      return apiClient<AnalysisReviewStatusResponse>(
        `/analyses/${analysisId}/review-status`,
        {
          method: "PUT",
          body: JSON.stringify(body),
          token: token || undefined,
        },
      );
    },
    onSuccess: (updatedStatus) => {
      queryClient.setQueryData(
        analysisReviewStatusKey(analysisId, token),
        updatedStatus,
      );
      invalidateAuthScopedQueries(
        queryClient,
        ["analyses", analysisId, "review-status"],
        token,
      );
      invalidateAuthScopedQueries(queryClient, ["analyses", analysisId], token);
      invalidateAuthScopedQueries(queryClient, ["analyses"], token);
      invalidateAuthScopedQueries(queryClient, ["reports", analysisId], token);
    },
  });
}

export { buildDemoReviewStatus };
