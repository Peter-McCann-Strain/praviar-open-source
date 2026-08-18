"use client";

import type { ConfigState } from "@/stores/config-store";

export type ThinkingEffortKey =
  | "thinkingEffortAnalysis"
  | "thinkingEffortTriage"
  | "thinkingEffortReport";

export const THINKING_EFFORT_OPTIONS = [
  { key: "thinkingEffortAnalysis" as const, label: "Analysis" },
  { key: "thinkingEffortTriage" as const, label: "Triage" },
  { key: "thinkingEffortReport" as const, label: "Report" },
] as const;

export function updateThinkingEffort(
  config: ConfigState,
  key: ThinkingEffortKey,
  value: "high" | "medium" | "low",
) {
  config.setConfig({ [key]: value } as Pick<ConfigState, ThinkingEffortKey>);
}
