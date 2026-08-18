"use client";

import Link from "next/link";
import {
  AlertTriangle,
  FileSearch,
  Loader2,
  ShieldCheck,
  X,
} from "lucide-react";
import { useBatch } from "@/hooks/use-batch";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { isAuthBoundaryError } from "@/lib/api-client";
import {
  canAccessFullReport,
  getReportAccessHrefWithQuery,
} from "@/lib/report-permissions";

interface BatchDetailPanelProps {
  batchId: string;
  batchName: string;
  onClose: () => void;
  currentUserRole?: string | null;
  riskRatingsRestricted?: boolean;
}

export function BatchDetailPanel({
  batchId,
  batchName,
  onClose,
  currentUserRole,
  riskRatingsRestricted,
}: BatchDetailPanelProps) {
  const { data: batch, isLoading, isError, error } = useBatch(batchId);
  const accessRestricted = isAuthBoundaryError(error);
  const displayBatchName = accessRestricted
    ? "Batch details restricted"
    : batchName;
  const displayBatchId = accessRestricted ? "Access restricted" : batchId;
  const progressPct =
    !accessRestricted && batch && batch.total_compounds > 0
      ? Math.min(
          100,
          Math.round(
            ((batch.completed_count + batch.failed_count) /
              batch.total_compounds) *
              100,
          ),
        )
      : 0;
  const fullReportAllowed = canAccessFullReport(
    currentUserRole,
    riskRatingsRestricted,
  );

  return (
    <Card
      className="overflow-hidden"
      data-testid="batch-detail-panel"
      data-batch-id={displayBatchId}
    >
      <CardHeader className="praviar-control-plane-header relative border-b border-[var(--border-subtle)] p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 pr-10 sm:pr-0">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
                <ShieldCheck className="h-4 w-4" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <CardTitle className="break-words text-base leading-6 [overflow-wrap:anywhere] sm:truncate sm:leading-none">
                  {displayBatchName}
                </CardTitle>
                <p className="mt-0.5 break-all font-mono text-xs text-[var(--text-tertiary)]">
                  {displayBatchId}
                </p>
              </div>
            </div>
            <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
              {accessRestricted
                ? "Cached batch identifiers, report links, and progress details stay hidden until access is restored."
                : "Counsel handoff, report links, and batch progress for the selected portfolio run."}
            </p>
          </div>
          <button
            aria-label="Close batch details"
            onClick={onClose}
            className="absolute right-3 top-3 flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-[var(--text-tertiary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 sm:static"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin motion-reduce:animate-none text-brand-primary" />
          </div>
        ) : accessRestricted ? (
          <div role="alert" className="px-5 py-8">
            <div className="rounded-lg border border-error/20 bg-error/10 p-4">
              <div className="flex items-start gap-3">
                <AlertTriangle
                  className="mt-0.5 h-5 w-5 shrink-0 text-error"
                  aria-hidden="true"
                />
                <div className="min-w-0">
                  <p className="font-semibold text-[var(--text-primary)]">
                    Batch details access restricted
                  </p>
                  <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                    Your current session is not authorized to view this batch.
                    Cached analysis packet links are hidden until access is
                    confirmed again.
                  </p>
                </div>
              </div>
            </div>
          </div>
        ) : isError ? (
          <div className="py-8 text-center">
            <p className="text-sm text-error">
              Failed to load batch details. Please try again.
            </p>
          </div>
        ) : !batch || batch.analysis_ids.length === 0 ? (
          <div className="py-8 text-center">
            <p className="text-sm text-[var(--text-tertiary)]">
              No analyses in this batch yet
            </p>
          </div>
        ) : (
          <div className="space-y-4 p-5">
            <div>
              <div className="mb-2 flex items-center justify-between gap-3">
                <span className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                  Batch progress
                </span>
                <Badge variant={batch.failed_count > 0 ? "warning" : "default"}>
                  {progressPct}% complete
                </Badge>
              </div>
              <div
                className="h-2 overflow-hidden rounded-full bg-[var(--surface-active)]"
                aria-hidden="true"
              >
                <div
                  className="h-full rounded-full bg-brand-primary"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2">
                <MiniMetric label="Compounds" value={batch.total_compounds} />
                <MiniMetric label="Complete" value={batch.completed_count} />
                <MiniMetric label="Failed" value={batch.failed_count} />
              </div>
            </div>

            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/74">
              <div className="border-b border-[var(--border-subtle)] px-4 py-3">
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  Available analysis packets
                </p>
                <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                  Open the first completed report or inspect individual runs.
                </p>
              </div>
              <ul className="divide-y divide-[var(--border-subtle)]">
                {batch.analysis_ids.map((analysisId: string) => (
                  <li key={analysisId}>
                    <Link
                      href={`/analyses/${analysisId}`}
                      className="group flex items-center gap-3 px-4 py-3 transition-colors hover:bg-[var(--surface-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
                    >
                      <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-brand-primary/20 bg-brand-primary/10">
                        <FileSearch className="h-4 w-4 text-brand-primary" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <span className="block truncate font-mono text-sm font-medium text-[var(--text-primary)] transition-colors group-hover:text-brand-primary">
                          {analysisId.slice(0, 14)}
                        </span>
                        <span className="mt-0.5 block text-xs text-[var(--text-tertiary)]">
                          View analysis workspace
                        </span>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
              {batch.analysis_ids[0] ? (
                <div className="border-t border-[var(--border-subtle)] p-4">
                  <Link
                    href={getReportAccessHrefWithQuery(
                      batch.analysis_ids[0],
                      currentUserRole,
                      riskRatingsRestricted,
                      {
                        audience: "diligence",
                        ai_context: "review_questions",
                        tab: "claims",
                      },
                    )}
                    className="inline-flex min-h-11 w-full items-center justify-center rounded-lg border border-brand-primary/30 bg-brand-primary text-sm font-semibold text-[var(--brand-paper)] shadow-[var(--shadow-xs)] transition-colors hover:bg-brand-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70"
                  >
                    {fullReportAllowed
                      ? "Open counsel report"
                      : "Open authorized summary"}
                  </Link>
                </div>
              ) : null}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function MiniMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/72 p-3">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-1 text-xl font-semibold tabular-nums text-[var(--text-primary)]">
        {value.toLocaleString()}
      </p>
    </div>
  );
}
