"use client";

import Link from "next/link";
import { Activity, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { AnalysisListItem } from "@/types/api";

interface RunningPipelinesAlertProps {
  runningAnalyses: AnalysisListItem[];
}

export function RunningPipelinesAlert({
  runningAnalyses,
}: RunningPipelinesAlertProps) {
  if (runningAnalyses.length === 0) {
    return null;
  }

  const visibleAnalyses = runningAnalyses.slice(0, 3);
  const remainingCount = runningAnalyses.length - visibleAnalyses.length;

  return (
    <section className="overflow-hidden rounded-lg border border-info/25 bg-info/[0.07] shadow-[var(--shadow-xs)]">
      <div className="grid gap-3 px-4 py-3 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.7fr)_auto] lg:items-center">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-info/10">
            <Activity className="h-4 w-4 animate-pulse motion-reduce:animate-none text-info" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-info">
              {runningAnalyses.length} pipeline
              {runningAnalyses.length > 1 ? "s" : ""} currently running
            </p>
            <p className="mt-0.5 text-xs leading-5 text-[var(--text-secondary)]">
              Live evidence packets are building across search, triage, and
              claim-review steps.
            </p>
          </div>
        </div>
        <div className="grid min-w-0 gap-2 sm:grid-cols-3">
          {visibleAnalyses.map((analysis) => {
            const progress = Math.max(0, Math.min(100, analysis.progress_pct));

            return (
              <Link
                key={analysis.id}
                href={`/analyses/${analysis.id}`}
                className="group min-w-0 rounded-md border border-info/15 bg-[var(--bg-surface)]/64 px-3 py-2 transition-colors hover:bg-info/10"
              >
                <div className="flex min-w-0 items-center justify-between gap-2">
                  <span className="min-w-0 truncate text-xs font-semibold text-[var(--text-primary)] group-hover:text-info">
                    {analysis.compound_name}
                  </span>
                  <span className="shrink-0 text-xs tabular-nums text-info">
                    {progress}%
                  </span>
                </div>
                <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-info/15">
                  <span
                    className="block h-full rounded-full bg-info"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <p className="mt-1 text-xs tabular-nums text-[var(--text-tertiary)]">
                  Step {analysis.current_step}/8
                </p>
              </Link>
            );
          })}
        </div>
        <Button
          asChild
          variant="ghost"
          size="sm"
          className="min-h-11 w-full justify-center text-info hover:text-info lg:w-auto"
        >
          <Link href="/analyses">
            View
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </Button>
      </div>
      {remainingCount > 0 ? (
        <div className="border-t border-info/15 px-4 py-2 text-xs text-[var(--text-secondary)]">
          +{remainingCount} more live pipeline
          {remainingCount > 1 ? "s" : ""}
        </div>
      ) : null}
    </section>
  );
}
