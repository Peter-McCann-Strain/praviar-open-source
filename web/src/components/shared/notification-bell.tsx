"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import * as Popover from "@radix-ui/react-popover";
import { useAuthToken } from "@/hooks/use-auth-token";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";
import {
  useNotifications,
  useUnreadCount,
  useDismissAll,
  useResolveNotificationAction,
  type Notification,
} from "@/hooks/use-notifications";
import { useToastStore } from "@/stores/toast-store";
import { NotificationBellContent } from "./notification-bell-content";
import { NotificationBellTrigger } from "./notification-bell-trigger";

// ── Main component ─────────────────────────────────────────────────────────

export function NotificationBell() {
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const router = useRouter();
  const addToast = useToastStore((state) => state.addToast);
  const [open, setOpen] = useState(false);
  const actionLockRef = useRef(false);

  const { data: unreadData } = useUnreadCount(token);
  const notificationsQuery = useNotifications(token, 1, 15);
  const resolveAction = useResolveNotificationAction(token);
  const dismissAll = useDismissAll(token);

  const unreadCount =
    unreadData?.unread_count ?? notificationsQuery.data?.unread_count ?? 0;
  const notifications = notificationsQuery.data?.items ?? [];

  const handleClickItem = useCallback(
    (notification: Notification) => {
      if (actionLockRef.current || resolveAction.isPending) {
        return;
      }
      const authorityUnavailable =
        principal.isError || principal.isRefetchError || !principal.data;
      if (authorityUnavailable) {
        addToast(
          "Notification access check unavailable. Retry after role authority refreshes.",
          "warning",
        );
        return;
      }
      actionLockRef.current = true;
      resolveAction.mutate(notification, {
        onSuccess: (resolution) => {
          if (!resolution.actionable || !resolution.destination) {
            addToast(
              "This notification has no current action. No destination was opened.",
              "info",
            );
            return;
          }
          setOpen(false);
          router.push(resolution.destination);
        },
        onError: () => {
          addToast(
            "Access to this notification changed or could not be re-verified. No restricted destination was opened.",
            "warning",
          );
        },
        onSettled: () => {
          actionLockRef.current = false;
        },
      });
    },
    [
      addToast,
      principal.data,
      principal.isError,
      principal.isRefetchError,
      resolveAction,
      router,
    ],
  );

  const handleDismissAll = useCallback(() => {
    dismissAll.mutate();
  }, [dismissAll]);

  const handleOpenSettings = useCallback(() => {
    if (actionLockRef.current || resolveAction.isPending) {
      return;
    }
    setOpen(false);
    router.push("/settings/notifications");
  }, [resolveAction.isPending, router]);

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <NotificationBellTrigger unreadCount={unreadCount} />
      </Popover.Trigger>

      <NotificationBellContent
        notifications={notifications}
        unreadCount={unreadCount}
        isLoading={notificationsQuery.isLoading}
        hasError={Boolean(notificationsQuery.error)}
        resolvingNotificationId={
          resolveAction.isPending ? (resolveAction.variables?.id ?? null) : null
        }
        notificationActionPending={resolveAction.isPending}
        dismissAllPending={dismissAll.isPending}
        onDismissAll={handleDismissAll}
        onClickItem={handleClickItem}
        onOpenSettings={handleOpenSettings}
        onRetry={() => {
          void notificationsQuery.refetch();
        }}
      />
    </Popover.Root>
  );
}
