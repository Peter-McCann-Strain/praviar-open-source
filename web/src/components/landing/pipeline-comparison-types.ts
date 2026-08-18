import type { LucideIcon } from "lucide-react";

export type StepType =
  | "input"
  | "step"
  | "thinking"
  | "tool_call"
  | "tool_result"
  | "element"
  | "critique"
  | "risk"
  | "complete";

export interface TraceStep {
  type: StepType;
  text: string;
  delay: number;
  status?: "met" | "not_met";
  risk?: "high" | "medium" | "low" | "clear";
}

export interface StepStyle {
  icon: LucideIcon;
  bg: string;
  border: string;
  iconColor: string;
}
