"use client";

import { useQuery } from "@tanstack/react-query";
import type { RiskLevel } from "@praviar/shared-types";
import { apiClient, isAuthBoundaryError } from "@/lib/api-client";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import { buildDemoReviewQueue } from "@/lib/demo-review-queue";
import { authScopedQueryKey } from "@/lib/query-keys";

export type ReviewQueueFilter = "mine" | "unassigned" | "overdue" | "escalated";

interface ReviewQueueCountsApi {
  open_total: number;
  mine: number;
  assigned: number;
  unassigned: number;
  overdue: number;
  escalated: number;
}

interface ReviewQueueItemApi {
  id: string;
  analysis_id: string;
  compound_name: string;
  analysis_status: "pending" | "running" | "completed" | "failed" | "cancelled";
  overall_risk: RiskLevel | null;
  body: string;
  assigned_to?: string | null;
  assigned_reviewer_name?: string | null;
  assigned_reviewer_email?: string | null;
  queue_age_hours?: number | null;
  reply_count?: number | null;
  is_mine?: boolean | null;
  is_overdue?: boolean | null;
  escalation_event_count?: number | null;
  escalated_at?: string | null;
  last_assignment_at?: string | null;
  last_escalation_at?: string | null;
  created_at: string;
}

interface ReviewQueueResponseApi {
  counts: ReviewQueueCountsApi;
  items: ReviewQueueItemApi[];
}

export interface ReviewQueueCounts {
  total: number;
  mine: number;
  unassigned: number;
  overdue: number;
  escalated: number;
}

export interface ReviewQueueItem {
  id: string;
  analysis_id: string;
  compound_name: string;
  analysis_status: "pending" | "running" | "completed" | "failed" | "cancelled";
  overall_risk: RiskLevel | null;
  comment_body: string;
  assigned_to_id?: string | null;
  assigned_to_name: string | null;
  assigned_to_email: string | null;
  queue_age_hours: number | null;
  is_mine: boolean;
  is_unassigned: boolean;
  is_overdue: boolean;
  overdue_label: string | null;
  is_escalated: boolean;
  escalated_at: string | null;
  last_activity_at: string;
  updated_at: string;
  comment_count: number;
}

export interface ReviewQueueResponse {
  counts: ReviewQueueCounts;
  items: ReviewQueueItem[];
  updated_at: string | null;
}

export interface ReviewQueueForbidden {
  forbidden: true;
}

export type ReviewQueueResult = ReviewQueueResponse | ReviewQueueForbidden;

function buildOverdueLabel(
  queueAgeHours: number | null | undefined,
): string | null {
  if (!queueAgeHours || queueAgeHours <= 0) {
    return null;
  }

  if (queueAgeHours >= 48) {
    return `Overdue · ${Math.floor(queueAgeHours / 24)}d open`;
  }
  return `Overdue · ${queueAgeHours}h open`;
}

function getNewestQueueTimestamp(
  ...timestamps: Array<string | null | undefined>
) {
  const validTimestamps = timestamps.filter((timestamp): timestamp is string =>
    Boolean(timestamp && !Number.isNaN(Date.parse(timestamp))),
  );

  if (validTimestamps.length === 0) {
    return new Date(0).toISOString();
  }

  return validTimestamps.reduce((newest, timestamp) =>
    Date.parse(timestamp) > Date.parse(newest) ? timestamp : newest,
  );
}

function mapQueueResponse(
  response: ReviewQueueResponseApi,
): ReviewQueueResponse {
  const items = response.items.map((item) => {
    const isUnassigned = !item.assigned_to;
    const isEscalated =
      (item.escalation_event_count ?? 0) > 0 || Boolean(item.escalated_at);
    const lastActivityAt = getNewestQueueTimestamp(
      item.last_escalation_at,
      item.last_assignment_at,
      item.escalated_at,
      item.created_at,
    );

    return {
      id: item.id,
      analysis_id: item.analysis_id,
      compound_name: item.compound_name,
      analysis_status: item.analysis_status,
      overall_risk: item.overall_risk,
      comment_body: item.body,
      assigned_to_id: item.assigned_to ?? null,
      assigned_to_name: item.assigned_reviewer_name ?? null,
      assigned_to_email: item.assigned_reviewer_email ?? null,
      queue_age_hours: item.queue_age_hours ?? null,
      is_mine: item.is_mine ?? false,
      is_unassigned: isUnassigned,
      is_overdue: Boolean(item.is_overdue),
      overdue_label: Boolean(item.is_overdue)
        ? buildOverdueLabel(item.queue_age_hours)
        : null,
      is_escalated: isEscalated,
      escalated_at: item.escalated_at ?? null,
      last_activity_at: lastActivityAt,
      updated_at: lastActivityAt,
      comment_count: (item.reply_count ?? 0) + 1,
    } satisfies ReviewQueueItem;
  });
  const newestActivity = items.reduce<string | null>((currentNewest, item) => {
    if (!currentNewest) {
      return item.updated_at;
    }

    return Date.parse(item.updated_at) > Date.parse(currentNewest)
      ? item.updated_at
      : currentNewest;
  }, null);

  return {
    counts: {
      total: response.counts.open_total,
      mine: response.counts.mine,
      unassigned: response.counts.unassigned,
      overdue: response.counts.overdue,
      escalated: response.counts.escalated,
    },
    items,
    updated_at: newestActivity,
  };
}

export function useReviewQueue(
  token: string | null,
  filter: ReviewQueueFilter,
) {
  return useQuery<ReviewQueueResult>({
    queryKey: authScopedQueryKey(["review-queue", filter] as const, token),
    queryFn: async ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return buildDemoReviewQueue(filter);
      }

      try {
        const response = await apiClient<ReviewQueueResponseApi>(
          `/comments/review-queue?filter=${filter}`,
          {
            token: token || undefined,
            signal,
          },
        );
        return mapQueueResponse(response);
      } catch (error) {
        if (isAuthBoundaryError(error)) {
          return { forbidden: true };
        }
        throw error;
      }
    },
    enabled: DEMO_MODE_ENABLED || !!token,
  });
}
