"use client";

import { Card, CardContent } from "@/components/ui/card";
import { MoleculeViewer2D } from "@/components/chemistry/molecule-viewer-2d";
import { cn, formatDuration } from "@/lib/utils";
import type { AnalysisListItem } from "@/types/api";
import { formatElapsed } from "@/components/analysis-detail/helpers";

interface CompoundSummaryCardProps {
  analysis: AnalysisListItem;
  isComplete: boolean;
  isDevelopmentFixture?: boolean;
  isFailed: boolean;
  isRunning: boolean;
  elapsedMs: number;
}

export function CompoundSummaryCard({
  analysis,
  isComplete,
  isDevelopmentFixture = false,
  isFailed,
  isRunning,
  elapsedMs,
}: CompoundSummaryCardProps) {
  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex flex-col items-center gap-6 sm:flex-row">
          <MoleculeViewer2D
            smiles={analysis.compound_smiles}
            width={200}
            height={160}
            className="flex-shrink-0"
          />
          <div className="grid w-full flex-1 grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <p className="text-xs text-[var(--text-tertiary)]">Status</p>
              <p
                className={cn(
                  "text-sm font-medium capitalize",
                  isComplete && "text-[var(--text-primary)]",
                  isRunning && "text-brand-primary",
                  isFailed && "text-error",
                  analysis.status === "pending" &&
                    "text-[var(--text-secondary)]",
                )}
              >
                {isDevelopmentFixture ? "Seeded preview" : analysis.status}
              </p>
            </div>
            <div>
              <p className="text-xs text-[var(--text-tertiary)]">
                Patents Found
              </p>
              <p className="text-sm font-medium text-[var(--text-primary)]">
                {analysis.total_patents_found}
                {!analysis.risk_ratings_restricted &&
                (analysis.blocking_patents_count ?? 0) > 0 ? (
                  <span className="ml-1 text-error">
                    ({analysis.blocking_patents_count} blocking)
                  </span>
                ) : null}
              </p>
            </div>
            <div>
              <p className="text-xs text-[var(--text-tertiary)]">Duration</p>
              <p className="text-sm font-medium tabular-nums text-[var(--text-primary)]">
                {analysis.pipeline_duration_seconds != null
                  ? formatDuration(analysis.pipeline_duration_seconds)
                  : isDevelopmentFixture
                    ? "Not executed"
                    : isRunning && elapsedMs > 0
                      ? formatElapsed(elapsedMs)
                      : isRunning
                        ? "Running..."
                        : "—"}
              </p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
