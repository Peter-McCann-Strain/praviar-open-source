"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { LockKeyhole } from "lucide-react";
import {
  ReviewQueuePage,
  type ReviewQueueReviewerScope,
} from "@/components/reviews/review-queue-page";
import { OperationalStatusFrame } from "@/components/shared/operational-status-frame";
import { useAuthToken } from "@/hooks/use-auth-token";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";
import type { ReviewQueueFilter } from "@/hooks/use-review-queue";
import type { ReviewQueueSortMode } from "@/components/reviews/review-queue-utils";

const ALLOWED_FILTERS: ReviewQueueFilter[] = [
  "mine",
  "unassigned",
  "overdue",
  "escalated",
];
const ALLOWED_SORTS: ReviewQueueSortMode[] = ["priority", "recent", "compound"];
const ALLOWED_REVIEWER_SCOPES: ReviewQueueReviewerScope[] = ["all", "mine"];
type ReviewQueueFocusPreset = "my-overdue" | "my-escalated";

const FOCUS_PRESET_FILTERS: Record<ReviewQueueFocusPreset, ReviewQueueFilter> =
  {
    "my-overdue": "overdue",
    "my-escalated": "escalated",
  };

const FOCUS_PRESET_SCOPES: Record<
  ReviewQueueFocusPreset,
  ReviewQueueReviewerScope
> = {
  "my-overdue": "mine",
  "my-escalated": "mine",
};

function ReviewsContent() {
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const searchParams = useSearchParams();
  if (!principal.data && (principal.isLoading || principal.isFetching)) {
    return (
      <OperationalStatusFrame
        contextItems={[
          "Review records remain unchanged",
          "No assignment action submitted",
        ]}
        dataTestId="review-queue-access-check"
        description="Praviar is confirming whether this role can open the organization review queue."
        eyebrow="Review queue access"
        icon={LockKeyhole}
        isPending
        recoveryBody="The authorization snapshot will refresh automatically."
        recoveryTitle="Confirming role permissions"
        title="Checking review access"
        titleId="review-queue-access-check-title"
        tone="default"
      />
    );
  }
  if (!principal.data) {
    return (
      <OperationalStatusFrame
        actionLabel="Retry access check"
        contextItems={[
          "Review records remain unchanged",
          "No assignment action submitted",
          "Role authority was not inferred",
        ]}
        dataTestId="review-queue-access-unavailable"
        description="Praviar could not load the authoritative application-role snapshot, so review records remain closed until the access check succeeds."
        eyebrow="Review queue access"
        icon={LockKeyhole}
        isPending={false}
        onRetry={() => {
          void principal.refetch();
        }}
        recoveryBody="Retry the capability check. If it continues to fail, verify the session or contact your workspace administrator."
        recoveryTitle="Restore the access check"
        title="Review access check unavailable"
        titleId="review-queue-access-unavailable-title"
        tone="warning"
      />
    );
  }
  if (principal.data?.can_view_review_queue !== true) {
    return (
      <OperationalStatusFrame
        contextItems={[
          "No review records disclosed",
          "No assignment action submitted",
          "Analysis summaries remain available",
        ]}
        dataTestId="review-queue-access-restricted"
        description="Your current application role can review permitted analysis summaries but cannot access internal scientific or legal review threads."
        eyebrow="Review queue access"
        icon={LockKeyhole}
        isPending={false}
        onRetry={() => {
          void principal.refetch();
        }}
        recoveryBody="Ask a workspace administrator or counsel owner to update your review role, then retry the authorization check."
        recoveryTitle="Request review access"
        title="Review queue access restricted"
        titleId="review-queue-access-restricted-title"
        tone="error"
      />
    );
  }
  const filterParam = searchParams.get("filter");
  const sortParam = searchParams.get("sort");
  const scopeParam = searchParams.get("scope");
  const focusParam = searchParams.get("focus");
  const focusPreset =
    focusParam === "my-overdue" || focusParam === "my-escalated"
      ? focusParam
      : null;
  const initialFilter = ALLOWED_FILTERS.includes(
    filterParam as ReviewQueueFilter,
  )
    ? (filterParam as ReviewQueueFilter)
    : focusPreset
      ? FOCUS_PRESET_FILTERS[focusPreset]
      : "mine";
  const initialSortMode = ALLOWED_SORTS.includes(
    sortParam as ReviewQueueSortMode,
  )
    ? (sortParam as ReviewQueueSortMode)
    : "priority";
  const initialReviewerScope = ALLOWED_REVIEWER_SCOPES.includes(
    scopeParam as ReviewQueueReviewerScope,
  )
    ? (scopeParam as ReviewQueueReviewerScope)
    : focusPreset &&
        (initialFilter === "overdue" || initialFilter === "escalated")
      ? FOCUS_PRESET_SCOPES[focusPreset]
      : "all";

  return (
    <ReviewQueuePage
      key={`${initialFilter}:${initialSortMode}:${initialReviewerScope}`}
      token={token}
      initialFilter={initialFilter}
      initialSortMode={initialSortMode}
      initialReviewerScope={initialReviewerScope}
    />
  );
}

export default function ReviewsPage() {
  return (
    <Suspense>
      <ReviewsContent />
    </Suspense>
  );
}
