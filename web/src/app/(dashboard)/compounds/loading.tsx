import { RouteLoadingFrame } from "@/components/shared/route-loading-frame";
import { Skeleton } from "@/components/shared/loading-skeleton";

const SUMMARY_WIDTHS = [88, 108, 96, 112];
const ROW_WIDTHS = [
  [132, 188, 68, 48, 92, 116, 92],
  [116, 220, 60, 44, 84, 88, 88],
  [148, 170, 74, 52, 98, 132, 96],
  [104, 196, 64, 46, 88, 104, 84],
];

function MetricSkeleton({ width }: { width: number }) {
  return (
    <div className="praviar-surface-premium flex min-w-0 items-start gap-3 rounded-lg border border-[var(--card-border)] p-4">
      <Skeleton width={40} height={40} borderRadius={8} />
      <div className="min-w-0 flex-1">
        <Skeleton width={width} height={10} borderRadius={4} />
        <Skeleton
          width={width * 0.7}
          height={24}
          borderRadius={6}
          style={{ marginTop: 8 }}
        />
        <Skeleton
          width="90%"
          height={12}
          borderRadius={4}
          style={{ marginTop: 8 }}
        />
      </div>
    </div>
  );
}

export default function CompoundsLoading() {
  return (
    <RouteLoadingFrame
      className="animate-fade-up"
      label="Loading compound library workspace"
      eyebrow="Compound library"
      title="Preparing compound library"
      description="Loading compound records, identifiers, and evidence links."
    >
      <div className="space-y-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <Skeleton width={240} height={16} borderRadius={6} />
            <Skeleton
              width={300}
              height={36}
              borderRadius={8}
              style={{ marginTop: 10 }}
            />
            <Skeleton
              width={360}
              height={16}
              borderRadius={6}
              style={{ marginTop: 8, maxWidth: "100%" }}
            />
          </div>
          <Skeleton width={180} height={40} borderRadius={8} />
        </div>

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {SUMMARY_WIDTHS.map((width) => (
            <MetricSkeleton key={width} width={width} />
          ))}
        </section>

        <section
          aria-label="Loading compound library controls"
          className="praviar-surface-premium rounded-lg border border-[var(--card-border)] p-3 sm:p-4"
        >
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
            <div className="min-w-0 flex-1">
              <Skeleton width={132} height={12} borderRadius={4} />
              <Skeleton
                width="100%"
                height={40}
                borderRadius={8}
                style={{ marginTop: 8 }}
              />
            </div>
            <Skeleton
              width={384}
              height={58}
              borderRadius={8}
              style={{ maxWidth: "100%" }}
            />
          </div>
          <Skeleton
            width="70%"
            height={14}
            borderRadius={4}
            style={{ marginTop: 16 }}
          />
        </section>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(20rem,24rem)] xl:items-start">
          <div className="space-y-3">
            <div className="overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--bg-surface)]">
              <div className="border-b border-[var(--border-subtle)] px-4 py-3">
                <Skeleton width={190} height={16} borderRadius={5} />
                <Skeleton
                  width={420}
                  height={12}
                  borderRadius={4}
                  style={{ marginTop: 8, maxWidth: "100%" }}
                />
              </div>
              <div className="hidden grid-cols-[1.3fr_1.5fr_0.7fr_0.5fr_0.8fr_1fr_0.8fr] gap-4 border-b border-[var(--border-subtle)] px-4 py-3 md:grid">
                {[
                  "Compound",
                  "Identifiers",
                  "Formula",
                  "MW",
                  "Evidence",
                  "Groups",
                  "Date",
                ].map((label) => (
                  <Skeleton
                    key={label}
                    width={label.length * 8}
                    height={10}
                    borderRadius={3}
                  />
                ))}
              </div>
              <div className="divide-y divide-[var(--border-subtle)]">
                {ROW_WIDTHS.map((row, rowIndex) => (
                  <div
                    key={rowIndex}
                    className="grid gap-3 p-4 md:grid-cols-[1.3fr_1.5fr_0.7fr_0.5fr_0.8fr_1fr_0.8fr] md:items-center"
                  >
                    {row.map((width, columnIndex) => (
                      <Skeleton
                        key={`${rowIndex}-${columnIndex}`}
                        width={width}
                        height={columnIndex === 4 ? 22 : 14}
                        borderRadius={columnIndex === 4 ? 12 : 4}
                        style={{ maxWidth: "100%" }}
                      />
                    ))}
                  </div>
                ))}
              </div>
            </div>
            <Skeleton width={260} height={16} borderRadius={4} />
          </div>

          <div className="hidden overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--bg-surface)] xl:block">
            <div className="border-b border-[var(--border-subtle)] px-4 py-4">
              <Skeleton width={168} height={10} borderRadius={4} />
              <Skeleton
                width={210}
                height={26}
                borderRadius={6}
                style={{ marginTop: 10 }}
              />
              <Skeleton
                width={260}
                height={24}
                borderRadius={12}
                style={{ marginTop: 12 }}
              />
            </div>
            <div className="space-y-4 p-4">
              {Array.from({ length: 4 }).map((_, index) => (
                <Skeleton
                  key={index}
                  width="100%"
                  height={index < 2 ? 74 : 42}
                  borderRadius={8}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </RouteLoadingFrame>
  );
}
