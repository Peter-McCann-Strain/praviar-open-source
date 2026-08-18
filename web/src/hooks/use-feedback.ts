"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { invalidateAuthScopedQueries } from "@/lib/query-keys";

interface CorrectionPayload {
  patent_id: string;
  field: string;
  original_value: string;
  corrected_value: string;
  notes: string;
}

export interface FeedbackPayload {
  analysis_id: string;
  overall_accuracy: number;
  risk_level_correct: boolean;
  corrected_risk?: string;
  corrections: CorrectionPayload[];
}

interface FeedbackResponse {
  id: string;
  analysis_id: string;
  created_at: string;
}

export function useSubmitFeedback(token: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: FeedbackPayload) =>
      apiClient<FeedbackResponse>("/feedback", {
        method: "POST",
        body: JSON.stringify(data),
        token: token || undefined,
      }),
    onSuccess: (_, variables) => {
      invalidateAuthScopedQueries(
        queryClient,
        ["analyses", variables.analysis_id],
        token,
      );
    },
  });
}
