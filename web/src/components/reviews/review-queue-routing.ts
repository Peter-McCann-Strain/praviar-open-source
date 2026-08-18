import type { ReviewQueueItem } from "@/hooks/use-review-queue";
import {
  canAccessFullReport,
  getReportAccessHref,
} from "@/lib/report-permissions";

type ReviewQueueRouteItem = Pick<
  ReviewQueueItem,
  "analysis_id" | "analysis_status"
>;

export function reviewQueueItemHasReport(item: ReviewQueueRouteItem) {
  return item.analysis_status === "completed";
}

export function buildReviewQueueItemHref(
  item: ReviewQueueRouteItem,
  currentUserRole?: string | null,
  riskRatingsRestricted?: boolean,
) {
  const analysisPath = `/analyses/${encodeURIComponent(item.analysis_id)}`;
  return reviewQueueItemHasReport(item)
    ? getReportAccessHref(
        item.analysis_id,
        currentUserRole,
        riskRatingsRestricted,
      )
    : analysisPath;
}

export function getReviewQueueItemActionLabel(
  item: ReviewQueueRouteItem,
  currentUserRole?: string | null,
  riskRatingsRestricted?: boolean,
) {
  if (!reviewQueueItemHasReport(item)) return "View run";
  return canAccessFullReport(currentUserRole, riskRatingsRestricted)
    ? "Open report"
    : "Open summary";
}

export function getReviewQueueItemSpotlightActionLabel(
  item: ReviewQueueRouteItem,
  currentUserRole?: string | null,
  riskRatingsRestricted?: boolean,
) {
  if (!reviewQueueItemHasReport(item)) return "View run";
  return canAccessFullReport(currentUserRole, riskRatingsRestricted)
    ? "View report"
    : "View summary";
}
