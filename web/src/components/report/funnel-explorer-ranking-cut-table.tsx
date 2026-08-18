"use client";

import { Badge } from "@/components/ui/badge";
import type { SearchFunnelEntry } from "@/components/report/funnel-explorer-helpers";

export function RankingCutTable({ entries }: { entries: SearchFunnelEntry[] }) {
  const cut = entries
    .filter((entry) => entry.passed_hard_filter && !entry.included_in_triage)
    .sort(
      (first, second) =>
        (first.pre_cut_rank ??
          first.composite_rank ??
          Number.MAX_SAFE_INTEGER) -
        (second.pre_cut_rank ??
          second.composite_rank ??
          Number.MAX_SAFE_INTEGER),
    );

  return (
    <div className="space-y-3">
      <p className="text-xs text-[var(--text-secondary)]">
        {cut.length.toLocaleString()} candidates passed hard filters but were
        excluded by a recorded ranking cutoff.
      </p>
      {cut.length === 0 ? (
        <p className="text-xs text-[var(--text-tertiary)]">
          No rank-cut candidates were retained for this run.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-[var(--border-default)]">
          <table className="w-full min-w-[620px] text-left text-xs">
            <thead className="bg-[var(--surface-muted)] text-[var(--text-secondary)]">
              <tr>
                <th className="px-3 py-2 font-medium">Patent</th>
                <th className="px-3 py-2 font-medium">Cutoff</th>
                <th className="px-3 py-2 font-medium">Composite rank</th>
                <th className="px-3 py-2 font-medium">Pre-cut rank</th>
                <th className="px-3 py-2 font-medium">Final score</th>
              </tr>
            </thead>
            <tbody>
              {cut.slice(0, 50).map((entry) => (
                <tr
                  key={`${entry.candidate_index ?? "supplemental"}-${entry.patent_id}`}
                  className="border-t border-[var(--border-default)]"
                >
                  <td className="px-3 py-2 font-mono text-[var(--text-primary)]">
                    {entry.patent_id}
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant="secondary" className="text-xs">
                      {(
                        entry.filter_reason ||
                        entry.exclusion_stage ||
                        "rank cut"
                      ).replace(/_/g, " ")}
                    </Badge>
                  </td>
                  <td className="px-3 py-2 text-[var(--text-secondary)]">
                    {entry.composite_rank ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-[var(--text-secondary)]">
                    {entry.pre_cut_rank ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-[var(--text-secondary)]">
                    {entry.final_blend_score?.toFixed(3) ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {cut.length > 50 ? (
            <p className="border-t border-[var(--border-default)] px-3 py-2 text-xs text-[var(--text-tertiary)]">
              Showing the first 50 of {cut.length.toLocaleString()} retained
              rank-cut receipts.
            </p>
          ) : null}
        </div>
      )}
    </div>
  );
}
