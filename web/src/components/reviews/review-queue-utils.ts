import type { ReviewQueueItem } from "@/hooks/use-review-queue";

export type ReviewQueueSortMode = "priority" | "recent" | "compound";

const RISK_ORDER: Record<string, number> = {
  high: 3,
  medium: 2,
  low: 1,
  clear: 0,
};

export const REVIEW_QUEUE_SORT_OPTIONS: Array<{
  value: ReviewQueueSortMode;
  label: string;
  description: string;
}> = [
  {
    value: "priority",
    label: "Priority",
    description: "Overdue, escalated, oldest first",
  },
  {
    value: "recent",
    label: "Recent",
    description: "Newest activity first",
  },
  {
    value: "compound",
    label: "Compound",
    description: "Alphabetical by compound",
  },
];

function compareText(left: string, right: string) {
  return left.localeCompare(right, undefined, { sensitivity: "base" });
}

function getActivityTimestamp(item: ReviewQueueItem) {
  const timestamp = Date.parse(item.updated_at || item.last_activity_at);
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function getPriorityScore(item: ReviewQueueItem) {
  return (
    Number(item.is_overdue) * 100 +
    Number(item.is_escalated) * 60 +
    Number(item.is_unassigned) * 30 +
    (RISK_ORDER[item.overall_risk ?? ""] ?? -1) * 10
  );
}

export function sortReviewQueueItems(
  items: ReviewQueueItem[],
  sortMode: ReviewQueueSortMode,
): ReviewQueueItem[] {
  const sortedItems = [...items];

  sortedItems.sort((left, right) => {
    switch (sortMode) {
      case "recent":
        return (
          getActivityTimestamp(right) - getActivityTimestamp(left) ||
          compareText(left.compound_name, right.compound_name) ||
          compareText(left.id, right.id)
        );
      case "compound":
        return (
          compareText(left.compound_name, right.compound_name) ||
          getActivityTimestamp(right) - getActivityTimestamp(left) ||
          compareText(left.id, right.id)
        );
      case "priority":
      default:
        return (
          getPriorityScore(right) - getPriorityScore(left) ||
          getActivityTimestamp(left) - getActivityTimestamp(right) ||
          compareText(left.compound_name, right.compound_name) ||
          compareText(left.id, right.id)
        );
    }
  });

  return sortedItems;
}
