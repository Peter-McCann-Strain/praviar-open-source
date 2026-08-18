"use client";

export const AGENT_COLORS: Record<string, string> = {
  claim_analysis: "bg-info/20 text-info border-info/30",
  prosecution: "bg-warning/20 text-warning border-warning/30",
  prior_art: "bg-success/20 text-success border-success/30",
  report: "bg-info/15 text-info-emphasis border-info/25",
};

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}
