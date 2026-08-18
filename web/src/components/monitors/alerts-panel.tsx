"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  AlertTriangle,
  CheckCircle,
  ChevronLeft,
  ChevronRight,
  Loader2,
  RotateCcw,
  X,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { MutationRecoveryNotice } from "@/components/shared/mutation-recovery-notice";
import {
  useDismissAlert,
  useMonitorAlerts,
  useReassessMonitorConclusion,
  type DismissAlertInput,
  type MonitorAlertResponse,
  type MonitorConclusionImpact,
} from "@/hooks/use-monitors";
import { useMutationRecovery } from "@/hooks/use-mutation-recovery";
import { useHydrationSafeRelativeTime } from "@/hooks/use-hydration-safe-relative-time";
import {
  formatMonitorDate,
  formatJurisdictionDeltas,
  formatMonitorStrategyMode,
  relativeTime,
  titleCase,
} from "@/components/monitors/helpers";
import { isAuthBoundaryError } from "@/lib/api-client";
import { cn } from "@/lib/utils";

interface AlertsPanelProps {
  monitorId: string;
  monitorName: string;
  openConclusionIds?: string[];
  canReassessConclusions?: boolean;
  className?: string;
  onClose: () => void;
}

export function AlertsPanel({
  monitorId,
  monitorName,
  openConclusionIds = [],
  canReassessConclusions = false,
  className,
  onClose,
}: AlertsPanelProps) {
  const perPage = 20;
  const [page, setPage] = useState(1);
  const { data, error, isLoading, isFetching, isPlaceholderData, refetch } =
    useMonitorAlerts(monitorId, page, perPage);
  const dismissAlert = useDismissAlert();
  const dismissRecovery = useMutationRecovery<DismissAlertInput>();
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const responsePerPage = data?.per_page ?? perPage;
  const totalPages = Math.max(
    1,
    Math.ceil((data?.total ?? 0) / responsePerPage),
  );
  const responsePage = data?.page ?? page;
  const displayPage = Math.min(Math.max(1, responsePage), totalPages);
  const accessRestricted = isAuthBoundaryError(error);
  const isPanelUpdating = Boolean(isFetching && data);
  const hasAlertRows = Boolean(
    !accessRestricted && data && data.items.length > 0,
  );
  const shouldShowLoadError = Boolean(
    error && (accessRestricted || !data || data.items.length === 0),
  );
  const shouldShowRefreshWarning = Boolean(error && hasAlertRows);
  const isOutOfRangeAlertPage = Boolean(
    data && data.total > 0 && data.items.length === 0 && !error,
  );

  useEffect(() => {
    if (!data) return undefined;
    if (page <= totalPages) return undefined;
    const clampTimer = window.setTimeout(() => {
      setPage(totalPages);
    }, 0);
    return () => window.clearTimeout(clampTimer);
  }, [data, page, totalPages]);

  useEffect(() => {
    closeButtonRef.current?.focus();
  }, [monitorId]);

  function applyAlertDismissal(variables: DismissAlertInput) {
    dismissRecovery.clearRecovery();
    const attempt = dismissRecovery.beginAttempt();
    dismissAlert.mutate(variables, {
      onSuccess: () => dismissRecovery.clearRecoveryForAttempt(attempt),
      onError: (mutationError) => {
        dismissRecovery.captureFailure(mutationError, variables, attempt);
      },
    });
  }

  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardHeader className="praviar-glass-strip border-b border-[var(--border-default)]">
        <div className="flex items-center justify-between">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
              Alert history
            </p>
            <CardTitle className="mt-1 min-w-0 break-words text-base">
              {monitorName}
            </CardTitle>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            aria-label="Close alerts panel"
            className="ml-3 flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {dismissRecovery.recovery ? (
          <div className="border-b border-[var(--border-subtle)] p-4 sm:p-5">
            <MutationRecoveryNotice
              actionLabel="Retry exact acknowledgement"
              actionPending={dismissAlert.isPending}
              dataTestId="monitor-alert-dismiss-recovery"
              description={
                dismissRecovery.recovery.mode === "outcome-unknown"
                  ? "Praviar could not confirm whether this alert was acknowledged. Reapplying the same acknowledgement is safe and will reconcile the alert history."
                  : "The alert was not acknowledged. Retry the exact acknowledgement or keep the alert open."
              }
              dismissLabel="Keep unacknowledged"
              mode={dismissRecovery.recovery.mode}
              onAction={() =>
                applyAlertDismissal(dismissRecovery.recovery!.variables)
              }
              onDismiss={
                dismissRecovery.recovery.mode === "failed"
                  ? dismissRecovery.clearRecovery
                  : undefined
              }
              title={
                dismissRecovery.recovery.mode === "outcome-unknown"
                  ? "Alert acknowledgement outcome unconfirmed"
                  : "Alert was not acknowledged"
              }
            />
          </div>
        ) : null}

        {isLoading && !data ? (
          <div
            role="status"
            aria-live="polite"
            aria-busy="true"
            className="flex flex-col items-center justify-center px-6 py-12 text-center"
          >
            <Loader2
              className="h-6 w-6 animate-spin motion-reduce:animate-none text-brand-primary"
              aria-hidden="true"
            />
            <p className="mt-3 text-sm font-medium text-[var(--text-primary)]">
              Loading monitor alerts
            </p>
            <p className="mt-1 max-w-md text-sm text-[var(--text-secondary)]">
              Retrieving new patent events and alert history for this watch.
            </p>
          </div>
        ) : shouldShowLoadError ? (
          <div
            role="alert"
            aria-labelledby="monitor-alerts-load-error-title"
            className="px-6 py-8"
          >
            <div className="rounded-lg border border-error/20 bg-error/10 p-4">
              <div className="flex items-start gap-3">
                <AlertTriangle
                  className="mt-0.5 h-5 w-5 shrink-0 text-error"
                  aria-hidden="true"
                />
                <div className="min-w-0">
                  <p
                    id="monitor-alerts-load-error-title"
                    className="font-semibold text-[var(--text-primary)]"
                  >
                    {accessRestricted
                      ? "Alert history access restricted"
                      : "Alert history temporarily unavailable"}
                  </p>
                  <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                    {accessRestricted
                      ? "Your current session is not authorized to view this monitor alert history. Cached alert rows are hidden until access is confirmed again."
                      : "Praviar could not load alert history for this monitor. The watch remains unchanged, and the absence of alerts has not been verified."}
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    className="mt-4 min-h-11 w-full gap-2 sm:w-auto"
                    onClick={() => {
                      void refetch();
                    }}
                  >
                    <RotateCcw className="h-4 w-4" aria-hidden="true" />
                    Retry alert load
                  </Button>
                </div>
              </div>
            </div>
          </div>
        ) : isOutOfRangeAlertPage ? (
          <div
            role="status"
            aria-live="polite"
            className="px-6 py-10 text-center"
          >
            <Loader2
              className="mx-auto h-7 w-7 animate-spin motion-reduce:animate-none text-brand-primary"
              aria-hidden="true"
            />
            <p className="mt-3 text-sm font-semibold text-[var(--text-primary)]">
              Refreshing alert page
            </p>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              The alert result window is empty while Praviar returns this watch
              to a valid page. No absence of alerts is being inferred.
            </p>
          </div>
        ) : !data || data.items.length === 0 ? (
          <div className="px-6 py-10 text-center">
            <CheckCircle
              className="mx-auto h-8 w-8 text-success"
              aria-hidden="true"
            />
            <p className="mt-3 text-sm font-semibold text-[var(--text-primary)]">
              No monitored changes detected
            </p>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              The alert history is empty for the selected watch and scope. This
              does not replace a completed monitoring run or legal review.
            </p>
          </div>
        ) : (
          <>
            {shouldShowRefreshWarning ? (
              <div
                role="status"
                className="border-b border-warning/20 bg-warning/10 px-5 py-3 text-xs leading-5 text-[var(--text-secondary)] sm:px-6"
              >
                Alert refresh failed. Showing the last loaded alert history; the
                absence of newer alerts has not been verified.
              </div>
            ) : null}
            <ul className="divide-y divide-[var(--border-subtle)]">
              {data.items.map((alert: MonitorAlertResponse) => (
                <AlertHistoryItem
                  key={alert.id}
                  alert={alert}
                  monitorId={monitorId}
                  monitorName={monitorName}
                  openConclusionIds={openConclusionIds}
                  canReassessConclusions={canReassessConclusions}
                  dismissPending={
                    dismissAlert.isPending || Boolean(dismissRecovery.recovery)
                  }
                  onDismiss={(alertId) =>
                    applyAlertDismissal({ monitorId, alertId })
                  }
                />
              ))}
            </ul>
            {totalPages > 1 ? (
              <div className="flex flex-col gap-3 border-t border-[var(--border-subtle)] px-6 py-3 sm:flex-row sm:items-center sm:justify-between">
                <p
                  className="text-xs text-[var(--text-tertiary)]"
                  role="status"
                  aria-live="polite"
                >
                  Page {displayPage} of {totalPages}
                  {isPanelUpdating && page !== displayPage
                    ? ` · updating page ${page}`
                    : isPanelUpdating
                      ? " · refreshing"
                      : ""}
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="min-h-11 min-w-11"
                    disabled={displayPage <= 1 || Boolean(isPlaceholderData)}
                    aria-label={`Previous alert page for ${monitorName}`}
                    onClick={() =>
                      setPage((current) =>
                        current > totalPages
                          ? totalPages
                          : Math.max(1, current - 1),
                      )
                    }
                  >
                    <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="min-h-11 min-w-11"
                    disabled={
                      displayPage >= totalPages || Boolean(isPlaceholderData)
                    }
                    aria-label={`Next alert page for ${monitorName}`}
                    onClick={() =>
                      setPage((current) => Math.min(totalPages, current + 1))
                    }
                  >
                    <ChevronRight className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </div>
              </div>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function AlertHistoryItem({
  alert,
  monitorId,
  monitorName,
  openConclusionIds,
  canReassessConclusions,
  dismissPending,
  onDismiss,
}: {
  alert: MonitorAlertResponse;
  monitorId: string;
  monitorName: string;
  openConclusionIds: string[];
  canReassessConclusions: boolean;
  dismissPending: boolean;
  onDismiss: (alertId: string) => void;
}) {
  const reassessConclusion = useReassessMonitorConclusion();
  const [selectedConclusion, setSelectedConclusion] =
    useState<MonitorConclusionImpact | null>(null);
  const [resolution, setResolution] = useState<
    "reaffirmed" | "superseded" | "withdrawn"
  >("reaffirmed");
  const [resolutionNote, setResolutionNote] = useState("");
  const [replacementAnalysisId, setReplacementAnalysisId] = useState("");
  const [attestationAccepted, setAttestationAccepted] = useState(false);
  const [showAllConclusions, setShowAllConclusions] = useState(false);
  const formatRelativeTime = useHydrationSafeRelativeTime(relativeTime);
  const patentIds = alert.new_patent_ids ?? [];
  const visiblePatentIds = patentIds.slice(0, 3);
  const extraPatentIds = Math.max(
    0,
    patentIds.length - visiblePatentIds.length,
  );
  const eventIds = alert.new_event_ids ?? [];
  const visibleEventIds = eventIds.slice(0, 3);
  const extraEventIds = Math.max(0, eventIds.length - visibleEventIds.length);
  const affectedConclusions = alert.affected_conclusions ?? [];
  const openConclusionIdSet = new Set(openConclusionIds);
  const visibleConclusions = showAllConclusions
    ? affectedConclusions
    : affectedConclusions.slice(0, 3);
  const hiddenConclusionCount = Math.max(0, affectedConclusions.length - 3);
  const alertHeadline =
    affectedConclusions.length > 0
      ? `${affectedConclusions.length.toLocaleString()} report conclusion${
          affectedConclusions.length === 1 ? "" : "s"
        } require${affectedConclusions.length === 1 ? "s" : ""} attorney reassessment`
      : alert.new_patent_count > 0 && eventIds.length > 0
        ? `${alert.new_patent_count.toLocaleString()} new patent${
            alert.new_patent_count === 1 ? "" : "s"
          } and ${eventIds.length.toLocaleString()} monitored event${
            eventIds.length === 1 ? "" : "s"
          } detected`
        : alert.new_patent_count > 0
          ? `${alert.new_patent_count.toLocaleString()} new patent${
              alert.new_patent_count === 1 ? "" : "s"
            } found`
          : eventIds.length > 0
            ? `${eventIds.length.toLocaleString()} monitored event${
                eventIds.length === 1 ? "" : "s"
              } detected`
            : "Monitored change detected";
  const severity = alert.severity ? titleCase(alert.severity) : null;
  const alertType = alert.alert_type ? titleCase(alert.alert_type) : null;
  const strategyMode = alert.strategy_mode
    ? formatMonitorStrategyMode(alert.strategy_mode)
    : null;
  const jurisdictionDeltaSummary = formatJurisdictionDeltas(
    alert.jurisdiction_deltas,
  );
  const normalizedNote = resolutionNote.trim();
  const exactEpisodeBound = Boolean(
    selectedConclusion?.reassessment_id &&
    selectedConclusion.alert_id === alert.id &&
    selectedConclusion.dependency_fingerprint &&
    selectedConclusion.evidence_digest &&
    selectedConclusion.evidence_version &&
    selectedConclusion.evidence_observed_at,
  );
  const reassessmentReady =
    selectedConclusion !== null &&
    exactEpisodeBound &&
    normalizedNote.length >= 20 &&
    attestationAccepted &&
    (resolution !== "superseded" || replacementAnalysisId.trim().length > 0);

  function resetReassessmentForm() {
    setSelectedConclusion(null);
    setResolution("reaffirmed");
    setResolutionNote("");
    setReplacementAnalysisId("");
    setAttestationAccepted(false);
    reassessConclusion.reset();
  }

  function submitReassessment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedConclusion || !reassessmentReady) return;
    reassessConclusion.mutate(
      {
        monitorId,
        conclusionId: selectedConclusion.conclusion_id,
        data: {
          resolution,
          resolution_note: normalizedNote,
          attestation_accepted: true,
          reassessment_id: selectedConclusion.reassessment_id!,
          alert_id: selectedConclusion.alert_id!,
          dependency_fingerprint: selectedConclusion.dependency_fingerprint,
          evidence_digest: selectedConclusion.evidence_digest!,
          evidence_version: selectedConclusion.evidence_version!,
          evidence_observed_at: selectedConclusion.evidence_observed_at!,
          ...(resolution === "superseded"
            ? { replacement_analysis_id: replacementAnalysisId.trim() }
            : {}),
        },
      },
      {
        onSuccess: resetReassessmentForm,
      },
    );
  }

  return (
    <li className="px-5 py-4 sm:px-6">
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border",
            alert.dismissed
              ? "border-success/20 bg-success/10 text-success"
              : "border-warning/25 bg-warning/10 text-warning",
          )}
        >
          {alert.dismissed ? (
            <CheckCircle className="h-4 w-4" aria-hidden="true" />
          ) : (
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {alertHeadline}
              </p>
              <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                {alert.summary ||
                  "New patent identifiers were detected for this monitor."}
              </p>
            </div>
            {!alert.dismissed ? (
              <Button
                variant="ghost"
                size="sm"
                className="min-h-11 shrink-0"
                disabled={dismissPending}
                aria-label={`Acknowledge alert ${alert.id} for ${monitorName}`}
                onClick={() => onDismiss(alert.id)}
              >
                Acknowledge alert
              </Button>
            ) : (
              <span className="rounded-full border border-success/20 bg-success/10 px-2.5 py-1 text-xs font-medium text-success">
                Acknowledged
              </span>
            )}
          </div>

          {visibleConclusions.length > 0 ? (
            <div
              className="mt-3 rounded-lg border border-warning/25 bg-warning/10 p-3"
              role="note"
              aria-label="Conclusions requiring attorney reassessment"
            >
              <p className="text-xs font-semibold text-warning">
                Do not rely on these prior conclusions until reassessed
              </p>
              <ul className="mt-2 space-y-2">
                {visibleConclusions.map((impact) => (
                  <li
                    key={impact.conclusion_id}
                    className="break-words text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]"
                  >
                    <span className="font-semibold text-[var(--text-primary)]">
                      {impact.label}
                    </span>
                    {" · "}previously {titleCase(impact.previous_outcome)}
                    {impact.jurisdictions.length > 0
                      ? ` · ${impact.jurisdictions.join(", ")}`
                      : ""}
                    <details className="mt-2 rounded-md border border-warning/20 bg-[var(--bg-surface)]/70 p-2">
                      <summary className="min-h-10 cursor-pointer py-2 text-xs font-semibold text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70">
                        Review exact changed evidence
                      </summary>
                      <dl className="mt-2 space-y-2 text-xs leading-5 text-[var(--text-tertiary)]">
                        <div>
                          <dt className="font-semibold text-[var(--text-secondary)]">
                            Trigger patents
                          </dt>
                          <dd className="break-all">
                            {impact.trigger_patent_ids.length > 0
                              ? impact.trigger_patent_ids.join(", ")
                              : "None"}
                          </dd>
                        </div>
                        <div>
                          <dt className="font-semibold text-[var(--text-secondary)]">
                            Trigger events
                          </dt>
                          <dd className="break-all">
                            {impact.trigger_event_ids.length > 0
                              ? impact.trigger_event_ids.join(", ")
                              : "None"}
                          </dd>
                        </div>
                        <div>
                          <dt className="font-semibold text-[var(--text-secondary)]">
                            Dependency fingerprint
                          </dt>
                          <dd className="break-all font-mono">
                            {impact.dependency_fingerprint}
                          </dd>
                        </div>
                        <div>
                          <dt className="font-semibold text-[var(--text-secondary)]">
                            Evidence receipt
                          </dt>
                          <dd className="break-all font-mono">
                            {impact.evidence_digest ||
                              "Historical receipt unavailable"}
                          </dd>
                        </div>
                        <div>
                          <dt className="font-semibold text-[var(--text-secondary)]">
                            Evidence version and observation
                          </dt>
                          <dd>
                            {impact.evidence_version || "Historical"}
                            {impact.evidence_observed_at
                              ? ` · ${formatMonitorDate(impact.evidence_observed_at)}`
                              : ""}
                          </dd>
                        </div>
                      </dl>
                    </details>
                    <div className="mt-1.5">
                      {openConclusionIdSet.has(impact.conclusion_id) ? (
                        canReassessConclusions &&
                        impact.reassessment_id &&
                        impact.alert_id === alert.id &&
                        impact.evidence_digest &&
                        impact.evidence_version &&
                        impact.evidence_observed_at ? (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="min-h-10"
                            disabled={reassessConclusion.isPending}
                            onClick={() => {
                              setSelectedConclusion(impact);
                              reassessConclusion.reset();
                            }}
                          >
                            Record counsel reassessment
                          </Button>
                        ) : (
                          <span className="text-xs text-[var(--text-tertiary)]">
                            {canReassessConclusions
                              ? "This historical alert is read-only because it lacks an exact episode receipt."
                              : "Attorney-role access is required to record the reassessment."}
                          </span>
                        )
                      ) : (
                        <span className="inline-flex rounded-full border border-success/20 bg-success/10 px-2 py-0.5 text-xs font-semibold text-success">
                          Reassessment recorded
                        </span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
              {hiddenConclusionCount > 0 ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="mt-2 min-h-10"
                  aria-expanded={showAllConclusions}
                  onClick={() => setShowAllConclusions((current) => !current)}
                >
                  {showAllConclusions
                    ? "Show fewer conclusions"
                    : `Show ${hiddenConclusionCount.toLocaleString()} more conclusion${
                        hiddenConclusionCount === 1 ? "" : "s"
                      }`}
                </Button>
              ) : null}
              <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">
                Acknowledging this notification does not restore conclusion
                currency.
              </p>
              {selectedConclusion ? (
                <form
                  className="mt-3 space-y-3 border-t border-warning/20 pt-3"
                  onSubmit={submitReassessment}
                >
                  <div>
                    <p className="text-xs font-semibold text-[var(--text-primary)]">
                      Reassess {selectedConclusion.label}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
                      This creates a durable, attributed legal record. The
                      source report remains unapproved until report-level review
                      is completed again.
                    </p>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor={`resolution-${alert.id}`}>
                      Counsel disposition
                    </Label>
                    <select
                      id={`resolution-${alert.id}`}
                      className="praviar-glass-field min-h-11 w-full rounded-lg px-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-brand-primary/70"
                      value={resolution}
                      disabled={reassessConclusion.isPending}
                      onChange={(event) =>
                        setResolution(
                          event.target.value as
                            | "reaffirmed"
                            | "superseded"
                            | "withdrawn",
                        )
                      }
                    >
                      <option value="reaffirmed">
                        Reaffirm after evidence review
                      </option>
                      <option value="superseded">
                        Supersede with replacement analysis
                      </option>
                      <option value="withdrawn">
                        Withdraw prior conclusion
                      </option>
                    </select>
                  </div>
                  {resolution === "superseded" ? (
                    <div className="space-y-1.5">
                      <Label htmlFor={`replacement-analysis-${alert.id}`}>
                        Replacement analysis ID
                      </Label>
                      <Input
                        id={`replacement-analysis-${alert.id}`}
                        value={replacementAnalysisId}
                        disabled={reassessConclusion.isPending}
                        placeholder="Completed analysis UUID"
                        onChange={(event) =>
                          setReplacementAnalysisId(event.target.value)
                        }
                      />
                    </div>
                  ) : null}
                  <div className="space-y-1.5">
                    <Label htmlFor={`resolution-note-${alert.id}`}>
                      Reassessment rationale
                    </Label>
                    <Textarea
                      id={`resolution-note-${alert.id}`}
                      value={resolutionNote}
                      disabled={reassessConclusion.isPending}
                      placeholder="Explain the evidence reviewed and why this disposition is appropriate."
                      onChange={(event) =>
                        setResolutionNote(event.target.value)
                      }
                    />
                    <p className="text-xs text-[var(--text-tertiary)]">
                      Minimum 20 characters · {normalizedNote.length}/5000
                    </p>
                  </div>
                  <label className="flex cursor-pointer items-start gap-2 text-xs leading-5 text-[var(--text-secondary)]">
                    <input
                      type="checkbox"
                      className="mt-1 h-4 w-4 rounded border-[var(--border-emphasis)] accent-brand-primary"
                      checked={attestationAccepted}
                      disabled={reassessConclusion.isPending}
                      onChange={(event) =>
                        setAttestationAccepted(event.target.checked)
                      }
                    />
                    <span>
                      I attest that I reviewed the cited monitoring changes, the
                      affected source-report conclusion, and its supporting
                      evidence, and that this disposition reflects my
                      professional reassessment.
                    </span>
                  </label>
                  {reassessConclusion.error ? (
                    <p className="text-xs leading-5 text-error" role="alert">
                      The reassessment was not recorded. Confirm your
                      attorney-role session, evidence, and replacement analysis,
                      then retry the exact disposition.
                    </p>
                  ) : null}
                  <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                    <Button
                      type="button"
                      variant="ghost"
                      className="min-h-11"
                      disabled={reassessConclusion.isPending}
                      onClick={resetReassessmentForm}
                    >
                      Cancel
                    </Button>
                    <Button
                      type="submit"
                      className="min-h-11"
                      disabled={
                        !reassessmentReady || reassessConclusion.isPending
                      }
                    >
                      {reassessConclusion.isPending ? (
                        <Loader2
                          className="mr-2 h-4 w-4 animate-spin motion-reduce:animate-none"
                          aria-hidden="true"
                        />
                      ) : null}
                      Attest and record
                    </Button>
                  </div>
                </form>
              ) : null}
            </div>
          ) : null}

          <div className="mt-3 flex flex-wrap gap-1.5">
            {severity ? <AlertChip label={severity} tone="warning" /> : null}
            {alertType ? <AlertChip label={alertType} /> : null}
            {strategyMode ? <AlertChip label={strategyMode} /> : null}
            <AlertChip label={`Run ${formatMonitorDate(alert.run_at)}`} />
            <AlertChip label={formatRelativeTime(alert.created_at)} />
          </div>

          {visiblePatentIds.length > 0 ? (
            <p className="mt-3 break-all font-mono text-xs leading-5 text-[var(--text-tertiary)]">
              {visiblePatentIds.join(", ")}
              {extraPatentIds > 0 ? ` +${extraPatentIds} more` : ""}
            </p>
          ) : null}

          {visibleEventIds.length > 0 ? (
            <p className="mt-2 break-all font-mono text-xs leading-5 text-[var(--text-tertiary)]">
              Event references: {visibleEventIds.join(", ")}
              {extraEventIds > 0 ? ` +${extraEventIds} more` : ""}
            </p>
          ) : null}

          {jurisdictionDeltaSummary ? (
            <p className="mt-2 break-words text-xs leading-5 text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
              Jurisdiction deltas: {jurisdictionDeltaSummary}
            </p>
          ) : null}
          <span className="sr-only">Monitor id {monitorId}</span>
        </div>
      </div>
    </li>
  );
}

function AlertChip({
  label,
  tone = "neutral",
}: {
  label: string;
  tone?: "neutral" | "warning";
}) {
  return (
    <span
      className={cn(
        "max-w-full break-words rounded-full border px-2.5 py-1 text-xs font-medium [overflow-wrap:anywhere]",
        tone === "warning"
          ? "border-warning/25 bg-warning/10 text-warning"
          : "border-[var(--border-subtle)] bg-[var(--surface-muted)] text-[var(--text-tertiary)]",
      )}
    >
      {label}
    </span>
  );
}
