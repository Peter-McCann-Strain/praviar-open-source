export type ReviewQueueAction = "assign" | "resolve" | "escalate";

const ACTION_LABELS: Record<ReviewQueueAction, string> = {
  assign: "Owner update",
  resolve: "Thread resolution",
  escalate: "Escalation",
};

const PARTIAL_ACTION_LABELS: Record<ReviewQueueAction, string> = {
  assign: "owner changes",
  resolve: "thread resolutions",
  escalate: "escalations",
};

export const REVIEW_QUEUE_LOAD_ERROR_COPY =
  "The queue data could not be loaded right now. Existing review assignments and thread states are unchanged.";

export const REVIEWER_LIST_ERROR_COPY =
  "Reviewer list temporarily unavailable. Existing owner assignments are unchanged.";

export function buildReviewQueueActionError(action: ReviewQueueAction): string {
  return `${ACTION_LABELS[action]} was not saved. Existing review state is unchanged.`;
}

export function buildReviewQueuePartialActionError({
  action,
  failed,
  total,
}: {
  action: ReviewQueueAction;
  failed: number;
  total: number;
}): string {
  if (failed >= total) {
    return buildReviewQueueActionError(action);
  }

  return `${failed} of ${total} selected ${PARTIAL_ACTION_LABELS[action]} were not saved. Successful updates remain traceable after refresh.`;
}
