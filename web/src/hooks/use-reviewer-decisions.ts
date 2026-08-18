"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import {
  authScopedQueryKey,
  invalidateAuthScopedQueries,
} from "@/lib/query-keys";
import { logError } from "@/lib/error-logger";
import {
  createDemoReviewerDecision,
  getDemoReviewerDecisions,
  type ReviewerDecision,
  type ReviewerDecisionInput,
  type ReviewerDecisionListResponse,
} from "@/lib/demo-reviewer-decisions";

export type {
  Decision,
  FindingType,
  ReviewerDecision,
  ReviewerDecisionInput,
  ReviewerDecisionListResponse,
} from "@/lib/demo-reviewer-decisions";

const decisionsKey = (analysisId: string, token: string | null) =>
  authScopedQueryKey(["reviewer-decisions", analysisId] as const, token);

export function useReviewerDecisions(analysisId: string, token: string | null) {
  return useQuery<ReviewerDecisionListResponse>({
    queryKey: decisionsKey(analysisId, token),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(getDemoReviewerDecisions(analysisId));
      }
      return apiClient<ReviewerDecisionListResponse>(
        `/analyses/${analysisId}/decisions`,
        { token: token || undefined, signal },
      );
    },
    enabled: !!analysisId && (DEMO_MODE_ENABLED || !!token),
    initialData: DEMO_MODE_ENABLED
      ? getDemoReviewerDecisions(analysisId)
      : undefined,
  });
}

export function useCreateReviewerDecision(
  analysisId: string,
  token: string | null,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ReviewerDecisionInput) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(createDemoReviewerDecision(analysisId, input));
      }
      return apiClient<ReviewerDecision>(`/analyses/${analysisId}/decisions`, {
        method: "POST",
        body: JSON.stringify({
          finding_type: input.finding_type,
          finding_ref: input.finding_ref,
          decision: input.decision,
          note: input.note ?? "",
          edited_text: input.edited_text ?? "",
        }),
        token: token || undefined,
      });
    },
    meta: { suppressGlobalErrorToast: true },
    onError: (err) => {
      logError(err, {
        source: "useCreateReviewerDecision",
        extra: { analysisId },
      });
    },
    onSuccess: () => {
      invalidateAuthScopedQueries(
        queryClient,
        ["reviewer-decisions", analysisId],
        token,
      );
      invalidateAuthScopedQueries(
        queryClient,
        ["analyses", analysisId, "review-status"],
        token,
      );
      invalidateAuthScopedQueries(queryClient, ["analyses", analysisId], token);
    },
  });
}
