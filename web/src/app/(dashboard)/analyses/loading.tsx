import { RouteLoadingFrame } from "@/components/shared/route-loading-frame";
import { Skeleton } from "@/components/shared/loading-skeleton";

export default function AnalysesLoading() {
  return (
    <RouteLoadingFrame
      label="Loading analysis library"
      eyebrow="Analyses"
      title="Preparing analysis library"
      description="Loading saved analyses, filters, status signals, and report handoffs."
    >
      <div className="space-y-6">
        <div className="grid gap-4 sm:flex sm:items-center sm:justify-between">
          <div className="min-w-0 space-y-2">
            <div className="max-w-[200px]">
              <Skeleton height={32} borderRadius={8} />
            </div>
            <div className="max-w-full sm:max-w-[300px]">
              <Skeleton height={16} borderRadius={6} />
            </div>
          </div>
          <div className="w-full sm:w-[130px]">
            <Skeleton height={40} borderRadius={8} />
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-[minmax(0,320px)_160px]">
          <Skeleton height={40} borderRadius={8} />
          <Skeleton height={40} borderRadius={8} />
        </div>

        <div className="space-y-3 xl:hidden">
          {Array.from({ length: 4 }).map((_, row) => (
            <div
              key={row}
              className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1 space-y-2">
                  <Skeleton height={16} borderRadius={4} />
                  <div className="max-w-[70%]">
                    <Skeleton height={11} borderRadius={3} />
                  </div>
                </div>
                <div className="w-20 shrink-0">
                  <Skeleton height={24} borderRadius={12} />
                </div>
              </div>
              <div className="mt-4 grid grid-cols-3 gap-3">
                {Array.from({ length: 3 }).map((__, metric) => (
                  <Skeleton key={metric} height={32} borderRadius={8} />
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] xl:block">
          <div className="grid grid-cols-[minmax(0,1.6fr)_repeat(5,minmax(0,1fr))] gap-4 border-b border-[var(--border-subtle)] px-6 py-3">
            {["Compound", "Status", "Risk", "Patents", "Duration", "Date"].map(
              (column) => (
                <div key={column} className="min-w-0">
                  <Skeleton height={10} borderRadius={3} />
                </div>
              ),
            )}
          </div>

          {Array.from({ length: 5 }).map((_, row) => (
            <div
              key={row}
              className="grid grid-cols-[minmax(0,1.6fr)_repeat(5,minmax(0,1fr))] gap-4 border-b border-[var(--surface-hover)] px-6 py-4 last:border-0"
            >
              <div className="min-w-0 space-y-1">
                <Skeleton height={14} borderRadius={4} />
                <div className="max-w-[72%]">
                  <Skeleton height={10} borderRadius={3} />
                </div>
              </div>
              <div className="min-w-0">
                <Skeleton height={22} borderRadius={12} />
              </div>
              <div className="min-w-0 max-w-16">
                <Skeleton height={22} borderRadius={12} />
              </div>
              <div className="min-w-0 max-w-12">
                <Skeleton height={14} borderRadius={4} />
              </div>
              <div className="min-w-0 max-w-16">
                <Skeleton height={14} borderRadius={4} />
              </div>
              <div className="min-w-0 max-w-20">
                <Skeleton height={14} borderRadius={4} />
              </div>
            </div>
          ))}
        </div>

        <div className="max-w-[180px]">
          <Skeleton height={14} borderRadius={4} />
        </div>
      </div>
    </RouteLoadingFrame>
  );
}
