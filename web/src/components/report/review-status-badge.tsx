"use client";

import { Check, FileSearch, PenLine, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ReviewStatus, ReviewTier } from "@/lib/review-rules";
import { REVIEW_STATUS_LABELS, REVIEW_TIER_LABELS } from "@/lib/review-rules";

const statusConfig: Record<
  ReviewStatus,
  { icon: typeof Check; bg: string; text: string; border: string }
> = {
  ai_draft: {
    icon: PenLine,
    bg: "bg-info/10",
    text: "text-info",
    border: "border-info/20",
  },
  reviewed: {
    icon: FileSearch,
    bg: "bg-warning/10",
    text: "text-warning",
    border: "border-warning/20",
  },
  approved: {
    icon: Check,
    bg: "bg-success/10",
    text: "text-success",
    border: "border-success/20",
  },
  accepted: {
    icon: Check,
    bg: "bg-success/10",
    text: "text-success",
    border: "border-success/20",
  },
  edited: {
    icon: PenLine,
    bg: "bg-warning/10",
    text: "text-warning",
    border: "border-warning/20",
  },
  rejected: {
    icon: XCircle,
    bg: "bg-error/10",
    text: "text-error",
    border: "border-error/20",
  },
};

interface ReviewStatusBadgeProps {
  status: ReviewStatus;
  className?: string;
  /** Show the review tier alongside status */
  tier?: ReviewTier;
  /** Compact mode (icon only) */
  compact?: boolean;
}

export function ReviewStatusBadge({
  status,
  className,
  tier,
  compact = false,
}: ReviewStatusBadgeProps) {
  const config = statusConfig[status];
  const Icon = config.icon;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium",
        config.bg,
        config.text,
        config.border,
        className,
      )}
      title={
        tier
          ? `${REVIEW_STATUS_LABELS[status]} — ${REVIEW_TIER_LABELS[tier]}`
          : REVIEW_STATUS_LABELS[status]
      }
    >
      <Icon className="h-3 w-3" />
      {!compact && REVIEW_STATUS_LABELS[status]}
    </span>
  );
}

interface ReviewTierBannerProps {
  tier: ReviewTier;
  className?: string;
}

/** Banner shown on patents that require review */
export function ReviewTierBanner({ tier, className }: ReviewTierBannerProps) {
  const isMandatory = tier === "mandate_review";

  return (
    <div
      className={cn(
        "flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium",
        isMandatory
          ? "bg-warning/10 border border-warning/20 text-warning"
          : "bg-info/10 border border-info/20 text-info",
        className,
      )}
    >
      <FileSearch className="h-3.5 w-3.5" />
      {isMandatory ? "Expert review required" : "Review suggested"}
    </div>
  );
}
