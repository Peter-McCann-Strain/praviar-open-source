"use client";

import { Badge } from "@/components/ui/badge";
import type { InvalidityAssessment } from "@/components/report/invalidity-tab-helpers";

interface InvalidityTabPtabProceedingsTableProps {
  proceedings: InvalidityAssessment["ptab"]["proceedings"];
}

export function InvalidityTabPtabProceedingsTable({
  proceedings,
}: InvalidityTabPtabProceedingsTableProps) {
  if (proceedings.length === 0) {
    return null;
  }

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)] mb-2">
        PTAB Proceedings
      </p>
      <div
        aria-label="Invalidity PTAB proceedings table"
        className="overflow-x-auto rounded-lg border border-[var(--border-subtle)] [scrollbar-gutter:stable] md:border-0"
        role="region"
        tabIndex={0}
      >
        <table className="w-full min-w-0 text-sm md:min-w-[920px]">
          <thead className="sr-only md:not-sr-only md:table-header-group">
            <tr className="border-b border-[var(--border-subtle)]">
              <th
                scope="col"
                className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
              >
                Proceeding
              </th>
              <th
                scope="col"
                className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
              >
                Type
              </th>
              <th
                scope="col"
                className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
              >
                Status
              </th>
              <th
                scope="col"
                className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
              >
                Filed
              </th>
              <th
                scope="col"
                className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
              >
                Decision
              </th>
              <th
                scope="col"
                className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
              >
                Challenged
              </th>
              <th
                scope="col"
                className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
              >
                Cancelled
              </th>
              <th
                scope="col"
                className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
              >
                Outcome
              </th>
            </tr>
          </thead>
          <tbody className="block divide-y divide-[var(--border-subtle)] md:table-row-group">
            {proceedings.map((proc) => (
              <tr
                key={proc.proceeding_number}
                className="block p-3 hover:bg-[var(--surface-muted)] md:table-row md:p-0"
              >
                <td className="flex items-start justify-between gap-3 py-2 font-mono text-[var(--text-primary)] md:table-cell md:px-3 md:align-top">
                  <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                    Proceeding
                  </span>
                  <span className="break-all text-right md:text-left">
                    {proc.proceeding_number}
                  </span>
                </td>
                <td className="flex items-start justify-between gap-3 py-2 md:table-cell md:px-3 md:align-top">
                  <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                    Proceeding type
                  </span>
                  <Badge variant="secondary">{proc.type}</Badge>
                </td>
                <td className="flex items-start justify-between gap-3 py-2 text-[var(--text-secondary)] md:table-cell md:px-3 md:align-top">
                  <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                    Status
                  </span>
                  <span className="break-words text-right [overflow-wrap:anywhere] md:text-left">
                    {proc.status}
                  </span>
                </td>
                <td className="flex items-start justify-between gap-3 py-2 text-[var(--text-secondary)] md:table-cell md:px-3 md:align-top">
                  <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                    Filed
                  </span>
                  <span>{proc.filing_date ?? "\u2014"}</span>
                </td>
                <td className="flex items-start justify-between gap-3 py-2 text-[var(--text-secondary)] md:table-cell md:px-3 md:align-top">
                  <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                    Decision
                  </span>
                  <span>{proc.decision_date ?? "\u2014"}</span>
                </td>
                <td className="flex items-start justify-between gap-3 py-2 text-[var(--text-secondary)] md:table-cell md:px-3 md:align-top">
                  <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                    Claims challenged
                  </span>
                  <span className="break-words text-right [overflow-wrap:anywhere] md:text-left">
                    {proc.claims_challenged.join(", ") || "\u2014"}
                  </span>
                </td>
                <td className="flex items-start justify-between gap-3 py-2 text-[var(--text-secondary)] md:table-cell md:px-3 md:align-top">
                  <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                    Claims cancelled
                  </span>
                  <span className="break-words text-right [overflow-wrap:anywhere] md:text-left">
                    {proc.claims_cancelled.join(", ") || "\u2014"}
                  </span>
                </td>
                <td className="grid gap-1 py-2 text-[var(--text-primary)] md:table-cell md:max-w-[240px] md:px-3 md:align-top">
                  <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                    Outcome
                  </span>
                  <span className="break-words [overflow-wrap:anywhere] md:inline">
                    {proc.outcome_summary}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
