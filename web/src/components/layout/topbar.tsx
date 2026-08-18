"use client";

import { usePathname } from "next/navigation";
import { ChevronRight, ClipboardCheck, Menu, Plus } from "lucide-react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { PraviarLockup } from "@/components/brand/praviar-lockup";
import { Button } from "@/components/ui/button";
import { NotificationBell } from "@/components/shared/notification-bell";
import { useAuthToken } from "@/hooks/use-auth-token";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";
import { DEMO_MODE_ENABLED, DEV_AUTH_BYPASS_ENABLED } from "@/lib/constants";
import {
  getDemoAnalysis,
  isDemoAnalysisId,
  isSeedDemoAnalysisId,
} from "@/lib/demo-data";
import {
  authScopedQueryKey,
  matchesAuthScopedQueryKey,
} from "@/lib/query-keys";
import { useClientReady } from "@/hooks/use-client-ready";
import { useUIStore } from "@/stores/ui-store";

const BREADCRUMB_MAP: Record<string, string> = {
  dashboard: "Dashboard",
  analyses: "Analyses",
  compounds: "Compounds",
  patents: "Patents",
  config: "Configuration",
  presets: "Presets",
  activity: "Activity",
  team: "Team",
  settings: "Settings",
  notifications: "Notification settings",
  billing: "Credits & Billing",
  help: "Help & Docs",
  new: "New Analysis",
  quick: "Adaptive Launch",
  report: "Report",
  summary: "Summary",
  compare: "Compare",
  batch: "Batch",
  watch: "Patent Watch",
  monitors: "Monitors",
  reviews: "Reviews",
  capabilities: "Workflow Atlas",
  admin: "Platform Admin",
  integrations: "Integrations",
  analytics: "Cost & Usage",
};

function resolveLabel(segment: string, _prevSegment?: string): string {
  // Check known labels first
  if (BREADCRUMB_MAP[segment]) return BREADCRUMB_MAP[segment];

  // If it looks like an ID (contains hyphens, numbers), truncate it
  if (/^[a-z0-9-]+$/i.test(segment) && segment.length > 8) {
    return segment.slice(0, 12) + "...";
  }

  return segment;
}

export function Topbar() {
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const mobileSidebarOpen = useUIStore((s) => s.mobileSidebarOpen);
  const setMobileSidebarOpen = useUIStore((s) => s.setMobileSidebarOpen);
  const clientReady = useClientReady();
  const segments = pathname.split("/").filter(Boolean);

  // Try to resolve analysis IDs from query cache for breadcrumbs
  function resolveAnalysisName(id: string): string | undefined {
    // Check query cache for individual analysis
    const cached = queryClient.getQueryData<{ compound_name?: string }>(
      authScopedQueryKey(["analyses", id] as const, token),
    );
    if (cached?.compound_name) return cached.compound_name;

    // Check analyses list cache (API returns { items: [...], total, page, per_page })
    const analysisLists = queryClient.getQueriesData<{
      items?: { compound_name?: string; id: string }[];
    }>({
      queryKey: ["analyses"],
      predicate: (query) =>
        matchesAuthScopedQueryKey(query.queryKey, ["analyses"] as const, token),
    });

    for (const [, listData] of analysisLists) {
      const match = listData?.items?.find((a) => a.id === id);
      if (match?.compound_name) return match.compound_name;
    }

    if (
      (DEMO_MODE_ENABLED || DEV_AUTH_BYPASS_ENABLED) &&
      isDemoAnalysisId(id) &&
      (isSeedDemoAnalysisId(id) || clientReady)
    ) {
      return getDemoAnalysis(id)?.compound_name;
    }

    return undefined;
  }

  return (
    <header
      className="sticky top-0 z-30 flex h-14 min-h-14 items-center gap-3 border-b border-[var(--border-default)] bg-[var(--bg-nav)]/88 px-3 shadow-[var(--shadow-xs)] backdrop-blur-xl sm:gap-4 sm:px-4 md:px-6"
      data-praviar-topbar-workbench
    >
      {/* Mobile hamburger */}
      <button
        type="button"
        onClick={() => setMobileSidebarOpen(true)}
        aria-label="Open navigation menu"
        aria-controls="dashboard-sidebar"
        aria-expanded={mobileSidebarOpen}
        data-praviar-mobile-menu-button
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 lg:hidden"
      >
        <Menu className="h-5 w-5" aria-hidden="true" />
      </button>

      <Link
        href="/dashboard"
        aria-label="Praviar dashboard"
        className="flex h-12 min-w-0 shrink items-center gap-2 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 lg:hidden"
        data-praviar-brand-lockup
        translate="no"
      >
        <PraviarLockup size="topbar" />
      </Link>

      {/* Breadcrumbs */}
      <nav
        aria-label="Breadcrumb"
        className="hidden min-w-0 flex-1 items-center gap-1.5 overflow-hidden text-sm lg:flex"
      >
        {segments.map((segment, i) => {
          const prevSegment = i > 0 ? segments[i - 1] : undefined;
          const isNotificationSettingsParent =
            pathname === "/settings/notifications" && i === 0;
          const labelSegment = isNotificationSettingsParent
            ? "dashboard"
            : segment;
          // Try query cache first for analysis IDs, fall back to static resolver
          const label =
            prevSegment === "analyses" && !BREADCRUMB_MAP[labelSegment]
              ? (resolveAnalysisName(segment) ??
                resolveLabel(segment, prevSegment))
              : resolveLabel(labelSegment, prevSegment);
          const href = isNotificationSettingsParent
            ? "/dashboard"
            : "/" + segments.slice(0, i + 1).join("/");
          const isLast = i === segments.length - 1;

          return (
            <span key={href} className="flex min-w-0 items-center gap-1.5">
              {i > 0 && (
                <ChevronRight
                  aria-hidden="true"
                  className="h-3.5 w-3.5 shrink-0 text-[var(--text-disabled)]"
                  data-praviar-breadcrumb-separator
                />
              )}
              {isLast ? (
                <span
                  aria-current="page"
                  className="inline-flex min-h-11 min-w-0 max-w-[32ch] items-center overflow-hidden rounded-md border border-[var(--border-subtle)] bg-[var(--surface-glass)] px-2.5 py-1 text-xs font-semibold text-[var(--text-primary)] shadow-[var(--shadow-xs)]"
                  title={label}
                >
                  <span className="min-w-0 flex-1 truncate">{label}</span>
                </span>
              ) : (
                <Link
                  href={href}
                  className="inline-flex min-h-11 max-w-[22ch] items-center rounded-md px-2 py-1 text-xs font-medium text-[var(--text-tertiary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]"
                  title={label}
                >
                  {label}
                </Link>
              )}
            </span>
          );
        })}
      </nav>

      {/* Workspace actions */}
      <div className="ml-auto flex flex-shrink-0 items-center gap-2">
        <NotificationBell />
        {principal.data?.can_view_review_queue === true ? (
          <Button
            asChild
            size="sm"
            variant="ghost"
            className="hidden min-h-11 gap-1.5 text-[var(--text-secondary)] sm:flex"
          >
            <Link href="/reviews">
              <ClipboardCheck
                className="h-3.5 w-3.5 text-info"
                aria-hidden="true"
              />
              Review Queue
            </Link>
          </Button>
        ) : null}
        {principal.data?.can_create_analysis === true ? (
          <Button
            asChild
            size="sm"
            className="min-h-11 w-11 min-w-11 shrink-0 gap-1.5 sm:w-auto"
          >
            <Link href="/analyses/new" aria-label="New Analysis">
              <Plus className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="hidden sm:inline">New Analysis</span>
            </Link>
          </Button>
        ) : null}
      </div>
    </header>
  );
}
