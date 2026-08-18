"use client";

import {
  AlertTriangle,
  ArrowUpDown,
  Check,
  Clock3,
  FileSearch,
  Inbox,
  Loader2,
  LockKeyhole,
  Scale,
  Users,
  X,
} from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type RefObject,
} from "react";
import { useAuthBoundaryReset } from "@/hooks/use-auth-boundary-reset";
import { Badge } from "@/components/ui/badge";
import { AppSurfaceHeader } from "@/components/shared/app-surface-header";
import { OperationalStatusFrame } from "@/components/shared/operational-status-frame";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  type ReviewQueueFilter,
  type ReviewQueueCounts,
  type ReviewQueueItem,
  useReviewQueue,
} from "@/hooks/use-review-queue";
import {
  ReviewQueueBulkToolbar,
  type ReviewQueueBulkActionSuccess,
} from "@/components/reviews/review-queue-bulk-toolbar";
import { ReviewQueueItemCard } from "@/components/reviews/review-queue-item-card";
import {
  REVIEW_QUEUE_SORT_OPTIONS,
  type ReviewQueueSortMode,
  sortReviewQueueItems,
} from "@/components/reviews/review-queue-utils";
import {
  buildBulkActionChangeSummary,
  buildBulkActionFeedbackMessage,
} from "@/components/reviews/review-queue-feedback";
import { REVIEW_QUEUE_LOAD_ERROR_COPY } from "@/components/reviews/review-queue-errors";

interface ReviewQueuePageProps {
  token: string | null;
  initialFilter?: ReviewQueueFilter;
  initialSortMode?: ReviewQueueSortMode;
  initialReviewerScope?: ReviewQueueReviewerScope;
}

export type ReviewQueueReviewerScope = "all" | "mine";

const FILTERS: Array<{
  value: ReviewQueueFilter;
  label: string;
  helper: string;
  icon: typeof Users;
  countKey: "mine" | "unassigned" | "overdue" | "escalated";
  tone: "brand" | "neutral" | "warning" | "danger";
}> = [
  {
    value: "mine",
    label: "Mine",
    helper: "Assigned to you",
    icon: Users,
    countKey: "mine",
    tone: "brand",
  },
  {
    value: "unassigned",
    label: "Needs owner",
    helper: "Awaiting handoff",
    icon: Inbox,
    countKey: "unassigned",
    tone: "neutral",
  },
  {
    value: "overdue",
    label: "Past SLA",
    helper: "Response overdue",
    icon: Clock3,
    countKey: "overdue",
    tone: "warning",
  },
  {
    value: "escalated",
    label: "Escalated",
    helper: "Counsel attention",
    icon: AlertTriangle,
    countKey: "escalated",
    tone: "danger",
  },
];

const EMPTY_QUEUE_ITEMS: ReviewQueueItem[] = [];
const EMPTY_SELECTED_ITEM_IDS: string[] = [];

interface ReviewQueueSelectionState {
  itemIds: string[];
}

function ReviewQueuePageHeader({
  openThreads,
  priorityMatterName,
  reviewerScopeActive = false,
}: {
  openThreads?: number;
  priorityMatterName?: string;
  reviewerScopeActive?: boolean;
}) {
  const priorityMatter = priorityMatterName?.trim()
    ? Array.from(priorityMatterName.trim().replace(/\s+/gu, " "))
        .slice(0, 160)
        .join("")
    : null;
  const metrics =
    typeof openThreads === "number"
      ? [
          {
            label: reviewerScopeActive ? "Org threads" : "Open threads",
            value: openThreads.toLocaleString(),
            detail: reviewerScopeActive
              ? "Organization workload remains visible"
              : "Active review handoffs",
          },
          {
            label: "Workload",
            value: reviewerScopeActive ? "Assigned to you" : "Org queue",
            detail: reviewerScopeActive
              ? "Personal overdue/escalation slice"
              : "Reviewer-owned queue",
          },
          {
            label: "Review",
            value: "Legal handoff",
            detail: "Assignments, escalations, and resolution state",
          },
        ]
      : undefined;

  return (
    <AppSurfaceHeader
      dataTestId="review-queue-app-surface-header"
      eyebrow="Praviar reviewer intelligence"
      title="Legal Review Queue"
      description={`Open ownership handoffs, overdue threads, and escalations across active analyses.${priorityMatter ? ` Current priority: ${priorityMatter}.` : ""}`}
      metrics={metrics}
      actions={
        reviewerScopeActive ? (
          <Badge
            variant="outline"
            className="w-fit px-2 py-1 text-xs font-semibold uppercase"
          >
            Assigned to you
          </Badge>
        ) : null
      }
    />
  );
}

function formatQueueSyncLabel(updatedAt: string | null | undefined) {
  if (!updatedAt) {
    return "Loaded";
  }

  const timestamp = Date.parse(updatedAt);
  if (Number.isNaN(timestamp)) {
    return "Sync time unavailable";
  }

  return (
    new Intl.DateTimeFormat("en-GB", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "UTC",
    }).format(new Date(timestamp)) + " UTC"
  );
}

function ReviewQueueStatusStrip({
  counts,
  orgCounts,
  activeLabel,
  visibleCount,
  updatedAt,
  reviewerScopeActive = false,
}: {
  counts: ReviewQueueCounts;
  orgCounts?: ReviewQueueCounts;
  activeLabel: string;
  visibleCount: number;
  updatedAt: string | null | undefined;
  reviewerScopeActive?: boolean;
}) {
  const urgentCount = counts.overdue + counts.escalated;
  const assignedCount = Math.max(counts.total - counts.unassigned, 0);
  const orgUrgentDetail = orgCounts
    ? ` · org ${orgCounts.overdue} overdue / ${orgCounts.escalated} escalated`
    : "";

  const statusItems = [
    {
      label: reviewerScopeActive ? "My urgent review" : "Urgent review",
      value: urgentCount.toLocaleString(),
      detail: reviewerScopeActive
        ? `${counts.overdue} overdue / ${counts.escalated} escalated assigned to you${orgUrgentDetail}`
        : `${counts.overdue} overdue / ${counts.escalated} escalated`,
      icon: AlertTriangle,
      tone: urgentCount > 0 ? "warning" : "neutral",
    },
    {
      label: reviewerScopeActive ? "My visible ownership" : "Ownership",
      value: `${assignedCount}/${counts.total}`,
      detail: reviewerScopeActive
        ? `${counts.total} assigned-to-you thread${counts.total === 1 ? "" : "s"} visible`
        : counts.unassigned > 0
          ? `${counts.unassigned} awaiting owner`
          : "All open threads owned",
      icon: Users,
      tone: counts.unassigned > 0 ? "brand" : "neutral",
    },
    {
      label: "Active slice",
      value: visibleCount.toLocaleString(),
      detail: `${activeLabel} visible now`,
      icon: Scale,
      tone: "neutral",
    },
    {
      label: "Queue sync",
      value: formatQueueSyncLabel(updatedAt),
      detail: reviewerScopeActive
        ? "Reviewer-filtered queue snapshot"
        : "Current queue snapshot",
      icon: Clock3,
      tone: "neutral",
    },
  ] as const;

  return (
    <section
      aria-label="Review queue status"
      className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
    >
      {statusItems.map((item) => {
        const Icon = item.icon;

        return (
          <div
            key={item.label}
            className={cn(
              "rounded-lg border bg-[var(--surface-card)] p-4",
              item.tone === "warning"
                ? "border-warning/25 bg-warning/10"
                : item.tone === "brand"
                  ? "border-brand-primary/20 bg-brand-primary/10"
                  : "border-[var(--border-subtle)]",
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
                  {item.label}
                </p>
                <p className="mt-1 break-words text-xl font-semibold leading-tight tabular-nums text-[var(--text-primary)] [overflow-wrap:anywhere]">
                  {item.value}
                </p>
                <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                  {item.detail}
                </p>
              </div>
              <span
                className={cn(
                  "flex h-9 w-9 shrink-0 items-center justify-center rounded-md",
                  item.tone === "warning"
                    ? "bg-warning/15 text-warning"
                    : item.tone === "brand"
                      ? "bg-brand-primary/15 text-brand-primary"
                      : "bg-[var(--surface-muted)] text-[var(--text-tertiary)]",
                )}
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
              </span>
            </div>
          </div>
        );
      })}
    </section>
  );
}

function shouldApplyReviewerScope(
  filter: ReviewQueueFilter,
  reviewerScope: ReviewQueueReviewerScope,
) {
  return (
    reviewerScope === "mine" && (filter === "overdue" || filter === "escalated")
  );
}

function getActiveQueueLabel(
  filter: ReviewQueueFilter,
  label: string,
  reviewerScopeActive: boolean,
) {
  if (!reviewerScopeActive) {
    return label;
  }

  if (filter === "overdue") {
    return "My overdue";
  }

  if (filter === "escalated") {
    return "My escalated";
  }

  return label;
}

function getEmptyStateCopy(
  filter: ReviewQueueFilter,
  activeLabel: string,
  reviewerScopeActive: boolean,
) {
  if (!reviewerScopeActive) {
    return {
      title: `No ${activeLabel.toLowerCase()} threads right now.`,
      description:
        "Switch filters to inspect a different slice of the legal workload.",
    };
  }

  if (filter === "overdue") {
    return {
      title: "No overdue threads assigned to you right now.",
      description:
        "Switch filters to inspect a different slice of your legal workload.",
    };
  }

  if (filter === "escalated") {
    return {
      title: "No escalated threads assigned to you right now.",
      description:
        "Switch filters to inspect a different slice of your legal workload.",
    };
  }

  return {
    title: `No ${activeLabel.toLowerCase()} threads right now.`,
    description:
      "Switch filters to inspect a different slice of the legal workload.",
  };
}

function buildCountsFromQueueItems(
  items: ReviewQueueItem[],
): ReviewQueueCounts {
  return items.reduce<ReviewQueueCounts>(
    (counts, item) => ({
      total: counts.total + 1,
      mine: counts.mine + Number(item.is_mine),
      unassigned: counts.unassigned + Number(item.is_unassigned),
      overdue: counts.overdue + Number(item.is_overdue),
      escalated: counts.escalated + Number(item.is_escalated),
    }),
    {
      total: 0,
      mine: 0,
      unassigned: 0,
      overdue: 0,
      escalated: 0,
    },
  );
}

type ReviewQueueStatusVariant = "loading" | "auth" | "restricted" | "temporary";

function ReviewQueueStatusState({
  onRetry,
  variant,
}: {
  onRetry?: () => void;
  variant: ReviewQueueStatusVariant;
}) {
  const isPending = variant === "loading" || variant === "auth";
  const copy = {
    loading: {
      actionLabel: undefined,
      contextItems: [
        "Reviewer queue requested",
        "Assignments remain unchanged",
        "Actions wait for a fresh view",
      ],
      description:
        "Loading queued analyses, ownership handoffs, SLA flags, and escalation context for the current reviewer scope.",
      eyebrow: "Reviewer workspace",
      icon: Loader2,
      recoveryBody:
        "Assignment, escalation, and resolution controls remain unavailable until the latest queue state is loaded.",
      recoveryTitle: "Opening the current reviewer queue",
      title: "Loading legal review queue",
      tone: "default" as const,
    },
    auth: {
      actionLabel: undefined,
      contextItems: [
        "Session check in progress",
        "Queue records remain private",
        "Review controls unlock after access",
      ],
      description:
        "Praviar waits for a reviewer-scoped session before requesting queue work.",
      eyebrow: "Review access",
      icon: LockKeyhole,
      recoveryBody:
        "No assignments or thread states are shown until access is confirmed for this organization.",
      recoveryTitle: "Preparing a governed review queue",
      title: "Checking review queue access",
      tone: "default" as const,
    },
    restricted: {
      actionLabel: undefined,
      contextItems: [
        "Reviewer role required",
        "No assignments exposed",
        "Ask an admin to update access",
      ],
      description:
        "This queue is available to internal scientific and legal reviewers. No assignments or thread states were changed.",
      eyebrow: "Review access",
      icon: AlertTriangle,
      recoveryBody:
        "Ask an organization administrator to review your role assignment before opening reviewer-scoped work.",
      recoveryTitle: "Use a reviewer-enabled account",
      title: "Review queue access restricted",
      tone: "warning" as const,
    },
    temporary: {
      actionLabel: "Retry",
      contextItems: [
        "No assignments changed",
        "Retry requests a fresh view",
        "Private reviewer records withheld",
      ],
      description: REVIEW_QUEUE_LOAD_ERROR_COPY,
      eyebrow: "Review queue load",
      icon: Scale,
      recoveryBody:
        "A retry asks for the latest reviewer-scoped queue without changing owners, escalations, or thread resolution.",
      recoveryTitle: "Retry the review queue request",
      title: "Review queue temporarily unavailable.",
      tone: "error" as const,
    },
  }[variant];

  return (
    <div className="mx-auto max-w-6xl space-y-6 animate-fade-up">
      <ReviewQueuePageHeader />
      <OperationalStatusFrame
        actionLabel={copy.actionLabel}
        aiBrief={
          variant === "temporary"
            ? {
                items: [
                  "Keep reviewer assignments and thread states unchanged while the queue reloads.",
                  "Retry only requests the latest reviewer-scoped queue snapshot.",
                  "Use open report packets as temporary handoff context until queue state returns.",
                ],
                note: "No owner update, escalation, or resolution action is submitted from this recovery state.",
              }
            : undefined
        }
        contextItems={copy.contextItems}
        dataTestId={`review-queue-${variant}`}
        description={copy.description}
        eyebrow={copy.eyebrow}
        icon={copy.icon}
        isLoading={variant === "loading"}
        isPending={isPending}
        onRetry={onRetry}
        recoveryBody={copy.recoveryBody}
        recoveryTitle={copy.recoveryTitle}
        title={copy.title}
        titleId={`review-queue-${variant}-title`}
        tone={copy.tone}
      />
    </div>
  );
}

function ReviewQueueRefreshWarning({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      role="status"
      className="rounded-lg border border-warning/20 bg-warning/10 px-4 py-3"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-2">
          <AlertTriangle
            className="mt-0.5 h-4 w-4 shrink-0 text-warning"
            aria-hidden="true"
          />
          <p className="text-sm leading-6 text-[var(--text-secondary)]">
            Review queue refresh failed. Existing reviewer data remains visible,
            and no assignments or thread states were changed by the refresh.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="min-h-11 w-full sm:w-auto"
          onClick={onRetry}
        >
          Retry refresh
        </Button>
      </div>
    </div>
  );
}

function ReviewQueueScopeNotice({
  workloadLabel,
  orgCount,
  visibleCount,
}: {
  workloadLabel: string;
  orgCount: number;
  visibleCount: number;
}) {
  return (
    <div
      role="status"
      className="rounded-lg border border-brand-primary/20 bg-brand-primary/[0.06] px-4 py-3"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-sm font-medium text-[var(--text-primary)]">
            Showing your assigned {workloadLabel} workload
          </p>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            {visibleCount} assigned-to-you thread
            {visibleCount === 1 ? "" : "s"} shown from {orgCount} current-filter{" "}
            {workloadLabel} thread
            {orgCount === 1 ? "" : "s"}. Filter tiles reflect the current queue
            response.
          </p>
        </div>
        <Badge
          variant="outline"
          className="w-fit px-2 py-0 text-xs font-semibold uppercase"
        >
          Reviewer scope
        </Badge>
      </div>
    </div>
  );
}

function ReviewQueueControlCard({
  activeLabel,
  visibleCount,
  allVisibleSelected,
  selectedCount,
  selectAllRef,
  onSelectAllVisible,
  onClearSelection,
  sortMode,
  onSortModeChange,
  controlsLocked = false,
  lockMessage,
}: {
  activeLabel: string;
  visibleCount: number;
  allVisibleSelected: boolean;
  selectedCount: number;
  selectAllRef: RefObject<HTMLInputElement | null>;
  onSelectAllVisible: () => void;
  onClearSelection: () => void;
  sortMode: ReviewQueueSortMode;
  onSortModeChange: (mode: ReviewQueueSortMode) => void;
  controlsLocked?: boolean;
  lockMessage?: string;
}) {
  const activeSort = REVIEW_QUEUE_SORT_OPTIONS.find(
    (option) => option.value === sortMode,
  );

  return (
    <div className="p-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-2">
          <div>
            <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
              {activeLabel} threads
            </p>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              <span className="font-medium text-[var(--text-primary)]">
                {visibleCount} visible
              </span>{" "}
              · sorted by {activeSort?.label.toLowerCase() ?? "priority"}
              {activeSort?.description ? ` · ${activeSort.description}` : ""}
            </p>
          </div>
          <div className="grid gap-2 sm:flex sm:flex-wrap sm:items-center sm:gap-3">
            <label
              htmlFor="review-queue-sort"
              className="text-sm font-medium text-[var(--text-primary)]"
            >
              Queue sort
            </label>
            <div className="relative w-full sm:w-auto">
              <ArrowUpDown className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-tertiary)]" />
              <select
                id="review-queue-sort"
                aria-label="Queue ordering"
                value={sortMode}
                disabled={controlsLocked}
                onChange={(event) =>
                  onSortModeChange(event.target.value as ReviewQueueSortMode)
                }
                className="h-11 w-full rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-muted)] py-2 pl-9 pr-3 text-sm text-[var(--text-primary)] outline-none transition-colors focus:border-brand-primary/40 focus:ring-2 focus:ring-brand-primary/30 disabled:cursor-not-allowed disabled:border-[var(--border-subtle)] disabled:text-[var(--text-disabled)] sm:min-w-[13rem]"
              >
                {REVIEW_QUEUE_SORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div className="grid gap-3 sm:flex sm:flex-wrap sm:items-center">
          <label
            htmlFor="review-queue-select-visible"
            className="relative flex min-h-11 items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-3 py-2 text-sm text-[var(--text-primary)] sm:rounded-full"
          >
            <input
              ref={selectAllRef}
              id="review-queue-select-visible"
              type="checkbox"
              checked={allVisibleSelected}
              disabled={controlsLocked}
              onChange={onSelectAllVisible}
              aria-label={`Select all visible ${activeLabel.toLowerCase()} threads`}
              className="peer absolute inset-0 z-10 h-full w-full cursor-pointer appearance-none rounded-lg opacity-0 focus-visible:outline-none disabled:cursor-not-allowed sm:rounded-full"
            />
            <span
              aria-hidden="true"
              className="pointer-events-none flex h-6 w-6 shrink-0 items-center justify-center rounded border border-[var(--border-emphasis)] bg-[var(--bg-surface)] text-transparent peer-checked:border-brand-primary peer-checked:bg-brand-primary peer-checked:text-[var(--brand-paper)] peer-focus-visible:ring-2 peer-focus-visible:ring-brand-primary/60 peer-focus-visible:ring-offset-2"
            >
              <Check className="h-4 w-4" />
            </span>
            <span>Select visible items</span>
          </label>
          {selectedCount > 0 ? (
            <Badge
              variant="secondary"
              className="rounded-full px-3 py-1 text-xs font-semibold uppercase"
            >
              {selectedCount} selected
            </Badge>
          ) : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onClearSelection}
            disabled={selectedCount === 0 || controlsLocked}
            className="min-h-11 w-full sm:w-auto"
          >
            Clear selection
          </Button>
        </div>
      </div>
      {controlsLocked ? (
        <p
          role="status"
          aria-live="polite"
          className="mt-3 text-xs font-medium text-[var(--text-tertiary)]"
        >
          {lockMessage ??
            "Applying review queue update. Filters, sort, and selection are locked until the queue settles."}
        </p>
      ) : null}
    </div>
  );
}

function ReviewQueueTriageRail({
  counts,
  activeLabel,
  selectedCount,
  visibleCount,
  reviewerScopeActive,
}: {
  counts: ReviewQueueCounts;
  activeLabel: string;
  selectedCount: number;
  visibleCount: number;
  reviewerScopeActive: boolean;
}) {
  const assignmentScope = reviewerScopeActive ? "assigned to you" : "open";
  const nextAction =
    counts.overdue > 0
      ? {
          title: "Clear past-SLA threads first",
          detail: `${counts.overdue} overdue review thread${counts.overdue === 1 ? "" : "s"} ${reviewerScopeActive ? "assigned to you " : ""}${counts.overdue === 1 ? "needs" : "need"} a response before routine ownership cleanup.`,
          tone: "warning" as const,
        }
      : counts.escalated > 0
        ? {
            title: "Review counsel escalations",
            detail: `${counts.escalated} escalated thread${counts.escalated === 1 ? "" : "s"} ${reviewerScopeActive ? "assigned to you " : ""}are waiting for legal decisioning.`,
            tone: "danger" as const,
          }
        : counts.unassigned > 0
          ? {
              title: "Assign ownership",
              detail: `${counts.unassigned} ${assignmentScope} thread${counts.unassigned === 1 ? "" : "s"} still need a named reviewer.`,
              tone: "brand" as const,
            }
          : {
              title: reviewerScopeActive
                ? "Your slice is controlled"
                : "Queue is controlled",
              detail: reviewerScopeActive
                ? "No overdue or escalated threads assigned to you are visible in this slice."
                : "Open review threads have owners and no urgent SLA flags.",
              tone: "neutral" as const,
            };

  return (
    <aside
      aria-label="Review queue cockpit"
      className="space-y-4 xl:sticky xl:top-24"
    >
      <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-card)] p-4 shadow-[var(--shadow-xs)]">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
              Reviewer cockpit
            </p>
            <h2 className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
              {nextAction.title}
            </h2>
          </div>
          <span
            className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-md",
              nextAction.tone === "warning"
                ? "bg-warning/15 text-warning"
                : nextAction.tone === "danger"
                  ? "bg-error/10 text-error"
                  : nextAction.tone === "brand"
                    ? "bg-brand-primary/15 text-brand-primary"
                    : "bg-[var(--surface-muted)] text-[var(--text-tertiary)]",
            )}
          >
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
          </span>
        </div>
        <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
          {nextAction.detail}
        </p>
        <dl className="mt-4 grid grid-cols-2 gap-3">
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-3 py-2">
            <dt className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
              Visible
            </dt>
            <dd className="mt-1 text-lg font-semibold tabular-nums text-[var(--text-primary)]">
              {visibleCount}
            </dd>
          </div>
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-3 py-2">
            <dt className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
              Selected
            </dt>
            <dd className="mt-1 text-lg font-semibold tabular-nums text-[var(--text-primary)]">
              {selectedCount}
            </dd>
          </div>
        </dl>
      </div>

      <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-card)] p-4">
        <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
          Work mode
        </p>
        <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">
          {activeLabel}
        </p>
        <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
          {reviewerScopeActive
            ? "Scoped to threads assigned to you for overdue and escalated handoffs."
            : "Showing the organization queue slice with URL-backed filter and sort state."}
        </p>
      </div>

      <div className="rounded-lg border border-brand-primary/20 bg-brand-primary/[0.05] p-4">
        <p className="text-xs font-semibold uppercase text-brand-primary">
          Evidence readiness
        </p>
        <div className="mt-3 space-y-2">
          <ReadinessSignal
            label="Blocking risk"
            value={`${counts.escalated} escalated`}
            tone={counts.escalated > 0 ? "danger" : "neutral"}
          />
          <ReadinessSignal
            label="SLA exposure"
            value={`${counts.overdue} overdue`}
            tone={counts.overdue > 0 ? "warning" : "neutral"}
          />
          <ReadinessSignal
            label="Owner gaps"
            value={`${counts.unassigned} unassigned`}
            tone={counts.unassigned > 0 ? "brand" : "neutral"}
          />
        </div>
        <p className="mt-3 text-xs leading-5 text-[var(--text-secondary)]">
          Batch reviewer updates require confirmation before Praviar changes
          assignment, escalation, or resolution state.
        </p>
      </div>
    </aside>
  );
}

function ReadinessSignal({
  label,
  tone,
  value,
}: {
  label: string;
  tone: "brand" | "danger" | "neutral" | "warning";
  value: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 py-2">
      <span className="text-xs text-[var(--text-secondary)]">{label}</span>
      <span
        className={cn(
          "text-xs font-semibold tabular-nums",
          tone === "danger" && "text-error",
          tone === "warning" && "text-warning",
          tone === "brand" && "text-brand-primary",
          tone === "neutral" && "text-[var(--text-primary)]",
        )}
      >
        {value}
      </span>
    </div>
  );
}

function ReviewQueueSelectionRow({
  item,
  selected,
  onToggle,
  token,
  onQueueRefresh,
  controlsLocked = false,
  onActionPendingChange,
}: {
  item: ReviewQueueItem;
  selected: boolean;
  onToggle: (itemId: string) => void;
  token: string | null;
  onQueueRefresh: () => Promise<unknown> | Promise<void>;
  controlsLocked?: boolean;
  onActionPendingChange?: (sourceId: string, pending: boolean) => void;
}) {
  const selectionControl = (
    <label
      className={cn(
        "relative flex min-h-11 shrink-0 items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)]",
        controlsLocked && "cursor-not-allowed opacity-60",
      )}
    >
      <input
        type="checkbox"
        checked={selected}
        disabled={controlsLocked}
        onChange={() => onToggle(item.id)}
        aria-label={`Select ${item.compound_name} thread`}
        className="peer absolute inset-0 z-10 h-full w-full cursor-pointer appearance-none rounded-md opacity-0 focus-visible:outline-none disabled:cursor-not-allowed"
      />
      <span
        aria-hidden="true"
        className="pointer-events-none flex h-6 w-6 shrink-0 items-center justify-center rounded border border-[var(--border-emphasis)] bg-[var(--bg-surface)] text-transparent peer-checked:border-brand-primary peer-checked:bg-brand-primary peer-checked:text-[var(--brand-paper)] peer-focus-visible:ring-2 peer-focus-visible:ring-brand-primary/60 peer-focus-visible:ring-offset-2"
      >
        <Check className="h-4 w-4" />
      </span>
      <span>Select</span>
    </label>
  );

  return (
    <div
      className={cn(
        "rounded-lg p-1 transition-colors",
        selected
          ? "bg-brand-primary/5 ring-1 ring-brand-primary/25"
          : "bg-transparent",
      )}
    >
      <div className="min-w-0 flex-1">
        <ReviewQueueItemCard
          item={item}
          token={token}
          onQueueRefresh={onQueueRefresh}
          selectionControl={selectionControl}
          actionsDisabled={controlsLocked}
          actionPendingSourceId={`item:${item.id}`}
          onActionPendingChange={onActionPendingChange}
        />
      </div>
    </div>
  );
}

export function ReviewQueuePage({
  token,
  initialFilter = "mine",
  initialSortMode = "priority",
  initialReviewerScope = "all",
}: ReviewQueuePageProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [activeFilter, setActiveFilter] =
    useState<ReviewQueueFilter>(initialFilter);
  const [sortMode, setSortMode] =
    useState<ReviewQueueSortMode>(initialSortMode);
  const [selectionState, setSelectionState] =
    useState<ReviewQueueSelectionState>({
      itemIds: EMPTY_SELECTED_ITEM_IDS,
    });
  const [bulkActionFeedback, setBulkActionFeedback] =
    useState<ReviewQueueBulkActionSuccess | null>(null);
  const [pendingActionSources, setPendingActionSources] = useState<
    Record<string, true>
  >({});
  const { data, isLoading, isError, refetch } = useReviewQueue(
    token,
    activeFilter,
  );
  const queueData = data && !("forbidden" in data) ? data : null;

  const items = queueData?.items ?? EMPTY_QUEUE_ITEMS;
  const reviewerScopeActive = shouldApplyReviewerScope(
    activeFilter,
    initialReviewerScope,
  );
  const visibleItems = useMemo(
    () => (reviewerScopeActive ? items.filter((item) => item.is_mine) : items),
    [items, reviewerScopeActive],
  );
  const workloadCounts = useMemo(
    () =>
      reviewerScopeActive ? buildCountsFromQueueItems(visibleItems) : null,
    [reviewerScopeActive, visibleItems],
  );
  const sortedItems = useMemo(
    () => sortReviewQueueItems(visibleItems, sortMode),
    [sortMode, visibleItems],
  );
  const visibleItemIdSet = useMemo(
    () => new Set(sortedItems.map((item) => item.id)),
    [sortedItems],
  );
  const currentItemIdSet = useMemo(
    () => new Set(items.map((item) => item.id)),
    [items],
  );
  const selectedItemIds = selectionState.itemIds;
  const selectedVisibleItemIds = useMemo(
    () => selectedItemIds.filter((itemId) => visibleItemIdSet.has(itemId)),
    [selectedItemIds, visibleItemIdSet],
  );
  const selectedVisibleItems = useMemo(
    () =>
      sortedItems.filter((item) => selectedVisibleItemIds.includes(item.id)),
    [selectedVisibleItemIds, sortedItems],
  );
  const selectedCount = selectedVisibleItemIds.length;
  const allVisibleSelected =
    sortedItems.length > 0 && selectedCount === sortedItems.length;
  const someVisibleSelected = selectedCount > 0 && !allVisibleSelected;
  const queueActionPending = Object.keys(pendingActionSources).length > 0;
  const queueControlsLocked = queueActionPending || isError;
  const selectAllRef = useRef<HTMLInputElement | null>(null);
  const bulkFeedbackDismissRef = useRef<HTMLButtonElement | null>(null);

  const setQueueActionSourcePending = useCallback(
    (sourceId: string, pending: boolean) => {
      setPendingActionSources((previousSources) => {
        if (pending) {
          if (previousSources[sourceId]) return previousSources;
          return { ...previousSources, [sourceId]: true };
        }

        if (!previousSources[sourceId]) return previousSources;
        const nextSources = { ...previousSources };
        delete nextSources[sourceId];
        return nextSources;
      });
    },
    [],
  );

  useEffect(() => {
    const prunedItemIds = selectionState.itemIds.filter((itemId) =>
      currentItemIdSet.has(itemId),
    );

    if (prunedItemIds.length === selectionState.itemIds.length) {
      return undefined;
    }

    const pruneTimer = window.setTimeout(() => {
      setSelectionState((previousState) => {
        const latestPrunedItemIds = previousState.itemIds.filter((itemId) =>
          currentItemIdSet.has(itemId),
        );

        if (latestPrunedItemIds.length === previousState.itemIds.length) {
          return previousState;
        }

        return { itemIds: latestPrunedItemIds };
      });
    }, 0);

    return () => window.clearTimeout(pruneTimer);
  }, [currentItemIdSet, selectionState.itemIds]);

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = someVisibleSelected;
    }
  }, [someVisibleSelected]);

  useEffect(() => {
    if (!bulkActionFeedback) {
      return undefined;
    }

    const focusTimer = window.setTimeout(() => {
      bulkFeedbackDismissRef.current?.focus();
    }, 0);

    return () => window.clearTimeout(focusTimer);
  }, [bulkActionFeedback]);

  const toggleVisibleSelection = () => {
    if (queueControlsLocked) return;

    setBulkActionFeedback(null);
    setSelectionState((previousState) => {
      const previous = previousState.itemIds;
      const visibleIds = sortedItems.map((item) => item.id);
      const visibleSelection = previous.filter((itemId) =>
        visibleItemIdSet.has(itemId),
      );
      if (visibleSelection.length === visibleIds.length) {
        return {
          itemIds: previous.filter((itemId) => !visibleItemIdSet.has(itemId)),
        };
      }
      return {
        itemIds: Array.from(new Set([...previous, ...visibleIds])),
      };
    });
  };

  const toggleItemSelection = (itemId: string) => {
    if (queueControlsLocked) return;

    setBulkActionFeedback(null);
    setSelectionState((previousState) => {
      const previous = previousState.itemIds;
      return {
        itemIds: previous.includes(itemId)
          ? previous.filter((selectedId) => selectedId !== itemId)
          : [...previous, itemId],
      };
    });
  };

  const clearSelection = () =>
    setSelectionState({ itemIds: EMPTY_SELECTED_ITEM_IDS });
  const clearSelectionFromUi = () => {
    if (queueControlsLocked) return;
    clearSelection();
  };
  const handleBulkActionComplete = (payload: ReviewQueueBulkActionSuccess) => {
    setBulkActionFeedback(payload);
  };

  useAuthBoundaryReset(() => {
    setSelectionState({
      itemIds: EMPTY_SELECTED_ITEM_IDS,
    });
    setBulkActionFeedback(null);
  });
  const replaceQueueUrl = ({
    filter,
    nextSortMode,
  }: {
    filter: ReviewQueueFilter;
    nextSortMode: ReviewQueueSortMode;
  }) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("filter", filter);
    params.set("sort", nextSortMode);
    params.delete("focus");
    if (
      initialReviewerScope === "mine" &&
      (filter === "overdue" || filter === "escalated")
    ) {
      params.set("scope", "mine");
    } else {
      params.delete("scope");
    }
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  };
  const handleFilterChange = (filter: ReviewQueueFilter) => {
    if (queueControlsLocked) return;

    setBulkActionFeedback(null);
    clearSelection();
    setActiveFilter(filter);
    replaceQueueUrl({ filter, nextSortMode: sortMode });
  };
  const handleSortModeChange = (nextSortMode: ReviewQueueSortMode) => {
    if (queueControlsLocked) return;

    setSortMode(nextSortMode);
    replaceQueueUrl({ filter: activeFilter, nextSortMode });
  };

  if (isLoading) {
    return <ReviewQueueStatusState variant="loading" />;
  }

  if (data && "forbidden" in data && data.forbidden) {
    return <ReviewQueueStatusState variant="restricted" />;
  }

  if (isError && !queueData) {
    return (
      <ReviewQueueStatusState
        variant="temporary"
        onRetry={() => {
          void refetch();
        }}
      />
    );
  }

  if (!queueData) {
    return <ReviewQueueStatusState variant="auth" />;
  }

  const counts = queueData?.counts ?? {
    total: 0,
    mine: 0,
    unassigned: 0,
    overdue: 0,
    escalated: 0,
  };
  const baseActiveLabel =
    FILTERS.find((filter) => filter.value === activeFilter)?.label ?? "Mine";
  const activeLabel = getActiveQueueLabel(
    activeFilter,
    baseActiveLabel,
    reviewerScopeActive,
  );
  const emptyStateCopy = getEmptyStateCopy(
    activeFilter,
    activeLabel,
    reviewerScopeActive,
  );
  const activeWorkloadCounts = workloadCounts ?? counts;
  const activeOrgFilterCount = counts[activeFilter];

  return (
    <div className="mx-auto max-w-6xl space-y-6 animate-fade-up">
      <ReviewQueuePageHeader
        reviewerScopeActive={reviewerScopeActive}
        openThreads={counts.total}
        priorityMatterName={sortedItems[0]?.compound_name}
      />

      <ReviewQueueStatusStrip
        counts={activeWorkloadCounts}
        orgCounts={reviewerScopeActive ? counts : undefined}
        activeLabel={activeLabel}
        visibleCount={sortedItems.length}
        updatedAt={queueData.updated_at}
        reviewerScopeActive={reviewerScopeActive}
      />

      {reviewerScopeActive ? (
        <ReviewQueueScopeNotice
          workloadLabel={activeFilter === "overdue" ? "overdue" : "escalated"}
          orgCount={activeOrgFilterCount}
          visibleCount={sortedItems.length}
        />
      ) : null}

      {isError ? (
        <ReviewQueueRefreshWarning
          onRetry={() => {
            void refetch();
          }}
        />
      ) : null}

      <div
        data-testid="review-queue-filter-grid"
        className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4"
      >
        {FILTERS.map((filter) => {
          const Icon = filter.icon;
          const count = counts[filter.countKey];
          const isActive = filter.value === activeFilter;

          return (
            <button
              key={filter.value}
              type="button"
              aria-label={`${filter.label}: ${count} ${reviewerScopeActive ? "org " : ""}open thread${count === 1 ? "" : "s"}`}
              aria-pressed={isActive}
              disabled={queueControlsLocked}
              onClick={() => handleFilterChange(filter.value)}
              className={cn(
                "min-h-24 rounded-lg border p-4 text-left transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--surface-background)] disabled:cursor-not-allowed disabled:opacity-60",
                isActive
                  ? "border-brand-primary/30 bg-brand-primary/10 shadow-[var(--shadow-xs)]"
                  : "border-[var(--border-subtle)] bg-[var(--surface-card)] hover:border-[var(--border-default)] hover:bg-[var(--surface-hover)]",
                filter.tone === "warning" &&
                  (isActive
                    ? "border-warning/35 bg-warning/10"
                    : "hover:border-warning/30"),
                filter.tone === "danger" &&
                  (isActive
                    ? "border-error/30 bg-error/10"
                    : "hover:border-error/25"),
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex min-w-0 items-center gap-2">
                    <span
                      className={cn(
                        "flex h-8 w-8 shrink-0 items-center justify-center rounded-md",
                        isActive
                          ? "bg-brand-primary/15 text-brand-primary"
                          : "bg-[var(--surface-muted)] text-[var(--text-tertiary)]",
                        filter.tone === "warning" &&
                          (isActive
                            ? "bg-warning/15 text-warning"
                            : "text-warning"),
                        filter.tone === "danger" &&
                          (isActive ? "bg-error/10 text-error" : "text-error"),
                      )}
                    >
                      <Icon className="h-4 w-4" aria-hidden="true" />
                    </span>
                    <span className="text-sm font-semibold text-[var(--text-primary)]">
                      {filter.label}
                    </span>
                  </div>
                  <span className="mt-2 block text-xs text-[var(--text-secondary)]">
                    {reviewerScopeActive &&
                    (filter.value === "overdue" || filter.value === "escalated")
                      ? `${filter.helper} · org count`
                      : filter.helper}
                  </span>
                </div>
                <span className="shrink-0 text-2xl font-semibold tabular-nums text-[var(--text-primary)]">
                  {count}
                </span>
              </div>
            </button>
          );
        })}
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <section
          aria-label="Review queue worklist"
          aria-busy={queueActionPending}
          className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-card)] shadow-[var(--shadow-xs)]"
        >
          <div className="border-b border-[var(--border-subtle)] bg-[var(--surface-glass)]">
            <ReviewQueueControlCard
              activeLabel={activeLabel}
              visibleCount={sortedItems.length}
              allVisibleSelected={allVisibleSelected}
              selectedCount={selectedCount}
              selectAllRef={selectAllRef}
              onSelectAllVisible={toggleVisibleSelection}
              onClearSelection={clearSelectionFromUi}
              sortMode={sortMode}
              onSortModeChange={handleSortModeChange}
              controlsLocked={queueControlsLocked}
              lockMessage={
                isError
                  ? "Review queue refresh failed. Filters, sort, selection, and queue actions are locked until the queue refreshes."
                  : undefined
              }
            />
          </div>
          <div className="space-y-3 p-4">
            {bulkActionFeedback ? (
              <div
                role="status"
                aria-live="polite"
                className="rounded-lg border border-brand-primary/20 bg-brand-primary/5 px-4 py-3"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge
                        variant="default"
                        className="px-2 py-0 text-xs font-semibold uppercase"
                      >
                        Queue updated
                      </Badge>
                      <span className="text-sm text-[var(--text-secondary)]">
                        {buildBulkActionFeedbackMessage(bulkActionFeedback)}
                      </span>
                    </div>
                    <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                      {buildBulkActionChangeSummary(bulkActionFeedback)}
                    </p>
                  </div>
                  <Button
                    ref={bulkFeedbackDismissRef}
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="min-h-11 w-full shrink-0 gap-2 sm:w-auto"
                    disabled={queueControlsLocked}
                    onClick={() => {
                      if (queueControlsLocked) return;
                      setBulkActionFeedback(null);
                    }}
                  >
                    <X className="h-4 w-4" aria-hidden="true" />
                    Dismiss update
                  </Button>
                </div>
              </div>
            ) : null}
            <ReviewQueueBulkToolbar
              token={token}
              selectedItems={selectedVisibleItems}
              onClearSelection={clearSelection}
              onActionComplete={handleBulkActionComplete}
              mode="compact"
              actionsDisabled={queueControlsLocked}
              actionPendingSourceId="bulk"
              onActionPendingChange={setQueueActionSourcePending}
            />
            {sortedItems.length > 0 ? (
              sortedItems.map((item) => (
                <ReviewQueueSelectionRow
                  key={item.id}
                  item={item}
                  selected={selectedVisibleItemIds.includes(item.id)}
                  onToggle={toggleItemSelection}
                  token={token}
                  onQueueRefresh={() => refetch()}
                  controlsLocked={queueControlsLocked}
                  onActionPendingChange={setQueueActionSourcePending}
                />
              ))
            ) : (
              <div className="rounded-lg border border-dashed border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-4 py-10 text-center">
                <FileSearch className="mx-auto h-8 w-8 text-[var(--text-disabled)]" />
                <p className="mt-3 text-sm font-medium text-[var(--text-primary)]">
                  {emptyStateCopy.title}
                </p>
                <p className="mt-1 text-sm text-[var(--text-secondary)]">
                  {emptyStateCopy.description}
                </p>
              </div>
            )}
          </div>
        </section>

        <ReviewQueueTriageRail
          counts={activeWorkloadCounts}
          activeLabel={activeLabel}
          selectedCount={selectedCount}
          visibleCount={sortedItems.length}
          reviewerScopeActive={reviewerScopeActive}
        />
      </div>
    </div>
  );
}
