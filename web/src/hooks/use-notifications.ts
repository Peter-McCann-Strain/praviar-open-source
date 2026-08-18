"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import {
  authScopedQueryKey,
  invalidateAuthScopedQueries,
} from "@/lib/query-keys";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import { useToastStore } from "@/stores/toast-store";
import { logError } from "@/lib/error-logger";

// ── Types ──────────────────────────────────────────────────────────────────

export type NotificationType =
  | "analysis_complete"
  | "monitor_alert"
  | "export_ready"
  | "team_invite"
  | "system";

export type DigestFrequency = "off" | "weekly";

export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  body: string;
  read: boolean;
  data: Record<string, unknown>;
  created_at: string;
  actionable?: boolean;
  tombstoned?: boolean;
}

export interface NotificationListResponse {
  items: Notification[];
  unread_count: number;
  total: number;
}

export interface UnreadCountResponse {
  unread_count: number;
}

export interface NotificationActionResolution {
  notification_id: string;
  actionable: boolean;
  destination: string | null;
  marked_read: boolean;
}

export interface NotificationPreferences {
  email_on_analysis_complete: boolean;
  email_on_monitor_alert: boolean;
  email_digest_frequency: DigestFrequency;
}

const DEMO_NOTIFICATIONS: Notification[] = [
  {
    id: "demo-notification-review",
    type: "analysis_complete",
    title: "Review packet ready",
    body: "The succinic acid sample report is ready for counsel review.",
    read: false,
    data: { analysis_id: "demo-succinic-acid" },
    created_at: "2026-04-12T12:00:00.000Z",
  },
];

const DEMO_NOTIFICATION_PREFERENCES: NotificationPreferences = {
  email_on_analysis_complete: true,
  email_on_monitor_alert: true,
  email_digest_frequency: "weekly",
};

// ── Hooks ──────────────────────────────────────────────────────────────────

/** Fetch paginated notification list for the current user. */
export function useNotifications(token: string | null, page = 1, perPage = 20) {
  return useQuery({
    queryKey: authScopedQueryKey(
      ["notifications", page, perPage] as const,
      token,
    ),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve({
          items: DEMO_NOTIFICATIONS,
          unread_count: DEMO_NOTIFICATIONS.filter((item) => !item.read).length,
          total: DEMO_NOTIFICATIONS.length,
        });
      }
      const params = new URLSearchParams({
        page: String(page),
        per_page: String(perPage),
      });
      return apiClient<NotificationListResponse>(`/notifications?${params}`, {
        token: token || undefined,
        signal,
      });
    },
    enabled: DEMO_MODE_ENABLED || !!token,
  });
}

/** Poll unread notification count every 30 seconds (for the badge). */
export function useUnreadCount(token: string | null) {
  return useQuery({
    queryKey: authScopedQueryKey(
      ["notifications", "unread-count"] as const,
      token,
    ),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve({
          unread_count: DEMO_NOTIFICATIONS.filter((item) => !item.read).length,
        });
      }
      return apiClient<UnreadCountResponse>("/notifications/unread-count", {
        token: token || undefined,
        signal,
      });
    },
    enabled: DEMO_MODE_ENABLED || !!token,
    refetchInterval: 30_000,
    // Passive badge poll — a transient refetch failure must not raise an error
    // toast the user never triggered. The error is still logged centrally.
    meta: { suppressGlobalErrorToast: true },
  });
}

/** Mark specific notification IDs as read. */
export function useMarkRead(token: string | null) {
  const queryClient = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);

  return useMutation({
    mutationFn: (notificationIds: string[]) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve({ marked: notificationIds.length });
      }
      return apiClient<{ marked: number }>("/notifications/mark-read", {
        method: "POST",
        body: JSON.stringify({ notification_ids: notificationIds }),
        token: token || undefined,
      });
    },
    meta: { suppressGlobalErrorToast: true },
    onSuccess: () => {
      invalidateAuthScopedQueries(queryClient, ["notifications"], token);
    },
    onError: (err) => {
      logError(err, { source: "useMarkRead" });
      addToast(
        "Failed to mark notification read. Notification history is unchanged.",
        "error",
      );
    },
  });
}

/** Resolve a notification action against current server-side authority. */
export function useResolveNotificationAction(token: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (notification: Notification) => {
      if (DEMO_MODE_ENABLED) {
        let destination: string | null = null;
        if (
          (notification.type === "analysis_complete" ||
            notification.type === "export_ready") &&
          typeof notification.data.analysis_id === "string"
        ) {
          destination = `/analyses/${encodeURIComponent(notification.data.analysis_id)}/report`;
        } else if (notification.type === "monitor_alert") {
          destination = "/monitors";
        } else if (notification.type === "team_invite") {
          destination =
            notification.data.action === "manage_users"
              ? "/admin?tab=users"
              : "/dashboard";
        } else if (
          notification.type === "system" &&
          typeof notification.data.href === "string" &&
          notification.data.href.startsWith("/") &&
          !notification.data.href.startsWith("//")
        ) {
          destination = notification.data.href;
        }
        return Promise.resolve<NotificationActionResolution>({
          notification_id: notification.id,
          actionable: destination !== null,
          destination,
          marked_read: destination !== null && !notification.read,
        });
      }
      if (!token) {
        throw new Error(
          "Authenticated notification action resolution requires a token.",
        );
      }
      return apiClient<NotificationActionResolution>(
        `/notifications/${encodeURIComponent(notification.id)}/resolve-action`,
        {
          method: "POST",
          token,
        },
      );
    },
    meta: { suppressGlobalErrorToast: true },
    onSuccess: () => {
      invalidateAuthScopedQueries(queryClient, ["notifications"], token);
    },
  });
}

/** Mark all notifications as read. */
export function useDismissAll(token: string | null) {
  const queryClient = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);

  return useMutation({
    mutationFn: () => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve({ marked: DEMO_NOTIFICATIONS.length });
      }
      return apiClient<{ marked: number }>("/notifications/dismiss-all", {
        method: "POST",
        token: token || undefined,
      });
    },
    meta: { suppressGlobalErrorToast: true },
    onSuccess: () => {
      invalidateAuthScopedQueries(queryClient, ["notifications"], token);
    },
    onError: (err) => {
      logError(err, { source: "useDismissAll" });
      addToast(
        "Failed to dismiss notifications. Notification history is unchanged.",
        "error",
      );
    },
  });
}

/** Fetch email notification preferences. */
export function useNotificationPreferences(token: string | null) {
  return useQuery({
    queryKey: authScopedQueryKey(
      ["notifications", "preferences"] as const,
      token,
    ),
    queryFn: ({ signal }) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(DEMO_NOTIFICATION_PREFERENCES);
      }
      return apiClient<NotificationPreferences>("/notifications/preferences", {
        token: token || undefined,
        signal,
      });
    },
    enabled: DEMO_MODE_ENABLED || !!token,
  });
}

/** Update email notification preferences. */
export function useUpdateNotificationPreferences(token: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    meta: { suppressGlobalErrorToast: true },
    mutationFn: (prefs: NotificationPreferences) => {
      if (DEMO_MODE_ENABLED) {
        return Promise.resolve(prefs);
      }
      return apiClient<NotificationPreferences>("/notifications/preferences", {
        method: "PUT",
        body: JSON.stringify(prefs),
        token: token || undefined,
      });
    },
    onSuccess: () => {
      invalidateAuthScopedQueries(
        queryClient,
        ["notifications", "preferences"],
        token,
      );
    },
  });
}
