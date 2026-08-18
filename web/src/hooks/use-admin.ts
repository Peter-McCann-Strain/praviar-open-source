/**
 * Admin dashboard hooks — TanStack Query wrappers for admin API endpoints.
 */

import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { APIError, apiClient } from "@/lib/api-client";
import { useAuthToken } from "@/hooks/use-auth-token";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import {
  authScopedQueryKey,
  invalidateAuthScopedQueries,
} from "@/lib/query-keys";
import { useToastStore } from "@/stores/toast-store";
import { logError } from "@/lib/error-logger";
import { PROBLEM_TYPES } from "@/lib/problem-types";

// ── Types ────────────────────────────────────────────────────────────────────

interface ServiceHealth {
  name: string;
  status: string;
  detail: string;
}

interface SystemHealth {
  services: ServiceHealth[];
  table_counts: Record<string, number>;
}

interface AdminCapabilities {
  admin_org_id: string;
  is_platform_superadmin: boolean;
  can_manage_org_billing: boolean;
  can_list_cross_org_users: boolean;
  can_manage_cross_org_user_roles: boolean;
  can_inspect_task_queue: boolean;
}

interface OrgSummary {
  id: string;
  name: string;
  slug: string;
  plan: string;
  user_count: number;
  analysis_count: number;
  max_analyses_per_month: number;
  free_analyses_remaining: number;
  created_at: string;
}

interface OrgListResponse {
  items: OrgSummary[];
  total: number;
  capabilities: AdminCapabilities;
}

interface UserSummary {
  id: string;
  email: string;
  full_name: string;
  role: string;
  org_id: string;
  org_name: string;
  last_active_at: string | null;
  membership_active: boolean;
  membership_synchronized: boolean;
  created_at: string;
}

interface UserListResponse {
  items: UserSummary[];
  total: number;
  capabilities: AdminCapabilities;
}

interface DailyMetric {
  date: string;
  count: number;
  cost: number;
  errors: number;
}

interface MetricsResponse {
  daily: DailyMetric[];
  total_analyses: number;
  total_cost: number;
  avg_duration_seconds: number | null;
  error_rate: number;
}

interface AuditLogEntry {
  id: string;
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
}

interface TaskInfo {
  id: string;
  name: string;
  args: unknown[];
  status: string;
}

interface TaskQueueResponse {
  backend: "celery" | "cloud_tasks" | string;
  detail: string;
  inspectable: boolean;
  active: TaskInfo[];
  reserved: TaskInfo[];
  scheduled_count: number;
}

interface AdminOperationStatus {
  operation_id: string;
  operation_type: "invite" | "role_update";
  state: string;
  outcome_confirmed: boolean;
  reconciliation_required: boolean;
  recovery_available?: boolean;
  recovery_action?: "retry_rejected_role" | null;
  provider_resource_id: string | null;
  target_user_id: string | null;
  target_email_normalized: string | null;
  requested_role: string;
  updated_at: string;
}

interface AdminOperationListResponse {
  items: AdminOperationStatus[];
  open_total: number;
  has_more: boolean;
}

interface AdminOperationNotice {
  kind: "unconfirmed" | "reconciled" | "failed";
  message: string;
  canReconcile: boolean;
}

const TERMINAL_ADMIN_OPERATION_ERROR_TYPE =
  PROBLEM_TYPES.adminOperationTerminalFailure;

function errorStatus(error: unknown): number | undefined {
  if (error instanceof APIError) return error.status;
  if (typeof error === "object" && error !== null && "status" in error) {
    const status = (error as { status?: unknown }).status;
    return typeof status === "number" ? status : undefined;
  }
  return undefined;
}

function isTerminalAdminOperationError(error: unknown): boolean {
  if (
    !(error instanceof APIError) ||
    typeof error.data !== "object" ||
    !error.data
  ) {
    return false;
  }
  return (
    (error.data as { type?: unknown }).type ===
    TERMINAL_ADMIN_OPERATION_ERROR_TYPE
  );
}

function isAmbiguousAdminMutationError(error: unknown): boolean {
  if (isTerminalAdminOperationError(error)) return false;
  const status = errorStatus(error);
  return status === undefined || status >= 500;
}

function adminMutationErrorMessage(error: unknown, label: string): string {
  if (isTerminalAdminOperationError(error)) {
    return `${label} was rejected and was not applied. Submit again to create a new operation.`;
  }
  const status = errorStatus(error);
  if (status === 401 || status === 403) {
    return `${label} was not applied because your current access does not permit it.`;
  }
  if (status === 409) {
    return `${label} was not applied because it conflicts with current membership authority. Refresh before trying a new request.`;
  }
  if (status === 400 || status === 422 || status === 429) {
    return `${label} was rejected before it could be applied. Review the request before submitting again.`;
  }
  return `${label} outcome is unconfirmed. Reconcile exact provider state before taking another action.`;
}

// ── Demo fixtures ────────────────────────────────────────────────────────────

const DEMO_HEALTH: SystemHealth = {
  services: [
    { name: "api", status: "healthy", detail: "All routes reachable" },
    { name: "worker", status: "healthy", detail: "0 stuck jobs" },
    { name: "redis", status: "healthy", detail: "Latency 1ms" },
  ],
  table_counts: { analyses: 21, monitors: 1, comments: 14 },
};

const DEMO_METRICS: MetricsResponse = {
  daily: [
    { date: "2026-04-19", count: 3, cost: 1.42, errors: 0 },
    { date: "2026-04-20", count: 5, cost: 2.31, errors: 0 },
    { date: "2026-04-21", count: 4, cost: 1.84, errors: 1 },
    { date: "2026-04-22", count: 6, cost: 2.91, errors: 0 },
  ],
  total_analyses: 18,
  total_cost: 8.48,
  avg_duration_seconds: 612,
  error_rate: 0.013,
};

const DEMO_CAPABILITIES: AdminCapabilities = {
  admin_org_id: "org_demo_001",
  is_platform_superadmin: false,
  can_manage_org_billing: true,
  can_list_cross_org_users: true,
  can_manage_cross_org_user_roles: true,
  can_inspect_task_queue: true,
};

const DEMO_ORGANIZATIONS: OrgListResponse = {
  items: [
    {
      id: "org_demo_001",
      name: "Praviar Demo Biotech",
      slug: "praviar-demo-biotech",
      plan: "growth",
      user_count: 7,
      analysis_count: 21,
      max_analyses_per_month: 40,
      free_analyses_remaining: 9,
      created_at: "2026-04-01T09:00:00.000Z",
    },
    {
      id: "org_demo_002",
      name: "Northstar Therapeutics",
      slug: "northstar-therapeutics",
      plan: "enterprise",
      user_count: 18,
      analysis_count: 64,
      max_analyses_per_month: 120,
      free_analyses_remaining: 22,
      created_at: "2026-03-18T14:15:00.000Z",
    },
  ],
  total: 2,
  capabilities: DEMO_CAPABILITIES,
};

const DEMO_USERS: UserListResponse = {
  items: [
    {
      id: "user_demo_ada",
      email: "ada@example.com",
      full_name: "Ada Lovelace",
      role: "admin",
      org_id: "org_demo_001",
      org_name: "Praviar Demo Biotech",
      last_active_at: "2026-07-02T16:30:00.000Z",
      membership_active: true,
      membership_synchronized: true,
      created_at: "2026-04-01T09:10:00.000Z",
    },
    {
      id: "user_demo_grace",
      email: "grace@example.com",
      full_name: "Grace Hopper",
      role: "attorney",
      org_id: "org_demo_001",
      org_name: "Praviar Demo Biotech",
      last_active_at: "2026-07-01T11:42:00.000Z",
      membership_active: true,
      membership_synchronized: true,
      created_at: "2026-04-02T10:45:00.000Z",
    },
    {
      id: "user_demo_katherine",
      email: "katherine@example.com",
      full_name: "Katherine Johnson",
      role: "scientist",
      org_id: "org_demo_001",
      org_name: "Praviar Demo Biotech",
      last_active_at: null,
      membership_active: true,
      membership_synchronized: true,
      created_at: "2026-06-14T08:20:00.000Z",
    },
  ],
  total: 3,
  capabilities: DEMO_CAPABILITIES,
};

const DEMO_AUDIT_LOGS: AuditLogListResponse = {
  items: [
    {
      id: "audit_demo_export_queued",
      action: "report.export.queued",
      user_id: "user_demo_ada",
      user_email: "ada@example.com",
      analysis_id: "ana_demo_001",
      details: {
        job_id: "demo-export-001",
        format: "pdf",
        audience: "counsel",
        sections: ["summary", "claims", "evidence"],
      },
      ip_address: "127.0.0.1",
      created_at: "2026-07-02T16:33:00.000Z",
    },
    {
      id: "audit_demo_key_created",
      action: "api_key.created",
      user_id: "user_demo_ada",
      user_email: "ada@example.com",
      analysis_id: null,
      details: {
        key_id: "key_demo_001",
        scopes: ["analyses:read", "reports:read"],
        expires_at: "2026-10-20T09:30:00.000Z",
      },
      ip_address: "127.0.0.1",
      created_at: "2026-07-01T12:15:00.000Z",
    },
    {
      id: "audit_demo_review_handoff",
      action: "analysis.review_handoff.created",
      user_id: "user_demo_grace",
      user_email: "grace@example.com",
      analysis_id: "ana_demo_001",
      details: {
        target_type: "patent",
        target_id: "US-demo-blocker",
        promoted_to_under_review: true,
      },
      ip_address: "127.0.0.1",
      created_at: "2026-06-30T15:22:00.000Z",
    },
  ],
  total: 3,
};

const DEMO_TASKS: TaskQueueResponse = {
  backend: "celery",
  detail: "Demo task queue is healthy; no live backend connection required.",
  inspectable: true,
  active: [
    {
      id: "task-demo-report-refresh",
      name: "reports.refresh_source_health",
      args: ["ana_demo_001"],
      status: "active",
    },
  ],
  reserved: [
    {
      id: "task-demo-export",
      name: "exports.render_report_packet",
      args: ["demo-export-001"],
      status: "reserved",
    },
  ],
  scheduled_count: 2,
};

// ── Hooks ────────────────────────────────────────────────────────────────────

export function useAdminHealth() {
  const token = useAuthToken();
  return useQuery({
    queryKey: authScopedQueryKey(["admin", "health"] as const, token),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(DEMO_HEALTH);
      }
      return apiClient<SystemHealth>("/admin/health", {
        token: token || undefined,
        signal,
      });
    },
    refetchInterval: DEMO_MODE_ENABLED ? false : 30_000,
    enabled: DEMO_MODE_ENABLED || !!token,
    // Background health poll — surface failures inline on the admin page, not
    // via an intrusive global toast on every failed 30s tick.
    meta: { suppressGlobalErrorToast: true },
  });
}

export function useAdminOrganizations(page = 1) {
  const token = useAuthToken();
  return useQuery({
    queryKey: authScopedQueryKey(
      ["admin", "organizations", page] as const,
      token,
    ),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(DEMO_ORGANIZATIONS);
      }
      return apiClient<OrgListResponse>(`/admin/organizations?page=${page}`, {
        token: token || undefined,
        signal,
      });
    },
    enabled: DEMO_MODE_ENABLED || !!token,
  });
}

export function useAdminUsers(page = 1, orgId?: string) {
  const token = useAuthToken();
  const params = new URLSearchParams({ page: String(page) });
  if (orgId) params.set("org_id", orgId);
  return useQuery({
    queryKey: authScopedQueryKey(
      ["admin", "users", page, orgId] as const,
      token,
    ),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(DEMO_USERS);
      }
      return apiClient<UserListResponse>(`/admin/users?${params}`, {
        token: token || undefined,
        signal,
      });
    },
    enabled: DEMO_MODE_ENABLED || !!token,
  });
}

export function useAdminMetrics() {
  const token = useAuthToken();
  return useQuery({
    queryKey: authScopedQueryKey(["admin", "metrics"] as const, token),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(DEMO_METRICS);
      }
      return apiClient<MetricsResponse>("/admin/metrics", {
        token: token || undefined,
        signal,
      });
    },
    enabled: DEMO_MODE_ENABLED || !!token,
  });
}

export function useAdminAuditLogs(page = 1, action?: string) {
  const token = useAuthToken();
  const params = new URLSearchParams({ page: String(page), per_page: "20" });
  if (action) params.set("action", action);
  return useQuery({
    queryKey: authScopedQueryKey(
      ["admin", "audit-logs", page, action] as const,
      token,
    ),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        const filtered = action
          ? DEMO_AUDIT_LOGS.items.filter((item) => item.action === action)
          : DEMO_AUDIT_LOGS.items;
        return Promise.resolve({
          items: filtered,
          total: filtered.length,
        });
      }
      return apiClient<AuditLogListResponse>(`/admin/audit-logs?${params}`, {
        token: token || undefined,
        signal,
      });
    },
    enabled: DEMO_MODE_ENABLED || !!token,
  });
}

export function useAdminTasks() {
  const token = useAuthToken();
  return useQuery({
    queryKey: authScopedQueryKey(["admin", "tasks"] as const, token),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(DEMO_TASKS);
      }
      return apiClient<TaskQueueResponse>("/admin/tasks", {
        token: token || undefined,
        signal,
      });
    },
    refetchInterval: DEMO_MODE_ENABLED ? false : 10_000,
    enabled: DEMO_MODE_ENABLED || !!token,
    // Background task-queue poll (every 10s) — a transient failure should not
    // raise a global error toast on each tick.
    meta: { suppressGlobalErrorToast: true },
  });
}

export function useAdminOperations() {
  const token = useAuthToken();
  return useQuery({
    queryKey: authScopedQueryKey(["admin", "operations"] as const, token),
    queryFn: ({ signal }) =>
      apiClient<AdminOperationListResponse>("/admin/operations", {
        token: token || undefined,
        signal,
      }),
    enabled: !DEMO_MODE_ENABLED && !!token,
    refetchInterval: 15_000,
    meta: { suppressGlobalErrorToast: true },
  });
}

export function useReconcileAdminOperation() {
  const token = useAuthToken();
  const queryClient = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  return useMutation({
    mutationFn: ({
      operationId,
      recoveryAction,
    }: {
      operationId: string;
      recoveryAction?: "retry_rejected_role";
    }) =>
      apiClient<AdminOperationStatus>(
        `/admin/operations/${operationId}/reconcile`,
        {
          token: token || undefined,
          method: "POST",
          body: recoveryAction
            ? JSON.stringify({ recovery_action: recoveryAction })
            : undefined,
        },
      ),
    meta: { suppressGlobalErrorToast: true },
    onSuccess: (status) => {
      invalidateAuthScopedQueries(queryClient, ["admin", "operations"], token);
      invalidateAuthScopedQueries(queryClient, ["admin", "users"], token);
      invalidateAuthScopedQueries(
        queryClient,
        ["admin", "organizations"],
        token,
      );
      addToast(
        status.state === "completed"
          ? "Admin operation reconciled and confirmed."
          : "Admin operation is confirmed as not applied.",
        status.state === "completed" ? "success" : "error",
      );
    },
    onError: (error) => {
      logError(error, { source: "useReconcileAdminOperation" });
      addToast(
        "Reconciliation could not confirm provider state yet. The operation remains protected from duplicate submission.",
        "error",
      );
      invalidateAuthScopedQueries(queryClient, ["admin", "operations"], token);
    },
  });
}

export function useUpdateUserRole() {
  const token = useAuthToken();
  const queryClient = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const operationKeys = useRef(new Map<string, string>());
  const [operationNotice, setOperationNotice] =
    useState<AdminOperationNotice | null>(null);
  const mutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) => {
      const requestIdentity = JSON.stringify({ role, userId });
      const idempotencyKey =
        operationKeys.current.get(requestIdentity) ?? crypto.randomUUID();
      operationKeys.current.set(requestIdentity, idempotencyKey);
      return apiClient(`/admin/users/${userId}/role`, {
        token: token || undefined,
        method: "PATCH",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify({ role }),
      });
    },
    meta: { suppressGlobalErrorToast: true },
    onSuccess: (_data, { userId, role }) => {
      const requestIdentity = JSON.stringify({ role, userId });
      operationKeys.current.delete(requestIdentity);
      setOperationNotice(null);
      invalidateAuthScopedQueries(queryClient, ["admin", "users"], token);
      invalidateAuthScopedQueries(queryClient, ["admin", "operations"], token);
    },
    onError: (err, { userId, role }) => {
      logError(err, { source: "useUpdateUserRole" });
      const requestIdentity = JSON.stringify({ role, userId });
      const message = adminMutationErrorMessage(err, "Role update");
      if (isAmbiguousAdminMutationError(err)) {
        setOperationNotice({
          kind: "unconfirmed",
          message,
          canReconcile: false,
        });
      } else {
        operationKeys.current.delete(requestIdentity);
        setOperationNotice({ kind: "failed", message, canReconcile: false });
      }
      addToast(message, "error");
      invalidateAuthScopedQueries(queryClient, ["admin", "users"], token);
      invalidateAuthScopedQueries(queryClient, ["admin", "operations"], token);
    },
  });

  return {
    ...mutation,
    operationNotice,
  };
}

export function useUpdateOrg() {
  const token = useAuthToken();
  const queryClient = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  return useMutation({
    mutationFn: ({
      orgId,
      data,
    }: {
      orgId: string;
      data: {
        plan?: string;
        max_analyses_per_month?: number;
        free_analyses_remaining?: number;
      };
    }) =>
      apiClient(`/admin/organizations/${orgId}`, {
        token: token || undefined,
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    meta: { suppressGlobalErrorToast: true },
    onSuccess: () => {
      invalidateAuthScopedQueries(
        queryClient,
        ["admin", "organizations"],
        token,
      );
    },
    onError: (err) => {
      logError(err, { source: "useUpdateOrg" });
      addToast(
        "Failed to update organization. Existing organization settings are unchanged.",
        "error",
      );
    },
  });
}

export function useInviteUser() {
  const token = useAuthToken();
  const queryClient = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const operationKeys = useRef(new Map<string, string>());
  const [operationNotice, setOperationNotice] =
    useState<AdminOperationNotice | null>(null);
  const mutation = useMutation({
    mutationFn: ({ email, role }: { email: string; role: string }) => {
      const requestIdentity = JSON.stringify({
        email: email.trim().toLowerCase(),
        role,
      });
      const idempotencyKey =
        operationKeys.current.get(requestIdentity) ?? crypto.randomUUID();
      operationKeys.current.set(requestIdentity, idempotencyKey);
      return apiClient("/admin/invite", {
        token: token || undefined,
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify({ email, role }),
      });
    },
    meta: { suppressGlobalErrorToast: true },
    onSuccess: (_data, { email, role }) => {
      const requestIdentity = JSON.stringify({
        email: email.trim().toLowerCase(),
        role,
      });
      operationKeys.current.delete(requestIdentity);
      setOperationNotice(null);
      invalidateAuthScopedQueries(queryClient, ["admin", "users"], token);
      invalidateAuthScopedQueries(queryClient, ["admin", "operations"], token);
      // An invite increments the org's user_count shown in the admin
      // organizations table; invalidate it so that count does not go stale.
      invalidateAuthScopedQueries(
        queryClient,
        ["admin", "organizations"],
        token,
      );
    },
    onError: (err, { email, role }) => {
      logError(err, { source: "useInviteUser" });
      const requestIdentity = JSON.stringify({
        email: email.trim().toLowerCase(),
        role,
      });
      const message = adminMutationErrorMessage(err, "Invitation");
      if (isAmbiguousAdminMutationError(err)) {
        setOperationNotice({
          kind: "unconfirmed",
          message,
          canReconcile: false,
        });
      } else {
        operationKeys.current.delete(requestIdentity);
        setOperationNotice({ kind: "failed", message, canReconcile: false });
      }
      addToast(message, "error");
      invalidateAuthScopedQueries(queryClient, ["admin", "users"], token);
      invalidateAuthScopedQueries(
        queryClient,
        ["admin", "organizations"],
        token,
      );
      invalidateAuthScopedQueries(queryClient, ["admin", "operations"], token);
    },
  });

  return {
    ...mutation,
    operationNotice,
  };
}

export type {
  SystemHealth,
  ServiceHealth,
  AdminCapabilities,
  OrgSummary,
  OrgListResponse,
  UserSummary,
  UserListResponse,
  DailyMetric,
  MetricsResponse,
  AuditLogEntry,
  AuditLogListResponse,
  TaskInfo,
  TaskQueueResponse,
  AdminOperationStatus,
  AdminOperationNotice,
};
