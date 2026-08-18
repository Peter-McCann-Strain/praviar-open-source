"use client";

import {
  createElement,
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { normalizeMonitorSchedule } from "@/components/monitors/helpers";
import { useMutationRecovery } from "@/hooks/use-mutation-recovery";
import {
  useCreateMonitor,
  useMonitorForAnalysisState,
  useUpdateMonitor,
} from "@/hooks/use-monitors";
import type {
  CreateMonitorInput,
  MonitorResponse,
  UpdateMonitorInput,
} from "@/hooks/use-monitors";
import { logError } from "@/lib/error-logger";
import type { FTOReport } from "@praviar/shared-types";

interface UseReportWatchControlArgs {
  analysisId: string;
  report: FTOReport;
}

export type ReportWatchRecoveryVariables =
  | { kind: "start"; variables: CreateMonitorInput }
  | { kind: "update"; variables: UpdateMonitorInput };

export type ReportWatchControl = ReturnType<typeof useReportWatchControl>;

const ReportWatchControlContext = createContext<ReportWatchControl | null>(
  null,
);

export function ReportWatchControlProvider({
  analysisId,
  children,
  report,
}: UseReportWatchControlArgs & { children: ReactNode }) {
  const control = useReportWatchControl({ analysisId, report });
  return createElement(
    ReportWatchControlContext.Provider,
    { value: control },
    children,
  );
}

export function useSharedReportWatchControl(): ReportWatchControl {
  const control = useContext(ReportWatchControlContext);
  if (!control) {
    throw new Error(
      "Report watch controls require ReportWatchControlProvider.",
    );
  }
  return control;
}

export function useReportWatchControl({
  analysisId,
  report,
}: UseReportWatchControlArgs) {
  const monitorQuery = useMonitorForAnalysisState(analysisId);
  const existingMonitor = monitorQuery.monitor;
  const createMonitor = useCreateMonitor();
  const updateMonitor = useUpdateMonitor();
  const mutationRecovery = useMutationRecovery<ReportWatchRecoveryVariables>();
  const [watchOverride, setWatchOverride] = useState<{
    enabled: boolean;
    monitorId?: string;
    schedule?: string;
  } | null>(null);
  const [recoveryRefreshPending, setRecoveryRefreshPending] = useState(false);
  const overrideDisabled = watchOverride?.enabled === false;
  const existingMonitorActive = existingMonitor?.is_active === true;
  const reactivatableMonitorId =
    watchOverride?.enabled === false && watchOverride.monitorId
      ? watchOverride.monitorId
      : watchOverride === null && existingMonitor?.is_active === false
        ? existingMonitor.id
        : undefined;
  const watchEnabled = overrideDisabled
    ? false
    : (watchOverride?.enabled ?? existingMonitorActive);
  const activeMonitorId = overrideDisabled
    ? undefined
    : (watchOverride?.monitorId ??
      (existingMonitorActive ? existingMonitor?.id : undefined));
  const watchSchedule = normalizeMonitorSchedule(
    watchOverride?.schedule ?? existingMonitor?.schedule ?? "weekly",
  );

  const applyMonitorSuccess = useCallback(
    (monitor: MonitorResponse) => {
      setWatchOverride({
        enabled: monitor.is_active,
        monitorId: monitor.id,
        schedule: monitor.schedule,
      });
      mutationRecovery.clearRecovery();
    },
    [mutationRecovery],
  );

  const applyMonitorUpdate = useCallback(
    (variables: UpdateMonitorInput, source: string) => {
      mutationRecovery.clearRecovery();
      const attempt = mutationRecovery.beginAttempt();
      updateMonitor.mutate(variables, {
        onSuccess: (monitor) => {
          if (!mutationRecovery.isAttemptCurrent(attempt)) return;
          applyMonitorSuccess(monitor);
        },
        onError: (error) => {
          logError(error, {
            source,
            extra: {
              analysisId,
              monitorId: variables.monitorId,
              schedule: variables.data.schedule,
              isActive: variables.data.is_active,
            },
          });
          mutationRecovery.captureFailure(
            error,
            {
              kind: "update",
              variables,
            },
            attempt,
          );
        },
      });
    },
    [analysisId, applyMonitorSuccess, mutationRecovery, updateMonitor],
  );

  const handleWatchToggle = useCallback(
    (enabled: boolean, schedule: string) => {
      if (
        createMonitor.isPending ||
        updateMonitor.isPending ||
        recoveryRefreshPending ||
        mutationRecovery.recovery
      ) {
        return;
      }

      const resolvedSchedule = normalizeMonitorSchedule(schedule);
      if (enabled) {
        const monitorIdToActivate = activeMonitorId ?? reactivatableMonitorId;

        if (monitorIdToActivate) {
          applyMonitorUpdate(
            {
              monitorId: monitorIdToActivate,
              data: { schedule: resolvedSchedule, is_active: true },
            },
            "useReportWatchControl.update",
          );
          return;
        }

        const variables: CreateMonitorInput = {
          analysis_id: analysisId,
          compound_smiles: report.compound?.canonical_smiles ?? undefined,
          compound_name: report.compound?.name ?? undefined,
          schedule: resolvedSchedule,
        };
        mutationRecovery.clearRecovery();
        const attempt = mutationRecovery.beginAttempt();
        createMonitor.mutate(variables, {
          onSuccess: (monitor) => {
            if (!mutationRecovery.isAttemptCurrent(attempt)) return;
            applyMonitorSuccess(monitor);
          },
          onError: (error) => {
            logError(error, {
              source: "useReportWatchControl.start",
              extra: { analysisId, schedule: resolvedSchedule },
            });
            mutationRecovery.captureFailure(
              error,
              {
                kind: "start",
                variables,
              },
              attempt,
            );
          },
        });
      } else if (activeMonitorId) {
        applyMonitorUpdate(
          {
            monitorId: activeMonitorId,
            data: { schedule: resolvedSchedule, is_active: false },
          },
          "useReportWatchControl.stop",
        );
      } else {
        setWatchOverride({ enabled: false });
      }
    },
    [
      activeMonitorId,
      analysisId,
      applyMonitorSuccess,
      applyMonitorUpdate,
      createMonitor,
      mutationRecovery,
      reactivatableMonitorId,
      recoveryRefreshPending,
      report.compound,
      updateMonitor.isPending,
    ],
  );

  const handleWatchRecoveryAction = useCallback(async () => {
    const recovery = mutationRecovery.recovery;
    if (!recovery || recoveryRefreshPending) return;

    if (recovery.variables.kind === "update") {
      applyMonitorUpdate(
        recovery.variables.variables,
        "useReportWatchControl.retryUpdate",
      );
      return;
    }

    if (recovery.mode === "failed") {
      mutationRecovery.clearRecovery();
      return;
    }

    setRecoveryRefreshPending(true);
    const attempt = mutationRecovery.beginAttempt();
    try {
      const refreshed = await monitorQuery.refetch();
      if (refreshed.error) {
        mutationRecovery.captureFailure(
          refreshed.error,
          recovery.variables,
          attempt,
          "outcome-unknown",
        );
        return;
      }
      if (!mutationRecovery.isAttemptCurrent(attempt)) return;
      setWatchOverride(null);
      mutationRecovery.clearRecoveryForAttempt(attempt);
    } catch (error) {
      logError(error, {
        source: "useReportWatchControl.refreshStartOutcome",
        extra: { analysisId },
      });
      mutationRecovery.captureFailure(
        error,
        recovery.variables,
        attempt,
        "outcome-unknown",
      );
    } finally {
      setRecoveryRefreshPending(false);
    }
  }, [
    analysisId,
    applyMonitorUpdate,
    monitorQuery,
    mutationRecovery,
    recoveryRefreshPending,
  ]);

  const watchPending =
    createMonitor.isPending ||
    updateMonitor.isPending ||
    recoveryRefreshPending;

  return useMemo(
    () => ({
      monitor: existingMonitor,
      watchEnabled,
      watchSchedule,
      watchPending,
      watchControlsLocked: watchPending || Boolean(mutationRecovery.recovery),
      watchRecovery: mutationRecovery.recovery,
      dismissWatchRecovery: mutationRecovery.clearRecovery,
      handleWatchRecoveryAction,
      handleWatchToggle,
    }),
    [
      existingMonitor,
      handleWatchRecoveryAction,
      handleWatchToggle,
      mutationRecovery.clearRecovery,
      mutationRecovery.recovery,
      watchEnabled,
      watchPending,
      watchSchedule,
    ],
  );
}
