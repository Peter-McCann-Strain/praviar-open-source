import type { MonitorResponse } from "@/hooks/use-monitors";

export const SCHEDULE_OPTIONS = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
] as const;

export type MonitorSchedule = (typeof SCHEDULE_OPTIONS)[number]["value"];

const UTC_DATE_TIME_FORMATTER = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
  timeZoneName: "short",
});

const UTC_DATE_FORMATTER = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});

const STALE_THRESHOLD_DAYS_BY_SCHEDULE: Record<MonitorSchedule, number> = {
  daily: 3,
  weekly: 14,
  monthly: 45,
};

export type MonitorPostureTone =
  | "healthy"
  | "warning"
  | "error"
  | "running"
  | "paused";

export interface MonitorPosture {
  label: string;
  detail: string;
  tone: MonitorPostureTone;
  needsAttention: boolean;
}

export interface MonitorWorkspaceReadiness {
  activeWatches: number;
  pausedWatches: number;
  needsAttention: number;
  freshActiveWatches: number;
  firstRunPending: number;
  trackedPatents: number;
  jurisdictionCount: number;
  latestCompletedRunAt: string | null;
  staleConclusions: number;
}

export function relativeTime(date: string): string {
  const timestamp = new Date(date).getTime();
  if (Number.isNaN(timestamp)) {
    return "Unknown";
  }

  const diff = Date.now() - timestamp;
  if (diff < 0) {
    return "Scheduled";
  }

  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function formatMonitorDateTime(date: string | null): string {
  if (!date) return "Never";
  const parsedDate = new Date(date);
  if (Number.isNaN(parsedDate.getTime())) return "Unknown";
  return UTC_DATE_TIME_FORMATTER.format(parsedDate);
}

export function formatMonitorDate(date: string | null): string {
  if (!date) return "Never";
  const parsedDate = new Date(date);
  if (Number.isNaN(parsedDate.getTime())) return "Unknown";
  return UTC_DATE_FORMATTER.format(parsedDate);
}

export function formatScheduleLabel(schedule: string): string {
  return (
    SCHEDULE_OPTIONS.find((option) => option.value === schedule)?.label ??
    titleCase(schedule)
  );
}

export function normalizeMonitorSchedule(
  schedule: string | null | undefined,
): MonitorSchedule {
  if (schedule === "daily" || schedule === "monthly") return schedule;
  return "weekly";
}

export function formatRunMode(mode: MonitorResponse["last_run_mode"]): string {
  if (mode === "bootstrap") return "Baseline run";
  if (mode === "diff_only") return "Diff watch";
  if (mode === "targeted_refresh") return "Targeted refresh";
  if (mode === "full_refresh") return "Full refresh";
  return "First run pending";
}

export function formatMonitorStrategyMode(mode: string): string {
  if (mode === "diff_only" || mode === "full_refresh" || mode === "pending") {
    return formatRunMode(mode);
  }
  return titleCase(mode);
}

export function formatJurisdictionDeltas(
  deltas: Record<string, unknown> | undefined,
): string | null {
  if (!deltas || Object.keys(deltas).length === 0) return null;

  const formatted = Object.entries(deltas)
    .map(([jurisdiction, value]) => {
      if (typeof value === "number") {
        return `${jurisdiction.toUpperCase()} ${value >= 0 ? "+" : ""}${value}`;
      }
      if (typeof value === "string" && value.trim()) {
        return `${jurisdiction.toUpperCase()} ${value.trim()}`;
      }
      if (
        value &&
        typeof value === "object" &&
        "count" in value &&
        typeof value.count === "number"
      ) {
        return `${jurisdiction.toUpperCase()} ${value.count >= 0 ? "+" : ""}${value.count}`;
      }
      return `${jurisdiction.toUpperCase()} updated`;
    })
    .filter(Boolean);

  return formatted.length > 0 ? formatted.join(" · ") : null;
}

export function getMonitorPosture(monitor: MonitorResponse): MonitorPosture {
  const staleConclusionCount = Math.max(
    monitor.stale_conclusion_count,
    monitor.stale_conclusions.length,
  );
  if (
    monitor.conclusion_status === "review_required" ||
    monitor.last_run_status === "review_required"
  ) {
    return {
      label: "Attorney review required",
      detail:
        staleConclusionCount > 0
          ? `${staleConclusionCount.toLocaleString()} prior conclusion${
              staleConclusionCount === 1 ? "" : "s"
            } no longer current`
          : "Prior report conclusions are no longer current",
      tone: "warning",
      needsAttention: true,
    };
  }

  if (!monitor.is_active) {
    return {
      label: "Paused",
      detail: "Watch is not checking for new patent events",
      tone: "paused",
      needsAttention: false,
    };
  }

  if (monitor.last_run_status === "error") {
    return {
      label: "Needs attention",
      detail: "Last monitoring run did not complete",
      tone: "error",
      needsAttention: true,
    };
  }

  if (monitor.last_run_status === "running") {
    return {
      label: "Running",
      detail: "Monitoring run is in progress",
      tone: "running",
      needsAttention: true,
    };
  }

  if (monitor.last_run_status === "pending" || !monitor.last_run_at) {
    return {
      label: "First run pending",
      detail: "No completed monitoring run yet",
      tone: "warning",
      needsAttention: true,
    };
  }

  const timestamp = new Date(monitor.last_run_at).getTime();
  if (Number.isNaN(timestamp)) {
    return {
      label: "Needs attention",
      detail: "Last run timestamp is unavailable",
      tone: "error",
      needsAttention: true,
    };
  }

  const staleThresholdDays =
    STALE_THRESHOLD_DAYS_BY_SCHEDULE[
      normalizeMonitorSchedule(monitor.schedule)
    ];
  const ageDays = Math.floor((Date.now() - timestamp) / 86_400_000);
  if (ageDays > staleThresholdDays) {
    return {
      label: "Stale",
      detail: `No completed run in ${ageDays.toLocaleString()} days`,
      tone: "warning",
      needsAttention: true,
    };
  }

  if (
    monitor.conclusion_status === "reassessed" ||
    monitor.last_run_status === "reassessed"
  ) {
    return {
      label: "Counsel reassessed",
      detail: "Every affected conclusion has an attorney-attested disposition",
      tone: "healthy",
      needsAttention: false,
    };
  }

  return {
    label: "Healthy",
    detail: "Latest monitoring run completed on schedule",
    tone: "healthy",
    needsAttention: false,
  };
}

export function getMonitorWorkspaceReadiness(
  monitors: MonitorResponse[],
): MonitorWorkspaceReadiness {
  const postures = monitors.map((monitor) => ({
    monitor,
    posture: getMonitorPosture(monitor),
  }));
  const activeWatches = monitors.filter((monitor) => monitor.is_active).length;
  const pausedWatches = monitors.length - activeWatches;
  const needsAttention = postures.filter(
    ({ posture }) => posture.needsAttention,
  ).length;
  const freshActiveWatches = postures.filter(
    ({ monitor, posture }) => monitor.is_active && posture.label === "Healthy",
  ).length;
  const firstRunPending = monitors.filter(
    (monitor) =>
      monitor.is_active &&
      (monitor.last_run_status === "pending" || !monitor.last_run_at),
  ).length;
  const trackedPatents = monitors.reduce(
    (sum, monitor) => sum + monitor.last_patent_count,
    0,
  );
  const jurisdictionCount = new Set(
    monitors.flatMap((monitor) => monitor.target_jurisdictions.filter(Boolean)),
  ).size;
  const latestCompletedRunAt = monitors.reduce<string | null>(
    (latest, monitor) => {
      if (
        !monitor.last_run_at ||
        !["ok", "ready", "review_required", "reassessed"].includes(
          monitor.last_run_status,
        )
      ) {
        return latest;
      }
      if (!latest) {
        return monitor.last_run_at;
      }
      return new Date(monitor.last_run_at).getTime() >
        new Date(latest).getTime()
        ? monitor.last_run_at
        : latest;
    },
    null,
  );
  const staleConclusions = monitors.reduce(
    (sum, monitor) =>
      sum +
      Math.max(
        monitor.stale_conclusion_count,
        monitor.stale_conclusions.length,
      ),
    0,
  );

  return {
    activeWatches,
    pausedWatches,
    needsAttention,
    freshActiveWatches,
    firstRunPending,
    trackedPatents,
    jurisdictionCount,
    latestCompletedRunAt,
    staleConclusions,
  };
}

export function titleCase(value: string): string {
  return value
    .replace(/[_-]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
