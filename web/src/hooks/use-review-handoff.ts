"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";
import { useAuthToken } from "@/hooks/use-auth-token";
import { logError } from "@/lib/error-logger";
import { invalidateAuthScopedQueries } from "@/lib/query-keys";
import type { AnalysisReviewStatusResponse } from "@/hooks/use-analysis-review-status";

export interface ReviewHandoffResponse {
  comment_id: string;
  created_at?: string | null;
  review_status: AnalysisReviewStatusResponse;
  escalated_to_review: boolean;
  target_type: "analysis" | "patent" | "claim";
  target_id: string;
}

export interface ReviewHandoffInput {
  body: string;
  review_note?: string;
  target_type: "analysis" | "patent" | "claim";
  target_id: string;
  mentions?: string[];
  promote_to_under_review?: boolean;
}

export function useReviewHandoff(
  analysisId: string,
  tokenOverride?: string | null,
) {
  const authToken = useAuthToken();
  const token = tokenOverride ?? authToken;
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: ReviewHandoffInput) =>
      apiClient<ReviewHandoffResponse>(
        `/analyses/${analysisId}/review-handoff`,
        {
          method: "POST",
          body: JSON.stringify(input),
          token: token || undefined,
        },
      ),
    meta: { suppressGlobalErrorToast: true },
    onError: (err) => {
      logError(err, {
        source: "useReviewHandoff",
        extra: { analysisId },
      });
    },
    onSuccess: () => {
      invalidateAuthScopedQueries(queryClient, ["comments", analysisId], token);
      invalidateAuthScopedQueries(
        queryClient,
        ["analyses", analysisId, "review-status"],
        token,
      );
      invalidateAuthScopedQueries(queryClient, ["analyses", analysisId], token);
      invalidateAuthScopedQueries(queryClient, ["reports", analysisId], token);
      invalidateAuthScopedQueries(queryClient, ["review-queue"], token);
    },
  });
}
