"use client";

import { AlertTriangle, CheckCircle2, Loader2, Users } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  buildReviewQueueActionError,
  REVIEWER_LIST_ERROR_COPY,
} from "@/components/reviews/review-queue-errors";
import {
  useAssignComment,
  useCommentReviewers,
  useEscalateComment,
  useToggleCommentResolution,
} from "@/hooks/use-comments";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";
import type { ReviewQueueItem } from "@/hooks/use-review-queue";

interface LegalReviewSpotlightActionsProps {
  item: ReviewQueueItem;
  token: string | null;
  onQueueRefresh: () => Promise<unknown> | Promise<void>;
  mode?: "spotlight" | "inline";
}

function formatAssignee(item: ReviewQueueItem): string {
  if (item.is_unassigned) {
    return "Unassigned";
  }

  return item.assigned_to_name ?? item.assigned_to_email ?? "Assigned";
}

function getErrorKind(error: unknown) {
  return error instanceof Error ? error.name : typeof error;
}

export function LegalReviewSpotlightActions({
  item,
  token,
  onQueueRefresh,
  mode = "spotlight",
}: LegalReviewSpotlightActionsProps) {
  const isInline = mode === "inline";
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
  const [reviewerSelection, setReviewerSelection] = useState<{
    itemId: string;
    reviewerId: string;
  } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<
    "assign" | "resolve" | "escalate" | null
  >(null);

  const currentReviewerId = item.assigned_to_id ?? "";
  const selectedReviewerId =
    reviewerSelection?.itemId === item.id
      ? reviewerSelection.reviewerId
      : currentReviewerId;

  const selectedReviewer =
    reviewerOptions.find((reviewer) => reviewer.id === selectedReviewerId) ??
    null;
  const canAssign =
    canAssignReview &&
    reviewerOptions.length > 0 &&
    !isLoadingReviewers &&
    !assignComment.isPending &&
    pendingAction === null &&
    selectedReviewerId !== currentReviewerId;
  const canResolve =
    canResolveReview &&
    !toggleCommentResolution.isPending &&
    pendingAction === null;
  const canEscalate =
    canEscalateReview &&
    !item.is_escalated &&
    !escalateComment.isPending &&
    pendingAction === null;
  const containerClassName = isInline
    ? "mt-2 rounded-lg border border-[var(--border-subtle)] bg-transparent p-2"
    : "mt-4 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-card)] p-3";
  const headerCopy = canResolveReview
    ? isInline
      ? "Reassign, resolve, or escalate this thread."
      : "Reassign, resolve, or escalate this owned thread without leaving the dashboard."
    : isInline
      ? "Reassign or escalate this thread. Counsel records resolution."
      : "Reassign or escalate this owned thread. Counsel records final resolution.";
  const rowSpacingClassName = isInline ? "mt-2 gap-2" : "mt-3 gap-3";
  const selectClassName = isInline
    ? "min-h-11 min-w-[10.5rem] max-w-full rounded-md border px-3 py-2 text-xs outline-none transition-colors"
    : "min-h-11 min-w-[12rem] max-w-full rounded-md border px-3 py-2 text-xs outline-none transition-colors";
  const ownerTextClassName = isInline ? "text-xs" : "text-xs";
  const statusTextClassName = isInline ? "text-xs" : "text-xs";
  const actionButtonLabelSize = "sm";
  const actionButtonClassName = "min-h-11 gap-2 px-3 leading-5";
  const assignButtonLabel = isInline ? "Assign" : "Assign owner";
  const resolveButtonLabel = isInline ? "Resolve" : "Resolve thread";
  const escalateButtonLabel = item.is_escalated ? "Escalated" : "Escalate";
  const assignOwnerAriaLabel = isInline
    ? `Assign owner for ${item.compound_name} from inline tray`
    : `Assign owner for ${item.compound_name} from spotlight`;

  const handleAssignOwner = async () => {
    if (!canAssign) return;

    setActionError(null);
    setPendingAction("assign");
    try {
      await assignComment.mutateAsync({
        analysis_id: item.analysis_id,
        comment_id: item.id,
        assigned_to: selectedReviewerId || null,
      });
      await onQueueRefresh();
    } catch (error) {
      console.error("[LegalReviewSpotlightActions] assign failed", {
        errorKind: getErrorKind(error),
      });
      setActionError(buildReviewQueueActionError("assign"));
    } finally {
      setPendingAction(null);
    }
  };

  const handleResolveThread = async () => {
    if (!canResolve) return;

    setActionError(null);
    setPendingAction("resolve");
    try {
      await toggleCommentResolution.mutateAsync({
        analysis_id: item.analysis_id,
        comment_id: item.id,
        resolved: true,
      });
      await onQueueRefresh();
    } catch (error) {
      console.error("[LegalReviewSpotlightActions] resolve failed", {
        errorKind: getErrorKind(error),
      });
      setActionError(buildReviewQueueActionError("resolve"));
    } finally {
      setPendingAction(null);
    }
  };

  const handleEscalateThread = async () => {
    if (!canEscalate) return;

    setActionError(null);
    setPendingAction("escalate");
    try {
      await escalateComment.mutateAsync({
        analysis_id: item.analysis_id,
        comment_id: item.id,
        promote_to_under_review: true,
      });
      await onQueueRefresh();
    } catch (error) {
      console.error("[LegalReviewSpotlightActions] escalate failed", {
        errorKind: getErrorKind(error),
      });
      setActionError(buildReviewQueueActionError("escalate"));
    } finally {
      setPendingAction(null);
    }
  };

  return (
    <div className={containerClassName}>
      <div
        className={cn(
          "flex flex-wrap items-center gap-2",
          isInline && "gap-1.5",
        )}
      >
        <span className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
          {isInline ? "Actions" : "Next Action"}
        </span>
        <span
          className={cn(
            "text-[var(--text-tertiary)]",
            isInline ? "text-xs" : "text-xs",
          )}
        >
          {headerCopy}
        </span>
      </div>

      <div
        className={cn(
          "flex flex-col xl:flex-row xl:items-end xl:justify-between",
          rowSpacingClassName,
        )}
      >
        <div className="min-w-0 flex-1 space-y-2">
          <div
            className={cn(
              "flex flex-wrap items-center gap-2",
              isInline && "gap-1.5",
            )}
          >
            <Users className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
            <span
              className={cn(
                "min-w-0 max-w-full font-medium text-[var(--text-primary)] [overflow-wrap:anywhere]",
                ownerTextClassName,
              )}
            >
              Current owner: {formatAssignee(item)}
            </span>
          </div>

          <div
            className={cn(
              "flex flex-wrap items-center gap-2",
              isInline && "gap-1.5",
            )}
          >
            <select
              aria-label={assignOwnerAriaLabel}
              value={selectedReviewerId}
              onChange={(event) =>
                setReviewerSelection({
                  itemId: item.id,
                  reviewerId: event.target.value,
                })
              }
              disabled={
                reviewerOptions.length === 0 ||
                isLoadingReviewers ||
                pendingAction !== null
              }
              className={cn(
                selectClassName,
                reviewerOptions.length > 0 && !isLoadingReviewers
                  ? "border-[var(--border-emphasis)] bg-[var(--surface-card)] text-[var(--text-secondary)] focus:border-brand-primary/40 focus:ring-1 focus:ring-brand-primary/30"
                  : "cursor-not-allowed border-[var(--border-subtle)] bg-[var(--surface-muted)] text-[var(--text-disabled)]",
              )}
            >
              <option value="">
                {isLoadingReviewers
                  ? "Loading reviewers..."
                  : reviewerOptions.length > 0
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
              size={actionButtonLabelSize}
              onClick={() => void handleAssignOwner()}
              disabled={!canAssign}
              className={actionButtonClassName}
            >
              {pendingAction === "assign" ? (
                <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" />
              ) : (
                <Users className="h-4 w-4" />
              )}
              {assignButtonLabel}
            </Button>
          </div>

          <div
            className={cn(
              "flex flex-wrap items-center gap-2 text-[var(--text-tertiary)]",
              statusTextClassName,
            )}
          >
            <span className="min-w-0 max-w-full [overflow-wrap:anywhere]">
              {selectedReviewer
                ? `Selected: ${selectedReviewer.label}`
                : "Select an owner or leave unassigned."}
            </span>
            {reviewerError instanceof Error ? (
              <>
                <span>•</span>
                <span className="min-w-0 max-w-full [overflow-wrap:anywhere]">
                  {REVIEWER_LIST_ERROR_COPY}
                </span>
              </>
            ) : null}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {canResolveReview ? (
            <Button
              type="button"
              variant="outline"
              size={actionButtonLabelSize}
              onClick={() => void handleResolveThread()}
              disabled={!canResolve}
              className={actionButtonClassName}
            >
              {pendingAction === "resolve" ? (
                <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" />
              ) : (
                <CheckCircle2 className="h-4 w-4" />
              )}
              {resolveButtonLabel}
            </Button>
          ) : (
            <span className="inline-flex min-h-11 items-center rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-3 text-xs font-medium text-[var(--text-tertiary)]">
              Counsel resolves
            </span>
          )}

          <Button
            type="button"
            variant={item.is_escalated ? "secondary" : "outline"}
            size={actionButtonLabelSize}
            onClick={() => void handleEscalateThread()}
            disabled={!canEscalate}
            className={actionButtonClassName}
          >
            {pendingAction === "escalate" ? (
              <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" />
            ) : (
              <AlertTriangle className="h-4 w-4" />
            )}
            {escalateButtonLabel}
          </Button>
        </div>
      </div>

      {actionError ? (
        <p className="mt-2 text-xs text-error" role="alert">
          {actionError}
        </p>
      ) : null}
    </div>
  );
}
