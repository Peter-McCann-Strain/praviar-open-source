"use client";

import Link from "next/link";
import {
  ArrowRight,
  Clock3,
  FileText,
  ListFilter,
  LockKeyhole,
  SlidersHorizontal,
} from "lucide-react";
import { useState } from "react";
import { useHydrationSafeRelativeTime } from "@/hooks/use-hydration-safe-relative-time";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { RiskDonut } from "@/components/charts/risk-donut";
import { RiskBadge } from "@/components/shared/risk-badge";
import { StatusBadge } from "@/components/shared/status-badge";
import {
  type DashboardPriorityDocketItem,
  RISK_LEGEND_COLORS,
  relativeTime,
} from "@/components/dashboard/helpers";
import { getReportAccessHref } from "@/lib/report-permissions";
import { cn } from "@/lib/utils";
import type { AnalysisListItem } from "@/types/api";

interface RiskDistributionItem {
  level: string;
  count: number;
}

interface RiskActivitySectionProps {
  priorityDocket: DashboardPriorityDocketItem[];
  recentAnalyses: AnalysisListItem[];
  riskRatingsRestricted?: boolean;
  riskDistribution: RiskDistributionItem[];
  sampleWindowSize: number;
}

const REVIEW_STATUS_LABELS: Record<string, string> = {
  approved: "Approved",
  changes_requested: "Changes requested",
  under_review: "Under review",
};

const RISK_FILL_CLASSES: Record<string, string> = {
  clear: "bg-info",
  high: "bg-error",
  low: "bg-success",
  medium: "bg-warning",
};

const RISK_ROW_RAIL_CLASSES: Record<string, string> = {
  clear: "border-l-info",
  high: "border-l-error",
  low: "border-l-success",
  medium: "border-l-warning",
};

const REASON_TONE_CLASSES: Record<
  DashboardPriorityDocketItem["reasonTone"],
  string
> = {
  critical: "border-error/25 bg-error/10 text-[var(--text-primary)]",
  warning: "border-warning/25 bg-warning/10 text-[var(--text-primary)]",
  info: "border-info/25 bg-info/10 text-[var(--text-primary)]",
  neutral:
    "border-[var(--border-subtle)] bg-[var(--surface-glass)] text-[var(--text-secondary)]",
};

function getPersistedReviewLabel(analysis: AnalysisListItem): string | null {
  const reviewStatus = analysis.review_status;
  if (!reviewStatus?.is_persisted || reviewStatus.status === "pending") {
    return null;
  }

  return REVIEW_STATUS_LABELS[reviewStatus.status] ?? reviewStatus.status;
}

function getActivitySummary(analysis: AnalysisListItem): string {
  const summary = analysis.executive_summary.trim();
  if (summary) {
    return summary;
  }

  if (analysis.status === "running") {
    return "Evidence packet is still building through source search, patent triage, and claim-review steps.";
  }
  if (analysis.status === "pending") {
    return "Analysis is queued and will begin evidence collection when launch capacity is available.";
  }
  if (analysis.status === "failed") {
    return "Run failed before a complete evidence packet could be assembled.";
  }
  if (analysis.status === "cancelled") {
    return "Run cancelled before the evidence packet was finalized.";
  }
  return "Evidence packet is ready for source inspection, claim review, and report handoff.";
}

function getDashboardAnalysisHref(analysis: AnalysisListItem): string {
  if (analysis.status !== "completed") {
    return `/analyses/${analysis.id}`;
  }

  const reportHref = getReportAccessHref(
    analysis.id,
    analysis.current_user_role,
    analysis.risk_ratings_restricted,
  );
  if (
    !analysis.risk_ratings_restricted &&
    (analysis.blocking_patents_count ?? 0) > 0
  ) {
    return `${reportHref}?tab=patents`;
  }

  return reportHref;
}

function getRecentReason(
  analysis: AnalysisListItem,
): DashboardPriorityDocketItem {
  if (analysis.status === "running") {
    return {
      analysis,
      reason: `Running step ${analysis.current_step}/8`,
      reasonTone: "info",
    };
  }
  if (analysis.status === "failed") {
    return { analysis, reason: "Run failed", reasonTone: "critical" };
  }
  if (analysis.status === "pending") {
    return { analysis, reason: "Pending launch", reasonTone: "neutral" };
  }
  if (
    analysis.review_status?.is_persisted &&
    analysis.review_status.status === "changes_requested"
  ) {
    return {
      analysis,
      reason: "Changes requested",
      reasonTone: "critical",
    };
  }
  if (
    !analysis.risk_ratings_restricted &&
    (analysis.blocking_patents_count ?? 0) > 0
  ) {
    return {
      analysis,
      reason: `${(analysis.blocking_patents_count ?? 0).toLocaleString()} blocking patent${
        analysis.blocking_patents_count === 1 ? "" : "s"
      }`,
      reasonTone: "critical",
    };
  }
  if (analysis.share_active) {
    const viewCount = analysis.share_view_count ?? 0;
    return {
      analysis,
      reason:
        viewCount > 0
          ? `Shared with ${viewCount.toLocaleString()} view${viewCount === 1 ? "" : "s"}`
          : "Shared report active",
      reasonTone: "info",
    };
  }
  return { analysis, reason: "Recent movement", reasonTone: "neutral" };
}

export function RiskActivitySection({
  priorityDocket,
  recentAnalyses,
  riskRatingsRestricted = false,
  riskDistribution,
  sampleWindowSize,
}: RiskActivitySectionProps) {
  const formatRelativeTime = useHydrationSafeRelativeTime(relativeTime);
  const [viewMode, setViewMode] = useState<"action" | "recent">("action");
  const riskData = riskDistribution.map((item) => ({
    level: item.level.toUpperCase(),
    count: item.count,
  }));
  const riskTotal = riskDistribution.reduce((sum, item) => sum + item.count, 0);
  const actionRows = priorityDocket.length
    ? priorityDocket
    : recentAnalyses.map(getRecentReason);
  const recentRows = recentAnalyses.map(getRecentReason);
  const visibleRows = viewMode === "action" ? actionRows : recentRows;
  const isActionMode = viewMode === "action";

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
      <Card className="overflow-hidden">
        {riskRatingsRestricted ? (
          <>
            <CardHeader className="p-5 pb-3">
              <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
                Decision boundary
              </p>
              <CardTitle className="text-sm">
                Counsel-only risk posture
              </CardTitle>
              <CardDescription>
                Risk distribution is intentionally unavailable for this role.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-5 pt-0">
              <div className="rounded-lg border border-warning/25 bg-warning/8 p-4">
                <span className="flex h-10 w-10 items-center justify-center rounded-md border border-warning/25 bg-[var(--bg-surface)] text-warning">
                  <LockKeyhole className="h-4 w-4" aria-hidden="true" />
                </span>
                <p className="mt-4 text-sm font-semibold text-[var(--text-primary)]">
                  No zero-risk inference
                </p>
                <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
                  Hidden ratings and blocker counts are not converted to zero.
                  Ask counsel or an authorized workspace owner for the governed
                  risk distribution.
                </p>
              </div>
            </CardContent>
          </>
        ) : (
          <>
            <CardHeader className="p-5 pb-3">
              <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
                Decision mix
              </p>
              <CardTitle className="text-sm">Risk Distribution</CardTitle>
              <CardDescription>
                {riskTotal} classified{" "}
                {riskTotal === 1 ? "analysis" : "analyses"}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5 p-5 pt-0">
              <RiskDonut data={riskData} size={190} centerLabel="analyses" />
              <div className="space-y-3">
                {riskDistribution.map((item) => (
                  <div key={item.level} className="space-y-1.5 text-xs">
                    <div className="flex items-center justify-between gap-3">
                      <span className="flex items-center gap-2 capitalize text-[var(--text-secondary)]">
                        <span
                          className={`h-2.5 w-2.5 rounded-sm ${
                            RISK_FILL_CLASSES[item.level] ??
                            "bg-[var(--text-disabled)]"
                          }`}
                        />
                        {item.level}
                      </span>
                      <span
                        className={`font-semibold tabular-nums ${
                          RISK_LEGEND_COLORS[item.level] ??
                          "text-[var(--text-primary)]"
                        }`}
                      >
                        {item.count}
                      </span>
                    </div>
                    <div
                      className="h-1.5 overflow-hidden rounded-full bg-[var(--surface-subtle)]"
                      aria-hidden="true"
                    >
                      <span
                        className={`block h-full rounded-full ${
                          RISK_FILL_CLASSES[item.level] ??
                          "bg-[var(--text-disabled)]"
                        }`}
                        style={{
                          width:
                            riskTotal > 0
                              ? `${Math.max(
                                  (item.count / riskTotal) * 100,
                                  item.count > 0 ? 5 : 0,
                                )}%`
                              : "0%",
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </>
        )}
      </Card>

      <Card className="overflow-hidden lg:col-span-2">
        <CardHeader className="border-b border-[var(--border-subtle)] p-5">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
                Evidence docket
              </p>
              <CardTitle className="text-sm">
                {isActionMode ? "Action docket" : "Recent activity"}
              </CardTitle>
              <CardDescription>
                {isActionMode
                  ? `Ranked attention view across the latest ${sampleWindowSize.toLocaleString()} analyses in the dashboard metric window.`
                  : "Latest report movement across analysis, legal review, and share handoff."}
              </CardDescription>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <div
                className="inline-flex rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/60 p-1"
                role="group"
                aria-label="Evidence docket view"
              >
                <button
                  type="button"
                  aria-pressed={isActionMode}
                  onClick={() => setViewMode("action")}
                  className={cn(
                    "inline-flex min-h-11 items-center justify-center gap-1.5 rounded-md px-3 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70",
                    isActionMode
                      ? "bg-brand-primary text-[var(--brand-paper)] shadow-[var(--shadow-xs)]"
                      : "text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
                  )}
                >
                  <SlidersHorizontal
                    className="h-3.5 w-3.5"
                    aria-hidden="true"
                  />
                  Action
                </button>
                <button
                  type="button"
                  aria-pressed={!isActionMode}
                  onClick={() => setViewMode("recent")}
                  className={cn(
                    "inline-flex min-h-11 items-center justify-center gap-1.5 rounded-md px-3 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70",
                    !isActionMode
                      ? "bg-[var(--bg-surface)] text-brand-primary shadow-[var(--shadow-xs)]"
                      : "text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
                  )}
                >
                  <Clock3 className="h-3.5 w-3.5" aria-hidden="true" />
                  Recent
                </button>
              </div>
              <Button asChild variant="ghost" size="sm" className="min-h-11">
                <Link href="/analyses" className="gap-1.5">
                  View all analyses
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="hidden border-b border-[var(--border-subtle)] bg-[var(--surface-muted)]/32 px-5 py-3 text-xs font-medium text-[var(--text-tertiary)] md:grid md:grid-cols-[minmax(0,1fr)_minmax(9rem,14rem)_minmax(5rem,6rem)_minmax(5rem,7rem)] md:gap-4">
            <span>Analysis</span>
            <span className="inline-flex items-center gap-1">
              <ListFilter className="h-3.5 w-3.5" aria-hidden="true" />
              Reason
            </span>
            <span>{riskRatingsRestricted ? "Risk access" : "Risk"}</span>
            <span>Updated</span>
          </div>
          <ul
            className="divide-y divide-[var(--border-subtle)]"
            aria-label={
              isActionMode
                ? "Action docket analyses"
                : "Recent activity analyses"
            }
          >
            {visibleRows.map((row) => {
              const analysis = row.analysis;
              const reviewLabel = getPersistedReviewLabel(analysis);
              const analysisHref = getDashboardAnalysisHref(analysis);

              return (
                <li key={analysis.id}>
                  <Link
                    href={analysisHref}
                    className={`group grid min-w-0 gap-3 border-l-2 px-5 py-4 transition-colors hover:bg-[var(--surface-subtle)] md:grid-cols-[minmax(0,1fr)_minmax(9rem,14rem)_minmax(5rem,6rem)_minmax(5rem,7rem)] md:items-start md:gap-4 ${
                      analysis.status === "running"
                        ? "border-l-info"
                        : riskRatingsRestricted ||
                            analysis.risk_ratings_restricted
                          ? "border-l-warning"
                          : (RISK_ROW_RAIL_CLASSES[
                              analysis.overall_risk ?? ""
                            ] ?? "border-l-[var(--border-subtle)]")
                    }`}
                  >
                    <div className="min-w-0 space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className="min-w-0 max-w-full truncate text-sm font-semibold text-[var(--text-primary)] transition-colors group-hover:text-brand-primary"
                          title={analysis.compound_name}
                        >
                          {analysis.compound_name}
                        </span>
                        {analysis.status === "running" ? (
                          <StatusBadge status={analysis.status} />
                        ) : null}
                        {reviewLabel ? (
                          <span className="rounded-full border border-info/20 bg-info/10 px-2 py-0.5 text-xs font-medium text-info">
                            {reviewLabel}
                          </span>
                        ) : null}
                      </div>
                      <p className="line-clamp-2 text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                        {getActivitySummary(analysis)}
                      </p>
                      <div className="flex flex-wrap gap-2 text-xs text-[var(--text-tertiary)]">
                        <span className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-glass)] px-2 py-1">
                          <FileText className="h-3 w-3" />
                          <span className="tabular-nums">
                            {analysis.total_patents_found}
                          </span>
                          patents
                        </span>
                        {analysis.share_active ? (
                          <span className="rounded-md border border-info/20 bg-info/10 px-2 py-1 text-info">
                            Shared
                            {analysis.share_view_count
                              ? ` · ${analysis.share_view_count} views`
                              : ""}
                          </span>
                        ) : null}
                      </div>
                    </div>
                    <div className="min-w-0">
                      <span
                        className={cn(
                          "inline-flex max-w-full items-center rounded-md border px-2 py-1 text-xs font-semibold leading-4",
                          REASON_TONE_CLASSES[row.reasonTone],
                        )}
                      >
                        <span className="truncate">{row.reason}</span>
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-[var(--text-secondary)] md:block">
                      <span className="text-[var(--text-tertiary)] md:hidden">
                        Risk
                      </span>
                      {analysis.status !== "completed" ? (
                        <span className="font-medium text-[var(--text-tertiary)]">
                          {analysis.status === "running"
                            ? "Pending classification"
                            : "Unclassified"}
                        </span>
                      ) : riskRatingsRestricted ||
                        analysis.risk_ratings_restricted ? (
                        <span className="font-medium text-warning">
                          Counsel only
                        </span>
                      ) : !analysis.overall_risk ? (
                        <span className="tabular-nums text-[var(--text-tertiary)]">
                          -
                        </span>
                      ) : (
                        <RiskBadge risk={analysis.overall_risk} size="sm" />
                      )}
                    </div>
                    <span className="flex items-center justify-between gap-2 text-xs tabular-nums text-[var(--text-tertiary)] md:flex-col md:items-start">
                      <span>{formatRelativeTime(analysis.updated_at)}</span>
                      <ArrowRight className="h-3.5 w-3.5 text-brand-primary opacity-0 transition-opacity group-hover:opacity-100" />
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
