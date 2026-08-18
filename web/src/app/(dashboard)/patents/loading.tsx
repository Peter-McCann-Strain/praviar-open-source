import { RouteLoadingFrame } from "@/components/shared/route-loading-frame";
import { Skeleton } from "@/components/shared/loading-skeleton";

const METRIC_WIDTHS = ["w-28", "w-32", "w-24", "w-28"];
const ROW_WIDTHS = [
  ["w-28", "w-48", "w-14", "w-32", "w-20", "w-10"],
  ["w-32", "w-56", "w-16", "w-28", "w-24", "w-12"],
  ["w-24", "w-44", "w-14", "w-36", "w-20", "w-10"],
  ["w-28", "w-52", "w-16", "w-32", "w-24", "w-12"],
  ["w-32", "w-40", "w-14", "w-28", "w-20", "w-10"],
];

export default function PatentsLoading() {
  return (
    <RouteLoadingFrame
      label="Loading patent evidence library"
      eyebrow="Patent evidence"
      title="Preparing patent library"
      description="Loading patent records, risk filters, and report handoff controls."
    >
      <div className="space-y-6">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {METRIC_WIDTHS.map((width, index) => (
            <div
              key={`${width}-${index}`}
              className="praviar-surface-premium flex min-w-0 items-start gap-3 rounded-lg border border-[var(--card-border)] p-4"
            >
              <Skeleton className="h-10 w-10 shrink-0 rounded-lg" />
              <div className="min-w-0 flex-1 space-y-2">
                <Skeleton className={`h-3 ${width}`} />
                <Skeleton className="h-7 w-20" />
                <Skeleton className="h-3 w-full" />
              </div>
            </div>
          ))}
        </div>

        <section
          aria-label="Loading patent library controls"
          className="praviar-surface-premium rounded-lg border border-[var(--card-border)] p-3 sm:p-4"
        >
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_28rem]">
            <Skeleton className="h-11 w-full rounded-lg" />
            <div className="grid gap-3 sm:grid-cols-2">
              <Skeleton className="h-11 w-full rounded-lg" />
              <Skeleton className="h-11 w-full rounded-lg" />
            </div>
          </div>
        </section>

        <section
          aria-label="Loading patent records"
          className="overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--bg-surface)]"
        >
          <div className="border-b border-[var(--border-subtle)] px-4 py-3">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="mt-2 h-3 w-64 max-w-full" />
          </div>

          <div className="divide-y divide-[var(--border-subtle)] md:hidden">
            {ROW_WIDTHS.slice(0, 4).map((row, index) => (
              <div key={index} className="space-y-3 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1 space-y-2">
                    <Skeleton className={`h-4 ${row[0]} max-w-full`} />
                    <Skeleton className={`h-3 ${row[1]} max-w-full`} />
                  </div>
                  <Skeleton className="h-6 w-16 shrink-0 rounded-full" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Skeleton className="h-3 w-28 max-w-full" />
                  <Skeleton className="h-3 w-20 max-w-full" />
                  <Skeleton className="h-3 w-32 max-w-full" />
                  <Skeleton className="h-3 w-12 max-w-full" />
                </div>
              </div>
            ))}
          </div>

          <div className="hidden md:block">
            <div className="grid grid-cols-[1.1fr_1.55fr_0.7fr_1.2fr_0.85fr_0.7fr] gap-4 border-b border-[var(--border-subtle)] px-6 py-3">
              {[
                "Patent ID",
                "Title",
                "Risk",
                "Assignee",
                "Expiry",
                "Jurisdiction",
              ].map((label) => (
                <Skeleton
                  key={label}
                  className="h-3 max-w-full"
                  style={{ width: `${Math.max(label.length * 8, 48)}px` }}
                />
              ))}
            </div>

            <div className="divide-y divide-[var(--surface-hover)]">
              {ROW_WIDTHS.map((row, rowIndex) => (
                <div
                  key={rowIndex}
                  className="grid grid-cols-[1.1fr_1.55fr_0.7fr_1.2fr_0.85fr_0.7fr] items-center gap-4 px-6 py-4"
                >
                  {row.map((width, columnIndex) => (
                    <Skeleton
                      key={`${rowIndex}-${columnIndex}`}
                      className={`${columnIndex === 2 ? "h-6 rounded-full" : "h-4"} ${width} max-w-full`}
                    />
                  ))}
                </div>
              ))}
            </div>
          </div>
        </section>

        <Skeleton className="h-4 w-44 max-w-full" />
      </div>
    </RouteLoadingFrame>
  );
}
