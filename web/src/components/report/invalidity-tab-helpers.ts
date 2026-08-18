"use client";

import type { FTOReport } from "@praviar/shared-types";

export type InvalidityAssessment = FTOReport["invalidity_assessments"][number];
export type GrahamFactors = NonNullable<InvalidityAssessment["graham_factors"]>;

export const strengthColors: Record<string, string> = {
  strong: "bg-success/20 text-success border-success/30",
  moderate: "bg-warning/20 text-warning border-warning/30",
  weak: "bg-error/20 text-error border-error/30",
};

export const disclosedIcons: Record<string, { icon: string; color: string }> = {
  yes: { icon: "\u25CF", color: "text-success" },
  partial: { icon: "\u25D0", color: "text-warning" },
  no: { icon: "\u25CB", color: "text-error" },
};
