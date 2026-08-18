import { RouteLoadingFrame } from "@/components/shared/route-loading-frame";
import { Skeleton } from "@/components/shared/loading-skeleton";

export default function Loading() {
  return (
    <RouteLoadingFrame
      label="Loading quick analysis launcher"
      eyebrow="Analysis launch"
      title="Preparing quick analysis"
      description="Preserving the submitted compound while the adaptive analysis workspace opens."
    >
      <div className="space-y-5">
        <div className="space-y-2">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-8 w-72 max-w-full" />
        </div>
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-10 w-32" />
      </div>
    </RouteLoadingFrame>
  );
}
