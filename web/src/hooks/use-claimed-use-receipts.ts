"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import { logError } from "@/lib/error-logger";
import {
  authScopedQueryKey,
  invalidateAuthScopedQueries,
} from "@/lib/query-keys";
import {
  claimedUseReceiptListResponseSchema,
  claimedUseReceiptResponseSchema,
  validateApiResponse,
} from "@/lib/validators";
import type {
  ClaimedUseReceipt,
  ClaimedUseReceiptIssueRequest,
  ClaimedUseReceiptListResponse,
  ClaimedUseReceiptRevokeRequest,
} from "@/types/api";

export function useClaimedUseReceipts(
  analysisId: string,
  token: string | null,
  enabled = true,
) {
  return useQuery<ClaimedUseReceiptListResponse>({
    queryKey: authScopedQueryKey(
      ["claimed-use-receipts", analysisId] as const,
      token,
    ),
    queryFn: async ({ signal }) => {
      const path = `/analyses/${analysisId}/claimed-use-receipts`;
      const data = await apiClient<ClaimedUseReceiptListResponse>(path, {
        token: token || undefined,
        signal,
      });
      return validateApiResponse(
        claimedUseReceiptListResponseSchema,
        data,
        path,
      );
    },
    enabled: Boolean(analysisId && token && enabled && !DEMO_MODE_ENABLED),
  });
}

export function useIssueClaimedUseReceipt(
  analysisId: string,
  token: string | null,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: ClaimedUseReceiptIssueRequest) => {
      const path = `/analyses/${analysisId}/claimed-use-receipts`;
      const data = await apiClient<ClaimedUseReceipt>(path, {
        method: "POST",
        body: JSON.stringify(input),
        token: token || undefined,
      });
      return validateApiResponse(claimedUseReceiptResponseSchema, data, path);
    },
    meta: { suppressGlobalErrorToast: true },
    onError: (error) => {
      logError(error, {
        source: "useIssueClaimedUseReceipt",
        extra: { analysisId },
      });
    },
    onSuccess: () => {
      invalidateAuthScopedQueries(
        queryClient,
        ["claimed-use-receipts", analysisId],
        token,
      );
      invalidateAuthScopedQueries(
        queryClient,
        ["analyses", analysisId, "review-status"],
        token,
      );
    },
  });
}

export function useRevokeClaimedUseReceipt(
  analysisId: string,
  token: string | null,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      receiptId,
      reason,
    }: {
      receiptId: string;
      reason: ClaimedUseReceiptRevokeRequest["reason"];
    }) => {
      const path = `/analyses/${analysisId}/claimed-use-receipts/${receiptId}/revoke`;
      const data = await apiClient<ClaimedUseReceipt>(path, {
        method: "POST",
        body: JSON.stringify({ reason }),
        token: token || undefined,
      });
      return validateApiResponse(claimedUseReceiptResponseSchema, data, path);
    },
    meta: { suppressGlobalErrorToast: true },
    onError: (error) => {
      logError(error, {
        source: "useRevokeClaimedUseReceipt",
        extra: { analysisId },
      });
    },
    onSuccess: () => {
      invalidateAuthScopedQueries(
        queryClient,
        ["claimed-use-receipts", analysisId],
        token,
      );
      invalidateAuthScopedQueries(
        queryClient,
        ["analyses", analysisId, "review-status"],
        token,
      );
    },
  });
}
