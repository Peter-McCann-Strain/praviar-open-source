/**
 * Admin analytics hooks -- TanStack Query wrappers for analytics API endpoints.
 */

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { useAuthToken } from "@/hooks/use-auth-token";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import { authScopedQueryKey } from "@/lib/query-keys";

// -- Types --------------------------------------------------------------------

interface DailyCost {
  date: string;
  total_cost_usd: number;
  analysis_count: number;
  total_input_tokens: number;
  total_output_tokens: number;
}

interface StepCost {
  step_name: string;
  total_cost_usd: number;
  analysis_count: number;
  avg_cost_usd: number;
}

interface ModelCost {
  model_name: string;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  request_count: number;
}

interface CostBreakdownResponse {
  daily_costs: DailyCost[];
  step_costs: StepCost[];
  model_costs: ModelCost[];
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  period: string;
  start_date: string | null;
  end_date: string | null;
}

interface OrgUsage {
  org_id: string;
  org_name: string;
  analysis_count: number;
  total_cost_usd: number;
  avg_cost_usd: number;
}

interface StatusBreakdown {
  status: string;
  count: number;
}

interface TopCompound {
  compound_name: string;
  compound_smiles: string;
  analysis_count: number;
}

interface UsageAnalyticsResponse {
  org_usage: OrgUsage[];
  status_breakdown: StatusBreakdown[];
  top_compounds: TopCompound[];
  total_analyses: number;
  avg_cost_per_analysis: number;
  avg_duration_seconds: number | null;
  period: string;
}

interface ModelUsageDetail {
  model_name: string;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  request_count: number;
  cache_hit_rate: number | null;
}

interface ModelUsageResponse {
  models: ModelUsageDetail[];
  total_tokens: number;
  total_cost_usd: number;
  overall_cache_hit_rate: number | null;
  period: string;
}

interface AuditLogEntry {
  id: string;
  org_id: string;
  action: string;
  user_id: string | null;
  user_email: string;
  analysis_id: string | null;
  details: Record<string, unknown>;
  ip_address: string;
  created_at: string;
}

interface AuditLogListResponse {
  items: AuditLogEntry[];
  total: number;
  page: number;
  per_page: number;
  has_next: boolean;
}

interface AuditLogFilters {
  action?: string;
  user_id?: string;
  start_date?: string;
  end_date?: string;
  sort?: "asc" | "desc";
}

// -- Demo fixtures ------------------------------------------------------------

const DEMO_COST_ANALYTICS: CostBreakdownResponse = {
  daily_costs: [
    {
      date: "2026-04-19",
      total_cost_usd: 1.42,
      analysis_count: 3,
      total_input_tokens: 220_000,
      total_output_tokens: 38_000,
    },
    {
      date: "2026-04-20",
      total_cost_usd: 2.31,
      analysis_count: 5,
      total_input_tokens: 360_000,
      total_output_tokens: 51_000,
    },
  ],
  step_costs: [
    {
      step_name: "claim_analysis",
      total_cost_usd: 4.12,
      analysis_count: 8,
      avg_cost_usd: 0.515,
    },
  ],
  model_costs: [
    {
      model_name: "claude-opus-4-6",
      total_cost_usd: 6.42,
      total_input_tokens: 720_000,
      total_output_tokens: 110_000,
      request_count: 32,
    },
  ],
  total_cost_usd: 8.48,
  total_input_tokens: 720_000,
  total_output_tokens: 110_000,
  period: "month",
  start_date: "2026-04-01",
  end_date: "2026-04-30",
};

const DEMO_USAGE_ANALYTICS: UsageAnalyticsResponse = {
  org_usage: [
    {
      org_id: "org_demo_001",
      org_name: "Praviar Demo Org",
      analysis_count: 18,
      total_cost_usd: 8.48,
      avg_cost_usd: 0.471,
    },
  ],
  status_breakdown: [
    { status: "completed", count: 16 },
    { status: "running", count: 2 },
  ],
  top_compounds: [
    {
      compound_name: "Succinic acid",
      compound_smiles: "OC(=O)CCC(O)=O",
      analysis_count: 4,
    },
    {
      compound_name: "Aspirin",
      compound_smiles: "CC(=O)Oc1ccccc1C(=O)O",
      analysis_count: 3,
    },
  ],
  total_analyses: 18,
  avg_cost_per_analysis: 0.471,
  avg_duration_seconds: 612,
  period: "month",
};

const DEMO_MODEL_USAGE: ModelUsageResponse = {
  models: [
    {
      model_name: "claude-sonnet-4-6",
      total_input_tokens: 480_000,
      total_output_tokens: 72_000,
      total_tokens: 552_000,
      estimated_cost_usd: 5.52,
      request_count: 22,
      cache_hit_rate: 41,
    },
    {
      model_name: "claude-haiku-4-5",
      total_input_tokens: 240_000,
      total_output_tokens: 38_000,
      total_tokens: 278_000,
      estimated_cost_usd: 2.96,
      request_count: 10,
      cache_hit_rate: 18,
    },
  ],
  total_tokens: 830_000,
  total_cost_usd: 8.48,
  overall_cache_hit_rate: 33,
  period: "month",
};

const DEMO_AUDIT_LOG: AuditLogListResponse = {
  items: [
    {
      id: "aud_demo_001",
      org_id: "org_demo_001",
      action: "analysis.created",
      user_id: "usr_demo_001",
      user_email: "demo@example.com",
      analysis_id: "ana_demo_001",
      details: { compound_name: "Succinic acid" },
      ip_address: "127.0.0.1",
      created_at: "2026-04-15T10:22:00Z",
    },
    {
      id: "aud_demo_002",
      org_id: "org_demo_001",
      action: "report.shared",
      user_id: "usr_demo_001",
      user_email: "demo@example.com",
      analysis_id: "ana_demo_001",
      details: {},
      ip_address: "127.0.0.1",
      created_at: "2026-04-15T11:04:00Z",
    },
  ],
  total: 2,
  page: 1,
  per_page: 50,
  has_next: false,
};

// -- Hooks --------------------------------------------------------------------

export function useCostAnalytics(
  period: string = "month",
  startDate?: string,
  endDate?: string,
) {
  const token = useAuthToken();
  const params = new URLSearchParams({ period });
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);

  return useQuery({
    queryKey: authScopedQueryKey(
      ["admin", "analytics", "costs", period, startDate, endDate] as const,
      token,
    ),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(DEMO_COST_ANALYTICS);
      }
      return apiClient<CostBreakdownResponse>(
        `/admin/analytics/costs?${params}`,
        { token: token ?? undefined, signal },
      );
    },
    enabled: DEMO_MODE_ENABLED || !!token,
    staleTime: 60_000, // 1 minute
  });
}

export function useUsageAnalytics(period: string = "month") {
  const token = useAuthToken();
  return useQuery({
    queryKey: authScopedQueryKey(
      ["admin", "analytics", "usage", period] as const,
      token,
    ),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(DEMO_USAGE_ANALYTICS);
      }
      return apiClient<UsageAnalyticsResponse>(
        `/admin/analytics/usage?period=${period}`,
        { token: token ?? undefined, signal },
      );
    },
    enabled: DEMO_MODE_ENABLED || !!token,
    staleTime: 60_000,
  });
}

export function useModelUsage(period: string = "month") {
  const token = useAuthToken();
  return useQuery({
    queryKey: authScopedQueryKey(
      ["admin", "analytics", "models", period] as const,
      token,
    ),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) return Promise.resolve(DEMO_MODEL_USAGE);
      return apiClient<ModelUsageResponse>(
        `/admin/analytics/models?period=${period}`,
        { token: token ?? undefined, signal },
      );
    },
    enabled: DEMO_MODE_ENABLED || !!token,
    staleTime: 60_000,
  });
}

export function useAuditLog(page: number = 1, filters: AuditLogFilters = {}) {
  const token = useAuthToken();
  const params = new URLSearchParams({
    page: String(page),
    per_page: "50",
  });
  if (filters.action) params.set("action", filters.action);
  if (filters.user_id) params.set("user_id", filters.user_id);
  if (filters.start_date) params.set("start_date", filters.start_date);
  if (filters.end_date) params.set("end_date", filters.end_date);
  if (filters.sort) params.set("sort", filters.sort);

  return useQuery({
    queryKey: authScopedQueryKey(
      ["admin", "analytics", "audit-log", page, filters] as const,
      token,
    ),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) return Promise.resolve(DEMO_AUDIT_LOG);
      return apiClient<AuditLogListResponse>(
        `/admin/analytics/audit-log?${params}`,
        { token: token ?? undefined, signal },
      );
    },
    enabled: DEMO_MODE_ENABLED || !!token,
  });
}

export type {
  CostBreakdownResponse,
  DailyCost,
  StepCost,
  ModelCost,
  UsageAnalyticsResponse,
  OrgUsage,
  StatusBreakdown,
  TopCompound,
  ModelUsageResponse,
  ModelUsageDetail,
  AuditLogEntry,
  AuditLogListResponse,
  AuditLogFilters,
};
