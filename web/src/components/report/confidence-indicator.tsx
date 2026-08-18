"use client";

import { ConfidenceBar } from "@/components/shared/confidence-bar";
import { cn } from "@/lib/utils";

interface ConfidenceIndicatorProps {
  /** Uncalibrated model-support score between 0 and 1. */
  value: number;
  /** Show a ConfidenceBar beneath the label */
  showBar?: boolean;
  /** Badge text size */
  size?: "sm" | "md";
}

function getConfidenceLevel(value: number) {
  if (value >= 0.8) {
    return {
      label: "High model support",
      classes: "bg-success/20 text-success",
    };
  }
  if (value >= 0.5) {
    return {
      label: "Moderate model support",
      classes: "bg-warning/20 text-warning",
    };
  }
  return {
    label: "Low model support",
    classes: "bg-error/20 text-error",
  };
}

export function ConfidenceIndicator({
  value,
  showBar = false,
  size = "md",
}: ConfidenceIndicatorProps) {
  const { label, classes } = getConfidenceLevel(value);

  const textSize = size === "sm" ? "text-xs" : "text-xs";

  return (
    <div className="flex flex-col gap-1.5">
      <span
        className={cn(
          "inline-flex w-fit items-center rounded-full px-2 py-0.5 font-medium",
          textSize,
          classes,
        )}
      >
        <span title="Uncalibrated model-support score; not a probability or review waiver.">
          {label}
        </span>
      </span>
      {showBar && <ConfidenceBar value={value} size={size} />}
    </div>
  );
}
