import { RouteLoadingFrame } from "@/components/shared/route-loading-frame";
import { Skeleton } from "@/components/shared/loading-skeleton";

export default function Loading() {
  return (
    <RouteLoadingFrame
      label="Loading help workspace"
      eyebrow="Support"
      title="Preparing help workspace"
      description="Loading guidance, support resources, and product references."
    >
      <div className="space-y-3">
        <Skeleton className="h-8 w-32" />
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-16 rounded-lg" />
        ))}
      </div>
    </RouteLoadingFrame>
  );
}
