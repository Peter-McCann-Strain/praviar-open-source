import type { CSSProperties } from "react";
import { cn } from "@/lib/utils";

type ChartSwatchShape = "dot" | "square";

interface ChartSwatchProps {
  className?: string;
  color: string;
  shape?: ChartSwatchShape;
}

export function ChartSwatch({
  className,
  color,
  shape = "dot",
}: ChartSwatchProps) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "praviar-chart-swatch inline-block shrink-0",
        shape === "square" ? "rounded-[3px]" : "rounded-full",
        className,
      )}
      style={{ "--chart-swatch-color": color } as CSSProperties}
    />
  );
}
