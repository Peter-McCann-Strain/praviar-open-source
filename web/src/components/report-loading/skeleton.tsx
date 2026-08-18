import type { ComponentProps } from "react";
import { Skeleton } from "@/components/shared/loading-skeleton";

type ReportSkeletonProps = ComponentProps<typeof Skeleton>;

export function ReportSkeleton(props: ReportSkeletonProps) {
  return <Skeleton {...props} />;
}
