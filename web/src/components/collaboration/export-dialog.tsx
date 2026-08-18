"use client";

import { type ReactNode, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ClipboardList,
  Copy,
  DatabaseZap,
  FileCheck2,
  Scale,
  type LucideIcon,
  X,
} from "lucide-react";
import { ExportDialogActions } from "@/components/collaboration/export-dialog-actions";
import { ExportDialogAudienceSelector } from "@/components/collaboration/export-dialog-audience-selector";
import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import { RiskBadge } from "@/components/shared/risk-badge";
import {
  ClaimedUseReceiptLedger,
  type ClaimedUseReceiptLedgerState,
} from "@/components/report/claimed-use-receipt-ledger";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useExportReport, useExportStatus } from "@/hooks/use-export";
import { useToastStore } from "@/stores/toast-store";
import { ExportDialogFormatOptions } from "@/components/collaboration/export-dialog-format-options";
import { ExportDialogSectionSelector } from "@/components/collaboration/export-dialog-section-selector";
import { ExportDialogStatus } from "@/components/collaboration/export-dialog-status";
import {
  AUDIENCE_PACKET_REQUIREMENTS,
  type ExportAudience,
  type ExportFormat,
  type ExportSection,
  getAudienceDefaultSections,
  getAudienceLabel,
  getExportArtifactLabel,
  getExportFormatLabel,
  getExportSectionLabel,
  getMissingAudienceRequiredSections,
  hasExportContentSection,
  hasRequiredExportSections,
} from "@/components/collaboration/export-dialog-constants";
import {
  getDefaultExportSections,
  toggleExportSection,
} from "@/components/collaboration/export-dialog-helpers";
import { useExportDialogFocusTrap } from "@/components/collaboration/use-export-dialog-focus-trap";
import {
  formatReportRiskLabel,
  getReportReference,
} from "@/components/report-page/report-command-summary";
import { getReviewLedgerSummary } from "@/components/report/review-ledger-summary";
import { APIError, isAuthBoundaryError } from "@/lib/api-client";
import {
  getCombinedExportReadinessBlockers,
  getExportDisabledReason,
  getRelianceLifecycleState,
  getReviewerDecisionExportBlockers,
  getReportSourceHealthReadiness,
  getWorkspaceBlockingJurisdictions,
  getWorkspaceExportReady,
  getWorkspaceOpinionSummary,
  type RelianceReadinessInput,
} from "@/components/report-page/report-reliance-readiness";
import { cn } from "@/lib/utils";
import { logError } from "@/lib/error-logger";
import type { AnalysisReviewStatusResponse } from "@/hooks/use-analysis-review-status";
import type { ReportWorkspaceSummaryResponse } from "@/hooks/use-report-workspace-summary";
import type { ReviewerDecisionListResponse } from "@/hooks/use-reviewer-decisions";
import type { FTOReport, RiskLevel } from "@praviar/shared-types";

const VERIFIED_CLAIM_CHART_PACKET_SECTIONS: readonly ExportSection[] = [
  "patent_analysis",
  "claim_charts",
  "audit_trail",
  "pipeline_metadata",
];
const EXPORT_FORMAT_FALLBACK_ORDER: readonly ExportFormat[] = [
  "pdf",
  "csv",
  "xlsx",
  "json",
  "docx",
  "pptx",
];
type ExportReadinessBlockerList = ReturnType<
  typeof getCombinedExportReadinessBlockers
>;
type ExportUserRole = "admin" | "attorney" | "scientist" | "client" | "unknown";
type ExportRoleResolutionState = "ready" | "loading" | "unavailable";

const NO_EXPORT_FORMAT_RESTRICTIONS = {} satisfies Partial<
  Record<ExportFormat, string>
>;
const SCIENTIST_EXPORT_FORMAT_RESTRICTIONS = {
  docx: "Attorney/admin only. Use PDF, CSV, XLSX, or JSON, or ask counsel to generate the Word Review Memo.",
  pptx: "Attorney/admin only. Use PDF, CSV, XLSX, or JSON, or ask counsel to generate the board deck.",
} satisfies Partial<Record<ExportFormat, string>>;
const CLIENT_EXPORT_FORMAT_RESTRICTIONS = {
  pdf: "Client role cannot export full report packets.",
  docx: "Client role cannot export full report packets.",
  pptx: "Client role cannot export full report packets.",
  csv: "Client role cannot export full report packets.",
  xlsx: "Client role cannot export full report packets.",
  json: "Client role cannot export full report packets.",
} satisfies Partial<Record<ExportFormat, string>>;
const UNKNOWN_EXPORT_FORMAT_RESTRICTIONS = {
  pdf: "Export role unavailable. Refresh access before preparing a packet.",
  docx: "Export role unavailable. Refresh access before preparing a packet.",
  pptx: "Export role unavailable. Refresh access before preparing a packet.",
  csv: "Export role unavailable. Refresh access before preparing a packet.",
  xlsx: "Export role unavailable. Refresh access before preparing a packet.",
  json: "Export role unavailable. Refresh access before preparing a packet.",
} satisfies Partial<Record<ExportFormat, string>>;
const LOADING_EXPORT_FORMAT_RESTRICTIONS = {
  pdf: "Confirming export role before preparing a packet.",
  docx: "Confirming export role before preparing a packet.",
  pptx: "Confirming export role before preparing a packet.",
  csv: "Confirming export role before preparing a packet.",
  xlsx: "Confirming export role before preparing a packet.",
  json: "Confirming export role before preparing a packet.",
} satisfies Partial<Record<ExportFormat, string>>;
const UNAVAILABLE_EXPORT_FORMAT_RESTRICTIONS = {
  pdf: "Report metadata unavailable. Retry report access before preparing a packet.",
  docx: "Report metadata unavailable. Retry report access before preparing a packet.",
  pptx: "Report metadata unavailable. Retry report access before preparing a packet.",
  csv: "Report metadata unavailable. Retry report access before preparing a packet.",
  xlsx: "Report metadata unavailable. Retry report access before preparing a packet.",
  json: "Report metadata unavailable. Retry report access before preparing a packet.",
} satisfies Partial<Record<ExportFormat, string>>;

interface ExportDialogProps {
  reportId: string;
  report?: FTOReport;
  open: boolean;
  reviewStatus?: AnalysisReviewStatusResponse;
  reviewStatusLoading?: boolean;
  reviewerDecisions?: ReviewerDecisionListResponse | null;
  reviewerDecisionsLoading?: boolean;
  shareActive?: boolean;
  shareLastViewedAt?: string | null;
  shareRecipientBound?: boolean;
  shareViewCount?: number | null;
  workspaceSummary?: ReportWorkspaceSummaryResponse;
  workspaceSummaryLoading?: boolean;
  currentUserRole?: string | null;
  currentUserRoleState?: ExportRoleResolutionState;
  claimedUseReceiptState?: ClaimedUseReceiptLedgerState;
  onRefreshCurrentUserRole?: () => void;
  onClose: () => void;
}

export function ExportDialog({
  currentUserRole,
  currentUserRoleState = "ready",
  ...props
}: ExportDialogProps) {
  if (!props.open) return null;
  if (typeof document === "undefined") return null;

  return renderExportDialogPortal({
    ...props,
    currentUserRole: normalizeExportUserRole(currentUserRole),
    currentUserRoleState,
  });
}

function renderExportDialogPortal({
  report,
  reportId,
  reviewStatus,
  reviewStatusLoading,
  reviewerDecisions,
  reviewerDecisionsLoading,
  shareActive,
  shareLastViewedAt,
  shareRecipientBound,
  shareViewCount,
  workspaceSummary,
  workspaceSummaryLoading,
  currentUserRole,
  currentUserRoleState = "ready",
  claimedUseReceiptState,
  onRefreshCurrentUserRole,
  onClose,
}: Omit<ExportDialogProps, "currentUserRole"> & {
  currentUserRole: ExportUserRole;
}) {
  return createPortal(
    <OpenExportDialog
      reportId={reportId}
      report={report}
      reviewStatus={reviewStatus}
      reviewStatusLoading={reviewStatusLoading}
      reviewerDecisions={reviewerDecisions}
      reviewerDecisionsLoading={reviewerDecisionsLoading}
      shareActive={shareActive}
      shareLastViewedAt={shareLastViewedAt}
      shareRecipientBound={shareRecipientBound}
      shareViewCount={shareViewCount}
      workspaceSummary={workspaceSummary}
      workspaceSummaryLoading={workspaceSummaryLoading}
      currentUserRole={currentUserRole}
      currentUserRoleState={currentUserRoleState}
      claimedUseReceiptState={claimedUseReceiptState}
      onRefreshCurrentUserRole={onRefreshCurrentUserRole}
      onClose={onClose}
    />,
    document.body,
  );
}

function OpenExportDialog({
  report,
  reportId,
  reviewStatus,
  reviewStatusLoading,
  reviewerDecisions,
  reviewerDecisionsLoading,
  shareActive,
  shareLastViewedAt,
  shareRecipientBound,
  shareViewCount,
  workspaceSummary,
  workspaceSummaryLoading,
  currentUserRole,
  currentUserRoleState = "ready",
  claimedUseReceiptState,
  onRefreshCurrentUserRole,
  onClose,
}: Omit<ExportDialogProps, "open" | "currentUserRole"> & {
  currentUserRole: ExportUserRole;
}) {
  const token = useAuthToken();
  const toast = useToastStore();
  const exportMutation = useExportReport(token);
  const [audience, setAudience] = useState<ExportAudience>("full");
  const [selectedFormat, setSelectedFormat] = useState<ExportFormat>("pdf");
  const [jobId, setJobId] = useState<string | null>(null);
  const { data: jobStatus, isPollingCapped } = useExportStatus(jobId, token);
  const [selectedSections, setSelectedSections] = useState<Set<ExportSection>>(
    getDefaultExportSections,
  );
  const [sourceCaveatAcknowledged, setSourceCaveatAcknowledged] =
    useState(false);
  const exportAccessScopeKey = JSON.stringify([reportId, token ?? null]);
  const [exportAccessRestrictedScopeKey, setExportAccessRestrictedScopeKey] =
    useState<string | null>(null);
  const exportAccessRestricted =
    exportAccessRestrictedScopeKey === exportAccessScopeKey;
  const dialogRef = useRef<HTMLDivElement>(null);
  const blockedRoleResolutionState =
    currentUserRoleState === "ready" ? null : currentUserRoleState;
  const roleResolutionBlocksExport = blockedRoleResolutionState !== null;
  const formatRestrictions = getExportFormatRestrictions(
    currentUserRole,
    currentUserRoleState,
  );
  const activeSelectedFormat = getActiveExportFormat(
    selectedFormat,
    formatRestrictions,
  );
  const selectedFormatRestriction =
    formatRestrictions[activeSelectedFormat] ?? null;

  useExportDialogFocusTrap(true, onClose, dialogRef);

  // Clear the completed/failed job result when the user changes export options
  // after a job finishes — the old download URL would otherwise show as "ready"
  // for the new (unsent) configuration. Also clears a poll-capped retryable job.
  const clearJobIfTerminal = () => {
    if (
      jobStatus?.status === "completed" ||
      jobStatus?.status === "failed" ||
      isPollingCapped
    ) {
      setJobId(null);
    }
  };

  const applyVerifiedClaimChartPacket = () => {
    if (!hasClaimChartData || formatRestrictions.docx) return;
    clearJobIfTerminal();
    setSelectedFormat("docx");
    setAudience("attorney");
    setSelectedSections(new Set(VERIFIED_CLAIM_CHART_PACKET_SECTIONS));
  };

  const handleExport = async () => {
    if (exportAccessRestricted) return;

    const selectedRestriction = formatRestrictions[activeSelectedFormat];
    if (selectedRestriction) {
      toast.addToast(selectedRestriction, "error");
      return;
    }

    try {
      const result = await exportMutation.mutateAsync({
        report_id: reportId,
        format: activeSelectedFormat,
        sections: Array.from(selectedSections),
        audience,
      });
      setJobId(result.job_id);
      toast.addToast(
        "Export started — you'll be notified when ready",
        "success",
      );
    } catch (err) {
      if (isAuthBoundaryError(err)) {
        setJobId(null);
        setExportAccessRestrictedScopeKey(exportAccessScopeKey);
        toast.addToast(
          "Export access restricted. Packet controls are locked until access is restored.",
          "error",
        );
        return;
      }
      logError(new Error("Export could not be started"), {
        source: "ExportDialog",
        extra: { action: "start_export", format: activeSelectedFormat },
      });
      toast.addToast(
        getExportStartFailureMessage(err, {
          verifiedClaimChartPacketActive,
        }),
        "error",
      );
    }
  };

  const isCompleted = jobStatus?.status === "completed";
  const isRetryableFailure = Boolean(jobStatus?.retryable) && !isPollingCapped;
  const isFailed = jobStatus?.status === "failed" && !jobStatus.retryable;
  // Treat the gap between mutation resolving and first poll returning as processing
  // to prevent a double-submit while jobStatus is still undefined.
  const isAwaitingFirstStatus = jobId !== null && jobStatus === undefined;
  const isProcessing =
    exportMutation.isPending ||
    isAwaitingFirstStatus ||
    jobStatus?.status === "processing" ||
    jobStatus?.status === "pending" ||
    isRetryableFailure;
  const exportControlsLocked =
    isProcessing || exportAccessRestricted || roleResolutionBlocksExport;
  const reviewerDecisionBlockers = getReviewerDecisionExportBlockers({
    report,
    reviewStatus,
    reviewerDecisions,
    reviewerDecisionsLoading,
  });
  const readinessInput = {
    additionalBlockers: reviewerDecisionBlockers,
    reviewStatus,
    reviewStatusLoading,
    workspaceSummary,
    workspaceSummaryLoading,
  };
  const exportDisabledReason = getExportDisabledReason(readinessInput);
  const hasRequiredSections = hasRequiredExportSections(selectedSections);
  const hasContentSections = hasExportContentSection(selectedSections);
  const missingAudienceSections = getMissingAudienceRequiredSections(
    audience,
    selectedSections,
  );
  const reportReference = report ? getReportReference(report) : reportId;
  const compoundName = report?.compound?.name ?? "Report packet";
  const risk = report?.risk_summary.overall_risk as RiskLevel | undefined;
  const riskLabel = risk ? formatReportRiskLabel(risk) : null;
  const sourceHealth = getReportSourceHealthReadiness(report);
  const claimChartCount = getReportClaimChartCount(report);
  const hasClaimChartData = claimChartCount > 0;
  const verifiedClaimChartPacketActive = isVerifiedClaimChartPacket({
    audience,
    selectedFormat: activeSelectedFormat,
    selectedSections,
  });
  const exportActionState = getExportActionState({
    audience,
    exportDisabledReason,
    hasContentSections,
    hasRequiredSections,
    isProcessing,
    missingAudienceSections,
    selectedSections,
    sourceCaveatAcknowledged,
    sourceHealth,
  });
  const effectiveExportActionState = exportAccessRestricted
    ? {
        ...exportActionState,
        isDisabled: true,
        disabledReason:
          "Your current session is not authorized to start exports for this report. Refresh access before preparing a packet.",
        disabledTone: "danger" as const,
        buttonLabel: "Access restricted",
      }
    : roleResolutionBlocksExport
      ? {
          ...exportActionState,
          isDisabled: true,
          disabledReason:
            currentUserRoleState === "loading"
              ? "Confirming your export role before preparing a packet."
              : "Report metadata is unavailable. Retry report access before preparing a packet.",
          disabledTone:
            currentUserRoleState === "loading"
              ? ("neutral" as const)
              : ("danger" as const),
          buttonLabel:
            currentUserRoleState === "loading"
              ? "Confirming role"
              : "Export unavailable",
        }
      : selectedFormatRestriction
        ? {
            ...exportActionState,
            isDisabled: true,
            disabledReason: selectedFormatRestriction,
            disabledTone: "neutral" as const,
            buttonLabel: "Choose another format",
          }
        : exportActionState;
  const isExportDisabled = effectiveExportActionState.isDisabled;
  const aiReviewNotice =
    reviewStatus?.status === "approved"
      ? "AI scoped evidence and blockers; counsel review recorded."
      : "AI scoped evidence and blockers; counsel review required.";
  const readinessBlockers = getCombinedExportReadinessBlockers(readinessInput);
  const handoffPrompts = getExportHandoffPrompts({
    blockers: readinessBlockers,
    riskLabel,
    sourceCaveatAcknowledged,
    sourceHealth,
  });
  const handoffBrief = buildExportHandoffBrief({
    audience,
    blockers: readinessBlockers,
    compoundName,
    handoffPrompts,
    reportReference,
    riskLabel,
    selectedFormat: activeSelectedFormat,
    selectedSections,
    sourceCaveatAcknowledged,
    sourceHealth,
  });
  const manifestPreview = buildExportManifestPreview({
    audience,
    blockers: readinessBlockers,
    compoundName,
    report,
    reportReference,
    reviewStatus,
    reviewStatusLoading,
    riskLabel,
    selectedFormat: activeSelectedFormat,
    selectedSections,
    shareActive,
    shareLastViewedAt,
    shareRecipientBound,
    shareViewCount,
    sourceCaveatAcknowledged,
    sourceHealth,
    workspaceSummary,
    workspaceSummaryLoading,
  });
  const decisionSummaryItems = getExportDecisionSummaryItems({
    audience,
    exportActionState: effectiveExportActionState,
    isProcessing,
    reviewStatus,
    reviewStatusLoading,
    selectedFormat: activeSelectedFormat,
    selectedSections,
    sourceCaveatAcknowledged,
    sourceHealth,
  });

  const handleCopyHandoffBrief = async () => {
    try {
      if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) {
        throw new Error("Clipboard API unavailable");
      }
      await navigator.clipboard.writeText(handoffBrief);
      toast.addToast("Readiness brief copied", "success");
    } catch {
      logError(new Error("Readiness brief could not be copied"), {
        source: "ExportDialog",
        extra: { action: "copy_handoff_brief" },
      });
      toast.addToast("Unable to copy readiness brief", "error");
    }
  };

  const handleCopyManifestPreview = async () => {
    try {
      if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) {
        throw new Error("Clipboard API unavailable");
      }
      await navigator.clipboard.writeText(manifestPreview.text);
      toast.addToast("Export manifest copied", "success");
    } catch {
      logError(new Error("Export manifest could not be copied"), {
        source: "ExportDialog",
        extra: { action: "copy_manifest_preview" },
      });
      toast.addToast("Unable to copy export manifest", "error");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="praviar-overlay-scrim absolute inset-0"
        onClick={onClose}
      />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="export-dialog-title"
        className="praviar-dialog-panel relative mx-3 flex max-h-[min(94dvh,860px)] w-full max-w-[60rem] flex-col overflow-hidden rounded-lg shadow-[0_24px_80px_rgba(11,31,36,0.24)]"
      >
        <button
          onClick={onClose}
          aria-label="Close export dialog"
          className="absolute right-4 top-4 z-10 flex h-11 w-11 items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-surface)_86%,transparent)] text-[var(--text-tertiary)] shadow-[var(--shadow-xs)] backdrop-blur-sm transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)]"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="min-h-0 overflow-y-auto pb-24 sm:pb-28">
          <div className="praviar-share-handoff-field border-b border-[var(--border-default)] px-5 pb-4 pt-5 sm:px-6">
            <div className="flex min-w-0 items-start gap-3 pr-12">
              <PraviarMarkFrame size="dialog" />
              <div className="min-w-0">
                <h3
                  id="export-dialog-title"
                  className="type-heading-sm text-[var(--text-primary)]"
                >
                  Export evidence packet
                </h3>
                <p className="mt-1 max-w-2xl text-sm leading-6 text-[var(--text-secondary)]">
                  Build a review evidence export with source links, section
                  scope, and caveats preserved.
                </p>
              </div>
            </div>

            <div
              className="mt-4 grid gap-3 rounded-lg border border-[var(--border-default)] bg-[color-mix(in_srgb,var(--bg-surface)_70%,transparent)] p-3 text-sm shadow-[var(--shadow-xs)] md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(13rem,0.72fr)]"
              role="group"
              aria-label="Export report identity"
            >
              <ExportIdentityField
                label="Report"
                value={reportReference}
                mono
              />
              <ExportIdentityField
                label="Compound"
                value={compoundName}
                risk={risk}
                riskLabel={riskLabel}
              />
              <div className="flex min-w-0 items-start gap-2 rounded-md border border-warning/20 bg-warning/10 px-3 py-2 text-warning">
                <AlertTriangle
                  className="mt-0.5 h-4 w-4 shrink-0"
                  aria-hidden="true"
                />
                <p className="text-xs font-semibold leading-5 text-[var(--text-secondary)]">
                  {aiReviewNotice}
                </p>
              </div>
            </div>

            {readinessBlockers.length > 0 ? (
              <ExportBlockerCallout blockers={readinessBlockers} />
            ) : null}

            {exportAccessRestricted ? <ExportAccessRestrictedCallout /> : null}
            {roleResolutionBlocksExport ? (
              <ExportRoleResolutionCallout
                state={blockedRoleResolutionState}
                onRetry={onRefreshCurrentUserRole}
              />
            ) : null}

            {claimedUseReceiptState ? (
              <ClaimedUseReceiptLedger
                state={claimedUseReceiptState}
                variant="export"
              />
            ) : null}

            <VerifiedClaimChartPacketShortcut
              active={verifiedClaimChartPacketActive}
              claimChartCount={claimChartCount}
              disabled={
                exportControlsLocked ||
                !hasClaimChartData ||
                Boolean(formatRestrictions.docx)
              }
              disabledReason={formatRestrictions.docx}
              onApply={applyVerifiedClaimChartPacket}
            />

            <ExportReviewDetails
              blockers={readinessBlockers}
              manifest={manifestPreview}
            >
              <ExportReadinessBrief
                audience={audience}
                selectedFormat={activeSelectedFormat}
                selectedSections={selectedSections}
                blockers={readinessBlockers}
                sourceHealth={sourceHealth}
                sourceCaveatAcknowledged={sourceCaveatAcknowledged}
                reviewApproved={reviewStatus?.status === "approved"}
                handoffPrompts={handoffPrompts}
                onCopyHandoffBrief={handleCopyHandoffBrief}
              />
              <ExportManifestPreview
                manifest={manifestPreview}
                onCopyManifest={handleCopyManifestPreview}
              />
            </ExportReviewDetails>
          </div>

          <div className="grid gap-6 px-5 py-5 lg:grid-cols-[minmax(18rem,0.82fr)_minmax(0,1fr)] lg:gap-7 sm:px-6">
            <section
              aria-labelledby="export-format-heading"
              className="min-w-0"
            >
              <div className="mb-3">
                <h4
                  id="export-format-heading"
                  className="text-sm font-semibold text-[var(--text-primary)]"
                >
                  1. Choose export format
                </h4>
                <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                  Select the file format for this evidence packet.
                </p>
              </div>
              <ExportDialogFormatOptions
                selectedFormat={activeSelectedFormat}
                disabled={exportControlsLocked}
                formatRestrictions={formatRestrictions}
                onSelect={(v) => {
                  clearJobIfTerminal();
                  setSelectedFormat(v);
                }}
              />
              <div
                className={cn(
                  "mt-3 flex items-start gap-2 rounded-md border px-3 py-2 text-xs leading-5",
                  sourceHealth.hasCaveats
                    ? "border-warning/20 bg-warning/10 text-[var(--text-secondary)]"
                    : "border-brand-primary/15 bg-brand-primary/8 text-[var(--text-secondary)]",
                )}
              >
                {sourceHealth.hasCaveats ? (
                  <AlertTriangle
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning"
                    aria-hidden="true"
                  />
                ) : (
                  <CheckCircle2
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-primary"
                    aria-hidden="true"
                  />
                )}
                <p>
                  {sourceHealth.hasCaveats
                    ? `Source audit caveat: ${sourceHealth.detail}`
                    : "Source audit, jurisdictional context, and caveats are preserved."}
                </p>
              </div>
              {sourceHealth.hasCaveats ? (
                <label className="mt-3 flex items-start gap-3 rounded-md border border-warning/25 bg-warning/10 px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]">
                  <input
                    type="checkbox"
                    checked={sourceCaveatAcknowledged}
                    disabled={exportControlsLocked}
                    onChange={(event) => {
                      clearJobIfTerminal();
                      setSourceCaveatAcknowledged(event.currentTarget.checked);
                    }}
                    className="mt-0.5 h-4 w-4 shrink-0 rounded border-warning/50 text-warning accent-warning focus:ring-warning focus:ring-offset-0 disabled:cursor-not-allowed disabled:opacity-50"
                  />
                  <span>
                    I confirm this export preserves the source coverage caveat,
                    remains an AI-assisted draft, and requires downstream review
                    of citations, claim mappings, and scientific assumptions.
                  </span>
                </label>
              ) : null}
            </section>

            <div className="min-w-0 space-y-5">
              <section
                aria-labelledby="export-audience-heading"
                className="min-w-0"
              >
                <h4
                  id="export-audience-heading"
                  className="text-sm font-semibold text-[var(--text-primary)]"
                >
                  2. Select audience
                </h4>
                <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                  Tailor the packet for the primary reviewer.
                </p>
                <div className="mt-3">
                  <ExportDialogAudienceSelector
                    audience={audience}
                    disabled={exportControlsLocked}
                    onAudienceChange={(v) => {
                      clearJobIfTerminal();
                      setAudience(v);
                      setSelectedSections(getAudienceDefaultSections(v));
                    }}
                  />
                </div>
                <AudiencePacketSummary
                  audience={audience}
                  missingSections={missingAudienceSections}
                  selectedSections={selectedSections}
                />
              </section>

              <section
                aria-labelledby="export-sections-heading"
                className="min-w-0"
              >
                <ExportDialogSectionSelector
                  audience={audience}
                  selectedSections={selectedSections}
                  disabled={exportControlsLocked}
                  onToggle={(sectionId) => {
                    clearJobIfTerminal();
                    setSelectedSections((previous) =>
                      toggleExportSection(previous, sectionId),
                    );
                  }}
                />
              </section>
            </div>
          </div>

          <div className="space-y-4 px-5 pb-5 sm:px-6">
            <ExportReadinessStrip
              report={report}
              readinessInput={readinessInput}
              shareActive={shareActive}
              shareRecipientBound={shareRecipientBound}
            />
            <div>
              <ExportDialogStatus
                isCompleted={isCompleted}
                isFailed={isFailed}
                isRetryableFailure={isRetryableFailure}
                isPollingCapped={isPollingCapped}
                selectedFormat={activeSelectedFormat}
                verifiedClaimChartPacketActive={verifiedClaimChartPacketActive}
                downloadUrl={jobStatus?.download_url}
                retryAfterSeconds={jobStatus?.retry_after_seconds}
                fileSizeBytes={jobStatus?.file_size_bytes}
                artifactLabel={getExportArtifactLabel(
                  audience,
                  activeSelectedFormat,
                )}
                manifestHash={jobStatus?.manifest_hash}
                manifestSnapshot={jobStatus?.manifest_snapshot}
                manifestSchemaVersion={jobStatus?.manifest_schema_version}
                artifactSha256={jobStatus?.artifact_sha256}
                reportPayloadSha256={jobStatus?.report_payload_sha256}
                completedAt={jobStatus?.completed_at}
                token={token}
              />
            </div>
          </div>
        </div>

        <footer className="shrink-0 border-t border-[var(--border-default)] bg-[var(--bg-surface)] px-5 py-4 shadow-[0_-18px_36px_rgba(11,31,36,0.08)] sm:px-6">
          <ExportDecisionSummary items={decisionSummaryItems} />
          <ExportDialogActions
            isCompleted={isCompleted}
            isProcessing={isProcessing}
            isDisabled={isExportDisabled}
            disabledReason={effectiveExportActionState.disabledReason}
            disabledTone={effectiveExportActionState.disabledTone}
            buttonLabel={
              verifiedClaimChartPacketActive &&
              !effectiveExportActionState.disabledReason
                ? "Generate verified claim-chart DOCX"
                : effectiveExportActionState.buttonLabel
            }
            onClose={onClose}
            onExport={handleExport}
          />
        </footer>
      </div>
    </div>
  );
}

type ExportDecisionSummaryTone = "success" | "warning" | "danger" | "neutral";

interface ExportDecisionSummaryItem {
  detail: string;
  icon: LucideIcon;
  label: string;
  tone: ExportDecisionSummaryTone;
  value: string;
}

function ExportDecisionSummary({
  items,
}: {
  items: ExportDecisionSummaryItem[];
}) {
  return (
    <section
      aria-label="Export decision summary"
      className="mb-3 grid gap-2 rounded-lg border border-brand-primary/15 bg-[linear-gradient(135deg,color-mix(in_srgb,var(--surface-muted)_72%,transparent),color-mix(in_srgb,var(--bg-surface)_94%,transparent))] p-2.5 shadow-[var(--shadow-xs)] sm:grid-cols-2 xl:grid-cols-4"
    >
      {items.map(({ detail, icon: Icon, label, tone, value }) => (
        <div
          key={label}
          className="flex min-w-0 items-start gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/72 px-2.5 py-2"
        >
          <span
            className={cn(
              "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border",
              tone === "danger"
                ? "border-error/25 bg-error/10 text-error"
                : tone === "warning"
                  ? "border-warning/25 bg-warning/10 text-warning"
                  : tone === "success"
                    ? "border-brand-primary/20 bg-brand-primary/10 text-brand-primary"
                    : "border-[var(--border-subtle)] bg-[var(--surface-subtle)] text-[var(--text-secondary)]",
            )}
            aria-hidden="true"
          >
            <Icon className="h-3.5 w-3.5" />
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.13em] text-[var(--text-tertiary)]">
              {label}
            </p>
            <p
              className="mt-0.5 truncate text-xs font-semibold leading-5 text-[var(--text-primary)]"
              title={value}
            >
              {value}
            </p>
            <p
              className="line-clamp-2 text-xs leading-4 text-[var(--text-tertiary)]"
              title={detail}
            >
              {detail}
            </p>
          </div>
        </div>
      ))}
    </section>
  );
}

function ExportReviewDetails({
  blockers,
  children,
  manifest,
}: {
  blockers: ExportReadinessBlockerList;
  children: ReactNode;
  manifest: ExportManifestPreviewModel;
}) {
  const blockerCount = blockers.length;
  const blockerLabel =
    blockerCount === 0
      ? "No known blockers"
      : `${blockerCount} blocker${blockerCount === 1 ? "" : "s"}`;
  const [detailsOpen, setDetailsOpen] = useState(false);

  return (
    <section
      aria-label="Review details"
      className="mt-4 overflow-hidden rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)]/78 shadow-[var(--shadow-xs)]"
    >
      <button
        type="button"
        aria-expanded={detailsOpen}
        aria-controls="export-review-details-body"
        onClick={() => setDetailsOpen((open) => !open)}
        className="flex min-h-11 w-full cursor-pointer flex-col gap-3 px-3 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)] sm:flex-row sm:items-center sm:justify-between"
      >
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-brand-primary/15 bg-brand-primary/8 text-brand-primary">
            <ClipboardList className="h-4 w-4" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              Review details
            </p>
            <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
              Readiness brief and receipt preview
            </p>
            <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
              Deeper proof stays available without pushing packet configuration
              below the fold.
            </p>
          </div>
        </div>
        <span className="flex shrink-0 flex-wrap items-center gap-2 text-xs font-semibold text-[var(--text-secondary)]">
          <span
            className={cn(
              "rounded-full border px-2.5 py-1",
              blockerCount > 0
                ? "border-warning/25 bg-warning/10 text-warning"
                : "border-brand-primary/20 bg-brand-primary/8 text-brand-primary",
            )}
          >
            {blockerLabel}
          </span>
          <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-2.5 py-1 text-[var(--text-tertiary)]">
            {manifest.sectionLabels.length.toLocaleString()} sections
          </span>
          <ChevronDown
            className={cn(
              "h-4 w-4 text-[var(--text-tertiary)] transition-transform",
              detailsOpen ? "rotate-180" : "",
            )}
            aria-hidden="true"
          />
        </span>
      </button>
      {detailsOpen ? (
        <div
          id="export-review-details-body"
          className="border-t border-[var(--border-subtle)] p-3"
        >
          {children}
        </div>
      ) : null}
    </section>
  );
}

function ExportReadinessBrief({
  audience,
  blockers,
  reviewApproved,
  selectedFormat,
  selectedSections,
  sourceCaveatAcknowledged,
  sourceHealth,
  handoffPrompts,
  onCopyHandoffBrief,
}: {
  audience: ExportAudience;
  blockers: ExportReadinessBlockerList;
  reviewApproved: boolean;
  selectedFormat: ExportFormat;
  selectedSections: Set<ExportSection>;
  sourceCaveatAcknowledged: boolean;
  sourceHealth: ReturnType<typeof getReportSourceHealthReadiness>;
  handoffPrompts: string[];
  onCopyHandoffBrief: () => void;
}) {
  const contentSectionCount = Array.from(selectedSections).filter(
    (sectionId) => !["audit_trail", "pipeline_metadata"].includes(sectionId),
  ).length;
  const blocked = blockers.length > 0;
  const recommendation = blocked
    ? "Resolve blockers"
    : sourceHealth.hasCaveats
      ? sourceCaveatAcknowledged
        ? "Export with caveat"
        : "Acknowledge caveats"
      : "Ready for final check";
  const recommendationDetail = blocked
    ? (blockers[0]?.detail ??
      "Review readiness blockers before generating the packet.")
    : sourceHealth.hasCaveats
      ? sourceCaveatAcknowledged
        ? `${sourceHealth.detail} Source caveat remains in the packet; acknowledgement is a local export gate.`
        : `${sourceHealth.detail} Acknowledge before generating the packet.`
      : `${getAudienceLabel(audience)} ${getExportFormatLabel(selectedFormat)} keeps provenance and caveats attached; backend export checks still run at start.`;
  const tone = blocked
    ? "danger"
    : sourceHealth.hasCaveats || !reviewApproved
      ? "warning"
      : "success";

  return (
    <section
      aria-label="Export readiness brief"
      className="rounded-lg border border-brand-primary/15 bg-[linear-gradient(135deg,color-mix(in_srgb,var(--bg-surface)_92%,transparent),color-mix(in_srgb,var(--surface-muted)_78%,transparent))] p-3 shadow-[var(--shadow-xs)]"
    >
      <div className="grid gap-3 md:grid-cols-[minmax(0,1.08fr)_minmax(0,0.92fr)] md:items-stretch">
        <div className="flex min-w-0 items-start gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/70 px-3 py-3">
          <span
            className={cn(
              "mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border",
              tone === "success"
                ? "border-brand-primary/20 bg-brand-primary/10 text-brand-primary"
                : tone === "danger"
                  ? "border-error/25 bg-error/10 text-error"
                  : "border-warning/25 bg-warning/10 text-warning",
            )}
          >
            {tone === "success" ? (
              <DatabaseZap className="h-4 w-4" aria-hidden="true" />
            ) : tone === "danger" ? (
              <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            ) : (
              <Scale className="h-4 w-4" aria-hidden="true" />
            )}
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              Readiness brief
            </p>
            <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
              {recommendation}
            </p>
            <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
              {recommendationDetail}
            </p>
          </div>
        </div>

        <dl className="grid gap-2 sm:grid-cols-3 md:grid-cols-3">
          <ReadinessBriefMetric
            label="Audience"
            value={getAudienceLabel(audience)}
          />
          <ReadinessBriefMetric
            label="Format"
            value={getExportFormatLabel(selectedFormat)}
          />
          <ReadinessBriefMetric
            label="Scope"
            value={`${contentSectionCount}/${SECTION_CONTENT_COUNT} content`}
            detail={`${selectedSections.size} sections total`}
          />
        </dl>
      </div>
      <p className="mt-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]">
        AI assistance summarizes the packet state only; export remains gated by
        persisted counsel review, source health, and backend readiness.
      </p>
      <div className="mt-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/72 px-3 py-2">
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
            Counsel handoff prompts
          </p>
          <button
            type="button"
            onClick={onCopyHandoffBrief}
            className="inline-flex min-h-11 items-center gap-1.5 rounded-md border border-brand-primary/20 bg-brand-primary/8 px-3 py-2 text-xs font-semibold text-brand-primary transition-colors hover:bg-brand-primary/12 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)]"
          >
            <Copy className="h-3.5 w-3.5" aria-hidden="true" />
            Copy readiness brief
          </button>
        </div>
        <ul className="mt-2 grid gap-1.5 text-xs leading-5 text-[var(--text-secondary)] md:grid-cols-3">
          {handoffPrompts.slice(0, 3).map((prompt) => (
            <li key={prompt} className="flex min-w-0 items-start gap-2">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-primary" />
              <span>{prompt}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

interface ExportManifestPreviewModel {
  artifactValue: string;
  backendGateValue: string;
  caveatValue: string;
  distributionDetail: string;
  distributionValue: string;
  reviewDetail: string | null;
  reviewValue: string;
  sectionLabels: string[];
  sourceDetail: string | null;
  sourceValue: string;
  text: string;
}

function ExportManifestPreview({
  manifest,
  onCopyManifest,
}: {
  manifest: ExportManifestPreviewModel;
  onCopyManifest: () => void;
}) {
  return (
    <section
      aria-label="Export manifest preview"
      className="mt-4 rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)]/76 p-3 shadow-[var(--shadow-xs)]"
    >
      <div className="flex min-w-0 flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-brand-primary/15 bg-brand-primary/8 text-brand-primary">
            <ClipboardList className="h-4 w-4" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              Receipt preview
            </p>
            <h4 className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
              Receipt preview before generation
            </h4>
            <p className="mt-1 max-w-2xl text-xs leading-5 text-[var(--text-secondary)]">
              This preview shows intended scope and review posture. The final
              receipt is created after Praviar renders and hashes the file.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onCopyManifest}
          className="inline-flex min-h-11 w-full items-center justify-center gap-1.5 rounded-md border border-brand-primary/20 bg-brand-primary/8 px-3 py-2 text-xs font-semibold text-brand-primary transition-colors hover:bg-brand-primary/12 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)] md:w-auto"
        >
          <Copy className="h-3.5 w-3.5" aria-hidden="true" />
          Copy manifest
        </button>
      </div>

      <dl className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        <ExportManifestItem label="Artifact" value={manifest.artifactValue} />
        <ExportManifestItem
          label="Review ledger"
          value={manifest.reviewValue}
          detail={manifest.reviewDetail ?? undefined}
        />
        <ExportManifestItem
          label="Source audit"
          value={manifest.sourceValue}
          detail={manifest.sourceDetail ?? undefined}
        />
        <ExportManifestItem
          label="Caveat posture"
          value={manifest.caveatValue}
        />
        <ExportManifestItem
          label="Distribution posture"
          value={manifest.distributionValue}
          detail={manifest.distributionDetail}
        />
        <ExportManifestItem
          label="Backend gate"
          value={manifest.backendGateValue}
        />
        <ExportManifestItem
          label="Selected scope"
          value={`${manifest.sectionLabels.length.toLocaleString()} sections`}
          detail={manifest.sectionLabels.join(", ")}
        />
      </dl>
    </section>
  );
}

function ExportManifestItem({
  detail,
  label,
  value,
}: {
  detail?: string;
  label: string;
  value: string;
}) {
  return (
    <div className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-3 py-2">
      <dt className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
        {label}
      </dt>
      <dd className="mt-1 text-xs font-semibold leading-5 text-[var(--text-primary)]">
        {value}
      </dd>
      {detail ? (
        <dd className="mt-0.5 line-clamp-2 text-xs leading-4 text-[var(--text-tertiary)]">
          {detail}
        </dd>
      ) : null}
    </div>
  );
}

const SECTION_CONTENT_COUNT = 4;

function isVerifiedClaimChartPacket({
  audience,
  selectedFormat,
  selectedSections,
}: {
  audience: ExportAudience;
  selectedFormat: ExportFormat;
  selectedSections: Set<ExportSection>;
}): boolean {
  return (
    selectedFormat === "docx" &&
    audience === "attorney" &&
    selectedSections.size === VERIFIED_CLAIM_CHART_PACKET_SECTIONS.length &&
    VERIFIED_CLAIM_CHART_PACKET_SECTIONS.every((sectionId) =>
      selectedSections.has(sectionId),
    )
  );
}

function getReportClaimChartCount(report?: FTOReport): number {
  return (report?.patent_analyses ?? []).reduce(
    (total, analysis) =>
      total +
      (analysis.claims_analyzed ?? []).reduce(
        (claimTotal, claim) => claimTotal + (claim.elements?.length ?? 0),
        0,
      ),
    0,
  );
}

function ReadinessBriefMetric({
  detail,
  label,
  value,
}: {
  detail?: string;
  label: string;
  value: string;
}) {
  return (
    <div className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/70 px-3 py-2">
      <dt className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
        {label}
      </dt>
      <dd className="mt-1 truncate text-xs font-semibold text-[var(--text-primary)]">
        {value}
      </dd>
      {detail ? (
        <dd className="mt-0.5 text-xs leading-4 text-[var(--text-tertiary)]">
          {detail}
        </dd>
      ) : null}
    </div>
  );
}

function ExportBlockerCallout({
  blockers,
}: {
  blockers: ExportReadinessBlockerList;
}) {
  const hasDangerBlocker = blockers.some(
    (blocker) => blocker.tone === "danger",
  );
  const tone = hasDangerBlocker ? "danger" : "warning";
  const title =
    tone === "danger"
      ? "Resolve export blockers before packet generation"
      : "Verify export readiness before packet generation";

  return (
    <section
      aria-label="Export blockers"
      className={cn(
        "mt-4 rounded-lg border px-4 py-3 text-sm shadow-[var(--shadow-xs)]",
        tone === "danger"
          ? "border-error/25 bg-error/8"
          : "border-warning/25 bg-warning/8",
      )}
      role={tone === "danger" ? "alert" : "status"}
    >
      <div className="flex min-w-0 items-start gap-3">
        <span
          className={cn(
            "mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border",
            tone === "danger"
              ? "border-error/25 bg-error/10 text-error"
              : "border-warning/25 bg-warning/10 text-warning",
          )}
        >
          <AlertTriangle className="h-4 w-4" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h4
            className={cn(
              "text-sm font-semibold",
              tone === "danger" ? "text-error" : "text-warning",
            )}
          >
            {title}
          </h4>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            This packet is protected until readiness, jurisdiction lane, and
            persisted review checks clear.
          </p>
          <ul className="mt-2 grid gap-1.5">
            {blockers.slice(0, 3).map((blocker) => (
              <li
                key={`${blocker.label}:${blocker.detail}`}
                className="flex min-w-0 items-start gap-2 text-xs leading-5 text-[var(--text-secondary)]"
              >
                <span
                  className={cn(
                    "mt-2 h-1.5 w-1.5 shrink-0 rounded-full",
                    blocker.tone === "danger" ? "bg-error" : "bg-warning",
                  )}
                />
                <span className="min-w-0">
                  <span className="font-semibold text-[var(--text-primary)]">
                    {blocker.label}:
                  </span>{" "}
                  {blocker.detail}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

function ExportAccessRestrictedCallout() {
  return (
    <section
      aria-label="Export access restricted"
      className="mt-4 rounded-lg border border-error/25 bg-error/8 px-4 py-3 text-sm shadow-[var(--shadow-xs)]"
      role="alert"
    >
      <div className="flex min-w-0 items-start gap-3">
        <span
          className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-error/25 bg-error/10 text-error"
          aria-hidden="true"
        >
          <AlertTriangle className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <h4 className="text-sm font-semibold text-error">
            Export access restricted
          </h4>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            Your current session is not authorized to generate this report
            packet. Packet controls and stale job state are locked until access
            is confirmed again.
          </p>
        </div>
      </div>
    </section>
  );
}

function ExportRoleResolutionCallout({
  state,
  onRetry,
}: {
  state: Exclude<ExportRoleResolutionState, "ready">;
  onRetry?: () => void;
}) {
  const loading = state === "loading";
  return (
    <section
      aria-label={
        loading ? "Export role confirmation" : "Export metadata retry"
      }
      className={cn(
        "mt-4 rounded-lg border px-4 py-3 text-sm shadow-[var(--shadow-xs)]",
        loading
          ? "border-brand-primary/25 bg-brand-primary/8"
          : "border-warning/30 bg-warning/10",
      )}
      role={loading ? "status" : "alert"}
    >
      <div className="flex min-w-0 items-start gap-3">
        <span
          className={cn(
            "mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border",
            loading
              ? "border-brand-primary/25 bg-brand-primary/10 text-brand-primary"
              : "border-warning/30 bg-warning/12 text-warning",
          )}
          aria-hidden="true"
        >
          <AlertTriangle className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <h4
            className={cn(
              "text-sm font-semibold",
              loading ? "text-brand-primary" : "text-warning",
            )}
          >
            {loading ? "Confirming export role" : "Report metadata unavailable"}
          </h4>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            {loading
              ? "Praviar is confirming your report role before enabling packet generation."
              : "Report content is visible, but export role metadata did not load. Retry report access before preparing a packet."}
          </p>
          {!loading && onRetry ? (
            <button
              type="button"
              className="mt-3 min-h-11 rounded-md border border-warning/30 bg-[var(--surface-card)] px-3 text-xs font-semibold text-warning transition-colors hover:bg-warning/12 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-warning/70"
              onClick={onRetry}
            >
              Retry report access
            </button>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function VerifiedClaimChartPacketShortcut({
  active,
  claimChartCount,
  disabled,
  disabledReason,
  onApply,
}: {
  active: boolean;
  claimChartCount: number;
  disabled: boolean;
  disabledReason?: string;
  onApply: () => void;
}) {
  const hasClaimChartData = claimChartCount > 0;
  const buttonLabel = !hasClaimChartData
    ? "No claim charts"
    : active
      ? "Packet selected"
      : "Use verified packet";

  return (
    <section
      aria-label="Verified claim-chart packet"
      className={cn(
        "mt-4 rounded-lg border p-3 shadow-[var(--shadow-xs)]",
        active
          ? "border-brand-primary/25 bg-brand-primary/8"
          : "border-[var(--border-default)] bg-[var(--bg-surface)]/74",
      )}
    >
      <div className="flex min-w-0 flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span
            className={cn(
              "mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md border",
              active
                ? "border-brand-primary/25 bg-brand-primary/12 text-brand-primary"
                : "border-[var(--border-subtle)] bg-[var(--surface-subtle)] text-[var(--text-secondary)]",
            )}
          >
            <FileCheck2 className="h-4 w-4" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
              Counsel packet shortcut
            </p>
            <h4 className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
              Verified claim-chart DOCX
            </h4>
            <p className="mt-1 max-w-2xl text-xs leading-5 text-[var(--text-secondary)]">
              {disabledReason
                ? disabledReason
                : hasClaimChartData
                  ? `Counsel-role Word Review Memo with ${claimChartCount.toLocaleString()} claim-chart row${claimChartCount === 1 ? "" : "s"}, audit trail, pipeline metadata, and final manifest receipt.`
                  : "This report has no claim-chart rows yet; use the standard export packet or rerun with claim-level analysis before generating a claim-chart DOCX."}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onApply}
          disabled={disabled}
          className={cn(
            "inline-flex min-h-11 w-full items-center justify-center gap-1.5 rounded-md border px-3 py-2 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)] md:w-auto",
            active
              ? "border-brand-primary/25 bg-brand-primary text-white hover:bg-brand-primary/90"
              : "border-brand-primary/20 bg-brand-primary/8 text-brand-primary hover:bg-brand-primary/12",
            disabled && "cursor-not-allowed opacity-60",
          )}
        >
          <FileCheck2 className="h-3.5 w-3.5" aria-hidden="true" />
          {buttonLabel}
        </button>
      </div>
    </section>
  );
}

function AudiencePacketSummary({
  audience,
  missingSections,
  selectedSections,
}: {
  audience: ExportAudience;
  missingSections: ExportSection[];
  selectedSections: Set<ExportSection>;
}) {
  const requirements = AUDIENCE_PACKET_REQUIREMENTS[audience];
  const requiredSections = requirements.requiredSections;
  const defaultSections = Array.from(getAudienceDefaultSections(audience));

  return (
    <section
      aria-label="Audience packet requirements"
      className={cn(
        "mt-3 rounded-lg border p-3 text-xs shadow-[var(--shadow-xs)]",
        missingSections.length > 0
          ? "border-warning/25 bg-warning/10"
          : "border-brand-primary/15 bg-brand-primary/5",
      )}
    >
      <div className="flex min-w-0 items-start gap-2">
        <span
          className={cn(
            "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border",
            missingSections.length > 0
              ? "border-warning/25 bg-warning/10 text-warning"
              : "border-brand-primary/15 bg-brand-primary/10 text-brand-primary",
          )}
        >
          {missingSections.length > 0 ? (
            <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-[var(--text-primary)]">
            Audience packet requirements
          </p>
          <p className="mt-1 leading-5 text-[var(--text-secondary)]">
            {requirements.summary} Preset scope is applied on audience change;
            Audit Trail and Pipeline Metadata stay attached for provenance.
          </p>
          <div className="mt-2 flex min-w-0 flex-wrap gap-1.5">
            {defaultSections.map((sectionId) => {
              const selected = selectedSections.has(sectionId);
              const required = requiredSections.includes(sectionId);
              return (
                <span
                  key={sectionId}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full border px-2 py-1 font-semibold",
                    selected && required
                      ? "border-brand-primary/20 bg-brand-primary/8 text-brand-primary"
                      : selected
                        ? "border-[var(--border-subtle)] bg-[var(--surface-subtle)] text-[var(--text-secondary)]"
                        : required
                          ? "border-warning/25 bg-warning/10 text-warning"
                          : "border-[var(--border-subtle)] bg-[var(--bg-surface)] text-[var(--text-tertiary)]",
                  )}
                >
                  {selected ? (
                    <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                  ) : (
                    <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                  )}
                  {getExportSectionLabel(sectionId)}
                </span>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}

function ExportIdentityField({
  label,
  mono,
  risk,
  riskLabel,
  value,
}: {
  label: string;
  mono?: boolean;
  risk?: RiskLevel;
  riskLabel?: string | null;
  value: string;
}) {
  return (
    <div className="min-w-0">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <div className="mt-1 flex min-w-0 flex-wrap items-center gap-2">
        <span
          className={
            mono
              ? "min-w-0 break-words font-mono text-sm font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]"
              : "min-w-0 break-words text-sm font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]"
          }
          title={value}
        >
          {value}
        </span>
        {risk ? (
          <RiskBadge
            risk={risk}
            label={riskLabel ?? undefined}
            size="sm"
            className="shrink-0"
          />
        ) : null}
      </div>
    </div>
  );
}

function ExportReadinessStrip({
  className,
  report,
  readinessInput,
  shareActive,
  shareRecipientBound,
}: {
  className?: string;
  report?: FTOReport;
  readinessInput: RelianceReadinessInput;
  shareActive?: boolean;
  shareRecipientBound?: boolean;
}) {
  const blockers = getCombinedExportReadinessBlockers(readinessInput);
  const sourceHealth = getReportSourceHealthReadiness(report);
  const lifecycleState = getRelianceLifecycleState({
    ...readinessInput,
    report,
    shareActive,
    shareRecipientBound,
  });
  const exportReady = getWorkspaceExportReady(readinessInput.workspaceSummary);
  const workspaceVerificationPending =
    Boolean(readinessInput.workspaceSummaryLoading) &&
    !readinessInput.workspaceSummary;
  const reviewVerificationPending =
    Boolean(readinessInput.reviewStatusLoading) && !readinessInput.reviewStatus;
  const verifying = workspaceVerificationPending || reviewVerificationPending;
  const blockingJurisdictions = getWorkspaceBlockingJurisdictions(
    readinessInput.workspaceSummary,
  );
  const opinionSummary = getWorkspaceOpinionSummary(
    readinessInput.workspaceSummary,
  );
  const hasBlockers = blockers.length > 0;
  const blocked = hasBlockers && !verifying;
  const caveated = !blocked && !verifying && sourceHealth.hasCaveats;
  const reviewContextValue = reviewVerificationPending
    ? "Review status verification in progress"
    : readinessInput.reviewStatus?.status === "approved"
      ? "Reviewer approval recorded"
      : readinessInput.reviewStatus
        ? `${readinessInput.reviewStatus.findings_reviewed}/${readinessInput.reviewStatus.findings_total} findings reviewed`
        : "Counsel caveat included";
  const reviewContextStatus = reviewVerificationPending
    ? "Verifying"
    : readinessInput.reviewStatus?.status === "approved"
      ? "Approved"
      : "Review required";
  const reviewContextTone = reviewVerificationPending
    ? ("warning" as const)
    : readinessInput.reviewStatus?.status === "approved"
      ? ("success" as const)
      : ("warning" as const);
  const exportCaveatValue = workspaceVerificationPending
    ? "Readiness verification in progress"
    : (opinionSummary ??
      (blockingJurisdictions.length > 0
        ? `${blockingJurisdictions.join(", ")} ${
            blockingJurisdictions.length === 1 ? "lane blocks" : "lanes block"
          } export`
        : "Not a legal opinion"));
  const exportCaveatStatus = workspaceVerificationPending
    ? "Verifying"
    : exportReady === false
      ? "Blocked"
      : exportReady === true
        ? "Backend ready"
        : "Verify";
  const exportCaveatTone = workspaceVerificationPending
    ? ("warning" as const)
    : exportReady === false || blockingJurisdictions.length > 0
      ? ("danger" as const)
      : exportReady === true
        ? ("success" as const)
        : ("warning" as const);
  const items = [
    {
      icon: DatabaseZap,
      label: "Source audit",
      value: sourceHealth.detail,
      status: sourceHealth.status,
      tone: sourceHealth.tone,
    },
    {
      icon: FileCheck2,
      label: "Review context",
      value: reviewContextValue,
      status: reviewContextStatus,
      tone: reviewContextTone,
    },
    {
      icon: Scale,
      label: "Export caveats",
      value: exportCaveatValue,
      status: exportCaveatStatus,
      tone: exportCaveatTone,
    },
  ];

  return (
    <section
      aria-label="Export readiness"
      className={cn(
        "rounded-lg border p-4",
        blocked
          ? "border-error/25 bg-error/5"
          : verifying
            ? "border-warning/25 bg-warning/5"
            : caveated
              ? "border-warning/25 bg-warning/5"
              : "border-brand-primary/15 bg-brand-primary/5",
        className,
      )}
    >
      <div className="mb-3 flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">
            4. Export readiness
          </h4>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            {blocked
              ? "Known readiness blockers must be resolved before export."
              : verifying
                ? "Readiness checks are still loading; export starts after verification completes."
                : caveated
                  ? "Export package preserves source links, with coverage caveats visible."
                  : "Export package preserves source links and reliance caveats; final backend checks run when export starts."}
          </p>
        </div>
        <span
          className={cn(
            "inline-flex w-fit items-center gap-1 rounded-full border px-2 py-1 text-xs font-semibold uppercase",
            blocked
              ? "border-error/25 bg-error/10 text-error"
              : verifying
                ? "border-warning/25 bg-warning/10 text-warning"
                : caveated
                  ? "border-warning/25 bg-warning/10 text-warning"
                  : "border-brand-primary/20 bg-brand-primary/10 text-brand-primary",
          )}
        >
          {blocked
            ? "Blocked"
            : verifying
              ? "Verifying"
              : caveated
                ? "Caveated"
                : "Final check"}
        </span>
      </div>
      <div
        role="group"
        aria-label="Authoritative reliance state"
        className="mb-3 grid gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/66 p-3 sm:grid-cols-2 xl:grid-cols-4"
      >
        <ExportStateDatum
          label="Authoritative state"
          value={lifecycleState.label}
          tone={lifecycleState.tone}
        />
        <ExportStateDatum label="Owner" value={lifecycleState.owner} />
        <ExportStateDatum
          label="Current blocker"
          value={lifecycleState.blocker}
        />
        <ExportStateDatum
          label="Next action"
          value={lifecycleState.nextAction}
        />
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {items.map(({ icon: Icon, label, status, tone, value }) => (
          <div key={label} className="flex min-w-0 items-start gap-3">
            <span
              className={cn(
                "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border",
                tone === "danger"
                  ? "border-error/25 bg-error/10 text-error"
                  : tone === "warning"
                    ? "border-warning/25 bg-warning/10 text-warning"
                    : "border-brand-primary/15 bg-brand-primary/10 text-brand-primary",
              )}
              aria-hidden="true"
            >
              <Icon className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-[var(--text-primary)]">
                {label}
              </p>
              <p className="mt-0.5 text-xs leading-5 text-[var(--text-secondary)]">
                {value}
              </p>
              <span
                className={cn(
                  "mt-1 inline-flex items-center gap-1 text-xs font-semibold",
                  tone === "danger"
                    ? "text-error"
                    : tone === "warning"
                      ? "text-warning"
                      : "text-success",
                )}
              >
                {tone === "danger" ? (
                  <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                ) : (
                  <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                )}
                {status}
              </span>
            </div>
          </div>
        ))}
      </div>
      {hasBlockers ? (
        <ul className="mt-3 space-y-1 text-xs leading-5 text-error">
          {blockers.map((blocker) => (
            <li key={`${blocker.label}-${blocker.detail}`}>
              {blocker.label}: {blocker.detail}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function ExportStateDatum({
  label,
  tone,
  value,
}: {
  label: string;
  tone?: "success" | "warning" | "danger" | "neutral";
  value: string;
}) {
  return (
    <div className="min-w-0">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p
        className={cn(
          "mt-1 line-clamp-2 text-xs font-semibold leading-5 text-[var(--text-primary)]",
          tone === "danger" && "text-error",
          tone === "warning" && "text-warning",
          tone === "success" && "text-success",
        )}
        title={value}
      >
        {value}
      </p>
    </div>
  );
}

type ExportActionDisabledTone = "danger" | "warning" | "neutral";

function getExportDecisionSummaryItems({
  audience,
  exportActionState,
  isProcessing,
  reviewStatus,
  reviewStatusLoading,
  selectedFormat,
  selectedSections,
  sourceCaveatAcknowledged,
  sourceHealth,
}: {
  audience: ExportAudience;
  exportActionState: {
    buttonLabel: string;
    disabledReason: string | null;
    disabledTone: ExportActionDisabledTone;
    isDisabled: boolean;
  };
  isProcessing: boolean;
  reviewStatus?: AnalysisReviewStatusResponse;
  reviewStatusLoading?: boolean;
  selectedFormat: ExportFormat;
  selectedSections: Set<ExportSection>;
  sourceCaveatAcknowledged: boolean;
  sourceHealth: ReturnType<typeof getReportSourceHealthReadiness>;
}): ExportDecisionSummaryItem[] {
  const contentSectionCount = Array.from(selectedSections).filter(
    (sectionId) => !isRequiredDecisionProvenanceSection(sectionId),
  ).length;
  const reviewLoading = Boolean(reviewStatusLoading) && !reviewStatus;
  const reviewApproved = reviewStatus?.status === "approved";
  const reviewValue = reviewLoading
    ? "Review verifying"
    : reviewApproved
      ? "Counsel approved"
      : "Counsel review required";
  const reviewDetail = reviewLoading
    ? "Persisted legal review status is loading."
    : reviewApproved
      ? "Reviewer approval is recorded before export."
      : reviewStatus
        ? `${reviewStatus.findings_reviewed}/${reviewStatus.findings_total} findings reviewed.`
        : "Export carries the counsel-review caveat.";
  const relianceTone =
    exportActionState.disabledTone === "danger"
      ? "danger"
      : exportActionState.disabledTone === "warning"
        ? "warning"
        : isProcessing
          ? "neutral"
          : sourceHealth.hasCaveats
            ? "warning"
            : "success";
  const relianceValue = isProcessing
    ? "Generating packet"
    : exportActionState.disabledReason
      ? exportActionState.buttonLabel
      : sourceHealth.hasCaveats
        ? sourceCaveatAcknowledged
          ? "Caveat acknowledged"
          : "Caveat pending"
        : "Ready for backend checks";
  const relianceDetail =
    exportActionState.disabledReason ??
    (sourceHealth.hasCaveats
      ? sourceCaveatAcknowledged
        ? "Artifact still carries the source caveat."
        : "Acknowledge source caveats before export."
      : "Backend readiness verifies again at export start.");

  return [
    {
      detail: `${contentSectionCount}/${SECTION_CONTENT_COUNT} content sections; ${selectedSections.size} total sections.`,
      icon: ClipboardList,
      label: "Artifact",
      tone: "neutral",
      value: getExportArtifactLabel(audience, selectedFormat),
    },
    {
      detail: reviewDetail,
      icon: FileCheck2,
      label: "Review",
      tone: reviewApproved ? "success" : "warning",
      value: reviewValue,
    },
    {
      detail: sourceHealth.detail,
      icon: DatabaseZap,
      label: "Sources",
      tone: sourceHealth.tone,
      value: sourceHealth.status,
    },
    {
      detail: relianceDetail,
      icon: Scale,
      label: "Reliance gate",
      tone: relianceTone,
      value: relianceValue,
    },
  ];
}

function isRequiredDecisionProvenanceSection(
  sectionId: ExportSection,
): boolean {
  return sectionId === "audit_trail" || sectionId === "pipeline_metadata";
}

function getExportActionState({
  audience,
  exportDisabledReason,
  hasContentSections,
  hasRequiredSections,
  isProcessing,
  missingAudienceSections,
  selectedSections,
  sourceCaveatAcknowledged,
  sourceHealth,
}: {
  audience: ExportAudience;
  exportDisabledReason: string | null;
  hasContentSections: boolean;
  hasRequiredSections: boolean;
  isProcessing: boolean;
  missingAudienceSections: ExportSection[];
  selectedSections: Set<ExportSection>;
  sourceCaveatAcknowledged: boolean;
  sourceHealth: ReturnType<typeof getReportSourceHealthReadiness>;
}): {
  buttonLabel: string;
  disabledReason: string | null;
  disabledTone: ExportActionDisabledTone;
  isDisabled: boolean;
} {
  if (isProcessing) {
    return {
      buttonLabel: "Exporting...",
      disabledReason: null,
      disabledTone: "neutral",
      isDisabled: true,
    };
  }

  if (exportDisabledReason) {
    return {
      buttonLabel: "Resolve blockers",
      disabledReason: exportDisabledReason,
      disabledTone: "danger",
      isDisabled: true,
    };
  }

  if (selectedSections.size === 0) {
    return {
      buttonLabel: "Complete packet scope",
      disabledReason: "Select at least one packet section before exporting.",
      disabledTone: "warning",
      isDisabled: true,
    };
  }

  if (!hasRequiredSections) {
    return {
      buttonLabel: "Complete packet scope",
      disabledReason:
        "Audit Trail and Pipeline Metadata are required for governed exports.",
      disabledTone: "warning",
      isDisabled: true,
    };
  }

  if (!hasContentSections) {
    return {
      buttonLabel: "Complete packet scope",
      disabledReason:
        "Select at least one report content section before exporting; provenance-only packets are audit records, not export deliverables.",
      disabledTone: "warning",
      isDisabled: true,
    };
  }

  if (missingAudienceSections.length > 0) {
    const missingLabels = missingAudienceSections
      .map((sectionId) => getExportSectionLabel(sectionId))
      .join(", ");
    return {
      buttonLabel: "Complete packet scope",
      disabledReason: `Add ${missingLabels} for the ${getAudienceLabel(audience)} packet before exporting.`,
      disabledTone: "warning",
      isDisabled: true,
    };
  }

  if (sourceHealth.hasCaveats && !sourceCaveatAcknowledged) {
    return {
      buttonLabel: "Acknowledge caveats",
      disabledReason:
        "Acknowledge source audit caveats before exporting this packet.",
      disabledTone: "warning",
      isDisabled: true,
    };
  }

  return {
    buttonLabel: "Export packet",
    disabledReason: null,
    disabledTone: "neutral",
    isDisabled: false,
  };
}

function getExportHandoffPrompts({
  blockers,
  riskLabel,
  sourceCaveatAcknowledged,
  sourceHealth,
}: {
  blockers: ExportReadinessBlockerList;
  riskLabel?: string | null;
  sourceCaveatAcknowledged: boolean;
  sourceHealth: ReturnType<typeof getReportSourceHealthReadiness>;
}): string[] {
  const prompts: string[] = [];

  for (const blocker of blockers.slice(0, 2)) {
    prompts.push(`${blocker.label}: ${blocker.detail}`);
  }

  if (sourceHealth.hasCaveats) {
    prompts.push(
      sourceCaveatAcknowledged
        ? `Confirm source coverage caveat remains visible: ${sourceHealth.detail}`
        : `Acknowledge source coverage caveat before export: ${sourceHealth.detail}`,
    );
  } else {
    prompts.push(`Confirm source audit completeness: ${sourceHealth.detail}`);
  }

  if (riskLabel) {
    prompts.push(
      `Review ${riskLabel.toLowerCase()} rationale against claim charts and design-around notes.`,
    );
  }

  prompts.push(
    "Confirm recipient scope, selected sections, and reliance caveats before downstream use.",
  );

  return prompts.slice(0, 5);
}

function buildExportHandoffBrief({
  audience,
  blockers,
  compoundName,
  handoffPrompts,
  reportReference,
  riskLabel,
  selectedFormat,
  selectedSections,
  sourceCaveatAcknowledged,
  sourceHealth,
}: {
  audience: ExportAudience;
  blockers: ExportReadinessBlockerList;
  compoundName: string;
  handoffPrompts: string[];
  reportReference: string;
  riskLabel?: string | null;
  selectedFormat: ExportFormat;
  selectedSections: Set<ExportSection>;
  sourceCaveatAcknowledged: boolean;
  sourceHealth: ReturnType<typeof getReportSourceHealthReadiness>;
}): string {
  const selectedSectionLabels = Array.from(selectedSections)
    .map((sectionId) => getExportSectionLabel(sectionId))
    .join(", ");
  const blockerLines =
    blockers.length > 0
      ? blockers.map((blocker) => `- ${blocker.label}: ${blocker.detail}`)
      : ["- No export readiness blockers are currently known."];
  const promptLines = handoffPrompts.map((prompt) => `- ${prompt}`);
  const sourceLine = sourceHealth.hasCaveats
    ? `${sourceHealth.detail} Acknowledgement: ${
        sourceCaveatAcknowledged
          ? "confirmed locally in the dialog; export artifact includes the source caveat, not this local confirmation"
          : "not yet confirmed"
      }.`
    : sourceHealth.detail;

  return [
    "Praviar export readiness brief",
    "",
    "Situation:",
    `${compoundName} is being prepared for ${getAudienceLabel(audience)} review with a ${riskLabel ?? "not reported"} screening posture.`,
    "",
    "Background:",
    `- Report: ${reportReference}`,
    `- Format: ${getExportFormatLabel(selectedFormat)}`,
    `- Included sections: ${selectedSectionLabels || "None selected"}`,
    `- Source audit: ${sourceLine}`,
    "",
    "Assessment:",
    ...blockerLines,
    "",
    "Recommendation:",
    ...promptLines,
    "",
    "Guardrail: AI assistance summarizes packet state only; export remains governed by persisted counsel review, source health, and backend readiness.",
  ].join("\n");
}

function buildExportManifestPreview({
  audience,
  blockers,
  compoundName,
  report,
  reportReference,
  reviewStatus,
  reviewStatusLoading,
  riskLabel,
  selectedFormat,
  selectedSections,
  shareActive,
  shareLastViewedAt,
  shareRecipientBound,
  shareViewCount,
  sourceCaveatAcknowledged,
  sourceHealth,
  workspaceSummary,
  workspaceSummaryLoading,
}: {
  audience: ExportAudience;
  blockers: ExportReadinessBlockerList;
  compoundName: string;
  report?: FTOReport;
  reportReference: string;
  reviewStatus?: AnalysisReviewStatusResponse;
  reviewStatusLoading?: boolean;
  riskLabel?: string | null;
  selectedFormat: ExportFormat;
  selectedSections: Set<ExportSection>;
  shareActive?: boolean;
  shareLastViewedAt?: string | null;
  shareRecipientBound?: boolean;
  shareViewCount?: number | null;
  sourceCaveatAcknowledged: boolean;
  sourceHealth: ReturnType<typeof getReportSourceHealthReadiness>;
  workspaceSummary?: ReportWorkspaceSummaryResponse;
  workspaceSummaryLoading?: boolean;
}): ExportManifestPreviewModel {
  const sectionLabels = Array.from(selectedSections).map((sectionId) =>
    getExportSectionLabel(sectionId),
  );
  const reviewSummary = getReviewLedgerSummary({
    decisionCounts: reviewStatus?.decision_counts,
    loading: reviewStatusLoading,
    reviewStatus,
  });
  const reviewValue =
    reviewStatus?.status === "approved"
      ? `Approved; ${reviewSummary.detailLabel ?? "review ledger recorded"}`
      : (reviewSummary.detailLabel ??
        (reviewStatusLoading
          ? "Review status verification in progress"
          : "Persisted legal review pending"));
  const reviewDetail = formatReviewManifestDetail(reviewStatus);
  const sourceDetail = formatSourceManifestDetail(report);
  const exportReady = getWorkspaceExportReady(workspaceSummary);
  const backendGateValue =
    workspaceSummaryLoading && !workspaceSummary
      ? "Readiness verification in progress"
      : exportReady === true
        ? "Backend ready"
        : exportReady === false
          ? "Blocked by opinion readiness"
          : "Backend readiness not confirmed";
  const caveatValue = sourceHealth.hasCaveats
    ? sourceCaveatAcknowledged
      ? "Source caveat acknowledged; artifact still carries caveat"
      : "Source caveat requires acknowledgement"
    : "No source caveat reported";
  const distributionPosture = buildExportDistributionPosture({
    audience,
    shareActive,
    shareLastViewedAt,
    shareRecipientBound,
    shareViewCount,
  });
  const artifactValue = getExportArtifactLabel(audience, selectedFormat);
  const blockerLines =
    blockers.length > 0
      ? blockers.map((blocker) => `- ${blocker.label}: ${blocker.detail}`)
      : ["- No export readiness blockers are currently known."];

  return {
    artifactValue,
    backendGateValue,
    caveatValue,
    distributionDetail: distributionPosture.detail,
    distributionValue: distributionPosture.value,
    reviewDetail,
    reviewValue,
    sectionLabels,
    sourceDetail,
    sourceValue: `${sourceHealth.status}; ${sourceHealth.detail}`,
    text: [
      "Praviar export manifest preview",
      `Report: ${reportReference}`,
      `Generated: ${formatManifestValue(report?.generated_at)}`,
      `Pipeline: ${formatManifestValue(report?.praviar_pipeline_version)}`,
      `Compound: ${compoundName}`,
      `Risk: ${riskLabel ?? "Not reported"}`,
      `Artifact: ${artifactValue}`,
      `Audience: ${getAudienceLabel(audience)}`,
      `Format: ${getExportFormatLabel(selectedFormat)}`,
      `Selected sections: ${sectionLabels.join(", ") || "None selected"}`,
      `Review ledger: ${reviewValue}`,
      `Reviewer: ${reviewDetail ?? "Not reported"}`,
      `Source audit: ${sourceHealth.status}; ${sourceHealth.detail}`,
      `Source records: ${sourceDetail ?? "Not reported"}`,
      `Caveat posture: ${caveatValue}`,
      `Distribution posture: ${distributionPosture.value}`,
      `Distribution detail: ${distributionPosture.detail}`,
      `Backend gate: ${backendGateValue}`,
      "Readiness blockers:",
      ...blockerLines,
      "Guardrail: AI-assisted screening remains a draft until qualified counsel reviews downstream use.",
    ].join("\n"),
  };
}

function buildExportDistributionPosture({
  audience,
  shareActive,
  shareLastViewedAt,
  shareRecipientBound,
  shareViewCount,
}: {
  audience: ExportAudience;
  shareActive?: boolean;
  shareLastViewedAt?: string | null;
  shareRecipientBound?: boolean;
  shareViewCount?: number | null;
}): { detail: string; value: string } {
  const shareViews =
    typeof shareViewCount === "number" && Number.isFinite(shareViewCount)
      ? shareViewCount
      : null;
  const shareState = shareActive
    ? `External share active; ${
        shareRecipientBound
          ? "access is bound to a mailbox-verified recipient"
          : "recipient binding is not confirmed"
      }${shareViews !== null ? `; ${shareViews.toLocaleString()} views` : ""}${
        shareLastViewedAt ? `; last viewed ${shareLastViewedAt}` : ""
      }`
    : "No active external share link recorded";
  const redactionState =
    audience === "full" || audience === "attorney"
      ? "Full/internal packet scope; not automatically redacted"
      : `${getAudienceLabel(audience)} scope limits sections, but does not automatically redact exported content`;

  return {
    value: shareActive
      ? "Share active; export separate"
      : "Internal export file",
    detail: `${shareState}. ${redactionState}. Exported files do not inherit recipient verification, read-only controls, view limits, or revocation.`,
  };
}

function formatManifestValue(value: string | null | undefined): string {
  const trimmed = value?.trim();
  return trimmed ? trimmed : "Not reported";
}

function formatReviewManifestDetail(
  reviewStatus?: AnalysisReviewStatusResponse,
): string | null {
  if (!reviewStatus) return null;
  const reviewer =
    reviewStatus.reviewer_name?.trim() ||
    reviewStatus.reviewer_email?.trim() ||
    null;
  const reviewedAt = reviewStatus.reviewed_at?.trim() || null;
  if (reviewer && reviewedAt) return `${reviewer} at ${reviewedAt}`;
  return reviewer ?? reviewedAt;
}

function formatSourceManifestDetail(report?: FTOReport): string | null {
  const entries = report?.source_health?.entries ?? [];
  if (entries.length === 0) {
    const listedSources = report?.search_sources_used ?? [];
    return listedSources.length > 0
      ? listedSources.map(formatSourceName).join(", ")
      : null;
  }
  return entries
    .map((entry) => {
      const source = formatSourceName(entry.source);
      const status = entry.status?.trim() || "not reported";
      return `${source}: ${status}`;
    })
    .join(", ");
}

function formatSourceName(source: string | null | undefined): string {
  const trimmed = source?.trim();
  return trimmed ? trimmed : "Unknown source";
}

function normalizeExportUserRole(
  role: string | null | undefined,
): ExportUserRole {
  const normalized = role?.toLowerCase().replace(/^org:/, "").trim();
  if (
    normalized === "admin" ||
    normalized === "attorney" ||
    normalized === "scientist" ||
    normalized === "client"
  ) {
    return normalized;
  }
  return "unknown";
}

function getExportFormatRestrictions(
  role: ExportUserRole,
  roleState: ExportRoleResolutionState = "ready",
): Partial<Record<ExportFormat, string>> {
  if (roleState === "loading") {
    return LOADING_EXPORT_FORMAT_RESTRICTIONS;
  }
  if (roleState === "unavailable") {
    return UNAVAILABLE_EXPORT_FORMAT_RESTRICTIONS;
  }
  if (role === "scientist") {
    return SCIENTIST_EXPORT_FORMAT_RESTRICTIONS;
  }
  if (role === "client") {
    return CLIENT_EXPORT_FORMAT_RESTRICTIONS;
  }
  if (role === "unknown") {
    return UNKNOWN_EXPORT_FORMAT_RESTRICTIONS;
  }
  return NO_EXPORT_FORMAT_RESTRICTIONS;
}

function getActiveExportFormat(
  selectedFormat: ExportFormat,
  restrictions: Partial<Record<ExportFormat, string>>,
): ExportFormat {
  if (!restrictions[selectedFormat]) {
    return selectedFormat;
  }
  return (
    EXPORT_FORMAT_FALLBACK_ORDER.find((format) => !restrictions[format]) ??
    selectedFormat
  );
}

function getExportStartFailureMessage(
  err: unknown,
  {
    verifiedClaimChartPacketActive,
  }: { verifiedClaimChartPacketActive: boolean },
): string {
  if (err instanceof APIError) {
    if (err.status === 403 && verifiedClaimChartPacketActive) {
      return "Export blocked — DOCX claim-chart packets require a counsel or admin role. Use a PDF/CSV/XLSX packet or ask counsel to generate the verified DOCX.";
    }
    if (err.status === 401 || err.status === 403) {
      return "Export blocked — your role or session cannot start this export.";
    }
    if (err.status >= 400 && err.status < 500) {
      return "Export blocked — review readiness and packet scope before trying again.";
    }
  }
  return "Export failed — please try again. If this repeats, use your deployment operator's approved support channel.";
}
