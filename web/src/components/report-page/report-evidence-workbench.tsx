"use client";

import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  Database,
  Download,
  FileSearch,
  FileLock2,
  Hourglass,
  Layers3,
  Link2,
  ShieldCheck,
} from "lucide-react";
import type React from "react";
import type { FTOReport } from "@praviar/shared-types";
import { Badge } from "@/components/ui/badge";
import { sanitizeReportDiagnosticText } from "@/components/report/report-diagnostic-copy";
import { ReportMobileDisclosure } from "@/components/report/report-mobile-disclosure";
import { cn } from "@/lib/utils";
import {
  getCombinedExportReadinessBlockers,
  isHealthySourceStatus,
  type RelianceReadinessInput,
} from "./report-reliance-readiness";

interface ReportEvidenceWorkbenchProps {
  readinessInput?: RelianceReadinessInput;
  report: FTOReport;
}

type ClaimSupportEntry = NonNullable<
  NonNullable<FTOReport["claim_source_span_map"]>["entries"]
>[number];
type SourceSpanMap = NonNullable<
  NonNullable<FTOReport["claim_source_span_map"]>["spans"]
>;
type VerificationCheckItem = NonNullable<
  NonNullable<FTOReport["verification"]>["checks"]
>[number];
type SourceLedgerEntry = {
  source: string;
  status: string;
  patent_count?: number;
  error_message?: string;
};
type ClaimSupportFilter =
  | "all"
  | "needs_review"
  | "missing_span"
  | "unsupported"
  | "supported";
type ClaimSupportLedgerRow = {
  entry: ClaimSupportEntry;
  hasMissingSpan: boolean;
  href: string;
  span: SourceSpanMap[string] | undefined;
  target: string;
};
type EvidenceArtifactStatus =
  | "supported"
  | "needs_review"
  | "rejected"
  | "draft";
type EvidenceArtifact = {
  artifactId: string;
  blocker: string;
  evidenceCount: number;
  href: string;
  row: ClaimSupportLedgerRow;
  sourceScope: string;
  status: EvidenceArtifactStatus;
};

export function ReportEvidenceWorkbench({
  readinessInput,
  report,
}: ReportEvidenceWorkbenchProps) {
  const sourceEntries = getSourceEntries(report);
  const verificationChecks = report.verification?.checks ?? [];
  const sourceSpans: SourceSpanMap = report.claim_source_span_map?.spans ?? {};
  const claimSupportEntries = (
    report.claim_source_span_map?.entries ?? []
  ).filter((entry) => entry.customer_visible !== false);
  const sourceFailures = sourceEntries.filter(
    (entry) => !isHealthySourceStatus(entry.status),
  );
  const sourceLedgerMissing = sourceEntries.length === 0;
  const verificationLedgerMissing = verificationChecks.length === 0;
  const claimSupportLedgerMissing =
    !report.claim_source_span_map || claimSupportEntries.length === 0;
  const verificationIssues = report.verification?.issues ?? [];
  const analysisFailures = report.analysis_failures ?? [];
  const dataLimitations = report.data_limitations ?? [];
  const coverageGaps = report.coverage_gaps ?? [];
  const missingSpanCount = claimSupportEntries.filter((entry) =>
    (entry.source_span_ids ?? []).some((spanId) => !sourceSpans[spanId]),
  ).length;
  const unsupportedCount =
    report.claim_source_span_map?.unsupported_customer_visible_claim_count ??
    claimSupportEntries.filter(
      (entry) => entry.support_status === "unsupported",
    ).length;
  const needsReviewCount =
    report.claim_source_span_map?.needs_review_count ??
    claimSupportEntries.filter(
      (entry) => entry.support_status === "needs_review",
    ).length;
  const supportedCount = claimSupportEntries.filter(
    (entry) => entry.support_status === "supported",
  ).length;
  const passedVerificationCount = verificationChecks.filter((check) =>
    isVerificationCheckPassed(check),
  ).length;
  const warningVerificationCount = verificationChecks.filter(
    (check) =>
      check.severity === "warning" || !isVerificationCheckPassed(check),
  ).length;
  const evidenceQuality = formatEvidenceQuality(
    report.clearance_decision?.evidence_quality,
  );
  const evidenceQualityPercent = normalizeEvidenceQualityPercent(
    report.clearance_decision?.evidence_quality,
  );
  const ledgerRows = claimSupportEntries.map((entry) =>
    buildClaimSupportLedgerRow(entry, sourceSpans),
  );
  const gapItems = buildGapItems({
    analysisFailures,
    claimSupportLedgerMissing,
    dataLimitations,
    evidenceQualityPercent,
    sourceFailures,
    sourceLedgerMissing,
    unsupportedCount,
    needsReviewCount,
    missingSpanCount,
    coverageGaps,
    verificationIssues,
    verificationLedgerMissing,
  });

  return (
    <section
      aria-label="Evidence workbench"
      className="space-y-4 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/40 p-4 shadow-[var(--shadow-xs)]"
      data-testid="report-evidence-workbench"
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-1">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            Evidence workbench
          </p>
          <h3 className="text-lg font-semibold text-[var(--text-primary)]">
            Source ledger and citation verification
          </h3>
          <p className="max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
            Review source coverage, claim support, verifier results, and gaps
            before relying on any generated conclusion.
          </p>
        </div>
        <Badge
          variant={gapItems.length > 0 ? "warning" : "success"}
          className="w-fit uppercase tracking-wide"
        >
          {gapItems.length > 0
            ? `${gapItems.length} review item${gapItems.length === 1 ? "" : "s"}`
            : "No recorded blockers"}
        </Badge>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <EvidenceMetric
          icon={<Database className="h-4 w-4" aria-hidden="true" />}
          label="Source health"
          value={`${countHealthySources(sourceEntries)} / ${sourceEntries.length || report.search_sources_used?.length || 0} healthy`}
          detail={
            sourceLedgerMissing
              ? "Source health ledger not reported"
              : sourceFailures.length > 0
                ? `${sourceFailures.length} source provider${sourceFailures.length === 1 ? "" : "s"} need review`
                : "All reported source providers healthy"
          }
          tone={
            sourceLedgerMissing || sourceFailures.length > 0
              ? "warning"
              : "success"
          }
        />
        <EvidenceMetric
          icon={<ShieldCheck className="h-4 w-4" aria-hidden="true" />}
          label="Verifier checks"
          value={`${passedVerificationCount} / ${verificationChecks.length}`}
          detail={
            verificationLedgerMissing
              ? "Verifier ledger not reported"
              : warningVerificationCount > 0
                ? `${warningVerificationCount} warning${warningVerificationCount === 1 ? "" : "s"}`
                : "Deterministic checks passed"
          }
          tone={
            verificationLedgerMissing || warningVerificationCount > 0
              ? "warning"
              : "success"
          }
        />
        <EvidenceMetric
          icon={<FileSearch className="h-4 w-4" aria-hidden="true" />}
          label="Claim support"
          value={`${supportedCount} supported`}
          detail={
            claimSupportLedgerMissing
              ? "Claim-support ledger not reported"
              : `${needsReviewCount} needs review / ${unsupportedCount} unsupported`
          }
          tone={
            claimSupportLedgerMissing ||
            needsReviewCount > 0 ||
            unsupportedCount > 0
              ? "warning"
              : "success"
          }
        />
        <EvidenceMetric
          icon={<AlertTriangle className="h-4 w-4" aria-hidden="true" />}
          label="Decision-evidence score"
          value={evidenceQuality ?? "Not reported"}
          detail="Weighted decision-input coverage; source health is reported separately"
          tone={
            evidenceQualityPercent === null ||
            evidenceQualityPercent < 80 ||
            analysisFailures.length > 0 ||
            dataLimitations.length > 0
              ? "warning"
              : "neutral"
          }
        />
      </div>

      <ReportMobileDisclosure
        label="Inspect source ledger, citations, and gaps"
        description="Open every source-health receipt, verifier result, and unresolved evidence item."
      >
        <div className="grid items-start gap-4 xl:grid-cols-2">
          <EvidenceLane title="Source ledger">
            {sourceEntries.length > 0 ? (
              <div className="divide-y divide-[var(--border-subtle)]">
                {sourceEntries.map((entry) => (
                  <div
                    key={entry.source}
                    className="grid gap-2 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start"
                  >
                    <div className="min-w-0">
                      <p className="break-words font-mono text-xs font-semibold text-[var(--text-primary)]">
                        {entry.source}
                      </p>
                      <p className="mt-1 text-xs text-[var(--text-secondary)]">
                        {(entry.patent_count ?? 0).toLocaleString()} patent
                        {(entry.patent_count ?? 0) === 1 ? "" : "s"}
                      </p>
                      {entry.error_message ? (
                        <p className="mt-1 text-xs leading-5 text-warning [overflow-wrap:anywhere]">
                          {sanitizeReportDiagnosticText(
                            entry.error_message,
                            "Source returned a diagnostic message for support review.",
                          )}
                        </p>
                      ) : null}
                    </div>
                    <EvidenceStatusBadge status={entry.status} />
                  </div>
                ))}
              </div>
            ) : (
              <EmptyLaneText text="No source health ledger was reported." />
            )}
          </EvidenceLane>

          <div className="min-w-0 xl:col-span-2 xl:row-start-2">
            <EvidenceLane title="Citation verifier">
              {claimSupportEntries.length > 0 ? (
                <div
                  className="grid gap-3 lg:grid-cols-2"
                  data-print-citation-verifier-grid
                >
                  {claimSupportEntries.slice(0, 4).map((entry) => {
                    const span = getFirstSourceSpan(
                      entry.source_span_ids,
                      sourceSpans,
                    );
                    const missingSpan = hasMissingSpans(
                      entry.source_span_ids,
                      sourceSpans,
                    );
                    return (
                      <div
                        key={entry.assertion_id}
                        className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/70 p-3"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-xs font-semibold text-[var(--text-primary)]">
                            {formatClaimTarget(entry)}
                          </p>
                          <Badge
                            variant={getClaimSupportVariant(
                              entry.support_status,
                            )}
                            className="text-xs uppercase"
                          >
                            {formatLabel(
                              entry.support_status ?? "needs_review",
                            )}
                          </Badge>
                        </div>
                        <a
                          href={buildClaimsElementHref(entry)}
                          aria-label={`Open in Claims for ${formatClaimTarget(entry)} (assertion ${entry.assertion_id})`}
                          className="mt-2 inline-flex min-h-11 max-w-full items-center gap-1.5 rounded-md border border-brand-primary/20 bg-brand-primary/8 px-2.5 text-xs font-semibold text-brand-primary transition-colors hover:bg-brand-primary/12"
                        >
                          <Link2
                            className="h-3.5 w-3.5 flex-shrink-0"
                            aria-hidden="true"
                          />
                          <span className="truncate">Open in Claims</span>
                        </a>
                        <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                          {entry.assertion_text}
                        </p>
                        <div className="mt-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)]/60 p-2">
                          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                            Source span
                          </p>
                          <p className="mt-1 text-xs text-[var(--text-primary)]">
                            {span?.citation ?? "Citation not reported"}
                          </p>
                          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                            {span?.excerpt ??
                              (missingSpan
                                ? "Referenced span is missing from the report ledger."
                                : "No source excerpt was reported.")}
                          </p>
                        </div>
                      </div>
                    );
                  })}

                  {verificationChecks.length > 0 ? (
                    <div
                      className="grid gap-2 pt-2 sm:col-span-2 sm:grid-cols-2 xl:grid-cols-4"
                      data-print-verification-checks-grid
                    >
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)] sm:col-span-2 xl:col-span-4">
                        Deterministic checks
                      </p>
                      {verificationChecks.map((check) => (
                        <VerificationCheckCard
                          key={check.check_name}
                          check={check}
                        />
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : verificationChecks.length > 0 ? (
                <div
                  className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4"
                  data-print-verification-checks-grid
                >
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)] sm:col-span-2 xl:col-span-4">
                    Deterministic checks
                  </p>
                  {verificationChecks.map((check) => (
                    <VerificationCheckCard
                      key={check.check_name}
                      check={check}
                    />
                  ))}
                </div>
              ) : (
                <EmptyLaneText text="No claim support or verification checks were reported." />
              )}
            </EvidenceLane>
          </div>

          <div className="min-w-0 xl:col-start-2 xl:row-start-1">
            <EvidenceLane title="Gaps board">
              {gapItems.length > 0 ? (
                <div className="space-y-2">
                  {gapItems.map((item) => (
                    <div
                      key={`${item.label}-${item.detail}`}
                      className="rounded-md border border-warning/20 bg-warning/5 p-3"
                    >
                      <p className="text-xs font-semibold text-[var(--text-primary)]">
                        {item.label}
                      </p>
                      <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                        {item.detail}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyLaneText text="No evidence gaps were recorded for this packet." />
              )}
            </EvidenceLane>
          </div>
        </div>
      </ReportMobileDisclosure>

      <ReportMobileDisclosure
        label={`Inspect ${ledgerRows.length.toLocaleString()} customer-visible assertions`}
        description="Open the counsel work ledger, review filters, and governed packet controls."
      >
        <CounselEvidenceLedger
          readinessInput={readinessInput}
          report={report}
          rows={ledgerRows}
        />
      </ReportMobileDisclosure>
    </section>
  );
}

function CounselEvidenceLedger({
  readinessInput,
  report,
  rows,
}: {
  readinessInput?: RelianceReadinessInput;
  report: FTOReport;
  rows: ClaimSupportLedgerRow[];
}) {
  const [filter, setFilter] = useState<ClaimSupportFilter>("all");
  const [copyState, setCopyState] = useState<"idle" | "copied" | "unavailable">(
    "idle",
  );
  const filteredRows = rows.filter((row) =>
    claimSupportRowMatchesFilter(row, filter),
  );
  const filteredArtifacts = filteredRows.map((row) =>
    buildEvidenceArtifact(report, row),
  );
  const activeFilterLabel = getClaimSupportFilterLabel(filter);
  const isFilteredPacket = filter !== "all";
  const packet = buildCounselEvidencePacket(
    report,
    filteredRows,
    filteredArtifacts,
    {
      filterLabel: activeFilterLabel,
      totalRows: rows.length,
    },
  );
  const packetHref = `data:text/plain;charset=utf-8,${encodeURIComponent(packet)}`;
  const packetDownloadName = `${getReportPacketName(report)}-${
    isFilteredPacket ? `${toDomId(activeFilterLabel)}-` : ""
  }evidence-work-packet.txt`;
  const filters = buildClaimSupportFilters(rows);
  const readinessBlockers = getCombinedExportReadinessBlockers(
    readinessInput ?? {},
  );
  const packetBlockedReason = readinessBlockers[0]
    ? `${readinessBlockers[0].label}: ${readinessBlockers[0].detail}`
    : null;

  const copyPacket = async () => {
    if (packetBlockedReason) {
      setCopyState("unavailable");
      return;
    }
    if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) {
      setCopyState("unavailable");
      return;
    }

    try {
      await navigator.clipboard.writeText(packet);
      setCopyState("copied");
    } catch {
      setCopyState("unavailable");
    }
  };

  return (
    <section
      aria-label="Counsel evidence ledger"
      className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/78 p-4"
      data-testid="counsel-evidence-ledger"
    >
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-start">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
            Counsel evidence ledger
          </p>
          <h4 className="mt-1 text-base font-semibold text-[var(--text-primary)]">
            Customer-visible claim assertions
          </h4>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
            Filter every visible assertion by review state, missing source
            spans, and support status before preparing local work product.
            Export-grade delivery remains governed by the report export flow.
          </p>
          <p className="mt-2 text-xs font-semibold text-warning">
            Packet scope: {activeFilterLabel}, showing{" "}
            {filteredRows.length.toLocaleString()} of{" "}
            {rows.length.toLocaleString()} customer-visible assertion
            {rows.length === 1 ? "" : "s"}.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={copyPacket}
            disabled={Boolean(packetBlockedReason)}
            className="inline-flex min-h-11 items-center gap-2 rounded-md border border-[var(--border-emphasis)] px-3 text-xs font-semibold text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-muted)]"
          >
            <ClipboardList className="h-4 w-4" aria-hidden="true" />
            {copyState === "copied"
              ? "Copied work packet"
              : copyState === "unavailable"
                ? "Copy unavailable"
                : "Copy work packet"}
          </button>
          {packetBlockedReason ? (
            <span className="inline-flex min-h-10 items-center gap-2 rounded-md border border-warning/25 bg-warning/10 px-3 text-xs font-semibold text-warning">
              <Download className="h-4 w-4" aria-hidden="true" />
              Packet blocked
            </span>
          ) : (
            <a
              href={packetHref}
              download={packetDownloadName}
              className="inline-flex min-h-11 items-center gap-2 rounded-md border border-brand-primary/20 bg-brand-primary/8 px-3 text-xs font-semibold text-brand-primary transition-colors hover:bg-brand-primary/12"
            >
              <Download className="h-4 w-4" aria-hidden="true" />
              Download work packet
            </a>
          )}
        </div>
      </div>
      {packetBlockedReason ? (
        <p className="mt-3 rounded-md border border-warning/25 bg-warning/10 p-3 text-xs font-semibold leading-5 text-warning">
          Work-packet export is blocked by readiness state.{" "}
          {packetBlockedReason}
        </p>
      ) : null}

      <div
        role="group"
        aria-label="Evidence ledger filters"
        className="mt-4 flex flex-wrap gap-2"
      >
        {filters.map((item) => (
          <button
            key={item.value}
            type="button"
            onClick={() => setFilter(item.value)}
            aria-pressed={filter === item.value}
            className={cn(
              "inline-flex min-h-11 items-center gap-2 rounded-full border px-3 text-xs font-semibold transition-colors",
              filter === item.value
                ? "border-brand-primary/30 bg-brand-primary/10 text-brand-primary"
                : "border-[var(--border-subtle)] bg-[var(--surface-muted)]/70 text-[var(--text-secondary)] hover:bg-[var(--surface-muted)]",
            )}
          >
            <span>{item.label}</span>
            <span className="rounded-full bg-[var(--bg-surface)] px-1.5 py-0.5 font-mono text-xs">
              {item.count.toLocaleString()}
            </span>
          </button>
        ))}
      </div>

      <EvidenceArtifactBinder artifacts={filteredArtifacts} />

      {filteredRows.length > 0 ? (
        <div
          role="region"
          aria-label="Evidence workbench findings table"
          tabIndex={0}
          className="mt-4 rounded-lg border border-[var(--border-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 sm:overflow-x-auto"
        >
          <table className="block min-w-0 text-left text-sm sm:table sm:min-w-[980px] sm:divide-y sm:divide-[var(--border-subtle)]">
            <thead className="sr-only bg-[var(--surface-muted)]/70 text-xs uppercase tracking-[0.14em] text-[var(--text-tertiary)] sm:not-sr-only sm:table-header-group">
              <tr>
                <th scope="col" className="px-3 py-2 font-semibold">
                  Claim target
                </th>
                <th scope="col" className="px-3 py-2 font-semibold">
                  Support
                </th>
                <th scope="col" className="px-3 py-2 font-semibold">
                  Source span
                </th>
                <th scope="col" className="px-3 py-2 font-semibold">
                  Assertion
                </th>
                <th scope="col" className="px-3 py-2 font-semibold">
                  Action
                </th>
              </tr>
            </thead>
            <tbody className="grid gap-3 p-3 sm:table-row-group sm:divide-y sm:divide-[var(--border-subtle)] sm:p-0">
              {filteredRows.map((row) => (
                <tr
                  key={row.entry.assertion_id}
                  className="grid gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/78 p-3 align-top sm:table-row sm:border-0 sm:bg-transparent sm:p-0"
                >
                  <td className="block min-w-0 px-0 py-0 sm:table-cell sm:min-w-48 sm:px-3 sm:py-3">
                    <span className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)] sm:hidden">
                      Claim target
                    </span>
                    <p className="font-mono text-xs font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
                      {row.target}
                    </p>
                    <p className="mt-1 text-xs text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
                      {row.entry.report_section}
                    </p>
                  </td>
                  <td className="block min-w-0 px-0 py-0 sm:table-cell sm:px-3 sm:py-3">
                    <span className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)] sm:hidden">
                      Support
                    </span>
                    <Badge
                      variant={getClaimSupportVariant(row.entry.support_status)}
                      className="text-xs uppercase"
                    >
                      {formatLabel(row.entry.support_status ?? "needs_review")}
                    </Badge>
                  </td>
                  <td className="block min-w-0 px-0 py-0 sm:table-cell sm:min-w-56 sm:px-3 sm:py-3">
                    <span className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)] sm:hidden">
                      Source span
                    </span>
                    <p
                      className={cn(
                        "text-xs font-semibold [overflow-wrap:anywhere]",
                        row.hasMissingSpan
                          ? "text-warning"
                          : "text-[var(--text-primary)]",
                      )}
                    >
                      {row.hasMissingSpan
                        ? "Missing source span"
                        : (row.span?.span_id ?? "No span referenced")}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere] sm:line-clamp-2">
                      {row.span?.citation ??
                        row.span?.excerpt ??
                        (row.hasMissingSpan
                          ? "Referenced span is absent from the report ledger."
                          : "No source excerpt was reported.")}
                    </p>
                  </td>
                  <td className="block min-w-0 px-0 py-0 sm:table-cell sm:min-w-80 sm:px-3 sm:py-3">
                    <span className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)] sm:hidden">
                      Assertion
                    </span>
                    <p className="text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere] sm:line-clamp-3">
                      {row.entry.assertion_text}
                    </p>
                  </td>
                  <td className="block min-w-0 px-0 py-0 sm:table-cell sm:px-3 sm:py-3">
                    <span className="mb-1 block text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)] sm:hidden">
                      Action
                    </span>
                    <a
                      href={row.href}
                      aria-label={`Open in Claims for ${row.target} (assertion ${row.entry.assertion_id})`}
                      className="inline-flex min-h-11 max-w-full items-center gap-1.5 rounded-md border border-brand-primary/20 bg-brand-primary/8 px-2.5 text-xs font-semibold text-brand-primary transition-colors hover:bg-brand-primary/12"
                    >
                      <Link2
                        className="h-3.5 w-3.5 shrink-0"
                        aria-hidden="true"
                      />
                      <span className="truncate">Claims</span>
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyLaneText text="No visible claim assertions match this filter." />
      )}
    </section>
  );
}

function EvidenceArtifactBinder({
  artifacts,
}: {
  artifacts: EvidenceArtifact[];
}) {
  const stats = buildEvidenceArtifactStats(artifacts);
  const priorityArtifacts = artifacts
    .filter((artifact) => artifact.status !== "supported")
    .slice(0, 4);
  const displayArtifacts =
    priorityArtifacts.length > 0 ? priorityArtifacts : artifacts.slice(0, 4);

  return (
    <section
      aria-label="Evidence artifact binder"
      className="mt-4 rounded-lg border border-brand-primary/15 bg-brand-primary/5 p-4"
      data-testid="evidence-artifact-binder"
    >
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-start">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-primary">
            Evidence artifact binder
          </p>
          <h5 className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
            Derived assertion index
          </h5>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-[var(--text-secondary)]">
            Report-scoped assertion IDs, review state, and source scope for
            every visible claim assertion in this packet.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <ArtifactStat
            icon={<Layers3 className="h-4 w-4" aria-hidden="true" />}
            label="Artifacts"
            value={artifacts.length.toLocaleString()}
          />
          <ArtifactStat
            icon={<CheckCircle2 className="h-4 w-4" aria-hidden="true" />}
            label="Supported"
            value={stats.supported.toLocaleString()}
          />
          <ArtifactStat
            icon={<Hourglass className="h-4 w-4" aria-hidden="true" />}
            label="Needs review"
            value={stats.needs_review.toLocaleString()}
          />
          <ArtifactStat
            icon={<FileLock2 className="h-4 w-4" aria-hidden="true" />}
            label="Blocked"
            value={(stats.rejected + stats.draft).toLocaleString()}
          />
        </div>
      </div>

      {displayArtifacts.length > 0 ? (
        <div className="mt-4 grid gap-2 lg:grid-cols-2">
          {displayArtifacts.map((artifact) => (
            <article
              key={artifact.artifactId}
              className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/78 p-3"
            >
              <div className="flex min-w-0 items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="break-all font-mono text-xs font-semibold text-[var(--text-primary)]">
                    {artifact.artifactId}
                  </p>
                  <p className="mt-1 text-xs text-[var(--text-secondary)]">
                    {artifact.row.target}
                  </p>
                </div>
                <Badge
                  variant={
                    artifact.status === "supported"
                      ? "success"
                      : artifact.status === "rejected"
                        ? "destructive"
                        : "warning"
                  }
                  className="shrink-0 text-xs uppercase"
                >
                  {formatLabel(artifact.status)}
                </Badge>
              </div>
              <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
                <ArtifactDatum
                  label="Source scope"
                  value={artifact.sourceScope}
                />
                <ArtifactDatum label="Gate" value={artifact.blocker} />
              </dl>
              <a
                href={artifact.href}
                aria-label={`Open artifact ${artifact.artifactId} in Claims`}
                className="mt-3 inline-flex min-h-11 max-w-full items-center gap-1.5 rounded-md border border-brand-primary/20 bg-brand-primary/8 px-2.5 text-xs font-semibold text-brand-primary transition-colors hover:bg-brand-primary/12"
              >
                <Link2 className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span className="truncate">Claims anchor</span>
              </a>
            </article>
          ))}
        </div>
      ) : (
        <EmptyLaneText text="No customer-visible evidence artifacts were recorded." />
      )}
    </section>
  );
}

function ArtifactStat({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="min-w-0 rounded-md border border-brand-primary/15 bg-[var(--bg-surface)]/76 p-2">
      <div className="flex items-center gap-1.5 text-brand-primary">
        {icon}
        <p className="truncate text-xs font-semibold uppercase tracking-[0.12em]">
          {label}
        </p>
      </div>
      <p className="mt-2 text-lg font-semibold tabular-nums text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}

function ArtifactDatum({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        {label}
      </dt>
      <dd className="mt-0.5 break-words text-[var(--text-secondary)]">
        {value}
      </dd>
    </div>
  );
}

function EvidenceMetric({
  detail,
  icon,
  label,
  tone,
  value,
}: {
  detail: string;
  icon: React.ReactNode;
  label: string;
  tone: "neutral" | "success" | "warning";
  value: string;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/76 p-3">
      <div className="flex items-center gap-2 text-[var(--text-tertiary)]">
        <span
          className={cn(
            "flex h-8 w-8 items-center justify-center rounded-md border",
            tone === "success" &&
              "border-success/25 bg-success/10 text-success",
            tone === "warning" &&
              "border-warning/25 bg-warning/10 text-warning",
            tone === "neutral" &&
              "border-[var(--border-subtle)] bg-[var(--surface-muted)] text-[var(--text-secondary)]",
          )}
        >
          {icon}
        </span>
        <p className="truncate text-xs font-semibold uppercase tracking-[0.14em]">
          {label}
        </p>
      </div>
      <p className="mt-3 text-xl font-semibold tabular-nums text-[var(--text-primary)]">
        {value}
      </p>
      <p className="mt-1 text-xs text-[var(--text-secondary)]">{detail}</p>
    </div>
  );
}

function EvidenceLane({
  children,
  title,
}: {
  children: React.ReactNode;
  title: string;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/72 p-4">
      <h4 className="text-sm font-semibold text-[var(--text-primary)]">
        {title}
      </h4>
      <div className="mt-3">{children}</div>
    </div>
  );
}

function EmptyLaneText({ text }: { text: string }) {
  return (
    <p className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)]/70 p-3 text-xs text-[var(--text-secondary)]">
      {text}
    </p>
  );
}

function EvidenceStatusBadge({ status }: { status: string }) {
  return (
    <Badge
      variant={isHealthySourceStatus(status) ? "success" : "warning"}
      className="w-fit text-xs uppercase"
    >
      {formatLabel(status || "unknown")}
    </Badge>
  );
}

function getSourceEntries(report: FTOReport): SourceLedgerEntry[] {
  const entries = report.source_health?.entries ?? [];
  if (entries.length > 0) return entries;

  return (report.search_sources_used ?? []).map((source) => ({
    source,
    status: "not_reported" as const,
    patent_count: undefined,
    error_message: "Source was listed, but health status was not reported.",
  }));
}

function countHealthySources(entries: SourceLedgerEntry[]) {
  return entries.filter((entry) => isHealthySourceStatus(entry.status)).length;
}

function formatEvidenceQuality(value: number | undefined) {
  const percent = normalizeEvidenceQualityPercent(value);
  return percent === null ? null : `${Math.round(percent)}%`;
}

function normalizeEvidenceQualityPercent(value: number | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return value <= 1 ? value * 100 : value;
}

function formatLabel(value: string) {
  return value
    .replaceAll("_", " ")
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function VerificationCheckCard({ check }: { check: VerificationCheckItem }) {
  const passed = isVerificationCheckPassed(check);
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/70 p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-semibold text-[var(--text-primary)]">
          {formatLabel(check.check_name)}
        </p>
        <Badge
          variant={passed ? "success" : "warning"}
          className="text-xs uppercase"
        >
          {check.severity ?? (passed ? "pass" : "review")}
        </Badge>
      </div>
      {check.details ? (
        <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
          {sanitizeReportDiagnosticText(
            check.details,
            "Verifier diagnostic details are available to support.",
          )}
        </p>
      ) : null}
    </div>
  );
}

function isVerificationCheckPassed(check: VerificationCheckItem) {
  return check.passed === true || check.severity === "pass";
}

function formatClaimTarget(entry: ClaimSupportEntry) {
  const parts = [
    entry.patent_id,
    entry.claim_number != null ? `claim ${entry.claim_number}` : null,
    entry.element_number != null ? `element ${entry.element_number}` : null,
  ].filter(Boolean);

  return parts.length > 0 ? parts.join(" / ") : entry.report_section;
}

function buildClaimsElementHref(entry: ClaimSupportEntry) {
  const params = new URLSearchParams({ tab: "claims" });
  if (entry.patent_id) params.set("patent", entry.patent_id);
  if (entry.claim_number != null) {
    params.set("claim", String(entry.claim_number));
  }
  if (entry.element_number != null) {
    params.set("element", String(entry.element_number));
  }

  return `?${params.toString()}#${toClaimElementDomId(entry)}`;
}

function toClaimElementDomId(entry: ClaimSupportEntry) {
  return `${toDomId(entry.patent_id || "report-packet")}-claim-${
    entry.claim_number ?? "unknown"
  }-element-${entry.element_number ?? "unknown"}`;
}

function toDomId(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function getClaimSupportVariant(
  status: NonNullable<ClaimSupportEntry["support_status"]> | undefined,
) {
  if (status === "supported") return "success";
  if (status === "unsupported") return "destructive";
  return "warning";
}

function getFirstSourceSpan(
  spanIds: ClaimSupportEntry["source_span_ids"] | undefined,
  spans: SourceSpanMap,
) {
  const firstSpanId = spanIds?.[0];
  return firstSpanId ? spans?.[firstSpanId] : undefined;
}

function hasMissingSpans(
  spanIds: ClaimSupportEntry["source_span_ids"] | undefined,
  spans: SourceSpanMap,
) {
  return Boolean(spanIds?.some((spanId) => !spans?.[spanId]));
}

function buildClaimSupportLedgerRow(
  entry: ClaimSupportEntry,
  spans: SourceSpanMap,
): ClaimSupportLedgerRow {
  return {
    entry,
    hasMissingSpan: hasMissingSpans(entry.source_span_ids, spans),
    href: buildClaimsElementHref(entry),
    span: getFirstSourceSpan(entry.source_span_ids, spans),
    target: formatClaimTarget(entry),
  };
}

function claimSupportRowMatchesFilter(
  row: ClaimSupportLedgerRow,
  filter: ClaimSupportFilter,
) {
  if (filter === "all") return true;
  if (filter === "missing_span") return row.hasMissingSpan;
  return row.entry.support_status === filter;
}

function buildClaimSupportFilters(rows: ClaimSupportLedgerRow[]) {
  const count = (filter: ClaimSupportFilter) =>
    rows.filter((row) => claimSupportRowMatchesFilter(row, filter)).length;

  return [
    { count: rows.length, label: "All", value: "all" },
    {
      count: count("needs_review"),
      label: "Needs review",
      value: "needs_review",
    },
    {
      count: count("missing_span"),
      label: "Missing spans",
      value: "missing_span",
    },
    { count: count("unsupported"), label: "Unsupported", value: "unsupported" },
    { count: count("supported"), label: "Supported", value: "supported" },
  ] satisfies Array<{
    count: number;
    label: string;
    value: ClaimSupportFilter;
  }>;
}

function getClaimSupportFilterLabel(filter: ClaimSupportFilter) {
  const labels = {
    all: "All assertions",
    missing_span: "Missing spans",
    needs_review: "Needs review",
    supported: "Supported",
    unsupported: "Unsupported",
  } satisfies Record<ClaimSupportFilter, string>;

  return labels[filter];
}

function buildEvidenceArtifact(
  report: FTOReport,
  row: ClaimSupportLedgerRow,
): EvidenceArtifact {
  const sourceIds = row.entry.source_span_ids ?? [];
  const evidenceCount = sourceIds.length;
  const missingSource = row.hasMissingSpan || sourceIds.length === 0;
  const status = getEvidenceArtifactStatus(row);

  return {
    artifactId: [
      getReportPacketName(report),
      row.entry.assertion_id || toDomId(row.target),
    ].join(":"),
    blocker: getEvidenceArtifactBlocker(row),
    evidenceCount,
    href: row.href,
    row,
    sourceScope: missingSource
      ? "Source scope incomplete"
      : `${evidenceCount.toLocaleString()} source span${evidenceCount === 1 ? "" : "s"}`,
    status,
  };
}

function getEvidenceArtifactStatus(
  row: ClaimSupportLedgerRow,
): EvidenceArtifactStatus {
  if (row.entry.support_status === "unsupported") return "rejected";
  if (row.hasMissingSpan || row.entry.support_status === "needs_review") {
    return "needs_review";
  }
  if (row.entry.support_status === "supported") return "supported";
  return "draft";
}

function getEvidenceArtifactBlocker(row: ClaimSupportLedgerRow) {
  if (row.hasMissingSpan) return "Missing source span";
  if (row.entry.support_status === "unsupported") return "Unsupported claim";
  if (row.entry.support_status === "needs_review")
    return "Reviewer confirmation";
  if (row.entry.support_status === "supported") return "Ready for appendix";
  return "Status not recorded";
}

function buildEvidenceArtifactStats(artifacts: EvidenceArtifact[]) {
  return artifacts.reduce(
    (acc, artifact) => {
      acc[artifact.status] += 1;
      return acc;
    },
    {
      supported: 0,
      draft: 0,
      needs_review: 0,
      rejected: 0,
    } satisfies Record<EvidenceArtifactStatus, number>,
  );
}

function buildCounselEvidencePacket(
  report: FTOReport,
  rows: ClaimSupportLedgerRow[],
  artifacts: EvidenceArtifact[],
  scope: {
    filterLabel: string;
    totalRows: number;
  },
) {
  const lines = [
    "Praviar local evidence work packet",
    "This packet is local work product from the Evidence tab, not an export-grade legal deliverable.",
    `Report: ${report.report_id ?? "not reported"}`,
    `Generated: ${report.generated_at ?? "not reported"}`,
    `Filter: ${scope.filterLabel}`,
    `Rows: ${rows.length.toLocaleString()} of ${scope.totalRows.toLocaleString()}`,
    "",
    "Evidence artifact binder",
    ...artifacts.flatMap((artifact, index) => [
      `${index + 1}. ${artifact.artifactId}`,
      `Status: ${formatLabel(artifact.status)}`,
      `Evidence references: ${artifact.evidenceCount.toLocaleString()}`,
      `Source scope: ${artifact.sourceScope}`,
      `Gate: ${artifact.blocker}`,
      `Claims link: ${artifact.href}`,
      "",
    ]),
    "Claim assertion ledger",
    "",
  ];

  rows.forEach((row, index) => {
    lines.push(
      `${index + 1}. ${row.target}`,
      `Assertion ID: ${row.entry.assertion_id}`,
      `Support: ${formatLabel(row.entry.support_status ?? "needs_review")}`,
      `Report section: ${row.entry.report_section}`,
      `Claims link: ${row.href}`,
      `Source span: ${
        row.hasMissingSpan
          ? "missing referenced span"
          : (row.span?.span_id ?? "not referenced")
      }`,
      `Citation: ${row.span?.citation ?? "not reported"}`,
      `Excerpt: ${row.span?.excerpt ?? "not reported"}`,
      `Assertion: ${row.entry.assertion_text}`,
      "",
    );
  });

  return lines.join("\n");
}

function getReportPacketName(report: FTOReport) {
  return toDomId(report.report_id ?? "praviar-report");
}

function buildGapItems({
  analysisFailures,
  claimSupportLedgerMissing,
  coverageGaps,
  dataLimitations,
  evidenceQualityPercent,
  missingSpanCount,
  needsReviewCount,
  sourceFailures,
  sourceLedgerMissing,
  unsupportedCount,
  verificationIssues,
  verificationLedgerMissing,
}: {
  analysisFailures: NonNullable<FTOReport["analysis_failures"]>;
  claimSupportLedgerMissing: boolean;
  coverageGaps: NonNullable<FTOReport["coverage_gaps"]>;
  dataLimitations: NonNullable<FTOReport["data_limitations"]>;
  evidenceQualityPercent: number | null;
  missingSpanCount: number;
  needsReviewCount: number;
  sourceFailures: SourceLedgerEntry[];
  sourceLedgerMissing: boolean;
  unsupportedCount: number;
  verificationIssues: string[];
  verificationLedgerMissing: boolean;
}) {
  return [
    ...(evidenceQualityPercent === null
      ? [
          {
            label: "Decision-evidence score missing",
            detail:
              "Weighted decision-input coverage was not reported, so decision-evidence completeness cannot be confirmed.",
          },
        ]
      : evidenceQualityPercent < 80
        ? [
            {
              label: "Decision-evidence score below review threshold",
              detail: `Weighted decision-input coverage is ${evidenceQualityPercent}%; review unresolved evidence before reliance.`,
            },
          ]
        : []),
    ...(sourceLedgerMissing
      ? [
          {
            label: "Source health ledger missing",
            detail:
              "Source health was not reported, so provider coverage cannot be confirmed.",
          },
        ]
      : []),
    ...(verificationLedgerMissing
      ? [
          {
            label: "Verifier ledger missing",
            detail:
              "Deterministic verification checks were not reported and cannot be confirmed.",
          },
        ]
      : []),
    ...(claimSupportLedgerMissing
      ? [
          {
            label: "Claim-support ledger missing",
            detail:
              "Customer-visible claim support was not reported and cannot be relied upon.",
          },
        ]
      : []),
    ...(missingSpanCount > 0
      ? [
          {
            label: "Missing source spans",
            detail: `${missingSpanCount} referenced source span${missingSpanCount === 1 ? "" : "s"} are absent from the report ledger.`,
          },
        ]
      : []),
    ...(unsupportedCount > 0
      ? [
          {
            label: "Unsupported claim assertions",
            detail: `${unsupportedCount} customer-visible assertion${unsupportedCount === 1 ? "" : "s"} lack source support.`,
          },
        ]
      : []),
    ...(needsReviewCount > 0
      ? [
          {
            label: "Claim assertions need review",
            detail: `${needsReviewCount} assertion${needsReviewCount === 1 ? "" : "s"} require reviewer confirmation.`,
          },
        ]
      : []),
    ...sourceFailures.map((entry) => ({
      label: `Source ${entry.source}`,
      detail: sanitizeReportDiagnosticText(
        entry.error_message,
        `Status: ${entry.status}`,
      ),
    })),
    ...verificationIssues.map((issue) => ({
      label: "Verifier issue",
      detail: sanitizeReportDiagnosticText(
        issue,
        "Verifier diagnostic details are available to support.",
      ),
    })),
    ...analysisFailures.map((failure) => ({
      label: `Analysis failure ${failure.patent_id}`,
      detail: `${failure.step}: ${failure.error_type} - ${sanitizeReportDiagnosticText(
        failure.error_message,
        "Analysis diagnostic details are available to support.",
      )}`,
    })),
    ...dataLimitations.map((limitation) => ({
      label: formatLabel(limitation.category),
      detail: `${sanitizeReportDiagnosticText(
        limitation.description,
        "Data limitation details are available to support.",
      )} Impact: ${sanitizeReportDiagnosticText(
        limitation.impact,
        "Impact details are available to support.",
      )}`,
    })),
    ...coverageGaps.map((gap) => ({
      label: formatLabel(gap.gap_type ?? "coverage_gap"),
      detail: [
        sanitizeReportDiagnosticText(
          gap.description,
          "Coverage gap details are available to support.",
        ),
        gap.suggested_action
          ? sanitizeReportDiagnosticText(
              gap.suggested_action,
              "Suggested action details are available to support.",
            )
          : null,
      ]
        .filter(Boolean)
        .join(" Action: "),
    })),
  ];
}
