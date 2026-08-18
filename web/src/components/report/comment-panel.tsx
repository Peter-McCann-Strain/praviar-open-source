"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";
import { MutationRecoveryNotice } from "@/components/shared/mutation-recovery-notice";
import { Button } from "@/components/ui/button";
import { useAuthBoundaryReset } from "@/hooks/use-auth-boundary-reset";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useMutationRecovery } from "@/hooks/use-mutation-recovery";
import { isAuthBoundaryError } from "@/lib/api-client";
import { logError } from "@/lib/error-logger";
import {
  useAssignComment,
  useCommentReviewers,
  useComments,
  useCreateComment,
  useEscalateComment,
  useToggleCommentResolution,
} from "@/hooks/use-comments";
import type {
  AssignCommentInput,
  CreateCommentInput,
  EscalateCommentInput,
  ResolveCommentInput,
} from "@/hooks/use-comments";
import { CommentPanelHeader } from "@/components/report/comment-panel-header";
import { CommentPanelComposer } from "@/components/report/comment-panel-composer";
import { CommentPanelList } from "@/components/report/comment-panel-list";
import type { CommentPanelComment } from "@/components/report/comment-panel-types";

interface CommentPanelProps {
  analysisId: string;
}

type CommentPatchState = {
  patch: Partial<CommentPanelComment>;
  sourceComments: CommentPanelComment[] | undefined;
};

type CommentThreadRecoveryVariables =
  | { kind: "assignment"; variables: AssignCommentInput }
  | { kind: "resolution"; variables: ResolveCommentInput }
  | { kind: "escalation"; variables: EscalateCommentInput };

const ASSIGNMENT_PATCH_KEYS = [
  "assigned_to",
  "assigned_by",
  "assigned_reviewer_name",
  "assigned_reviewer_email",
  "assigned_at",
  "assignment_event_count",
  "last_assignment_at",
  "queue_age_hours",
  "is_overdue",
] as const satisfies readonly (keyof CommentPanelComment)[];

const RESOLUTION_PATCH_KEYS = [
  "resolved",
  "resolved_by",
  "resolved_at",
] as const satisfies readonly (keyof CommentPanelComment)[];

const ESCALATION_PATCH_KEYS = [
  "escalation_status",
  "escalated_by",
  "escalated_by_name",
  "escalated_by_email",
  "escalated_at",
  "escalation_event_count",
  "last_escalation_at",
  "escalated_to_review",
  "review_handoff_comment_id",
] as const satisfies readonly (keyof CommentPanelComment)[];

function pickCommentPatch(
  comment: Partial<CommentPanelComment>,
  keys: readonly (keyof CommentPanelComment)[],
): Partial<CommentPanelComment> {
  const patch: Partial<CommentPanelComment> = {};
  const writablePatch = patch as Record<string, unknown>;
  for (const key of keys) {
    if (key in comment) {
      writablePatch[key] = comment[key];
    }
  }
  return patch;
}

function getThreadRootId(
  comments: CommentPanelComment[] | undefined,
  commentId: string,
): string {
  const target = comments?.find((comment) => comment.id === commentId);
  return target?.parent_id ?? target?.id ?? commentId;
}

export function CommentPanel({ analysisId }: CommentPanelProps) {
  const token = useAuthToken();
  const {
    data: comments,
    error: commentsError,
    isLoading,
    refetch: refetchComments,
  } = useComments(analysisId, token);
  const { data: reviewers = [] } = useCommentReviewers(analysisId, token);
  const createComment = useCreateComment(token);
  const assignComment = useAssignComment(token);
  const toggleCommentResolution = useToggleCommentResolution(token);
  const escalateComment = useEscalateComment(token);
  const postRecovery = useMutationRecovery<CreateCommentInput>();
  const threadRecovery = useMutationRecovery<CommentThreadRecoveryVariables>();
  const [body, setBody] = useState("");
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const [recoveryActionPending, setRecoveryActionPending] = useState(false);
  const [threadMutationLocked, setThreadMutationLocked] = useState(false);
  const threadMutationInFlightRef = useRef(false);
  const [commentPatches, setCommentPatches] = useState<
    Record<string, CommentPatchState>
  >({});
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const commentsAccessRestricted = isAuthBoundaryError(commentsError);
  const commentsUnavailable = Boolean(commentsError);
  const mutationRecoveryActive = Boolean(
    postRecovery.recovery || threadRecovery.recovery,
  );
  const commentControlsLocked =
    mutationRecoveryActive ||
    recoveryActionPending ||
    threadMutationLocked ||
    createComment.isPending ||
    assignComment.isPending ||
    toggleCommentResolution.isPending ||
    escalateComment.isPending;

  const resetPrivateCommentState = useCallback(() => {
    setBody("");
    setReplyTo(null);
    setRecoveryActionPending(false);
    threadMutationInFlightRef.current = false;
    setThreadMutationLocked(false);
  }, []);
  useAuthBoundaryReset(resetPrivateCommentState);

  useEffect(() => {
    if (replyTo && inputRef.current) {
      inputRef.current.focus();
    }
  }, [replyTo]);

  const displayComments = useMemo(
    () =>
      commentsUnavailable
        ? undefined
        : comments?.map((comment) => {
            const patchState = commentPatches[comment.id];
            return patchState?.sourceComments === comments
              ? { ...comment, ...patchState.patch }
              : comment;
          }),
    [comments, commentPatches, commentsUnavailable],
  );

  const applyCommentPatch = useCallback(
    (commentId: string, patch: Partial<CommentPanelComment>) => {
      setCommentPatches((current) => ({
        ...current,
        [commentId]: {
          patch: { ...current[commentId]?.patch, ...patch },
          sourceComments: comments,
        },
      }));
    },
    [comments],
  );

  const handleSubmit = async () => {
    const trimmed = body.trim();
    if (!trimmed || createComment.isPending || commentControlsLocked) return;
    const variables: CreateCommentInput = {
      analysis_id: analysisId,
      body: trimmed,
      parent_id: replyTo || undefined,
      target_type: "analysis",
      target_id: analysisId,
    };
    const attempt = postRecovery.beginAttempt();

    try {
      await createComment.mutateAsync(variables);
      if (!postRecovery.isAttemptCurrent(attempt)) return;
      setBody("");
      setReplyTo(null);
      postRecovery.clearRecoveryForAttempt(attempt);
    } catch (err) {
      logError(err, {
        source: "CommentPanel.createComment",
        extra: { analysisId },
      });
      postRecovery.captureFailure(err, variables, attempt);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleAssignOwner = async (commentId: string, reviewerId: string) => {
    if (
      threadMutationInFlightRef.current ||
      mutationRecoveryActive ||
      recoveryActionPending ||
      createComment.isPending
    ) {
      return;
    }
    threadMutationInFlightRef.current = true;
    setThreadMutationLocked(true);
    const variables: AssignCommentInput = {
      analysis_id: analysisId,
      comment_id: commentId,
      assigned_to: reviewerId || null,
    };
    const attempt = threadRecovery.beginAttempt();
    try {
      const updated = await assignComment.mutateAsync(variables);
      if (!threadRecovery.isAttemptCurrent(attempt)) return;
      applyCommentPatch(
        commentId,
        pickCommentPatch(updated, ASSIGNMENT_PATCH_KEYS),
      );
    } catch (err) {
      logError(err, {
        source: "CommentPanel.assignComment",
        extra: { analysisId, commentId },
      });
      threadRecovery.captureFailure(
        err,
        {
          kind: "assignment",
          variables,
        },
        attempt,
      );
    } finally {
      threadMutationInFlightRef.current = false;
      setThreadMutationLocked(false);
    }
  };

  const handleResolve = async (commentId: string, nextResolved: boolean) => {
    if (
      threadMutationInFlightRef.current ||
      mutationRecoveryActive ||
      recoveryActionPending ||
      createComment.isPending
    ) {
      return;
    }
    threadMutationInFlightRef.current = true;
    setThreadMutationLocked(true);
    const variables: ResolveCommentInput = {
      analysis_id: analysisId,
      comment_id: commentId,
      resolved: nextResolved,
    };
    const attempt = threadRecovery.beginAttempt();
    try {
      const updated = await toggleCommentResolution.mutateAsync(variables);
      if (!threadRecovery.isAttemptCurrent(attempt)) return;
      applyCommentPatch(
        commentId,
        pickCommentPatch(updated, RESOLUTION_PATCH_KEYS),
      );
    } catch (err) {
      logError(err, {
        source: "CommentPanel.resolveComment",
        extra: { analysisId, commentId, resolved: nextResolved },
      });
      threadRecovery.captureFailure(
        err,
        {
          kind: "resolution",
          variables,
        },
        attempt,
      );
    } finally {
      threadMutationInFlightRef.current = false;
      setThreadMutationLocked(false);
    }
  };

  const handleEscalate = async (commentId: string) => {
    if (
      threadMutationInFlightRef.current ||
      mutationRecoveryActive ||
      recoveryActionPending ||
      createComment.isPending
    ) {
      return;
    }
    threadMutationInFlightRef.current = true;
    setThreadMutationLocked(true);
    const variables: EscalateCommentInput = {
      analysis_id: analysisId,
      comment_id: commentId,
      promote_to_under_review: true,
    };
    const attempt = threadRecovery.beginAttempt();
    try {
      const updated = await escalateComment.mutateAsync(variables);
      if (!threadRecovery.isAttemptCurrent(attempt)) return;
      applyCommentPatch(
        commentId,
        pickCommentPatch(updated, ESCALATION_PATCH_KEYS),
      );
    } catch (err) {
      logError(err, {
        source: "CommentPanel.escalateComment",
        extra: { analysisId, commentId },
      });
      threadRecovery.captureFailure(
        err,
        {
          kind: "escalation",
          variables,
        },
        attempt,
      );
    } finally {
      threadMutationInFlightRef.current = false;
      setThreadMutationLocked(false);
    }
  };

  const refreshDiscussionForRecovery = async (
    source: string,
    captureRefreshFailure: (error: unknown) => void,
    clearRecovery: () => void,
    isAttemptCurrent: () => boolean,
  ) => {
    setRecoveryActionPending(true);
    try {
      const refreshed = await refetchComments();
      if (refreshed.error) {
        captureRefreshFailure(refreshed.error);
        return;
      }
      if (!isAttemptCurrent()) return;
      clearRecovery();
    } catch (err) {
      logError(err, {
        source,
        extra: { analysisId },
      });
      captureRefreshFailure(err);
    } finally {
      if (isAttemptCurrent()) {
        setRecoveryActionPending(false);
      }
    }
  };

  const handlePostRecoveryAction = async () => {
    const recovery = postRecovery.recovery;
    if (!recovery || recoveryActionPending) return;

    if (recovery.mode === "failed") {
      postRecovery.clearRecovery();
      requestAnimationFrame(() => inputRef.current?.focus());
      return;
    }

    const attempt = postRecovery.beginAttempt();
    await refreshDiscussionForRecovery(
      "CommentPanel.refreshPostOutcome",
      (error) =>
        postRecovery.captureFailure(
          error,
          recovery.variables,
          attempt,
          "outcome-unknown",
        ),
      () => {
        postRecovery.clearRecoveryForAttempt(attempt);
      },
      () => postRecovery.isAttemptCurrent(attempt),
    );
  };

  const handleThreadRecoveryAction = async () => {
    const recovery = threadRecovery.recovery;
    if (!recovery || recoveryActionPending) return;
    const recoveryVariables = recovery.variables;

    if (recovery.mode === "failed") {
      threadRecovery.clearRecovery();
      return;
    }

    if (
      recoveryVariables.kind === "escalation" ||
      recoveryVariables.kind === "resolution"
    ) {
      const attempt = threadRecovery.beginAttempt();
      await refreshDiscussionForRecovery(
        recoveryVariables.kind === "escalation"
          ? "CommentPanel.refreshEscalationOutcome"
          : "CommentPanel.refreshResolutionOutcome",
        (error) =>
          threadRecovery.captureFailure(
            error,
            recoveryVariables,
            attempt,
            "outcome-unknown",
          ),
        () => {
          threadRecovery.clearRecoveryForAttempt(attempt);
        },
        () => threadRecovery.isAttemptCurrent(attempt),
      );
      return;
    }

    const attempt = threadRecovery.beginAttempt();
    setRecoveryActionPending(true);
    try {
      const updated = await assignComment.mutateAsync(
        recoveryVariables.variables,
      );
      if (!threadRecovery.isAttemptCurrent(attempt)) return;
      applyCommentPatch(
        recoveryVariables.variables.comment_id,
        pickCommentPatch(updated, ASSIGNMENT_PATCH_KEYS),
      );
      threadRecovery.clearRecoveryForAttempt(attempt);
    } catch (err) {
      logError(err, {
        source: `CommentPanel.retry${recoveryVariables.kind}`,
        extra: {
          analysisId,
          commentId: recoveryVariables.variables.comment_id,
        },
      });
      threadRecovery.captureFailure(err, recoveryVariables, attempt);
    } finally {
      if (threadRecovery.isAttemptCurrent(attempt)) {
        setRecoveryActionPending(false);
      }
    }
  };

  // Track the active row for precise progress copy. All thread controls are
  // locked while any legal-ledger mutation is in flight so a second mutation
  // cannot overwrite the single recovery receipt.
  const pendingEscalateCommentId = escalateComment.isPending
    ? escalateComment.variables?.comment_id
    : undefined;
  const pendingResolveCommentId = toggleCommentResolution.isPending
    ? toggleCommentResolution.variables?.comment_id
    : undefined;
  const pendingAssignCommentId = assignComment.isPending
    ? assignComment.variables?.comment_id
    : undefined;
  const threadRecoveryRootId = threadRecovery.recovery
    ? getThreadRootId(
        displayComments,
        threadRecovery.recovery.variables.variables.comment_id,
      )
    : null;
  const postRecoveryCopy = postRecovery.recovery
    ? postRecovery.recovery.mode === "outcome-unknown"
      ? {
          actionLabel: "Refresh discussion",
          description:
            "Your draft is preserved. Refresh the discussion to check whether it was posted before sending it again.",
          title: "Comment outcome unconfirmed",
        }
      : {
          actionLabel: "Review draft",
          description:
            "The comment was not posted. Your draft and reply target are preserved so you can review them before trying again.",
          title: "Comment was not posted",
        }
    : null;
  const threadRecoveryCopy = threadRecovery.recovery
    ? threadRecovery.recovery.variables.kind === "assignment"
      ? {
          actionLabel:
            threadRecovery.recovery.mode === "outcome-unknown"
              ? "Retry assignment"
              : "Revise assignment",
          description:
            threadRecovery.recovery.mode === "outcome-unknown"
              ? "The requested owner remains recorded here. Retry the same assignment before making another thread change."
              : "The requested owner was not applied. Clear this notice to revise the assignment without losing the discussion.",
          title:
            threadRecovery.recovery.mode === "outcome-unknown"
              ? "Assignment outcome unconfirmed"
              : "Assignment was not applied",
        }
      : threadRecovery.recovery.variables.kind === "resolution"
        ? {
            actionLabel:
              threadRecovery.recovery.mode === "outcome-unknown"
                ? "Refresh discussion"
                : "Revise resolution",
            description:
              threadRecovery.recovery.mode === "outcome-unknown"
                ? "Refresh the discussion to confirm the current resolved state. Praviar will not rewrite the resolution timestamp or audit trail automatically."
                : "The requested thread state was not applied. Clear this notice to review the thread and choose a new action.",
            title:
              threadRecovery.recovery.mode === "outcome-unknown"
                ? "Resolution outcome unconfirmed"
                : "Resolution was not applied",
          }
        : {
            actionLabel:
              threadRecovery.recovery.mode === "outcome-unknown"
                ? "Refresh discussion"
                : "Review thread",
            description:
              threadRecovery.recovery.mode === "outcome-unknown"
                ? "Refresh the discussion to confirm whether the escalation was recorded. Praviar will not submit a second escalation automatically."
                : "The escalation was not recorded. Review the thread before submitting a new escalation.",
            title:
              threadRecovery.recovery.mode === "outcome-unknown"
                ? "Escalation outcome unconfirmed"
                : "Escalation was not applied",
          }
    : null;

  return (
    <div className="space-y-6">
      <CommentPanelHeader
        count={commentsUnavailable ? 0 : (comments?.length ?? 0)}
      />

      {commentsUnavailable ? (
        <div
          role="alert"
          aria-labelledby="comment-panel-load-error-title"
          className="rounded-lg border border-error/20 bg-error/10 p-4"
          data-testid="comment-panel-load-error"
        >
          <div className="flex items-start gap-3">
            <AlertTriangle
              className="mt-0.5 h-5 w-5 shrink-0 text-error"
              aria-hidden="true"
            />
            <div className="min-w-0 flex-1">
              <p
                id="comment-panel-load-error-title"
                className="font-semibold text-[var(--text-primary)]"
              >
                {commentsAccessRestricted
                  ? "Comment access restricted"
                  : "Comments temporarily unavailable"}
              </p>
              <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                {commentsAccessRestricted
                  ? "Your current session is not authorized to view or update this discussion. Cached comments are hidden until access is confirmed again."
                  : "Praviar could not load the discussion thread. The composer and thread actions stay locked so the report does not imply discussion is empty."}
              </p>
              <Button
                type="button"
                variant="outline"
                className="mt-3 min-h-11 w-full gap-2 sm:w-auto"
                onClick={() => {
                  void refetchComments();
                }}
              >
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
                Retry comments load
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <>
          <CommentPanelComposer
            body={body}
            controlsDisabled={commentControlsLocked}
            inputRef={inputRef}
            isSubmitting={createComment.isPending}
            onBodyChange={setBody}
            onCancelReply={() => setReplyTo(null)}
            onKeyDown={handleKeyDown}
            onSubmit={handleSubmit}
            replyTo={replyTo}
          />
          {postRecovery.recovery && postRecoveryCopy ? (
            <MutationRecoveryNotice
              actionLabel={postRecoveryCopy.actionLabel}
              actionPending={recoveryActionPending}
              dataTestId="comment-post-recovery"
              description={postRecoveryCopy.description}
              mode={postRecovery.recovery.mode}
              onAction={() => {
                void handlePostRecoveryAction();
              }}
              title={postRecoveryCopy.title}
            />
          ) : null}

          <CommentPanelList
            actionsLocked={commentControlsLocked}
            comments={displayComments}
            isLoading={isLoading}
            onAssignOwner={handleAssignOwner}
            onEscalate={handleEscalate}
            onReply={setReplyTo}
            onResolve={handleResolve}
            reviewers={reviewers}
            pendingResolveCommentId={pendingResolveCommentId}
            pendingAssignCommentId={pendingAssignCommentId}
            pendingEscalateCommentId={pendingEscalateCommentId}
            renderThreadRecovery={(threadRootId) =>
              threadRecovery.recovery &&
              threadRecoveryCopy &&
              threadRecoveryRootId === threadRootId ? (
                <MutationRecoveryNotice
                  actionLabel={threadRecoveryCopy.actionLabel}
                  actionPending={recoveryActionPending}
                  dataTestId={`comment-${threadRecovery.recovery.variables.kind}-recovery-${threadRootId}`}
                  description={threadRecoveryCopy.description}
                  mode={threadRecovery.recovery.mode}
                  onAction={() => {
                    void handleThreadRecoveryAction();
                  }}
                  dismissLabel="Dismiss and revise"
                  onDismiss={
                    threadRecovery.recovery.mode === "failed"
                      ? threadRecovery.clearRecovery
                      : undefined
                  }
                  title={threadRecoveryCopy.title}
                />
              ) : null
            }
          />
        </>
      )}
    </div>
  );
}
