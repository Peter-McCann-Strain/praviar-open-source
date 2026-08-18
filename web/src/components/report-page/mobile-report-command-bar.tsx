"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ComponentType,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";
import {
  ChevronRight,
  Download,
  LockKeyhole,
  MessageSquareText,
  MoreHorizontal,
  Printer,
  Radar,
  Search,
  Share2,
  X,
  type LucideProps,
} from "lucide-react";
import { PraviarMarkFrame } from "@/components/brand/praviar-mark-frame";
import { Button } from "@/components/ui/button";
import { FlagButton } from "@/components/collaboration/flag-button";
import { ReviewerDecisionButton } from "@/components/report/reviewer-decision-button";
import { WatchToggle } from "@/components/report/watch-toggle";
import { ReportWatchRecoveryNotice } from "@/components/report-page/report-watch-recovery-notice";
import {
  formatReportRiskLabel,
  getReportReference,
} from "@/components/report-page/report-command-summary";
import {
  getRelianceExportAction,
  getRelianceLifecycleState,
  getReviewerDecisionExportBlockers,
  type RelianceLifecycleInput,
  type RelianceLifecycleState,
  type RelianceReadinessInput,
} from "@/components/report-page/report-reliance-readiness";
import { useSharedReportWatchControl } from "@/components/report-page/use-report-watch-control";
import { formatRelativeTime } from "@/components/report/share-analytics-helpers";
import { motionAwareScrollBehavior } from "@/lib/motion-preferences";
import { cn } from "@/lib/utils";
import { canManageReportCollaboration } from "@/lib/report-permissions";
import type { AnalysisReviewStatusResponse } from "@/hooks/use-analysis-review-status";
import type { ReportWorkspaceSummaryResponse } from "@/hooks/use-report-workspace-summary";
import type { ReviewerDecisionListResponse } from "@/hooks/use-reviewer-decisions";
import type { FTOReport } from "@praviar/shared-types";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");
const MOBILE_COMMAND_GEOMETRY =
  "[--praviar-mobile-command-rail-height:3.625rem] [--praviar-mobile-command-rail-top:6.25rem] sm:[--praviar-mobile-command-rail-top:6.75rem]";
const MOBILE_COMMAND_SURFACE_OFFSET =
  "top-[calc(var(--praviar-mobile-command-rail-top)+var(--praviar-mobile-command-rail-height)+0.5rem)] max-h-[calc(100dvh_-_var(--praviar-mobile-command-rail-top)_-_var(--praviar-mobile-command-rail-height)_-_1.25rem_-_env(safe-area-inset-bottom))]";

interface MobileReportCommandBarProps {
  analysisId: string;
  token: string | null;
  report: FTOReport;
  chatOpen: boolean;
  onAsk: () => void;
  onSearch: () => void;
  onExport: () => void;
  onShare: () => void;
  onMonitorPlan?: () => void;
  onFeedback: () => void;
  onRequestCounsel?: () => void;
  onReviewOpen?: () => void;
  reviewerDecisions?: ReviewerDecisionListResponse | null;
  reviewerDecisionsLoading?: boolean;
  reviewStatus?: AnalysisReviewStatusResponse;
  reviewStatusLoading?: boolean;
  workspaceSummary?: ReportWorkspaceSummaryResponse;
  workspaceSummaryLoading?: boolean;
  shareActive?: boolean;
  shareRecipientBound?: boolean;
  shareLastViewedAt?: string | null;
  shareViewCount?: number | null;
  askButtonRef: RefObject<HTMLButtonElement | null>;
  currentUserRole?: string | null;
  canExportReport?: boolean;
}

interface SheetActionProps {
  ariaLabel?: string;
  detail?: string;
  icon: ComponentType<LucideProps>;
  label: string;
  onClick: () => void;
  tone?: "default" | "warning" | "danger";
}

function SheetAction({
  ariaLabel,
  detail,
  icon: Icon,
  label,
  onClick,
  tone = "default",
}: SheetActionProps) {
  const detailId = useId();

  return (
    <Button
      type="button"
      variant="ghost"
      className={cn(
        "h-auto min-h-11 min-w-0 max-w-full w-full justify-start gap-2.5 whitespace-normal rounded-md border border-transparent px-2.5 py-2 text-sm hover:border-[var(--border-subtle)] hover:bg-[var(--surface-hover)]",
        tone === "danger" &&
          "border-error/25 bg-error/8 text-error hover:border-error/35 hover:bg-error/12 hover:text-error",
        tone === "warning" &&
          "border-warning/25 bg-warning/8 text-warning hover:border-warning/35 hover:bg-warning/12 hover:text-warning",
      )}
      onClick={onClick}
      aria-label={ariaLabel}
      aria-describedby={detail ? detailId : undefined}
    >
      <span
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] text-[var(--brand-primary)]"
        aria-hidden="true"
      >
        <Icon className="h-3.5 w-3.5" />
      </span>
      <span className="min-w-0 flex-1 text-left">
        <span className="block break-words leading-5 [overflow-wrap:anywhere]">
          {label}
        </span>
        {detail ? (
          <span
            id={detailId}
            className="mt-0.5 block break-words text-xs font-medium leading-4 opacity-80 [overflow-wrap:anywhere]"
          >
            {detail}
          </span>
        ) : null}
      </span>
      <ChevronRight
        className="h-4 w-4 shrink-0 text-[var(--text-disabled)]"
        aria-hidden="true"
      />
    </Button>
  );
}

function SheetSection({
  children,
  label,
}: {
  children: ReactNode;
  label: string;
}) {
  const labelId = useId();

  return (
    <section aria-labelledby={labelId} className="grid min-w-0 gap-1.5">
      <h3
        id={labelId}
        className="min-w-0 px-1 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--brand-primary)]"
      >
        {label}
      </h3>
      <div className="grid min-w-0 gap-1 rounded-lg border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-surface)_86%,transparent)] p-1">
        {children}
      </div>
    </section>
  );
}

export function MobileReportCommandBar(props: MobileReportCommandBarProps) {
  if (props.chatOpen) {
    return null;
  }

  return <MobileReportCommandBarSurface {...props} />;
}

function MobileReportCommandBarSurface({
  analysisId,
  token,
  report,
  chatOpen,
  onAsk,
  onSearch,
  onExport,
  onShare,
  onMonitorPlan,
  onFeedback,
  onRequestCounsel,
  onReviewOpen,
  reviewerDecisions,
  reviewerDecisionsLoading,
  reviewStatus,
  reviewStatusLoading,
  workspaceSummary,
  workspaceSummaryLoading,
  shareActive,
  shareRecipientBound,
  shareLastViewedAt,
  shareViewCount,
  askButtonRef,
  currentUserRole,
  canExportReport,
}: MobileReportCommandBarProps) {
  const canManageCollaboration = canManageReportCollaboration(currentUserRole);
  const canExport = canExportReport ?? canManageCollaboration;
  const [actionsOpen, setActionsOpen] = useState(false);
  const actionsButtonRef = useRef<HTMLButtonElement>(null);
  const sheetRef = useRef<HTMLDivElement>(null);
  const {
    watchControlsLocked = false,
    watchEnabled,
    watchPending,
    watchRecovery,
    watchSchedule,
    handleWatchRecoveryAction,
    handleWatchToggle,
  } = useSharedReportWatchControl();
  const reportReference = getReportReference(report);
  const riskLabel = formatReportRiskLabel(report.risk_summary.overall_risk);
  const shareStatus = shareActive
    ? getMobileShareStatus(shareViewCount ?? 0, shareLastViewedAt)
    : null;
  const compoundName = report.compound?.name ?? "Report workspace";
  const visibleActionsOpen = actionsOpen && !chatOpen;
  const reviewerDecisionBlockers = getReviewerDecisionExportBlockers({
    report,
    reviewStatus,
    reviewerDecisions,
    reviewerDecisionsLoading,
  });
  const exportAction = getMobileExportAction({
    additionalBlockers: reviewerDecisionBlockers,
    report,
    reviewStatus,
    reviewStatusLoading,
    workspaceSummary,
    workspaceSummaryLoading,
  });
  const exportOpensDialog = exportAction.opensExportDialog;
  const lifecycleState = getMobileLifecycleState({
    additionalBlockers: reviewerDecisionBlockers,
    report,
    shareActive,
    shareRecipientBound,
    reviewStatus,
    reviewStatusLoading,
    workspaceSummary,
    workspaceSummaryLoading,
  });
  const lifecycleToneClass = getMobileLifecycleToneClass(lifecycleState.tone);
  const compactNextAction = getCompactNextAction(lifecycleState.nextAction);

  const closeActions = useCallback(() => {
    setActionsOpen(false);
    requestAnimationFrame(() => actionsButtonRef.current?.focus());
  }, []);

  const runSheetAction = useCallback(
    (action: () => void, options: { restoreFocus?: boolean } = {}) => {
      setActionsOpen(false);
      action();
      if (options.restoreFocus ?? true) {
        requestAnimationFrame(() => actionsButtonRef.current?.focus());
      }
    },
    [],
  );
  const focusRelianceReadiness = useCallback(() => {
    const target = document.getElementById("report-reliance-readiness");
    const disclosure = target?.closest("details");
    if (disclosure) {
      disclosure.open = true;
    }
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
  }, []);
  const handleExportAction = () => {
    if (exportOpensDialog) {
      onExport();
      return;
    }

    focusRelianceReadiness();
  };

  useEffect(() => {
    if (!visibleActionsOpen) return;
    const first =
      sheetRef.current?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
    requestAnimationFrame(() => first?.focus());
  }, [visibleActionsOpen]);

  const handleSheetKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      closeActions();
      return;
    }
    if (event.key !== "Tab" || !sheetRef.current) return;

    const focusable = Array.from(
      sheetRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
    ).filter((el) => el.getAttribute("aria-hidden") !== "true");
    if (focusable.length === 0) {
      event.preventDefault();
      sheetRef.current.focus();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || active === sheetRef.current)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <>
      {visibleActionsOpen ? (
        <div
          className="praviar-overlay-scrim-soft no-print fixed inset-0 z-40 cursor-default lg:hidden"
          aria-hidden="true"
          onClick={closeActions}
        />
      ) : null}

      {visibleActionsOpen ? (
        <div
          ref={sheetRef}
          id="mobile-report-actions"
          role="dialog"
          aria-modal="true"
          aria-labelledby="mobile-report-actions-title"
          tabIndex={-1}
          onKeyDown={handleSheetKeyDown}
          className={cn(
            "praviar-dialog-panel no-print fixed inset-x-3 z-50 max-w-[calc(100vw-1.5rem)] overflow-x-hidden overflow-y-auto overscroll-contain rounded-lg p-3 shadow-[var(--shadow-lg)] focus:outline-none lg:hidden",
            MOBILE_COMMAND_GEOMETRY,
            MOBILE_COMMAND_SURFACE_OFFSET,
          )}
        >
          <div
            className="mx-auto mb-3 h-1 w-12 rounded-full bg-[var(--border-emphasis)]"
            aria-hidden="true"
          />
          <div className="mb-2 flex items-center justify-between gap-3 px-1">
            <div className="flex min-w-0 items-center gap-2.5">
              <PraviarMarkFrame size="xs" />
              <h2
                id="mobile-report-actions-title"
                className="text-base font-semibold text-[var(--text-primary)]"
              >
                Report actions
              </h2>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-12 w-12 rounded-lg"
              onClick={closeActions}
              aria-label="Close report actions"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>

          <div
            role="group"
            className="mb-3 rounded-lg border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-surface)_82%,transparent)] px-3 py-2 shadow-[var(--shadow-xs)]"
            aria-label={`Current report ${reportReference}, ${riskLabel}. Owner ${lifecycleState.owner}. Next action ${lifecycleState.nextAction}`}
            data-praviar-mobile-command-summary
          >
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <span
                className="min-w-0 max-w-full break-all font-mono text-xs font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]"
                title={reportReference}
              >
                {reportReference}
              </span>
              <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-2 py-0.5 text-xs font-semibold uppercase text-[var(--text-secondary)]">
                {riskLabel}
              </span>
              {shareStatus ? (
                <span className="rounded-full border border-info/20 bg-info/10 px-2 py-0.5 text-xs font-semibold text-info">
                  {shareStatus.visible}
                </span>
              ) : null}
            </div>
            <p className="mt-1 break-words text-xs font-semibold leading-5 text-[var(--text-primary)] [overflow-wrap:anywhere]">
              {compoundName}
            </p>
            <p
              className={cn(
                "mt-1.5 break-words rounded-md bg-[var(--surface-muted)] px-2.5 py-1.5 text-xs font-semibold leading-4 [overflow-wrap:anywhere]",
                lifecycleToneClass,
              )}
              data-praviar-mobile-lifecycle-context
              title={`Owner: ${lifecycleState.owner}. Next action: ${lifecycleState.nextAction}`}
            >
              Owner: {lifecycleState.owner} · Next: {compactNextAction}
            </p>
          </div>

          <div className="grid min-w-0 gap-3">
            <SheetSection label="Evidence & readiness">
              <SheetAction
                ariaLabel="Search reviewed evidence"
                detail="Claims, citations, and reviewer notes"
                icon={Search}
                label="Search reviewed evidence"
                onClick={() =>
                  runSheetAction(onSearch, { restoreFocus: false })
                }
              />
              {canExport ? (
                <SheetAction
                  ariaLabel={exportAction.ariaLabel}
                  detail={exportAction.detail}
                  icon={exportAction.icon}
                  label={exportAction.label}
                  onClick={() =>
                    runSheetAction(handleExportAction, {
                      restoreFocus: false,
                    })
                  }
                  tone={exportAction.tone}
                />
              ) : null}
            </SheetSection>
            <SheetSection label="Collaboration">
              {canManageCollaboration ? (
                <SheetAction
                  icon={Share2}
                  label="Share report"
                  onClick={() =>
                    runSheetAction(onShare, { restoreFocus: false })
                  }
                />
              ) : null}
              {onMonitorPlan ? (
                <SheetAction
                  ariaLabel="Open report-to-monitor plan"
                  detail="Patent families, jurisdictions, and cadence"
                  icon={Radar}
                  label="Monitor plan"
                  onClick={() =>
                    runSheetAction(onMonitorPlan, { restoreFocus: false })
                  }
                />
              ) : null}
              <div className="min-w-0 overflow-hidden px-1 py-1">
                <WatchToggle
                  analysisId={analysisId}
                  enabled={watchEnabled}
                  isPending={watchControlsLocked}
                  schedule={watchSchedule}
                  onToggle={handleWatchToggle}
                  className="flex-wrap"
                />
                {watchRecovery ? (
                  <div className="mt-2">
                    <ReportWatchRecoveryNotice
                      actionPending={watchPending}
                      onAction={() => {
                        void handleWatchRecoveryAction();
                      }}
                      recovery={watchRecovery}
                      surface="mobile"
                    />
                  </div>
                ) : null}
              </div>
            </SheetSection>
            <SheetSection label="Record">
              <SheetAction
                icon={Printer}
                label="Print current section"
                onClick={() => runSheetAction(() => window.print())}
              />
              <div className="min-w-0 overflow-hidden px-1 py-1">
                <FlagButton
                  analysisId={analysisId}
                  variant="ghost"
                  size="sm"
                  className="min-h-12 min-w-0 max-w-full w-full justify-start rounded-lg px-3"
                />
              </div>
              {canManageCollaboration ? (
                <SheetAction
                  icon={MessageSquareText}
                  label="Submit feedback"
                  onClick={() =>
                    runSheetAction(onFeedback, { restoreFocus: false })
                  }
                />
              ) : null}
            </SheetSection>
          </div>
        </div>
      ) : null}

      {!chatOpen ? (
        <div
          role="toolbar"
          aria-label={`Report command bar for ${reportReference}. ${riskLabel}. Next action ${lifecycleState.nextAction}`}
          className={cn(
            "praviar-mobile-command-surface no-print sticky z-20 rounded-lg px-2 py-1.5 lg:hidden",
            MOBILE_COMMAND_GEOMETRY,
            "top-[var(--praviar-mobile-command-rail-top)]",
          )}
          data-praviar-mobile-command-bar
        >
          <div className="mx-auto max-w-lg">
            {shareStatus ? (
              <span
                aria-label="External share status"
                className="sr-only"
                role="status"
              >
                {shareStatus.full}
              </span>
            ) : null}
            <div
              className="grid grid-cols-3 gap-1.5"
              data-praviar-mobile-primary-actions
            >
              {canManageCollaboration ? (
                <ReviewerDecisionButton
                  analysisId={analysisId}
                  token={token}
                  report={report}
                  label="Review"
                  ariaLabel="Review findings"
                  variant="default"
                  className="h-11 min-w-0 flex-col gap-0.5 rounded-lg px-1.5 text-xs"
                  testId="mobile-reviewer-decision-button"
                  onBeforeOpen={onReviewOpen}
                  reviewStatus={reviewStatus}
                  reviewStatusLoading={reviewStatusLoading}
                />
              ) : (
                <Button
                  type="button"
                  variant="default"
                  className="h-11 min-w-0 flex-col gap-0.5 rounded-lg px-1.5 text-xs"
                  onClick={onRequestCounsel}
                  disabled={!onRequestCounsel}
                  aria-label="Request counsel review"
                >
                  <MessageSquareText className="h-4 w-4" aria-hidden="true" />
                  <span>Counsel</span>
                </Button>
              )}
              <Button
                ref={askButtonRef}
                type="button"
                variant="default"
                className="h-11 min-w-0 flex-col gap-0.5 rounded-lg px-1.5 text-xs"
                onClick={onAsk}
                aria-label="AI-assisted report evidence gap check"
                aria-expanded={chatOpen}
              >
                <MessageSquareText className="h-4 w-4" aria-hidden="true" />
                <span>Gap check</span>
              </Button>
              <Button
                ref={actionsButtonRef}
                type="button"
                variant="ghost"
                className="h-11 min-w-0 flex-col gap-0.5 rounded-lg px-1.5 text-xs"
                onClick={() => setActionsOpen((open) => !open)}
                aria-label="More report actions"
                aria-expanded={visibleActionsOpen}
                aria-controls={
                  visibleActionsOpen ? "mobile-report-actions" : undefined
                }
                data-praviar-mobile-actions-trigger
              >
                <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
                <span>Actions</span>
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}

function formatShareViewCount(value: number): string {
  return `${value.toLocaleString()} ${value === 1 ? "view" : "views"}`;
}

function getMobileExportAction(
  readinessInput: RelianceReadinessInput & { report: FTOReport },
): {
  ariaLabel: string;
  detail?: string;
  icon: ComponentType<LucideProps>;
  label: string;
  opensExportDialog: boolean;
  tone: SheetActionProps["tone"];
} {
  const action = getRelianceExportAction(readinessInput);

  if (action.tone === "blocked") {
    return {
      ariaLabel: action.ariaLabel,
      detail: action.detail,
      icon: LockKeyhole,
      label: action.label,
      opensExportDialog: false,
      tone: "danger",
    };
  }

  if (action.tone === "verify") {
    return {
      ariaLabel: action.ariaLabel,
      detail: action.detail,
      icon: LockKeyhole,
      label: action.label,
      opensExportDialog: false,
      tone: "warning",
    };
  }

  if (action.tone === "caveat") {
    return {
      ariaLabel: action.ariaLabel,
      detail: action.detail ?? "Source caveat remains attached",
      icon: Download,
      label: action.label,
      opensExportDialog: true,
      tone: "warning",
    };
  }

  return {
    ariaLabel: action.ariaLabel,
    detail: action.detail,
    icon: Download,
    label: action.label,
    opensExportDialog: true,
    tone: "default",
  };
}

function getMobileLifecycleState(
  input: RelianceLifecycleInput & { report: FTOReport },
): RelianceLifecycleState {
  return getRelianceLifecycleState(input);
}

function getMobileLifecycleToneClass(tone: RelianceLifecycleState["tone"]) {
  switch (tone) {
    case "danger":
      return "text-error";
    case "success":
      return "text-success";
    case "warning":
      return "text-warning";
    default:
      return "text-[var(--text-secondary)]";
  }
}

function getMobileShareStatus(
  shareViewCount: number,
  shareLastViewedAt: string | null | undefined,
) {
  const viewCount = formatShareViewCount(shareViewCount);
  const lastViewed = shareLastViewedAt
    ? formatRelativeTime(shareLastViewedAt)
    : "never";

  return {
    full: `External share active, ${viewCount}, last viewed ${lastViewed}`,
    visible: `Shared · ${viewCount}`,
  };
}

function getCompactNextAction(nextAction: string): string {
  const normalized = nextAction.trim();
  if (/resolve the blocker/i.test(normalized)) {
    return "Export blocked";
  }
  if (/assign counsel review/i.test(normalized)) {
    return "Assign counsel review";
  }
  if (/rerun export readiness/i.test(normalized)) {
    return "Rerun export readiness";
  }
  return normalized;
}
