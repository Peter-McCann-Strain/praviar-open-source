"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Copy, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import { canonicalPriorArtSourceUrl } from "@/lib/prior-art-source-url";
import {
  disclosedIcons,
  type InvalidityAssessment,
} from "@/components/report/invalidity-tab-helpers";

interface InvalidityTabClaimChartsSectionProps {
  claimCharts: InvalidityAssessment["claim_charts"];
  priorArt: InvalidityAssessment["prior_art"];
  reportContext?: {
    generatedAt?: string | null;
    pipelineVersion?: string | null;
    reportId?: string | null;
  };
}

export function InvalidityTabClaimChartsSection({
  claimCharts,
  priorArt,
  reportContext,
}: InvalidityTabClaimChartsSectionProps) {
  const [copiedRowId, setCopiedRowId] = useState<string | null>(null);
  const [copyFailedRowId, setCopyFailedRowId] = useState<string | null>(null);
  const [manualPacket, setManualPacket] = useState<{
    rowId: string;
    text: string;
  } | null>(null);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const priorArtByReferenceId = useMemo(
    () =>
      new Map(priorArt.map((reference) => [reference.reference_id, reference])),
    [priorArt],
  );

  useEffect(
    () => () => {
      if (copyTimerRef.current !== null) clearTimeout(copyTimerRef.current);
    },
    [],
  );

  if (claimCharts.length === 0) {
    return null;
  }

  const handleCopyRow = async ({
    chart,
    entry,
    priorArtReference,
    rowId,
  }: {
    chart: InvalidityAssessment["claim_charts"][number];
    entry: InvalidityAssessment["claim_charts"][number]["entries"][number];
    priorArtReference?: InvalidityAssessment["prior_art"][number];
    rowId: string;
  }) => {
    const packet = buildClaimChartRowPacket({
      chart,
      entry,
      priorArtReference,
      reportContext,
    });

    try {
      await writeClipboardText(packet);
      setCopiedRowId(rowId);
      setCopyFailedRowId(null);
      setManualPacket(null);
      if (copyTimerRef.current !== null) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => {
        setCopiedRowId(null);
        setCopyFailedRowId(null);
      }, 2000);
    } catch {
      setCopiedRowId(null);
      setCopyFailedRowId(rowId);
      setManualPacket({ rowId, text: packet });
      if (copyTimerRef.current !== null) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => setCopyFailedRowId(null), 2000);
    }
  };

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)] mb-2">
        Claim Charts
      </p>
      <div className="space-y-4">
        {claimCharts.map((chart) => (
          <div
            key={`${chart.patent_id}-${chart.claim_number}-${chart.prior_art_reference_id}`}
            className="praviar-glass-panel-soft overflow-hidden rounded-lg"
          >
            <div className="praviar-glass-strip min-w-0 px-4 py-2 text-xs text-[var(--text-secondary)]">
              <p className="break-words font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
                Claim {chart.claim_number} vs {chart.prior_art_reference_id}
              </p>
              {priorArtByReferenceId.get(chart.prior_art_reference_id)
                ?.title && (
                <p className="mt-1 break-words text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
                  {
                    priorArtByReferenceId.get(chart.prior_art_reference_id)
                      ?.title
                  }
                </p>
              )}
            </div>
            <div
              aria-label={`Claim chart rows for ${chart.patent_id} claim ${chart.claim_number}`}
              className="overflow-x-auto [scrollbar-gutter:stable]"
              role="region"
              tabIndex={0}
            >
              <table className="w-full min-w-0 table-auto text-sm md:min-w-[900px]">
                <thead className="sr-only md:not-sr-only md:table-header-group">
                  <tr className="border-b border-[var(--border-subtle)]">
                    <th
                      scope="col"
                      className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)] w-12"
                    >
                      #
                    </th>
                    <th
                      scope="col"
                      className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                    >
                      Element
                    </th>
                    <th
                      scope="col"
                      className="px-3 py-2 text-center text-xs font-semibold uppercase text-[var(--text-tertiary)] w-20"
                    >
                      Disclosed
                    </th>
                    <th
                      scope="col"
                      className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                    >
                      Prior Art
                    </th>
                    <th
                      scope="col"
                      className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                    >
                      Citation
                    </th>
                    <th
                      scope="col"
                      className="px-3 py-2 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)] w-32"
                    >
                      Packet
                    </th>
                  </tr>
                </thead>
                <tbody className="block divide-y divide-[var(--border-subtle)] md:table-row-group">
                  {chart.entries.map((entry) => {
                    const disc =
                      disclosedIcons[entry.disclosed] ?? disclosedIcons.no;
                    const rowId = `${chart.patent_id}-${chart.claim_number}-${chart.prior_art_reference_id}-${entry.element_number}`;
                    const copied = copiedRowId === rowId;
                    const copyFailed = copyFailedRowId === rowId;
                    const manualPacketVisible = manualPacket?.rowId === rowId;
                    const referenceId =
                      entry.prior_art_reference_id ||
                      chart.prior_art_reference_id;
                    const priorArtReference =
                      priorArtByReferenceId.get(referenceId) ??
                      priorArtByReferenceId.get(chart.prior_art_reference_id);
                    const sourceHref = getPriorArtHref(priorArtReference);
                    const copyLabel = `Copy packet for ${chart.patent_id} claim ${chart.claim_number} element ${entry.element_number} vs ${referenceId}`;
                    const sourceLabel = `Open source for ${chart.patent_id} claim ${chart.claim_number} element ${entry.element_number} via ${referenceId}`;
                    return (
                      <tr
                        key={entry.element_number}
                        className="block p-3 align-top hover:bg-[var(--surface-muted)] md:table-row md:p-0"
                      >
                        <td className="flex items-start justify-between gap-3 py-2 font-mono text-[var(--text-tertiary)] md:table-cell md:px-3">
                          <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                            Element #
                          </span>
                          <span>{entry.element_number}</span>
                        </td>
                        <td className="grid gap-1 py-2 text-[var(--text-primary)] md:table-cell md:max-w-[300px] md:px-3">
                          <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                            Claim element
                          </span>
                          <span className="break-words [overflow-wrap:anywhere] md:inline">
                            {entry.element_text}
                          </span>
                        </td>
                        <td className="flex items-center justify-between gap-3 py-2 md:table-cell md:px-3 md:text-center">
                          <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                            Disclosed
                          </span>
                          <span className={cn("text-lg", disc.color)}>
                            {disc.icon}
                          </span>
                          <span
                            className={cn(
                              "inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold uppercase",
                              getDisclosureBadgeClass(entry.disclosed),
                            )}
                          >
                            {getDisclosureLabel(entry.disclosed)}
                          </span>
                        </td>
                        <td className="grid gap-1 py-2 text-xs text-[var(--text-secondary)] md:table-cell md:max-w-[340px] md:px-3">
                          <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                            Prior art disclosure
                          </span>
                          <span className="break-words [overflow-wrap:anywhere] md:inline">
                            {entry.prior_art_disclosure}
                          </span>
                          <span className="text-xs text-[var(--text-tertiary)]">
                            {formatPriorArtMicrocopy(
                              priorArtReference,
                              referenceId,
                            )}
                          </span>
                        </td>
                        <td className="grid gap-1 py-2 text-xs text-[var(--text-tertiary)] md:table-cell md:px-3">
                          <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                            Citation location
                          </span>
                          <span className="break-words [overflow-wrap:anywhere]">
                            {entry.citation_location || "Not reported"}
                          </span>
                        </td>
                        <td className="grid gap-1 py-2 text-xs text-[var(--text-secondary)] md:table-cell md:px-3">
                          <span className="text-xs font-semibold uppercase text-[var(--text-tertiary)] md:hidden">
                            Evidence packet
                          </span>
                          <div className="flex min-w-0 flex-wrap items-center gap-2">
                            {sourceHref ? (
                              <a
                                href={sourceHref}
                                target="_blank"
                                rel="noreferrer"
                                aria-label={sourceLabel}
                                className="inline-flex min-h-11 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-2.5 py-1.5 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:border-brand-primary/30 hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)]"
                              >
                                <ExternalLink
                                  className="h-3.5 w-3.5"
                                  aria-hidden="true"
                                />
                                Source
                              </a>
                            ) : (
                              <span className="inline-flex min-h-9 items-center rounded-md border border-[var(--border-subtle)] px-2.5 py-1.5 text-xs font-semibold uppercase text-[var(--text-tertiary)]">
                                No source link
                              </span>
                            )}
                            <button
                              type="button"
                              aria-label={copyLabel}
                              onClick={() =>
                                handleCopyRow({
                                  chart,
                                  entry,
                                  priorArtReference,
                                  rowId,
                                })
                              }
                              data-testid={`claim-chart-copy-${chart.patent_id}-${chart.claim_number}-${entry.element_number}`}
                              className="inline-flex min-h-11 items-center gap-1.5 rounded-md border border-brand-primary/20 bg-brand-primary/8 px-2.5 py-1.5 text-xs font-semibold text-brand-primary transition-colors hover:bg-brand-primary/12 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)]"
                            >
                              {copied ? (
                                <>
                                  <Check
                                    className="h-3.5 w-3.5"
                                    aria-hidden="true"
                                  />
                                  Copied
                                </>
                              ) : copyFailed ? (
                                <>
                                  <Copy
                                    className="h-3.5 w-3.5"
                                    aria-hidden="true"
                                  />
                                  Copy unavailable
                                </>
                              ) : (
                                <>
                                  <Copy
                                    className="h-3.5 w-3.5"
                                    aria-hidden="true"
                                  />
                                  Copy row
                                </>
                              )}
                            </button>
                          </div>
                          {manualPacketVisible && (
                            <textarea
                              readOnly
                              aria-label={`Manual packet text for ${chart.patent_id} claim ${chart.claim_number} element ${entry.element_number}`}
                              value={manualPacket.text}
                              onFocus={(event) => event.currentTarget.select()}
                              className="mt-2 h-28 w-full min-w-0 max-w-full resize-y rounded-md border border-warning/30 bg-warning/5 p-2 font-mono text-xs leading-relaxed text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-warning/60"
                            />
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {chart.chart_summary && (
              <div className="praviar-glass-strip border-t border-[var(--border-subtle)] px-4 py-2">
                <p className="text-xs text-[var(--text-secondary)]">
                  {chart.chart_summary}
                </p>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

async function writeClipboardText(text: string): Promise<void> {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // Fall through to the selection-based copy path for locked-down browsers.
    }
  }

  if (typeof document === "undefined" || !document.execCommand) {
    throw new Error("Clipboard API unavailable");
  }

  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.setAttribute("readonly", "");
  textArea.style.position = "fixed";
  textArea.style.left = "-9999px";
  textArea.style.top = "0";
  document.body.appendChild(textArea);
  textArea.select();

  try {
    if (!document.execCommand("copy")) {
      throw new Error("Clipboard copy rejected");
    }
  } finally {
    document.body.removeChild(textArea);
  }
}

function getDisclosureLabel(disclosed: string): string {
  if (disclosed === "yes") return "Disclosed";
  if (disclosed === "partial") return "Partial";
  return "Gap";
}

function getDisclosureBadgeClass(disclosed: string): string {
  if (disclosed === "yes") {
    return "border-success/25 bg-success/10 text-success";
  }
  if (disclosed === "partial") {
    return "border-warning/25 bg-warning/10 text-warning";
  }
  return "border-error/25 bg-error/10 text-error";
}

function buildClaimChartRowPacket({
  chart,
  entry,
  priorArtReference,
  reportContext,
}: {
  chart: InvalidityAssessment["claim_charts"][number];
  entry: InvalidityAssessment["claim_charts"][number]["entries"][number];
  priorArtReference?: InvalidityAssessment["prior_art"][number];
  reportContext?: InvalidityTabClaimChartsSectionProps["reportContext"];
}): string {
  const referenceId =
    entry.prior_art_reference_id || chart.prior_art_reference_id;

  return [
    "Praviar claim chart row packet",
    `Report: ${formatPacketValue(reportContext?.reportId)}`,
    `Generated: ${formatPacketValue(reportContext?.generatedAt)}`,
    `Pipeline: ${formatPacketValue(reportContext?.pipelineVersion)}`,
    `Patent: ${chart.patent_id}`,
    `Claim: ${chart.claim_number}`,
    `Prior art reference: ${referenceId}`,
    `Prior art title: ${formatPacketValue(priorArtReference?.title)}`,
    `Authors: ${formatAuthors(priorArtReference?.authors)}`,
    `Published: ${formatPacketValue(priorArtReference?.publication_date)}`,
    `Reference type: ${formatPacketValue(priorArtReference?.reference_type)}`,
    `Source database: ${formatPacketValue(priorArtReference?.source_database)}`,
    `DOI: ${formatPacketValue(priorArtReference?.doi)}`,
    `Source URL: ${formatPacketValue(getPriorArtHref(priorArtReference))}`,
    `Element: ${entry.element_number}`,
    `Disclosure posture: ${getDisclosureLabel(entry.disclosed)}`,
    `Element text: ${formatPacketText(entry.element_text)}`,
    `Prior art disclosure: ${formatPacketText(entry.prior_art_disclosure)}`,
    `Citation location: ${formatPacketValue(entry.citation_location)}`,
    `Notes: ${formatPacketValue(entry.notes)}`,
    `Chart summary: ${formatPacketValue(chart.chart_summary)}`,
    "Guardrail: Automated invalidity screening is not a legal opinion; confirm cited prior art and claim mapping before downstream reliance.",
  ].join("\n");
}

function formatPacketValue(value: string | number | null | undefined): string {
  const trimmed = String(value ?? "").trim();
  return trimmed ? trimmed : "Not reported";
}

function formatPacketText(value: string | null | undefined): string {
  return formatPacketValue(value).replace(/\s+/g, " ");
}

function getPriorArtHref(
  reference: InvalidityAssessment["prior_art"][number] | undefined,
): string | null {
  return canonicalPriorArtSourceUrl(reference);
}

function formatAuthors(authors: string[] | null | undefined): string {
  return authors && authors.length > 0 ? authors.join(", ") : "Not reported";
}

function formatPriorArtMicrocopy(
  reference: InvalidityAssessment["prior_art"][number] | undefined,
  fallbackReferenceId: string,
): string {
  if (!reference) return `Reference ${fallbackReferenceId}`;

  const parts = [
    reference.title,
    reference.publication_date,
    reference.source_database,
  ].filter((part): part is string => Boolean(part));

  return parts.length > 0
    ? parts.join(" / ")
    : `Reference ${fallbackReferenceId}`;
}
