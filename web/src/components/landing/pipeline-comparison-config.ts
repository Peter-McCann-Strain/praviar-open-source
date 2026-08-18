import {
  Atom,
  CheckCircle2,
  Database,
  Search,
  ShieldCheck,
  Wrench,
  Zap,
} from "lucide-react";
import type {
  StepType,
  StepStyle,
} from "@/components/landing/pipeline-comparison-types";

export const TIMELINE_CONFIG = {
  label: "Adaptive Evidence Timeline",
  tagline: "One path · escalates only when the record demands it",
  accentBg: "bg-brand-primary/15",
  accentBorder: "border-brand-primary/25",
  accentText: "text-brand-primary",
  progressBar: "bg-gradient-to-r from-warning via-brand-primary to-success",
} as const;

export const STEP_STYLES: Record<StepType, StepStyle> = {
  input: {
    icon: Atom,
    bg: "bg-brand-primary/10",
    border: "border-brand-primary/20",
    iconColor: "text-brand-primary",
  },
  step: {
    icon: Zap,
    bg: "bg-[var(--surface-muted)]",
    border: "border-[var(--border-default)]",
    iconColor: "text-[var(--text-tertiary)]",
  },
  thinking: {
    icon: ShieldCheck,
    bg: "bg-warning/10",
    border: "border-warning/20",
    iconColor: "text-warning",
  },
  tool_call: {
    icon: Wrench,
    bg: "bg-info/10",
    border: "border-info/20",
    iconColor: "text-info",
  },
  tool_result: {
    icon: Database,
    bg: "bg-success/10",
    border: "border-success/20",
    iconColor: "text-success-emphasis",
  },
  element: {
    icon: Search,
    bg: "bg-warning/8",
    border: "border-warning/15",
    iconColor: "text-warning",
  },
  critique: {
    icon: ShieldCheck,
    bg: "bg-info/10",
    border: "border-info/20",
    iconColor: "text-info",
  },
  risk: {
    icon: ShieldCheck,
    bg: "bg-success/10",
    border: "border-success/20",
    iconColor: "text-success-emphasis",
  },
  complete: {
    icon: CheckCircle2,
    bg: "bg-success/10",
    border: "border-success/20",
    iconColor: "text-success-emphasis",
  },
};
