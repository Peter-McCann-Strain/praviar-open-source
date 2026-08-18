"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Loader2,
  Users,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RiskBadge } from "@/components/shared/risk-badge";
import { StatusBadge } from "@/components/shared/status-badge";
import { relativeTime } from "@/components/dashboard/helpers";
import { cn } from "@/lib/utils";
import {
  useAssignComment,
  useCommentReviewers,
  useEscalateComment,
  useToggleCommentResolution,
  type CommentReviewer,
} from "@/hooks/use-comments";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";
import { useHydrationSafeRelativeTime } from "@/hooks/use-hydration-safe-relative-time";
import {
  REVIEWER_LIST_ERROR_COPY,
  buildReviewQueueActionError,
} from "@/components/reviews/review-queue-errors";
import {
  buildReviewQueueItemHref,
  getReviewQueueItemActionLabel,
} from "@/components/reviews/review-queue-routing";
import type { ReviewQueueItem } from "@/hooks/use-review-queue";

interface ReviewQueueItemCardProps {
  item: ReviewQueueItem;
  token: string | null;
  onQueueRefresh: () => Promise<unknown> | Promise<void>;
  selectionControl?: ReactNode;
  actionsDisabled?: boolean;
  actionPendingSourceId?: string;
  onActionPendingChange?: (sourceId: string, pending: boolean) => void;
}

type PendingSingleConfirmation = "resolve" | "escalate";
type PendingAction = "assign" | "resolve" | "escalate" | null;

interface ReviewerSelection {
  itemId: string;
  reviewerId: string;
}

interface SavedOwner {
  itemId: string;
  reviewerId: string | null;
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
  if (item.is_escalated) {
    flags.push({ label: "Escalated", variant: "destructive" });
  }

  return flags;
}

function formatAssignee(item: ReviewQueueItem): string {
  if (item.is_unassigned) {
    return "Unassigned";
  }
  return item.assigned_to_name ?? item.assigned_to_email ?? "Assigned";
}

function getPriorityRailClass(item: ReviewQueueItem): string {
  if (item.is_escalated || item.overall_risk === "high") {
    return "bg-error";
  }
  if (item.is_overdue) {
    return "bg-warning";
  }
  if (item.is_unassigned) {
    return "bg-brand-primary";
  }
  return "bg-[var(--border-emphasis)]";
}

function needsSingleDecisionConfirmation(item: ReviewQueueItem): boolean {
  return item.is_overdue || item.is_escalated || item.overall_risk === "high";
}

function getSingleConfirmationTitle(action: PendingSingleConfirmation): string {
  return action === "escalate"
    ? "Confirm legal escalation"
    : "Confirm thread resolution";
}

function getSingleConfirmationButtonLabel(
  action: PendingSingleConfirmation,
): string {
  return action === "escalate" ? "Confirm escalation" : "Confirm resolution";
}

function getSingleConfirmationConsequence(
  action: PendingSingleConfirmation,
): string {
  if (action === "escalate") {
    return "This thread will be promoted for counsel attention and remain visible until the refreshed queue lands.";
  }

  return "Resolved threads leave open review queues once the refreshed queue lands. Confirm only after the legal decision has been captured.";
}

function getSingleConfirmationRiskSummary(item: ReviewQueueItem): string {
  const summaries = [
    item.overall_risk === "high" ? "High-risk thread" : null,
    item.is_overdue ? (item.overdue_label ?? "Overdue thread") : null,
    item.is_escalated ? "Escalated thread" : null,
  ].filter(Boolean);

  return summaries.length > 0 ? summaries.join(" · ") : "No urgent flags";
}

function getCurrentReviewerId(
  item: ReviewQueueItem,
  savedOwner: SavedOwner | null,
): string {
  if (savedOwner?.itemId === item.id) return savedOwner.reviewerId ?? "";
  return item.assigned_to_id ?? "";
}

function getOwnerHelperText({
  canClearCurrentOwner,
  hasCurrentOwner,
  hasReviewerOptions,
  isLoadingReviewers,
  selectedReviewer,
}: {
  canClearCurrentOwner: boolean;
  hasCurrentOwner: boolean;
  hasReviewerOptions: boolean;
  isLoadingReviewers: boolean;
  selectedReviewer: CommentReviewer | null;
}): string {
  if (selectedReviewer) return `Selected: ${selectedReviewer.label}`;
  if (canClearCurrentOwner) return "Selected: Unassigned";
  if (!hasReviewerOptions && hasCurrentOwner && !isLoadingReviewers) {
    return "Reviewer list unavailable; owner clearing remains available.";
  }
  return "Select an owner or leave unassigned.";
}

function canUseOwnerControl({
  actionsDisabled,
  canAssignReview,
  hasCurrentOwner,
  hasReviewerOptions,
  isLoadingReviewers,
  pendingAction,
  pendingConfirmation,
}: {
  actionsDisabled: boolean;
  canAssignReview: boolean;
  hasCurrentOwner: boolean;
  hasReviewerOptions: boolean;
  isLoadingReviewers: boolean;
  pendingAction: PendingAction;
  pendingConfirmation: PendingSingleConfirmation | null;
}): boolean {
  return (
    canAssignReview &&
    !actionsDisabled &&
    !isLoadingReviewers &&
    pendingAction === null &&
    pendingConfirmation === null &&
    (hasReviewerOptions || hasCurrentOwner)
  );
}

function canSubmitOwnerAssignment({
  assignIsPending,
  canClearCurrentOwner,
  canUseControl,
  currentReviewerId,
  hasReviewerOptions,
  selectedReviewerId,
}: {
  assignIsPending: boolean;
  canClearCurrentOwner: boolean;
  canUseControl: boolean;
  currentReviewerId: string;
  hasReviewerOptions: boolean;
  selectedReviewerId: string;
}): boolean {
  return (
    canUseControl &&
    !assignIsPending &&
    selectedReviewerId !== currentReviewerId &&
    (canClearCurrentOwner || hasReviewerOptions)
  );
}

function buildOwnerViewModel({
  actionsDisabled,
  assignIsPending,
  canAssignReview,
  isLoadingReviewers,
  item,
  pendingAction,
  pendingConfirmation,
  reviewerOptions,
  reviewerSelection,
  savedOwner,
}: {
  actionsDisabled: boolean;
  assignIsPending: boolean;
  canAssignReview: boolean;
  isLoadingReviewers: boolean;
  item: ReviewQueueItem;
  pendingAction: PendingAction;
  pendingConfirmation: PendingSingleConfirmation | null;
  reviewerOptions: CommentReviewer[];
  reviewerSelection: ReviewerSelection | null;
  savedOwner: SavedOwner | null;
}) {
  const hasSavedOwnerForItem = savedOwner?.itemId === item.id;
  const currentReviewerId = getCurrentReviewerId(item, savedOwner);
  const selectedReviewerId =
    reviewerSelection?.itemId === item.id
      ? reviewerSelection.reviewerId
      : currentReviewerId;
  const selectedReviewer =
    reviewerOptions.find((reviewer) => reviewer.id === selectedReviewerId) ??
    null;
  const hasReviewerOptions = reviewerOptions.length > 0;
  const hasCurrentOwner = currentReviewerId.length > 0;
  const canClearCurrentOwner = hasCurrentOwner && selectedReviewerId === "";
  const currentOwnerMissingFromOptions =
    hasCurrentOwner &&
    !reviewerOptions.some((reviewer) => reviewer.id === currentReviewerId);
  const ownerControlEnabled = canUseOwnerControl({
    actionsDisabled,
    canAssignReview,
    hasCurrentOwner,
    hasReviewerOptions,
    isLoadingReviewers,
    pendingAction,
    pendingConfirmation,
  });

  return {
    canAssign: canSubmitOwnerAssignment({
      assignIsPending,
      canClearCurrentOwner,
      canUseControl: ownerControlEnabled,
      currentReviewerId,
      hasReviewerOptions,
      selectedReviewerId,
    }),
    canUseOwnerControl: ownerControlEnabled,
    currentOwnerMissingFromOptions,
    currentReviewerId,
    displayedAssignee: hasSavedOwnerForItem
      ? (selectedReviewer?.label ?? "Unassigned")
      : formatAssignee(item),
    hasCurrentOwner,
    hasReviewerOptions,
    ownerActionLabel: canClearCurrentOwner ? "Clear owner" : "Assign owner",
    ownerHelperText: getOwnerHelperText({
      canClearCurrentOwner,
      hasCurrentOwner,
      hasReviewerOptions,
      isLoadingReviewers,
      selectedReviewer,
    }),
    selectedReviewerId,
  };
}

function buildDecisionViewModel({
  actionsDisabled,
  canEscalateReview,
  canResolveReview,
  escalateIsPending,
  item,
  pendingAction,
  pendingConfirmation,
  resolveIsPending,
  savedEscalationItemId,
  savedResolutionItemId,
}: {
  actionsDisabled: boolean;
  canEscalateReview: boolean;
  canResolveReview: boolean;
  escalateIsPending: boolean;
  item: ReviewQueueItem;
  pendingAction: PendingAction;
  pendingConfirmation: PendingSingleConfirmation | null;
  resolveIsPending: boolean;
  savedEscalationItemId: string | null;
  savedResolutionItemId: string | null;
}) {
  const resolutionSaved = savedResolutionItemId === item.id;
  const escalationSaved = savedEscalationItemId === item.id;
  const canPerformResolve =
    canResolveReview &&
    !resolutionSaved &&
    !actionsDisabled &&
    !resolveIsPending &&
    pendingAction === null;
  const canPerformEscalate =
    canEscalateReview &&
    !item.is_escalated &&
    !escalationSaved &&
    !actionsDisabled &&
    !escalateIsPending &&
    pendingAction === null;

  return {
    canEscalate: canPerformEscalate && pendingConfirmation === null,
    canPerformEscalate,
    canPerformResolve,
    canResolve: canPerformResolve && pendingConfirmation === null,
    decisionRequiresConfirmation: needsSingleDecisionConfirmation(item),
    escalationSaved,
    resolutionSaved,
  };
}

function hasPendingQueueAction({
  assignIsPending,
  escalateIsPending,
  pendingAction,
  pendingConfirmation,
  resolveIsPending,
}: {
  assignIsPending: boolean;
  escalateIsPending: boolean;
  pendingAction: PendingAction;
  pendingConfirmation: PendingSingleConfirmation | null;
  resolveIsPending: boolean;
}): boolean {
  return (
    pendingAction !== null ||
    pendingConfirmation !== null ||
    assignIsPending ||
    resolveIsPending ||
    escalateIsPending
  );
}

type OwnerViewModel = ReturnType<typeof buildOwnerViewModel>;
type DecisionViewModel = ReturnType<typeof buildDecisionViewModel>;
type ReviewQueueFlag = ReturnType<typeof getItemFlags>[number];

function ReviewQueueItemSummary({
  displayedAssignee,
  flags,
  formatRelativeTime,
  item,
  itemActionLabel,
  itemHref,
  selectionControl,
}: {
  displayedAssignee: string;
  flags: ReviewQueueFlag[];
  formatRelativeTime: (date: string) => string;
  item: ReviewQueueItem;
  itemActionLabel: string;
  itemHref: string;
  selectionControl: ReactNode;
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-start">
      <div className="min-w-0 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          {selectionControl}
          <h2 className="min-w-0 break-words text-sm font-semibold text-[var(--text-primary)]">
            {item.compound_name}
          </h2>
          <StatusBadge status={item.analysis_status} className="text-xs" />
          {item.overall_risk ? (
            <RiskBadge risk={item.overall_risk} size="sm" />
          ) : null}
          {flags.map((flag) => (
            <Badge
              key={flag.label}
              variant={flag.variant}
              className="px-2 py-0 text-xs font-semibold uppercase"
            >
              {flag.label}
            </Badge>
          ))}
        </div>
        <p className="line-clamp-2 break-words text-sm leading-6 text-[var(--text-secondary)]">
          {item.comment_body}
        </p>
        <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--text-tertiary)]">
          <span className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-2 py-1 font-medium text-[var(--text-secondary)]">
            {displayedAssignee}
          </span>
          <span>
            {item.comment_count} comment
            {item.comment_count === 1 ? "" : "s"}
          </span>
          <span>•</span>
          <span>{formatRelativeTime(item.last_activity_at)}</span>
        </div>
      </div>
      <Button
        asChild
        variant="outline"
        size="sm"
        className="min-h-11 w-full gap-2 sm:w-auto"
      >
        <Link href={itemHref}>
          {itemActionLabel}
          <ArrowRight className="h-4 w-4" />
        </Link>
      </Button>
    </div>
  );
}

function OwnerHandoffSection({
  isLoadingReviewers,
  item,
  onAssignOwner,
  onReviewerSelection,
  owner,
  pendingAction,
  reviewerError,
  reviewerOptions,
}: {
  isLoadingReviewers: boolean;
  item: ReviewQueueItem;
  onAssignOwner: () => void;
  onReviewerSelection: (reviewerId: string) => void;
  owner: OwnerViewModel;
  pendingAction: PendingAction;
  reviewerError: Error | null;
  reviewerOptions: CommentReviewer[];
}) {
  return (
    <section aria-label={`Owner handoff for ${item.compound_name}`}>
      <div className="min-w-0 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Users className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
          <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
            Owner handoff
          </span>
          <span className="min-w-0 break-words rounded-md border border-[var(--border-subtle)] bg-[var(--surface-card)] px-2 py-1 text-xs font-medium text-[var(--text-primary)]">
            Current owner: {owner.displayedAssignee}
          </span>
        </div>
        <div className="grid gap-2 sm:flex sm:flex-wrap sm:items-center">
          <select
            aria-label={`Assign owner for ${item.compound_name}`}
            value={owner.selectedReviewerId}
            onChange={(event) => onReviewerSelection(event.target.value)}
            disabled={!owner.canUseOwnerControl}
            className={cn(
              "h-11 w-full rounded-md border px-2 text-sm outline-none transition-colors sm:min-w-[12rem] sm:w-auto sm:text-xs",
              owner.canUseOwnerControl
                ? "border-[var(--border-emphasis)] bg-[var(--surface-card)] text-[var(--text-secondary)] focus:border-brand-primary/40 focus:ring-1 focus:ring-brand-primary/30"
                : "cursor-not-allowed border-[var(--border-subtle)] bg-[var(--surface-muted)] text-[var(--text-disabled)]",
            )}
          >
            {owner.currentOwnerMissingFromOptions ? (
              <option value={owner.currentReviewerId}>
                {owner.displayedAssignee}
              </option>
            ) : null}
            <option value="">
              {isLoadingReviewers
                ? "Loading reviewers..."
                : owner.hasReviewerOptions || owner.hasCurrentOwner
                  ? "Unassigned"
                  : "Reviewer list unavailable"}
            </option>
            {reviewerOptions.map((reviewer) => (
              <option key={reviewer.id} value={reviewer.id}>
                {reviewer.label}
              </option>
            ))}
          </select>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onAssignOwner}
            disabled={!owner.canAssign}
            className="min-h-11 w-full gap-2 sm:w-auto"
          >
            {pendingAction === "assign" ? (
              <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" />
            ) : (
              <Users className="h-4 w-4" />
            )}
            {owner.ownerActionLabel}
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--text-tertiary)]">
          <span>{owner.ownerHelperText}</span>
          {reviewerError instanceof Error ? (
            <>
              <span>•</span>
              <span className="break-words">{REVIEWER_LIST_ERROR_COPY}</span>
            </>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function ThreadDecisionSection({
  canResolveReview,
  decision,
  item,
  onEscalate,
  onResolve,
  pendingAction,
}: {
  canResolveReview: boolean;
  decision: DecisionViewModel;
  item: ReviewQueueItem;
  onEscalate: () => void;
  onResolve: () => void;
  pendingAction: PendingAction;
}) {
  return (
    <section
      aria-label={`Thread decision for ${item.compound_name}`}
      className="grid gap-2 sm:flex sm:flex-wrap sm:items-center sm:justify-end"
    >
      <span className="hidden text-xs font-semibold uppercase text-[var(--text-tertiary)] xl:block">
        Thread decision
      </span>
      {canResolveReview ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onResolve}
          disabled={!decision.canResolve}
          className="min-h-11 w-full gap-2 sm:w-auto"
        >
          {pendingAction === "resolve" ? (
            <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" />
          ) : (
            <CheckCircle2 className="h-4 w-4" />
          )}
          {decision.resolutionSaved ? "Resolution saved" : "Resolve thread"}
        </Button>
      ) : (
        <span className="inline-flex min-h-11 w-full items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-3 text-xs font-medium text-[var(--text-tertiary)] sm:w-auto">
          Counsel resolves
        </span>
      )}
      <Button
        type="button"
        variant={
          item.is_escalated || decision.escalationSaved
            ? "secondary"
            : "outline"
        }
        size="sm"
        onClick={onEscalate}
        disabled={!decision.canEscalate}
        className="min-h-11 w-full gap-2 sm:w-auto"
      >
        {pendingAction === "escalate" ? (
          <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" />
        ) : (
          <AlertTriangle className="h-4 w-4" />
        )}
        {item.is_escalated || decision.escalationSaved
          ? "Escalated"
          : "Escalate"}
      </Button>
    </section>
  );
}

function SingleDecisionConfirmation({
  item,
  onCancel,
  onConfirm,
  pendingConfirmation,
}: {
  item: ReviewQueueItem;
  onCancel: () => void;
  onConfirm: () => void;
  pendingConfirmation: PendingSingleConfirmation | null;
}) {
  if (!pendingConfirmation) return null;

  return (
    <div
      role="alert"
      className="rounded-lg border border-warning/25 bg-warning/10 p-3 xl:col-span-2"
      data-testid="single-review-action-confirmation"
    >
      <div className="flex items-start gap-2">
        <AlertTriangle
          className="mt-0.5 h-4 w-4 shrink-0 text-warning"
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {getSingleConfirmationTitle(pendingConfirmation)}
          </p>
          <p className="mt-1 text-xs font-semibold uppercase tracking-[0.12em] text-warning">
            {getSingleConfirmationRiskSummary(item)}
          </p>
          <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
            {getSingleConfirmationConsequence(pendingConfirmation)}
          </p>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row">
            <Button
              type="button"
              size="sm"
              className="min-h-11 w-full sm:w-auto"
              onClick={onConfirm}
            >
              {getSingleConfirmationButtonLabel(pendingConfirmation)}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="min-h-11 w-full sm:w-auto"
              onClick={onCancel}
            >
              Cancel
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function QueueActionFeedback({
  actionError,
  onRetryRefresh,
  refreshWarning,
}: {
  actionError: string | null;
  onRetryRefresh: () => void;
  refreshWarning: string | null;
}) {
  return (
    <>
      {refreshWarning ? (
        <div
          role="status"
          className="flex flex-col gap-2 rounded-lg border border-warning/20 bg-warning/10 px-3 py-2 sm:flex-row sm:items-center sm:justify-between xl:col-span-2"
        >
          <p className="text-xs leading-5 text-[var(--text-secondary)]">
            {refreshWarning}
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="min-h-11 w-full sm:w-auto"
            onClick={onRetryRefresh}
          >
            Retry refresh
          </Button>
        </div>
      ) : null}
      {actionError ? (
        <p className="text-xs text-error xl:col-span-2" role="alert">
          {actionError}
        </p>
      ) : null}
    </>
  );
}

function ReviewQueueItemView({
  actionError,
  canResolveReview,
  decision,
  flags,
  formatRelativeTime,
  isLoadingReviewers,
  item,
  itemActionLabel,
  itemHref,
  onAssignOwner,
  onCancelConfirmation,
  onConfirmDecision,
  onEscalate,
  onResolve,
  onRetryRefresh,
  onReviewerSelection,
  owner,
  pendingAction,
  pendingConfirmation,
  refreshWarning,
  reviewerError,
  reviewerOptions,
  selectionControl,
}: {
  actionError: string | null;
  canResolveReview: boolean;
  decision: DecisionViewModel;
  flags: ReviewQueueFlag[];
  formatRelativeTime: (date: string) => string;
  isLoadingReviewers: boolean;
  item: ReviewQueueItem;
  itemActionLabel: string;
  itemHref: string;
  onAssignOwner: () => void;
  onCancelConfirmation: () => void;
  onConfirmDecision: () => void;
  onEscalate: () => void;
  onResolve: () => void;
  onRetryRefresh: () => void;
  onReviewerSelection: (reviewerId: string) => void;
  owner: OwnerViewModel;
  pendingAction: PendingAction;
  pendingConfirmation: PendingSingleConfirmation | null;
  refreshWarning: string | null;
  reviewerError: Error | null;
  reviewerOptions: CommentReviewer[];
  selectionControl: ReactNode;
}) {
  return (
    <article className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-card)] shadow-[var(--shadow-xs)]">
      <div
        className={cn("h-1", getPriorityRailClass(item))}
        data-testid="review-queue-priority-rail"
      />
      <div className="p-4">
        <ReviewQueueItemSummary
          displayedAssignee={owner.displayedAssignee}
          flags={flags}
          formatRelativeTime={formatRelativeTime}
          item={item}
          itemActionLabel={itemActionLabel}
          itemHref={itemHref}
          selectionControl={selectionControl}
        />
        <div className="mt-4 grid gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)] p-3 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-end">
          <OwnerHandoffSection
            isLoadingReviewers={isLoadingReviewers}
            item={item}
            onAssignOwner={onAssignOwner}
            onReviewerSelection={onReviewerSelection}
            owner={owner}
            pendingAction={pendingAction}
            reviewerError={reviewerError}
            reviewerOptions={reviewerOptions}
          />
          <ThreadDecisionSection
            canResolveReview={canResolveReview}
            decision={decision}
            item={item}
            onEscalate={onEscalate}
            onResolve={onResolve}
            pendingAction={pendingAction}
          />
          <SingleDecisionConfirmation
            item={item}
            onCancel={onCancelConfirmation}
            onConfirm={onConfirmDecision}
            pendingConfirmation={pendingConfirmation}
          />
          <QueueActionFeedback
            actionError={actionError}
            onRetryRefresh={onRetryRefresh}
            refreshWarning={refreshWarning}
          />
        </div>
      </div>
    </article>
  );
}

export function ReviewQueueItemCard({
  item,
  token,
  onQueueRefresh,
  selectionControl,
  actionsDisabled = false,
  actionPendingSourceId,
  onActionPendingChange,
}: ReviewQueueItemCardProps) {
  const formatRelativeTime = useHydrationSafeRelativeTime(relativeTime);
  const {
    data: reviewerOptions = [],
    error: reviewerError,
    isLoading: isLoadingReviewers,
  } = useCommentReviewers(item.analysis_id, token);
  const assignComment = useAssignComment(token);
  const toggleCommentResolution = useToggleCommentResolution(token);
  const escalateComment = useEscalateComment(token);
  const principal = usePrincipalCapabilities(token);
  const canAssignReview = principal.data?.can_assign_review === true;
  const canResolveReview = principal.data?.can_resolve_review === true;
  const canEscalateReview = principal.data?.can_escalate_review === true;
  const [reviewerSelection, setReviewerSelection] =
    useState<ReviewerSelection | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [refreshWarning, setRefreshWarning] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  const [pendingConfirmation, setPendingConfirmation] =
    useState<PendingSingleConfirmation | null>(null);
  const [savedOwner, setSavedOwner] = useState<SavedOwner | null>(null);
  const [savedResolutionItemId, setSavedResolutionItemId] = useState<
    string | null
  >(null);
  const [savedEscalationItemId, setSavedEscalationItemId] = useState<
    string | null
  >(null);

  const actionIsPending = hasPendingQueueAction({
    assignIsPending: assignComment.isPending,
    escalateIsPending: escalateComment.isPending,
    pendingAction,
    pendingConfirmation,
    resolveIsPending: toggleCommentResolution.isPending,
  });
  const pendingSourceId = actionPendingSourceId ?? item.id;

  useEffect(() => {
    onActionPendingChange?.(pendingSourceId, actionIsPending);

    return () => {
      onActionPendingChange?.(pendingSourceId, false);
    };
  }, [actionIsPending, onActionPendingChange, pendingSourceId]);

  const owner = buildOwnerViewModel({
    actionsDisabled,
    assignIsPending: assignComment.isPending,
    canAssignReview,
    isLoadingReviewers,
    item,
    pendingAction,
    pendingConfirmation,
    reviewerOptions,
    reviewerSelection,
    savedOwner,
  });
  const decision = buildDecisionViewModel({
    actionsDisabled,
    canEscalateReview,
    canResolveReview,
    escalateIsPending: escalateComment.isPending,
    item,
    pendingAction,
    pendingConfirmation,
    resolveIsPending: toggleCommentResolution.isPending,
    savedEscalationItemId,
    savedResolutionItemId,
  });
  const flags = getItemFlags(item);
  const currentUserRole = principal.data?.role;
  const riskRatingsRestricted = principal.data?.risk_ratings_restricted;
  const itemHref = buildReviewQueueItemHref(
    item,
    currentUserRole,
    riskRatingsRestricted,
  );
  const itemActionLabel = getReviewQueueItemActionLabel(
    item,
    currentUserRole,
    riskRatingsRestricted,
  );
  const handleAssignOwner = async () => {
    if (!owner.canAssign) return;

    setActionError(null);
    setRefreshWarning(null);
    setPendingAction("assign");
    try {
      await assignComment.mutateAsync({
        analysis_id: item.analysis_id,
        comment_id: item.id,
        assigned_to: owner.selectedReviewerId || null,
      });
      setSavedOwner({
        itemId: item.id,
        reviewerId: owner.selectedReviewerId || null,
      });
      try {
        await onQueueRefresh();
      } catch {
        console.error(
          "[ReviewQueueItemCard] Failed to refresh after owner assignment",
        );
        setRefreshWarning(
          "Owner update was saved, but the queue refresh failed. Retry refresh to confirm the current queue placement.",
        );
      }
    } catch {
      console.error("[ReviewQueueItemCard] Failed to assign owner");
      setActionError(buildReviewQueueActionError("assign"));
    } finally {
      setPendingAction(null);
    }
  };

  const performResolveThread = async () => {
    if (!decision.canPerformResolve) return;

    setActionError(null);
    setRefreshWarning(null);
    setPendingAction("resolve");
    try {
      await toggleCommentResolution.mutateAsync({
        analysis_id: item.analysis_id,
        comment_id: item.id,
        resolved: true,
      });
      setSavedResolutionItemId(item.id);
      try {
        await onQueueRefresh();
      } catch {
        console.error(
          "[ReviewQueueItemCard] Failed to refresh after thread resolution",
        );
        setRefreshWarning(
          "Thread resolution was saved, but the queue refresh failed. Retry refresh to confirm the current queue placement.",
        );
      }
    } catch {
      console.error("[ReviewQueueItemCard] Failed to resolve thread");
      setActionError(buildReviewQueueActionError("resolve"));
    } finally {
      setPendingAction(null);
    }
  };

  const handleResolveThread = async () => {
    if (!decision.canPerformResolve) return;
    if (decision.decisionRequiresConfirmation) {
      setActionError(null);
      setRefreshWarning(null);
      setPendingConfirmation("resolve");
      return;
    }
    await performResolveThread();
  };

  const performEscalateThread = async () => {
    if (!decision.canPerformEscalate) return;

    setActionError(null);
    setRefreshWarning(null);
    setPendingAction("escalate");
    try {
      await escalateComment.mutateAsync({
        analysis_id: item.analysis_id,
        comment_id: item.id,
        promote_to_under_review: true,
      });
      setSavedEscalationItemId(item.id);
      try {
        await onQueueRefresh();
      } catch {
        console.error(
          "[ReviewQueueItemCard] Failed to refresh after escalation",
        );
        setRefreshWarning(
          "Escalation was saved, but the queue refresh failed. Retry refresh to confirm the current queue placement.",
        );
      }
    } catch {
      console.error("[ReviewQueueItemCard] Failed to escalate thread");
      setActionError(buildReviewQueueActionError("escalate"));
    } finally {
      setPendingAction(null);
    }
  };

  const handleEscalateThread = async () => {
    if (!decision.canPerformEscalate) return;
    if (decision.decisionRequiresConfirmation) {
      setActionError(null);
      setRefreshWarning(null);
      setPendingConfirmation("escalate");
      return;
    }
    await performEscalateThread();
  };

  const handleConfirmDecision = async () => {
    const action = pendingConfirmation;
    if (!action) return;

    setPendingConfirmation(null);
    if (action === "resolve") {
      await performResolveThread();
      return;
    }
    await performEscalateThread();
  };

  const selectReviewer = (reviewerId: string) => {
    setReviewerSelection({ itemId: item.id, reviewerId });
  };
  const cancelConfirmation = () => {
    setPendingConfirmation(null);
  };
  const retryQueueRefresh = () => {
    void onQueueRefresh()
      .then(() => {
        setRefreshWarning(null);
      })
      .catch(() => {
        console.error("[ReviewQueueItemCard] Failed to retry queue refresh");
      });
  };

  return (
    <ReviewQueueItemView
      actionError={actionError}
      canResolveReview={canResolveReview}
      decision={decision}
      flags={flags}
      formatRelativeTime={formatRelativeTime}
      isLoadingReviewers={isLoadingReviewers}
      item={item}
      itemActionLabel={itemActionLabel}
      itemHref={itemHref}
      onAssignOwner={() => void handleAssignOwner()}
      onCancelConfirmation={cancelConfirmation}
      onConfirmDecision={() => void handleConfirmDecision()}
      onEscalate={() => void handleEscalateThread()}
      onResolve={() => void handleResolveThread()}
      onRetryRefresh={retryQueueRefresh}
      onReviewerSelection={selectReviewer}
      owner={owner}
      pendingAction={pendingAction}
      pendingConfirmation={pendingConfirmation}
      refreshWarning={refreshWarning}
      reviewerError={reviewerError}
      reviewerOptions={reviewerOptions}
      selectionControl={selectionControl}
    />
  );
}
