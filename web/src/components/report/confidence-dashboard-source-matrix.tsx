import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";

import { cn } from "@/lib/utils";

import type { DisplayedSourceEntry } from "./confidence-dashboard-helpers";
import { SOURCE_LABELS } from "./summary-tab-helpers";

interface ConfidenceDashboardSourceMatrixProps {
  displayedSources: DisplayedSourceEntry[];
}

export function ConfidenceDashboardSourceMatrix({
  displayedSources,
}: ConfidenceDashboardSourceMatrixProps) {
  return (
    <div>
      <span className="text-xs font-medium text-[var(--text-secondary)] block mb-2">
        Patent Databases
      </span>
      <div className="grid grid-cols-2 gap-2">
        {displayedSources.map((sourceEntry) => {
          const label =
            SOURCE_LABELS[sourceEntry.source]?.label ?? sourceEntry.source;
          const failed = sourceEntry.status === "failed";
          const incomplete =
            sourceEntry.status === "skipped" ||
            sourceEntry.status === "not_configured";

          return (
            <div
              key={sourceEntry.source}
              className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-start gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-2 py-1.5 text-xs"
            >
              {sourceEntry.status === "ok" && !failed ? (
                <CheckCircle2
                  className="h-3.5 w-3.5 text-success"
                  aria-hidden="true"
                />
              ) : failed ? (
                <XCircle
                  className="h-3.5 w-3.5 text-error"
                  aria-hidden="true"
                />
              ) : incomplete ? (
                <AlertTriangle
                  className="h-3.5 w-3.5 text-warning"
                  aria-hidden="true"
                />
              ) : (
                <XCircle
                  className="h-3.5 w-3.5 text-[var(--text-disabled)]"
                  aria-hidden="true"
                />
              )}
              <span className="min-w-0">
                <span
                  className={cn(
                    "block break-words leading-4 [overflow-wrap:anywhere]",
                    sourceEntry.status === "ok"
                      ? "text-[var(--text-primary)]"
                      : "text-[var(--text-disabled)]",
                  )}
                >
                  {label}
                </span>
                <span className="mt-0.5 block text-xs text-[var(--text-tertiary)] tabular-nums">
                  {sourceEntry.patent_count.toLocaleString()} patents
                </span>
                <span className="sr-only">
                  {getSourceStatusLabel(sourceEntry.status)}
                </span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function getSourceStatusLabel(status: DisplayedSourceEntry["status"]): string {
  if (status === "ok") {
    return "available";
  }
  return status.replace("_", " ");
}
