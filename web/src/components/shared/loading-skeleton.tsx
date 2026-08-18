import type { CSSProperties, HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  baseColor?: string;
  borderRadius?: number | string;
  circle?: boolean;
  count?: number;
  height?: number | string;
  highlightColor?: string;
  width?: number | string;
}

function sizeValue(value: number | string | undefined) {
  return typeof value === "number" ? `${value}px` : value;
}

function cssVariableStyle(
  baseColor: string | undefined,
  highlightColor: string | undefined,
): CSSProperties {
  return {
    ...(baseColor ? { "--skeleton-base": baseColor } : {}),
    ...(highlightColor ? { "--skeleton-highlight": highlightColor } : {}),
  } as CSSProperties;
}

export function Skeleton({
  baseColor,
  borderRadius,
  circle = false,
  className,
  count = 1,
  height,
  highlightColor,
  style,
  width,
  ...props
}: SkeletonProps) {
  const skeletonStyle: CSSProperties = {
    ...cssVariableStyle(baseColor, highlightColor),
    ...style,
    ...(width !== undefined ? { width: sizeValue(width) } : {}),
    ...(height !== undefined ? { height: sizeValue(height) } : {}),
    ...(circle
      ? { borderRadius: "9999px" }
      : borderRadius !== undefined
        ? { borderRadius: sizeValue(borderRadius) }
        : {}),
  };
  const skeletonClassName = cn(
    "skeleton-shimmer rounded-md motion-reduce:animate-none",
    circle && "rounded-full",
    className,
  );

  if (count > 1) {
    return (
      <div className="space-y-2">
        {Array.from({ length: count }).map((_, index) => (
          <div
            key={index}
            className={skeletonClassName}
            style={skeletonStyle}
            {...props}
          />
        ))}
      </div>
    );
  }

  return <div className={skeletonClassName} style={skeletonStyle} {...props} />;
}
