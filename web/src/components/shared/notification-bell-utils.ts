"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Download,
  Info,
  UserPlus,
} from "lucide-react";
import type { ElementType } from "react";
import type { NotificationType } from "@/hooks/use-notifications";

export const NOTIFICATION_ICON_BY_TYPE: Record<NotificationType, ElementType> =
  {
    analysis_complete: CheckCircle2,
    monitor_alert: AlertTriangle,
    export_ready: Download,
    team_invite: UserPlus,
    system: Info,
  };

export const NOTIFICATION_COLOR_BY_TYPE: Record<NotificationType, string> = {
  analysis_complete: "text-success",
  monitor_alert: "text-warning",
  export_ready: "text-brand-primary",
  team_invite: "text-brand-primary",
  system: "text-[var(--text-secondary)]",
};

export function relativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60_000);
  const diffHr = Math.floor(diffMs / 3_600_000);
  const diffDay = Math.floor(diffMs / 86_400_000);

  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay < 7) return `${diffDay}d ago`;
  return new Date(dateStr).toLocaleDateString();
}
