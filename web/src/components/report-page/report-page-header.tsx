"use client";

import { useRef, useState } from "react";
import type { ReactNode, RefObject } from "react";
import {
  AlertTriangle,
  ArrowRight,
  ChevronDown,
  CheckCircle2,
  DatabaseZap,
  Download,
  Eye,
  FileCheck2,
  FileLock2,
  Info,
  LockKeyhole,
  Loader2,
  MessageSquareText,
  Printer,
  Radar,
  Scale,
  Share2,
  ShieldAlert,
  Sparkles,
  UserCheck,
  Users,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import { Button } from "@/components/ui/button";
import { FlagButton } from "@/components/collaboration/flag-button";
import { RiskBadge } from "@/components/shared/risk-badge";
import { Breadcrumb } from "@/components/shared/breadcrumb";
import { ReportCoverageBanner } from "@/components/report/coverage-banner";
import { ReportMobileDisclosure } from "@/components/report/report-mobile-disclosure";
import { ReviewerDecisionButton } from "@/components/report/reviewer-decision-button";
import { VerdictBanner } from "@/components/report/verdict-banner";
import { ShareAnalyticsStats } from "@/components/report/share-analytics-stats";
import { WatchToggle } from "@/components/report/watch-toggle";
import { ReportWatchRecoveryNotice } from "@/components/report-page/report-watch-recovery-notice";
import {
  ReportEvidenceFact,
  getCanonicalBlockerCounts,
  getEvidenceQualityMeta,
  getReportEvidenceItems,
  type ReportEvidenceFactItem,
} from "@/components/report-page/report-page-header-evidence";
import {
  RelianceReadinessPanel,
  type ReadinessTone,
  type RelianceReadinessModel,
  type ReportReviewHandoffDraft,
  type ReportReviewHandoffState,
} from "@/components/report-page/report-page-header-readiness";
import {
  formatShareViewCount,
  getRelianceReadinessModel,
} from "@/components/report-page/report-page-header-readiness-model";
import { useSharedReportWatchControl } from "@/components/report-page/use-report-watch-control";
import type { ApprovalStatus } from "@/components/collaboration/approval-flow";
import type { ReportChatLaunchContext } from "@/components/report/chat-launch-context";
import { motionAwareScrollBehavior } from "@/lib/motion-preferences";
import {
  formatReportRiskLabel,
  getReportReference,
} from "@/components/report-page/report-command-summary";
import { formatRelativeTime } from "@/components/report/share-analytics-helpers";
import { cn, formatDate } from "@/lib/utils";
import { canManageReportCollaboration } from "@/lib/report-permissions";
import type { FTOReport, RiskLevel } from "@praviar/shared-types";
import type { AnalysisReviewStatusResponse } from "@/hooks/use-analysis-review-status";
import type { ReportWorkspaceSummaryResponse } from "@/hooks/use-report-workspace-summary";
import type { ReviewerDecisionListResponse } from "@/hooks/use-reviewer-decisions";

interface ReportPageHeaderProps {
  analysisId: string;
  token: string | null;
  report: FTOReport;
  sectionNavigation?: ReactNode;
  showDecisionCockpit?: boolean;
  shareActive?: boolean;
  shareRecipientBound?: boolean;
  shareViewCount?: number | null;
  shareLastViewedAt?: string | null;
  onExport: () => void;
  onShare: () => void;
  onMonitorPlan?: () => void;
  onFeedback: () => void;
  onAskAi?: (context?: ReportChatLaunchContext) => void;
  askAiButtonRef?: RefObject<HTMLButtonElement | null>;
  onOpenComments?: () => void;
  onPrepareHandoff?: (draft: ReportReviewHandoffDraft) => void;
  reviewHandoffState?: ReportReviewHandoffState;
  onReviewOpen?: () => void;
  reviewerDecisions?: ReviewerDecisionListResponse | null;
  reviewerDecisionsLoading?: boolean;
  reviewStatus?: AnalysisReviewStatusResponse;
  reviewStatusLoading?: boolean;
  workspaceSummary?: ReportWorkspaceSummaryResponse;
  workspaceSummaryLoading?: boolean;
  currentUserRole?: string | null;
  canExportReport?: boolean;
}

export type {
  ReportReviewHandoffDraft,
  ReportReviewHandoffState,
} from "@/components/report-page/report-page-header-readiness";

type ReportWatchControl = ReturnType<typeof useSharedReportWatchControl>;

function ReportHeaderIdentity({
  evidenceQualityLabel,
  executionProfileLabel,
  report,
  reportReference,
  risk,
  riskLabel,
}: {
  evidenceQualityLabel: string;
  executionProfileLabel: string | null;
  report: FTOReport;
  reportReference: string;
  risk: RiskLevel;
  riskLabel: string;
}) {
  return (
    <div className="min-w-0">
      <div className="flex min-w-0 items-start gap-3 sm:gap-4">
        <PraviarMarkFrame
          size="xs"
          className="sm:h-12 sm:w-12"
          markClassName="sm:h-10 sm:w-10"
        />
        <div className="min-w-0 flex-1">
          <div className="hidden min-w-0 flex-col items-start gap-1.5 text-xs font-semibold uppercase text-[var(--text-tertiary)] sm:flex sm:flex-row sm:flex-wrap sm:items-center sm:gap-2">
            <span>Praviar FTO decision packet</span>
            <span
              className="inline-flex w-full max-w-full items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-2 py-0.5 font-mono tracking-normal text-[var(--text-secondary)] [overflow-wrap:anywhere] sm:w-auto sm:max-w-[15rem]"
              title={reportReference}
            >
              <span className="truncate [overflow-wrap:anywhere]">
                {reportReference}
              </span>
            </span>
          </div>
          <h1
            id="report-workbench-title"
            className="max-w-xl break-words text-lg font-semibold leading-6 text-[var(--text-primary)] [overflow-wrap:anywhere] sm:mt-2 sm:type-heading-xl"
          >
            {report.compound?.name ?? "Unknown Compound"}
          </h1>
          <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-2 sm:mt-3">
            <RiskBadge risk={risk} label={riskLabel} size="sm" />
            <Badge
              variant="secondary"
              className="hidden text-xs uppercase sm:inline-flex"
            >
              {evidenceQualityLabel}
            </Badge>
            <p className="hidden text-xs text-[var(--text-tertiary)] sm:block">
              Generated {formatDate(report.generated_at)}
            </p>
            {executionProfileLabel ? (
              <Badge
                variant="secondary"
                className="hidden text-xs uppercase sm:inline-flex"
              >
                {executionProfileLabel}
              </Badge>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function PrimaryReportActions({
  analysisId,
  canExport,
  canManageCollaboration,
  onAskAi,
  onExportAction,
  onMonitorPlan,
  onPrepareHandoff,
  onReviewOpen,
  onShare,
  readinessModel,
  report,
  reviewStatus,
  reviewStatusLoading,
  token,
}: {
  analysisId: string;
  canExport: boolean;
  canManageCollaboration: boolean;
  onAskAi: ReportPageHeaderProps["onAskAi"];
  onExportAction: () => void;
  onMonitorPlan: ReportPageHeaderProps["onMonitorPlan"];
  onPrepareHandoff: ReportPageHeaderProps["onPrepareHandoff"];
  onReviewOpen: ReportPageHeaderProps["onReviewOpen"];
  onShare: () => void;
  readinessModel: RelianceReadinessModel;
  report: FTOReport;
  reviewStatus: ReportPageHeaderProps["reviewStatus"];
  reviewStatusLoading: ReportPageHeaderProps["reviewStatusLoading"];
  token: string | null;
}) {
  return (
    <div
      role="group"
      className="grid min-w-0 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5"
      aria-label="Primary report actions"
    >
      {canManageCollaboration ? (
        <ReviewerDecisionButton
          analysisId={analysisId}
          token={token}
          report={report}
          variant="default"
          className="min-h-11 justify-center gap-2"
          onBeforeOpen={onReviewOpen}
          reviewStatus={reviewStatus}
          reviewStatusLoading={reviewStatusLoading}
        />
      ) : (
        <Button
          type="button"
          variant="default"
          className="min-h-11 justify-center gap-2"
          onClick={() => onPrepareHandoff?.(readinessModel.handoffDraft)}
          disabled={!onPrepareHandoff}
          aria-label="Request counsel review"
        >
          <Users className="h-3.5 w-3.5" aria-hidden="true" />
          <span>Request counsel</span>
        </Button>
      )}
      <Button
        variant="outline"
        size="sm"
        className="min-h-11 justify-center gap-2"
        onClick={() => onAskAi?.(readinessModel.aiContext)}
        disabled={!onAskAi}
        aria-label="AI-assisted report critique: readiness and evidence gaps"
      >
        <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
        <span>Check report gaps</span>
      </Button>
      {canManageCollaboration ? (
        <Button
          variant="ghost"
          size="sm"
          className="min-h-11 gap-2"
          onClick={onShare}
          aria-label="Share"
        >
          <Share2 className="h-3.5 w-3.5" aria-hidden="true" />
          <span>Share</span>
        </Button>
      ) : null}
      {onMonitorPlan ? (
        <Button
          variant="ghost"
          size="sm"
          className="min-h-11 gap-2"
          onClick={onMonitorPlan}
          aria-label="Open report-to-monitor plan"
        >
          <Radar className="h-3.5 w-3.5" aria-hidden="true" />
          <span>Monitor plan</span>
        </Button>
      ) : null}
      {canExport ? (
        <Button
          variant="outline"
          size="sm"
          className={cn(
            "min-h-11 gap-2",
            readinessModel.exportAction.tone === "blocked" &&
              "border-error/35 bg-error/8 text-error hover:bg-error/12 hover:text-error",
            (readinessModel.exportAction.tone === "verify" ||
              readinessModel.exportAction.tone === "caveat") &&
              "border-warning/35 bg-warning/8 text-warning hover:bg-warning/12 hover:text-warning",
          )}
          onClick={onExportAction}
          aria-label={readinessModel.exportAction.ariaLabel}
        >
          {readinessModel.exportAction.tone === "ready" ||
          readinessModel.exportAction.tone === "caveat" ? (
            <Download className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <LockKeyhole className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          <span>{readinessModel.exportAction.label}</span>
        </Button>
      ) : null}
    </div>
  );
}

function SecondaryReportUtilities({
  analysisId,
  canManageCollaboration,
  onFeedback,
  watchControl,
  watchControlsLocked,
}: {
  analysisId: string;
  canManageCollaboration: boolean;
  onFeedback: () => void;
  watchControl: ReportWatchControl;
  watchControlsLocked: boolean;
}) {
  return (
    <div
      role="group"
      className="grid min-w-0 gap-2 border-t border-[var(--border-subtle)] pt-2 sm:grid-cols-2 xl:grid-cols-4"
      aria-label="Secondary report utilities"
    >
      <Button
        variant="ghost"
        size="sm"
        className="min-h-11 justify-center gap-2"
        onClick={() => window.print()}
        aria-label="Print current report section"
      >
        <Printer className="h-3.5 w-3.5" aria-hidden="true" />
        <span>Print section</span>
      </Button>
      <WatchToggle
        analysisId={analysisId}
        enabled={watchControl.watchEnabled}
        isPending={watchControlsLocked}
        schedule={watchControl.watchSchedule}
        onToggle={watchControl.handleWatchToggle}
      />
      <FlagButton
        analysisId={analysisId}
        variant="ghost"
        size="sm"
        className="min-h-11"
      />
      {canManageCollaboration ? (
        <Button
          variant="ghost"
          size="sm"
          className="min-h-11 gap-2"
          onClick={onFeedback}
          aria-label="Submit feedback"
        >
          <MessageSquareText className="h-3.5 w-3.5" aria-hidden="true" />
          <span>Feedback</span>
        </Button>
      ) : null}
    </div>
  );
}

function DesktopReportControls({
  analysisId,
  canExport,
  canManageCollaboration,
  onAskAi,
  onExportAction,
  onFeedback,
  onMonitorPlan,
  onPrepareHandoff,
  onReviewOpen,
  onShare,
  readinessModel,
  report,
  reviewStatus,
  reviewStatusLoading,
  shareActive,
  shareLastViewedAt,
  shareViewCount,
  token,
  watchControl,
  watchControlsLocked,
}: {
  analysisId: string;
  canExport: boolean;
  canManageCollaboration: boolean;
  onAskAi: ReportPageHeaderProps["onAskAi"];
  onExportAction: () => void;
  onFeedback: () => void;
  onMonitorPlan: ReportPageHeaderProps["onMonitorPlan"];
  onPrepareHandoff: ReportPageHeaderProps["onPrepareHandoff"];
  onReviewOpen: ReportPageHeaderProps["onReviewOpen"];
  onShare: () => void;
  readinessModel: RelianceReadinessModel;
  report: FTOReport;
  reviewStatus: ReportPageHeaderProps["reviewStatus"];
  reviewStatusLoading: ReportPageHeaderProps["reviewStatusLoading"];
  shareActive: ReportPageHeaderProps["shareActive"];
  shareLastViewedAt: ReportPageHeaderProps["shareLastViewedAt"];
  shareViewCount: ReportPageHeaderProps["shareViewCount"];
  token: string | null;
  watchControl: ReportWatchControl;
  watchControlsLocked: boolean;
}) {
  return (
    <div className="hidden min-w-0 lg:block">
      <div
        role="group"
        aria-label="Report actions"
        className="praviar-glass-panel-soft w-full min-w-0 rounded-lg border border-[var(--border-subtle)] p-2 shadow-[var(--shadow-xs)]"
      >
        <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-2 pb-2">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
              Decision controls
            </p>
            <p className="mt-0.5 max-w-xl text-xs leading-5 text-[var(--text-secondary)]">
              Review, critique, share, and export this packet from one governed
              rail.
            </p>
          </div>
        </div>
        <div className="grid min-w-0 gap-2 px-1 pt-2 text-xs">
          <PrimaryReportActions
            analysisId={analysisId}
            canExport={canExport}
            canManageCollaboration={canManageCollaboration}
            onAskAi={onAskAi}
            onExportAction={onExportAction}
            onMonitorPlan={onMonitorPlan}
            onPrepareHandoff={onPrepareHandoff}
            onReviewOpen={onReviewOpen}
            onShare={onShare}
            readinessModel={readinessModel}
            report={report}
            reviewStatus={reviewStatus}
            reviewStatusLoading={reviewStatusLoading}
            token={token}
          />
          {shareActive ? (
            <ReportShareHandoffChip
              viewCount={shareViewCount ?? 0}
              lastViewedAt={shareLastViewedAt}
            />
          ) : null}
          <SecondaryReportUtilities
            analysisId={analysisId}
            canManageCollaboration={canManageCollaboration}
            onFeedback={onFeedback}
            watchControl={watchControl}
            watchControlsLocked={watchControlsLocked}
          />
          {watchControl.watchRecovery ? (
            <ReportWatchRecoveryNotice
              actionPending={watchControl.watchPending}
              onAction={() => {
                void watchControl.handleWatchRecoveryAction();
              }}
              recovery={watchControl.watchRecovery}
              surface="desktop"
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}

function EvidenceFactsDisclosure({
  evidenceItems,
  onOpenChange,
  open,
}: {
  evidenceItems: ReportEvidenceFactItem[];
  onOpenChange: (open: boolean) => void;
  open: boolean;
}) {
  return (
    <details
      className="group rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/58 shadow-[var(--shadow-xs)]"
      data-testid="report-evidence-facts-disclosure"
      open={open}
      onToggle={(event) => onOpenChange(event.currentTarget.open)}
    >
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 sm:px-4 [&::-webkit-details-marker]:hidden">
        <span className="min-w-0">
          <span className="block text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
            Evidence facts
          </span>
          <span className="mt-0.5 block text-sm font-semibold text-[var(--text-primary)]">
            Coverage, source health, and screening facts
          </span>
        </span>
        <span className="inline-flex shrink-0 items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-glass)] px-2.5 py-1 text-xs font-semibold text-brand-primary">
          {open ? "Hide" : "Show"} details
          <ChevronDown
            className={cn("h-4 w-4 transition-transform", open && "rotate-180")}
            aria-hidden="true"
          />
        </span>
      </summary>
      <div className="grid min-w-0 auto-rows-min gap-3 border-t border-[var(--border-subtle)] p-3 sm:grid-cols-2 sm:p-4 xl:grid-cols-4">
        {evidenceItems.map((item, index) => (
          <ReportEvidenceFact key={item.label} step={index + 1} {...item} />
        ))}
      </div>
    </details>
  );
}

function ReportReadinessDetails({
  askAiButtonRef,
  evidenceItems,
  model,
  onAskAi,
  onOpenComments,
  onPrepareHandoff,
  onReadinessFactsOpenChange,
  readinessFactsOpen,
  report,
  reviewHandoffState,
  reviewStatus,
  shareActive,
  shareLastViewedAt,
  shareViewCount,
}: {
  askAiButtonRef: ReportPageHeaderProps["askAiButtonRef"];
  evidenceItems: ReportEvidenceFactItem[];
  model: RelianceReadinessModel;
  onAskAi: ReportPageHeaderProps["onAskAi"];
  onOpenComments: ReportPageHeaderProps["onOpenComments"];
  onPrepareHandoff: ReportPageHeaderProps["onPrepareHandoff"];
  onReadinessFactsOpenChange: (open: boolean) => void;
  readinessFactsOpen: boolean;
  report: FTOReport;
  reviewHandoffState: ReportPageHeaderProps["reviewHandoffState"];
  reviewStatus: ReportPageHeaderProps["reviewStatus"];
  shareActive: ReportPageHeaderProps["shareActive"];
  shareLastViewedAt: ReportPageHeaderProps["shareLastViewedAt"];
  shareViewCount: ReportPageHeaderProps["shareViewCount"];
}) {
  return (
    <div className="hidden group-open:block sm:block">
      <div
        role="region"
        aria-label="Report readiness console"
        className="praviar-provenance-rail scroll-mt-24 border-t border-[var(--border-subtle)] p-4"
        data-testid="report-evidence-handoff"
      >
        <div className="grid gap-3">
          <RelianceReadinessPanel
            model={model}
            onAskAi={onAskAi}
            askAiButtonRef={askAiButtonRef}
            onOpenComments={onOpenComments}
            onPrepareHandoff={onPrepareHandoff}
            reviewHandoffState={reviewHandoffState}
          />
          <EvidenceFactsDisclosure
            evidenceItems={evidenceItems}
            onOpenChange={onReadinessFactsOpenChange}
            open={readinessFactsOpen}
          />
        </div>
      </div>
      <div className="border-t border-[var(--border-subtle)]">
        <VerdictBanner
          report={report}
          embedded
          approvalStatus={getVerdictApprovalStatus(reviewStatus)}
          approvalApprover={getVerdictApprovalApprover(reviewStatus)}
          approvalApprovedAt={getVerdictApprovalDate(reviewStatus)}
        />
        <div className="grid gap-3 border-t border-[var(--border-subtle)] p-4 sm:p-5 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.75fr)] lg:items-start">
          <ReportCoverageBanner report={report} />
          <div className="praviar-glass-panel-soft flex gap-2 rounded-lg px-3 py-2.5 text-xs text-[var(--text-secondary)]">
            <Info
              className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--text-tertiary)]"
              aria-hidden="true"
            />
            <p>
              AI has scoped evidence, blockers, and caveats; qualified patent
              counsel should review before commercial reliance.
            </p>
          </div>
        </div>
      </div>
      {shareActive ? (
        <div className="praviar-glass-strip border-t border-[var(--border-subtle)] p-4">
          <p className="mb-2 text-xs font-medium text-[var(--text-secondary)]">
            Share active — open Share to retrieve, copy, or revoke the link
          </p>
          <ShareAnalyticsStats
            viewCount={shareViewCount ?? 0}
            lastAccessedAt={shareLastViewedAt}
          />
        </div>
      ) : null}
    </div>
  );
}

function ReportDecisionAndReadiness({
  askAiButtonRef,
  evidenceItems,
  model,
  onAskAi,
  onOpenComments,
  onPrepareHandoff,
  onReadinessFactsOpenChange,
  readinessDetailsRef,
  readinessFactsOpen,
  report,
  reviewHandoffState,
  reviewStatus,
  riskLabel,
  shareActive,
  shareLastViewedAt,
  shareViewCount,
  snapshotItems,
}: {
  askAiButtonRef: ReportPageHeaderProps["askAiButtonRef"];
  evidenceItems: ReportEvidenceFactItem[];
  model: RelianceReadinessModel;
  onAskAi: ReportPageHeaderProps["onAskAi"];
  onOpenComments: ReportPageHeaderProps["onOpenComments"];
  onPrepareHandoff: ReportPageHeaderProps["onPrepareHandoff"];
  onReadinessFactsOpenChange: (open: boolean) => void;
  readinessDetailsRef: RefObject<HTMLDetailsElement | null>;
  readinessFactsOpen: boolean;
  report: FTOReport;
  reviewHandoffState: ReportPageHeaderProps["reviewHandoffState"];
  reviewStatus: ReportPageHeaderProps["reviewStatus"];
  riskLabel: string;
  shareActive: ReportPageHeaderProps["shareActive"];
  shareLastViewedAt: ReportPageHeaderProps["shareLastViewedAt"];
  shareViewCount: ReportPageHeaderProps["shareViewCount"];
  snapshotItems: DecisionPacketSnapshotItem[];
}) {
  return (
    <section
      aria-label="Report decision and readiness"
      className="praviar-report-decision-field order-1 overflow-hidden rounded-lg sm:order-2"
      data-no-print
    >
      <div className="p-4 sm:p-5">
        <ReportDecisionMemo
          items={snapshotItems}
          model={model}
          onAskAi={onAskAi}
          onPrepareHandoff={onPrepareHandoff}
          reviewHandoffState={reviewHandoffState}
          riskLabel={riskLabel}
        />
      </div>
      <details
        ref={readinessDetailsRef}
        className="group border-t border-[var(--border-subtle)] sm:contents"
      >
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 bg-[var(--surface-muted)]/45 px-4 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 sm:hidden [&::-webkit-details-marker]:hidden">
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-[var(--text-primary)]">
              Readiness and reliance controls
            </span>
            <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
              Open evidence facts, coverage, verdict, and counsel caveats.
            </span>
          </span>
          <ChevronDown
            className="h-4 w-4 shrink-0 text-brand-primary transition-transform group-open:rotate-180"
            aria-hidden="true"
          />
        </summary>
        <ReportReadinessDetails
          askAiButtonRef={askAiButtonRef}
          evidenceItems={evidenceItems}
          model={model}
          onAskAi={onAskAi}
          onOpenComments={onOpenComments}
          onPrepareHandoff={onPrepareHandoff}
          onReadinessFactsOpenChange={onReadinessFactsOpenChange}
          readinessFactsOpen={readinessFactsOpen}
          report={report}
          reviewHandoffState={reviewHandoffState}
          reviewStatus={reviewStatus}
          shareActive={shareActive}
          shareLastViewedAt={shareLastViewedAt}
          shareViewCount={shareViewCount}
        />
      </details>
    </section>
  );
}

function ReportDecisionArea({
  sectionNavigation,
  showDecisionCockpit,
  ...decisionProps
}: {
  sectionNavigation: ReactNode;
  showDecisionCockpit: boolean;
} & Parameters<typeof ReportDecisionAndReadiness>[0]) {
  if (!sectionNavigation && !showDecisionCockpit) return null;

  return (
    <div className="flex min-w-0 flex-col gap-6">
      {sectionNavigation ? (
        <div
          className={cn("min-w-0", showDecisionCockpit && "order-2 sm:order-1")}
          data-testid="report-section-navigation-slot"
        >
          {sectionNavigation}
        </div>
      ) : null}
      {showDecisionCockpit ? (
        <ReportDecisionAndReadiness {...decisionProps} />
      ) : null}
    </div>
  );
}

export function ReportPageHeader({
  analysisId,
  token,
  report,
  sectionNavigation,
  showDecisionCockpit = true,
  shareActive,
  shareRecipientBound,
  shareViewCount,
  shareLastViewedAt,
  onExport,
  onShare,
  onMonitorPlan,
  onFeedback,
  onAskAi,
  askAiButtonRef,
  onOpenComments,
  onPrepareHandoff,
  reviewHandoffState,
  onReviewOpen,
  reviewerDecisions,
  reviewerDecisionsLoading,
  reviewStatus,
  reviewStatusLoading,
  workspaceSummary,
  workspaceSummaryLoading,
  currentUserRole,
  canExportReport,
}: ReportPageHeaderProps) {
  const canManageCollaboration = canManageReportCollaboration(currentUserRole);
  const canExport = canExportReport ?? canManageCollaboration;
  const watchControl = useSharedReportWatchControl();
  const { watchControlsLocked = false } = watchControl;
  const evidenceItems = getReportEvidenceItems(report);
  const reportReference = getReportReference(report);
  const riskLabel = formatReportRiskLabel(report.risk_summary.overall_risk);
  const risk = report.risk_summary.overall_risk as RiskLevel;
  const evidenceQuality = getEvidenceQualityMeta(
    report.clearance_decision?.evidence_quality,
  );
  const executionProfileLabel = getExecutionProfileLabel(
    report.execution_profile,
  );
  const readinessModel = getRelianceReadinessModel({
    analysisId,
    report,
    shareActive,
    shareRecipientBound,
    reviewerDecisions,
    reviewerDecisionsLoading,
    reviewStatus,
    reviewStatusLoading,
    workspaceSummary,
    workspaceSummaryLoading,
  });
  const packetSnapshotItems = getDecisionPacketSnapshotItems({
    evidenceItems,
    evidenceQuality,
    readinessModel,
    report,
    riskLabel,
  });
  const [readinessFactsOpen, setReadinessFactsOpen] = useState(
    readinessModel.statusTone !== "success",
  );
  const readinessDetailsRef = useRef<HTMLDetailsElement>(null);
  const focusRelianceReadiness = () => {
    if (readinessDetailsRef.current) {
      readinessDetailsRef.current.open = true;
    }
    const target = document.getElementById("report-reliance-readiness");
    target?.scrollIntoView?.({
      block: "center",
      behavior: motionAwareScrollBehavior(),
    });
    requestAnimationFrame(() => {
      const action = target?.querySelector<HTMLElement>(
        '[data-testid="report-export-recovery-ai-action"], [data-testid="report-reliance-ai-action"]',
      );
      action?.focus();
    });
  };
  const handleExportAction = () => {
    if (
      readinessModel.exportAction.tone === "ready" ||
      readinessModel.exportAction.tone === "caveat"
    ) {
      onExport();
      return;
    }

    focusRelianceReadiness();
  };

  return (
    <>
      <Breadcrumb
        ariaLabel="Report breadcrumb"
        className="lg:hidden"
        items={[
          { label: "Analyses", href: "/analyses" },
          {
            label: report.compound?.name ?? "Analysis",
            href: `/analyses/${analysisId}`,
          },
          { label: "Report" },
        ]}
      />
      <section
        aria-labelledby="report-workbench-title"
        className="praviar-report-decision-field overflow-hidden rounded-lg"
        data-no-print
      >
        <div className="grid min-w-0 gap-4 p-3 sm:p-5">
          <ReportHeaderIdentity
            evidenceQualityLabel={evidenceQuality.label}
            executionProfileLabel={executionProfileLabel}
            report={report}
            reportReference={reportReference}
            risk={risk}
            riskLabel={riskLabel}
          />
          <DesktopReportControls
            analysisId={analysisId}
            canExport={canExport}
            canManageCollaboration={canManageCollaboration}
            onAskAi={onAskAi}
            onExportAction={handleExportAction}
            onFeedback={onFeedback}
            onMonitorPlan={onMonitorPlan}
            onPrepareHandoff={onPrepareHandoff}
            onReviewOpen={onReviewOpen}
            onShare={onShare}
            readinessModel={readinessModel}
            report={report}
            reviewStatus={reviewStatus}
            reviewStatusLoading={reviewStatusLoading}
            shareActive={shareActive}
            shareLastViewedAt={shareLastViewedAt}
            shareViewCount={shareViewCount}
            token={token}
            watchControl={watchControl}
            watchControlsLocked={watchControlsLocked}
          />
        </div>
      </section>
      <ReportDecisionArea
        askAiButtonRef={askAiButtonRef}
        evidenceItems={evidenceItems}
        model={readinessModel}
        onAskAi={onAskAi}
        onOpenComments={onOpenComments}
        onPrepareHandoff={onPrepareHandoff}
        onReadinessFactsOpenChange={setReadinessFactsOpen}
        readinessDetailsRef={readinessDetailsRef}
        readinessFactsOpen={readinessFactsOpen}
        report={report}
        reviewHandoffState={reviewHandoffState}
        reviewStatus={reviewStatus}
        riskLabel={riskLabel}
        sectionNavigation={sectionNavigation}
        shareActive={shareActive}
        shareLastViewedAt={shareLastViewedAt}
        shareViewCount={shareViewCount}
        showDecisionCockpit={showDecisionCockpit}
        snapshotItems={packetSnapshotItems}
      />
    </>
  );
}

function getVerdictApprovalStatus(
  reviewStatus?: AnalysisReviewStatusResponse,
): ApprovalStatus {
  switch (reviewStatus?.status) {
    case "approved":
      return "approved";
    case "changes_requested":
      return "changes_requested";
    case "under_review":
      return "under_review";
    default:
      return "pending";
  }
}

function getVerdictApprovalApprover(
  reviewStatus?: AnalysisReviewStatusResponse,
): string | undefined {
  return (
    reviewStatus?.reviewer_name ?? reviewStatus?.reviewer_email ?? undefined
  );
}

function getVerdictApprovalDate(
  reviewStatus?: AnalysisReviewStatusResponse,
): string | undefined {
  if (
    reviewStatus?.status !== "approved" &&
    reviewStatus?.status !== "changes_requested"
  ) {
    return undefined;
  }

  return reviewStatus.reviewed_at ?? undefined;
}

function ReportShareHandoffChip({
  lastViewedAt,
  viewCount,
}: {
  lastViewedAt?: string | null;
  viewCount: number;
}) {
  return (
    <div
      aria-label="External share status"
      className="rounded-lg border border-info/20 bg-info/10 px-3 py-2 text-info"
      role="status"
    >
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <span className="inline-flex min-w-0 items-center gap-2 text-xs font-semibold">
          <Share2 className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span className="min-w-0 truncate">External share active</span>
        </span>
        <span className="inline-flex shrink-0 items-center gap-1 text-xs font-semibold tabular-nums">
          <Eye className="h-3.5 w-3.5" aria-hidden="true" />
          {formatShareViewCount(viewCount)}
        </span>
      </div>
      <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
        Last viewed {lastViewedAt ? formatRelativeTime(lastViewedAt) : "never"}
      </p>
    </div>
  );
}

interface DecisionPacketSnapshotItem {
  detail: string;
  icon: ReactNode;
  label: string;
  tone: ReadinessTone;
  value: string;
}

function buildDecisionMemoViewModel({
  items,
  model,
  riskLabel,
}: {
  items: DecisionPacketSnapshotItem[];
  model: RelianceReadinessModel;
  riskLabel: string;
}) {
  const riskPosture = items.find((item) => item.label === "Risk posture");
  const evidenceBasis = items.find((item) => item.label === "Evidence basis");
  const sourceScope = items.find((item) => item.label === "Source scope");
  const evidenceValue = [evidenceBasis?.value, sourceScope?.value]
    .filter(Boolean)
    .join(" / ");
  const evidenceDetail = [evidenceBasis?.detail, sourceScope?.detail]
    .filter(Boolean)
    .join(" ");
  const memoItems: DecisionPacketSnapshotItem[] = [
    {
      detail: riskPosture?.detail ?? "Screening result requires review.",
      icon: riskPosture?.icon ?? <Scale className="h-3.5 w-3.5" />,
      label: "Decision posture",
      tone: riskPosture?.tone ?? model.statusTone,
      value: riskLabel,
    },
    {
      detail: model.lifecycleState.owner,
      icon: <FileLock2 className="h-3.5 w-3.5" />,
      label: "Reliance gate",
      tone: model.statusTone,
      value: compactReadinessStatusLabel(model.statusLabel),
    },
    {
      detail: model.lifecycleState.detail,
      icon: <ShieldAlert className="h-3.5 w-3.5" />,
      label: "Top blocker",
      tone: model.lifecycleState.tone,
      value: model.lifecycleState.blocker,
    },
    {
      detail:
        evidenceDetail || "Coverage and source facts remain visible below.",
      icon: evidenceBasis?.icon ?? <DatabaseZap className="h-3.5 w-3.5" />,
      label: "Evidence basis",
      tone: evidenceBasis?.tone ?? sourceScope?.tone ?? "neutral",
      value: evidenceValue || "Evidence review",
    },
    {
      detail: model.lifecycleState.owner,
      icon: <ArrowRight className="h-3.5 w-3.5" />,
      label: "Next counsel action",
      tone: model.lifecycleState.tone,
      value: compactDecisionMemoAction(model.lifecycleState.nextAction),
    },
  ];
  const primaryMemoItems = memoItems.filter((item) =>
    ["Top blocker", "Next counsel action"].includes(item.label),
  );

  return {
    evidenceValue,
    primaryMemoItems,
    statusIcon:
      model.statusTone === "success" ? (
        <CheckCircle2 className="h-5 w-5" />
      ) : (
        <AlertTriangle className="h-5 w-5" />
      ),
    supportingMemoItems: memoItems.filter(
      (item) => !primaryMemoItems.includes(item),
    ),
  };
}

function ReportDecisionMemo({
  items,
  model,
  onAskAi,
  onPrepareHandoff,
  reviewHandoffState,
  riskLabel,
}: {
  items: DecisionPacketSnapshotItem[];
  model: RelianceReadinessModel;
  onAskAi?: (context?: ReportChatLaunchContext) => void;
  onPrepareHandoff?: (draft: ReportReviewHandoffDraft) => void;
  reviewHandoffState?: ReportReviewHandoffState;
  riskLabel: string;
}) {
  const viewModel = buildDecisionMemoViewModel({ items, model, riskLabel });

  return (
    <section
      aria-label="FTO decision brief"
      className={cn(
        "rounded-lg border px-3 py-3 shadow-[var(--shadow-xs)] sm:px-4",
        model.statusTone === "danger" && "border-error/25 bg-error/8",
        model.statusTone === "warning" && "border-warning/30 bg-warning/8",
        model.statusTone === "success" && "border-success/25 bg-success/8",
        model.statusTone === "neutral" &&
          "border-brand-primary/18 bg-brand-primary/[0.055]",
      )}
      data-testid="report-decision-memo"
    >
      <div className="grid min-w-0 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(12rem,0.42fr)] lg:items-start">
        <div className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-start gap-3">
          <span
            className={cn(
              "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border",
              model.statusTone === "danger" &&
                "border-error/25 bg-error/10 text-error",
              model.statusTone === "warning" &&
                "border-warning/25 bg-warning/10 text-warning",
              model.statusTone === "success" &&
                "border-success/25 bg-success/10 text-success",
              model.statusTone === "neutral" &&
                "border-brand-primary/20 bg-brand-primary/10 text-brand-primary",
            )}
            aria-hidden="true"
          >
            {viewModel.statusIcon}
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
              FTO decision brief
            </p>
            <h2 className="mt-1 text-lg font-semibold leading-6 text-[var(--text-primary)]">
              {riskLabel}: {compactReadinessStatusLabel(model.statusLabel)}
            </h2>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              {model.headline}
            </p>
          </div>
        </div>
        <div className="hidden rounded-md border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-elevated)_80%,transparent)] px-3 py-2 sm:block">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
            Reliance state
          </p>
          <p
            className={cn(
              "mt-1 text-sm font-semibold leading-5 text-[var(--text-primary)]",
              model.statusTone === "danger" && "text-error",
              model.statusTone === "warning" && "text-warning",
              model.statusTone === "success" && "text-success",
            )}
          >
            {model.lifecycleState.label}
          </p>
          <p className="mt-0.5 line-clamp-2 text-xs leading-4 text-[var(--text-secondary)]">
            Owner: {model.lifecycleState.owner}
          </p>
        </div>
      </div>
      <dl className="mt-3 grid min-w-0 gap-2 sm:grid-cols-2 2xl:grid-cols-3">
        {viewModel.primaryMemoItems.map((item) => (
          <DecisionMemoDatum key={item.label} {...item} />
        ))}
      </dl>
      <div className="mt-3">
        <ReportMobileDisclosure
          label="Evidence, ownership & readiness details"
          description={`${model.exportAction.label}. ${viewModel.evidenceValue || "Evidence facts available"}.`}
          testId="report-decision-memo-details"
        >
          <dl className="grid min-w-0 gap-2 sm:grid-cols-2">
            {viewModel.supportingMemoItems.map((item) => (
              <DecisionMemoDatum key={item.label} {...item} />
            ))}
          </dl>
          <DecisionActionCockpit
            model={model}
            onAskAi={onAskAi}
            onPrepareHandoff={onPrepareHandoff}
            reviewHandoffState={reviewHandoffState}
          />
        </ReportMobileDisclosure>
      </div>
    </section>
  );
}

function DecisionActionCockpit({
  model,
  onAskAi,
  onPrepareHandoff,
  reviewHandoffState,
}: {
  model: RelianceReadinessModel;
  onAskAi?: (context?: ReportChatLaunchContext) => void;
  onPrepareHandoff?: (draft: ReportReviewHandoffDraft) => void;
  reviewHandoffState?: ReportReviewHandoffState;
}) {
  const primaryAction = model.decisionQueue[0];
  const exportTone =
    model.exportAction.tone === "ready"
      ? "success"
      : model.exportAction.tone === "blocked"
        ? "danger"
        : "warning";
  const handoffPending = reviewHandoffState?.isPending === true;
  const handoffCreated = Boolean(reviewHandoffState?.commentId);
  const handoffDisabled = !onPrepareHandoff || handoffPending || handoffCreated;

  return (
    <div
      role="group"
      aria-label="Decision action rail"
      className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-elevated)_82%,transparent)] p-2.5 shadow-[var(--shadow-xs)]"
      data-testid="report-decision-cockpit"
    >
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
          Decision action rail
        </p>
        <span className="inline-flex min-h-7 items-center gap-1.5 rounded-full border border-brand-primary/20 bg-brand-primary/8 px-2.5 text-xs font-semibold uppercase text-brand-primary">
          <Sparkles className="h-3 w-3" aria-hidden="true" />
          AI gap check
        </span>
      </div>
      <div className="mt-2 grid gap-1.5 lg:grid-cols-3">
        <DecisionCockpitDatum
          detail={primaryAction?.detail ?? model.lifecycleState.nextAction}
          icon={<Sparkles className="h-3.5 w-3.5" />}
          label="Next required action"
          tone={primaryAction?.tone ?? model.statusTone}
          value={primaryAction?.label ?? "Verify gaps"}
        />
        <DecisionCockpitDatum
          detail={model.lifecycleState.label}
          icon={<UserCheck className="h-3.5 w-3.5" />}
          label="Owner"
          tone={model.lifecycleState.tone}
          value={model.lifecycleState.owner}
        />
        <DecisionCockpitDatum
          detail={compactLifecycleBlocker(model.lifecycleState.blocker)}
          icon={<LockKeyhole className="h-3.5 w-3.5" />}
          label="Export gate"
          tone={exportTone}
          value={model.exportAction.label}
        />
      </div>
      <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:hidden">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="min-h-11 justify-between gap-2"
          onClick={() => onAskAi?.(model.aiContext)}
          disabled={!onAskAi}
          aria-label="Open AI gap check from decision cockpit"
        >
          <span className="inline-flex items-center gap-2">
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
            Check with AI
          </span>
          <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="min-h-11 justify-between gap-2"
          onClick={() => onPrepareHandoff?.(model.handoffDraft)}
          disabled={handoffDisabled}
          aria-label="Prepare review handoff from decision cockpit"
        >
          <span className="inline-flex items-center gap-2">
            {handoffPending ? (
              <Loader2
                className="h-3.5 w-3.5 animate-spin"
                aria-hidden="true"
              />
            ) : (
              <FileCheck2 className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            {handoffCreated
              ? "Handoff created"
              : handoffPending
                ? "Preparing handoff"
                : "Prepare handoff"}
          </span>
          <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}

function DecisionCockpitDatum({
  detail,
  icon,
  label,
  tone,
  value,
}: {
  detail: string;
  icon: ReactNode;
  label: string;
  tone?: ReadinessTone;
  value: string;
}) {
  return (
    <div className="grid min-w-0 grid-cols-[1.75rem_minmax(0,1fr)] gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/72 px-2.5 py-2">
      <span className={decisionCockpitIconClass(tone)} aria-hidden="true">
        {icon}
      </span>
      <span className="min-w-0">
        <span className="block text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
          {label}
        </span>
        <span className="mt-0.5 block break-words text-xs font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
          {value}
        </span>
        <span className="mt-0.5 line-clamp-2 block text-xs leading-4 text-[var(--text-secondary)]">
          {detail}
        </span>
      </span>
    </div>
  );
}

function DecisionMemoDatum({
  detail,
  icon,
  label,
  tone,
  value,
}: {
  detail?: string;
  icon: ReactNode;
  label: string;
  tone?: ReadinessTone;
  value: string;
}) {
  return (
    <div className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/72 px-3 py-2">
      <dt className="inline-flex min-w-0 items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-tertiary)]">
        <span className={decisionCockpitIconClass(tone)} aria-hidden="true">
          {icon}
        </span>
        <span className="truncate">{label}</span>
      </dt>
      <dd className="mt-1 min-w-0">
        <p
          className={cn(
            "line-clamp-2 min-w-0 text-xs font-semibold leading-5 text-[var(--text-primary)]",
            tone === "danger" && "text-error",
            tone === "warning" && "text-warning",
            tone === "success" && "text-success",
          )}
          title={value}
        >
          {value}
        </p>
        {detail ? (
          <p
            className="mt-0.5 line-clamp-2 min-w-0 text-xs leading-4 text-[var(--text-secondary)]"
            title={detail}
          >
            {detail}
          </p>
        ) : null}
      </dd>
    </div>
  );
}

function decisionCockpitIconClass(tone?: ReadinessTone): string {
  const base =
    "flex h-7 w-7 shrink-0 items-center justify-center rounded-md border";
  if (tone === "danger")
    return `${base} border-error/25 bg-error/10 text-error`;
  if (tone === "warning")
    return `${base} border-warning/25 bg-warning/10 text-warning`;
  if (tone === "success")
    return `${base} border-success/25 bg-success/10 text-success`;
  return `${base} border-brand-primary/15 bg-brand-primary/8 text-brand-primary`;
}

function getDecisionPacketSnapshotItems({
  evidenceItems,
  evidenceQuality,
  readinessModel,
  report,
  riskLabel,
}: {
  evidenceItems: ReportEvidenceFactItem[];
  evidenceQuality: {
    label: string;
    tone: ReportEvidenceFactItem["tone"];
  };
  readinessModel: RelianceReadinessModel;
  report: FTOReport;
  riskLabel: string;
}): DecisionPacketSnapshotItem[] {
  const verdict = evidenceItems.find(
    (item) => item.label === "Screening verdict",
  );
  const coverage = evidenceItems.find(
    (item) => item.label === "Evidence coverage",
  );
  const sourceAudit = evidenceItems.find(
    (item) => item.label === "Source audit",
  );
  const blockerCounts = getCanonicalBlockerCounts(report);
  const triagedCount =
    typeof report.patents_after_triage === "number"
      ? report.patents_after_triage
      : null;
  const foundCount =
    typeof report.total_patents_found === "number"
      ? report.total_patents_found
      : null;

  return [
    {
      icon: <ShieldAlert className="h-3.5 w-3.5" />,
      label: "Risk posture",
      value: riskLabel,
      detail:
        blockerCounts.familyCount > 0
          ? `${blockerCounts.familyCount.toLocaleString()} famil${
              blockerCounts.familyCount === 1 ? "y" : "ies"
            } containing blocking national claims; ${blockerCounts.referenceCount.toLocaleString()} canonical patent or publication reference${
              blockerCounts.referenceCount === 1 ? "" : "s"
            }.`
          : "No canonical blocker-family record reported.",
      tone: normalizeReadinessTone(verdict?.tone),
    },
    {
      icon: <FileCheck2 className="h-3.5 w-3.5" />,
      label: "Evidence basis",
      value: compactEvidenceQualityLabel(evidenceQuality.label),
      detail:
        triagedCount !== null && foundCount !== null
          ? `${triagedCount.toLocaleString()} / ${foundCount.toLocaleString()} patents.`
          : (coverage?.detail ??
            "Evidence coverage travels with the decision packet."),
      tone: normalizeReadinessTone(evidenceQuality.tone),
    },
    {
      icon: <UserCheck className="h-3.5 w-3.5" />,
      label: "Review state",
      value: compactReadinessStatusLabel(readinessModel.statusLabel),
      detail: compactLifecycleBlocker(readinessModel.lifecycleState.blocker),
      tone: readinessModel.statusTone,
    },
    {
      icon: <DatabaseZap className="h-3.5 w-3.5" />,
      label: "Source scope",
      value: sourceAudit?.value ?? "Source audit",
      detail:
        compactSourceAuditDetail(sourceAudit?.detail) ??
        "Source coverage and provenance remain visible for review.",
      tone: normalizeReadinessTone(sourceAudit?.tone),
    },
  ];
}

function compactSourceAuditDetail(detail?: string): string | undefined {
  if (!detail) return undefined;
  if (/failed/i.test(detail)) return "1 source failed.";
  if (/disclosed/i.test(detail)) return "Disclosed for review.";
  return detail;
}

function compactLifecycleBlocker(value: string): string {
  if (/US lane blocks export/i.test(value)) return "US export blocked.";
  if (/review/i.test(value)) return "Review gate open.";
  return value;
}

function compactEvidenceQualityLabel(label: string): string {
  const percentMatch = label.match(/^(\d+)%/);
  if (percentMatch) return `${percentMatch[0]} score`;
  return label;
}

function compactReadinessStatusLabel(label: string): string {
  if (/not ready/i.test(label)) return "Not ready";
  if (/counsel review/i.test(label)) return "Counsel review";
  return label;
}

function compactDecisionMemoAction(value: string): string {
  if (/resolve the blocker, then rerun export readiness checks/i.test(value)) {
    return "Resolve blocker; rerun readiness checks.";
  }
  if (/assign counsel review and close material findings/i.test(value)) {
    return "Assign counsel review; close material findings.";
  }
  return value;
}

function normalizeReadinessTone(
  tone: ReportEvidenceFactItem["tone"],
): ReadinessTone {
  if (tone === "danger" || tone === "warning" || tone === "success") {
    return tone;
  }
  return "neutral";
}

function getExecutionProfileLabel(profile: string | undefined): string | null {
  if (!profile) {
    return "Execution profile not reported";
  }

  if (profile === "world_class_adaptive") {
    return "Adaptive pipeline";
  }

  if (profile === "agentic" || profile === "adaptive_agentic") {
    return "Agentic pipeline";
  }

  return "Execution profile not reported";
}
