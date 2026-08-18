"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";
import { invalidateAuthScopedQueries } from "@/lib/query-keys";
import type { CheckpointState } from "@/stores/pipeline-store";

export type CheckpointDecision = "approve" | "reject" | "modify";

export interface CheckpointDecisionInput {
  checkpointId: string;
  checkpointType: CheckpointState["checkpoint_type"];
  decision: CheckpointDecision;
  note?: string;
  reviewPayloadSha256?: string;
}

export interface CheckpointDecisionResponse {
  id: string;
  analysis_id: string;
  checkpoint_id: string;
  checkpoint_type: CheckpointState["checkpoint_type"];
  decision: CheckpointDecision;
  note: string;
  reviewer_id: string;
  reviewed_at: string;
}

export function useSubmitCheckpointDecision(
  analysisId: string,
  token: string | null,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CheckpointDecisionInput) =>
      apiClient<CheckpointDecisionResponse>(
        `/analyses/${analysisId}/checkpoints/${encodeURIComponent(input.checkpointId)}/decision`,
        {
          method: "POST",
          body: JSON.stringify({
            checkpoint_type: input.checkpointType,
            decision: input.decision,
            note: input.note ?? "",
            review_payload_sha256: input.reviewPayloadSha256,
          }),
          token: token || undefined,
        },
      ),
    meta: { suppressGlobalErrorToast: true },
    onSuccess: () => {
      invalidateAuthScopedQueries(queryClient, ["analyses", analysisId], token);
    },
  });
}
