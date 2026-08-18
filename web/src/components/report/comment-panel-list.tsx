"use client";

import type { ReactNode } from "react";
import { Loader2, MessageSquare } from "lucide-react";
import { groupCommentsByParent } from "@/components/report/comment-panel-utils";
import type {
  CommentPanelComment,
  CommentPanelReviewer,
} from "@/components/report/comment-panel-types";
import { CommentPanelThread } from "@/components/report/comment-panel-thread";

interface CommentPanelListProps {
  actionsLocked?: boolean;
  comments: CommentPanelComment[] | undefined;
  isLoading: boolean;
  onAssignOwner: (commentId: string, reviewerId: string) => void;
  onEscalate: (commentId: string) => void;
  onReply: (commentId: string) => void;
  onResolve: (commentId: string, nextResolved: boolean) => void;
  reviewers: CommentPanelReviewer[];
  pendingResolveCommentId?: string;
  pendingAssignCommentId?: string;
  pendingEscalateCommentId?: string;
  renderThreadRecovery?: (threadRootId: string) => ReactNode;
}

export function CommentPanelList({
  actionsLocked = false,
  comments,
  isLoading,
  onAssignOwner,
  onEscalate,
  onReply,
  onResolve,
  reviewers,
  pendingResolveCommentId,
  pendingAssignCommentId,
  pendingEscalateCommentId,
  renderThreadRecovery,
}: CommentPanelListProps) {
  const allComments = comments ?? [];
  const allThreadsResolved =
    allComments.length > 0 && allComments.every((comment) => comment.resolved);
  const { topLevel, repliesByParent } = groupCommentsByParent(allComments);

  if (isLoading) {
    return (
      <div
        className="flex items-center justify-center py-8"
        role="status"
        aria-label="Loading comments"
      >
        <Loader2 className="h-5 w-5 animate-spin motion-reduce:animate-none text-brand-primary" />
      </div>
    );
  }

  if (topLevel.length === 0) {
    return (
      <div className="py-8 text-center">
        <MessageSquare className="mx-auto mb-2 h-8 w-8 text-[var(--text-disabled)]" />
        <p className="text-sm text-[var(--text-tertiary)]">
          No comments yet. Start the discussion.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {allThreadsResolved ? (
        <p className="text-xs text-[var(--text-tertiary)] text-center py-1">
          No open threads. Everything here is resolved.
        </p>
      ) : null}
      {topLevel.map((comment) => (
        <CommentPanelThread
          key={comment.id}
          comment={comment}
          isActionPending={actionsLocked}
          isResolutionPending={!!pendingResolveCommentId}
          pendingCommentId={pendingResolveCommentId ?? null}
          isAssignmentPending={!!pendingAssignCommentId}
          pendingAssignmentCommentId={pendingAssignCommentId ?? null}
          isEscalationPending={!!pendingEscalateCommentId}
          pendingEscalateCommentId={pendingEscalateCommentId ?? null}
          onAssignOwner={onAssignOwner}
          onEscalate={onEscalate}
          replies={repliesByParent.get(comment.id) ?? []}
          onReply={onReply}
          onResolve={onResolve}
          reviewers={reviewers}
          recoveryNotice={renderThreadRecovery?.(comment.id)}
        />
      ))}
    </div>
  );
}
