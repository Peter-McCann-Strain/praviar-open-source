"use client";

import { MutationRecoveryNotice } from "@/components/shared/mutation-recovery-notice";
import type { MutationRecoveryState } from "@/hooks/use-mutation-recovery";
import type { ReportWatchRecoveryVariables } from "@/components/report-page/use-report-watch-control";

interface ReportWatchRecoveryNoticeProps {
  actionPending: boolean;
  onAction: () => void;
  recovery: MutationRecoveryState<ReportWatchRecoveryVariables>;
  surface: "desktop" | "dialog" | "mobile";
}

export function ReportWatchRecoveryNotice({
  actionPending,
  onAction,
  recovery,
  surface,
}: ReportWatchRecoveryNoticeProps) {
  const copy =
    recovery.variables.kind === "start"
      ? recovery.mode === "outcome-unknown"
        ? {
            actionLabel: "Refresh watch state",
            description:
              "Refresh the monitor state to check whether the watch was created. Praviar will not create a second watch automatically.",
            title: "Watch start outcome unconfirmed",
          }
        : {
            actionLabel: "Revise watch request",
            description:
              "The watch was not started. Clear this notice, then review the cadence and report scope before trying again.",
            title: "Watch was not started",
          }
      : recovery.variables.variables.data.is_active === false
        ? {
            actionLabel: "Retry stop",
            description:
              "Retry the exact paused state before changing this monitor again.",
            title:
              recovery.mode === "outcome-unknown"
                ? "Watch stop outcome unconfirmed"
                : "Watch was not stopped",
          }
        : {
            actionLabel: "Retry watch settings",
            description:
              "Retry the exact cadence and active state before changing this monitor again.",
            title:
              recovery.mode === "outcome-unknown"
                ? "Watch update outcome unconfirmed"
                : "Watch settings were not updated",
          };

  return (
    <MutationRecoveryNotice
      actionLabel={copy.actionLabel}
      actionPending={actionPending}
      dataTestId={`report-watch-recovery-${surface}`}
      description={copy.description}
      mode={recovery.mode}
      onAction={onAction}
      title={copy.title}
    />
  );
}
