import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { FTOReport } from "@praviar/shared-types";

interface AnalysisSelectionCardProps {
  analysisEntries: FTOReport["audit_trail"]["analysis_audit"];
}

function SelectionMark({ selected }: { selected: boolean }) {
  return (
    <span
      aria-label={selected ? "Selected" : "Not selected"}
      className={selected ? "text-success" : "text-[var(--text-tertiary)]"}
    >
      <span aria-hidden="true">{selected ? "\u2713" : "\u2715"}</span>
    </span>
  );
}

export function AnalysisSelectionCard({
  analysisEntries,
}: AnalysisSelectionCardProps) {
  if (analysisEntries.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader className="space-y-1.5">
        <CardTitle className="text-sm">Candidate Analysis Routing</CardTitle>
        <p className="text-xs leading-5 text-[var(--text-secondary)]">
          Checkmarks record workflow routing, not completed findings. Selection
          for validity review does not mean invalidity was assessed.
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
                  className="px-4 py-2 text-center text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                >
                  Claim analysis
                </th>
                <th
                  scope="col"
                  className="px-4 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                >
                  Routing basis
                </th>
                <th
                  scope="col"
                  className="px-4 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                >
                  Recorded risk
                </th>
                <th
                  scope="col"
                  className="px-4 py-2 text-center text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                >
                  DoE review
                </th>
                <th
                  scope="col"
                  className="px-4 py-2 text-center text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                >
                  Validity review
                </th>
              </tr>
            </thead>
            <tbody className="block divide-y divide-[var(--border-subtle)] md:table-row-group">
              {analysisEntries.map((analysisEntry) => (
                <tr
                  key={analysisEntry.patent_id}
                  className="block p-4 hover:bg-[var(--surface-muted)] md:table-row md:p-0"
                >
                  <td className="flex items-start justify-between gap-4 py-2 font-mono text-xs text-[var(--text-primary)] md:table-cell md:px-4 md:py-3">
                    <span className="type-label-sm font-sans text-[var(--text-tertiary)] md:hidden">
                      Patent
                    </span>
                    <span className="min-w-0 break-all text-right md:text-left">
                      {analysisEntry.patent_id}
                    </span>
                  </td>
                  <td className="flex items-center justify-between gap-4 py-2 md:table-cell md:px-4 md:py-3 md:text-center">
                    <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                      Claim analysis
                    </span>
                    <SelectionMark
                      selected={analysisEntry.selected_for_analysis}
                    />
                  </td>
                  <td className="flex items-start justify-between gap-4 py-2 text-xs text-[var(--text-secondary)] md:table-cell md:max-w-[250px] md:truncate md:px-4 md:py-3">
                    <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                      Routing basis
                    </span>
                    <span className="min-w-0 text-right md:block md:truncate md:text-left">
                      {analysisEntry.selection_reason}
                    </span>
                  </td>
                  <td className="flex items-center justify-between gap-4 py-2 text-xs text-[var(--text-primary)] md:table-cell md:px-4 md:py-3">
                    <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                      Recorded risk
                    </span>
                    <span>{analysisEntry.risk_level ?? "\u2014"}</span>
                  </td>
                  <td className="flex items-center justify-between gap-4 py-2 md:table-cell md:px-4 md:py-3 md:text-center">
                    <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                      DoE review
                    </span>
                    <SelectionMark selected={analysisEntry.selected_for_doe} />
                  </td>
                  <td className="flex items-center justify-between gap-4 py-2 md:table-cell md:px-4 md:py-3 md:text-center">
                    <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                      Validity review
                    </span>
                    <SelectionMark
                      selected={analysisEntry.selected_for_invalidity}
                    />
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
