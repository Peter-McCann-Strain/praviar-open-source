"use client";

import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Info,
} from "lucide-react";
import type { FTOReport } from "@praviar/shared-types";
import { cn } from "@/lib/utils";
import { sanitizeReportDiagnosticText } from "./report-diagnostic-copy";
import { SOURCE_LABELS } from "./summary-tab-helpers";

interface ReportCoverageBannerProps {
  report: FTOReport;
  className?: string;
}

/**
 * SG-111 — surface source-health on the report view.
 *
 * - Green pill: all sources succeeded, none skipped.
 * - Amber pill: some sources skipped but none failed.
 * - Red banner: at least one source failed. Expands to show the specific
 *   sources and error messages so attorneys can judge the coverage gap.
 *
 * Uses existing design tokens (--risk-*, --bg-surface, --border-default) so
 * the banner matches the rest of the report chrome.
 */
export function ReportCoverageBanner({
  report,
  className,
}: ReportCoverageBannerProps) {
  const entries = report.source_health?.entries ?? [];
  const [expanded, setExpanded] = useState(false);

  // Legacy / empty reports: render nothing rather than a misleading pill.
  if (entries.length === 0) {
    return null;
  }

  const total = entries.length;
  const okEntries = entries.filter((entry) => entry.status === "ok");
  const failedEntries = entries.filter((entry) => entry.status === "failed");
  const skippedEntries = entries.filter((entry) => entry.status === "skipped");
  const notConfiguredEntries = entries.filter(
    (entry) => entry.status === "not_configured",
  );
  const okCount = okEntries.length;
  const failedCount = failedEntries.length;
  const skippedCount = skippedEntries.length;
  const notConfiguredCount = notConfiguredEntries.length;

  const anyFailed = failedCount > 0;
  const anySkipped = skippedCount > 0;
  const anyNotConfigured = notConfiguredCount > 0;

  // All OK → compact green pill. No expansion.
  if (!anyFailed && !anySkipped && !anyNotConfigured) {
    return (
      <div
        role="status"
        aria-live="polite"
        className={cn(
          "inline-flex items-center gap-2 rounded-md border px-3 py-1.5",
          "border-success/30 bg-success/10 text-success",
          "text-xs font-medium",
          className,
        )}
        data-testid="coverage-banner-ok"
      >
        <CheckCircle className="h-4 w-4" aria-hidden />
        <span>All {total} sources OK</span>
      </div>
    );
  }

  // Incomplete but no failures → amber pill. No expansion.
  if (!anyFailed) {
    return (
      <div
        role="status"
        aria-live="polite"
        className={cn(
          "inline-flex items-center gap-2 rounded-md border px-3 py-1.5",
          "border-warning/30 bg-warning/10 text-warning",
          "text-xs font-medium",
          className,
        )}
        data-testid="coverage-banner-incomplete"
      >
        <Info className="h-4 w-4" aria-hidden />
        <span>
          {okCount} of {total} sources queried (
          {formatSourceGapCounts({ skippedCount, notConfiguredCount })})
        </span>
      </div>
    );
  }

  // At least one failed → expandable red banner with details.
  const headline = `${failedCount} of ${total} source${total !== 1 ? "s" : ""} failed — results may be incomplete`;

  return (
    <div
      role="alert"
      aria-live="polite"
      className={cn(
        "w-full rounded-lg border border-error/30 bg-error/5",
        "text-[var(--text-primary)]",
        className,
      )}
      data-testid="coverage-banner-failed"
    >
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className={cn(
          "flex w-full items-center gap-3 px-4 py-3 text-left",
          "hover:bg-error/10 focus:outline-none focus:ring-2 focus:ring-error/40",
          "rounded-lg",
        )}
        aria-expanded={expanded}
        aria-controls="coverage-banner-details"
      >
        <AlertTriangle
          className="h-5 w-5 flex-shrink-0 text-error"
          aria-hidden
        />
        <div className="flex-1 space-y-0.5">
          <p className="text-sm font-semibold text-error">{headline}</p>
          <p className="text-xs text-[var(--text-secondary)]">
            {okCount} succeeded
            {skippedCount > 0 ? `, ${skippedCount} skipped` : ""}
            {notConfiguredCount > 0
              ? `, ${notConfiguredCount} not configured`
              : ""}
            {" · Confidence impact: "}
            {failedCount >= 3 ? "High" : "Moderate"}
          </p>
        </div>
        {expanded ? (
          <ChevronUp
            className="h-4 w-4 text-[var(--text-tertiary)]"
            aria-hidden
          />
        ) : (
          <ChevronDown
            className="h-4 w-4 text-[var(--text-tertiary)]"
            aria-hidden
          />
        )}
      </button>

      {expanded ? (
        <div
          id="coverage-banner-details"
          className="border-t border-error/20 px-4 py-3"
        >
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
            Failed sources
          </p>
          <ul className="space-y-1.5">
            {failedEntries.map((entry) => {
              const label = SOURCE_LABELS[entry.source]?.label ?? entry.source;
              return (
                <li
                  key={entry.source}
                  className="flex flex-col gap-0.5 text-xs"
                >
                  <span className="font-medium text-[var(--text-primary)]">
                    {label}
                  </span>
                  {entry.error_message ? (
                    <span className="text-[var(--text-secondary)]">
                      {sanitizeReportDiagnosticText(
                        entry.error_message,
                        `${label} did not complete; diagnostic details are available to support.`,
                      )}
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ul>
          {skippedEntries.length > 0 ? (
            <div className="mt-3">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
                Skipped sources
              </p>
              <p className="text-xs text-[var(--text-secondary)]">
                {skippedEntries
                  .map(
                    (entry) =>
                      SOURCE_LABELS[entry.source]?.label ?? entry.source,
                  )
                  .join(", ")}
              </p>
            </div>
          ) : null}
          {notConfiguredEntries.length > 0 ? (
            <div className="mt-3">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
                Not configured sources
              </p>
              <p className="text-xs text-[var(--text-secondary)]">
                {notConfiguredEntries
                  .map(
                    (entry) =>
                      SOURCE_LABELS[entry.source]?.label ?? entry.source,
                  )
                  .join(", ")}
              </p>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function formatSourceGapCounts({
  skippedCount,
  notConfiguredCount,
}: {
  skippedCount: number;
  notConfiguredCount: number;
}): string {
  const parts = [
    skippedCount > 0 ? `${skippedCount} skipped` : null,
    notConfiguredCount > 0 ? `${notConfiguredCount} not configured` : null,
  ].filter(Boolean);

  return parts.join(", ");
}
