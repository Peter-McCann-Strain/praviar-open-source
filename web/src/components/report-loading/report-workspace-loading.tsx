import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import { ReportSkeleton } from "@/components/report-loading/skeleton";
import { cn } from "@/lib/utils";

interface ReportWorkspaceLoadingProps {
  className?: string;
}

const DECISION_METRIC_WIDTHS = ["72%", "58%", "66%", "52%"] as const;
const REPORT_TAB_WIDTHS = ["76%", "68%", "72%", "64%", "70%"] as const;

export function ReportWorkspaceLoading({
  className,
}: ReportWorkspaceLoadingProps) {
  return (
    <section
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-atomic="true"
      className={cn(
        "praviar-report-workspace mx-auto w-full min-w-0 max-w-[90rem] overflow-x-clip",
        className,
      )}
      data-praviar-report-loading-workspace
      data-praviar-app-state="loading"
    >
      <span className="sr-only">Loading report workspace</span>

      <div aria-hidden="true" className="space-y-6">
        <div className="flex min-h-11 items-center gap-2 lg:hidden">
          {[72, 112, 52].map((width) => (
            <ReportSkeleton
              key={width}
              width={width}
              height={12}
              borderRadius={4}
            />
          ))}
        </div>

        <section
          className="praviar-report-decision-field overflow-hidden rounded-lg"
          data-praviar-report-loading-identity
        >
          <div className="grid min-w-0 gap-4 p-4 sm:p-5">
            <div className="flex min-w-0 items-start gap-4">
              <PraviarMarkFrame />
              <div className="min-w-0 flex-1">
                <ReportSkeleton
                  width="min(15rem, 72%)"
                  height={12}
                  borderRadius={4}
                />
                <ReportSkeleton
                  width="min(24rem, 92%)"
                  height={28}
                  borderRadius={7}
                  style={{ marginTop: 10 }}
                />
                <div className="mt-3 flex flex-wrap gap-2">
                  {[84, 110, 128].map((width) => (
                    <ReportSkeleton
                      key={width}
                      width={width}
                      height={24}
                      borderRadius={999}
                    />
                  ))}
                </div>
              </div>
            </div>

            <div className="hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/76 p-2 lg:block">
              <div className="flex items-center justify-between gap-4 border-b border-[var(--border-subtle)] px-2 pb-2">
                <div className="space-y-2">
                  <ReportSkeleton width={116} height={10} borderRadius={3} />
                  <ReportSkeleton width={260} height={10} borderRadius={3} />
                </div>
              </div>
              <div className="grid grid-cols-5 gap-2 px-1 pt-2">
                {Array.from({ length: 5 }).map((_, index) => (
                  <ReportSkeleton key={index} height={44} borderRadius={8} />
                ))}
              </div>
            </div>
          </div>
        </section>

        <div
          className="sticky top-14 z-30"
          data-praviar-report-loading-section-rail
        >
          <div className="min-h-11 rounded-lg border border-[var(--border-default)] bg-[var(--surface-glass)] p-2 shadow-[var(--shadow-xs)] sm:hidden">
            <ReportSkeleton
              width="min(13rem, 72%)"
              height={20}
              borderRadius={4}
            />
          </div>
          <div className="hidden min-h-[3.25rem] grid-cols-[repeat(5,minmax(0,1fr))_9rem] gap-1 rounded-lg border border-[var(--border-default)] bg-[var(--surface-glass)] p-1 shadow-[var(--shadow-xs)] sm:grid">
            {REPORT_TAB_WIDTHS.map((width) => (
              <div
                key={width}
                className="flex min-w-0 items-center justify-center rounded-lg px-2"
              >
                <ReportSkeleton width={width} height={12} borderRadius={4} />
              </div>
            ))}
            <ReportSkeleton height={44} borderRadius={8} />
          </div>
        </div>

        <div
          className="praviar-mobile-command-surface sticky top-[6.25rem] z-20 grid min-h-[3.625rem] grid-cols-3 gap-1.5 rounded-lg px-2 py-1.5 sm:top-[6.75rem] lg:hidden"
          data-praviar-report-loading-command-rail
        >
          {Array.from({ length: 3 }).map((_, index) => (
            <ReportSkeleton key={index} height={44} borderRadius={8} />
          ))}
        </div>

        <div
          className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/76 p-3 shadow-[var(--shadow-xs)]"
          data-praviar-report-loading-section-context
        >
          <div className="flex min-w-0 items-start gap-3">
            <ReportSkeleton width={32} height={32} borderRadius={8} />
            <div className="min-w-0 flex-1 space-y-2">
              <ReportSkeleton width={136} height={12} borderRadius={4} />
              <ReportSkeleton
                width="min(34rem, 88%)"
                height={12}
                borderRadius={4}
              />
            </div>
          </div>
        </div>

        <section
          className="praviar-report-decision-field overflow-hidden rounded-lg"
          data-praviar-report-loading-decision-brief
        >
          <div className="p-4 sm:p-5">
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.38fr)]">
              <div className="min-w-0">
                <ReportSkeleton width={136} height={10} borderRadius={3} />
                <ReportSkeleton
                  width="min(28rem, 84%)"
                  height={24}
                  borderRadius={6}
                  style={{ marginTop: 8 }}
                />
                <div className="mt-4 grid grid-cols-2 gap-2 xl:grid-cols-4">
                  {DECISION_METRIC_WIDTHS.map((width) => (
                    <div
                      key={width}
                      className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/72 p-3"
                    >
                      <ReportSkeleton
                        width="58%"
                        height={10}
                        borderRadius={3}
                      />
                      <ReportSkeleton
                        width={width}
                        height={18}
                        borderRadius={5}
                        style={{ marginTop: 8 }}
                      />
                    </div>
                  ))}
                </div>
              </div>
              <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/48 p-4">
                <ReportSkeleton width={96} height={10} borderRadius={3} />
                <ReportSkeleton
                  width="82%"
                  height={18}
                  borderRadius={5}
                  style={{ marginTop: 10 }}
                />
                <ReportSkeleton
                  height={44}
                  borderRadius={8}
                  style={{ marginTop: 16 }}
                />
              </div>
            </div>
          </div>

          <div
            className="border-t border-[var(--border-subtle)]"
            data-praviar-report-loading-readiness-disclosure
          >
            <div className="flex min-h-16 items-center justify-between gap-3 bg-[var(--surface-muted)]/45 px-4 py-3 sm:hidden">
              <div className="min-w-0 flex-1 space-y-2">
                <ReportSkeleton width={168} height={14} borderRadius={4} />
                <ReportSkeleton width="82%" height={10} borderRadius={3} />
              </div>
              <ReportSkeleton width={28} height={28} borderRadius={7} />
            </div>
            <div className="hidden gap-3 p-4 sm:grid lg:grid-cols-3">
              {Array.from({ length: 3 }).map((_, index) => (
                <div
                  key={index}
                  className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/72 p-3"
                >
                  <ReportSkeleton width={104} height={10} borderRadius={3} />
                  <ReportSkeleton
                    height={14}
                    borderRadius={4}
                    style={{ marginTop: 10 }}
                  />
                  <ReportSkeleton
                    width="76%"
                    height={10}
                    borderRadius={3}
                    style={{ marginTop: 8 }}
                  />
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </section>
  );
}
