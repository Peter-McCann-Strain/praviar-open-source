"use client";

import { Badge } from "@/components/ui/badge";
import { groupRejectedByReason } from "@/components/report/funnel-explorer-table-helpers";
import type { SearchFunnelEntry } from "@/components/report/funnel-explorer-helpers";

export function HardFilterTable({ entries }: { entries: SearchFunnelEntry[] }) {
  const rejected = entries.filter(
    (entry) => !entry.passed_hard_filter && entry.filter_reason,
  );
  const byReason = groupRejectedByReason(entries);

  return (
    <div className="space-y-2">
      <p className="text-xs text-[var(--text-secondary)]">
        {rejected.length} patents removed by hard filters
      </p>
      {Array.from(byReason.entries()).map(([reason, patents]) => (
        <div
          key={reason}
          className="min-w-0 rounded-lg border border-[var(--border-default)] p-3"
        >
          <div className="flex min-w-0 items-center justify-between gap-3">
            <span className="min-w-0 break-words text-xs font-medium capitalize text-[var(--text-primary)] [overflow-wrap:anywhere]">
              {reason.replace(/_/g, " ")}
            </span>
            <Badge variant="secondary" className="shrink-0 text-xs">
              {patents.length}
            </Badge>
          </div>
          <div className="mt-2 flex min-w-0 flex-wrap gap-1">
            {patents.slice(0, 10).map((patent) => (
              <span
                key={patent.patent_id}
                className="max-w-full break-all text-xs font-mono text-[var(--text-tertiary)] [overflow-wrap:anywhere]"
              >
                {patent.patent_id}
              </span>
            ))}
            {patents.length > 10 ? (
              <span className="text-xs text-[var(--text-disabled)]">
                +{patents.length - 10} more
              </span>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}
