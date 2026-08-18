"use client";

import { Badge } from "@/components/ui/badge";
import type { InvalidityAssessment } from "@/components/report/invalidity-tab-helpers";

interface InvalidityTabPriorArtTableProps {
  patentId: string;
  priorArt: InvalidityAssessment["prior_art"];
}

export function InvalidityTabPriorArtTable({
  patentId,
  priorArt,
}: InvalidityTabPriorArtTableProps) {
  if (priorArt.length === 0) {
    return null;
  }

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)] mb-2">
        Prior Art References
      </p>
      <div
        aria-label={`Invalidity prior art references table for ${patentId}`}
        className="overflow-x-auto rounded-lg border border-[var(--border-subtle)] [scrollbar-gutter:stable] md:border-0"
        role="region"
        tabIndex={0}
      >
        <table className="w-full min-w-0 text-sm md:min-w-[860px]">
          <thead className="sr-only md:not-sr-only md:table-header-group">
            <tr className="border-b border-[var(--border-subtle)]">
              <th
                scope="col"
                className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
              >
                Reference
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
                Title
              </th>
              <th
                scope="col"
                className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
              >
                Published
              </th>
              <th
                scope="col"
                className="px-3 py-2 text-right text-xs font-semibold uppercase text-[var(--text-tertiary)]"
              >
                Antic.
              </th>
              <th
                scope="col"
                className="px-3 py-2 text-right text-xs font-semibold uppercase text-[var(--text-tertiary)]"
              >
                Obvious.
              </th>
              <th
                scope="col"
                className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
              >
                Source
              </th>
            </tr>
          </thead>
          <tbody className="block divide-y divide-[var(--border-subtle)] md:table-row-group">
            {priorArt.map((ref) => (
              <tr
                key={ref.reference_id}
                className="block p-3 hover:bg-[var(--surface-muted)] md:table-row md:p-0"
              >
                <td className="flex items-start justify-between gap-3 py-2 font-mono text-xs text-[var(--text-primary)] md:table-cell md:px-3">
                  <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                    Reference
                  </span>
                  <span className="break-all text-right md:text-left">
                    {ref.reference_id}
                  </span>
                </td>
                <td className="flex items-start justify-between gap-3 py-2 md:table-cell md:px-3">
                  <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                    Reference type
                  </span>
                  <Badge variant="secondary" className="text-xs">
                    {ref.reference_type}
                  </Badge>
                </td>
                <td className="grid gap-1 py-2 text-[var(--text-primary)] md:table-cell md:max-w-[220px] md:px-3">
                  <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                    Title
                  </span>
                  <span className="break-words [overflow-wrap:anywhere] md:inline">
                    {ref.title}
                  </span>
                </td>
                <td className="flex items-start justify-between gap-3 py-2 text-[var(--text-secondary)] md:table-cell md:px-3">
                  <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                    Published
                  </span>
                  <span>{ref.publication_date ?? "\u2014"}</span>
                </td>
                <td className="flex items-start justify-between gap-3 py-2 text-[var(--text-primary)] md:table-cell md:px-3 md:text-right">
                  <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                    Anticipation
                  </span>
                  <span>{(ref.anticipation_score * 100).toFixed(0)}%</span>
                </td>
                <td className="flex items-start justify-between gap-3 py-2 text-[var(--text-primary)] md:table-cell md:px-3 md:text-right">
                  <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                    Obviousness
                  </span>
                  <span>{(ref.obviousness_score * 100).toFixed(0)}%</span>
                </td>
                <td className="flex items-start justify-between gap-3 py-2 text-xs text-[var(--text-secondary)] md:table-cell md:px-3">
                  <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                    Source database
                  </span>
                  <span className="break-words text-right [overflow-wrap:anywhere] md:text-left">
                    {ref.source_database || "\u2014"}
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
