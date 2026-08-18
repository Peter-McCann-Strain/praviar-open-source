"use client";

import Link from "next/link";
import { ArrowRight, AlertTriangle, Clock3, Inbox, Users } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useAuthBoundaryReset } from "@/hooks/use-auth-boundary-reset";
import { useHydrationSafeRelativeTime } from "@/hooks/use-hydration-safe-relative-time";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { LegalReviewSpotlightActions } from "@/components/dashboard/legal-review-spotlight-actions";
import {
  ReviewQueueBulkToolbar,
  type ReviewQueueBulkActionSuccess,
} from "@/components/reviews/review-queue-bulk-toolbar";
import {
  buildBulkActionChangeSummary,
  buildBulkActionFeedbackMessage,
} from "@/components/reviews/review-queue-feedback";
import { REVIEW_QUEUE_LOAD_ERROR_COPY } from "@/components/reviews/review-queue-errors";
import {
  buildReviewQueueItemHref,
  getReviewQueueItemActionLabel,
  getReviewQueueItemSpotlightActionLabel,
} from "@/components/reviews/review-queue-routing";
import { cn } from "@/lib/utils";
import { relativeTime } from "@/components/dashboard/helpers";
import {
  type ReviewQueueCounts,
  type ReviewQueueFilter,
  useReviewQueue,
  type ReviewQueueItem,
  type ReviewQueueResult,
} from "@/hooks/use-review-queue";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";

interface LegalReviewWorkloadPanelProps {
  token: string | null;
}

const DASHBOARD_REVIEW_QUEUE_PREVIEW_LIMIT = 3;

const FILTERS: Array<{
  value: ReviewQueueFilter;
  label: string;
  icon: typeof Users;
}> = [
  { value: "mine", label: "Mine", icon: Users },
  { value: "unassigned", label: "Unassigned", icon: Inbox },
  { value: "overdue", label: "Overdue", icon: Clock3 },
  { value: "escalated", label: "Escalated", icon: AlertTriangle },
];

const WATCH_WINDOW_HOURS = 24;
const AT_RISK_NEXT_HOURS = 36;

function buildQueueHref(filter: ReviewQueueFilter) {
  return `/reviews?filter=${filter}&sort=priority`;
}

function buildOwnedFocusHref(focus: "my-overdue" | "my-escalated") {
  return `/reviews?focus=${focus}&sort=priority`;
}

function buildReportHref(
  item: ReviewQueueItem,
  currentUserRole?: string | null,
  riskRatingsRestricted?: boolean,
) {
  return buildReviewQueueItemHref(item, currentUserRole, riskRatingsRestricted);
}

function formatQueueAge(ageHours: number | null) {
  if (ageHours == null || ageHours <= 0) {
    return null;
  }

  if (ageHours >= 48) {
    const dayCount = Math.max(1, Math.floor(ageHours / 24));
    return `${dayCount}d open`;
  }

  return `${Math.round(ageHours)}h open`;
}

function isAtRiskNext(item: ReviewQueueItem) {
  return !item.is_overdue && (item.queue_age_hours ?? 0) >= AT_RISK_NEXT_HOURS;
}

function isWatchWindow(item: ReviewQueueItem) {
  const ageHours = item.queue_age_hours ?? 0;
  return (
    !item.is_overdue &&
    ageHours >= WATCH_WINDOW_HOURS &&
    ageHours < AT_RISK_NEXT_HOURS
  );
}

function formatAssignee(item: ReviewQueueItem): string {
  if (item.is_unassigned) {
    return "Unassigned";
  }

  return item.assigned_to_name ?? item.assigned_to_email ?? "Assigned";
}

function getItemPriorityScore(item: ReviewQueueItem) {
  if (item.is_overdue && item.is_escalated) return 0;
  if (item.is_overdue) return 1;
  if (isAtRiskNext(item)) return 2;
  if (item.is_escalated) return 3;
  if (isWatchWindow(item)) return 4;
  return 5;
}

function compareQueueItems(left: ReviewQueueItem, right: ReviewQueueItem) {
  const priorityDelta =
    getItemPriorityScore(left) - getItemPriorityScore(right);
  if (priorityDelta !== 0) {
    return priorityDelta;
  }

  const activityDelta =
    Date.parse(left.last_activity_at) - Date.parse(right.last_activity_at);
  if (activityDelta !== 0) {
    return activityDelta;
  }

  return left.compound_name.localeCompare(right.compound_name);
}

function getUrgencyLabel(item: ReviewQueueItem) {
  if (item.is_overdue && item.is_escalated) {
    return item.overdue_label ?? "Overdue + escalated";
  }

  if (item.is_overdue) {
    return item.overdue_label ?? "Overdue";
  }

  if (isAtRiskNext(item)) {
    return `At risk next${formatQueueAge(item.queue_age_hours) ? ` · ${formatQueueAge(item.queue_age_hours)}` : ""}`;
  }

  if (item.is_escalated) {
    return "Escalated";
  }

  return "Owned";
}

function summarizeActivityContext(item: ReviewQueueItem) {
  const rawContext = item.comment_body.trim().replace(/\s+/g, " ");

  if (!rawContext) {
    return "No recent comment context.";
  }

  if (rawContext.length <= 110) {
    return rawContext;
  }

  return `${rawContext.slice(0, 107).trimEnd()}...`;
}

function getItemFlags(item: ReviewQueueItem): Array<{
  label: string;
  variant: "default" | "warning" | "destructive" | "outline";
}> {
  const flags: Array<{
    label: string;
    variant: "default" | "warning" | "destructive" | "outline";
  }> = [];

  if (item.is_mine) {
    flags.push({ label: "Mine", variant: "default" });
  }
  if (item.is_unassigned) {
    flags.push({ label: "Unassigned", variant: "outline" });
  }
  if (item.is_overdue) {
    flags.push({ label: item.overdue_label ?? "Overdue", variant: "warning" });
  }
  if (isAtRiskNext(item)) {
    flags.push({
      label: `At risk next${formatQueueAge(item.queue_age_hours) ? ` · ${formatQueueAge(item.queue_age_hours)}` : ""}`,
      variant: "warning",
    });
  } else if (isWatchWindow(item)) {
    flags.push({
      label: `Watch window${formatQueueAge(item.queue_age_hours) ? ` · ${formatQueueAge(item.queue_age_hours)}` : ""}`,
      variant: "outline",
    });
  }
  if (item.is_escalated) {
    flags.push({ label: "Escalated", variant: "destructive" });
  }

  return flags.slice(0, 2);
}

function buildVisibleScopeShortcuts(items: ReviewQueueItem[]) {
  const groupedScopes = new Map<
    string,
    { analysisId: string; label: string; items: ReviewQueueItem[] }
  >();

  for (const item of items) {
    const existingGroup = groupedScopes.get(item.analysis_id);
    if (existingGroup) {
      existingGroup.items.push(item);
      continue;
    }

    groupedScopes.set(item.analysis_id, {
      analysisId: item.analysis_id,
      label: item.compound_name,
      items: [item],
    });
  }

  return Array.from(groupedScopes.values())
    .filter((group) => group.items.length > 1)
    .sort(
      (left, right) =>
        right.items.length - left.items.length ||
        left.label.localeCompare(right.label),
    );
}

function buildSelectionReadinessMessage(selectedItems: ReviewQueueItem[]) {
  if (selectedItems.length === 0) {
    return null;
  }

  const analysisIds = new Set(selectedItems.map((item) => item.analysis_id));
  if (analysisIds.size > 1) {
    return {
      tone: "mixed" as const,
      title: "Mixed scope selected",
      description:
        "Bulk resolve and escalation are ready, but owner assignment needs one shared analysis scope.",
    };
  }

  const [firstItem] = selectedItems;
  if (!firstItem) {
    return null;
  }

  if (selectedItems.length === 1) {
    return {
      tone: "ready" as const,
      title: "Shared scope ready",
      description: `Owner assignment is ready for ${firstItem.compound_name}.`,
    };
  }

  return {
    tone: "ready" as const,
    title: "Shared scope ready",
    description: `Bulk owner assignment is ready for ${firstItem.compound_name} scope (${selectedItems.length} threads).`,
  };
}

function QueueLoadingState() {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {FILTERS.map((filter) => (
          <div
            key={filter.value}
            className="h-12 animate-pulse motion-reduce:animate-none rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)]"
          />
        ))}
      </div>
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, index) => (
          <div
            key={index}
            className="h-20 animate-pulse motion-reduce:animate-none rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)]"
          />
        ))}
      </div>
    </div>
  );
}

type FormatRelativeTime = (value: string) => string;

function isForbiddenQueueResult(
  result: ReviewQueueResult | undefined,
): boolean {
  return Boolean(result && "forbidden" in result && result.forbidden);
}

function getQueueData(result: ReviewQueueResult | undefined) {
  if (!result || "forbidden" in result) {
    return { counts: null, items: [] as ReviewQueueItem[] };
  }
  return { counts: result.counts, items: result.items };
}

function buildVisibleItems(items: ReviewQueueItem[]) {
  return [...items]
    .sort(compareQueueItems)
    .slice(0, DASHBOARD_REVIEW_QUEUE_PREVIEW_LIMIT);
}

function buildSelectionState(
  visibleItems: ReviewQueueItem[],
  selectedQueueItemIds: string[],
) {
  const selectedIds = new Set(selectedQueueItemIds);
  const selectedVisibleItems = visibleItems.filter((item) =>
    selectedIds.has(item.id),
  );
  const hasItems = visibleItems.length > 0;
  const selectedScopeCount = new Set(
    selectedVisibleItems.map((item) => item.analysis_id),
  ).size;

  return {
    allVisibleSelected:
      hasItems && visibleItems.every((item) => selectedIds.has(item.id)),
    hasItems,
    hasMixedScopeSelection: selectedScopeCount > 1,
    selectedVisibleCount: selectedVisibleItems.length,
    selectedVisibleItems,
    selectionReadiness: buildSelectionReadinessMessage(selectedVisibleItems),
  };
}

function buildReviewerSummary(mineItems: ReviewQueueItem[], mineCount: number) {
  let myOverdueCount = 0;
  let myAtRiskCount = 0;
  let myWatchCount = 0;
  let myEscalatedCount = 0;
  let ownedPressureCount = 0;
  let oldestOwnedItem: ReviewQueueItem | null = null;

  for (const item of mineItems) {
    if (item.is_overdue) myOverdueCount += 1;
    if (isAtRiskNext(item)) myAtRiskCount += 1;
    if (isWatchWindow(item)) myWatchCount += 1;
    if (item.is_escalated) myEscalatedCount += 1;
    if (item.is_overdue || item.is_escalated) ownedPressureCount += 1;
    if (
      !oldestOwnedItem ||
      Date.parse(item.last_activity_at) <
        Date.parse(oldestOwnedItem.last_activity_at)
    ) {
      oldestOwnedItem = item;
    }
  }

  const spotlightItem =
    [...mineItems]
      .sort(compareQueueItems)
      .find(
        (item) => item.is_overdue || item.is_escalated || isAtRiskNext(item),
      ) ?? null;

  return {
    myAtRiskCount,
    myEscalatedCount,
    myOpenCount: mineItems.length || mineCount,
    myOverdueCount,
    myWatchCount,
    oldestOwnedItem,
    ownedPressureCount,
    spotlightItem,
  };
}

function buildPressureLabel(
  overdueCount: number,
  escalatedCount: number,
  mineCount: number,
) {
  if (overdueCount > 0) return `${overdueCount} overdue`;
  if (escalatedCount > 0) return `${escalatedCount} escalated`;
  if (mineCount > 0) return `${mineCount} mine`;
  return "Queue stable";
}

function buildReviewerLabel({
  myAtRiskCount,
  myEscalatedCount,
  myOpenCount,
  myOverdueCount,
}: Pick<
  ReturnType<typeof buildReviewerSummary>,
  "myAtRiskCount" | "myEscalatedCount" | "myOpenCount" | "myOverdueCount"
>) {
  if (myOverdueCount > 0) return `${myOverdueCount} of yours overdue`;
  if (myAtRiskCount > 0) return `${myAtRiskCount} at risk next`;
  if (myEscalatedCount > 0) return `${myEscalatedCount} of yours escalated`;
  if (myOpenCount > 0) return `${myOpenCount} assigned to you`;
  return "No owned pressure";
}

type ReviewerMetric = {
  label: string;
  value: number;
  href: string;
  helper: string;
  tone: string;
};

function buildReviewerMetrics(
  counts: ReviewQueueCounts | null,
  summary: ReturnType<typeof buildReviewerSummary>,
  formatRelativeTime: FormatRelativeTime,
): ReviewerMetric[] {
  const unassignedCount = counts?.unassigned ?? 0;
  return [
    {
      label: "Assigned to you",
      value: summary.myOpenCount,
      href: buildQueueHref("mine"),
      helper: summary.oldestOwnedItem
        ? `Oldest owned update ${formatRelativeTime(summary.oldestOwnedItem.last_activity_at)}`
        : "No owned legal threads.",
      tone:
        summary.myOpenCount > 0
          ? "border-brand-primary/20 bg-brand-primary/5"
          : "border-[var(--border-subtle)] bg-[var(--surface-card)]",
    },
    {
      label: "My overdue",
      value: summary.myOverdueCount,
      href: buildOwnedFocusHref("my-overdue"),
      helper:
        summary.myOverdueCount > 0
          ? "Resolve from your owned queue."
          : "Your queue is within SLA.",
      tone:
        summary.myOverdueCount > 0
          ? "border-warning/30 bg-warning/5"
          : "border-[var(--border-subtle)] bg-[var(--surface-card)]",
    },
    {
      label: "My escalations",
      value: summary.myEscalatedCount,
      href: buildOwnedFocusHref("my-escalated"),
      helper:
        summary.myEscalatedCount > 0
          ? "Escalated threads assigned to you."
          : "No owned escalations right now.",
      tone:
        summary.myEscalatedCount > 0
          ? "border-error/30 bg-error/5"
          : "border-[var(--border-subtle)] bg-[var(--surface-card)]",
    },
    {
      label: "Needs owner",
      value: unassignedCount,
      href: buildQueueHref("unassigned"),
      helper:
        unassignedCount > 0
          ? "Threads waiting for assignment."
          : "No owner gaps.",
      tone:
        unassignedCount > 0
          ? "border-[var(--border-default)] bg-[var(--surface-subtle)]"
          : "border-[var(--border-subtle)] bg-[var(--surface-card)]",
    },
  ];
}

function WorkloadPanelHeader({ total }: { total: number }) {
  return (
    <CardHeader className="min-w-0 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-[0.22em] text-brand-primary">
              Legal operations
            </span>
            <Badge
              variant="outline"
              className="px-2 py-0 text-xs font-semibold uppercase tracking-[0.16em]"
            >
              Review queue
            </Badge>
          </div>
          <CardTitle className="text-base">Legal review workload</CardTitle>
          <CardDescription>
            Open comment threads, escalations, and ownership handoffs that need
            attention.
          </CardDescription>
        </div>
        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-4 py-3 text-right">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
            Open items
          </p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-[var(--text-primary)]">
            {total}
          </p>
        </div>
      </div>
    </CardHeader>
  );
}

function QueueErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="rounded-lg border border-warning/20 bg-warning/5 p-4">
      <p className="text-sm font-medium text-[var(--text-primary)]">
        Review queue temporarily unavailable.
      </p>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        The dashboard can still load without this panel. If you need the queue,
        try again.
      </p>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="mt-3 min-h-11"
        onClick={onRetry}
      >
        Retry
      </Button>
      <p className="mt-2 text-xs text-[var(--text-tertiary)]">
        {REVIEW_QUEUE_LOAD_ERROR_COPY}
      </p>
    </div>
  );
}

function QueuePressureCard({
  counts,
  escalatedCount,
  mineCount,
  overdueCount,
  pressureLabel,
}: {
  counts: ReviewQueueCounts | null;
  escalatedCount: number;
  mineCount: number;
  overdueCount: number;
  pressureLabel: string;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)] p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          variant={
            overdueCount > 0 || escalatedCount > 0 ? "destructive" : "secondary"
          }
          className="px-2 py-0 text-xs font-semibold uppercase tracking-[0.16em]"
        >
          {pressureLabel}
        </Badge>
        <span className="text-sm font-medium text-[var(--text-primary)]">
          Legal queue pressure
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-xs text-[var(--text-secondary)]">
        <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 py-1">
          {mineCount} mine
        </span>
        <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 py-1">
          {overdueCount} overdue
        </span>
        <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 py-1">
          {escalatedCount} escalated
        </span>
        <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 py-1">
          {counts?.unassigned ?? 0} unassigned
        </span>
      </div>
    </div>
  );
}

function buildOwnedPressureDescription(
  summary: ReturnType<typeof buildReviewerSummary>,
  formatRelativeTime: FormatRelativeTime,
) {
  if (summary.ownedPressureCount > 0) {
    const suffix = summary.ownedPressureCount === 1 ? "" : "s";
    return `${summary.ownedPressureCount} pressured thread${suffix} currently sit in your queue.`;
  }
  if (summary.oldestOwnedItem) {
    return `Oldest owned update ${formatRelativeTime(summary.oldestOwnedItem.last_activity_at)}.`;
  }
  return "No owned queue pressure right now.";
}

function ReviewerWorkloadCard({
  formatRelativeTime,
  reviewerLabel,
  summary,
}: {
  formatRelativeTime: FormatRelativeTime;
  reviewerLabel: string;
  summary: ReturnType<typeof buildReviewerSummary>;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)] p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          variant={
            summary.myOverdueCount > 0 || summary.myEscalatedCount > 0
              ? "destructive"
              : "secondary"
          }
          className="px-2 py-0 text-xs font-semibold uppercase tracking-[0.16em]"
        >
          {reviewerLabel}
        </Badge>
        <span className="text-sm font-medium text-[var(--text-primary)]">
          Your workload
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-xs text-[var(--text-secondary)]">
        <span className="rounded-full border border-brand-primary/20 bg-brand-primary/5 px-3 py-1 text-brand-primary">
          {summary.myOpenCount} assigned to you
        </span>
        <span
          className={cn(
            "rounded-full border px-3 py-1",
            summary.myOverdueCount > 0
              ? "border-warning/25 bg-warning/10 text-[var(--text-primary)]"
              : "border-[var(--border-subtle)] bg-[var(--surface-card)]",
          )}
        >
          {summary.myOverdueCount} my overdue
        </span>
        <span
          className={cn(
            "rounded-full border px-3 py-1",
            summary.myAtRiskCount > 0
              ? "border-warning/25 bg-warning/10 text-[var(--text-primary)]"
              : "border-[var(--border-subtle)] bg-[var(--surface-card)]",
          )}
        >
          {summary.myAtRiskCount} at risk next
        </span>
        <span
          className={cn(
            "rounded-full border px-3 py-1",
            summary.myEscalatedCount > 0
              ? "border-error/25 bg-error/10 text-[var(--text-primary)]"
              : "border-[var(--border-subtle)] bg-[var(--surface-card)]",
          )}
        >
          {summary.myEscalatedCount} my escalations
        </span>
      </div>
      <p className="mt-3 text-xs text-[var(--text-tertiary)]">
        {buildOwnedPressureDescription(summary, formatRelativeTime)}
      </p>
      <p className="mt-2 text-xs text-[var(--text-tertiary)]">
        Aging buckets: {summary.myOverdueCount} overdue
        {" · "}
        {summary.myAtRiskCount} at risk next
        {" · "}
        {summary.myWatchCount} watch window
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button asChild variant="outline" size="sm" className="min-h-11">
          <Link href={buildQueueHref("mine")}>Open my queue</Link>
        </Button>
        <Button asChild variant="ghost" size="sm" className="min-h-11">
          <Link href={buildOwnedFocusHref("my-overdue")}>Open my overdue</Link>
        </Button>
        <Button asChild variant="ghost" size="sm" className="min-h-11">
          <Link href={buildOwnedFocusHref("my-escalated")}>
            Open my escalations
          </Link>
        </Button>
      </div>
    </div>
  );
}

function getSpotlightBadgeVariant(item: ReviewQueueItem) {
  if (item.is_overdue) return "destructive" as const;
  if (isAtRiskNext(item) || item.is_escalated) return "warning" as const;
  return "secondary" as const;
}

function OwnedSpotlight({
  currentUserRole,
  formatRelativeTime,
  item,
  onQueueRefresh,
  riskRatingsRestricted,
  token,
}: {
  currentUserRole?: string | null;
  formatRelativeTime: FormatRelativeTime;
  item: ReviewQueueItem | null;
  onQueueRefresh: () => Promise<void>;
  riskRatingsRestricted?: boolean;
  token: string | null;
}) {
  if (!item) return null;

  return (
    <div className="min-w-0 rounded-lg border border-brand-primary/20 bg-gradient-to-br from-brand-primary/10 via-brand-primary/5 to-transparent p-4 shadow-[var(--shadow-xs)] xl:col-span-2">
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          variant={getSpotlightBadgeVariant(item)}
          className="px-2 py-0 text-xs font-semibold uppercase tracking-[0.16em]"
        >
          {getUrgencyLabel(item)}
        </Badge>
        <span className="text-sm font-medium text-[var(--text-primary)]">
          Owned spotlight
        </span>
      </div>
      <div className="mt-3 min-w-0">
        <p className="truncate text-base font-semibold text-[var(--text-primary)]">
          {item.compound_name}
        </p>
        <p className="mt-1 text-sm text-[var(--text-secondary)] [overflow-wrap:anywhere]">
          Last activity {formatRelativeTime(item.last_activity_at)} ·{" "}
          {summarizeActivityContext(item)}
        </p>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button asChild size="sm" className="min-h-11">
          <Link
            href={buildReportHref(item, currentUserRole, riskRatingsRestricted)}
          >
            {getReviewQueueItemSpotlightActionLabel(
              item,
              currentUserRole,
              riskRatingsRestricted,
            )}
          </Link>
        </Button>
        <Button asChild variant="ghost" size="sm" className="min-h-11">
          <Link href={buildQueueHref("mine")}>Open my queue</Link>
        </Button>
      </div>
      <LegalReviewSpotlightActions
        item={item}
        token={token}
        onQueueRefresh={onQueueRefresh}
      />
    </div>
  );
}

function WorkloadOverview({
  counts,
  currentUserRole,
  escalatedCount,
  formatRelativeTime,
  mineCount,
  onQueueRefresh,
  overdueCount,
  pressureLabel,
  reviewerLabel,
  reviewerSummary,
  riskRatingsRestricted,
  token,
}: {
  counts: ReviewQueueCounts | null;
  currentUserRole?: string | null;
  escalatedCount: number;
  formatRelativeTime: FormatRelativeTime;
  mineCount: number;
  onQueueRefresh: () => Promise<void>;
  overdueCount: number;
  pressureLabel: string;
  reviewerLabel: string;
  reviewerSummary: ReturnType<typeof buildReviewerSummary>;
  riskRatingsRestricted?: boolean;
  token: string | null;
}) {
  return (
    <div className="grid min-w-0 gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <QueuePressureCard
        counts={counts}
        escalatedCount={escalatedCount}
        mineCount={mineCount}
        overdueCount={overdueCount}
        pressureLabel={pressureLabel}
      />
      <ReviewerWorkloadCard
        formatRelativeTime={formatRelativeTime}
        reviewerLabel={reviewerLabel}
        summary={reviewerSummary}
      />
      <OwnedSpotlight
        currentUserRole={currentUserRole}
        formatRelativeTime={formatRelativeTime}
        item={reviewerSummary.spotlightItem}
        onQueueRefresh={onQueueRefresh}
        riskRatingsRestricted={riskRatingsRestricted}
        token={token}
      />
    </div>
  );
}

function ReviewerMetricsGrid({ metrics }: { metrics: ReviewerMetric[] }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
      {metrics.map((metric) => (
        <Link
          key={metric.label}
          href={metric.href}
          className={cn(
            "rounded-lg border px-4 py-3 transition-colors hover:border-brand-primary/30 hover:bg-brand-primary/5",
            metric.tone,
          )}
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
                {metric.label}
              </p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-[var(--text-primary)]">
                {metric.value}
              </p>
            </div>
            <ArrowRight className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--text-tertiary)]" />
          </div>
          <p className="mt-2 text-xs text-[var(--text-secondary)]">
            {metric.helper}
          </p>
        </Link>
      ))}
    </div>
  );
}

function QueueFilterBar({
  activeFilter,
  counts,
  onFilterChange,
}: {
  activeFilter: ReviewQueueFilter;
  counts: ReviewQueueCounts | null;
  onFilterChange: (filter: ReviewQueueFilter) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {FILTERS.map((filter) => {
        const count = counts?.[filter.value] ?? 0;
        const Icon = filter.icon;
        const isActive = activeFilter === filter.value;

        return (
          <button
            key={filter.value}
            type="button"
            aria-pressed={isActive}
            onClick={() => onFilterChange(filter.value)}
            className={cn(
              "flex min-h-16 items-center justify-between gap-3 rounded-lg border px-3 py-2 text-left transition-all",
              isActive
                ? "border-brand-primary/30 bg-brand-primary/10 text-brand-primary shadow-[var(--shadow-xs)]"
                : "border-[var(--border-subtle)] bg-[var(--surface-subtle)] text-[var(--text-secondary)] hover:border-[var(--border-default)] hover:bg-[var(--surface-hover)]",
            )}
          >
            <span className="flex items-center gap-2">
              <Icon
                className={cn(
                  "h-4 w-4",
                  isActive
                    ? "text-brand-primary"
                    : "text-[var(--text-tertiary)]",
                )}
              />
              <span className="text-sm font-medium">{filter.label}</span>
            </span>
            <span className="text-lg font-semibold tabular-nums">{count}</span>
          </button>
        );
      })}
    </div>
  );
}

function QueueSelectionControls({
  activeFilter,
  activeLabel,
  allVisibleSelected,
  hasItems,
  onClearSelection,
  onSelectVisibleItems,
  selectedVisibleCount,
  visibleItemCount,
}: {
  activeFilter: ReviewQueueFilter;
  activeLabel: string;
  allVisibleSelected: boolean;
  hasItems: boolean;
  onClearSelection: () => void;
  onSelectVisibleItems: () => void;
  selectedVisibleCount: number;
  visibleItemCount: number;
}) {
  return (
    <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
      <p className="min-w-0 text-sm text-[var(--text-secondary)]">
        Showing {hasItems ? visibleItemCount : 0} {activeLabel.toLowerCase()}{" "}
        item{visibleItemCount === 1 ? "" : "s"}
        {selectedVisibleCount > 0 ? ` · ${selectedVisibleCount} selected` : ""}
      </p>
      <div className="flex flex-wrap items-center gap-2 sm:justify-end">
        {hasItems ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="min-h-11"
            disabled={allVisibleSelected}
            onClick={onSelectVisibleItems}
          >
            {allVisibleSelected ? "Visible selected" : "Select visible"}
          </Button>
        ) : null}
        {selectedVisibleCount > 0 ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="min-h-11"
            onClick={onClearSelection}
          >
            Clear selection
          </Button>
        ) : null}
        <Link
          href={buildQueueHref(activeFilter)}
          className="inline-flex min-h-11 items-center rounded-md px-3 text-xs font-medium text-brand-primary transition-colors hover:bg-brand-primary/10 hover:text-brand-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
        >
          Open this slice
        </Link>
      </div>
    </div>
  );
}

function BulkActionFeedback({
  feedback,
}: {
  feedback: ReviewQueueBulkActionSuccess | null;
}) {
  if (!feedback) return null;

  return (
    <div className="rounded-lg border border-brand-primary/20 bg-brand-primary/5 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          variant="default"
          className="px-2 py-0 text-xs font-semibold uppercase tracking-[0.16em]"
        >
          Queue updated
        </Badge>
        <span className="text-sm text-[var(--text-secondary)]">
          {buildBulkActionFeedbackMessage(feedback)}
        </span>
      </div>
      <p className="mt-2 text-xs text-[var(--text-tertiary)]">
        {buildBulkActionChangeSummary(feedback)}
      </p>
    </div>
  );
}

type SelectionReadiness = NonNullable<
  ReturnType<typeof buildSelectionReadinessMessage>
>;

function SelectionReadinessCard({
  readiness,
}: {
  readiness: SelectionReadiness | null;
}) {
  if (!readiness) return null;

  return (
    <div
      className={cn(
        "rounded-lg border px-4 py-3",
        readiness.tone === "ready"
          ? "border-brand-primary/20 bg-brand-primary/5"
          : "border-warning/25 bg-warning/10",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          variant={readiness.tone === "ready" ? "default" : "warning"}
          className="px-2 py-0 text-xs font-semibold uppercase tracking-[0.16em]"
        >
          {readiness.title}
        </Badge>
        <span className="text-sm text-[var(--text-secondary)]">
          {readiness.description}
        </span>
      </div>
    </div>
  );
}

function BulkSelectionTray({
  onActionComplete,
  onClearSelection,
  readiness,
  selectedItems,
  token,
}: {
  onActionComplete: (payload: ReviewQueueBulkActionSuccess) => void;
  onClearSelection: () => void;
  readiness: SelectionReadiness | null;
  selectedItems: ReviewQueueItem[];
  token: string | null;
}) {
  if (selectedItems.length === 0) return null;

  return (
    <div className="space-y-2">
      <SelectionReadinessCard readiness={readiness} />
      <ReviewQueueBulkToolbar
        token={token}
        selectedItems={selectedItems}
        onClearSelection={onClearSelection}
        mode="compact"
        onActionComplete={onActionComplete}
      />
    </div>
  );
}

type ScopeShortcut = ReturnType<typeof buildVisibleScopeShortcuts>[number];

function isScopeExactlySelected(
  scopeShortcut: ScopeShortcut,
  selectedIds: Set<string>,
  selectedVisibleCount: number,
) {
  return (
    selectedVisibleCount === scopeShortcut.items.length &&
    scopeShortcut.items.every((item) => selectedIds.has(item.id))
  );
}

function ScopeShortcuts({
  hasMixedScopeSelection,
  onSelectScope,
  scopeShortcuts,
  selectedQueueItemIds,
  selectedVisibleCount,
}: {
  hasMixedScopeSelection: boolean;
  onSelectScope: (analysisId: string) => void;
  scopeShortcuts: ScopeShortcut[];
  selectedQueueItemIds: string[];
  selectedVisibleCount: number;
}) {
  if (scopeShortcuts.length === 0) return null;
  const selectedIds = new Set(selectedQueueItemIds);

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
          Scope shortcuts
        </span>
        {scopeShortcuts.map((scopeShortcut) => {
          const isExactScopeSelected = isScopeExactlySelected(
            scopeShortcut,
            selectedIds,
            selectedVisibleCount,
          );
          const shortcutLabel = isExactScopeSelected
            ? `${scopeShortcut.label} scope selected`
            : `Select ${scopeShortcut.label} scope (${scopeShortcut.items.length})`;

          return (
            <Button
              key={scopeShortcut.analysisId}
              type="button"
              variant={isExactScopeSelected ? "secondary" : "outline"}
              size="sm"
              className="max-w-full min-w-0 whitespace-normal min-h-11 text-left leading-5 [overflow-wrap:anywhere]"
              title={shortcutLabel}
              onClick={() => onSelectScope(scopeShortcut.analysisId)}
              disabled={isExactScopeSelected}
            >
              <span className="min-w-0 [overflow-wrap:anywhere]">
                {shortcutLabel}
              </span>
            </Button>
          );
        })}
      </div>
      <p className="text-xs text-[var(--text-tertiary)]">
        {hasMixedScopeSelection
          ? "Replace mixed selections with one shared analysis scope to bulk assign owner."
          : "Bulk owner assignment unlocks once the selected threads share one review scope."}
      </p>
    </div>
  );
}

function QueueItemRow({
  currentUserRole,
  formatRelativeTime,
  isInlineActionsOpen,
  isSelected,
  isSpotlightRow,
  item,
  onQueueRefresh,
  onToggleInlineActions,
  onToggleSelection,
  riskRatingsRestricted,
  token,
}: {
  currentUserRole?: string | null;
  formatRelativeTime: FormatRelativeTime;
  isInlineActionsOpen: boolean;
  isSelected: boolean;
  isSpotlightRow: boolean;
  item: ReviewQueueItem;
  onQueueRefresh: () => Promise<void>;
  onToggleInlineActions: (itemId: string) => void;
  onToggleSelection: (itemId: string) => void;
  riskRatingsRestricted?: boolean;
  token: string | null;
}) {
  const flags = getItemFlags(item);
  const hasInlineActions = !isSpotlightRow;

  return (
    <li>
      <div className="px-4 py-3 transition-colors hover:bg-[var(--surface-subtle)]">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <Link
            href={buildReportHref(item, currentUserRole, riskRatingsRestricted)}
            className="group flex min-h-11 min-w-0 flex-1 items-start gap-3 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
          >
            <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-brand-primary/10 text-sm font-semibold text-brand-primary">
              {item.compound_name.trim().charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="min-w-0 truncate text-sm font-medium text-[var(--text-primary)] transition-colors group-hover:text-brand-primary">
                  {item.compound_name}
                </span>
                {flags.map((flag) => (
                  <Badge
                    key={flag.label}
                    variant={flag.variant}
                    className="px-2 py-0 text-xs font-semibold uppercase tracking-[0.14em]"
                  >
                    {flag.label}
                  </Badge>
                ))}
              </div>
              <p className="mt-1 line-clamp-2 text-sm text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                {item.comment_body}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-[var(--text-tertiary)]">
                <span className="min-w-0 [overflow-wrap:anywhere]">
                  {formatAssignee(item)}
                </span>
                <span>•</span>
                <span>
                  {item.comment_count} comment
                  {item.comment_count === 1 ? "" : "s"}
                </span>
                <span>•</span>
                <span className="min-w-0 [overflow-wrap:anywhere]">
                  {formatRelativeTime(item.last_activity_at)}
                </span>
              </div>
            </div>
          </Link>

          <div className="flex shrink-0 flex-wrap items-center gap-2 lg:justify-end">
            <Button
              type="button"
              variant={isSelected ? "secondary" : "ghost"}
              size="sm"
              className="min-h-11"
              aria-label={`${isSelected ? "Deselect" : "Select"} ${item.compound_name} for bulk actions`}
              onClick={() => onToggleSelection(item.id)}
            >
              {isSelected ? "Selected" : "Select"}
            </Button>
            <Button asChild variant="outline" size="sm" className="min-h-11">
              <Link
                href={buildReportHref(
                  item,
                  currentUserRole,
                  riskRatingsRestricted,
                )}
              >
                {getReviewQueueItemActionLabel(
                  item,
                  currentUserRole,
                  riskRatingsRestricted,
                )}
              </Link>
            </Button>
            {hasInlineActions ? (
              <Button
                type="button"
                variant={isInlineActionsOpen ? "secondary" : "ghost"}
                size="sm"
                className="min-h-11"
                onClick={() => onToggleInlineActions(item.id)}
              >
                {isInlineActionsOpen ? "Hide actions" : "Quick actions"}
              </Button>
            ) : (
              <span className="text-xs text-[var(--text-tertiary)]">
                Spotlighted above
              </span>
            )}
          </div>
        </div>

        {isInlineActionsOpen ? (
          <LegalReviewSpotlightActions
            item={item}
            token={token}
            onQueueRefresh={onQueueRefresh}
            mode="inline"
          />
        ) : null}
      </div>
    </li>
  );
}

function QueueItems({
  activeLabel,
  currentUserRole,
  expandedQueueActionItemId,
  formatRelativeTime,
  onQueueRefresh,
  onToggleInlineActions,
  onToggleSelection,
  riskRatingsRestricted,
  selectedQueueItemIds,
  spotlightItemId,
  token,
  visibleItems,
}: {
  activeLabel: string;
  currentUserRole?: string | null;
  expandedQueueActionItemId: string | null;
  formatRelativeTime: FormatRelativeTime;
  onQueueRefresh: () => Promise<void>;
  onToggleInlineActions: (itemId: string) => void;
  onToggleSelection: (itemId: string) => void;
  riskRatingsRestricted?: boolean;
  selectedQueueItemIds: string[];
  spotlightItemId?: string;
  token: string | null;
  visibleItems: ReviewQueueItem[];
}) {
  if (visibleItems.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-4 py-8 text-center">
        <p className="text-sm font-medium text-[var(--text-primary)]">
          No {activeLabel.toLowerCase()} review items right now.
        </p>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Switch filters to inspect a different slice of the legal workload.
        </p>
      </div>
    );
  }

  const selectedIds = new Set(selectedQueueItemIds);
  return (
    <div className="overflow-hidden rounded-lg border border-[var(--border-subtle)]">
      <ul className="divide-y divide-[var(--border-subtle)]">
        {visibleItems.map((item) => (
          <QueueItemRow
            key={item.id}
            currentUserRole={currentUserRole}
            formatRelativeTime={formatRelativeTime}
            isInlineActionsOpen={expandedQueueActionItemId === item.id}
            isSelected={selectedIds.has(item.id)}
            isSpotlightRow={spotlightItemId === item.id}
            item={item}
            onQueueRefresh={onQueueRefresh}
            onToggleInlineActions={onToggleInlineActions}
            onToggleSelection={onToggleSelection}
            riskRatingsRestricted={riskRatingsRestricted}
            token={token}
          />
        ))}
      </ul>
    </div>
  );
}

type ReadyWorkloadContentProps = {
  activeFilter: ReviewQueueFilter;
  activeLabel: string;
  bulkActionFeedback: ReviewQueueBulkActionSuccess | null;
  counts: ReviewQueueCounts | null;
  currentUserRole?: string | null;
  escalatedCount: number;
  expandedQueueActionItemId: string | null;
  formatRelativeTime: FormatRelativeTime;
  mineCount: number;
  onBulkActionComplete: (payload: ReviewQueueBulkActionSuccess) => void;
  onClearSelection: () => void;
  onFilterChange: (filter: ReviewQueueFilter) => void;
  onQueueRefresh: () => Promise<void>;
  onSelectScope: (analysisId: string) => void;
  onSelectVisibleItems: () => void;
  onToggleInlineActions: (itemId: string) => void;
  onToggleSelection: (itemId: string) => void;
  overdueCount: number;
  pressureLabel: string;
  reviewerLabel: string;
  reviewerMetrics: ReviewerMetric[];
  reviewerSummary: ReturnType<typeof buildReviewerSummary>;
  riskRatingsRestricted?: boolean;
  scopeShortcuts: ScopeShortcut[];
  selectedQueueItemIds: string[];
  selection: ReturnType<typeof buildSelectionState>;
  token: string | null;
  visibleItems: ReviewQueueItem[];
};

function ReadyWorkloadContent(props: ReadyWorkloadContentProps) {
  return (
    <>
      <WorkloadOverview
        counts={props.counts}
        currentUserRole={props.currentUserRole}
        escalatedCount={props.escalatedCount}
        formatRelativeTime={props.formatRelativeTime}
        mineCount={props.mineCount}
        onQueueRefresh={props.onQueueRefresh}
        overdueCount={props.overdueCount}
        pressureLabel={props.pressureLabel}
        reviewerLabel={props.reviewerLabel}
        reviewerSummary={props.reviewerSummary}
        riskRatingsRestricted={props.riskRatingsRestricted}
        token={props.token}
      />
      <ReviewerMetricsGrid metrics={props.reviewerMetrics} />
      <QueueFilterBar
        activeFilter={props.activeFilter}
        counts={props.counts}
        onFilterChange={props.onFilterChange}
      />
      <QueueSelectionControls
        activeFilter={props.activeFilter}
        activeLabel={props.activeLabel}
        allVisibleSelected={props.selection.allVisibleSelected}
        hasItems={props.selection.hasItems}
        onClearSelection={props.onClearSelection}
        onSelectVisibleItems={props.onSelectVisibleItems}
        selectedVisibleCount={props.selection.selectedVisibleCount}
        visibleItemCount={props.visibleItems.length}
      />
      <BulkActionFeedback feedback={props.bulkActionFeedback} />
      <BulkSelectionTray
        onActionComplete={props.onBulkActionComplete}
        onClearSelection={props.onClearSelection}
        readiness={props.selection.selectionReadiness}
        selectedItems={props.selection.selectedVisibleItems}
        token={props.token}
      />
      <ScopeShortcuts
        hasMixedScopeSelection={props.selection.hasMixedScopeSelection}
        onSelectScope={props.onSelectScope}
        scopeShortcuts={props.scopeShortcuts}
        selectedQueueItemIds={props.selectedQueueItemIds}
        selectedVisibleCount={props.selection.selectedVisibleCount}
      />
      <QueueItems
        activeLabel={props.activeLabel}
        currentUserRole={props.currentUserRole}
        expandedQueueActionItemId={props.expandedQueueActionItemId}
        formatRelativeTime={props.formatRelativeTime}
        onQueueRefresh={props.onQueueRefresh}
        onToggleInlineActions={props.onToggleInlineActions}
        onToggleSelection={props.onToggleSelection}
        riskRatingsRestricted={props.riskRatingsRestricted}
        selectedQueueItemIds={props.selectedQueueItemIds}
        spotlightItemId={props.reviewerSummary.spotlightItem?.id}
        token={props.token}
        visibleItems={props.visibleItems}
      />
    </>
  );
}

function WorkloadPanelBody({
  isError,
  isLoading,
  onRetry,
  readyContent,
}: {
  isError: boolean;
  isLoading: boolean;
  onRetry: () => void;
  readyContent: ReactNode;
}) {
  if (isLoading) return <QueueLoadingState />;
  if (isError) return <QueueErrorState onRetry={onRetry} />;
  return readyContent;
}

function shouldHideWorkloadPanel({
  data,
  isLoading,
  isMineLoading,
  mineData,
  token,
}: {
  data: ReviewQueueResult | undefined;
  isLoading: boolean;
  isMineLoading: boolean;
  mineData: ReviewQueueResult | undefined;
  token: string | null;
}) {
  const hasNoAvailableQueue =
    !token && !isLoading && !isMineLoading && !data && !mineData;
  return (
    hasNoAvailableQueue ||
    isForbiddenQueueResult(data) ||
    isForbiddenQueueResult(mineData)
  );
}

export function LegalReviewWorkloadPanel({
  token,
}: LegalReviewWorkloadPanelProps) {
  const formatRelativeTime = useHydrationSafeRelativeTime(relativeTime);
  const principal = usePrincipalCapabilities(token);
  const [activeFilter, setActiveFilter] = useState<ReviewQueueFilter>("mine");
  const [expandedQueueActionItemId, setExpandedQueueActionItemId] = useState<
    string | null
  >(null);
  const [selectedQueueItemIds, setSelectedQueueItemIds] = useState<string[]>(
    [],
  );
  const [bulkActionFeedback, setBulkActionFeedback] =
    useState<ReviewQueueBulkActionSuccess | null>(null);
  const { data, isLoading, isError, refetch } = useReviewQueue(
    token,
    activeFilter,
  );
  const {
    data: mineData,
    isLoading: isMineLoading,
    isError: isMineError,
    refetch: refetchMine,
  } = useReviewQueue(token, "mine");

  const { counts, items } = getQueueData(data);
  const { items: mineItems } = getQueueData(mineData);
  const visibleItems = buildVisibleItems(items);
  const visibleScopeShortcuts = buildVisibleScopeShortcuts(visibleItems);
  const selection = buildSelectionState(visibleItems, selectedQueueItemIds);
  const activeLabel =
    FILTERS.find((filter) => filter.value === activeFilter)?.label ?? "Mine";
  const overdueCount = counts?.overdue ?? 0;
  const escalatedCount = counts?.escalated ?? 0;
  const mineCount = counts?.mine ?? 0;
  const reviewerSummary = buildReviewerSummary(mineItems, mineCount);
  const currentUserRole = principal.data?.role;
  const riskRatingsRestricted = principal.data?.risk_ratings_restricted;
  const pressureLabel = buildPressureLabel(
    overdueCount,
    escalatedCount,
    mineCount,
  );
  const reviewerLabel = buildReviewerLabel(reviewerSummary);
  const refreshQueues = async () => {
    await Promise.all([refetch(), refetchMine()]);
  };
  const clearSelection = () => {
    setSelectedQueueItemIds([]);
  };
  const handleFilterChange = (filter: ReviewQueueFilter) => {
    setExpandedQueueActionItemId(null);
    clearSelection();
    setBulkActionFeedback(null);
    setActiveFilter(filter);
  };
  const handleRetry = () => {
    void refetch();
    void refetchMine();
  };
  const selectVisibleItems = () => {
    setExpandedQueueActionItemId(null);
    setBulkActionFeedback(null);
    setSelectedQueueItemIds(visibleItems.map((item) => item.id));
  };
  const selectScopeItems = (analysisId: string) => {
    setExpandedQueueActionItemId(null);
    setBulkActionFeedback(null);
    setSelectedQueueItemIds(
      visibleItems
        .filter((item) => item.analysis_id === analysisId)
        .map((item) => item.id),
    );
  };
  const toggleItemSelection = (itemId: string) => {
    setExpandedQueueActionItemId(null);
    setBulkActionFeedback(null);
    setSelectedQueueItemIds((currentIds) =>
      currentIds.includes(itemId)
        ? currentIds.filter((currentId) => currentId !== itemId)
        : [...currentIds, itemId],
    );
  };
  const toggleInlineActions = (itemId: string) => {
    setExpandedQueueActionItemId((currentItemId) =>
      currentItemId === itemId ? null : itemId,
    );
  };
  const handleBulkActionComplete = (payload: ReviewQueueBulkActionSuccess) => {
    setBulkActionFeedback(payload);
  };

  // Clear queue-item selection state on org/user switch. Selected and expanded
  // ids reference review-queue rows scoped to the previous auth context; the
  // refetched queue belongs to a different org, so carrying them over could
  // briefly target stale ids. Reset to the default slice as well.
  const resetWorkloadSelection = useCallback(() => {
    setSelectedQueueItemIds([]);
    setExpandedQueueActionItemId(null);
    setBulkActionFeedback(null);
    setActiveFilter("mine");
  }, []);
  useAuthBoundaryReset(resetWorkloadSelection);

  useEffect(() => {
    if (!bulkActionFeedback) {
      return undefined;
    }

    const timeout = window.setTimeout(() => {
      setBulkActionFeedback(null);
    }, 4000);

    return () => window.clearTimeout(timeout);
  }, [bulkActionFeedback]);

  if (
    shouldHideWorkloadPanel({
      data,
      isLoading,
      isMineLoading,
      mineData,
      token,
    })
  ) {
    return null;
  }

  const reviewerMetrics = buildReviewerMetrics(
    counts,
    reviewerSummary,
    formatRelativeTime,
  );

  return (
    <Card className="min-w-0 overflow-hidden border-brand-primary/15 bg-gradient-to-br from-brand-primary/5 via-transparent to-transparent shadow-[var(--shadow-sm)]">
      <div className="h-1 bg-gradient-to-r from-brand-primary via-brand-primary/30 to-transparent" />
      <WorkloadPanelHeader total={counts?.total ?? 0} />
      <CardContent className="min-w-0 space-y-4">
        <WorkloadPanelBody
          isError={isError || isMineError}
          isLoading={isLoading || isMineLoading}
          onRetry={handleRetry}
          readyContent={
            <ReadyWorkloadContent
              activeFilter={activeFilter}
              activeLabel={activeLabel}
              bulkActionFeedback={bulkActionFeedback}
              counts={counts}
              currentUserRole={currentUserRole}
              escalatedCount={escalatedCount}
              expandedQueueActionItemId={expandedQueueActionItemId}
              formatRelativeTime={formatRelativeTime}
              mineCount={mineCount}
              onBulkActionComplete={handleBulkActionComplete}
              onClearSelection={clearSelection}
              onFilterChange={handleFilterChange}
              onQueueRefresh={refreshQueues}
              onSelectScope={selectScopeItems}
              onSelectVisibleItems={selectVisibleItems}
              onToggleInlineActions={toggleInlineActions}
              onToggleSelection={toggleItemSelection}
              overdueCount={overdueCount}
              pressureLabel={pressureLabel}
              reviewerLabel={reviewerLabel}
              reviewerMetrics={reviewerMetrics}
              reviewerSummary={reviewerSummary}
              riskRatingsRestricted={riskRatingsRestricted}
              scopeShortcuts={visibleScopeShortcuts}
              selectedQueueItemIds={selectedQueueItemIds}
              selection={selection}
              token={token}
              visibleItems={visibleItems}
            />
          }
        />
      </CardContent>
    </Card>
  );
}
