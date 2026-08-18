"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import { authScopedQueryKey } from "@/lib/query-keys";
import { canAccessFullReport } from "@/lib/report-permissions";

export type ApplicationRole = "admin" | "attorney" | "scientist" | "client";

export interface PrincipalCapabilities {
  role: ApplicationRole;
  can_create_analysis: boolean;
  can_view_patents: boolean;
  can_manage_monitors: boolean;
  can_view_review_queue: boolean;
  can_assign_review: boolean;
  can_resolve_review: boolean;
  can_escalate_review: boolean;
  can_create_batch: boolean;
  can_manage_config: boolean;
  can_export_report: boolean;
  can_share_report: boolean;
  can_deliver_report: boolean;
  can_view_billing: boolean;
  can_manage_billing: boolean;
  can_manage_api_keys: boolean;
  can_view_platform_admin: boolean;
  risk_ratings_restricted: boolean;
  api_key_report_export_scope_available: boolean;
}

export function canAccessWorkspaceHref(
  capabilities: Partial<PrincipalCapabilities> | null | undefined,
  href: string,
): boolean {
  if (href.startsWith("#") || href.startsWith("/sample-reports/")) {
    return true;
  }
  const pathname = href.split(/[?#]/u, 1)[0] ?? href;

  if (pathname === "/analyses/new") {
    return capabilities?.can_create_analysis === true;
  }
  if (pathname === "/patents" || pathname.startsWith("/patents/")) {
    return capabilities?.can_view_patents === true;
  }
  if (
    /^\/analyses\/[^/]+\/report(?:\/|$)/u.test(pathname) &&
    !pathname.endsWith("/report/summary")
  ) {
    return canAccessFullReport(
      capabilities?.role,
      capabilities?.risk_ratings_restricted,
    );
  }
  if (pathname === "/batch" || pathname.startsWith("/batch/")) {
    return capabilities?.can_create_batch === true;
  }
  if (pathname === "/reviews" || pathname.startsWith("/reviews/")) {
    return capabilities?.can_view_review_queue === true;
  }
  if (pathname === "/monitors" || pathname.startsWith("/monitors/")) {
    return capabilities?.can_manage_monitors === true;
  }
  if (pathname === "/config" || pathname.startsWith("/config/")) {
    return capabilities?.can_manage_config === true;
  }
  if (pathname === "/billing" || pathname.startsWith("/billing/")) {
    return capabilities?.can_view_billing === true;
  }
  if (
    pathname === "/settings" ||
    (pathname.startsWith("/settings/") &&
      !pathname.startsWith("/settings/notifications"))
  ) {
    return capabilities?.can_manage_api_keys === true;
  }
  if (pathname === "/admin" || pathname.startsWith("/admin/")) {
    return capabilities?.can_view_platform_admin === true;
  }
  return true;
}

const DEMO_PRINCIPAL_CAPABILITIES: PrincipalCapabilities = {
  role: "admin",
  can_create_analysis: true,
  can_view_patents: true,
  can_manage_monitors: true,
  can_view_review_queue: true,
  can_assign_review: true,
  can_resolve_review: true,
  can_escalate_review: true,
  can_create_batch: true,
  can_manage_config: true,
  can_export_report: true,
  can_share_report: true,
  can_deliver_report: true,
  can_view_billing: true,
  can_manage_billing: true,
  can_manage_api_keys: true,
  can_view_platform_admin: true,
  risk_ratings_restricted: false,
  api_key_report_export_scope_available: false,
};

export function usePrincipalCapabilities(token: string | null) {
  const query = useQuery({
    queryKey: authScopedQueryKey(["principal-capabilities"] as const, token),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(DEMO_PRINCIPAL_CAPABILITIES);
      }
      return apiClient<PrincipalCapabilities>("/principal/capabilities", {
        token: token || undefined,
        signal,
      });
    },
    enabled: DEMO_MODE_ENABLED || !!token,
    initialData: DEMO_MODE_ENABLED ? DEMO_PRINCIPAL_CAPABILITIES : undefined,
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

  if (query.isError || query.isRefetchError) {
    return {
      ...query,
      data: undefined,
    };
  }

  return query;
}
