"use client";

import { useMemo, useRef } from "react";
import { CalendarClock, FileText, Globe2, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  SCHEDULE_OPTIONS,
  normalizeMonitorSchedule,
  titleCase,
} from "@/components/monitors/helpers";
import { ReportWatchRecoveryNotice } from "@/components/report-page/report-watch-recovery-notice";
import { useSharedReportWatchControl } from "@/components/report-page/use-report-watch-control";
import type { ReportWorkspaceSummaryResponse } from "@/hooks/use-report-workspace-summary";
import type { FTOReport, PatentAnalysis } from "@praviar/shared-types";

interface ReportMonitorPlanDialogProps {
  analysisId: string;
  open: boolean;
  report: FTOReport;
  workspaceSummary?: ReportWorkspaceSummaryResponse;
  onOpenChange: (open: boolean) => void;
}

export function ReportMonitorPlanDialog({
  open,
  report,
  workspaceSummary,
  onOpenChange,
}: ReportMonitorPlanDialogProps) {
  const {
    monitor,
    watchControlsLocked = false,
    watchEnabled,
    watchPending,
    watchRecovery,
    watchSchedule,
    handleWatchRecoveryAction,
    handleWatchToggle,
  } = useSharedReportWatchControl();
  const defaultSchedule = normalizeMonitorSchedule(
    workspaceSummary?.monitor_seed_defaults?.schedule ??
      watchSchedule ??
      "weekly",
  );
  const scheduleSelectRef = useRef<HTMLSelectElement>(null);
  const plan = useMemo(
    () => buildMonitorPlan(report, workspaceSummary),
    [report, workspaceSummary],
  );
  const firstRunStatus = monitor
    ? titleCase(monitor.last_run_status || "pending")
    : "Queued after activation";
  const getSelectedSchedule = () =>
    normalizeMonitorSchedule(
      scheduleSelectRef.current?.value ?? defaultSchedule,
    );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Report-to-monitor plan</DialogTitle>
          <DialogDescription>
            Seed exact report patent IDs, named assignees, and jurisdictions for
            new publication, prosecution, and status events.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <PlanStat
              icon={FileText}
              label="Source report"
              value={plan.sourceReportLabel}
            />
            <PlanStat
              icon={Globe2}
              label="Jurisdictions"
              value={plan.jurisdictionLabel}
            />
            <PlanStat
              icon={CalendarClock}
              label="First run"
              value={firstRunStatus}
            />
          </div>

          <section
            aria-label="Report patent targets"
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 p-3"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
                  Report patent targets
                </p>
                <p className="mt-1 text-sm text-[var(--text-secondary)]">
                  {plan.targetSummary}
                </p>
              </div>
              <span className="shrink-0 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-2.5 py-1 text-xs text-[var(--text-secondary)]">
                {plan.targets.length} of {plan.targetCount} shown
              </span>
            </div>
            <div className="mt-3 grid gap-2">
              {plan.targets.map((target) => (
                <div
                  key={target.patentId}
                  className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 py-2"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-sm font-semibold text-[var(--text-primary)]">
                      {target.patentId}
                    </span>
                    <span className="rounded-full border border-[var(--border-subtle)] px-2 py-0.5 text-xs uppercase text-[var(--text-tertiary)]">
                      {target.riskLabel}
                    </span>
                  </div>
                  {target.detail ? (
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--text-secondary)]">
                      {target.detail}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          </section>

          <div className="grid gap-3 sm:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold uppercase text-[var(--text-tertiary)]">
                Cadence
              </span>
              <select
                key={defaultSchedule}
                ref={scheduleSelectRef}
                defaultValue={defaultSchedule}
                disabled={watchControlsLocked}
                className="praviar-glass-field h-11 w-full rounded-md border border-[var(--border-emphasis)] px-3 text-sm text-[var(--text-secondary)] focus:border-brand-primary/40 focus:outline-none focus:ring-2 focus:ring-brand-primary/50"
              >
                {SCHEDULE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 p-3 text-xs leading-5 text-[var(--text-secondary)]">
              <p className="font-semibold text-[var(--text-primary)]">
                Query budget
              </p>
              <p className="mt-1">
                Prioritizes report patents, named assignees, jurisdictions, and
                prosecution/status events before broad discovery.
              </p>
            </div>
          </div>
        </div>

        {watchRecovery ? (
          <ReportWatchRecoveryNotice
            actionPending={watchPending}
            onAction={() => {
              void handleWatchRecoveryAction();
            }}
            recovery={watchRecovery}
            surface="dialog"
          />
        ) : null}

        <DialogFooter>
          {watchEnabled ? (
            <Button
              type="button"
              variant="outline"
              className="min-h-11"
              disabled={watchControlsLocked}
              onClick={() => handleWatchToggle(false, getSelectedSchedule())}
            >
              Pause monitor
            </Button>
          ) : null}
          <Button
            type="button"
            className="min-h-11"
            disabled={watchControlsLocked}
            loading={watchPending}
            onClick={() => handleWatchToggle(true, getSelectedSchedule())}
          >
            {watchEnabled ? "Update monitor plan" : "Start monitor plan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PlanStat({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 p-3">
      <Icon
        className="h-4 w-4 text-[var(--brand-primary)]"
        aria-hidden="true"
      />
      <p className="mt-2 text-xs font-semibold uppercase text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-1 break-words text-sm font-semibold text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}

function buildMonitorPlan(
  report: FTOReport,
  workspaceSummary?: ReportWorkspaceSummaryResponse,
) {
  const targets = getMonitorTargets(report.patent_analyses ?? []);
  const jurisdictions =
    workspaceSummary?.target_jurisdictions?.filter(Boolean) ??
    getReportJurisdictions(report);
  const sourceTrust =
    workspaceSummary?.monitor_seed_defaults?.source_trust_mode ??
    workspaceSummary?.trust_mode ??
    "report";
  const sourceReportId =
    workspaceSummary?.monitor_seed_defaults?.source_report_id ??
    report.report_id;
  return {
    jurisdictionLabel:
      jurisdictions.length > 0
        ? jurisdictions.slice(0, 4).join(", ")
        : "Report scope",
    sourceReportLabel: `${sourceReportId} / ${titleCase(sourceTrust)}`,
    targetSummary:
      targets.length > 0
        ? "Highest-risk exact publication targets shown; activation seeds every report patent target"
        : "Report-derived compound and assignee search",
    targetCount: Math.max(targets.length, report.patent_analyses?.length ?? 0),
    targets:
      targets.length > 0
        ? targets
        : [
            {
              patentId: report.compound?.name || "Compound watch",
              riskLabel: titleCase(report.risk_summary?.overall_risk ?? "risk"),
              detail:
                "New patent publications and family/status changes tied to this report.",
            },
          ],
  };
}

function getMonitorTargets(patents: PatentAnalysis[]) {
  const rank: Record<string, number> = { high: 0, medium: 1, low: 2, clear: 3 };
  return [...patents]
    .sort(
      (a, b) =>
        (rank[String(a.risk_level).toLowerCase()] ?? 4) -
          (rank[String(b.risk_level).toLowerCase()] ?? 4) ||
        a.patent_id.localeCompare(b.patent_id),
    )
    .slice(0, 4)
    .map((patent) => ({
      patentId: patent.patent_id,
      riskLabel: titleCase(String(patent.risk_level)),
      detail: patent.risk_summary || patent.title || patent.assignee,
    }));
}

function getReportJurisdictions(report: FTOReport) {
  const jurisdictionDecisions = Array.isArray(report.jurisdiction_decisions)
    ? report.jurisdiction_decisions
    : [];
  return Array.from(
    new Set(
      jurisdictionDecisions
        .map((decision) =>
          typeof decision === "object" && decision && "jurisdiction" in decision
            ? String(decision.jurisdiction)
            : "",
        )
        .filter(Boolean),
    ),
  );
}
