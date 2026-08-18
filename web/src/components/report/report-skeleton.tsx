"use client";

import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import { Skeleton, SkeletonText } from "@/components/ui/skeleton";

/**
 * Responsive preview of the report workspace while the final packet is being
 * assembled during pipeline execution.
 */
export function ReportSkeleton() {
  return (
    <div
      className="praviar-report-workspace w-full min-w-0 space-y-4 overflow-hidden"
      data-praviar-report-preview-skeleton
    >
      <div className="praviar-report-decision-field overflow-hidden rounded-lg p-4 sm:p-5">
        <div className="flex min-w-0 flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <PraviarMarkFrame size="sm" />
            <div className="min-w-0 flex-1 space-y-2">
              <Skeleton className="h-3 w-24 max-w-full" />
              <Skeleton className="h-5 w-full max-w-64" />
              <Skeleton className="h-3 w-full max-w-80" />
            </div>
          </div>
          <div className="grid min-w-0 grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:justify-end">
            <Skeleton className="h-8 min-w-0 rounded-lg sm:w-24" />
            <Skeleton className="h-8 min-w-0 rounded-lg sm:w-24" />
          </div>
        </div>

        <div className="mt-4 grid min-w-0 gap-2 sm:grid-cols-4">
          {[92, 76, 84, 68].map((width) => (
            <div
              key={width}
              className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 p-3"
            >
              <Skeleton className="h-2.5 w-16 max-w-full" />
              <Skeleton
                className="mt-2 h-5 max-w-full"
                style={{ width: `${width}%` }}
              />
            </div>
          ))}
        </div>
      </div>

      <div className="flex min-w-0 gap-1 overflow-hidden rounded-lg border border-[var(--border-default)] bg-[var(--surface-glass)] p-1">
        {["Outcome", "Patents", "Claims", "Validity"].map((tab) => (
          <Skeleton
            key={tab}
            className="h-10 min-w-0 flex-1 rounded-lg"
            aria-label={`${tab} loading tab`}
          />
        ))}
        <Skeleton className="h-10 w-20 shrink-0 rounded-lg" />
      </div>

      <div className="grid min-w-0 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(16rem,0.42fr)]">
        <div className="space-y-4">
          <div className="praviar-surface-premium rounded-lg p-4 sm:p-5">
            <Skeleton className="h-5 w-full max-w-44" />
            <SkeletonText lines={4} className="mt-4" />
          </div>
          <div className="praviar-surface-premium space-y-3 rounded-lg p-4 sm:p-5">
            <Skeleton className="h-5 w-full max-w-36" />
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="grid min-w-0 gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/40 p-3 sm:grid-cols-[minmax(0,1fr)_5rem]"
              >
                <div className="min-w-0 space-y-2">
                  <Skeleton className="h-4 w-full max-w-72" />
                  <Skeleton className="h-3 w-full max-w-96" />
                </div>
                <Skeleton className="h-7 w-full rounded-full" />
              </div>
            ))}
          </div>
        </div>

        <div className="grid min-w-0 gap-3 sm:grid-cols-3 lg:grid-cols-1">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="praviar-surface-premium space-y-3 rounded-lg p-4"
            >
              <Skeleton className="h-3 w-full max-w-24" />
              <Skeleton className="h-8 w-full max-w-20" />
              <Skeleton className="h-2 w-full rounded-full" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
