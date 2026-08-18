"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import { DEMO_ANALYSIS_ID } from "@/lib/demo-data";
import {
  assignDemoReviewQueueItem,
  escalateDemoReviewQueueItem,
  recordDemoReviewQueueComment,
  resolveDemoReviewQueueItem,
} from "@/lib/demo-review-queue";
import {
  authScopedQueryKey,
  invalidateAuthScopedQueries,
} from "@/lib/query-keys";
import type { CommentAssignmentHistory } from "@/components/report/comment-panel-types";

export interface Comment {
  id: string;
  user_id: string;
  body: string;
  target_type: string;
  target_id: string;
  parent_id: string | null;
  resolved: boolean;
  resolved_by?: string | null;
  resolved_at?: string | null;
  assigned_to?: string | null;
  assigned_by?: string | null;
  assigned_at?: string | null;
  assigned_reviewer_name?: string | null;
  assigned_reviewer_email?: string | null;
  assignment_event_count?: number;
  last_assignment_at?: string | null;
  escalation_status?: string;
  escalated_by?: string | null;
  escalated_at?: string | null;
  escalation_event_count?: number;
  last_escalation_at?: string | null;
  escalated_to_review?: boolean;
  created_at: string;
}

interface CommentReviewerApi {
  id: string;
  email: string;
  full_name: string;
  role: string;
}

export interface CommentReviewer extends CommentReviewerApi {
  label: string;
}

function reviewerLabel(reviewer: CommentReviewerApi) {
  const name = reviewer.full_name.trim();
  return name ? `${name} (${reviewer.email})` : reviewer.email;
}

function mapReviewer(reviewer: CommentReviewerApi): CommentReviewer {
  return {
    ...reviewer,
    label: reviewerLabel(reviewer),
  };
}

const DEMO_COMMENTS: Comment[] = [
  {
    id: "comment-demo-1",
    user_id: "user-demo-ada",
    body: "Claim 1 of US-DEMO-001 reads broadly on the core scaffold. Flagging for attorney review before we rely on the design-around.",
    target_type: "analysis",
    target_id: "",
    parent_id: null,
    resolved: false,
    assigned_to: "user-demo-grace",
    assigned_reviewer_name: "Grace Hopper",
    assigned_reviewer_email: "grace@example.com",
    escalation_status: "escalated",
    escalated_to_review: true,
    created_at: "2026-04-22T10:15:00.000Z",
  },
  {
    id: "comment-demo-2",
    user_id: "user-demo-grace",
    body: "Agreed. The dependent claims narrow it materially — I think the alternative salt form keeps us clear. Resolving once the report reflects that.",
    target_type: "analysis",
    target_id: "",
    parent_id: "comment-demo-1",
    resolved: false,
    created_at: "2026-04-22T11:02:00.000Z",
  },
];

const DEMO_REVIEWERS: CommentReviewer[] = [
  {
    id: "user-demo-ada",
    email: "ada@example.com",
    full_name: "Ada Lovelace",
    role: "attorney",
    label: "Ada Lovelace (ada@example.com)",
  },
  {
    id: "user-demo-grace",
    email: "grace@example.com",
    full_name: "Grace Hopper",
    role: "admin",
    label: "Grace Hopper (grace@example.com)",
  },
];

const DEMO_COMMENT_CLOCK_START_MS = Date.parse("2026-07-16T00:00:00.000Z");
const demoCommentsByAnalysis = new Map<string, Comment[]>();

function getDemoComments(analysisId: string): Comment[] {
  const existing = demoCommentsByAnalysis.get(analysisId);
  if (existing) return existing;

  const seeded =
    analysisId === DEMO_ANALYSIS_ID
      ? DEMO_COMMENTS.map((comment) => ({
          ...comment,
          target_id: analysisId,
        }))
      : [];
  demoCommentsByAnalysis.set(analysisId, seeded);
  return seeded;
}

function createDemoComment(data: CreateCommentInput): Comment {
  const comments = getDemoComments(data.analysis_id);
  const parent = data.parent_id
    ? comments.find((comment) => comment.id === data.parent_id)
    : undefined;
  if (data.parent_id && !parent) {
    throw new Error("Demo comment parent is unavailable");
  }

  const root = parent?.parent_id
    ? comments.find((comment) => comment.id === parent.parent_id)
    : parent;
  if (parent?.parent_id && !root) {
    throw new Error("Demo comment root is unavailable");
  }

  const localOrdinal =
    comments.filter((comment) =>
      comment.id.startsWith(`comment-demo-${data.analysis_id}-`),
    ).length + 1;
  const createdAt = new Date(
    DEMO_COMMENT_CLOCK_START_MS + localOrdinal * 1_000,
  ).toISOString();
  const comment: Comment = {
    id: `comment-demo-${data.analysis_id}-${localOrdinal}`,
    user_id: "user-demo-ada",
    body: data.body,
    target_type: data.target_type ?? "analysis",
    target_id: data.target_id ?? data.analysis_id,
    parent_id: data.parent_id ?? null,
    resolved: false,
    created_at: createdAt,
  };
  const nextComments = [...comments, comment];
  demoCommentsByAnalysis.set(data.analysis_id, nextComments);

  const rootComment = root ?? comment;
  const rootCommentId = rootComment.id;
  recordDemoReviewQueueComment({
    analysisId: data.analysis_id,
    commentCount: nextComments.filter(
      (item) => item.id === rootCommentId || item.parent_id === rootCommentId,
    ).length,
    createdAt,
    rootBody: rootComment.body,
    rootCommentId,
  });

  return comment;
}

export function resetDemoCommentsState() {
  demoCommentsByAnalysis.clear();
}

export interface CreateCommentInput {
  analysis_id: string;
  body: string;
  parent_id?: string;
  target_type?: string;
  target_id?: string;
}

export interface AssignCommentInput {
  analysis_id: string;
  comment_id: string;
  assigned_to: string | null;
}

export interface ResolveCommentInput {
  analysis_id: string;
  comment_id: string;
  resolved: boolean;
}

export interface EscalateCommentInput {
  analysis_id: string;
  comment_id: string;
  promote_to_under_review?: boolean;
  review_note?: string;
}

export function useComments(analysisId: string, token: string | null) {
  return useQuery({
    queryKey: authScopedQueryKey(["comments", analysisId] as const, token),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        // Seed the canonical demo analysis with a representative thread so the
        // Comments tab shows realistic collaboration in demo mode (token is
        // null there). Other demo analyses correctly show the empty state.
        return Promise.resolve(getDemoComments(analysisId));
      }
      return apiClient<Comment[]>(`/comments?analysis_id=${analysisId}`, {
        token: token || undefined,
        signal,
      });
    },
    enabled: !!analysisId && (DEMO_MODE_ENABLED || !!token),
  });
}

export function useCommentReviewers(analysisId: string, token: string | null) {
  return useQuery({
    queryKey: authScopedQueryKey(
      ["comments", analysisId, "reviewers"] as const,
      token,
    ),
    queryFn: async ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return DEMO_REVIEWERS;
      }

      const reviewers = await apiClient<CommentReviewerApi[]>(
        `/comments/reviewers?analysis_id=${analysisId}`,
        { token: token || undefined, signal },
      );
      return reviewers.map(mapReviewer);
    },
    enabled: !!analysisId && (DEMO_MODE_ENABLED || !!token),
  });
}

export function useCommentAssignmentHistory(
  commentId: string,
  token: string | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: authScopedQueryKey(
      ["comments", commentId, "assignment-history"] as const,
      token,
    ),
    queryFn: ({ signal }) =>
      apiClient<CommentAssignmentHistory>(
        `/comments/${commentId}/assignment-history`,
        {
          token: token || undefined,
          signal,
        },
      ),
    enabled: enabled && !!token && !!commentId,
  });
}

export function useCreateComment(token: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateCommentInput) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(createDemoComment(data));
      }

      return apiClient<{ id: string }>("/comments", {
        method: "POST",
        body: JSON.stringify(data),
        token: token || undefined,
      });
    },
    meta: { suppressGlobalErrorToast: true },
    onSuccess: (_, variables) => {
      if (DEMO_MODE_ENABLED) {
        queryClient.setQueryData<Comment[]>(
          authScopedQueryKey(
            ["comments", variables.analysis_id] as const,
            token,
          ),
          getDemoComments(variables.analysis_id),
        );
        invalidateAuthScopedQueries(queryClient, ["review-queue"], token);
        return;
      }

      invalidateAuthScopedQueries(
        queryClient,
        ["comments", variables.analysis_id],
        token,
      );
      // A new root comment (parent_id undefined) becomes an unresolved
      // review-queue row immediately on the server, and a reply increments the
      // thread's comment_count shown in the queue. The queue is rendered on a
      // separate surface (dashboard workload panel / reviews page) whose cache
      // would otherwise stay stale until an independent refetch, so invalidate
      // it here to match useAssignComment/useToggleCommentResolution/
      // useEscalateComment, which already do.
      invalidateAuthScopedQueries(queryClient, ["review-queue"], token);
    },
  });
}

export function useAssignComment(token: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: AssignCommentInput) => {
      if (DEMO_MODE_ENABLED) {
        assignDemoReviewQueueItem({
          commentId: data.comment_id,
          assignedTo: data.assigned_to,
        });
        return {
          id: data.comment_id,
          user_id: "user-demo",
          body: "",
          target_type: "analysis",
          target_id: "",
          parent_id: null,
          resolved: false,
          assigned_to: data.assigned_to,
          created_at: new Date().toISOString(),
        } satisfies Comment;
      }

      return apiClient<Comment>(`/comments/${data.comment_id}/assignment`, {
        method: "PATCH",
        body: JSON.stringify({ assigned_to: data.assigned_to }),
        token: token || undefined,
      });
    },
    meta: { suppressGlobalErrorToast: true },
    onSuccess: (_, variables) => {
      invalidateAuthScopedQueries(
        queryClient,
        ["comments", variables.analysis_id],
        token,
      );
      invalidateAuthScopedQueries(
        queryClient,
        ["comments", variables.comment_id, "assignment-history"],
        token,
      );
      invalidateAuthScopedQueries(queryClient, ["review-queue"], token);
    },
  });
}

export function useToggleCommentResolution(token: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: ResolveCommentInput) => {
      if (DEMO_MODE_ENABLED) {
        if (data.resolved) {
          resolveDemoReviewQueueItem(data.comment_id);
        }
        return {
          id: data.comment_id,
          user_id: "user-demo",
          body: "",
          target_type: "analysis",
          target_id: "",
          parent_id: null,
          resolved: data.resolved,
          created_at: new Date().toISOString(),
        } satisfies Comment;
      }

      return apiClient<Comment>(`/comments/${data.comment_id}/resolution`, {
        method: "PATCH",
        body: JSON.stringify({ resolved: data.resolved }),
        token: token || undefined,
      });
    },
    meta: { suppressGlobalErrorToast: true },
    onSuccess: (_, variables) => {
      invalidateAuthScopedQueries(
        queryClient,
        ["comments", variables.analysis_id],
        token,
      );
      invalidateAuthScopedQueries(queryClient, ["review-queue"], token);
    },
  });
}

export function useEscalateComment(token: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: EscalateCommentInput) => {
      if (DEMO_MODE_ENABLED) {
        escalateDemoReviewQueueItem(data.comment_id);
        return {
          id: data.comment_id,
          user_id: "user-demo",
          body: data.review_note ?? "",
          target_type: "analysis",
          target_id: "",
          parent_id: null,
          resolved: false,
          escalation_status: "escalated",
          escalated_to_review: data.promote_to_under_review ?? true,
          created_at: new Date().toISOString(),
        } satisfies Comment;
      }

      return apiClient<Comment>(`/comments/${data.comment_id}/escalation`, {
        method: "POST",
        body: JSON.stringify({
          promote_to_under_review: data.promote_to_under_review ?? true,
          review_note: data.review_note ?? "",
        }),
        token: token || undefined,
      });
    },
    meta: { suppressGlobalErrorToast: true },
    onSuccess: (_, variables) => {
      invalidateAuthScopedQueries(
        queryClient,
        ["comments", variables.analysis_id],
        token,
      );
      invalidateAuthScopedQueries(queryClient, ["review-queue"], token);
      invalidateAuthScopedQueries(
        queryClient,
        ["analyses", variables.analysis_id, "review-status"],
        token,
      );
    },
  });
}
