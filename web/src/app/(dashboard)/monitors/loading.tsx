import { RouteLoadingFrame } from "@/components/shared/route-loading-frame";
import { Skeleton } from "@/components/shared/loading-skeleton";

const SUMMARY_WIDTHS = ["w-28", "w-24", "w-24", "w-28"];
const ROW_WIDTHS = [
  ["w-52", "w-28", "w-40", "w-28", "w-16", "w-44"],
  ["w-44", "w-32", "w-36", "w-24", "w-20", "w-40"],
  ["w-56", "w-24", "w-44", "w-32", "w-14", "w-48"],
  ["w-40", "w-36", "w-32", "w-28", "w-16", "w-36"],
];

export default function MonitorsLoading() {
  return (
    <RouteLoadingFrame
      className="animate-fade-up"
      label="Loading monitor workspace"
      eyebrow="Monitoring"
      title="Preparing monitor workspace"
      description="Loading patent watchlists, evidence posture, and review actions."
    >
      <div className="space-y-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-start gap-4">
            <Skeleton className="h-12 w-12 rounded-lg" />
            <div className="min-w-0 space-y-2">
              <Skeleton className="h-3 w-48" />
              <Skeleton className="h-9 w-80 max-w-full" />
              <Skeleton className="h-4 w-96 max-w-full" />
            </div>
          </div>
          <Skeleton className="h-11 w-full rounded-md sm:w-36" />
        </div>

        <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {SUMMARY_WIDTHS.map((width) => (
            <div
              key={width}
              className="praviar-surface-premium flex min-w-0 items-start gap-3 rounded-lg border border-[var(--card-border)] p-4"
            >
              <Skeleton className="h-10 w-10 rounded-md" />
              <div className="min-w-0 flex-1 space-y-2">
                <Skeleton className={`h-3 ${width}`} />
                <Skeleton className="h-7 w-16" />
                <Skeleton className="h-3 w-full" />
              </div>
            </div>
          ))}
        </section>

        <section className="praviar-surface-premium rounded-lg border border-[var(--card-border)] p-3 sm:p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0 space-y-2">
              <Skeleton className="h-3 w-44" />
              <Skeleton className="h-4 w-80 max-w-full" />
            </div>
            <div className="flex flex-wrap gap-2">
              <Skeleton className="h-8 w-24 rounded-md" />
              <Skeleton className="h-8 w-20 rounded-md" />
              <Skeleton className="h-8 w-20 rounded-md" />
            </div>
          </div>
        </section>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(22rem,26rem)] xl:items-start">
          <div className="space-y-3">
            <div className="overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--bg-surface)]">
              <div className="border-b border-[var(--border-subtle)] px-4 py-3">
                <Skeleton className="h-4 w-44" />
                <Skeleton className="mt-2 h-3 w-96 max-w-full" />
              </div>
              <div className="hidden grid-cols-[1.4fr_0.9fr_1.2fr_1fr_0.8fr_1fr] gap-4 border-b border-[var(--border-subtle)] px-4 py-3 md:grid">
                {[
                  "Monitor",
                  "Posture",
                  "Strategy",
                  "Last run",
                  "Patents",
                  "Actions",
                ].map((label) => (
                  <Skeleton key={label} className="h-3 w-20" />
                ))}
              </div>
              <div className="divide-y divide-[var(--border-subtle)]">
                {ROW_WIDTHS.map((row, rowIndex) => (
                  <div
                    key={rowIndex}
                    className="grid gap-3 p-4 md:grid-cols-[1.4fr_0.9fr_1.2fr_1fr_0.8fr_1fr] md:items-center"
                  >
                    {row.map((width, columnIndex) => (
                      <Skeleton
                        key={`${rowIndex}-${columnIndex}`}
                        className={`${columnIndex === 1 ? "h-6 rounded-full" : "h-4"} ${width} max-w-full`}
                      />
                    ))}
                  </div>
                ))}
              </div>
            </div>
            <Skeleton className="h-4 w-64" />
          </div>

          <div className="hidden overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--bg-surface)] xl:block">
            <div className="border-b border-[var(--border-subtle)] px-5 py-4">
              <Skeleton className="h-3 w-28" />
              <Skeleton className="mt-2 h-5 w-56" />
            </div>
            <div className="divide-y divide-[var(--border-subtle)]">
              {Array.from({ length: 4 }).map((_, index) => (
                <div key={index} className="p-5">
                  <div className="flex items-start gap-3">
                    <Skeleton className="h-9 w-9 rounded-lg" />
                    <div className="min-w-0 flex-1 space-y-2">
                      <Skeleton className="h-4 w-44" />
                      <Skeleton className="h-3 w-full" />
                      <div className="flex flex-wrap gap-2">
                        <Skeleton className="h-6 w-20 rounded-full" />
                        <Skeleton className="h-6 w-24 rounded-full" />
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </RouteLoadingFrame>
  );
}
