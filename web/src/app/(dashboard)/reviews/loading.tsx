import { RouteLoadingFrame } from "@/components/shared/route-loading-frame";
import { Skeleton } from "@/components/shared/loading-skeleton";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

export default function ReviewsLoading() {
  return (
    <RouteLoadingFrame
      className="animate-fade-up"
      label="Loading reviewer queue"
      eyebrow="Reviewer queue"
      title="Preparing reviewer queue"
      description="Loading queued analyses, decision context, and review controls."
    >
      <div className="space-y-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 items-start gap-4">
            <Skeleton className="h-12 w-12 shrink-0 rounded-lg" />
            <div className="min-w-0 space-y-2">
              <Skeleton className="h-3 w-40 max-w-full" />
              <Skeleton className="h-8 w-56 max-w-full" />
              <Skeleton className="h-4 w-full max-w-sm" />
            </div>
          </div>
          <div className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)] p-3 sm:w-36">
            <Skeleton className="ml-auto h-3 w-24 max-w-full" />
            <Skeleton className="ml-auto mt-2 h-7 w-14" />
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-24 rounded-lg" />
          ))}
        </div>

        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-card)] p-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="min-w-0 space-y-2">
              <Skeleton className="h-3 w-32" />
              <Skeleton className="h-4 w-full max-w-md" />
              <Skeleton className="h-11 w-full max-w-xs sm:h-9" />
            </div>
            <div className="grid gap-2 sm:flex sm:items-center">
              <Skeleton className="h-11 w-full rounded-lg sm:h-9 sm:w-44" />
              <Skeleton className="h-11 w-full rounded-md sm:h-9 sm:w-32" />
            </div>
          </div>
        </div>

        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}>
              <CardHeader className="space-y-3">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 space-y-2">
                    <Skeleton className="h-5 w-48 max-w-full" />
                    <Skeleton className="h-3 w-full max-w-sm" />
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Skeleton className="h-6 w-16 rounded-full" />
                    <Skeleton className="h-6 w-20 rounded-full" />
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-3 w-5/6" />
                <div className="flex flex-col gap-3 pt-2 sm:flex-row sm:items-center sm:justify-between">
                  <Skeleton className="h-3 w-32" />
                  <div className="grid gap-2 sm:flex">
                    <Skeleton className="h-11 w-full rounded-md sm:h-8 sm:w-24" />
                    <Skeleton className="h-11 w-full rounded-md sm:h-8 sm:w-24" />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </RouteLoadingFrame>
  );
}
