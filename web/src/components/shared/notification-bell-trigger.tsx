"use client";

import type { ButtonHTMLAttributes } from "react";
import { Bell } from "lucide-react";
import { cn } from "@/lib/utils";

export function NotificationBellTrigger({
  unreadCount,
  className,
  "aria-controls": controlledId,
  "aria-expanded": expanded,
  ...props
}: {
  unreadCount: number;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      type="button"
      aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ""}`}
      aria-controls={expanded ? controlledId : undefined}
      aria-expanded={expanded}
      className={cn(
        "relative inline-flex h-11 w-11 items-center justify-center rounded-md text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
        className,
      )}
    >
      <Bell className="h-4.5 w-4.5" />
      {unreadCount > 0 && (
        <span className="absolute -right-0.5 -top-0.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-error-emphasis px-1 text-xs font-bold leading-none text-[var(--brand-paper)]">
          {unreadCount > 99 ? "99+" : unreadCount}
        </span>
      )}
    </button>
  );
}
