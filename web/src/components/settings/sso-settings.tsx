"use client";

import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  ExternalLink,
  Loader2,
  RotateCcw,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useConfigureSSO, useSSOStatus } from "@/hooks/use-sso";
import type { SSOConfigureResponse, SSOStatus } from "@/hooks/use-sso";
import { isAuthBoundaryError } from "@/lib/api-client";
import { useToastStore } from "@/stores/toast-store";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import { validatedClerkDashboardUrl } from "@/lib/sso-dashboard-url";

const SSO_STATUS_MAX_AGE_MS = 5 * 60_000;

function hasFreshSSOStatus(status: SSOStatus): boolean {
  if (
    !status.sso_status_available ||
    status.sso_status_stale ||
    !status.sso_last_synced_at
  ) {
    return false;
  }
  const syncedAt = Date.parse(status.sso_last_synced_at);
  const age = Date.now() - syncedAt;
  return Number.isFinite(syncedAt) && age >= 0 && age <= SSO_STATUS_MAX_AGE_MS;
}

type ConfigureRecoveryMode = "outcome_unknown" | "checking" | "retry_safe";

interface ConfigureRecovery {
  enable: boolean;
  mode: ConfigureRecoveryMode;
}

// ── Status badge ──────────────────────────────────────────────────────────────

function SSOStatusBadge({ status }: { status: SSOStatus["status"] }) {
  if (status === "active") {
    return (
      <Badge variant="success" className="gap-1">
        <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
        Active
      </Badge>
    );
  }
  if (status === "pending") {
    return (
      <Badge variant="warning" className="gap-1">
        <Clock className="h-3 w-3" aria-hidden="true" />
        Pending setup
      </Badge>
    );
  }
  return (
    <Badge variant="secondary" className="gap-1">
      <XCircle className="h-3 w-3" aria-hidden="true" />
      Not configured
    </Badge>
  );
}

// ── Setup instructions panel ──────────────────────────────────────────────────

interface InstructionsPanelProps {
  result: SSOConfigureResponse;
  onDismiss: () => void;
}

function InstructionsPanel({ result, onDismiss }: InstructionsPanelProps) {
  const dashboardUrl = validatedClerkDashboardUrl(result.clerk_dashboard_url, {
    demoMode: DEMO_MODE_ENABLED,
  });

  return (
    <div
      role="region"
      aria-label="SSO setup instructions"
      className="space-y-4 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)] p-5"
    >
      <p className="type-body-sm text-[var(--text-secondary)]">
        {result.message}
      </p>

      <ol className="space-y-2 list-none">
        {result.next_steps.map((step, index) => (
          <li key={index} className="flex gap-3">
            <span className="flex-none flex items-center justify-center h-5 w-5 rounded-full bg-brand-primary/10 text-brand-primary text-xs font-semibold mt-0.5">
              {index + 1}
            </span>
            <span className="type-body-sm text-[var(--text-primary)]">
              {step}
            </span>
          </li>
        ))}
      </ol>

      <div className="flex flex-wrap items-center gap-3 pt-1">
        {dashboardUrl ? (
          <Button
            asChild
            variant="default"
            size="sm"
            className="min-h-11 gap-2"
          >
            <a href={dashboardUrl} target="_blank" rel="noopener noreferrer">
              Open Clerk Dashboard
              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
            </a>
          </Button>
        ) : null}
        <Button
          variant="ghost"
          size="sm"
          className="min-h-11"
          onClick={onDismiss}
        >
          Dismiss
        </Button>
      </div>
      {result.clerk_dashboard_url && !dashboardUrl ? (
        <p role="alert" className="type-body-xs text-error">
          The identity-provider dashboard link was rejected because it did not
          match Praviar&apos;s trusted Clerk destination.
        </p>
      ) : null}
    </div>
  );
}

// ── Domains list ──────────────────────────────────────────────────────────────

function DomainsList({ domains }: { domains: string[] }) {
  if (domains.length === 0) return null;
  return (
    <div className="space-y-1">
      <p className="type-label-sm text-[var(--text-tertiary)] uppercase tracking-wide">
        SSO-enrolled domains
      </p>
      <div className="flex min-w-0 max-w-full flex-wrap gap-2">
        {domains.map((domain) => (
          <code
            key={domain}
            title={domain}
            className="inline-block max-w-full min-w-0 break-all rounded bg-[var(--surface-active)] px-2 py-0.5 font-mono text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]"
          >
            {domain}
          </code>
        ))}
      </div>
    </div>
  );
}

interface SSOSettingsViewModel {
  accessRestricted: boolean;
  configurePending: boolean;
  configureRecovery: ConfigureRecovery | null;
  detailsOpen: boolean;
  disableRequested: boolean;
  hasStatusError: boolean;
  instructions: SSOConfigureResponse | null;
  isLoading: boolean;
  providerStatusUnavailable: boolean;
  showDisableConfirmation: boolean;
  showInstructions: boolean;
  ssoActionDisabled: boolean;
  ssoActionLabel: string;
  statusDashboardUrl: string | null;
  statusData: SSOStatus | undefined;
  statusUnavailable: boolean;
}

interface SSOSettingsViewActions {
  onCancelDisable: () => void;
  onConfigure: () => void;
  onConfirmDisable: () => void;
  onDismissInstructions: () => void;
  onReconcileConfigure: () => void;
  onRetryStatus: () => void;
  onToggleDetails: () => void;
}

function getSSOActionLabel(status: SSOStatus["status"] | undefined): string {
  if (status === "active") return "Start disable request";
  if (status === "pending") return "Continue SSO setup";
  return "Start SSO setup";
}

function SSOSettingsHeader({
  model,
  onToggleDetails,
}: {
  model: SSOSettingsViewModel;
  onToggleDetails: () => void;
}) {
  return (
    <CardHeader className="flex flex-col gap-4 pb-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-3 min-w-0">
        <ShieldCheck
          className="h-5 w-5 flex-none text-[var(--text-tertiary)]"
          aria-hidden="true"
        />
        <div className="min-w-0">
          <CardTitle
            className="text-sm leading-snug"
            role="heading"
            aria-level={3}
          >
            Single sign-on (SSO)
          </CardTitle>
          <p className="type-body-xs text-[var(--text-tertiary)] mt-0.5">
            SAML 2.0 / OIDC via Clerk Enterprise Connections
          </p>
        </div>
      </div>

      <div className="flex flex-none flex-wrap items-center gap-3">
        {model.isLoading ? (
          <span role="status" aria-label="Loading SSO status">
            <Loader2
              className="h-4 w-4 animate-spin motion-reduce:animate-none text-[var(--text-tertiary)]"
              aria-hidden="true"
            />
          </span>
        ) : model.statusUnavailable ? (
          <Badge variant="secondary" className="gap-1">
            <AlertTriangle className="h-3 w-3" aria-hidden="true" />
            Unavailable
          </Badge>
        ) : (
          <SSOStatusBadge status={model.statusData?.status ?? "inactive"} />
        )}
        {!model.statusUnavailable ? (
          <Button
            variant="outline"
            size="sm"
            className="min-h-11 gap-1"
            onClick={onToggleDetails}
            aria-expanded={model.detailsOpen}
            aria-controls="sso-details-panel"
          >
            {model.detailsOpen ? (
              <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            {model.detailsOpen ? "Hide" : "Manage"}
          </Button>
        ) : null}
      </div>
    </CardHeader>
  );
}

function SSOStatusAlert({
  accessRestricted,
  onRetryStatus,
  show,
}: {
  accessRestricted: boolean;
  onRetryStatus: () => void;
  show: boolean;
}) {
  if (!show) return null;

  return (
    <div
      role="alert"
      className="rounded-lg border border-error/20 bg-error/10 px-4 py-3"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle
          className="mt-0.5 h-5 w-5 shrink-0 text-error"
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-[var(--text-primary)]">
            {accessRestricted
              ? "SSO access restricted"
              : "SSO status temporarily unavailable"}
          </p>
          <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
            {accessRestricted
              ? "Your current session is not authorized to view or update SSO configuration. Cached identity provider details are hidden until access is confirmed again."
              : "Live single sign-on status is unavailable. Cached identity provider details may be stale, and SSO changes stay locked until a successful refresh."}
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-3 min-h-11 gap-2"
            onClick={onRetryStatus}
          >
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            Retry SSO status
          </Button>
        </div>
      </div>
    </div>
  );
}

function SSOConfigureRecoveryAlert({
  configurePending,
  onReconcileConfigure,
  recovery,
}: {
  configurePending: boolean;
  onReconcileConfigure: () => void;
  recovery: ConfigureRecovery | null;
}) {
  if (!recovery) return null;

  const retrySafe = recovery.mode === "retry_safe";
  const checking = recovery.mode === "checking";
  return (
    <div
      role="alert"
      aria-live="polite"
      aria-atomic="true"
      className={`rounded-lg border px-4 py-3 ${
        retrySafe
          ? "border-error/25 bg-error/10"
          : "border-warning/25 bg-warning/10"
      }`}
      data-testid="sso-configuration-error"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <AlertTriangle
            className="mt-0.5 h-5 w-5 shrink-0 text-error"
            aria-hidden="true"
          />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {retrySafe
                ? "SSO change not found after status refresh"
                : "SSO change outcome unknown"}
            </p>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              {retrySafe
                ? "Current SSO status does not show the requested change. It is now safe to retry the same request."
                : checking
                  ? "Checking authoritative SSO status before allowing any retry."
                  : "The server may have applied this change. Check authoritative SSO status before retrying."}
            </p>
          </div>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="min-h-11 shrink-0"
          onClick={onReconcileConfigure}
          loading={configurePending || checking}
          disabled={configurePending || checking}
        >
          {retrySafe
            ? "Retry SSO change"
            : checking
              ? "Checking SSO status..."
              : "Check SSO status"}
        </Button>
      </div>
    </div>
  );
}

function SSOProviderDetails({
  isLoading,
  status,
}: {
  isLoading: boolean;
  status: SSOStatus | undefined;
}) {
  if (!status || isLoading) return null;

  return (
    <div className="space-y-4">
      {status.provider ? (
        <div className="space-y-1">
          <p className="type-label-sm text-[var(--text-tertiary)] uppercase tracking-wide">
            Identity provider
          </p>
          <p className="type-body-sm text-[var(--text-primary)] font-medium">
            {status.provider}
          </p>
        </div>
      ) : null}

      <DomainsList domains={status.domains} />

      {status.status === "inactive" ? (
        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)] px-4 py-3 space-y-1">
          <p className="type-body-sm text-[var(--text-secondary)] font-medium">
            SSO not yet configured
          </p>
          <p className="type-body-xs text-[var(--text-tertiary)]">
            SSO configuration requires admin access to your Identity Provider
            (Okta, Azure AD, Google Workspace, etc.) and is completed via the
            Clerk dashboard. An identified deployment operator must own and
            support that configuration.
          </p>
        </div>
      ) : null}

      {status.status === "pending" ? (
        <div className="rounded-lg border border-warning/25 bg-warning/5 px-4 py-3">
          <p className="type-body-xs text-[var(--text-secondary)]">
            An SSO connection is configured but not yet active. Complete the IdP
            setup in the Clerk dashboard to activate it.
          </p>
        </div>
      ) : null}
    </div>
  );
}

function SSODisableConfirmation({
  actionDisabled,
  configurePending,
  onCancel,
  onConfirm,
  show,
}: {
  actionDisabled: boolean;
  configurePending: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  show: boolean;
}) {
  if (!show) return null;

  return (
    <div
      role="alert"
      className="space-y-3 rounded-lg border border-error/25 bg-error/10 px-4 py-3"
    >
      <div className="space-y-1">
        <p className="type-body-sm font-semibold text-[var(--text-primary)]">
          Confirm SSO disable request
        </p>
        <p className="type-body-xs leading-6 text-[var(--text-secondary)]">
          SSO stays active until the Clerk disable workflow is completed.
          Confirm only after you have verified the fallback sign-in path for
          enrolled domains.
        </p>
      </div>
      <div className="flex flex-wrap justify-end gap-2">
        <Button
          variant="ghost"
          size="sm"
          className="min-h-11"
          onClick={onCancel}
          disabled={configurePending}
        >
          Cancel
        </Button>
        <Button
          variant="destructive"
          size="sm"
          className="min-h-11"
          onClick={onConfirm}
          loading={configurePending}
          disabled={actionDisabled}
        >
          Confirm disable request
        </Button>
      </div>
    </div>
  );
}

function SSOConfigurationInstructions({
  disableRequested,
  instructions,
  onDismiss,
  show,
}: {
  disableRequested: boolean;
  instructions: SSOConfigureResponse | null;
  onDismiss: () => void;
  show: boolean;
}) {
  if (!show || !instructions) return null;

  return (
    <div className="space-y-3">
      {disableRequested ? (
        <div className="rounded-lg border border-warning/30 bg-warning/10 px-4 py-3">
          <p className="type-body-sm font-medium text-warning">
            SSO is still active — follow the steps below to complete disabling
            it.
          </p>
        </div>
      ) : null}
      <InstructionsPanel result={instructions} onDismiss={onDismiss} />
    </div>
  );
}

function SSOActionBar({
  actionDisabled,
  actionLabel,
  configurePending,
  onConfigure,
  status,
  statusDashboardUrl,
}: {
  actionDisabled: boolean;
  actionLabel: string;
  configurePending: boolean;
  onConfigure: () => void;
  status: SSOStatus | undefined;
  statusDashboardUrl: string | null;
}) {
  if (!status) return null;

  return (
    <div className="flex flex-wrap items-center gap-3 pt-1 border-t border-[var(--border-subtle)]">
      <Button
        variant={status.status === "active" ? "outline" : "default"}
        size="sm"
        className="min-h-11"
        onClick={onConfigure}
        loading={configurePending}
        disabled={actionDisabled}
      >
        {actionLabel}
      </Button>

      {statusDashboardUrl ? (
        <Button asChild variant="ghost" size="sm" className="min-h-11 gap-1.5">
          <a
            href={statusDashboardUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open Clerk Dashboard
            <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
          </a>
        </Button>
      ) : null}
    </div>
  );
}

function SSODashboardLinkWarning({
  hasStatusError,
  status,
  statusDashboardUrl,
}: {
  hasStatusError: boolean;
  status: SSOStatus | undefined;
  statusDashboardUrl: string | null;
}) {
  if (hasStatusError || !status?.clerk_dashboard_url || statusDashboardUrl) {
    return null;
  }

  return (
    <p role="alert" className="type-body-xs text-error">
      The identity-provider dashboard link was rejected because it did not match
      Praviar&apos;s trusted Clerk destination.
    </p>
  );
}

function SSOSettingsDetails({
  actions,
  model,
}: {
  actions: SSOSettingsViewActions;
  model: SSOSettingsViewModel;
}) {
  if (!model.detailsOpen) return null;

  return (
    <CardContent
      id="sso-details-panel"
      className="pt-0 space-y-5"
      role="region"
      aria-label="SSO configuration details"
    >
      <SSOStatusAlert
        accessRestricted={model.accessRestricted}
        onRetryStatus={actions.onRetryStatus}
        show={model.hasStatusError || model.providerStatusUnavailable}
      />
      <SSOConfigureRecoveryAlert
        configurePending={model.configurePending}
        onReconcileConfigure={actions.onReconcileConfigure}
        recovery={model.statusUnavailable ? null : model.configureRecovery}
      />
      <SSOProviderDetails
        isLoading={model.isLoading}
        status={model.statusData}
      />
      <SSODisableConfirmation
        actionDisabled={model.ssoActionDisabled}
        configurePending={model.configurePending}
        onCancel={actions.onCancelDisable}
        onConfirm={actions.onConfirmDisable}
        show={model.showDisableConfirmation}
      />
      <SSOConfigurationInstructions
        disableRequested={model.disableRequested}
        instructions={model.instructions}
        onDismiss={actions.onDismissInstructions}
        show={model.showInstructions && !model.statusUnavailable}
      />
      <SSOActionBar
        actionDisabled={model.ssoActionDisabled}
        actionLabel={model.ssoActionLabel}
        configurePending={model.configurePending}
        onConfigure={actions.onConfigure}
        status={model.isLoading ? undefined : model.statusData}
        statusDashboardUrl={model.statusDashboardUrl}
      />
      <SSODashboardLinkWarning
        hasStatusError={model.hasStatusError}
        status={model.statusData}
        statusDashboardUrl={model.statusDashboardUrl}
      />
    </CardContent>
  );
}

function SSOSettingsView({
  actions,
  model,
}: {
  actions: SSOSettingsViewActions;
  model: SSOSettingsViewModel;
}) {
  return (
    <Card id="single-sign-on" className="scroll-mt-20" tabIndex={-1}>
      <SSOSettingsHeader
        model={model}
        onToggleDetails={actions.onToggleDetails}
      />
      <SSOSettingsDetails actions={actions} model={model} />
    </Card>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function SSOSettings() {
  const { data, isLoading, error, refetch } = useSSOStatus();
  const configureSSO = useConfigureSSO();
  const { addToast } = useToastStore();

  const [showInstructions, setShowInstructions] = useState(false);
  const [instructions, setInstructions] = useState<SSOConfigureResponse | null>(
    null,
  );
  const [disableRequested, setDisableRequested] = useState(false);
  const [disableConfirmationOpen, setDisableConfirmationOpen] = useState(false);
  const [configureRecovery, setConfigureRecovery] =
    useState<ConfigureRecovery | null>(null);
  const [expanded, setExpanded] = useState(false);
  const accessRestricted = isAuthBoundaryError(error);
  const statusData = accessRestricted ? undefined : data;
  const providerStatusUnavailable = Boolean(
    statusData && !hasFreshSSOStatus(statusData),
  );
  const statusUnavailable = Boolean(error || providerStatusUnavailable);
  const showDisableConfirmation =
    disableConfirmationOpen && statusData?.status === "active";
  const statusDashboardUrl = validatedClerkDashboardUrl(
    statusUnavailable ? null : statusData?.clerk_dashboard_url,
    { demoMode: DEMO_MODE_ENABLED },
  );
  const detailsOpen = expanded || statusUnavailable;

  const submitConfigure = (enable: boolean) => {
    // A new provider request invalidates instructions from the previous
    // action. Keeping them visible while this request is pending (or after it
    // fails) can attach setup guidance to a disable attempt, and vice versa.
    setShowInstructions(false);
    setInstructions(null);
    setConfigureRecovery(null);
    configureSSO.mutate(enable, {
      onSuccess: (result) => {
        setConfigureRecovery(null);
        setDisableRequested(!enable);
        setInstructions(result);
        setShowInstructions(true);
        setDisableConfirmationOpen(false);
        setExpanded(true);
      },
      onError: () => {
        console.error("[SSOSettings] Failed to update SSO configuration");
        setConfigureRecovery({ enable, mode: "outcome_unknown" });
        addToast(
          "SSO change outcome is unconfirmed. Check current SSO status before retrying.",
          "warning",
        );
      },
    });
  };

  const reconcileConfigure = async () => {
    if (!configureRecovery || configureRecovery.mode === "checking") return;
    if (configureRecovery.mode === "retry_safe") {
      submitConfigure(configureRecovery.enable);
      return;
    }

    const requestedEnable = configureRecovery.enable;
    setConfigureRecovery({ enable: requestedEnable, mode: "checking" });
    try {
      const result = await refetch();
      const refreshedStatus = result.data;
      if (
        result.error ||
        !refreshedStatus ||
        !hasFreshSSOStatus(refreshedStatus)
      ) {
        setConfigureRecovery({
          enable: requestedEnable,
          mode: "outcome_unknown",
        });
        return;
      }

      const wasApplied = requestedEnable
        ? refreshedStatus.status !== "inactive"
        : refreshedStatus.status === "inactive";
      if (wasApplied) {
        setConfigureRecovery(null);
        addToast(
          requestedEnable
            ? "SSO setup request confirmed in current status."
            : "SSO disable request confirmed in current status.",
          "success",
        );
        return;
      }

      setConfigureRecovery({
        enable: requestedEnable,
        mode: "retry_safe",
      });
    } catch {
      setConfigureRecovery({
        enable: requestedEnable,
        mode: "outcome_unknown",
      });
    }
  };

  const handleConfigure = () => {
    if (!statusData) {
      return;
    }

    if (statusData.status === "active") {
      setDisableConfirmationOpen(true);
      return;
    }

    setDisableConfirmationOpen(false);
    submitConfigure(true);
  };

  const handleConfirmDisable = () => {
    submitConfigure(false);
  };

  const ssoActionDisabled =
    configureSSO.isPending || isLoading || !statusData || statusUnavailable;
  const ssoActionLabel = getSSOActionLabel(statusData?.status);
  const retryStatus = () => {
    void refetch();
  };
  const reconcileStatus = () => {
    void reconcileConfigure();
  };
  const cancelDisable = () => {
    setDisableConfirmationOpen(false);
  };
  const dismissInstructions = () => {
    setShowInstructions(false);
  };
  const toggleDetails = () => {
    setExpanded((value) => !value);
  };
  const model: SSOSettingsViewModel = {
    accessRestricted,
    configurePending: configureSSO.isPending,
    configureRecovery,
    detailsOpen,
    disableRequested,
    hasStatusError: Boolean(error),
    instructions,
    isLoading,
    providerStatusUnavailable,
    showDisableConfirmation,
    showInstructions,
    ssoActionDisabled,
    ssoActionLabel,
    statusDashboardUrl,
    statusData,
    statusUnavailable,
  };
  const actions: SSOSettingsViewActions = {
    onCancelDisable: cancelDisable,
    onConfigure: handleConfigure,
    onConfirmDisable: handleConfirmDisable,
    onDismissInstructions: dismissInstructions,
    onReconcileConfigure: reconcileStatus,
    onRetryStatus: retryStatus,
    onToggleDetails: toggleDetails,
  };

  return <SSOSettingsView actions={actions} model={model} />;
}
