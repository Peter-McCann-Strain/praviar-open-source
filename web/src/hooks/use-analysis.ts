"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { normalizeAnalysisSearch } from "@/lib/analysis-search";
import type { ProductContextPayload } from "@/lib/product-context";
import type { AnalysisListItem, AnalysisListResponse } from "@/types/api";
import type {
  AssetTypeHint,
  DevelopmentStage,
  IntendedAction,
  JurisdictionBundle,
  PipelineConfig,
} from "@/types/pipeline";
import type { TrustMode } from "@/stores/config-store";
import { ANALYSIS_POLL_INTERVAL_MS, DEMO_MODE_ENABLED } from "@/lib/constants";
import { useClientReady } from "@/hooks/use-client-ready";
import {
  authScopeKey,
  authScopedQueryKey,
  invalidateAuthScopedQueries,
  keepPreviousDataForAuthScope,
} from "@/lib/query-keys";
import {
  createDemoAnalysis,
  getDemoAnalysis,
  isDemoAnalysisId,
  isSeedDemoAnalysisId,
  listDemoAnalyses,
} from "@/lib/demo-data";

function buildDemoStatusCounts(items: AnalysisListItem[]) {
  const counts: Record<string, number> = {
    all: items.length,
    pending: 0,
    running: 0,
    completed: 0,
    failed: 0,
    cancelled: 0,
  };

  for (const item of items) {
    counts[item.status] = (counts[item.status] ?? 0) + 1;
  }

  return counts;
}

const DEMO_RISK_ORDER: Record<string, number> = {
  high: 3,
  medium: 2,
  low: 1,
  clear: 0,
};

function matchesDemoSearch(item: AnalysisListItem, search: string) {
  if (!search) {
    return true;
  }

  const query = search.toLowerCase();
  return [
    item.compound_name,
    item.compound_input,
    item.compound_smiles,
    item.id,
  ]
    .filter((value): value is string => Boolean(value))
    .some((value) => value.toLowerCase().includes(query));
}

function sortDemoAnalyses(items: AnalysisListItem[], sortBy?: string) {
  return [...items].sort((first, second) => {
    switch (sortBy) {
      case "date-asc":
        return (
          new Date(first.created_at).getTime() -
          new Date(second.created_at).getTime()
        );
      case "risk-desc":
        return (
          (DEMO_RISK_ORDER[second.overall_risk ?? ""] ?? -1) -
          (DEMO_RISK_ORDER[first.overall_risk ?? ""] ?? -1)
        );
      case "risk-asc":
        return (
          (DEMO_RISK_ORDER[first.overall_risk ?? ""] ?? -1) -
          (DEMO_RISK_ORDER[second.overall_risk ?? ""] ?? -1)
        );
      case "date-desc":
      default:
        return (
          new Date(second.created_at).getTime() -
          new Date(first.created_at).getTime()
        );
    }
  });
}

function buildDemoAnalysesResponse({
  page,
  perPage,
  statusFilter,
  riskFilter,
  search,
  sortBy,
}: {
  page: number;
  perPage: number;
  statusFilter?: string;
  riskFilter?: string;
  search: string;
  sortBy?: string;
}): AnalysisListResponse {
  const searchAndRiskScopedItems = listDemoAnalyses().filter((item) => {
    if (!matchesDemoSearch(item, search)) {
      return false;
    }
    return riskFilter && riskFilter !== "all"
      ? item.overall_risk === riskFilter
      : true;
  });
  const statusCounts = buildDemoStatusCounts(searchAndRiskScopedItems);
  const filteredItems = searchAndRiskScopedItems.filter((item) =>
    statusFilter && statusFilter !== "all"
      ? item.status === statusFilter
      : true,
  );
  const sortedItems = sortDemoAnalyses(filteredItems, sortBy);
  const safePage = Math.max(1, page);
  const safePerPage = Math.max(1, perPage);
  const start = (safePage - 1) * safePerPage;

  return {
    items: sortedItems.slice(start, start + safePerPage),
    total: filteredItems.length,
    page: safePage,
    per_page: safePerPage,
    status_counts: statusCounts,
  };
}

export function useAnalyses(
  token: string | null,
  page = 1,
  perPage = 20,
  statusFilter?: string,
  riskFilter?: string,
  search?: string,
  sortBy?: string,
  riskRatingsRestricted = false,
) {
  const normalizedSearch = normalizeAnalysisSearch(search);
  const effectiveRiskFilter = riskRatingsRestricted ? "all" : riskFilter;
  const effectiveSortBy =
    riskRatingsRestricted && (sortBy === "risk-desc" || sortBy === "risk-asc")
      ? "date-desc"
      : sortBy;
  const currentAuthScope = authScopeKey(token);

  return useQuery({
    queryKey: authScopedQueryKey(
      [
        "analyses",
        page,
        perPage,
        statusFilter,
        effectiveRiskFilter,
        normalizedSearch,
        effectiveSortBy,
      ] as const,
      token,
    ),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(
          buildDemoAnalysesResponse({
            page,
            perPage,
            statusFilter,
            riskFilter: effectiveRiskFilter,
            search: normalizedSearch,
            sortBy: effectiveSortBy,
          }),
        );
      }
      if (!token) {
        return Promise.reject(
          new Error("Authenticated analysis list requests require a token."),
        );
      }
      const params = new URLSearchParams({
        page: String(page),
        per_page: String(perPage),
      });
      if (statusFilter && statusFilter !== "all")
        params.set("status_filter", statusFilter);
      if (effectiveRiskFilter && effectiveRiskFilter !== "all")
        params.set("risk_filter", effectiveRiskFilter);
      if (normalizedSearch) params.set("search", normalizedSearch);
      if (effectiveSortBy && effectiveSortBy !== "date-desc")
        params.set("sort_by", effectiveSortBy);
      return apiClient<AnalysisListResponse>(`/analyses?${params}`, {
        token,
        signal,
      });
    },
    enabled: DEMO_MODE_ENABLED || !!token,
    // In demo mode the data is static and known at render time. Providing
    // initialData ensures isLoading is false on both the server and client
    // renders, avoiding a hydration mismatch caused by React 18 concurrent
    // mode resolving the synchronous Promise.resolve() between render passes.
    initialData: DEMO_MODE_ENABLED
      ? (() =>
          buildDemoAnalysesResponse({
            page,
            perPage,
            statusFilter,
            riskFilter: effectiveRiskFilter,
            search: normalizedSearch,
            sortBy: effectiveSortBy,
          }))()
      : undefined,
    placeholderData:
      DEMO_MODE_ENABLED || token
        ? keepPreviousDataForAuthScope<AnalysisListResponse>(currentAuthScope)
        : undefined,
  });
}

/**
 * Fetch a single analysis. Polls at ANALYSIS_POLL_INTERVAL_MS while status is
 * "pending" (before SSE connects). Once "running", the SSE stream drives UI
 * updates so polling is disabled to avoid duplicate requests.
 */
export function useAnalysis(id: string, token: string | null) {
  const clientReady = useClientReady();
  const isLocalDemoEnvironment = DEMO_MODE_ENABLED;
  const isDemoId = isDemoAnalysisId(id);
  const waitForGeneratedDemoState =
    isLocalDemoEnvironment &&
    isDemoId &&
    !isSeedDemoAnalysisId(id) &&
    !clientReady;
  const shouldUseLocalDemoAnalysis =
    isLocalDemoEnvironment && isDemoId && !waitForGeneratedDemoState;

  return useQuery({
    queryKey: authScopedQueryKey(["analyses", id] as const, token),
    queryFn: ({ signal }) => {
      if (shouldUseLocalDemoAnalysis) {
        const analysis = getDemoAnalysis(id);
        if (!analysis) {
          throw new Error(`Demo analysis ${id} not found`);
        }
        return Promise.resolve(analysis);
      }
      return apiClient<AnalysisListItem>(`/analyses/${id}`, {
        token: token || undefined,
        signal,
      });
    },
    enabled:
      !!id &&
      !waitForGeneratedDemoState &&
      (shouldUseLocalDemoAnalysis || DEMO_MODE_ENABLED || !!token),
    // apiClient already retries retryable transport responses. Keep 403/404
    // analysis states terminal so the detail and report routes can render the
    // governed error surface immediately.
    retry: false,
    refetchInterval: (query) => {
      if (shouldUseLocalDemoAnalysis || DEMO_MODE_ENABLED) return false;
      const data = query.state.data;
      // Only poll while pending (waiting for worker pickup).
      // Once running, SSE stream provides real-time updates.
      if (data?.status === "pending") return ANALYSIS_POLL_INTERVAL_MS;
      return false;
    },
  });
}

export function useCreateAnalysis(token: string | null) {
  const queryClient = useQueryClient();

  type CreateAnalysisInput = {
    client_idempotency_key: string;
    compound_input: string;
    input_type: "name" | "smiles" | "cas" | "inchi" | "inchikey";
    submitted_identity_confirmed: true;
    submitted_identity_value: string;
    trust_mode?: TrustMode;
    intended_actions?: IntendedAction[];
    target_jurisdictions?: string[];
    jurisdiction_bundle?: JurisdictionBundle;
    development_stage?: DevelopmentStage;
    asset_type_hint?: AssetTypeHint | null;
    product_context?: ProductContextPayload;
    config?: Partial<PipelineConfig>;
  };

  return useMutation({
    mutationFn: (data: CreateAnalysisInput) => {
      const { client_idempotency_key: idempotencyKey, ...request } = data;
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(createDemoAnalysis(request));
      }
      return apiClient<AnalysisListItem>("/analyses", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(request),
        token: token || undefined,
      });
    },
    onSuccess: () => {
      invalidateAuthScopedQueries(queryClient, ["analyses"], token);
    },
  });
}
