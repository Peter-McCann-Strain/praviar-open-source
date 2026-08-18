"use client";

import { AnimatedCounter } from "@/components/shared/animated-counter";
import {
  StaggerContainer,
  StaggerItem,
} from "@/components/shared/stagger-container";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  AdminRefreshWarning,
  AdminStatusState,
} from "@/components/admin-dashboard/helpers";
import { useAdminMetrics } from "@/hooks/use-admin";
import { useErrorDiagnostic } from "@/hooks/use-error-diagnostic";
import { isAuthBoundaryError } from "@/lib/api-client";

function reportPlatformMetricsAccessRestriction() {
  console.error("[MetricsTab] Platform metrics access restricted");
}

function reportPlatformMetricsLoadFailure() {
  console.error("[MetricsTab] Failed to load platform metrics");
}

export function MetricsTab() {
  const { data: metrics, isLoading, error, refetch } = useAdminMetrics();
  const accessRestricted = isAuthBoundaryError(error);
  const initialLoading = isLoading && !metrics;
  const metricsLoadFailed = Boolean(
    !initialLoading && error && !metrics && !accessRestricted,
  );

  useErrorDiagnostic(
    !initialLoading && accessRestricted,
    error,
    reportPlatformMetricsAccessRestriction,
  );
  useErrorDiagnostic(
    metricsLoadFailed,
    error,
    reportPlatformMetricsLoadFailure,
  );

  if (initialLoading) {
    return <AdminStatusState surface="metrics" variant="loading" />;
  }

  if (accessRestricted) {
    return (
      <AdminStatusState
        surface="metrics"
        variant="restricted"
        onRetry={() => {
          void refetch();
        }}
      />
    );
  }

  if (error && !metrics) {
    return (
      <AdminStatusState
        surface="metrics"
        variant="temporary"
        onRetry={() => {
          void refetch();
        }}
      />
    );
  }

  if (!metrics) return <AdminStatusState surface="metrics" variant="auth" />;

  return (
    <div className="space-y-6">
      {error ? <AdminRefreshWarning label="Platform metrics" /> : null}
      <StaggerContainer className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StaggerItem>
          <Card>
            <CardContent className="p-5">
              <p className="text-xs text-[var(--text-secondary)]">
                Total Analyses
              </p>
              <p className="type-heading-xl text-[var(--text-primary)] tabular-nums">
                <AnimatedCounter value={metrics.total_analyses} />
              </p>
            </CardContent>
          </Card>
        </StaggerItem>
        <StaggerItem>
          <Card>
            <CardContent className="p-5">
              <p className="text-xs text-[var(--text-secondary)]">Total Cost</p>
              <p className="type-heading-xl text-[var(--text-primary)] tabular-nums">
                <AnimatedCounter
                  value={metrics.total_cost}
                  prefix="$"
                  decimals={2}
                />
              </p>
            </CardContent>
          </Card>
        </StaggerItem>
        <StaggerItem>
          <Card>
            <CardContent className="p-5">
              <p className="text-xs text-[var(--text-secondary)]">
                Avg Duration
              </p>
              <p className="type-heading-xl text-[var(--text-primary)] tabular-nums">
                {metrics.avg_duration_seconds != null ? (
                  <AnimatedCounter
                    value={metrics.avg_duration_seconds}
                    suffix="s"
                    decimals={1}
                  />
                ) : (
                  "--"
                )}
              </p>
            </CardContent>
          </Card>
        </StaggerItem>
        <StaggerItem>
          <Card>
            <CardContent className="p-5">
              <p className="text-xs text-[var(--text-secondary)]">Error Rate</p>
              <p className="type-heading-xl text-[var(--text-primary)] tabular-nums">
                <AnimatedCounter
                  value={metrics.error_rate * 100}
                  suffix="%"
                  decimals={1}
                />
              </p>
            </CardContent>
          </Card>
        </StaggerItem>
      </StaggerContainer>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Daily Activity</CardTitle>
        </CardHeader>
        <CardContent>
          {metrics.daily.length === 0 ? (
            <p className="py-8 text-center text-sm text-[var(--text-tertiary)]">
              No daily data yet
            </p>
          ) : (
            <div
              aria-label="Admin platform daily activity table"
              className="overflow-x-auto [scrollbar-gutter:stable] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
              role="region"
              tabIndex={0}
            >
              <table className="min-w-[36rem] w-full text-sm">
                <caption className="sr-only">
                  Admin platform daily activity table with date, analysis count,
                  cost, and error count.
                </caption>
                <thead>
                  <tr className="border-b border-[var(--border-subtle)]">
                    <th
                      scope="col"
                      className="px-4 py-2 text-left type-label-sm font-medium text-[var(--text-tertiary)]"
                    >
                      Date
                    </th>
                    <th
                      scope="col"
                      className="px-4 py-2 text-right type-label-sm font-medium text-[var(--text-tertiary)]"
                    >
                      Analyses
                    </th>
                    <th
                      scope="col"
                      className="px-4 py-2 text-right type-label-sm font-medium text-[var(--text-tertiary)]"
                    >
                      Cost
                    </th>
                    <th
                      scope="col"
                      className="px-4 py-2 text-right type-label-sm font-medium text-[var(--text-tertiary)]"
                    >
                      Errors
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-subtle)]">
                  {metrics.daily.slice(-14).map((day) => (
                    <tr
                      key={day.date}
                      className="transition-colors hover:bg-[var(--surface-subtle)]"
                    >
                      <td className="px-4 py-2 text-sm text-[var(--text-primary)]">
                        <span>{day.date}</span>
                      </td>
                      <td className="px-4 py-2 text-right text-sm tabular-nums text-[var(--text-primary)]">
                        <span>{day.count}</span>
                      </td>
                      <td className="px-4 py-2 text-right text-sm tabular-nums text-[var(--text-primary)]">
                        <span>${day.cost.toFixed(2)}</span>
                      </td>
                      <td className="px-4 py-2 text-right text-sm tabular-nums">
                        <span
                          className={
                            day.errors > 0
                              ? "text-error"
                              : "text-[var(--text-tertiary)]"
                          }
                        >
                          {day.errors}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
