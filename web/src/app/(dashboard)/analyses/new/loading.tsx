import { RouteLoadingFrame } from "@/components/shared/route-loading-frame";
import { Skeleton } from "@/components/shared/loading-skeleton";

export default function Loading() {
  return (
    <RouteLoadingFrame
      label="Loading new analysis workspace"
      eyebrow="Analysis launch"
      title="Preparing analysis workspace"
      description="Setting up compound intake, evidence controls, and governed submission actions."
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
