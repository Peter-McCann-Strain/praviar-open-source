"use client";

import type {
  SearchFunnelEntry,
  TriageAuditEntry,
} from "@/components/report/funnel-explorer-helpers";

export const TRIAGE_PAGE_SIZE = 20;

export const TRIAGE_TABS = [
  { id: "all", label: "All" },
  { id: "relevant", label: "Relevant" },
  { id: "possibly_relevant", label: "Possibly" },
  { id: "not_relevant", label: "Not Relevant" },
] as const;

export type TriageTabId = (typeof TRIAGE_TABS)[number]["id"];

export function groupRejectedByReason(entries: SearchFunnelEntry[]) {
  const byReason = new Map<string, SearchFunnelEntry[]>();

  for (const entry of entries) {
    if (!entry.passed_hard_filter && entry.filter_reason) {
      const list = byReason.get(entry.filter_reason) ?? [];
      list.push(entry);
      byReason.set(entry.filter_reason, list);
    }
  }

  return byReason;
}

export function buildTriageTabCounts(entries: TriageAuditEntry[]) {
  return TRIAGE_TABS.map((tab) => ({
    ...tab,
    count:
      tab.id === "all"
        ? entries.length
        : entries.filter((entry) => entry.relevance === tab.id).length,
  }));
}

export function filterTriageEntries(
  entries: TriageAuditEntry[],
  filter: TriageTabId,
) {
  return filter === "all"
    ? entries
    : entries.filter((entry) => entry.relevance === filter);
}

export function sortTriageEntries(entries: TriageAuditEntry[]) {
  return [...entries].sort(
    (first, second) => second.confidence - first.confidence,
  );
}

export function paginateTriageEntries(
  entries: TriageAuditEntry[],
  page: number,
) {
  return entries.slice(page * TRIAGE_PAGE_SIZE, (page + 1) * TRIAGE_PAGE_SIZE);
}
