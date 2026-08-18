"use client";

import type { FTOReport } from "@praviar/shared-types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useReviewerDecisions } from "@/hooks/use-reviewer-decisions";
import { PatentRiskTableRow } from "./patents-tab-risk-table-row";

export function PatentRiskOverview({
  report,
  sortedAnalyses,
  analysisId,
  onPatentSelect,
}: {
  report: FTOReport;
  sortedAnalyses: FTOReport["patent_analyses"];
  analysisId?: string;
  onPatentSelect: (patentId: string) => void;
}) {
  // Resolve auth + reviewer decisions ONCE for the whole table rather than per
  // row. Each row previously called useAuthToken() and useReviewerDecisions()
  // itself, so a 500-patent landscape spun up 500 Clerk token-polling intervals
  // and window event listeners — a real main-thread/memory burden. The query is
  // analysis-scoped (identical for every row), so a single subscription is
  // sufficient and the result is threaded down.
  const token = useAuthToken();
  const { data: serverDecisions } = useReviewerDecisions(
    analysisId ?? "",
    token,
  );

  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <CardTitle className="text-sm">Patent Risk Summary</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <table className="w-full">
          <thead className="sr-only md:not-sr-only md:table-header-group">
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
                Risk
              </th>
              <th
                scope="col"
                className="px-4 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
              >
                Review
              </th>
              <th
                scope="col"
                className="px-4 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
              >
                Assignee
              </th>
              <th
                scope="col"
                className="px-4 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
              >
                Expiry
              </th>
            </tr>
          </thead>
          <tbody className="block divide-y divide-[var(--border-subtle)] md:table-row-group">
            {sortedAnalyses.map((analysis) => (
              <PatentRiskTableRow
                key={analysis.patent_id}
                report={report}
                analysis={analysis}
                analysisId={analysisId}
                serverDecisions={serverDecisions}
                onPatentSelect={onPatentSelect}
              />
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
