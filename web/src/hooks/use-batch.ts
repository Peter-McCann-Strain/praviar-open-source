/**
 * Batch analysis hooks — TanStack Query wrappers for batch API endpoints.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { useAuthToken } from "@/hooks/use-auth-token";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import { DEMO_ANALYSIS_ID } from "@/lib/demo-data";
import {
  authScopedQueryKey,
  invalidateAuthScopedQueries,
} from "@/lib/query-keys";

interface BatchResponse {
  id: string;
  name: string;
  total_compounds: number;
  completed_count: number;
  failed_count: number;
  status: string;
  analysis_ids: string[];
  created_at: string;
  updated_at: string;
}

interface BatchListResponse {
  items: BatchResponse[];
  total: number;
}

const DEMO_BATCHES: BatchResponse[] = [
  {
    id: "batch_demo_001",
    name: "Series A diligence screen",
    total_compounds: 12,
    completed_count: 9,
    failed_count: 0,
    status: "running",
    analysis_ids: [DEMO_ANALYSIS_ID, "ana_demo_002", "ana_demo_003"],
    created_at: "2026-04-10T08:30:00.000Z",
    updated_at: "2026-04-10T09:21:00.000Z",
  },
  {
    id: "batch_demo_002",
    name: "Platform acid portfolio",
    total_compounds: 18,
    completed_count: 18,
    failed_count: 1,
    status: "partial",
    analysis_ids: [DEMO_ANALYSIS_ID],
    created_at: "2026-04-02T13:45:00.000Z",
    updated_at: "2026-04-03T16:12:00.000Z",
  },
];

function buildDemoBatchList(page: number): BatchListResponse {
  const safePage = Math.max(1, page);
  const perPage = 20;
  const start = (safePage - 1) * perPage;
  return {
    items: DEMO_BATCHES.slice(start, start + perPage),
    total: DEMO_BATCHES.length,
  };
}

export function useBatches(page = 1) {
  const token = useAuthToken();
  return useQuery({
    queryKey: authScopedQueryKey(["batches", page] as const, token),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(buildDemoBatchList(page));
      }
      return apiClient<BatchListResponse>(`/batch?page=${page}`, {
        token: token || undefined,
        signal,
      });
    },
    enabled: DEMO_MODE_ENABLED || !!token,
    initialData: DEMO_MODE_ENABLED ? buildDemoBatchList(page) : undefined,
  });
}

export function useBatch(batchId: string) {
  const token = useAuthToken();
  return useQuery({
    queryKey: authScopedQueryKey(["batches", batchId] as const, token),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        const batch = DEMO_BATCHES.find((item) => item.id === batchId);
        if (!batch) throw new Error(`Demo batch ${batchId} not found`);
        return Promise.resolve(batch);
      }
      return apiClient<BatchResponse>(`/batch/${batchId}`, {
        token: token || undefined,
        signal,
      });
    },
    enabled: !!batchId && (DEMO_MODE_ENABLED || !!token),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "running" || status === "pending" ? 5000 : false;
    },
  });
}

export function useCreateBatch() {
  const token = useAuthToken();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      client_idempotency_key: string;
      name: string;
      compounds: string[];
      config?: Record<string, unknown>;
    }) => {
      const { client_idempotency_key: idempotencyKey, ...request } = data;
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve({
          id: `batch_demo_${Date.now()}`,
          name: request.name,
          total_compounds: request.compounds.length,
          completed_count: 0,
          failed_count: 0,
          status: "pending",
          analysis_ids: [],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      }
      return apiClient<BatchResponse>("/batch", {
        token: token || undefined,
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(request),
      });
    },
    onSuccess: () => {
      invalidateAuthScopedQueries(queryClient, ["batches"], token);
    },
  });
}

export function useCancelBatch() {
  const token = useAuthToken();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (batchId: string) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve({ id: batchId, cancelled: true });
      }
      return apiClient(`/batch/${batchId}`, {
        token: token || undefined,
        method: "DELETE",
      });
    },
    onSuccess: (_data, batchId) => {
      invalidateAuthScopedQueries(queryClient, ["batches"], token);
      invalidateAuthScopedQueries(queryClient, ["batches", batchId], token);
    },
  });
}

export type { BatchResponse, BatchListResponse };
