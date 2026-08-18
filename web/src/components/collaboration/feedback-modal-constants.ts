"use client";

import { FileText, Gauge, Scale, Type, type LucideIcon } from "lucide-react";

export const RISK_LEVELS = ["HIGH", "MEDIUM", "LOW", "CLEAR"] as const;

export const ISSUE_TYPES = [
  { value: "wrong_risk", label: "Wrong Risk Level" },
  { value: "missed_patent", label: "Missed Patent" },
  { value: "irrelevant_patent", label: "Irrelevant Patent" },
  { value: "wrong_claim_interpretation", label: "Wrong Claim Interpretation" },
  { value: "missing_prior_art", label: "Missing Prior Art" },
  { value: "outdated_status", label: "Outdated Status" },
  { value: "wrong_compound_mapping", label: "Wrong Compound Mapping" },
  { value: "procedural_error", label: "Procedural Error" },
  { value: "markush_scope_error", label: "Markush Scope Error" },
] as const;

export const ANNOTATION_TYPES = [
  { value: "inaccurate", label: "Inaccurate" },
  { value: "incomplete", label: "Incomplete" },
  { value: "misleading", label: "Misleading" },
  { value: "well_done", label: "Well Done" },
] as const;

export const FEEDBACK_TABS = [
  { id: "report", label: "Report", icon: FileText },
  { id: "patent", label: "Patent", icon: Gauge },
  { id: "claim", label: "Claim", icon: Scale },
  { id: "text", label: "Text", icon: Type },
] as const satisfies ReadonlyArray<{
  id: string;
  label: string;
  icon: LucideIcon;
}>;

export type FeedbackTabId = (typeof FEEDBACK_TABS)[number]["id"];

export const selectClass =
  "w-full h-9 rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-muted)] px-3 text-sm text-[var(--text-secondary)]";

export const textareaClass =
  "w-full rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary resize-none";

export const inputClass =
  "w-full h-9 rounded-md border border-[var(--border-default)] bg-[var(--surface-muted)] px-3 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary";

export function riskColor(level: string) {
  switch (level.toLowerCase()) {
    case "high":
      return "border-error bg-error/10 text-error";
    case "medium":
      return "border-warning bg-warning/10 text-warning";
    case "low":
      return "border-info bg-info/10 text-info";
    case "clear":
      return "border-success bg-success/10 text-success";
    default:
      return "border-[var(--border-emphasis)] bg-[var(--surface-hover)] text-[var(--text-secondary)]";
  }
}
