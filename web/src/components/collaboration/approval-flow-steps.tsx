"use client";

import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  statusConfig,
  type ApprovalStatus,
} from "@/components/collaboration/approval-flow-config";

export function ApprovalSteps({
  currentStatus,
}: {
  currentStatus: ApprovalStatus;
}) {
  const steps: ApprovalStatus[] = ["pending", "under_review", "approved"];
  const currentIndex = steps.indexOf(currentStatus);

  return (
    <div className="flex items-center gap-1">
      {steps.map((step, index) => {
        const isActive = index <= currentIndex;
        const config = statusConfig[step];
        const StepIcon = config.icon;

        return (
          <div key={step} className="flex items-center gap-1">
            <div
              className={cn(
                "flex h-6 w-6 items-center justify-center rounded-full",
                isActive ? config.bg : "bg-[var(--surface-muted)]",
              )}
            >
              <StepIcon
                className={cn(
                  "h-3 w-3",
                  isActive ? config.color : "text-[var(--text-disabled)]",
                )}
              />
            </div>
            {index < steps.length - 1 ? (
              <ArrowRight
                className={cn(
                  "h-3 w-3",
                  isActive
                    ? "text-[var(--text-tertiary)]"
                    : "text-[var(--text-disabled)]",
                )}
              />
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
