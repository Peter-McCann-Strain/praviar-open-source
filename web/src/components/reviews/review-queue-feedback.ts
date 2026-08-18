import type { ReviewQueueBulkActionSuccess } from "@/components/reviews/review-queue-bulk-toolbar";

function buildScopeTargetLabel(feedback: ReviewQueueBulkActionSuccess) {
  if (!feedback.sharedAnalysisId && feedback.count > 1) {
    return `selected threads (${feedback.count})`;
  }

  const scopeSuffix =
    feedback.sharedAnalysisId && feedback.count > 1
      ? `${feedback.scopeLabel ?? "selected"} scope`
      : (feedback.scopeLabel ?? "selected thread");

  return feedback.count === 1
    ? scopeSuffix
    : `${scopeSuffix} (${feedback.count} threads)`;
}

export function buildBulkActionFeedbackMessage(
  feedback: ReviewQueueBulkActionSuccess,
) {
  const targetLabel = buildScopeTargetLabel(feedback);
  const skippedCopy = feedback.skippedCount
    ? ` ${feedback.skippedCount} already unchanged.`
    : "";

  switch (feedback.action) {
    case "assign":
      if (feedback.assignedToLabel === "Unassigned") {
        return `Cleared owner on ${targetLabel}.${skippedCopy}`;
      }
      return `Assigned ${targetLabel} to ${feedback.assignedToLabel ?? "reviewer"}.${skippedCopy}`;
    case "escalate":
      return `Escalated ${targetLabel} to legal review.`;
    case "resolve":
    default:
      return `Resolved ${targetLabel}.`;
  }
}

export function buildBulkActionChangeSummary(
  feedback: ReviewQueueBulkActionSuccess,
) {
  switch (feedback.action) {
    case "assign":
      if (feedback.assignedToLabel === "Unassigned") {
        return feedback.skippedCount
          ? `Ownership was cleared where needed. ${feedback.skippedCount} selected thread${feedback.skippedCount === 1 ? " was" : "s were"} already unassigned.`
          : "Ownership was cleared for the selected scope. The unassigned queue will reflect the refresh.";
      }
      return `Ownership is now routed to ${feedback.assignedToLabel ?? "the selected reviewer"} across the selected scope.`;
    case "escalate":
      return "These threads now count toward legal-review pressure and stay traceable in escalated queue slices.";
    case "resolve":
    default:
      return "Resolved threads move out of open review queues once the refreshed slice lands.";
  }
}
