import { RouteLoadingFrame } from "@/components/shared/route-loading-frame";
import { Skeleton } from "@/components/shared/loading-skeleton";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

export default function AnalyticsLoading() {
  return (
    <RouteLoadingFrame
      className="animate-fade-up"
      label="Loading admin analytics"
      eyebrow="Admin analytics"
      title="Preparing analytics"
      description="Loading operational metrics, trend charts, and export controls."
    >
      <div className="space-y-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-2">
            <Skeleton className="h-8 w-48 max-w-full" />
            <Skeleton className="h-4 w-full max-w-72" />
          </div>
          <div className="grid w-full grid-cols-1 gap-3 sm:flex sm:w-auto sm:items-center">
            <Skeleton className="h-11 w-full rounded-lg sm:h-9 sm:w-56" />
            <Skeleton className="h-11 w-full rounded-md sm:h-9 sm:w-32" />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-5">
                <div className="flex items-center gap-3.5">
                  <Skeleton className="h-10 w-10 rounded-lg" />
                  <div className="space-y-2 flex-1">
                    <Skeleton className="h-3 w-20" />
                    <Skeleton className="h-7 w-24" />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="space-y-4">
          <div className="flex max-w-full gap-1 overflow-x-auto border-b border-[var(--border-default)] pb-1">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-24 rounded-md" />
            ))}
          </div>

          {/* Chart area skeleton */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <Card className="lg:col-span-2">
              <CardHeader>
                <Skeleton className="h-5 w-32" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-[320px] w-full rounded-lg" />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <Skeleton className="h-5 w-40" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-[320px] w-full rounded-lg" />
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </RouteLoadingFrame>
  );
}
