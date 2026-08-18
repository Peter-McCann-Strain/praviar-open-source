"use client";

import { Check } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartSwatch } from "@/components/charts/chart-swatch";
import { cn } from "@/lib/utils";
import {
  SOURCE_LABELS,
  SOURCE_STATUS_FALLBACK_SWATCH_COLOR,
  SOURCE_STATUS_SWATCH_COLORS,
  formatJurisdictionScopeLabel,
} from "@/components/report/summary-tab-helpers";
import {
  getReportSourceHealthReadiness,
  isHealthySourceStatus,
} from "@/components/report-page/report-reliance-readiness";
import type { FTOReport } from "@praviar/shared-types";

interface SourceHealthCardProps {
  report: FTOReport;
  variant?: "default" | "rail";
}

function SourceStatusSwatch({ status }: { status: string }) {
  return (
    <ChartSwatch
      className="h-2 w-2"
      color={
        SOURCE_STATUS_SWATCH_COLORS[status] ??
        SOURCE_STATUS_FALLBACK_SWATCH_COLOR
      }
    />
  );
}

function JurisdictionScopePill({
  jurisdiction,
  active = false,
  listed = false,
}: {
  jurisdiction: string;
  active?: boolean;
  listed?: boolean;
}) {
  const label = formatJurisdictionScopeLabel(jurisdiction);
  const coverageState = active
    ? "searched"
    : listed
      ? "listed coverage"
      : "not directly searched";

  return (
    <span
      title={`${label} ${coverageState}`}
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-1 text-xs font-medium",
        active
          ? "border-success/30 bg-success/10 text-success"
          : listed
            ? "border-[var(--border-default)] bg-[var(--surface-subtle)] text-[var(--text-secondary)]"
            : "border-[var(--border-default)] bg-[var(--surface-hover)] text-[var(--text-disabled)]",
      )}
    >
      {active ? <Check className="mr-1 h-3 w-3" aria-hidden="true" /> : null}
      <span aria-hidden="true">{label}</span>
      <span className="sr-only">
        {label} {coverageState}
      </span>
    </span>
  );
}

export function SourceHealthCard({
  report,
  variant = "default",
}: SourceHealthCardProps) {
  const entries = report.source_health?.entries ?? [];
  const sourceHealthReadiness = getReportSourceHealthReadiness(report);
  const listedSourceCount = report.search_sources_used?.length ?? 0;
  const rail = variant === "rail";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Source Health &amp; Coverage</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="praviar-glass-strip border-b border-[var(--border-default)] px-4 py-3">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
            Direct Jurisdiction Searches
          </p>
          <div className="flex flex-wrap gap-1.5">
            {["US", "EP", "WO", "JP", "KR", "CN", "IN", "CA", "AU"].map(
              (jurisdiction) => {
                const isActive = entries.some((entry) => {
                  const meta = SOURCE_LABELS[entry.source];

                  return (
                    isHealthySourceStatus(entry.status) &&
                    (meta?.jurisdictions.includes(jurisdiction) ?? false)
                  );
                });

                return (
                  <JurisdictionScopePill
                    key={jurisdiction}
                    jurisdiction={jurisdiction}
                    active={isActive}
                  />
                );
              },
            )}
          </div>
        </div>

        {rail ? (
          <div className="divide-y divide-[var(--border-default)]">
            {entries.length === 0 && listedSourceCount > 0 ? (
              <div
                className="px-4 py-3 text-xs leading-5 text-warning"
                role="status"
              >
                {sourceHealthReadiness.detail}
              </div>
            ) : null}
            {entries.map((entry) => {
              const meta = SOURCE_LABELS[entry.source];
              return (
                <div
                  key={entry.source}
                  className="grid gap-2 px-4 py-3 text-sm"
                >
                  <div className="flex min-w-0 items-center justify-between gap-3">
                    <span className="min-w-0 truncate font-medium text-[var(--text-primary)]">
                      {meta?.label ?? entry.source}
                    </span>
                    <span className="shrink-0 tabular-nums text-[var(--text-primary)]">
                      {(entry.patent_count ?? 0).toLocaleString()}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--text-secondary)]">
                    <span className="inline-flex items-center gap-1">
                      <SourceStatusSwatch status={entry.status} />
                      <span className="capitalize">
                        {entry.status.replace(/_/g, " ")}
                      </span>
                    </span>
                    {(meta?.jurisdictions ?? [])
                      .slice(0, 2)
                      .map((jurisdiction) => (
                        <JurisdictionScopePill
                          key={jurisdiction}
                          jurisdiction={jurisdiction}
                          listed
                        />
                      ))}
                    {(meta?.jurisdictions.length ?? 0) > 2 ? (
                      <span className="text-[var(--text-tertiary)]">
                        +{(meta?.jurisdictions.length ?? 0) - 2} scope
                      </span>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div
            aria-label="Source health table horizontal scroll area"
            className="overflow-x-auto focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
            role="region"
            tabIndex={0}
          >
            {entries.length === 0 && listedSourceCount > 0 ? (
              <div
                className="border-b border-[var(--border-default)] px-4 py-3 text-xs leading-5 text-warning"
                role="status"
              >
                {sourceHealthReadiness.detail}
              </div>
            ) : null}
            <table className="min-w-[34rem] w-full">
              <thead>
                <tr className="border-b border-[var(--border-default)]">
                  <th
                    scope="col"
                    className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]"
                  >
                    Source
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]"
                  >
                    Coverage
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]"
                  >
                    Status
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-2 text-right text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]"
                  >
                    Patents
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-default)]">
                {entries.map((entry) => {
                  const meta = SOURCE_LABELS[entry.source];

                  return (
                    <tr
                      key={entry.source}
                      className="hover:bg-[var(--surface-hover)]"
                    >
                      <td className="px-4 py-3">
                        <span className="text-sm text-[var(--text-primary)]">
                          {meta?.label ?? entry.source}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          {(meta?.jurisdictions ?? []).map((jurisdiction) => (
                            <JurisdictionScopePill
                              key={jurisdiction}
                              jurisdiction={jurisdiction}
                              listed
                            />
                          ))}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <SourceStatusSwatch status={entry.status} />
                          <span className="text-xs capitalize text-[var(--text-secondary)]">
                            {entry.status.replace(/_/g, " ")}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right text-sm tabular-nums text-[var(--text-primary)]">
                        {(entry.patent_count ?? 0).toLocaleString()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
