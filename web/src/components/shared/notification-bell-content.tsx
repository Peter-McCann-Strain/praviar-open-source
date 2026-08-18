"use client";

import * as Popover from "@radix-ui/react-popover";
import { Check, TriangleAlert } from "lucide-react";
import { useId } from "react";
import type { Notification } from "@/hooks/use-notifications";
import { NotificationBellEmptyState } from "./notification-bell-empty-state";
import { NotificationBellItem } from "./notification-bell-item";

export function NotificationBellContent({
  notifications,
  unreadCount,
  isLoading,
  hasError,
  resolvingNotificationId,
  notificationActionPending,
  dismissAllPending,
  onDismissAll,
  onClickItem,
  onOpenSettings,
  onRetry,
}: {
  notifications: Notification[];
  unreadCount: number;
  isLoading: boolean;
  hasError: boolean;
  resolvingNotificationId: string | null;
  notificationActionPending: boolean;
  dismissAllPending: boolean;
  onDismissAll: () => void;
  onClickItem: (notification: Notification) => void;
  onOpenSettings: () => void;
  onRetry: () => void;
}) {
  const titleId = useId();

  return (
    <Popover.Portal>
      <Popover.Content
        align="end"
        aria-labelledby={titleId}
        collisionPadding={8}
        sideOffset={8}
        className="praviar-dialog-panel z-50 max-h-[calc(100dvh-1rem)] w-[calc(100vw-1rem)] max-w-[380px] overflow-hidden rounded-lg animate-in fade-in-0 zoom-in-95 slide-in-from-top-2 duration-200 motion-reduce:animate-none motion-reduce:transition-none sm:w-[380px]"
      >
        <div className="flex items-center justify-between border-b border-[var(--border-default)] px-4 py-3">
          <h3
            id={titleId}
            className="text-sm font-semibold text-[var(--text-primary)]"
          >
            Notifications
          </h3>
          {unreadCount > 0 && (
            <button
              type="button"
              onClick={onDismissAll}
              disabled={dismissAllPending || notificationActionPending}
              className="inline-flex min-h-11 items-center gap-1 rounded-md px-2 text-xs text-brand-primary transition-colors hover:bg-brand-primary/10 hover:text-brand-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 disabled:opacity-50"
            >
              <Check className="h-3 w-3" aria-hidden="true" />
              Mark all read
            </button>
          )}
        </div>

        <div className="max-h-[calc(100dvh-10rem)] divide-y divide-[var(--border-default)] overflow-y-auto sm:max-h-[380px]">
          {isLoading ? (
            <div
              role="status"
              aria-label="Loading notifications"
              className="flex items-center justify-center py-10"
            >
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-[var(--text-disabled)] border-t-brand-primary motion-reduce:animate-none" />
            </div>
          ) : hasError ? (
            <div
              role="alert"
              className="space-y-3 px-4 py-6 text-center"
              data-testid="notification-load-error"
            >
              <TriangleAlert
                className="mx-auto h-5 w-5 text-warning"
                aria-hidden="true"
              />
              <div>
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  Notifications unavailable
                </p>
                <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                  Praviar could not load a current, authorized notification
                  list. No empty state was inferred.
                </p>
              </div>
              <button
                type="button"
                onClick={onRetry}
                className="min-h-11 rounded-md border border-[var(--border-emphasis)] px-3 text-xs font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
              >
                Retry notifications
              </button>
            </div>
          ) : notifications.length === 0 ? (
            <NotificationBellEmptyState />
          ) : (
            notifications.map((notification) => (
              <NotificationBellItem
                key={notification.id}
                notification={notification}
                isResolving={resolvingNotificationId === notification.id}
                actionsDisabled={resolvingNotificationId !== null}
                onClickItem={onClickItem}
              />
            ))
          )}
        </div>

        <div className="border-t border-[var(--border-default)] px-4 py-2.5">
          <button
            type="button"
            onClick={onOpenSettings}
            disabled={notificationActionPending}
            className="min-h-11 w-full rounded-md text-center text-xs text-[var(--text-tertiary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 disabled:cursor-wait disabled:opacity-60"
          >
            Notification Settings
          </button>
        </div>
      </Popover.Content>
    </Popover.Portal>
  );
}
