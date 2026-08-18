"use client";

import { useCallback, useRef } from "react";
import { Printer } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  ClaimedUseReceiptLedger,
  type ClaimedUseReceiptLedgerState,
} from "./claimed-use-receipt-ledger";
import { PRINT_STYLES } from "./print-report-styles";
import { PrintReportFooter } from "./print-report-footer";
import { PrintReportHeader } from "./print-report-header";
import {
  getPrintReportProvenanceItems,
  PrintReportProvenance,
  type PrintReportProvenanceItem,
} from "./print-report-provenance";
import {
  getPrintReportRelianceItems,
  PrintReportReliance,
  type PrintReportRelianceItem,
} from "./print-report-reliance";
import type { PrintReportBranding } from "./print-report-branding";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PrintReportProps {
  /** The report content to render in print mode. */
  children: React.ReactNode;
  /** Optional title shown in the print header */
  title?: string;
  /** Optional compound name for the print header */
  compoundName?: string;
  /** Optional date string for the print header */
  date?: string;
  /** Print-only provenance metadata for counsel/export review. */
  provenanceItems?: PrintReportProvenanceItem[];
  /** Print-only reliance boundary shown before evidence content. */
  relianceItems?: PrintReportRelianceItem[];
  /** Print-only packet readiness summary shown before reliance/provenance. */
  packetSummary?: PrintReportPacketSummary;
  /** Trusted print branding snapshot for white-label artifacts. */
  branding?: PrintReportBranding;
  /** Render the visible print trigger. Report pages provide this elsewhere. */
  showButton?: boolean;
  /** Render a screen-only preview of print caveats before invoking print. */
  showPacketPreview?: boolean;
  /** Verified counsel overlay rendered into the printable packet. */
  claimedUseReceiptState?: ClaimedUseReceiptLedgerState;
}

export interface PrintReportPacketSummaryItem {
  label: string;
  value: string;
}

export interface PrintReportPacketSummary {
  detail: string;
  items?: PrintReportPacketSummaryItem[];
  label: string;
  tone?: "ready" | "warning" | "danger" | "neutral";
}

const DEFAULT_PACKET_SUMMARY: PrintReportPacketSummary = {
  detail:
    "Reliance boundary and AI provenance are inserted before report content.",
  items: [
    { label: "Scope", value: "Current print artifact" },
    { label: "Use", value: "Counsel review support" },
  ],
  label: "Print packet governance",
  tone: "neutral",
};

export function getPrintReportPacketSummary(
  summary?: PrintReportPacketSummary,
): PrintReportPacketSummary {
  if (!summary) {
    return DEFAULT_PACKET_SUMMARY;
  }

  return {
    ...summary,
    items:
      summary.items && summary.items.length > 0
        ? summary.items
        : DEFAULT_PACKET_SUMMARY.items,
    tone: summary.tone ?? "neutral",
  };
}

/**
 * Wraps report content with print-optimized styles.
 *
 * Features:
 * - CSS @media print rules to hide navigation, sidebar, and interactive elements
 * - Proper table and chart formatting for print
 * - Page break control via .print-page-break and .print-avoid-break classes
 * - Print header with title, compound name, and date
 * - "Print Report" button triggers window.print()
 */
export function PrintReport({
  children,
  title = "FTO Analysis Report",
  compoundName,
  date,
  provenanceItems,
  relianceItems,
  packetSummary,
  branding,
  showButton = true,
  showPacketPreview = showButton,
  claimedUseReceiptState,
}: PrintReportProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const resolvedRelianceItems = getPrintReportRelianceItems(relianceItems);
  const resolvedProvenanceItems =
    getPrintReportProvenanceItems(provenanceItems);
  const resolvedPacketSummary = getPrintReportPacketSummary(packetSummary);

  const handlePrint = useCallback(() => {
    window.print();
  }, []);

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: PRINT_STYLES }} />

      {showButton || showPacketPreview ? (
        <div className="no-print mb-4 space-y-3">
          {showPacketPreview ? (
            <PrintPacketScreenPreview
              packetSummary={resolvedPacketSummary}
              provenanceItems={resolvedProvenanceItems}
              relianceItems={resolvedRelianceItems}
            />
          ) : null}
          {showButton ? (
            <div className="flex justify-end">
              <Button
                variant="outline"
                size="sm"
                onClick={handlePrint}
                data-print-trigger
                className="min-h-11 gap-2"
              >
                <Printer className="h-4 w-4" />
                Print Report
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}

      {/* Print wrapper */}
      <div ref={wrapperRef} className="print-report-wrapper">
        <PrintReportHeader
          title={title}
          compoundName={compoundName}
          date={date}
          branding={branding}
        />
        <PrintReportPacketSummary summary={resolvedPacketSummary} />
        <PrintReportReliance items={resolvedRelianceItems} />
        <PrintReportProvenance items={resolvedProvenanceItems} />
        {claimedUseReceiptState ? (
          <ClaimedUseReceiptLedger
            state={claimedUseReceiptState}
            variant="print"
          />
        ) : null}

        {/* Report content */}
        {children}

        <PrintReportFooter branding={branding} />
      </div>
    </>
  );
}

function PrintPacketScreenPreview({
  packetSummary,
  provenanceItems,
  relianceItems,
}: {
  packetSummary: PrintReportPacketSummary;
  provenanceItems: PrintReportProvenanceItem[];
  relianceItems: PrintReportRelianceItem[];
}) {
  const toneClass = getPacketSummaryToneClass(packetSummary.tone);

  return (
    <section
      aria-label="Print packet preview"
      className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 shadow-[var(--shadow-xs)]"
    >
      <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-primary">
            Included in print packet
          </p>
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            Review reliance and provenance before printing
          </h2>
        </div>
        <p className="max-w-xl text-xs leading-5 text-[var(--text-secondary)]">
          These notes are inserted into the printed artifact before the report
          body.
        </p>
      </div>

      <div className={cn("mt-3 rounded-lg border p-3", toneClass)}>
        <p className="text-xs font-semibold uppercase tracking-[0.14em]">
          {packetSummary.label}
        </p>
        <p className="mt-1 text-xs leading-5">{packetSummary.detail}</p>
        <dl className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {(packetSummary.items ?? []).map((item) => (
            <div key={item.label} className="min-w-0">
              <dt className="text-xs font-semibold uppercase tracking-[0.12em] opacity-75">
                {item.label}
              </dt>
              <dd className="mt-0.5 break-words text-xs font-semibold">
                {item.value}
              </dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <PrintPacketPreviewGroup
          title="Reliance boundary"
          items={relianceItems.map((item) => ({
            detail: item.value,
            label: item.label,
          }))}
        />
        <PrintPacketPreviewGroup
          title="AI provenance and evidence scope"
          items={provenanceItems.map((item) => ({
            detail: `${item.value}. ${item.detail}`,
            label: item.label,
          }))}
        />
      </div>
    </section>
  );
}

function PrintReportPacketSummary({
  summary,
}: {
  summary: PrintReportPacketSummary;
}) {
  return (
    <section
      aria-label="Print packet readiness summary"
      className={`print-packet-summary print-packet-summary-${summary.tone ?? "neutral"}`}
      role="region"
    >
      <div className="print-packet-summary-status">
        <p className="print-packet-summary-kicker">Packet readiness</p>
        <p className="print-packet-summary-label">{summary.label}</p>
        <p className="print-packet-summary-detail">{summary.detail}</p>
      </div>
      <dl className="print-packet-summary-grid">
        {(summary.items ?? []).map((item) => (
          <div key={item.label} className="print-packet-summary-item">
            <dt className="print-packet-summary-item-label">{item.label}</dt>
            <dd className="print-packet-summary-item-value">{item.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function getPacketSummaryToneClass(
  tone: PrintReportPacketSummary["tone"] = "neutral",
) {
  if (tone === "ready") {
    return "border-success/25 bg-success/10 text-[var(--text-primary)]";
  }
  if (tone === "warning") {
    return "border-warning/30 bg-warning/10 text-[var(--text-primary)]";
  }
  if (tone === "danger") {
    return "border-error/30 bg-error/8 text-[var(--text-primary)]";
  }
  return "border-brand-primary/20 bg-brand-primary/8 text-[var(--text-primary)]";
}

function PrintPacketPreviewGroup({
  items,
  title,
}: {
  items: Array<{ detail: string; label: string }>;
  title: string;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/45 p-3">
      <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        {title}
      </h3>
      <dl className="mt-2 grid gap-2">
        {items.map((item) => (
          <div key={item.label} className="min-w-0">
            <dt className="text-xs font-semibold text-[var(--text-primary)]">
              {item.label}
            </dt>
            <dd className="mt-0.5 break-words text-xs leading-5 text-[var(--text-secondary)]">
              {item.detail}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export { PrintPageBreak, PrintAvoidBreak } from "./print-report-breaks";
export type { PrintReportBranding } from "./print-report-branding";
