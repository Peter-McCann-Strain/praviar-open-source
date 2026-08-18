/**
 * Policy-gated review rules.
 * Raw model confidence is not externally calibrated and must never suppress
 * human review or imply that an AI finding was accepted automatically.
 */

export type ReviewTier = "suggest_review" | "mandate_review";

export type ReviewStatus =
  | "ai_draft"
  | "reviewed"
  | "approved"
  | "accepted"
  | "edited"
  | "rejected";

/** Raw confidence alone can never waive review. */
export function getReviewTier(_confidence: number): ReviewTier {
  return "suggest_review";
}

/** Risk policy determines the minimum patent-review posture. */
export function getPatentReviewTier(analysis: {
  risk_level: string;
  claims_analyzed?: Array<{ confidence?: number }>;
}): ReviewTier {
  const riskLevel = analysis.risk_level.trim().toLowerCase();
  return riskLevel === "high" || riskLevel === "medium"
    ? "mandate_review"
    : "suggest_review";
}

/** Display label for review status */
export const REVIEW_STATUS_LABELS: Record<ReviewStatus, string> = {
  ai_draft: "AI Draft",
  reviewed: "Reviewed",
  approved: "Approved",
  accepted: "Accepted",
  edited: "Edited",
  rejected: "Rejected",
};

/** Display label for review tier */
export const REVIEW_TIER_LABELS: Record<ReviewTier, string> = {
  suggest_review: "Review Suggested",
  mandate_review: "Review Required",
};
