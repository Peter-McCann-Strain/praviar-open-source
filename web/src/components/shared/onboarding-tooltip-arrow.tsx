import { cn } from "@/lib/utils";
import type { TooltipPlacement } from "./onboarding-tooltip-position";

interface TooltipArrowProps {
  placement: TooltipPlacement;
}

export function TooltipArrow({ placement }: TooltipArrowProps) {
  const arrowClasses = {
    top: "bottom-[-6px] left-1/2 -translate-x-1/2 border-l-transparent border-r-transparent border-b-transparent border-t-[var(--bg-elevated)]",
    bottom:
      "top-[-6px] left-1/2 -translate-x-1/2 border-l-transparent border-r-transparent border-t-transparent border-b-[var(--bg-elevated)]",
    left: "right-[-6px] top-1/2 -translate-y-1/2 border-t-transparent border-b-transparent border-r-transparent border-l-[var(--bg-elevated)]",
    right:
      "left-[-6px] top-1/2 -translate-y-1/2 border-t-transparent border-b-transparent border-l-transparent border-r-[var(--bg-elevated)]",
  };

  return (
    <div
      className={cn(
        "absolute w-0 h-0 border-[6px] border-solid",
        arrowClasses[placement],
      )}
    />
  );
}
