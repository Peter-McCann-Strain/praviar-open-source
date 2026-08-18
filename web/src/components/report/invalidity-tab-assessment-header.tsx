"use client";

import { CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  strengthColors,
  type InvalidityAssessment,
} from "@/components/report/invalidity-tab-helpers";

interface InvalidityTabAssessmentHeaderProps {
  assessment: InvalidityAssessment;
}

export function InvalidityTabAssessmentHeader({
  assessment,
}: InvalidityTabAssessmentHeaderProps) {
  return (
    <CardHeader>
      <div className="flex min-w-0 items-center justify-between">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <CardTitle className="min-w-0 break-all text-sm font-mono">
            {assessment.patent_id}
          </CardTitle>
          <span
            className={cn(
              "flex-shrink-0 rounded-full border px-2 py-0.5 text-xs font-semibold",
              strengthColors[
                assessment.overall_invalidity_strength.toLowerCase()
              ] ??
                "bg-[var(--surface-muted)] text-[var(--text-tertiary)] border-[var(--border-default)]",
            )}
          >
            {assessment.overall_invalidity_strength}
          </span>
          <span
            className={cn(
              "flex-shrink-0 rounded-full px-2 py-0.5 text-xs",
              assessment.confidence_band === "HIGH"
                ? "bg-success/20 text-success"
                : assessment.confidence_band === "MODERATE"
                  ? "bg-warning/20 text-warning"
                  : "bg-error/20 text-error",
            )}
          >
            {assessment.confidence_band}
          </span>
        </div>
      </div>
    </CardHeader>
  );
}
