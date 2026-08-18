"use client";

import { useState } from "react";
import { AppSurfaceHeader } from "@/components/shared/app-surface-header";
import { Button } from "@/components/ui/button";
import { AlertTriangle } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useErrorDiagnostic } from "@/hooks/use-error-diagnostic";
import { AccountControlStatusState } from "@/components/shared/account-control-status-state";
import { MutationRecoveryNotice } from "@/components/shared/mutation-recovery-notice";
import {
  useNotificationPreferences,
  useUpdateNotificationPreferences,
  type NotificationPreferences,
} from "@/hooks/use-notifications";
import {
  useMutationRecovery,
  type MutationRecoveryState,
} from "@/hooks/use-mutation-recovery";
import { isAuthBoundaryError } from "@/lib/api-client";
import { useToastStore } from "@/stores/toast-store";
import { DEFAULT_NOTIFICATION_PREFERENCES } from "./notification-settings-constants";
import { NotificationSettingsFrequencySelector } from "./notification-settings-frequency-selector";
import { NotificationSettingsToggle } from "./notification-settings-toggle";

function reportNotificationPreferencesAccessRestriction() {
  console.error(
    "[NotificationSettingsPage] Notification preferences access restricted",
  );
}

function reportNotificationPreferencesLoadFailure() {
  console.error("[NotificationSettingsPage] Failed to load preferences");
}

export default function NotificationSettingsPage() {
  const token = useAuthToken();
  const addToast = useToastStore((state) => state.addToast);
  const {
    data: prefs,
    error,
    isLoading,
    isError,
    refetch,
  } = useNotificationPreferences(token);
  const updatePrefs = useUpdateNotificationPreferences(token);
  const saveRecovery = useMutationRecovery<NotificationPreferences>();
  const accessRestricted = isAuthBoundaryError(error);
  const authPending = !token && !prefs;
  const preferencesLoadFailed = Boolean(
    !isLoading && !authPending && isError && !prefs && !accessRestricted,
  );

  useErrorDiagnostic(
    !isLoading && !authPending && accessRestricted,
    error,
    reportNotificationPreferencesAccessRestriction,
  );
  useErrorDiagnostic(
    preferencesLoadFailed,
    error,
    reportNotificationPreferencesLoadFailure,
  );

  if (isLoading) {
    return (
      <div className="mx-auto max-w-2xl space-y-5">
        <NotificationSettingsHeader />
        <AccountControlStatusState surface="notifications" variant="loading" />
      </div>
    );
  }

  if (authPending) {
    return (
      <div className="mx-auto max-w-2xl space-y-5">
        <NotificationSettingsHeader />
        <AccountControlStatusState surface="notifications" variant="auth" />
      </div>
    );
  }

  if (accessRestricted) {
    return (
      <div className="mx-auto max-w-2xl space-y-5">
        <NotificationSettingsHeader />
        <AccountControlStatusState
          surface="notifications"
          variant="restricted"
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (isError && !prefs) {
    return (
      <div className="mx-auto max-w-2xl space-y-5">
        <NotificationSettingsHeader />
        <AccountControlStatusState
          surface="notifications"
          variant="temporary"
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  const initialPrefs = prefs ?? DEFAULT_NOTIFICATION_PREFERENCES;

  return (
    <NotificationSettingsForm
      key={JSON.stringify(initialPrefs)}
      initialPrefs={initialPrefs}
      isRefreshStale={Boolean(isError && prefs)}
      isSaving={updatePrefs.isPending}
      recovery={saveRecovery.recovery}
      onClearRecovery={saveRecovery.clearRecovery}
      onRetry={() => {
        void refetch();
      }}
      onSave={(nextPrefs, callbacks) => {
        const attempt = saveRecovery.beginAttempt();
        updatePrefs.mutate(nextPrefs, {
          onSuccess: () => {
            if (saveRecovery.clearRecoveryForAttempt(attempt)) {
              addToast("Notification preferences saved", "success");
              callbacks.onSaved();
            }
            callbacks.onSettled();
          },
          onError: (mutationError) => {
            saveRecovery.captureFailure(mutationError, nextPrefs, attempt);
            callbacks.onSettled();
          },
        });
      }}
    />
  );
}

function NotificationSettingsForm({
  initialPrefs,
  isRefreshStale,
  isSaving,
  recovery,
  onClearRecovery,
  onRetry,
  onSave,
}: {
  initialPrefs: NotificationPreferences;
  isRefreshStale: boolean;
  isSaving: boolean;
  recovery: MutationRecoveryState<NotificationPreferences> | null;
  onClearRecovery: () => void;
  onRetry: () => void;
  onSave: (
    prefs: NotificationPreferences,
    callbacks: { onSaved: () => void; onSettled: () => void },
  ) => void;
}) {
  const [localPrefs, setLocalPrefs] =
    useState<NotificationPreferences>(initialPrefs);
  const [isDirty, setIsDirty] = useState(false);
  const [saveSubmitted, setSaveSubmitted] = useState(false);
  const controlsDisabled =
    isSaving || saveSubmitted || isRefreshStale || Boolean(recovery);

  function updateLocal(patch: Partial<NotificationPreferences>) {
    if (controlsDisabled) {
      return;
    }
    setLocalPrefs((prev) => ({ ...prev, ...patch }));
    setIsDirty(true);
  }

  function submitPreferences(prefs: NotificationPreferences) {
    setSaveSubmitted(true);
    onSave(prefs, {
      onSaved: () => setIsDirty(false),
      onSettled: () => setSaveSubmitted(false),
    });
  }

  function handleSave() {
    if (!isDirty || controlsDisabled) {
      return;
    }
    submitPreferences(localPrefs);
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <NotificationSettingsHeader />

      {isRefreshStale ? (
        <div
          role="status"
          aria-live="polite"
          className="rounded-lg border border-warning/20 bg-warning/10 px-4 py-3"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-start gap-2">
              <AlertTriangle
                className="mt-0.5 h-4 w-4 shrink-0 text-warning"
                aria-hidden="true"
              />
              <p className="text-sm leading-6 text-[var(--text-secondary)]">
                Notification preference refresh failed. Existing preferences
                remain visible for reference, but edits are locked until the
                latest settings reload.
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              className="min-h-11 w-full sm:w-auto"
              onClick={onRetry}
            >
              Retry refresh
            </Button>
          </div>
        </div>
      ) : null}

      {recovery ? (
        <MutationRecoveryNotice
          actionLabel={
            recovery.mode === "outcome-unknown"
              ? "Reapply exact preferences"
              : "Retry exact save"
          }
          actionPending={isSaving || saveSubmitted}
          dataTestId="notification-preferences-save-recovery"
          description={
            recovery.mode === "outcome-unknown"
              ? "Praviar could not confirm the saved delivery policy. Reapplying the exact preserved preference payload is safe because this update replaces the full preference state."
              : "The preserved preference payload was not saved. Retry that exact payload or keep editing without losing the selected values."
          }
          dismissLabel="Keep editing"
          mode={recovery.mode}
          onAction={() => submitPreferences(recovery.variables)}
          onDismiss={recovery.mode === "failed" ? onClearRecovery : undefined}
          title={
            recovery.mode === "outcome-unknown"
              ? "Notification save outcome unconfirmed"
              : "Notification preferences were not saved"
          }
        />
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle role="heading" aria-level={2}>
            Email notifications
          </CardTitle>
          <CardDescription>
            Toggle individual email notification types on or off.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="divide-y divide-[var(--border-default)]">
            <NotificationSettingsToggle
              checked={localPrefs.email_on_analysis_complete}
              disabled={controlsDisabled}
              onChange={(value) =>
                updateLocal({ email_on_analysis_complete: value })
              }
              label="Analysis Complete"
              description="Receive an email when an FTO analysis finishes. Emails may reveal analysis activity; report contents stay behind sign-in."
            />
            <NotificationSettingsToggle
              checked={localPrefs.email_on_monitor_alert}
              disabled={controlsDisabled}
              onChange={(value) =>
                updateLocal({ email_on_monitor_alert: value })
              }
              label="Patent Monitor Alerts"
              description="Receive an email when patent monitoring detects new patent activity. Alert details stay behind sign-in."
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle role="heading" aria-level={2}>
            Activity digest
          </CardTitle>
          <CardDescription>
            Periodic summary of your organization&apos;s FTO activity.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <NotificationSettingsFrequencySelector
            value={localPrefs.email_digest_frequency}
            disabled={controlsDisabled}
            onChange={(value) => updateLocal({ email_digest_frequency: value })}
          />
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center justify-end gap-3">
        {isDirty ? (
          <p className="text-xs text-[var(--text-tertiary)]">
            You have unsaved changes
          </p>
        ) : null}
        <Button
          className="min-h-11"
          onClick={handleSave}
          disabled={!isDirty || controlsDisabled}
          loading={isSaving || saveSubmitted}
        >
          Save Preferences
        </Button>
      </div>
    </div>
  );
}

function NotificationSettingsHeader() {
  return (
    <AppSurfaceHeader
      dataTestId="notification-settings-app-surface-header"
      eyebrow="Notification policy"
      mobileDensity="compact"
      title="Notification settings"
      description="Choose which workspace events can leave the product by email."
      metrics={[
        { label: "Channel", value: "Email" },
        { label: "Evidence", value: "Sign-in gated" },
        { label: "Scope", value: "Organization" },
      ]}
    />
  );
}
