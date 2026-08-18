import { RouteLoadingFrame } from "@/components/shared/route-loading-frame";
import { Skeleton } from "@/components/shared/loading-skeleton";

export default function AnalysisDetailLoading() {
  return (
    <RouteLoadingFrame
      className="mx-auto max-w-3xl"
      label="Loading analysis detail workspace"
      eyebrow="Analysis detail"
      title="Preparing analysis detail"
      description="Loading compound context, pipeline progress, and governed review state."
    >
      <div className="space-y-8">
        {/* Header with compound info */}
        <div className="flex min-w-0 flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <Skeleton
              width={220}
              height={28}
              borderRadius={6}
              className="max-w-full"
            />
            <Skeleton
              width={300}
              height={14}
              borderRadius={4}
              className="max-w-full"
              style={{ marginTop: 6 }}
            />
            <Skeleton
              width={180}
              height={10}
              borderRadius={3}
              className="max-w-full"
              style={{ marginTop: 4 }}
            />
          </div>
          <Skeleton width={80} height={28} borderRadius={14} />
        </div>

        {/* Compound preview card */}
        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-6">
          <div className="flex min-w-0 flex-col gap-6 sm:flex-row sm:items-center">
            {/* Molecule viewer placeholder */}
            <Skeleton
              width={200}
              height={160}
              borderRadius={12}
              className="max-w-full"
            />
            {/* Stats 2x2 grid */}
            <div className="grid min-w-0 flex-1 grid-cols-2 gap-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="min-w-0">
                  <Skeleton
                    width={60}
                    height={10}
                    borderRadius={3}
                    className="max-w-full"
                  />
                  <Skeleton
                    width={80}
                    height={16}
                    borderRadius={4}
                    className="max-w-full"
                    style={{ marginTop: 4 }}
                  />
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Pipeline stepper card */}
        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-8">
          <div className="space-y-4">
            {Array.from({ length: 8 }).map((_, i) => {
              const labelWidths = [150, 200, 130, 160, 170, 150, 140, 140];
              return (
                <div key={i} className="flex min-w-0 items-center gap-4">
                  {/* Step icon circle */}
                  <Skeleton width={40} height={40} circle />
                  {/* Step label */}
                  <div className="min-w-0 flex-1">
                    <Skeleton
                      width={labelWidths[i]}
                      height={14}
                      borderRadius={4}
                      className="max-w-full"
                    />
                  </div>
                  {/* Step status text */}
                  <Skeleton
                    width={48}
                    height={12}
                    borderRadius={4}
                    className="max-w-full shrink-0"
                  />
                </div>
              );
            })}
          </div>

          {/* Progress bar */}
          <div className="mt-8">
            <Skeleton height={8} borderRadius={9999} />
            <div className="flex justify-center mt-2">
              <Skeleton width={180} height={12} borderRadius={4} />
            </div>
          </div>
        </div>
      </div>
    </RouteLoadingFrame>
  );
}
