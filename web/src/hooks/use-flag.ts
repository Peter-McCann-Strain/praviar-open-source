"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { invalidateAuthScopedQueries } from "@/lib/query-keys";

export function useFlagAnalysis(token: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (analysisId: string) =>
      apiClient<{ flagged_for_review: boolean }>(
        `/analyses/${analysisId}/flag`,
        {
          method: "POST",
          token: token || undefined,
        },
      ),
    onSuccess: (_, analysisId) => {
      invalidateAuthScopedQueries(queryClient, ["analyses", analysisId], token);
      invalidateAuthScopedQueries(queryClient, ["analyses"], token);
    },
  });
}
