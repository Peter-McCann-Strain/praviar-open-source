/**
 * Monitor management hooks — TanStack Query wrappers for monitor API endpoints.
 *
 * Demo-mode (NEXT_PUBLIC_DEMO_MODE=true) returns seeded fixtures synchronously
 * via the local demo cache, never invoking the API client.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, isAuthBoundaryError } from "@/lib/api-client";
import { useAuthToken } from "@/hooks/use-auth-token";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import {
  authScopeKey,
  authScopedQueryKey,
  invalidateAuthScopedQueries,
  keepPreviousDataForAuthScope,
} from "@/lib/query-keys";
import {
  createDemoMonitor,
  deleteDemoMonitor,
  dismissDemoAlert,
  getDemoMonitorAlerts,
  listDemoMonitors,
  reassessDemoMonitorConclusion,
  updateDemoMonitor,
} from "@/lib/demo-monitors";

export interface MonitorResponse {
  id: string;
  compound_smiles: string;
  compound_name: string;
  source_analysis_id: string | null;
  source_report_id: string;
  source_trust_mode: string;
  schedule: string;
  is_active: boolean;
  jurisdiction_bundle: string;
  target_jurisdictions: string[];
  strategy_version: string;
  monitoring_strategy: Record<string, unknown>;
  watch_targets: unknown[];
  last_run_at: string | null;
  last_full_refresh_at: string | null;
  last_run_mode:
    | "bootstrap"
    | "diff_only"
    | "targeted_refresh"
    | "full_refresh"
    | "pending";
  last_run_status:
    | "pending"
    | "ok"
    | "review_required"
    | "reassessed"
    | "ready"
    | "running"
    | "error";
  last_run_summary: string;
  last_patent_count: number;
  conclusion_status: "unbound" | "fresh" | "review_required" | "reassessed";
  stale_conclusions: MonitorConclusionImpact[];
  stale_conclusion_count: number;
  created_at: string;
}

export interface MonitorConclusionImpact {
  conclusion_id: string;
  conclusion_type: string;
  label: string;
  previous_outcome: string;
  status: "review_required";
  source_report_id: string;
  dependency_fingerprint: string;
  invalidated_at: string;
  latest_observed_at: string;
  reason_codes: string[];
  trigger_patent_ids: string[];
  trigger_event_ids: string[];
  jurisdictions: string[];
  reassessment_id?: string | null;
  alert_id?: string | null;
  evidence_digest?: string;
  evidence_version?: string;
  evidence_observed_at?: string | null;
}

export interface MonitorListResponse {
  items: MonitorResponse[];
  total: number;
  page: number;
  per_page: number;
  is_active?: boolean;
}

export interface MonitorAlertResponse {
  id: string;
  monitor_id: string;
  new_patent_ids: string[];
  new_patent_count: number;
  run_at: string;
  dismissed: boolean;
  created_at: string;
  summary?: string;
  alert_type?: string;
  severity?: string;
  strategy_mode?: string;
  new_event_ids?: string[];
  jurisdiction_deltas?: Record<string, unknown>;
  affected_conclusions?: MonitorConclusionImpact[];
  stale_conclusion_count?: number;
}

export interface MonitorAlertListResponse {
  items: MonitorAlertResponse[];
  total: number;
  page: number;
  per_page: number;
}

export function useMonitors(page = 1, isActive?: boolean, perPage = 20) {
  const token = useAuthToken();
  const currentAuthScope = authScopeKey(token);
  const params = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
  });
  if (isActive !== undefined) params.set("is_active", String(isActive));
  return useQuery<MonitorListResponse>({
    queryKey: authScopedQueryKey(
      ["monitors", page, isActive, perPage] as const,
      token,
    ),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        const monitors =
          isActive === undefined
            ? listDemoMonitors()
            : listDemoMonitors().filter(
                (monitor) => monitor.is_active === isActive,
              );
        const start = Math.max(0, (page - 1) * perPage);
        return Promise.resolve<MonitorListResponse>({
          items: monitors.slice(start, start + perPage),
          total: monitors.length,
          page,
          per_page: perPage,
          is_active: isActive,
        });
      }
      if (!token) {
        return Promise.reject(
          new Error("Authenticated monitor list requests require a token."),
        );
      }
      return apiClient<Omit<MonitorListResponse, "page" | "per_page">>(
        `/monitors?${params}`,
        {
          token,
          signal,
        },
      ).then((response) => ({
        ...response,
        page,
        per_page: perPage,
        is_active: isActive,
      }));
    },
    enabled: DEMO_MODE_ENABLED || !!token,
    placeholderData:
      DEMO_MODE_ENABLED || token
        ? keepPreviousDataForAuthScope<MonitorListResponse>(currentAuthScope)
        : undefined,
  });
}

export function useMonitorForAnalysisState(analysisId: string | undefined) {
  const token = useAuthToken();
  const query = useQuery<MonitorResponse | null>({
    queryKey: authScopedQueryKey(
      ["monitors", "by-analysis", analysisId] as const,
      token,
    ),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(
          listDemoMonitors().find(
            (item) => item.source_analysis_id === analysisId,
          ) ?? null,
        );
      }
      if (!token) {
        return Promise.reject(
          new Error("Authenticated monitor lookup requests require a token."),
        );
      }
      return apiClient<MonitorResponse | null>(
        `/monitors/by-analysis/${analysisId}`,
        { token, signal },
      );
    },
    enabled: (DEMO_MODE_ENABLED || !!token) && !!analysisId,
  });
  const monitor =
    !analysisId || isAuthBoundaryError(query.error)
      ? undefined
      : (query.data ?? undefined);
  return { ...query, monitor };
}

export function useMonitorForAnalysis(analysisId: string | undefined) {
  return useMonitorForAnalysisState(analysisId).monitor;
}

export function useMonitorAlerts(monitorId: string, page = 1, perPage = 20) {
  const token = useAuthToken();
  const currentAuthScope = authScopeKey(token);
  return useQuery<MonitorAlertListResponse>({
    queryKey: authScopedQueryKey(
      ["monitors", monitorId, "alerts", page, perPage] as const,
      token,
    ),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        const alerts = getDemoMonitorAlerts(monitorId);
        const start = Math.max(0, (page - 1) * perPage);
        return Promise.resolve<MonitorAlertListResponse>({
          items: alerts.slice(start, start + perPage),
          total: alerts.length,
          page,
          per_page: perPage,
        });
      }
      if (!token) {
        return Promise.reject(
          new Error("Authenticated monitor alert requests require a token."),
        );
      }
      return apiClient<Omit<MonitorAlertListResponse, "page" | "per_page">>(
        `/monitors/${monitorId}/alerts?page=${page}&per_page=${perPage}`,
        { token, signal },
      ).then((response) => ({ ...response, page, per_page: perPage }));
    },
    enabled: (DEMO_MODE_ENABLED || !!token) && !!monitorId,
    placeholderData:
      DEMO_MODE_ENABLED || token
        ? keepPreviousDataForAuthScope<MonitorAlertListResponse>(
            currentAuthScope,
          )
        : undefined,
  });
}

export interface CreateMonitorInput {
  analysis_id?: string;
  compound_smiles?: string;
  compound_name?: string;
  schedule?: string;
}

export interface UpdateMonitorInput {
  monitorId: string;
  data: {
    schedule?: string;
    is_active?: boolean;
    compound_name?: string;
  };
}

export interface DismissAlertInput {
  monitorId: string;
  alertId: string;
}

export interface ReassessMonitorConclusionInput {
  monitorId: string;
  conclusionId: string;
  data: {
    resolution: "reaffirmed" | "superseded" | "withdrawn";
    resolution_note: string;
    attestation_accepted: true;
    reassessment_id: string;
    alert_id: string;
    dependency_fingerprint: string;
    evidence_digest: string;
    evidence_version: string;
    evidence_observed_at: string;
    replacement_analysis_id?: string;
  };
}

export interface MonitorConclusionReassessmentResponse {
  id: string;
  monitor_id: string | null;
  source_analysis_id: string;
  source_report_id: string;
  conclusion_id: string;
  conclusion_type: string;
  conclusion_label: string;
  previous_outcome: string;
  dependency_fingerprint: string;
  status: "open" | "reaffirmed" | "superseded" | "withdrawn";
  trigger_evidence: Record<string, unknown>;
  invalidated_at: string;
  latest_observed_at: string;
  resolved_at: string | null;
  reviewer_role: string;
  reviewer_name: string;
  reviewer_email: string;
  resolution_note: string;
  attestation_version: string;
  attestation_statement: string;
  attestation_accepted: boolean;
  replacement_analysis_id: string | null;
  created_at: string;
  updated_at: string;
}

export function useCreateMonitor() {
  const token = useAuthToken();
  const queryClient = useQueryClient();
  return useMutation({
    meta: { suppressGlobalErrorToast: true },
    mutationFn: (data: CreateMonitorInput) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(createDemoMonitor(data));
      }
      if (!token) {
        throw new Error("Authenticated monitor creation requires a token.");
      }
      return apiClient<MonitorResponse>("/monitors", {
        token,
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    onSuccess: () => {
      invalidateAuthScopedQueries(queryClient, ["monitors"], token);
    },
  });
}

export function useUpdateMonitor() {
  const token = useAuthToken();
  const queryClient = useQueryClient();
  return useMutation({
    meta: { suppressGlobalErrorToast: true },
    mutationFn: ({ monitorId, data }: UpdateMonitorInput) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(updateDemoMonitor(monitorId, data));
      }
      if (!token) {
        throw new Error("Authenticated monitor updates require a token.");
      }
      return apiClient<MonitorResponse>(`/monitors/${monitorId}`, {
        token,
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },
    onSuccess: () => {
      invalidateAuthScopedQueries(queryClient, ["monitors"], token);
    },
  });
}

export function useDeleteMonitor() {
  const token = useAuthToken();
  const queryClient = useQueryClient();
  return useMutation({
    meta: { suppressGlobalErrorToast: true },
    mutationFn: (monitorId: string) => {
      if (DEMO_MODE_ENABLED) {
        deleteDemoMonitor(monitorId);
        return Promise.resolve({});
      }
      if (!token) {
        throw new Error("Authenticated monitor deletion requires a token.");
      }
      return apiClient(`/monitors/${monitorId}`, {
        token,
        method: "DELETE",
      });
    },
    onSuccess: () => {
      invalidateAuthScopedQueries(queryClient, ["monitors"], token);
    },
  });
}

export function useDismissAlert() {
  const token = useAuthToken();
  const queryClient = useQueryClient();
  return useMutation({
    meta: { suppressGlobalErrorToast: true },
    mutationFn: ({ monitorId, alertId }: DismissAlertInput) => {
      if (DEMO_MODE_ENABLED) {
        dismissDemoAlert(monitorId, alertId);
        return Promise.resolve({});
      }
      if (!token) {
        throw new Error("Authenticated alert updates require a token.");
      }
      return apiClient(`/monitors/${monitorId}/alerts/${alertId}/dismiss`, {
        token,
        method: "POST",
      });
    },
    onSuccess: (_data, variables) => {
      invalidateAuthScopedQueries(
        queryClient,
        ["monitors", variables.monitorId, "alerts"],
        token,
      );
    },
  });
}

export function useReassessMonitorConclusion() {
  const token = useAuthToken();
  const queryClient = useQueryClient();
  return useMutation({
    meta: { suppressGlobalErrorToast: true },
    mutationFn: ({
      monitorId,
      conclusionId,
      data,
    }: ReassessMonitorConclusionInput) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(
          reassessDemoMonitorConclusion(monitorId, conclusionId, data),
        );
      }
      if (!token) {
        throw new Error(
          "Authenticated conclusion reassessment requires a token.",
        );
      }
      return apiClient<MonitorConclusionReassessmentResponse>(
        `/monitors/${monitorId}/conclusions/${encodeURIComponent(
          conclusionId,
        )}/reassess`,
        {
          token,
          method: "POST",
          body: JSON.stringify(data),
        },
      );
    },
    onSuccess: (_data, variables) => {
      invalidateAuthScopedQueries(queryClient, ["monitors"], token);
      invalidateAuthScopedQueries(
        queryClient,
        ["monitors", variables.monitorId, "alerts"],
        token,
      );
    },
  });
}
