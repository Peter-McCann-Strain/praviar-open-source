"use client";

import { RiskBadge } from "@/components/shared/risk-badge";
import type { AnalysisAuditEntry } from "@/components/report/funnel-explorer-helpers";

export function AnalysisTable({ entries }: { entries: AnalysisAuditEntry[] }) {
  return (
    <div className="praviar-glass-panel-soft overflow-hidden rounded-lg">
      <table className="w-full">
        <thead className="hidden md:table-header-group">
          <tr className="praviar-glass-strip border-b border-[var(--border-subtle)]">
            <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]">
              Patent
            </th>
            <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]">
              Selected
            </th>
            <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]">
              Risk
            </th>
            <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]">
              DoE
            </th>
            <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]">
              Invalidity
            </th>
          </tr>
        </thead>
        <tbody className="block divide-y divide-[var(--border-subtle)] md:table-row-group">
          {entries.map((entry) => (
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
                  Selected
                </span>
                <span
                  className={`text-xs ${
                    entry.selected_for_analysis
                      ? "text-success"
                      : "text-[var(--text-disabled)]"
                  }`}
                >
                  {entry.selected_for_analysis ? "Yes" : "No"}
                </span>
              </td>
              <td className="flex items-center justify-between gap-4 py-2 md:table-cell md:px-3 md:py-2">
                <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                  Risk
                </span>
                {entry.risk_level ? (
                  <RiskBadge
                    risk={
                      entry.risk_level as "high" | "medium" | "low" | "clear"
                    }
                    size="sm"
                  />
                ) : (
                  <span className="text-xs text-[var(--text-disabled)]">—</span>
                )}
              </td>
              <td className="flex items-center justify-between gap-4 py-2 md:table-cell md:px-3 md:py-2">
                <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                  DoE
                </span>
                <span className="text-xs text-[var(--text-secondary)]">
                  {entry.selected_for_doe ? "Yes" : "—"}
                </span>
              </td>
              <td className="flex items-center justify-between gap-4 py-2 md:table-cell md:px-3 md:py-2">
                <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                  Invalidity
                </span>
                <span className="text-xs text-[var(--text-secondary)]">
                  {entry.selected_for_invalidity ? "Yes" : "—"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
