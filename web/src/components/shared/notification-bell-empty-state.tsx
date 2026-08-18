"use client";

import { Bell } from "lucide-react";

export function NotificationBellEmptyState() {
  return (
    <div className="flex flex-col items-center justify-center px-4 py-10">
      <Bell className="mb-3 h-8 w-8 text-[var(--text-disabled)]" />
      <p className="text-sm font-medium text-[var(--text-secondary)]">
        No notifications
      </p>
      <p className="mt-1 text-xs text-[var(--text-tertiary)]">
        You&apos;re all caught up!
      </p>
    </div>
  );
}
