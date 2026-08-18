"use client";

import { Clock, Eye } from "lucide-react";
import { formatRelativeTime } from "@/components/report/share-analytics-helpers";

interface ShareAnalyticsStatsProps {
  viewCount: number;
  lastAccessedAt?: string | null;
  expiresAt?: string | null;
}

export function ShareAnalyticsStats({
  viewCount,
  lastAccessedAt,
  expiresAt,
}: ShareAnalyticsStatsProps) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-6 gap-y-3">
      <div className="flex min-w-[6rem] items-center gap-2">
        <Eye className="h-4 w-4 shrink-0 text-[var(--text-tertiary)]" />
        <div className="min-w-0">
          <p className="text-lg font-semibold tabular-nums text-[var(--text-primary)]">
            {viewCount}
          </p>
          <p className="text-xs text-[var(--text-tertiary)]">views</p>
        </div>
      </div>

      <div className="flex min-w-0 items-center gap-2">
        <Clock className="h-4 w-4 shrink-0 text-[var(--text-tertiary)]" />
        <div className="min-w-0">
          <p className="break-words text-sm text-[var(--text-secondary)]">
            {lastAccessedAt
              ? formatRelativeTime(lastAccessedAt)
              : "Never accessed"}
          </p>
          <p className="text-xs text-[var(--text-tertiary)]">last viewed</p>
        </div>
      </div>

      {expiresAt && (
        <div className="flex min-w-0 items-center gap-2">
          <Clock className="h-4 w-4 shrink-0 text-warning" />
          <div className="min-w-0">
            <p className="break-words text-sm text-warning">
              {formatRelativeTime(expiresAt)}
            </p>
            <p className="text-xs text-[var(--text-tertiary)]">expires</p>
          </div>
        </div>
      )}
    </div>
  );
}
