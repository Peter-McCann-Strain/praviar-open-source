"use client";

import { useClientReady } from "@/hooks/use-client-ready";

type RelativeTimeFormatter = (date: string) => string;

const STABLE_TIMESTAMP_FORMATTER = new Intl.DateTimeFormat("en-US", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

export function formatHydrationStableTimestamp(date: string): string {
  const parsed = new Date(date);
  if (Number.isNaN(parsed.getTime())) return "Unknown";
  return STABLE_TIMESTAMP_FORMATTER.format(parsed);
}

/**
 * Returns deterministic UTC copy for SSR and the first hydrated render, then
 * switches to the supplied clock-relative formatter once the browser is ready.
 */
export function useHydrationSafeRelativeTime(
  formatRelativeTime: RelativeTimeFormatter,
): RelativeTimeFormatter {
  const clientReady = useClientReady();
  return clientReady ? formatRelativeTime : formatHydrationStableTimestamp;
}
