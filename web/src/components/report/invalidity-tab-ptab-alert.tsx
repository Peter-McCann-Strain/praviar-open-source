"use client";

import { AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { InvalidityAssessment } from "@/components/report/invalidity-tab-helpers";

interface InvalidityTabPtabAlertProps {
  ptab: InvalidityAssessment["ptab"];
}

export function InvalidityTabPtabAlert({ ptab }: InvalidityTabPtabAlertProps) {
  if (!ptab.has_been_challenged) {
    return null;
  }

  return (
    <div className="flex items-center gap-2 rounded-lg border border-warning/25 bg-warning/10 p-3">
      <AlertTriangle className="h-4 w-4 text-warning flex-shrink-0" />
      <p className="text-sm font-semibold text-warning-emphasis">
        Active PTAB Challenge
      </p>
      <Badge variant="secondary" className="text-xs ml-auto">
        {ptab.proceedings.length} proceeding
        {ptab.proceedings.length !== 1 ? "s" : ""}
      </Badge>
    </div>
  );
}
