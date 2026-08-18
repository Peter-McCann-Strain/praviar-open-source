import { Calendar } from "lucide-react";
import type { UsageAnalyticsResponse } from "@/hooks/use-admin-analytics";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  formatCurrency,
  formatDuration,
} from "@/components/admin-analytics/helpers";
import { AnalyticsPanelStatus } from "@/components/admin-analytics/status-state";

interface UsageTabProps {
  usageData: UsageAnalyticsResponse | undefined;
  usageLoading: boolean;
  usageError?: unknown;
  onRetry: () => void;
}

export function UsageTab({
  usageData,
  usageLoading,
  usageError,
  onRetry,
}: UsageTabProps) {
  if (usageError && !usageData) {
    return (
      <AnalyticsPanelStatus
        title="Usage telemetry unavailable"
        description="Usage breakdowns could not be loaded. Existing analyses and organization controls are unchanged."
        onRetry={onRetry}
      />
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle aria-level={2} className="text-sm">
            Top Organizations by Usage
          </CardTitle>
        </CardHeader>
        <CardContent>
          {usageLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <div
                  key={i}
                  className="skeleton-shimmer h-10 rounded-md bg-[var(--skeleton-base)]"
                />
              ))}
            </div>
          ) : (
            <div className="space-y-2">
              {(usageData?.org_usage ?? []).map((org, i) => (
                <div
                  key={org.org_id}
                  className="flex flex-col gap-2 rounded-lg px-3 py-3 transition-colors hover:bg-[var(--surface-hover)] sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="w-5 text-xs font-mono text-[var(--text-tertiary)]">
                      {i + 1}.
                    </span>
                    <span className="truncate text-sm text-[var(--text-primary)]">
                      {org.org_name || "Unknown"}
                    </span>
                  </div>
                  <div className="flex flex-shrink-0 flex-wrap items-center gap-2 sm:gap-4">
                    <span className="text-xs text-[var(--text-secondary)] tabular-nums">
                      {org.analysis_count} analyses
                    </span>
                    <Badge variant="secondary">
                      {formatCurrency(org.total_cost_usd)}
                    </Badge>
                  </div>
                </div>
              ))}
              {(usageData?.org_usage ?? []).length === 0 && (
                <p className="py-8 text-center text-sm text-[var(--text-tertiary)]">
                  No usage data for this period
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle aria-level={2} className="text-sm">
              Analysis Status Breakdown
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              {(usageData?.status_breakdown ?? []).map((s) => (
                <div
                  key={s.status}
                  className="flex items-center gap-2 rounded-lg border border-[var(--border-default)] px-3 py-2"
                >
                  <span className="text-sm capitalize text-[var(--text-secondary)]">
                    {s.status}
                  </span>
                  <Badge
                    variant={
                      s.status === "completed"
                        ? "success"
                        : s.status === "failed"
                          ? "destructive"
                          : s.status === "running"
                            ? "default"
                            : "secondary"
                    }
                  >
                    {s.count}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle aria-level={2} className="text-sm">
              Top Compounds
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {(usageData?.top_compounds ?? []).map((c, i) => (
                <div
                  key={c.compound_name}
                  className="flex items-center justify-between gap-3 py-1.5"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="w-5 text-xs font-mono text-[var(--text-tertiary)]">
                      {i + 1}.
                    </span>
                    <span className="min-w-0 break-words text-sm text-[var(--text-primary)] sm:truncate">
                      {c.compound_name}
                    </span>
                  </div>
                  <Badge variant="secondary">{c.analysis_count}x</Badge>
                </div>
              ))}
              {(usageData?.top_compounds ?? []).length === 0 && (
                <p className="py-4 text-center text-sm text-[var(--text-tertiary)]">
                  No compound data
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-[var(--text-secondary)]">
                  Avg Pipeline Duration
                </p>
                <p className="type-heading-lg mt-1 text-[var(--text-primary)] tabular-nums">
                  {usageLoading
                    ? "--"
                    : formatDuration(usageData?.avg_duration_seconds ?? null)}
                </p>
              </div>
              <Calendar className="h-8 w-8 text-[var(--text-disabled)]" />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
