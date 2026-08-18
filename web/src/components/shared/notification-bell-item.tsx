"use client";

import { Info, LoaderCircle, LockKeyhole } from "lucide-react";
import type { Notification } from "@/hooks/use-notifications";
import { cn } from "@/lib/utils";
import { useHydrationSafeRelativeTime } from "@/hooks/use-hydration-safe-relative-time";
import {
  NOTIFICATION_COLOR_BY_TYPE,
  NOTIFICATION_ICON_BY_TYPE,
  relativeTime,
} from "./notification-bell-utils";

export function NotificationBellItem({
  notification,
  onClickItem,
  isResolving = false,
  actionsDisabled = false,
}: {
  notification: Notification;
  onClickItem: (notification: Notification) => void;
  isResolving?: boolean;
  actionsDisabled?: boolean;
}) {
  const formatRelativeTime = useHydrationSafeRelativeTime(relativeTime);
  const isActionable =
    notification.actionable !== false && !notification.tombstoned;
  const Icon = notification.tombstoned
    ? LockKeyhole
    : (NOTIFICATION_ICON_BY_TYPE[notification.type] ?? Info);
  const colorClass = notification.tombstoned
    ? "text-[var(--text-disabled)]"
    : (NOTIFICATION_COLOR_BY_TYPE[notification.type] ??
      "text-[var(--text-secondary)]");

  const content = (
    <>
      <div className={cn("mt-0.5 flex-shrink-0", colorClass)}>
        {isResolving ? (
          <LoaderCircle
            className="h-4 w-4 animate-spin motion-reduce:animate-none"
            aria-hidden="true"
          />
        ) : (
          <Icon className="h-4 w-4" aria-hidden="true" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p
            className={cn(
              "truncate text-sm",
              notification.read
                ? "text-[var(--text-secondary)]"
                : "font-medium text-[var(--text-primary)]",
            )}
          >
            {notification.title}
          </p>
          {!notification.read && (
            <span
              className="h-2 w-2 flex-shrink-0 rounded-full bg-brand-primary"
              aria-hidden="true"
            />
          )}
        </div>
        <p className="mt-0.5 line-clamp-2 text-xs leading-5 text-[var(--text-tertiary)]">
          {notification.body}
        </p>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-[var(--text-disabled)]">
          <span>{formatRelativeTime(notification.created_at)}</span>
          {!isActionable ? (
            <span className="rounded-full bg-[var(--surface-muted)] px-2 py-0.5 text-[var(--text-tertiary)]">
              {notification.tombstoned ? "Access changed" : "No action"}
            </span>
          ) : null}
        </div>
        {!notification.read ? (
          <span className="sr-only">Unread notification</span>
        ) : null}
      </div>
    </>
  );

  if (!isActionable) {
    return (
      <div
        className={cn(
          "flex min-h-16 w-full items-start gap-3 px-4 py-3 text-left",
          !notification.read && "bg-[var(--surface-active)]/50",
        )}
      >
        {content}
      </div>
    );
  }

  return (
    <button
      type="button"
      disabled={actionsDisabled}
      onClick={() => onClickItem(notification)}
      className={cn(
        "flex min-h-16 w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-[var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-primary/70 disabled:cursor-wait disabled:opacity-70",
        !notification.read && "bg-[var(--surface-active)]/50",
      )}
    >
      {content}
    </button>
  );
}
