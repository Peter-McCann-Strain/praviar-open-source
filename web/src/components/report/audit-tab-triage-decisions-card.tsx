import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartSwatch } from "@/components/charts/chart-swatch";
import {
  TRIAGE_RELEVANCE_FALLBACK_SWATCH_COLOR,
  TRIAGE_RELEVANCE_SWATCH_COLORS,
  formatTriageRelevanceLabel,
} from "@/components/report/triage-relevance";
import type { FTOReport } from "@praviar/shared-types";

interface TriageDecisionsCardProps {
  triageEntries: FTOReport["audit_trail"]["triage_audit"];
}

export function TriageDecisionsCard({
  triageEntries,
}: TriageDecisionsCardProps) {
  if (triageEntries.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader className="space-y-1.5">
        <CardTitle className="text-sm">Pre-analysis Triage</CardTitle>
        <p className="text-xs leading-5 text-[var(--text-secondary)]">
          Retrieval relevance and confidence are screening signals, not final
          FTO risk or clearance findings.
        </p>
      </CardHeader>
      <CardContent className="p-0">
        <div>
          <table className="w-full text-sm">
            <thead className="hidden md:table-header-group">
              <tr className="border-b border-[var(--border-subtle)]">
                <th
                  scope="col"
                  className="px-4 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                >
                  Patent
                </th>
                <th
                  scope="col"
                  className="px-4 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                >
                  Retrieval relevance
                </th>
                <th
                  scope="col"
                  className="px-4 py-2 text-right text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                >
                  Triage confidence
                </th>
                <th
                  scope="col"
                  className="px-4 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                >
                  Selection basis
                </th>
              </tr>
            </thead>
            <tbody className="block divide-y divide-[var(--border-subtle)] md:table-row-group">
              {triageEntries.map((triageEntry) => (
                <tr
                  key={triageEntry.patent_id}
                  className="block p-4 hover:bg-[var(--surface-muted)] md:table-row md:p-0"
                >
                  <td className="flex items-start justify-between gap-4 py-2 font-mono text-xs text-[var(--text-primary)] md:table-cell md:px-4 md:py-3">
                    <span className="type-label-sm font-sans text-[var(--text-tertiary)] md:hidden">
                      Patent
                    </span>
                    <span className="min-w-0 break-all text-right md:text-left">
                      {triageEntry.patent_id}
                    </span>
                  </td>
                  <td className="flex items-center justify-between gap-4 py-2 md:table-cell md:px-4 md:py-3">
                    <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                      Retrieval relevance
                    </span>
                    <div className="flex items-center gap-2">
                      <ChartSwatch
                        className="h-2 w-2"
                        color={
                          TRIAGE_RELEVANCE_SWATCH_COLORS[
                            triageEntry.relevance
                          ] ?? TRIAGE_RELEVANCE_FALLBACK_SWATCH_COLOR
                        }
                      />
                      <span className="text-xs text-[var(--text-secondary)]">
                        {formatTriageRelevanceLabel(triageEntry.relevance)}
                      </span>
                    </div>
                  </td>
                  <td className="flex items-center justify-between gap-4 py-2 text-[var(--text-primary)] md:table-cell md:px-4 md:py-3 md:text-right">
                    <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                      Triage confidence
                    </span>
                    <span>{(triageEntry.confidence * 100).toFixed(0)}%</span>
                  </td>
                  <td className="flex items-start justify-between gap-4 py-2 text-xs text-[var(--text-secondary)] md:table-cell md:max-w-[300px] md:truncate md:px-4 md:py-3">
                    <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                      Selection basis
                    </span>
                    <span className="min-w-0 text-right md:block md:truncate md:text-left">
                      {triageEntry.reason}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
