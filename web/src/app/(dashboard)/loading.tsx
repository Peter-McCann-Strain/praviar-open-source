import { RouteLoadingFrame } from "@/components/shared/route-loading-frame";
import { Skeleton } from "@/components/shared/loading-skeleton";
import { KPISkeleton, TableSkeleton } from "@/components/shared/skeletons";

export default function DashboardLoading() {
  return (
    <RouteLoadingFrame
      label="Loading Praviar workspace"
      eyebrow="Workspace"
      title="Preparing workspace"
      description="Loading navigation context and the current workspace surface."
    >
      <div className="space-y-6">
        <div className="space-y-2">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-64" />
        </div>
        <KPISkeleton />
        <TableSkeleton rows={4} cols={5} />
      </div>
    </RouteLoadingFrame>
  );
}
