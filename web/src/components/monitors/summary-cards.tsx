"use client";

import {
  Activity,
  BellDot,
  CircleCheck,
  Globe2,
  ShieldAlert,
  Scale,
  type LucideIcon,
} from "lucide-react";
import { AnimatedCounter } from "@/components/shared/animated-counter";
import {
  StaggerContainer,
  StaggerItem,
} from "@/components/shared/stagger-container";
import type { MonitorResponse } from "@/hooks/use-monitors";
import {
  formatMonitorDateTime,
  getMonitorPosture,
  getMonitorWorkspaceReadiness,
} from "@/components/monitors/helpers";

interface MonitorSummaryCardsProps {
  monitors: MonitorResponse[];
}

export function MonitorSummaryCards({ monitors }: MonitorSummaryCardsProps) {
  const postures = monitors.map((monitor) => getMonitorPosture(monitor));
  const readiness = getMonitorWorkspaceReadiness(monitors);
  const needsAttention = postures.filter(
    (posture) => posture.needsAttention,
  ).length;
  const healthyWatches = postures.filter(
    (posture) => posture.label === "Healthy",
  ).length;
  const trackedPatents = monitors.reduce(
    (sum, monitor) => sum + monitor.last_patent_count,
    0,
  );
  const jurisdictions = new Set(
    monitors.flatMap((monitor) => monitor.target_jurisdictions),
  ).size;

  return (
    <div
      className="space-y-3"
      role="group"
      aria-label="Patent monitoring posture summary"
    >
      <MonitorReadinessStrip readiness={readiness} />
      <StaggerContainer className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StaggerItem>
          <MonitorSummaryMetric
            icon={ShieldAlert}
            label="Visible attention"
            value={needsAttention}
            detail="Attention states on this page"
            tone={needsAttention > 0 ? "warning" : "neutral"}
          />
        </StaggerItem>
        <StaggerItem>
          <MonitorSummaryMetric
            icon={CircleCheck}
            label="Visible healthy"
            value={healthyWatches}
            detail="On-schedule watches on this page"
            tone="success"
          />
        </StaggerItem>
        <StaggerItem>
          <MonitorSummaryMetric
            icon={BellDot}
            label="Visible patents"
            value={trackedPatents}
            detail="Patent records under visible watches"
          />
        </StaggerItem>
        <StaggerItem>
          <MonitorSummaryMetric
            icon={Globe2}
            label="Visible scope"
            value={jurisdictions}
            detail="Unique jurisdictions on this page"
          />
        </StaggerItem>
      </StaggerContainer>
    </div>
  );
}

function MonitorReadinessStrip({
  readiness,
}: {
  readiness: ReturnType<typeof getMonitorWorkspaceReadiness>;
}) {
  const latestRun = formatMonitorDateTime(readiness.latestCompletedRunAt);

  return (
    <div className="praviar-surface-premium rounded-lg border border-[var(--card-border)] p-3 sm:p-4">
      <div className="grid gap-3 md:grid-cols-[1.15fr_repeat(3,minmax(0,1fr))]">
        <ReadinessItem
          icon={Scale}
          label="No clearance inferred"
          value="Scope watch"
          detail="Monitoring surfaces changes for review; it is not a legal clearance opinion."
          tone="warning"
        />
        <ReadinessItem
          icon={Activity}
          label="Visible fresh watches"
          value={readiness.freshActiveWatches.toLocaleString()}
          detail={`${readiness.activeWatches.toLocaleString()} active, ${readiness.pausedWatches.toLocaleString()} paused on this page`}
          tone={readiness.needsAttention > 0 ? "neutral" : "success"}
        />
        <ReadinessItem
          icon={ShieldAlert}
          label="Visible attention queue"
          value={readiness.needsAttention.toLocaleString()}
          detail={`${readiness.staleConclusions.toLocaleString()} stale conclusions · ${readiness.firstRunPending.toLocaleString()} first runs pending on this page`}
          tone={readiness.needsAttention > 0 ? "warning" : "success"}
        />
        <ReadinessItem
          icon={Globe2}
          label="Visible scope coverage"
          value={readiness.jurisdictionCount.toLocaleString()}
          detail={`${readiness.trackedPatents.toLocaleString()} tracked patents on this page · latest visible ready run ${latestRun}`}
        />
      </div>
    </div>
  );
}

function ReadinessItem({
  icon: Icon,
  label,
  value,
  detail,
  tone = "neutral",
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  detail: string;
  tone?: "neutral" | "warning" | "success";
}) {
  const iconClass =
    tone === "warning"
      ? "border-warning/25 bg-warning/10 text-warning"
      : tone === "success"
        ? "border-success/25 bg-success/10 text-success"
        : "border-brand-primary/20 bg-brand-primary/10 text-[var(--brand-primary)]";

  return (
    <div className="flex min-w-0 gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 p-3">
      <span
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md border ${iconClass}`}
      >
        <Icon className="h-4 w-4" aria-hidden="true" />
      </span>
      <span className="min-w-0">
        <span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
          {label}
        </span>
        <span className="mt-1 block break-words text-sm font-semibold leading-tight text-[var(--text-primary)] [overflow-wrap:anywhere]">
          {value}
        </span>
        <span className="mt-1 block text-xs leading-5 text-[var(--text-secondary)]">
          {detail}
        </span>
      </span>
    </div>
  );
}

function MonitorSummaryMetric({
  icon: Icon,
  label,
  value,
  detail,
  tone = "neutral",
}: {
  icon: LucideIcon;
  label: string;
  value: number;
  detail: string;
  tone?: "neutral" | "warning" | "success";
}) {
  const iconClass =
    tone === "warning"
      ? "border-warning/25 bg-warning/10 text-warning"
      : tone === "success"
        ? "border-success/25 bg-success/10 text-success"
        : "border-brand-primary/20 bg-brand-primary/10 text-[var(--brand-primary)]";

  return (
    <div className="praviar-surface-premium flex min-w-0 items-start gap-3 rounded-lg border border-[var(--card-border)] p-4">
      <span
        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-md border ${iconClass}`}
      >
        <Icon className="h-4 w-4" aria-hidden="true" />
      </span>
      <span className="min-w-0">
        <span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
          {label}
        </span>
        <span className="mt-1 block text-xl font-semibold leading-tight tabular-nums text-[var(--text-primary)]">
          <AnimatedCounter value={value} />
        </span>
        <span className="mt-1 block text-xs leading-5 text-[var(--text-secondary)]">
          {detail}
        </span>
      </span>
    </div>
  );
}
