"use client";

import type { FTOReport, ReasoningTrace } from "@praviar/shared-types";
import { ReasoningTabEmptyState } from "./reasoning-tab-empty-state";
import { ReasoningPatentGroup } from "./reasoning-tab-patent-group";
import { ReasoningTabSummaryCards } from "./reasoning-tab-summary-cards";

interface ReasoningTabProps {
  report: FTOReport;
}

export function ReasoningTab({ report }: ReasoningTabProps) {
  const traces = report.reasoning_traces ?? [];

  if (traces.length === 0) {
    return <ReasoningTabEmptyState />;
  }

  // Group by patent_id
  const grouped = new Map<string, ReasoningTrace[]>();
  for (const trace of traces) {
    const key = trace.patent_id || "general";
    const existing = grouped.get(key) ?? [];
    existing.push(trace);
    grouped.set(key, existing);
  }

  // Aggregate stats
  const totalRounds = traces.reduce((sum, t) => sum + t.rounds.length, 0);
  const totalTokens = traces.reduce(
    (sum, t) => sum + t.total_input_tokens + t.total_output_tokens,
    0,
  );
  const totalDuration = traces.reduce((sum, t) => sum + t.total_duration_ms, 0);

  return (
    <div className="space-y-6">
      <ReasoningTabSummaryCards
        traceCount={traces.length}
        totalRounds={totalRounds}
        totalTokens={totalTokens}
        totalDuration={totalDuration}
      />

      {/* Traces grouped by patent */}
      {Array.from(grouped.entries()).map(([patentId, patentTraces]) => (
        <ReasoningPatentGroup
          key={patentId}
          patentId={patentId}
          traces={patentTraces}
        />
      ))}
    </div>
  );
}
