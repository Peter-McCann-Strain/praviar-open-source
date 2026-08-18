"use client";

import { useState } from "react";
import {
  TRIAGE_PAGE_SIZE,
  buildTriageTabCounts,
  filterTriageEntries,
  paginateTriageEntries,
  sortTriageEntries,
  type TriageTabId,
} from "@/components/report/funnel-explorer-table-helpers";
import type { TriageAuditEntry } from "@/components/report/funnel-explorer-helpers";
import { ChartSwatch } from "@/components/charts/chart-swatch";
import {
  TRIAGE_RELEVANCE_FALLBACK_SWATCH_COLOR,
  TRIAGE_RELEVANCE_SWATCH_COLORS,
  formatTriageRelevanceLabel,
} from "@/components/report/triage-relevance";

export function TriageTable({ entries }: { entries: TriageAuditEntry[] }) {
  const [filter, setFilter] = useState<TriageTabId>("all");
  const [page, setPage] = useState(0);
  const tabs = buildTriageTabCounts(entries);
  const filtered = filterTriageEntries(entries, filter);
  const sorted = sortTriageEntries(filtered);
  const paged = paginateTriageEntries(sorted, page);
  const totalPages = Math.ceil(sorted.length / TRIAGE_PAGE_SIZE);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:gap-1">
        {tabs.map((tab) => (
          <button
            type="button"
            key={tab.id}
            onClick={() => {
              setFilter(tab.id);
              setPage(0);
            }}
            className={`min-h-11 rounded-lg px-3 py-2 text-xs transition-colors sm:py-1.5 ${
              filter === tab.id
                ? "praviar-glass-pill text-brand-primary"
                : "border border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--surface-muted)]"
            }`}
          >
            {tab.label} ({tab.count})
          </button>
        ))}
      </div>

      <div className="praviar-glass-panel-soft overflow-hidden rounded-lg">
        <table className="w-full">
          <thead className="hidden md:table-header-group">
            <tr className="praviar-glass-strip border-b border-[var(--border-subtle)]">
              <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]">
                Patent
              </th>
              <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]">
                Relevance
              </th>
              <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]">
                Confidence
              </th>
              <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]">
                Reason
              </th>
            </tr>
          </thead>
          <tbody className="block divide-y divide-[var(--border-subtle)] md:table-row-group">
            {paged.map((entry) => (
              <tr
                key={entry.patent_id}
                className="block p-3 transition-colors hover:bg-[var(--surface-muted)] md:table-row md:p-0"
              >
                <td className="flex items-start justify-between gap-4 py-2 md:table-cell md:px-3 md:py-2">
                  <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                    Patent
                  </span>
                  <code className="min-w-0 break-all text-right font-mono text-xs text-[var(--text-primary)] md:text-left">
                    {entry.patent_id}
                  </code>
                </td>
                <td className="flex items-center justify-between gap-4 py-2 md:table-cell md:px-3 md:py-2">
                  <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                    Relevance
                  </span>
                  <div className="flex items-center gap-1.5">
                    <ChartSwatch
                      className="h-2 w-2"
                      color={
                        TRIAGE_RELEVANCE_SWATCH_COLORS[entry.relevance] ??
                        TRIAGE_RELEVANCE_FALLBACK_SWATCH_COLOR
                      }
                    />
                    <span className="text-xs capitalize text-[var(--text-secondary)]">
                      {formatTriageRelevanceLabel(entry.relevance)}
                    </span>
                  </div>
                </td>
                <td className="flex items-center justify-between gap-4 py-2 md:table-cell md:px-3 md:py-2">
                  <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                    Confidence
                  </span>
                  <span className="text-xs tabular-nums text-[var(--text-primary)]">
                    {(entry.confidence * 100).toFixed(0)}%
                  </span>
                </td>
                <td className="flex items-start justify-between gap-4 py-2 md:table-cell md:px-3 md:py-2">
                  <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                    Reason
                  </span>
                  <p className="min-w-0 break-words text-right text-xs text-[var(--text-secondary)] [overflow-wrap:anywhere] md:max-w-[300px] md:truncate md:text-left">
                    {entry.reason}
                  </p>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 ? (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-[var(--text-disabled)]">
            Showing {page * TRIAGE_PAGE_SIZE + 1}–
            {Math.min((page + 1) * TRIAGE_PAGE_SIZE, sorted.length)} of{" "}
            {sorted.length}
          </p>
          <div className="flex gap-1">
            <button
              type="button"
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="min-h-11 flex-1 rounded border border-[var(--border-default)] px-3 py-2 text-xs disabled:opacity-30 sm:flex-none sm:px-2 sm:py-1"
            >
              Prev
            </button>
            <button
              type="button"
              onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
              disabled={page >= totalPages - 1}
              className="min-h-11 flex-1 rounded border border-[var(--border-default)] px-3 py-2 text-xs disabled:opacity-30 sm:flex-none sm:px-2 sm:py-1"
            >
              Next
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
