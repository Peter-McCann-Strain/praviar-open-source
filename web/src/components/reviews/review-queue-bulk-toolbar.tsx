"use client";

import { AlertTriangle, CheckCircle2, Loader2, Users, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  useAssignComment,
  useCommentReviewers,
  useEscalateComment,
  useToggleCommentResolution,
  type CommentReviewer,
} from "@/hooks/use-comments";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";
import {
  buildReviewQueuePartialActionError,
  type ReviewQueueAction,
} from "@/components/reviews/review-queue-errors";
import type { ReviewQueueItem } from "@/hooks/use-review-queue";

const CLEAR_OWNER_VALUE = "__clear_owner__";

export interface ReviewQueueBulkActionSuccess {
  action: "assign" | "resolve" | "escalate";
  count: number;
  skippedCount?: number;
  scopeLabel: string | null;
  sharedAnalysisId: string | null;
  assignedToLabel?: string | null;
}

interface ReviewQueueBulkToolbarProps {
  token: string | null;
  selectedItems: ReviewQueueItem[];
  onClearSelection?: () => void;
  mode?: "full" | "compact";
  onActionComplete?: (payload: ReviewQueueBulkActionSuccess) => void;
  actionsDisabled?: boolean;
  actionPendingSourceId?: string;
  onActionPendingChange?: (sourceId: string, pending: boolean) => void;
}

type PendingBulkConfirmation =
  | {
      action: "assign";
      targetItems: ReviewQueueItem[];
      reviewerId: string | null;
      reviewerLabel: string;
      skippedCount?: number;
    }
  | {
      action: "resolve" | "escalate";
      targetItems: ReviewQueueItem[];
      skippedCount?: number;
    };

type PendingBulkAction = "assign" | "resolve" | "escalate" | null;

interface BulkReviewerSelection {
  scopeKey: string;
  reviewerId: string;
}

function summarizeSelection(items: ReviewQueueItem[]): string {
  if (items.length === 0) return "No items selected";
  if (items.length === 1) return items[0]?.compound_name ?? "1 selected item";
  if (items.length === 2)
    return items.map((item) => item.compound_name).join(", ");

  const [first, second] = items;
  return `${first?.compound_name}, ${second?.compound_name} +${items.length - 2} more`;
}

function needsBulkConfirmation(items: ReviewQueueItem[]) {
  return (
    items.length > 1 ||
    items.some(
      (item) =>
        item.is_overdue || item.is_escalated || item.overall_risk === "high",
    )
  );
}

function getConfirmationTitle(action: PendingBulkConfirmation["action"]) {
  if (action === "assign") return "Confirm owner assignment";
  if (action === "escalate") return "Confirm legal escalation";
  return "Confirm thread resolution";
}

function getConfirmationButtonLabel(action: PendingBulkConfirmation["action"]) {
  if (action === "assign") return "Confirm assignment";
  if (action === "escalate") return "Confirm escalation";
  return "Confirm resolution";
}

function getConfirmationConsequence(confirmation: PendingBulkConfirmation) {
  if (confirmation.action === "assign") {
    if (confirmation.reviewerId === null) {
      const skippedCopy = confirmation.skippedCount
        ? ` ${confirmation.skippedCount} already-unassigned thread${confirmation.skippedCount === 1 ? "" : "s"} will be skipped.`
        : "";
      return `Owner will be cleared and these threads will move into the unassigned review queue after refresh.${skippedCopy}`;
    }
    return `Owner will be set to ${confirmation.reviewerLabel} for the selected review threads.`;
  }

  if (confirmation.action === "escalate") {
    const skippedCopy = confirmation.skippedCount
      ? ` ${confirmation.skippedCount} already-escalated thread${confirmation.skippedCount === 1 ? "" : "s"} will be skipped.`
      : "";
    return `Threads will be promoted for counsel attention and remain visible until the refreshed queue lands.${skippedCopy}`;
  }

  return "Resolved threads leave open review queues once the refreshed queue lands.";
}

function getConfirmationRiskSummary(items: ReviewQueueItem[]) {
  const highRiskCount = items.filter(
    (item) => item.overall_risk === "high",
  ).length;
  const overdueCount = items.filter((item) => item.is_overdue).length;
  const escalatedCount = items.filter((item) => item.is_escalated).length;
  const summaries = [
    highRiskCount > 0
      ? `${highRiskCount} high-risk thread${highRiskCount === 1 ? "" : "s"}`
      : null,
    overdueCount > 0
      ? `${overdueCount} overdue thread${overdueCount === 1 ? "" : "s"}`
      : null,
    escalatedCount > 0
      ? `${escalatedCount} escalated thread${escalatedCount === 1 ? "" : "s"}`
      : null,
  ].filter(Boolean);

  return summaries.length > 0 ? summaries.join(" · ") : "No urgent flags";
}

function buildScopeNote({
  isCompact,
  hasSharedScope,
  canBulkAssign,
  reviewerOptionsReady,
  unresolvedCount,
}: {
  isCompact: boolean;
  hasSharedScope: boolean;
  canBulkAssign: boolean;
  reviewerOptionsReady: boolean;
  unresolvedCount: number;
}) {
  if (canBulkAssign) {
    if (unresolvedCount > 1) {
      return isCompact
        ? "Owner assignment is ready across this shared scope."
        : "Bulk owner assignment is available because the selection shares one review scope.";
    }

    return isCompact
      ? "Owner assignment is ready for this selected thread."
      : "Owner assignment is available for this selected thread.";
  }

  if (!hasSharedScope) {
    return isCompact
      ? "Owner assignment only works within one analysis scope."
      : "Bulk owner assignment is limited to selections from a single analysis scope.";
  }

  if (!reviewerOptionsReady) {
    return isCompact
      ? "Reviewer list unavailable for owner assignment."
      : "Owner assignment is unavailable until the reviewer list loads for this selection.";
  }

  return isCompact
    ? "Owner assignment is unavailable for this selection."
    : "Bulk owner assignment is unavailable for this selection.";
}

function getSharedAnalysisId(items: ReviewQueueItem[]): string {
  if (items.length === 0) return "";
  const analysisId = items[0]?.analysis_id ?? "";
  return items.every((item) => item.analysis_id === analysisId)
    ? analysisId
    : "";
}

function buildOwnerSelectionState({
  canAssignReview,
  isLoadingReviewers,
  reviewerOptions,
  reviewerSelection,
  selectedItems,
  sharedAnalysisId,
}: {
  canAssignReview: boolean;
  isLoadingReviewers: boolean;
  reviewerOptions: CommentReviewer[];
  reviewerSelection: BulkReviewerSelection | null;
  selectedItems: ReviewQueueItem[];
  sharedAnalysisId: string;
}) {
  const hasSharedScope = Boolean(sharedAnalysisId);
  const reviewerOptionsReady =
    reviewerOptions.length > 0 && !isLoadingReviewers;
  const canBulkAssign =
    canAssignReview && hasSharedScope && reviewerOptionsReady;
  const ownedSelectedItems = selectedItems.filter(
    (item) => !item.is_unassigned,
  );
  const canClearOwner = canAssignReview && ownedSelectedItems.length > 0;
  const selectionScopeKey = `${sharedAnalysisId}:${selectedItems.map((item) => item.id).join(",")}`;
  const selectedReviewerId =
    reviewerSelection?.scopeKey === selectionScopeKey
      ? reviewerSelection.reviewerId
      : "";
  const ownerClearSelected = selectedReviewerId === CLEAR_OWNER_VALUE;

  return {
    canAssignSelection:
      selectedReviewerId.length > 0 &&
      (ownerClearSelected ? canClearOwner : canBulkAssign),
    canBulkAssign,
    canClearOwner,
    canUseOwnerControl: canBulkAssign || canClearOwner,
    hasSharedScope,
    ownedSelectedItems,
    ownerClearSelected,
    reviewerOptionsReady,
    selectedReviewerId,
    selectionScopeKey,
  };
}

function buildBulkActionState({
  actionsDisabled,
  assignPending,
  canEscalateReview,
  escalatePending,
  pendingAction,
  resolvePending,
  selectedItems,
}: {
  actionsDisabled: boolean;
  assignPending: boolean;
  canEscalateReview: boolean;
  escalatePending: boolean;
  pendingAction: PendingBulkAction;
  resolvePending: boolean;
  selectedItems: ReviewQueueItem[];
}) {
  const actionIsPending =
    pendingAction !== null ||
    assignPending ||
    resolvePending ||
    escalatePending;
  const escalationTargets = selectedItems.filter((item) => !item.is_escalated);

  return {
    actionIsPending,
    canAct:
      selectedItems.length > 0 && pendingAction === null && !actionsDisabled,
    canEscalateSelection: canEscalateReview && escalationTargets.length > 0,
    controlsLocked: actionsDisabled || actionIsPending,
    escalationTargets,
  };
}

function buildBulkToolbarCopy({
  canBulkAssign,
  canResolveReview,
  hasSharedScope,
  isCompact,
  ownerClearSelected,
  reviewerOptionsReady,
  unresolvedCount,
}: {
  canBulkAssign: boolean;
  canResolveReview: boolean;
  hasSharedScope: boolean;
  isCompact: boolean;
  ownerClearSelected: boolean;
  reviewerOptionsReady: boolean;
  unresolvedCount: number;
}) {
  return {
    assignLabel: ownerClearSelected
      ? isCompact
        ? "Clear owner"
        : "Clear owners"
      : isCompact
        ? "Assign"
        : "Assign selected",
    clearLabel: isCompact ? "Clear" : "Clear selection",
    description: canResolveReview
      ? isCompact
        ? "Resolve, escalate, or reassign selected threads."
        : "Resolve selected threads in one pass or escalate them to legal review. Selection clears automatically after a successful bulk action."
      : isCompact
        ? "Escalate or reassign selected threads. Counsel records resolution."
        : "Escalate or reassign selected threads. An attorney or administrator records final resolution.",
    escalateLabel: isCompact ? "Escalate" : "Escalate selected",
    resolveLabel: isCompact ? "Resolve" : "Resolve selected",
    scopeNote: buildScopeNote({
      isCompact,
      hasSharedScope,
      canBulkAssign,
      reviewerOptionsReady,
      unresolvedCount,
    }),
  };
}

type OwnerSelectionState = ReturnType<typeof buildOwnerSelectionState>;
type BulkActionState = ReturnType<typeof buildBulkActionState>;
type BulkToolbarCopy = ReturnType<typeof buildBulkToolbarCopy>;

function buildActionScope(targetItems: ReviewQueueItem[]) {
  const sharedAnalysisId = getSharedAnalysisId(targetItems);
  return {
    scopeLabel: sharedAnalysisId
      ? (targetItems[0]?.compound_name ?? null)
      : null,
    sharedAnalysisId: sharedAnalysisId || null,
  };
}

function getFulfilledItems(
  targetItems: ReviewQueueItem[],
  results: Array<PromiseSettledResult<unknown>>,
) {
  return targetItems.filter(
    (_, index) => results[index]?.status === "fulfilled",
  );
}

function BulkToolbarSummary({
  actionError,
  copy,
  isCompact,
  selectionSummary,
  unresolvedCount,
}: {
  actionError: string | null;
  copy: BulkToolbarCopy;
  isCompact: boolean;
  selectionSummary: string;
  unresolvedCount: number;
}) {
  return (
    <div className={`min-w-0 ${isCompact ? "space-y-1.5" : "space-y-2"}`}>
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <Badge
          variant="default"
          className="px-2 py-0 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--brand-primary-dim)]"
        >
          {unresolvedCount} selected
        </Badge>
        <span
          className={
            isCompact
              ? "min-w-0 break-words text-xs font-medium text-[var(--text-primary)]"
              : "min-w-0 break-words text-sm font-medium text-[var(--text-primary)]"
          }
        >
          {selectionSummary}
        </span>
      </div>
      <p
        className={
          isCompact
            ? "max-w-2xl text-xs text-[var(--text-secondary)]"
            : "max-w-2xl text-sm text-[var(--text-secondary)]"
        }
      >
        {copy.description}
      </p>
      <p className="max-w-2xl text-xs text-[var(--text-tertiary)]">
        {copy.scopeNote}
      </p>
      {actionError ? (
        <p className="text-xs text-error" role="alert">
          {actionError}
        </p>
      ) : null}
    </div>
  );
}

function BulkOwnerSelect({
  actionState,
  isCompact,
  onReviewerChange,
  ownerState,
  reviewerOptions,
  sharedAnalysisId,
}: {
  actionState: BulkActionState;
  isCompact: boolean;
  onReviewerChange: (reviewerId: string) => void;
  ownerState: OwnerSelectionState;
  reviewerOptions: CommentReviewer[];
  sharedAnalysisId: string;
}) {
  return (
    <select
      aria-label="Bulk assign owner"
      value={ownerState.selectedReviewerId}
      onChange={(event) => onReviewerChange(event.target.value)}
      disabled={!ownerState.canUseOwnerControl || actionState.controlsLocked}
      className={`h-11 w-full rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-card)] px-3 text-sm text-[var(--text-primary)] outline-none transition-colors focus:border-brand-primary/40 focus:ring-2 focus:ring-brand-primary/30 disabled:cursor-not-allowed disabled:bg-[var(--surface-muted)] disabled:text-[var(--text-disabled)] sm:w-auto ${
        isCompact ? "sm:min-w-[10.5rem]" : "sm:min-w-[12rem]"
      }`}
    >
      <option value="">
        {ownerState.canBulkAssign
          ? "Choose reviewer..."
          : ownerState.canClearOwner
            ? "Owner action..."
            : sharedAnalysisId
              ? "Reviewer list unavailable"
              : "Mixed analysis selection"}
      </option>
      {ownerState.canClearOwner ? (
        <option value={CLEAR_OWNER_VALUE}>Clear owner</option>
      ) : null}
      {reviewerOptions.map((reviewer) => (
        <option key={reviewer.id} value={reviewer.id}>
          {reviewer.label}
        </option>
      ))}
    </select>
  );
}

function BulkActionButtons({
  actionState,
  canResolveReview,
  copy,
  isCompact,
  onAssign,
  onClear,
  onEscalate,
  onResolve,
  ownerState,
  pendingAction,
}: {
  actionState: BulkActionState;
  canResolveReview: boolean;
  copy: BulkToolbarCopy;
  isCompact: boolean;
  onAssign: () => void;
  onClear: () => void;
  onEscalate: () => void;
  onResolve: () => void;
  ownerState: OwnerSelectionState;
  pendingAction: PendingBulkAction;
}) {
  const buttonClass = `min-h-11 w-full gap-2 sm:w-auto ${isCompact ? "px-3" : ""}`;
  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={onAssign}
        disabled={!ownerState.canAssignSelection || actionState.controlsLocked}
        className={buttonClass}
      >
        {pendingAction === "assign" ? (
          <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" />
        ) : (
          <Users className="h-4 w-4" />
        )}
        {copy.assignLabel}
      </Button>
      {canResolveReview ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onResolve}
          disabled={!actionState.canAct}
          className={buttonClass}
        >
          {pendingAction === "resolve" ? (
            <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" />
          ) : (
            <CheckCircle2 className="h-4 w-4" />
          )}
          {copy.resolveLabel}
        </Button>
      ) : null}
      <Button
        type="button"
        variant="secondary"
        size="sm"
        onClick={onEscalate}
        disabled={!actionState.canAct || !actionState.canEscalateSelection}
        className={buttonClass}
      >
        {pendingAction === "escalate" ? (
          <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" />
        ) : (
          <AlertTriangle className="h-4 w-4" />
        )}
        {copy.escalateLabel}
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={onClear}
        disabled={actionState.controlsLocked}
        className={`min-h-11 w-full gap-2 text-[var(--text-secondary)] sm:w-auto ${isCompact ? "px-3" : ""}`}
      >
        <X className="h-4 w-4" />
        {copy.clearLabel}
      </Button>
    </>
  );
}

function BulkToolbarActionRail({
  actionState,
  canResolveReview,
  copy,
  isCompact,
  onAssign,
  onClear,
  onEscalate,
  onResolve,
  onReviewerChange,
  ownerState,
  pendingAction,
  reviewerOptions,
  sharedAnalysisId,
}: {
  actionState: BulkActionState;
  canResolveReview: boolean;
  copy: BulkToolbarCopy;
  isCompact: boolean;
  onAssign: () => void;
  onClear: () => void;
  onEscalate: () => void;
  onResolve: () => void;
  onReviewerChange: (reviewerId: string) => void;
  ownerState: OwnerSelectionState;
  pendingAction: PendingBulkAction;
  reviewerOptions: CommentReviewer[];
  sharedAnalysisId: string;
}) {
  return (
    <div
      className={
        isCompact
          ? "grid w-full grid-cols-1 gap-2 sm:flex sm:w-auto sm:flex-wrap sm:items-center sm:gap-1.5"
          : "grid w-full grid-cols-1 gap-2 sm:flex sm:w-auto sm:flex-wrap sm:items-center"
      }
    >
      <BulkOwnerSelect
        actionState={actionState}
        isCompact={isCompact}
        onReviewerChange={onReviewerChange}
        ownerState={ownerState}
        reviewerOptions={reviewerOptions}
        sharedAnalysisId={sharedAnalysisId}
      />
      <BulkActionButtons
        actionState={actionState}
        canResolveReview={canResolveReview}
        copy={copy}
        isCompact={isCompact}
        onAssign={onAssign}
        onClear={onClear}
        onEscalate={onEscalate}
        onResolve={onResolve}
        ownerState={ownerState}
        pendingAction={pendingAction}
      />
    </div>
  );
}

function ConfirmationThreadItem({ item }: { item: ReviewQueueItem }) {
  return (
    <li className="px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p
            className="text-sm font-medium leading-5 text-[var(--text-primary)] [overflow-wrap:anywhere]"
            title={item.compound_name}
          >
            {item.compound_name}
          </p>
          <p className="mt-1 text-xs text-[var(--text-tertiary)]">
            {item.analysis_id} · {item.comment_count} comment
            {item.comment_count === 1 ? "" : "s"} ·{" "}
            {item.is_unassigned
              ? "Unassigned"
              : (item.assigned_to_name ?? item.assigned_to_email ?? "Assigned")}
          </p>
        </div>
        {item.is_overdue || item.is_escalated ? (
          <Badge
            variant={item.is_escalated ? "destructive" : "warning"}
            className="shrink-0 px-2 py-0 text-xs font-semibold uppercase tracking-[0.14em]"
          >
            {item.is_escalated ? "Escalated" : "Past SLA"}
          </Badge>
        ) : null}
      </div>
    </li>
  );
}

function ConfirmationThreadList({ items }: { items: ReviewQueueItem[] }) {
  const remainingCount = items.length - 5;
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)]">
      <div className="border-b border-[var(--border-subtle)] px-4 py-2">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
          Selected threads
        </p>
      </div>
      <ul className="max-h-48 divide-y divide-[var(--border-subtle)] overflow-y-auto">
        {items.slice(0, 5).map((item) => (
          <ConfirmationThreadItem key={item.id} item={item} />
        ))}
      </ul>
      {remainingCount > 0 ? (
        <p className="border-t border-[var(--border-subtle)] px-4 py-2 text-xs text-[var(--text-tertiary)]">
          +{remainingCount} more selected thread
          {remainingCount === 1 ? "" : "s"}
        </p>
      ) : null}
    </div>
  );
}

function BulkConfirmationDialog({
  confirmation,
  controlsLocked,
  onCancel,
  onConfirm,
  onOpenChange,
  pendingAction,
}: {
  confirmation: PendingBulkConfirmation | null;
  controlsLocked: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  onOpenChange: (open: boolean) => void;
  pendingAction: PendingBulkAction;
}) {
  return (
    <Dialog open={confirmation !== null} onOpenChange={onOpenChange}>
      {confirmation ? (
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>
              {getConfirmationTitle(confirmation.action)}
            </DialogTitle>
            <DialogDescription>
              Review the selected legal-review state change before it is
              applied.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="rounded-lg border border-warning/25 bg-warning/10 px-4 py-3">
              <div className="flex items-start gap-2">
                <AlertTriangle
                  className="mt-0.5 h-4 w-4 shrink-0 text-warning"
                  aria-hidden="true"
                />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-[var(--text-primary)]">
                    {confirmation.targetItems.length} thread
                    {confirmation.targetItems.length === 1 ? "" : "s"} affected
                  </p>
                  <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                    {getConfirmationConsequence(confirmation)}
                  </p>
                  <p className="mt-1 text-xs font-medium text-warning">
                    {getConfirmationRiskSummary(confirmation.targetItems)}
                  </p>
                </div>
              </div>
            </div>
            <ConfirmationThreadList items={confirmation.targetItems} />
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              type="button"
              variant="outline"
              className="min-h-11"
              onClick={onCancel}
              disabled={controlsLocked}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant={
                confirmation.action === "escalate" ? "secondary" : "default"
              }
              className="min-h-11"
              onClick={onConfirm}
              loading={pendingAction === confirmation.action}
              disabled={controlsLocked}
            >
              {getConfirmationButtonLabel(confirmation.action)}
            </Button>
          </DialogFooter>
        </DialogContent>
      ) : null}
    </Dialog>
  );
}

function BulkToolbarView({
  actionError,
  actionState,
  canResolveReview,
  confirmation,
  copy,
  isCompact,
  onAssign,
  onCancelConfirmation,
  onClear,
  onConfirm,
  onConfirmationOpenChange,
  onEscalate,
  onResolve,
  onReviewerChange,
  ownerState,
  pendingAction,
  reviewerOptions,
  selectionSummary,
  sharedAnalysisId,
  unresolvedCount,
}: {
  actionError: string | null;
  actionState: BulkActionState;
  canResolveReview: boolean;
  confirmation: PendingBulkConfirmation | null;
  copy: BulkToolbarCopy;
  isCompact: boolean;
  onAssign: () => void;
  onCancelConfirmation: () => void;
  onClear: () => void;
  onConfirm: () => void;
  onConfirmationOpenChange: (open: boolean) => void;
  onEscalate: () => void;
  onResolve: () => void;
  onReviewerChange: (reviewerId: string) => void;
  ownerState: OwnerSelectionState;
  pendingAction: PendingBulkAction;
  reviewerOptions: CommentReviewer[];
  selectionSummary: string;
  sharedAnalysisId: string;
  unresolvedCount: number;
}) {
  return (
    <section
      className="rounded-lg border border-brand-primary/25 bg-brand-primary/[0.06] shadow-[var(--shadow-xs)]"
      data-testid="review-queue-bulk-toolbar"
      aria-label="Selected review thread actions"
    >
      <div
        className={
          isCompact
            ? "flex flex-col gap-3 p-3 lg:flex-row lg:items-center lg:justify-between"
            : "flex flex-col gap-4 p-4 lg:flex-row lg:items-center lg:justify-between"
        }
      >
        <BulkToolbarSummary
          actionError={actionError}
          copy={copy}
          isCompact={isCompact}
          selectionSummary={selectionSummary}
          unresolvedCount={unresolvedCount}
        />
        <BulkToolbarActionRail
          actionState={actionState}
          canResolveReview={canResolveReview}
          copy={copy}
          isCompact={isCompact}
          onAssign={onAssign}
          onClear={onClear}
          onEscalate={onEscalate}
          onResolve={onResolve}
          onReviewerChange={onReviewerChange}
          ownerState={ownerState}
          pendingAction={pendingAction}
          reviewerOptions={reviewerOptions}
          sharedAnalysisId={sharedAnalysisId}
        />
      </div>
      <BulkConfirmationDialog
        confirmation={confirmation}
        controlsLocked={actionState.controlsLocked}
        onCancel={onCancelConfirmation}
        onConfirm={onConfirm}
        onOpenChange={onConfirmationOpenChange}
        pendingAction={pendingAction}
      />
    </section>
  );
}

export function ReviewQueueBulkToolbar({
  token,
  selectedItems,
  onClearSelection,
  mode = "full",
  onActionComplete,
  actionsDisabled = false,
  actionPendingSourceId = "bulk",
  onActionPendingChange,
}: ReviewQueueBulkToolbarProps) {
  const isCompact = mode === "compact";
  const sharedAnalysisId = getSharedAnalysisId(selectedItems);
  const { data: reviewerOptions = [], isLoading: isLoadingReviewers } =
    useCommentReviewers(sharedAnalysisId, token);
  const assignComment = useAssignComment(token);
  const toggleCommentResolution = useToggleCommentResolution(token);
  const escalateComment = useEscalateComment(token);
  const principal = usePrincipalCapabilities(token);
  const canAssignReview = principal.data?.can_assign_review === true;
  const canResolveReview = principal.data?.can_resolve_review === true;
  const canEscalateReview = principal.data?.can_escalate_review === true;
  const [reviewerSelection, setReviewerSelection] =
    useState<BulkReviewerSelection | null>(null);
  const [pendingAction, setPendingAction] = useState<PendingBulkAction>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingConfirmation, setPendingConfirmation] =
    useState<PendingBulkConfirmation | null>(null);

  const selectionSummary = useMemo(
    () => summarizeSelection(selectedItems),
    [selectedItems],
  );
  const unresolvedCount = selectedItems.length;
  const ownerState = buildOwnerSelectionState({
    canAssignReview,
    isLoadingReviewers,
    reviewerOptions,
    reviewerSelection,
    selectedItems,
    sharedAnalysisId,
  });
  const actionState = buildBulkActionState({
    actionsDisabled,
    assignPending: assignComment.isPending,
    canEscalateReview,
    escalatePending: escalateComment.isPending,
    pendingAction,
    resolvePending: toggleCommentResolution.isPending,
    selectedItems,
  });
  const { actionIsPending, canAct, controlsLocked, escalationTargets } =
    actionState;
  const { canAssignSelection, ownedSelectedItems, selectedReviewerId } =
    ownerState;

  useEffect(() => {
    onActionPendingChange?.(actionPendingSourceId, actionIsPending);

    return () => {
      onActionPendingChange?.(actionPendingSourceId, false);
    };
  }, [actionIsPending, actionPendingSourceId, onActionPendingChange]);

  if (unresolvedCount === 0) {
    return null;
  }

  const copy = buildBulkToolbarCopy({
    canBulkAssign: ownerState.canBulkAssign,
    canResolveReview,
    hasSharedScope: ownerState.hasSharedScope,
    isCompact,
    ownerClearSelected: ownerState.ownerClearSelected,
    reviewerOptionsReady: ownerState.reviewerOptionsReady,
    unresolvedCount,
  });

  const clearSelectionAfterSuccess = () => {
    onClearSelection?.();
  };
  const clearSelectionFromUi = () => {
    if (controlsLocked) return;
    onClearSelection?.();
  };

  const notifyActionComplete = (payload: ReviewQueueBulkActionSuccess) => {
    onActionComplete?.(payload);
  };

  const runBulkMutation = async (
    action: Extract<ReviewQueueAction, "resolve" | "escalate">,
    targetItems = selectedItems,
  ) => {
    if (!canAct || targetItems.length === 0) return;

    setActionError(null);
    setPendingAction(action);
    try {
      // Use allSettled so a single failure does not abort remaining items and
      // we can report a partial success count rather than claiming all-or-nothing.
      const results = await Promise.allSettled(
        targetItems.map((item) =>
          action === "resolve"
            ? toggleCommentResolution.mutateAsync({
                analysis_id: item.analysis_id,
                comment_id: item.id,
                resolved: true,
              })
            : escalateComment.mutateAsync({
                analysis_id: item.analysis_id,
                comment_id: item.id,
                promote_to_under_review: true,
              }),
        ),
      );
      const succeeded = results.filter((r) => r.status === "fulfilled").length;
      const failed = results.filter((r) => r.status === "rejected").length;
      const succeededItems = getFulfilledItems(targetItems, results);

      if (succeeded > 0) {
        const actionScope = buildActionScope(succeededItems);
        notifyActionComplete({
          action,
          count: succeeded,
          scopeLabel: actionScope.scopeLabel,
          sharedAnalysisId: actionScope.sharedAnalysisId,
        });
        if (failed === 0) clearSelectionAfterSuccess();
      }
      if (failed > 0) {
        console.error(
          "[ReviewQueueBulkToolbar] Bulk action partially failed:",
          {
            action,
            failed,
            total: targetItems.length,
          },
        );
        setActionError(
          buildReviewQueuePartialActionError({
            action,
            failed,
            total: targetItems.length,
          }),
        );
      }
    } finally {
      setPendingAction(null);
    }
  };

  const runBulkAssign = async ({
    reviewerId = selectedReviewerId,
    targetItems = selectedItems,
    skippedCount = 0,
    assignedToLabel,
  }: {
    reviewerId?: string | null;
    targetItems?: ReviewQueueItem[];
    skippedCount?: number;
    assignedToLabel?: string | null;
  } = {}) => {
    const assignedTo =
      reviewerId === CLEAR_OWNER_VALUE || reviewerId === null
        ? null
        : reviewerId;
    const clearingOwner = assignedTo === null;
    if (
      !canAct ||
      targetItems.length === 0 ||
      (!clearingOwner && !assignedTo)
    ) {
      return;
    }

    setActionError(null);
    setPendingAction("assign");
    try {
      const results = await Promise.allSettled(
        targetItems.map((item) =>
          assignComment.mutateAsync({
            analysis_id: item.analysis_id,
            comment_id: item.id,
            assigned_to: assignedTo,
          }),
        ),
      );
      const succeeded = results.filter((r) => r.status === "fulfilled").length;
      const failed = results.filter((r) => r.status === "rejected").length;
      const succeededItems = getFulfilledItems(targetItems, results);

      if (succeeded > 0) {
        const assignedReviewer = reviewerOptions.find(
          (reviewer) => reviewer.id === assignedTo,
        );
        const successScope = buildActionScope(succeededItems);
        notifyActionComplete({
          action: "assign",
          count: succeeded,
          skippedCount: skippedCount > 0 ? skippedCount : undefined,
          scopeLabel: successScope.scopeLabel,
          sharedAnalysisId: successScope.sharedAnalysisId,
          assignedToLabel:
            assignedTo === null
              ? "Unassigned"
              : (assignedToLabel ?? assignedReviewer?.label ?? "reviewer"),
        });
        if (failed === 0) clearSelectionAfterSuccess();
      }
      if (failed > 0) {
        console.error(
          "[ReviewQueueBulkToolbar] Bulk assignment partially failed:",
          {
            failed,
            total: targetItems.length,
          },
        );
        setActionError(
          buildReviewQueuePartialActionError({
            action: "assign",
            failed,
            total: targetItems.length,
          }),
        );
      }
    } finally {
      setPendingAction(null);
    }
  };

  const requestBulkAssign = () => {
    if (!canAct || !canAssignSelection) return;

    const clearingOwner = selectedReviewerId === CLEAR_OWNER_VALUE;
    const assignedReviewer = reviewerOptions.find(
      (reviewer) => reviewer.id === selectedReviewerId,
    );
    const reviewerId = clearingOwner ? null : selectedReviewerId;
    const reviewerLabel = clearingOwner
      ? "Unassigned"
      : (assignedReviewer?.label ?? "the selected reviewer");
    const targetItems = clearingOwner ? ownedSelectedItems : selectedItems;
    const skippedCount = clearingOwner
      ? selectedItems.length - ownedSelectedItems.length
      : 0;

    if (needsBulkConfirmation(selectedItems)) {
      setPendingConfirmation({
        action: "assign",
        targetItems,
        reviewerId,
        reviewerLabel,
        skippedCount,
      });
      return;
    }

    void runBulkAssign({
      reviewerId,
      targetItems,
      skippedCount,
      assignedToLabel: reviewerLabel,
    });
  };

  const requestBulkMutation = (
    action: Extract<ReviewQueueAction, "resolve" | "escalate">,
    targetItems = selectedItems,
    skippedCount = 0,
  ) => {
    if (!canAct || targetItems.length === 0) return;

    if (needsBulkConfirmation(targetItems)) {
      setPendingConfirmation({ action, targetItems, skippedCount });
      return;
    }

    void runBulkMutation(action, targetItems);
  };

  const confirmPendingAction = () => {
    if (!pendingConfirmation) return;

    const confirmation = pendingConfirmation;
    setPendingConfirmation(null);

    if (confirmation.action === "assign") {
      void runBulkAssign({
        reviewerId: confirmation.reviewerId,
        targetItems: confirmation.targetItems,
        skippedCount: confirmation.skippedCount ?? 0,
        assignedToLabel: confirmation.reviewerLabel,
      });
      return;
    }

    void runBulkMutation(confirmation.action, confirmation.targetItems);
  };

  const selectReviewer = (reviewerId: string) => {
    setReviewerSelection({
      scopeKey: ownerState.selectionScopeKey,
      reviewerId,
    });
  };
  const resolveSelection = () => {
    requestBulkMutation("resolve");
  };
  const escalateSelection = () => {
    requestBulkMutation(
      "escalate",
      escalationTargets,
      selectedItems.length - escalationTargets.length,
    );
  };
  const cancelConfirmation = () => {
    setPendingConfirmation(null);
  };
  const handleConfirmationOpenChange = (open: boolean) => {
    if (!open && !controlsLocked) {
      setPendingConfirmation(null);
    }
  };

  return (
    <BulkToolbarView
      actionError={actionError}
      actionState={actionState}
      canResolveReview={canResolveReview}
      confirmation={pendingConfirmation}
      copy={copy}
      isCompact={isCompact}
      onAssign={requestBulkAssign}
      onCancelConfirmation={cancelConfirmation}
      onClear={clearSelectionFromUi}
      onConfirm={confirmPendingAction}
      onConfirmationOpenChange={handleConfirmationOpenChange}
      onEscalate={escalateSelection}
      onResolve={resolveSelection}
      onReviewerChange={selectReviewer}
      ownerState={ownerState}
      pendingAction={pendingAction}
      reviewerOptions={reviewerOptions}
      selectionSummary={selectionSummary}
      sharedAnalysisId={sharedAnalysisId}
      unresolvedCount={unresolvedCount}
    />
  );
}
