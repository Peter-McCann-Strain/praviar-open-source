import { listDemoAnalyses } from "@/lib/demo-data";
import { SHOWCASE_PAYLOAD } from "@/lib/showcase-report";
import type {
  ReviewQueueFilter,
  ReviewQueueItem,
  ReviewQueueResponse,
} from "@/hooks/use-review-queue";

const DEMO_REVIEWER_DIRECTORY = new Map<
  string,
  { name: string; email: string }
>([
  [
    SHOWCASE_PAYLOAD.review.assigned_to.id,
    {
      name: SHOWCASE_PAYLOAD.review.assigned_to.display_name,
      email: "riley@example.invalid",
    },
  ],
  [
    SHOWCASE_PAYLOAD.matter.owner.id,
    {
      name: SHOWCASE_PAYLOAD.matter.owner.display_name,
      email: "casey@example.invalid",
    },
  ],
]);

let demoReviewQueueItems: ReviewQueueItem[] | null = null;

function buildInitialDemoReviewQueueItems(): ReviewQueueItem[] {
  const analyses = listDemoAnalyses();
  const completed = analyses.find(
    (analysis) => analysis.status === "completed",
  );
  const running = analyses.find((analysis) => analysis.status === "running");
  const failed = analyses.find((analysis) => analysis.status === "failed");

  return [
    {
      id: "rq-demo-1",
      analysis_id: completed?.id ?? "ana_demo_001",
      compound_name:
        completed?.compound_name ?? SHOWCASE_PAYLOAD.compound.display_name,
      analysis_status: "completed",
      overall_risk: completed?.overall_risk ?? "medium",
      comment_body: SHOWCASE_PAYLOAD.review.required_actions[1],
      assigned_to_id: SHOWCASE_PAYLOAD.review.assigned_to.id,
      assigned_to_name: SHOWCASE_PAYLOAD.review.assigned_to.display_name,
      assigned_to_email: "riley@example.invalid",
      is_mine: true,
      is_unassigned: false,
      is_overdue: false,
      overdue_label: null,
      is_escalated: true,
      queue_age_hours: 18.5,
      escalated_at: "2026-01-15T00:15:00Z",
      last_activity_at: SHOWCASE_PAYLOAD.clock,
      updated_at: SHOWCASE_PAYLOAD.clock,
      comment_count: 3,
    },
    {
      id: "rq-demo-2",
      analysis_id: running?.id ?? "ana_demo_002",
      compound_name:
        running?.compound_name ?? SHOWCASE_PAYLOAD.compound.display_name,
      analysis_status: "running",
      overall_risk: running?.overall_risk ?? null,
      comment_body: SHOWCASE_PAYLOAD.review.required_actions[0],
      assigned_to_id: null,
      assigned_to_name: null,
      assigned_to_email: null,
      is_mine: false,
      is_unassigned: true,
      is_overdue: false,
      overdue_label: null,
      is_escalated: false,
      queue_age_hours: 6.25,
      escalated_at: null,
      last_activity_at: "2026-01-15T09:05:00Z",
      updated_at: "2026-01-15T09:05:00Z",
      comment_count: 1,
    },
    {
      id: "rq-demo-3",
      analysis_id: failed?.id ?? "ana_demo_003",
      compound_name:
        failed?.compound_name ?? SHOWCASE_PAYLOAD.compound.display_name,
      analysis_status: "failed",
      overall_risk: failed?.overall_risk ?? null,
      comment_body: SHOWCASE_PAYLOAD.failure_states[0].user_action,
      assigned_to_id: SHOWCASE_PAYLOAD.matter.owner.id,
      assigned_to_name: SHOWCASE_PAYLOAD.matter.owner.display_name,
      assigned_to_email: "casey@example.invalid",
      is_mine: false,
      is_unassigned: false,
      is_overdue: true,
      overdue_label: "Overdue · 2d open",
      is_escalated: true,
      queue_age_hours: 53,
      escalated_at: "2026-01-13T07:10:00Z",
      last_activity_at: "2026-01-15T07:10:00Z",
      updated_at: "2026-01-15T07:10:00Z",
      comment_count: 5,
    },
  ];
}

function getDemoReviewQueueItems() {
  if (!demoReviewQueueItems) {
    demoReviewQueueItems = buildInitialDemoReviewQueueItems();
  }

  return demoReviewQueueItems;
}

function applyReviewQueueFilter(
  items: ReviewQueueItem[],
  filter: ReviewQueueFilter,
): ReviewQueueItem[] {
  switch (filter) {
    case "mine":
      return items.filter((item) => item.is_mine);
    case "unassigned":
      return items.filter((item) => item.is_unassigned);
    case "overdue":
      return items.filter((item) => item.is_overdue);
    case "escalated":
      return items.filter((item) => item.is_escalated);
    default:
      return items;
  }
}

function newestQueueActivity(items: ReviewQueueItem[]) {
  return items.reduce<string | null>((currentNewest, item) => {
    if (!currentNewest) {
      return item.updated_at;
    }

    return Date.parse(item.updated_at) > Date.parse(currentNewest)
      ? item.updated_at
      : currentNewest;
  }, null);
}

export function buildDemoReviewQueue(
  filter: ReviewQueueFilter,
): ReviewQueueResponse {
  const items = getDemoReviewQueueItems();

  return {
    counts: {
      total: items.length,
      mine: items.filter((item) => item.is_mine).length,
      unassigned: items.filter((item) => item.is_unassigned).length,
      overdue: items.filter((item) => item.is_overdue).length,
      escalated: items.filter((item) => item.is_escalated).length,
    },
    items: applyReviewQueueFilter(items, filter),
    updated_at: newestQueueActivity(items),
  };
}

export function assignDemoReviewQueueItem({
  commentId,
  assignedTo,
}: {
  commentId: string;
  assignedTo: string | null;
}) {
  const reviewer = assignedTo ? DEMO_REVIEWER_DIRECTORY.get(assignedTo) : null;
  demoReviewQueueItems = getDemoReviewQueueItems().map((item) =>
    item.id === commentId
      ? {
          ...item,
          assigned_to_id: assignedTo,
          assigned_to_name: reviewer?.name ?? null,
          assigned_to_email: reviewer?.email ?? null,
          is_mine: assignedTo === SHOWCASE_PAYLOAD.review.assigned_to.id,
          is_unassigned: assignedTo === null,
          updated_at: new Date().toISOString(),
        }
      : item,
  );
}

export function resolveDemoReviewQueueItem(commentId: string) {
  demoReviewQueueItems = getDemoReviewQueueItems().filter(
    (item) => item.id !== commentId,
  );
}

export function escalateDemoReviewQueueItem(commentId: string) {
  demoReviewQueueItems = getDemoReviewQueueItems().map((item) => {
    if (item.id !== commentId || item.is_escalated) {
      return item;
    }

    const timestamp = new Date().toISOString();
    return {
      ...item,
      is_escalated: true,
      escalated_at: timestamp,
      last_activity_at: timestamp,
      updated_at: timestamp,
    };
  });
}

export function recordDemoReviewQueueComment({
  analysisId,
  commentCount,
  createdAt,
  rootBody,
  rootCommentId,
}: {
  analysisId: string;
  commentCount: number;
  createdAt: string;
  rootBody: string;
  rootCommentId: string;
}) {
  const items = getDemoReviewQueueItems();
  const existing = items.find((item) => item.id === rootCommentId);

  if (existing) {
    demoReviewQueueItems = items.map((item) =>
      item.id === rootCommentId
        ? {
            ...item,
            comment_count: commentCount,
            last_activity_at: createdAt,
            updated_at: createdAt,
          }
        : item,
    );
    return;
  }

  const analysis = listDemoAnalyses().find((item) => item.id === analysisId);
  demoReviewQueueItems = [
    ...items,
    {
      id: rootCommentId,
      analysis_id: analysisId,
      compound_name: analysis?.compound_name ?? "Demo compound",
      analysis_status: analysis?.status ?? "completed",
      overall_risk: analysis?.overall_risk ?? null,
      comment_body: rootBody,
      assigned_to_id: null,
      assigned_to_name: null,
      assigned_to_email: null,
      is_mine: false,
      is_unassigned: true,
      is_overdue: false,
      overdue_label: null,
      is_escalated: false,
      queue_age_hours: 0,
      escalated_at: null,
      last_activity_at: createdAt,
      updated_at: createdAt,
      comment_count: commentCount,
    },
  ];
}

export function resetDemoReviewQueueState() {
  demoReviewQueueItems = null;
}
