/**
 * SSO configuration hooks — TanStack Query wrappers for the SSO admin endpoints.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { useAuthToken } from "@/hooks/use-auth-token";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import {
  authScopedQueryKey,
  invalidateAuthScopedQueries,
} from "@/lib/query-keys";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface SSOStatus {
  sso_enabled: boolean;
  provider: string | null;
  domains: string[];
  status: "active" | "pending" | "inactive";
  clerk_dashboard_url: string | null;
  sso_status_available: boolean;
  sso_last_synced_at: string | null;
  sso_status_stale: boolean;
  sso_unavailable_reason:
    | "missing_secret"
    | "circuit_open"
    | "transport_error"
    | "not_found"
    | "provider_error"
    | "malformed_response"
    | null;
}

export interface SSOConfigureResponse {
  status: string;
  message: string;
  next_steps: string[];
  clerk_dashboard_url: string | null;
}

// ── Demo fixture ──────────────────────────────────────────────────────────────

let demoSSOStatus: SSOStatus = {
  sso_enabled: false,
  provider: null,
  domains: [],
  status: "inactive",
  clerk_dashboard_url: null,
  sso_status_available: true,
  sso_last_synced_at: new Date().toISOString(),
  sso_status_stale: false,
  sso_unavailable_reason: null,
};

// ── Hooks ─────────────────────────────────────────────────────────────────────

export function useSSOStatus() {
  const token = useAuthToken();
  return useQuery({
    queryKey: authScopedQueryKey(["admin", "sso", "status"] as const, token),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(demoSSOStatus);
      }
      return apiClient<SSOStatus>("/admin/sso/status", {
        token: token || undefined,
        signal,
      });
    },
    enabled: DEMO_MODE_ENABLED || !!token,
    staleTime: 30_000,
    refetchInterval: 4 * 60_000,
  });
}

export function useConfigureSSO() {
  const token = useAuthToken();
  const queryClient = useQueryClient();
  return useMutation({
    meta: { suppressGlobalErrorToast: true },
    mutationFn: (enable: boolean) => {
      if (DEMO_MODE_ENABLED) {
        demoSSOStatus = enable
          ? {
              // Requesting setup is not the same as an active connection.
              sso_enabled: false,
              provider: "Demo IdP",
              domains: ["demo.praviar.local"],
              status: "pending",
              clerk_dashboard_url: "/settings?demo_sso=clerk",
              sso_status_available: true,
              sso_last_synced_at: new Date().toISOString(),
              sso_status_stale: false,
              sso_unavailable_reason: null,
            }
          : {
              sso_enabled: false,
              provider: null,
              domains: [],
              status: "inactive",
              clerk_dashboard_url: null,
              sso_status_available: true,
              sso_last_synced_at: new Date().toISOString(),
              sso_status_stale: false,
              sso_unavailable_reason: null,
            };

        return Promise.resolve<SSOConfigureResponse>({
          status: enable ? "pending" : "inactive",
          message: enable
            ? "Demo SSO setup is ready to complete in Clerk."
            : "Demo SSO disable flow is ready to complete in Clerk.",
          next_steps: enable
            ? [
                "Open the Clerk dashboard.",
                "Connect your identity provider.",
                "Verify an enrolled domain before enforcing SSO.",
              ]
            : [
                "Open the Clerk dashboard.",
                "Disable the enterprise connection.",
                "Confirm users can still sign in through another method.",
              ],
          clerk_dashboard_url: demoSSOStatus.clerk_dashboard_url,
        });
      }
      return apiClient<SSOConfigureResponse>("/admin/sso/configure", {
        token: token || undefined,
        method: "POST",
        body: JSON.stringify({ enable }),
      });
    },
    onSuccess: () => {
      invalidateAuthScopedQueries(queryClient, ["admin", "sso"], token);
      invalidateAuthScopedQueries(queryClient, ["setup-readiness"], token);
    },
  });
}
