"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import {
  AlertTriangle,
  CheckCircle,
  ChevronDown,
  History,
  Reply,
  UserRoundCheck,
} from "lucide-react";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useCommentAssignmentHistory } from "@/hooks/use-comments";
import { COMMENT_ASSIGNMENT_ACTIVITY_ERROR_MESSAGE } from "@/hooks/report-interaction-copy";
import { cn } from "@/lib/utils";
import { CommentPanelAvatar } from "@/components/report/comment-panel-avatar";
import { formatRelativeTime } from "@/components/report/comment-panel-utils";
import type {
  CommentAssignmentHistoryEvent,
  CommentPanelComment,
  CommentPanelReviewer,
} from "@/components/report/comment-panel-types";

interface CommentPanelThreadProps {
  comment: CommentPanelComment;
  replies: CommentPanelComment[];
  onReply: (commentId: string) => void;

  isActionPending?: boolean;
  onAssignOwner?: (commentId: string, reviewerId: string) => void;
  onEscalate?: (commentId: string) => void;
  onResolve?: (commentId: string, nextResolved: boolean) => void;
  reviewers?: CommentPanelReviewer[];

  threadStatus?: "open" | "resolved" | string;
  threadResolvedAt?: string | null;
  threadResolvedBy?: string | null;
  threadAssignedReviewerId?: string | null;
  threadAssignedReviewerName?: string | null;
  threadAssignedReviewerEmail?: string | null;
  threadAssignedAt?: string | null;
  threadAssignmentHistoryCount?: number;
  threadLastAssignedAt?: string | null;
  threadEscalatedAt?: string | null;
  threadEscalatedBy?: string | null;
  threadEscalatedByName?: string | null;
  threadEscalatedByEmail?: string | null;
  threadEscalationEventCount?: number;
  threadLastEscalatedAt?: string | null;
  threadIsEscalated?: boolean;
  threadEscalatedToReview?: boolean;
  threadReviewHandoffCommentId?: string | null;
  threadAgeLabel?: string | null;
  threadOverdueLabel?: string | null;
  threadIsOverdue?: boolean;
  onAssignReviewer?: (commentId: string, reviewerId: string) => void;
  onEscalateComment?: (commentId: string) => void;
  onToggleResolved?: (commentId: string, nextResolved: boolean) => void;
  isResolutionPending?: boolean;
  pendingCommentId?: string | null;
  resolutionError?: { commentId: string; message: string } | null;
  isAssignmentPending?: boolean;
  pendingAssignmentCommentId?: string | null;
  assignmentError?: { commentId: string; message: string } | null;
  isEscalationPending?: boolean;
  pendingEscalateCommentId?: string | null;
  recoveryNotice?: ReactNode;
  reviewerOptions?: CommentPanelReviewer[];
}

function formatTargetType(value: string): string {
  return value.replace(/_/g, " ");
}

function formatResolvedBy(value: string | null | undefined): string {
  return formatActorLabel(value, "Workspace reviewer");
}

function formatActorLabel(
  value: string | null | undefined,
  fallback = "Workspace reviewer",
): string {
  const normalized = value?.trim();
  if (!normalized) return fallback;
  if (normalized.includes(" ") || normalized.includes("@")) return normalized;
  if (normalized.toLowerCase().includes("attorney")) return "Counsel reviewer";
  return fallback;
}

function formatTargetLabel(comment: CommentPanelComment): string {
  const targetType = formatTargetType(comment.target_type ?? "");
  if (targetType === "analysis" || targetType === "review handoff") {
    return "Current analysis";
  }
  if (targetType === "patent") return `Patent ${comment.target_id}`;
  if (targetType === "claim") return `Claim ${comment.target_id}`;
  return "Linked review record";
}

function TargetMetadata({ comment }: { comment: CommentPanelComment }) {
  if (!comment.target_type || !comment.target_id) return null;

  return (
    <div className="mt-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-2 py-1.5 text-xs text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
      <span className="font-medium text-[var(--text-secondary)]">
        {formatTargetType(comment.target_type).replace(/^\w/, (char) =>
          char.toUpperCase(),
        )}{" "}
        target
      </span>
      <span className="mx-1.5 text-[var(--text-disabled)]">·</span>
      <span className="font-medium text-[var(--text-primary)]">
        {formatTargetLabel(comment)}
      </span>
    </div>
  );
}

function AssignmentActivityEvent({
  event,
}: {
  event: CommentAssignmentHistoryEvent;
}) {
  const assignedTo = formatActorLabel(
    event.assigned_to_name ?? event.assigned_to_email ?? event.assigned_to,
  );
  const assignedBy = formatActorLabel(
    event.assigned_by_name ?? event.assigned_by_email ?? event.assigned_by,
  );
  const verb = event.event_type === "unassigned" ? "Unassigned" : "Assigned";
  const actor = assignedBy ? ` by ${assignedBy}` : "";

  return (
    <li className="text-xs text-[var(--text-secondary)]">
      {assignedTo ? `${verb} to ${assignedTo}${actor}` : `${verb}${actor}`}{" "}
      <span className="text-[var(--text-disabled)]">
        {formatRelativeTime(event.created_at)}
      </span>
    </li>
  );
}

interface CommentBodyProps {
  comment: CommentPanelComment;
  isActionPending: boolean;
  isResolutionPending: boolean;
  isAssignmentPending: boolean;
  isEscalationPending: boolean;
  pendingCommentId: string | null;
  pendingAssignmentCommentId: string | null;
  pendingEscalateCommentId: string | null;
  onAssignOwner: (commentId: string, reviewerId: string) => void;
  onEscalate: (commentId: string) => void;
  onReply?: (commentId: string) => void;
  onResolve: (commentId: string, nextResolved: boolean) => void;
  reviewers: CommentPanelReviewer[];
  resolutionError?: { commentId: string; message: string } | null;
  assignmentError?: { commentId: string; message: string } | null;
  showReplyAction?: boolean;
}

function buildCommentBodyViewModel(
  comment: CommentPanelComment,
  reviewers: CommentPanelReviewer[],
  pending: {
    isAssignmentPending: boolean;
    isEscalationPending: boolean;
    isResolutionPending: boolean;
    pendingAssignmentCommentId: string | null;
    pendingCommentId: string | null;
    pendingEscalateCommentId: string | null;
  },
) {
  const assignedReviewer = reviewers.find(
    (reviewer) => reviewer.id === comment.assigned_to,
  );
  const assignedLabel = formatActorLabel(
    comment.assigned_reviewer_name ??
      assignedReviewer?.label ??
      comment.assigned_to,
    "",
  );
  const escalatedBy = formatActorLabel(
    comment.escalated_by_name ?? comment.escalated_by,
  );
  const isEscalated =
    comment.escalation_status === "escalated" ||
    (comment.escalation_event_count ?? 0) > 0;

  return {
    assignedLabel,
    assignmentPendingForComment:
      pending.isAssignmentPending &&
      pending.pendingAssignmentCommentId === comment.id,
    escalatedBy,
    escalationPendingForComment:
      pending.isEscalationPending &&
      pending.pendingEscalateCommentId === comment.id,
    isEscalated,
    pendingResolvedActionLabel: comment.resolved
      ? "Unresolving..."
      : "Resolving...",
    resolutionPendingForComment:
      pending.isResolutionPending && pending.pendingCommentId === comment.id,
    resolvedActionLabel: comment.resolved ? "Unresolve" : "Resolve",
  };
}

type CommentBodyViewModel = ReturnType<typeof buildCommentBodyViewModel>;

function CommentBodyHeader({ comment }: { comment: CommentPanelComment }) {
  return (
    <div className="mb-1 flex flex-wrap items-center gap-2">
      <span className="text-xs font-medium text-[var(--text-secondary)]">
        {formatActorLabel(comment.user_id)}
      </span>
      <span className="text-xs text-[var(--text-disabled)]">
        {formatRelativeTime(comment.created_at)}
      </span>
      {comment.resolved ? (
        <span className="flex items-center gap-1 text-xs text-success">
          <CheckCircle className="h-3 w-3" />
          Resolved
        </span>
      ) : null}
    </div>
  );
}

function CommentActions({
  comment,
  isActionPending,
  onAssignOwner,
  onEscalate,
  onResolve,
  reviewers,
  viewModel,
}: {
  comment: CommentPanelComment;
  isActionPending: boolean;
  onAssignOwner: (commentId: string, reviewerId: string) => void;
  onEscalate: (commentId: string) => void;
  onResolve: (commentId: string, nextResolved: boolean) => void;
  reviewers: CommentPanelReviewer[];
  viewModel: CommentBodyViewModel;
}) {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-[var(--border-subtle)] pt-3">
      <label className="flex items-center gap-2 text-xs text-[var(--text-tertiary)]">
        <UserRoundCheck className="h-3.5 w-3.5" />
        <span className="sr-only">Assign owner</span>
        <select
          aria-label="Assign owner"
          className="min-h-11 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-2 text-xs text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
          disabled={isActionPending || viewModel.assignmentPendingForComment}
          onChange={(event) => {
            if (event.target.value === (comment.assigned_to ?? "")) return;
            onAssignOwner(comment.id, event.target.value);
          }}
          value={comment.assigned_to ?? ""}
        >
          <option value="">Unassigned</option>
          {reviewers.map((reviewer) => (
            <option key={reviewer.id} value={reviewer.id}>
              {reviewer.label}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        onClick={() => onResolve(comment.id, !comment.resolved)}
        disabled={isActionPending || viewModel.resolutionPendingForComment}
        className="inline-flex min-h-11 items-center gap-1 rounded-md border border-[var(--border-subtle)] px-2 text-xs text-[var(--text-secondary)] transition-colors hover:border-success/50 hover:text-success focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-success/60 disabled:opacity-50"
      >
        <CheckCircle className="h-3.5 w-3.5" />
        {viewModel.resolutionPendingForComment
          ? viewModel.pendingResolvedActionLabel
          : viewModel.resolvedActionLabel}
      </button>
      <button
        type="button"
        onClick={() => onEscalate(comment.id)}
        disabled={
          isActionPending ||
          viewModel.isEscalated ||
          viewModel.escalationPendingForComment
        }
        className="inline-flex min-h-11 items-center gap-1 rounded-md border border-[var(--border-subtle)] px-2 text-xs text-[var(--text-secondary)] transition-colors hover:border-warning/50 hover:text-warning focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-warning/60 disabled:opacity-50"
      >
        <AlertTriangle className="h-3.5 w-3.5" />
        {viewModel.isEscalated
          ? "Escalated"
          : viewModel.escalationPendingForComment
            ? "Escalating..."
            : "Escalate"}
      </button>
      {viewModel.assignedLabel ? (
        <span className="text-xs text-[var(--text-tertiary)]">
          Assigned to {viewModel.assignedLabel}
        </span>
      ) : null}
      {viewModel.isEscalated ? (
        <span className="text-xs text-warning">
          Escalated to legal review
          {viewModel.escalatedBy ? ` by ${viewModel.escalatedBy}` : ""}
        </span>
      ) : null}
    </div>
  );
}

function CommentActionErrors({
  assignmentError,
  commentId,
  resolutionError,
}: {
  assignmentError?: { commentId: string; message: string } | null;
  commentId: string;
  resolutionError?: { commentId: string; message: string } | null;
}) {
  return (
    <>
      {resolutionError?.commentId === commentId ? (
        <p className="mt-2 text-xs text-error" role="alert">
          {resolutionError.message}
        </p>
      ) : null}
      {assignmentError?.commentId === commentId ? (
        <p className="mt-2 text-xs text-error" role="alert">
          {assignmentError.message}
        </p>
      ) : null}
    </>
  );
}

function CommentReplyAction({
  commentId,
  isActionPending,
  onReply,
  showReplyAction,
}: {
  commentId: string;
  isActionPending: boolean;
  onReply?: (commentId: string) => void;
  showReplyAction: boolean;
}) {
  if (!showReplyAction || !onReply) return null;

  return (
    <button
      type="button"
      onClick={() => onReply(commentId)}
      disabled={isActionPending}
      className={cn(
        "mt-2 inline-flex min-h-11 items-center gap-1 rounded-md px-2 text-xs text-[var(--text-disabled)] transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70",
        "opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100",
        "disabled:pointer-events-none disabled:opacity-50",
      )}
    >
      <Reply className="h-3 w-3" />
      Reply
    </button>
  );
}

function CommentBody({
  comment,
  isActionPending,
  isResolutionPending,
  isAssignmentPending,
  isEscalationPending,
  pendingCommentId,
  pendingAssignmentCommentId,
  pendingEscalateCommentId,
  onAssignOwner,
  onEscalate,
  onReply,
  onResolve,
  reviewers,
  resolutionError,
  assignmentError,
  showReplyAction = true,
}: CommentBodyProps) {
  const viewModel = buildCommentBodyViewModel(comment, reviewers, {
    isAssignmentPending,
    isEscalationPending,
    isResolutionPending,
    pendingAssignmentCommentId,
    pendingCommentId,
    pendingEscalateCommentId,
  });

  return (
    <div className="min-w-0 flex-1">
      <CommentBodyHeader comment={comment} />
      <p className="whitespace-pre-wrap break-words text-sm text-[var(--text-primary)] [overflow-wrap:anywhere]">
        {comment.body}
      </p>
      <TargetMetadata comment={comment} />

      <CommentActions
        comment={comment}
        isActionPending={isActionPending}
        onAssignOwner={onAssignOwner}
        onEscalate={onEscalate}
        onResolve={onResolve}
        reviewers={reviewers}
        viewModel={viewModel}
      />
      <CommentActionErrors
        assignmentError={assignmentError}
        commentId={comment.id}
        resolutionError={resolutionError}
      />
      <CommentReplyAction
        commentId={comment.id}
        isActionPending={isActionPending}
        onReply={onReply}
        showReplyAction={showReplyAction}
      />
    </div>
  );
}

function noopAssignOwner(_commentId: string, _reviewerId: string) {}
function noopEscalate(_commentId: string) {}
function noopResolve(_commentId: string, _nextResolved: boolean) {}

function buildThreadActions(props: CommentPanelThreadProps) {
  return {
    assignOwner:
      props.onAssignOwner ?? props.onAssignReviewer ?? noopAssignOwner,
    escalate: props.onEscalate ?? props.onEscalateComment ?? noopEscalate,
    resolve: props.onResolve ?? props.onToggleResolved ?? noopResolve,
    reviewers: props.reviewers ?? props.reviewerOptions ?? [],
  };
}

function buildThreadResolutionMetadata(props: CommentPanelThreadProps) {
  const status =
    props.threadStatus ?? (props.comment.resolved ? "resolved" : "open");
  return {
    isResolved: status === "resolved",
    resolvedAt: props.threadResolvedAt ?? props.comment.resolved_at ?? null,
    resolvedBy: props.threadResolvedBy ?? props.comment.resolved_by ?? null,
  };
}

function buildThreadAssignmentMetadata(props: CommentPanelThreadProps) {
  return {
    assignedLabel: formatActorLabel(
      props.threadAssignedReviewerName ??
        props.threadAssignedReviewerEmail ??
        props.threadAssignedReviewerId ??
        props.comment.assigned_reviewer_name ??
        props.comment.assigned_reviewer_email ??
        props.comment.assigned_to,
      "",
    ),
    assignmentCount:
      props.threadAssignmentHistoryCount ??
      props.comment.assignment_event_count ??
      0,
    lastAssignedAt:
      props.threadLastAssignedAt ?? props.comment.last_assignment_at ?? null,
  };
}

function buildThreadEscalationMetadata(props: CommentPanelThreadProps) {
  const escalatedAt =
    props.threadEscalatedAt ?? props.comment.escalated_at ?? null;
  const escalationCount =
    props.threadEscalationEventCount ??
    props.comment.escalation_event_count ??
    0;
  return {
    escalatedBy: formatActorLabel(
      props.threadEscalatedByName ??
        props.threadEscalatedByEmail ??
        props.threadEscalatedBy,
    ),
    escalatedToReview:
      props.threadEscalatedToReview ?? props.comment.escalated_to_review,
    escalationCount,
    isEscalated:
      props.threadIsEscalated ??
      (props.comment.escalation_status === "escalated" || escalationCount > 0),
    lastEscalatedAt:
      props.threadLastEscalatedAt ??
      props.comment.last_escalation_at ??
      escalatedAt,
    reviewHandoffCommentId:
      props.threadReviewHandoffCommentId ??
      props.comment.review_handoff_comment_id ??
      null,
  };
}

type ThreadResolutionMetadata = ReturnType<
  typeof buildThreadResolutionMetadata
>;
type ThreadAssignmentMetadata = ReturnType<
  typeof buildThreadAssignmentMetadata
>;
type ThreadEscalationMetadata = ReturnType<
  typeof buildThreadEscalationMetadata
>;

function ThreadStatusBar({
  assignment,
  escalation,
  resolution,
  threadAgeLabel,
  threadAssignedAt,
  threadIsOverdue,
  threadOverdueLabel,
}: {
  assignment: ThreadAssignmentMetadata;
  escalation: ThreadEscalationMetadata;
  resolution: ThreadResolutionMetadata;
  threadAgeLabel: string | null | undefined;
  threadAssignedAt: string | null | undefined;
  threadIsOverdue: boolean | undefined;
  threadOverdueLabel: string | null | undefined;
}) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 border-b border-[var(--border-subtle)] pb-3">
      <span
        className={cn(
          "inline-flex items-center gap-1.5 text-xs font-semibold",
          resolution.isResolved
            ? "text-success"
            : "text-[var(--text-secondary)]",
        )}
      >
        <span
          aria-hidden="true"
          className={cn(
            "h-1.5 w-1.5 rounded-full",
            resolution.isResolved ? "bg-success" : "bg-warning",
          )}
        />
        {resolution.isResolved ? "Thread resolved" : "Thread open"}
      </span>
      {threadAgeLabel ? (
        <span className="text-xs text-[var(--text-tertiary)]">
          {threadAgeLabel}
        </span>
      ) : null}
      {threadOverdueLabel ? (
        <span
          className={cn(
            "text-xs font-medium",
            threadIsOverdue ? "text-error" : "text-[var(--text-tertiary)]",
          )}
        >
          {threadOverdueLabel}
        </span>
      ) : null}
      {resolution.resolvedAt ? (
        <span className="text-xs text-success">
          Resolved by {formatResolvedBy(resolution.resolvedBy)} ·{" "}
          {formatRelativeTime(resolution.resolvedAt)}
        </span>
      ) : null}
      {assignment.assignmentCount > 0 ? (
        <span className="text-xs text-[var(--text-tertiary)]">
          {assignment.assignmentCount} assignments
          {assignment.lastAssignedAt
            ? ` · Last assigned ${formatRelativeTime(assignment.lastAssignedAt)}`
            : ""}
        </span>
      ) : null}
      {assignment.assignedLabel ? (
        <span className="text-xs text-[var(--text-tertiary)]">
          Owner {assignment.assignedLabel}
          {threadAssignedAt ? ` · ${formatRelativeTime(threadAssignedAt)}` : ""}
        </span>
      ) : null}
      {escalation.isEscalated ? (
        <>
          <span className="text-xs font-medium text-warning">Legal review</span>
          <span className="text-xs text-warning">
            {escalation.escalationCount} escalations
            {escalation.lastEscalatedAt
              ? ` · Last escalated ${formatRelativeTime(escalation.lastEscalatedAt)}`
              : ""}
          </span>
          {escalation.escalatedBy ? (
            <span className="text-xs text-[var(--text-tertiary)]">
              Escalated by {escalation.escalatedBy}
            </span>
          ) : null}
          {escalation.escalatedToReview && escalation.reviewHandoffCommentId ? (
            <span className="text-xs text-[var(--text-tertiary)]">
              Review handoff comment {escalation.reviewHandoffCommentId}
            </span>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

type SharedCommentBodyProps = Omit<
  CommentBodyProps,
  "comment" | "onReply" | "showReplyAction"
>;

function ThreadRootComment({
  bodyProps,
  comment,
  onReply,
}: {
  bodyProps: SharedCommentBodyProps;
  comment: CommentPanelComment;
  onReply: (commentId: string) => void;
}) {
  return (
    <div className="flex items-start gap-3">
      <CommentPanelAvatar userId={comment.user_id} />
      <CommentBody {...bodyProps} comment={comment} onReply={onReply} />
    </div>
  );
}

type AssignmentHistoryQuery = ReturnType<typeof useCommentAssignmentHistory>;

function AssignmentActivity({
  activityOpen,
  assignmentCount,
  assignmentHistory,
  onToggle,
}: {
  activityOpen: boolean;
  assignmentCount: number;
  assignmentHistory: AssignmentHistoryQuery;
  onToggle: () => void;
}) {
  if (assignmentCount <= 0) return null;

  return (
    <div className="mt-3 border-t border-[var(--border-subtle)] pt-3">
      <button
        type="button"
        onClick={onToggle}
        className="inline-flex min-h-11 items-center gap-1 rounded-md px-2 text-xs text-[var(--text-secondary)] transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
      >
        <History className="h-3.5 w-3.5" />
        {activityOpen ? "Hide activity" : "View activity"}
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 transition-transform",
            activityOpen && "rotate-180",
          )}
        />
      </button>
      {activityOpen ? (
        <div className="mt-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-2">
          <p className="mb-1 text-xs font-medium text-[var(--text-secondary)]">
            Assignment activity
          </p>
          {assignmentHistory.isLoading ? (
            <p className="text-xs text-[var(--text-tertiary)]">
              Loading assignment activity...
            </p>
          ) : null}
          {assignmentHistory.error ? (
            <p className="text-xs text-error" role="alert">
              {COMMENT_ASSIGNMENT_ACTIVITY_ERROR_MESSAGE}
            </p>
          ) : null}
          {assignmentHistory.data?.events?.length ? (
            <ul className="space-y-1">
              {assignmentHistory.data.events.map((event) => (
                <AssignmentActivityEvent key={event.id} event={event} />
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function ThreadReplies({
  bodyProps,
  replies,
}: {
  bodyProps: SharedCommentBodyProps;
  replies: CommentPanelComment[];
}) {
  if (replies.length === 0) return null;

  return (
    <div className="ml-8 space-y-2 border-l-2 border-[var(--border-subtle)] pl-4">
      {replies.map((reply) => (
        <div
          key={reply.id}
          className="rounded-lg bg-[var(--surface-subtle)] p-3"
        >
          <div className="flex items-start gap-3">
            <CommentPanelAvatar userId={reply.user_id} />
            <CommentBody
              {...bodyProps}
              comment={reply}
              showReplyAction={false}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function CommentThreadView({
  activityOpen,
  assignment,
  assignmentHistory,
  bodyProps,
  comment,
  escalation,
  onReply,
  onToggleActivity,
  recoveryNotice,
  replies,
  resolution,
  threadAgeLabel,
  threadAssignedAt,
  threadIsOverdue,
  threadOverdueLabel,
}: {
  activityOpen: boolean;
  assignment: ThreadAssignmentMetadata;
  assignmentHistory: AssignmentHistoryQuery;
  bodyProps: SharedCommentBodyProps;
  comment: CommentPanelComment;
  escalation: ThreadEscalationMetadata;
  onReply: (commentId: string) => void;
  onToggleActivity: () => void;
  recoveryNotice: ReactNode;
  replies: CommentPanelComment[];
  resolution: ThreadResolutionMetadata;
  threadAgeLabel: string | null | undefined;
  threadAssignedAt: string | null | undefined;
  threadIsOverdue: boolean | undefined;
  threadOverdueLabel: string | null | undefined;
}) {
  return (
    <div className="space-y-2">
      <div
        className={cn(
          "group rounded-lg border border-l-2 bg-[var(--surface-subtle)] p-3",
          resolution.isResolved
            ? "border-[var(--border-subtle)] border-l-success/60"
            : "border-[var(--border-subtle)] border-l-warning/60",
        )}
      >
        <ThreadStatusBar
          assignment={assignment}
          escalation={escalation}
          resolution={resolution}
          threadAgeLabel={threadAgeLabel}
          threadAssignedAt={threadAssignedAt}
          threadIsOverdue={threadIsOverdue}
          threadOverdueLabel={threadOverdueLabel}
        />
        {recoveryNotice ? <div className="mb-3">{recoveryNotice}</div> : null}
        <ThreadRootComment
          bodyProps={bodyProps}
          comment={comment}
          onReply={onReply}
        />
        <AssignmentActivity
          activityOpen={activityOpen}
          assignmentCount={assignment.assignmentCount}
          assignmentHistory={assignmentHistory}
          onToggle={onToggleActivity}
        />
      </div>
      <ThreadReplies bodyProps={bodyProps} replies={replies} />
    </div>
  );
}

export function CommentPanelThread(props: CommentPanelThreadProps) {
  const {
    assignmentError = null,
    comment,
    isActionPending = false,
    isAssignmentPending = false,
    isEscalationPending = false,
    isResolutionPending = false,
    onReply,
    pendingAssignmentCommentId = null,
    pendingCommentId = null,
    pendingEscalateCommentId = null,
    recoveryNotice,
    replies,
    resolutionError = null,
    threadAgeLabel,
    threadAssignedAt,
    threadIsOverdue,
    threadOverdueLabel,
  } = props;
  const token = useAuthToken();
  const [activityOpen, setActivityOpen] = useState(false);
  const assignmentHistory = useCommentAssignmentHistory(
    comment.id,
    token,
    activityOpen,
  );
  const actions = buildThreadActions(props);
  const assignment = buildThreadAssignmentMetadata(props);
  const escalation = buildThreadEscalationMetadata(props);
  const resolution = buildThreadResolutionMetadata(props);
  const bodyProps: SharedCommentBodyProps = {
    assignmentError,
    isActionPending,
    isAssignmentPending,
    isEscalationPending,
    isResolutionPending,
    onAssignOwner: actions.assignOwner,
    onEscalate: actions.escalate,
    onResolve: actions.resolve,
    pendingAssignmentCommentId,
    pendingCommentId,
    pendingEscalateCommentId,
    resolutionError,
    reviewers: actions.reviewers,
  };
  const toggleActivity = () => {
    setActivityOpen((current) => !current);
  };

  return (
    <CommentThreadView
      activityOpen={activityOpen}
      assignment={assignment}
      assignmentHistory={assignmentHistory}
      bodyProps={bodyProps}
      comment={comment}
      escalation={escalation}
      onReply={onReply}
      onToggleActivity={toggleActivity}
      recoveryNotice={recoveryNotice}
      replies={replies}
      resolution={resolution}
      threadAgeLabel={threadAgeLabel}
      threadAssignedAt={threadAssignedAt}
      threadIsOverdue={threadIsOverdue}
      threadOverdueLabel={threadOverdueLabel}
    />
  );
}
